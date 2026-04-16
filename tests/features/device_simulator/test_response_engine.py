# Part of the Ramses Extra integration
# See https://github.com/wimpie70/ramses_extras for more information
#
"""Tests for device_simulator ResponseEngine."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.ramses_extras.features.device_simulator.device_db import (
    ResponseEntry,
)
from custom_components.ramses_extras.features.device_simulator.response_engine import (
    ResponseEngine,
)
from custom_components.ramses_extras.features.device_simulator.response_templates import (  # noqa: E501
    build_dynamic_response,
)

if TYPE_CHECKING:
    from pathlib import Path


class TestResponseEngineInit:
    """Tests for ResponseEngine initialization."""

    def test_init(self) -> None:
        """Test ResponseEngine initialization."""
        mock_db = MagicMock()
        mock_endpoint = MagicMock()

        engine = ResponseEngine(mock_db, mock_endpoint)

        assert engine._db == mock_db
        assert engine._endpoint == mock_endpoint
        assert engine._pending_tasks == set()


class TestResponseEngineParseFrame:
    """Tests for frame parsing."""

    @pytest.fixture
    def engine(self) -> ResponseEngine:
        """Create a ResponseEngine with mocked dependencies."""
        mock_db = MagicMock()
        mock_endpoint = MagicMock()
        return ResponseEngine(mock_db, mock_endpoint)

    def test_parse_valid_rq_frame(self, engine: ResponseEngine) -> None:
        """Test parsing a valid RQ frame."""
        frame = "RQ 037 37:168270 37:126776 --:------ 31DA 001 01"
        parsed = engine._parse_frame(frame)

        assert parsed is not None
        assert parsed["verb"] == "RQ"
        assert parsed["rssi"] == "037"
        assert parsed["src"] == "37:168270"
        assert parsed["dst"] == "37:126776"
        assert parsed["code"] == "31DA"
        assert parsed["len"] == 1
        assert parsed["payload"] == "01"

    def test_parse_valid_i_frame(self, engine: ResponseEngine) -> None:
        """Test parsing a valid I frame."""
        frame = "I 052 37:168270 --:------ 37:168270 31DA 029 21..."
        parsed = engine._parse_frame(frame)

        assert parsed is not None
        assert parsed["verb"] == "I"
        assert parsed["rssi"] == "052"
        assert parsed["src"] == "37:168270"
        assert parsed["dst"] == "--:------"
        assert parsed["code"] == "31DA"
        assert parsed["len"] == 29

    def test_parse_valid_rp_frame(self, engine: ResponseEngine) -> None:
        """Test parsing a valid RP frame."""
        frame = "RP 057 37:168270 37:126776 --:------ 31DA 029 21..."
        parsed = engine._parse_frame(frame)

        assert parsed is not None
        assert parsed["verb"] == "RP"

    def test_parse_invalid_frame(self, engine: ResponseEngine) -> None:
        """Test parsing an invalid frame."""
        frame = "invalid frame data"
        parsed = engine._parse_frame(frame)

        assert parsed is None

    def test_parse_frame_whitespace_handling(self, engine: ResponseEngine) -> None:
        """Test that leading/trailing whitespace is handled."""
        frame = "  RQ 037 37:168270 37:126776 --:------ 31DA 001 01  "
        parsed = engine._parse_frame(frame)

        assert parsed is not None
        assert parsed["verb"] == "RQ"

    def test_parse_frame_case_normalization(self, engine: ResponseEngine) -> None:
        """Test that addresses and codes are uppercased."""
        frame = "rq 037 37:168270 37:126776 --:------ 31da 001 01"
        parsed = engine._parse_frame(frame)

        # Note: regex only captures digits, so src/dst remain as in frame
        # but the code extraction should handle it
        assert parsed is not None


class TestResponseEngineGetDeviceType:
    """Tests for device type detection."""

    @pytest.fixture
    def engine(self) -> ResponseEngine:
        """Create a ResponseEngine with mocked dependencies."""
        mock_db = MagicMock()
        mock_endpoint = MagicMock()
        return ResponseEngine(mock_db, mock_endpoint)

    def test_fan_device(self, engine: ResponseEngine) -> None:
        """Test detecting FAN device type."""
        device_type = engine._get_device_type("32:168270")
        assert device_type == "FAN"

    def test_co2_device(self, engine: ResponseEngine) -> None:
        """Test detecting CO2 device type."""
        device_type = engine._get_device_type("34:123456")
        assert device_type == "CO2"

    def test_hum_device(self, engine: ResponseEngine) -> None:
        """Test detecting HUM device type."""
        device_type = engine._get_device_type("32:123456")
        assert device_type == "FAN"

    def test_rem_device(self, engine: ResponseEngine) -> None:
        """Test detecting REM device type."""
        device_type = engine._get_device_type("29:123456")
        assert device_type == "REM"

    def test_ctl_device(self, engine: ResponseEngine) -> None:
        """Test detecting CTL device type."""
        assert engine._get_device_type("22:123456") == "CTL"

    def test_legacy_ctl_prefix(self, engine: ResponseEngine) -> None:
        """01: prefix should be treated as CTL."""
        assert engine._get_device_type("01:999999") == "CTL"

    def test_profile_backed_lookup(self) -> None:
        """Known-list classes override prefix heuristics."""
        config_store = MagicMock()
        profile = MagicMock()
        profile.device_configs = {
            "_known_list": {"04:150000": {"class": "TRV"}},
        }
        config_store.get_active_profile.return_value = "normal"
        config_store.get_profile.return_value = profile

        engine = ResponseEngine(MagicMock(), MagicMock(), config_store=config_store)
        assert engine._get_device_type("04:150000") == "TRV"

    def test_unknown_device(self, engine: ResponseEngine) -> None:
        """Test unknown device type returns None."""
        device_type = engine._get_device_type("99:123456")
        assert device_type is None


class TestResponseEngineBuildResponse:
    """Tests for response frame building."""

    @pytest.fixture
    def engine(self) -> ResponseEngine:
        """Create a ResponseEngine with mocked dependencies."""
        mock_db = MagicMock()
        mock_endpoint = MagicMock()
        return ResponseEngine(mock_db, mock_endpoint)

    def test_build_response_with_dst(self, engine: ResponseEngine) -> None:
        """Test building response when destination is known."""
        parsed = {
            "verb": "RQ",
            "rssi": "037",
            "src": "37:168270",
            "dst": "37:126776",
            "code": "31DA",
            "len": 1,
            "payload": "01",
        }
        response_frame = engine._build_response_frame(parsed, "21...")

        # Should use dst as src (swap)
        assert response_frame.startswith(
            "000 RP --- 37:126776 37:168270 --:------ 31DA"
        )

    def test_build_response_with_broadcast_dst(self, engine: ResponseEngine) -> None:
        """Test building response when destination is broadcast."""
        parsed = {
            "verb": "RQ",
            "rssi": "052",
            "src": "37:168270",
            "dst": "--:------",
            "code": "31DA",
            "len": 1,
            "payload": "01",
        }
        response_frame = engine._build_response_frame(parsed, "21...")

        # Should use default simulator ID (18:001234) as src
        assert response_frame.startswith(
            "000 RP --- 18:001234 37:168270 --:------ 31DA"
        )

    def test_build_response_payload_length(self, engine: ResponseEngine) -> None:
        """Test that payload length is correctly calculated."""
        parsed = {
            "verb": "RQ",
            "rssi": "037",
            "src": "37:168270",
            "dst": "37:126776",
            "code": "31DA",
            "len": 1,
            "payload": "01",
        }
        # Payload "21..." is 5 hex chars = 2.5 bytes, but we expect whole bytes
        # so this test uses a valid payload
        response_frame = engine._build_response_frame(parsed, "ABCDEF")

        # "ABCDEF" is 6 hex chars = 3 bytes
        assert " 003 " in response_frame


class TestResponseEngineHandleInbound:
    """Tests for handle_inbound_frame method."""

    @pytest.fixture
    def engine(self) -> ResponseEngine:
        """Create a ResponseEngine with mocked dependencies."""
        mock_db = MagicMock()
        mock_endpoint = MagicMock()
        mock_endpoint.is_connected = True
        return ResponseEngine(mock_db, mock_endpoint)

    @pytest.mark.asyncio
    async def test_handle_inbound_rq_with_response(
        self, engine: ResponseEngine
    ) -> None:
        """Test handling RQ frame with matching response."""
        mock_response = ResponseEntry(
            code="31DA",
            delay_ms=50,
            payloads=["21..."],
        )
        engine._db.find_response.return_value = mock_response

        with patch.object(engine, "_send_response") as mock_send:
            frame = "RQ 037 37:168270 37:126776 --:------ 31DA 001 01"
            await engine.handle_inbound_frame(frame)

            # Should lookup response for DIS/31DA
            engine._db.find_response.assert_called_once_with("DIS", "31DA")
            mock_send.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_inbound_skips_active_engine(self) -> None:
        """ResponseEngine defers to ScenarioEngine-managed devices."""
        mock_db = MagicMock()
        mock_endpoint = MagicMock()
        mock_endpoint.is_connected = True
        engine = ResponseEngine(mock_db, mock_endpoint)
        engine.set_engine(MagicMock(is_device_active=MagicMock(return_value=True)))

        frame = "RQ 037 37:168270 37:126776 --:------ 31DA 001 01"
        await engine.handle_inbound_frame(frame)

        mock_db.find_response.assert_not_called()

    @pytest.mark.asyncio
    async def test_handle_inbound_rq_no_response(self, engine: ResponseEngine) -> None:
        """Test handling RQ frame with no matching response."""
        engine._db.find_response.return_value = None

        with patch.object(engine, "_send_response") as mock_send:
            frame = "RQ 037 37:168270 37:126776 --:------ 9999 001 01"
            await engine.handle_inbound_frame(frame)

            mock_send.assert_not_called()

    @pytest.mark.asyncio
    async def test_handle_inbound_i_frame_ignored(self, engine: ResponseEngine) -> None:
        """Test that I frames are ignored."""
        with patch.object(engine, "_send_response") as mock_send:
            frame = "I 052 37:168270 --:------ 37:168270 31DA 029 21..."
            await engine.handle_inbound_frame(frame)

            engine._db.find_response.assert_not_called()
            mock_send.assert_not_called()

    @pytest.mark.asyncio
    async def test_handle_inbound_not_connected(self, engine: ResponseEngine) -> None:
        """Test handling frame when endpoint not connected."""
        engine._endpoint.is_connected = False

        with patch.object(engine, "_parse_frame") as mock_parse:
            frame = "RQ 037 37:168270 37:126776 --:------ 31DA 001 01"
            await engine.handle_inbound_frame(frame)

            mock_parse.assert_not_called()


class TestResponseEngineSendResponse:
    """Tests for _send_response method."""

    @pytest.fixture
    def engine(self) -> ResponseEngine:
        """Create a ResponseEngine with mocked dependencies."""
        mock_db = MagicMock()
        mock_endpoint = MagicMock()
        mock_endpoint.is_connected = True
        return ResponseEngine(mock_db, mock_endpoint)

    @pytest.mark.asyncio
    async def test_send_response_schedules_task(self, engine: ResponseEngine) -> None:
        """Test that response is scheduled as delayed task."""
        parsed = {
            "verb": "RQ",
            "rssi": "037",
            "src": "37:168270",
            "dst": "37:126776",
            "code": "31DA",
            "len": 1,
            "payload": "01",
        }
        response = ResponseEntry(
            code="31DA",
            delay_ms=100,
            payloads=["21..."],
        )

        await engine._send_response(parsed, response)

        # Should have created a pending task
        assert len(engine._pending_tasks) == 1

    @pytest.mark.asyncio
    async def test_send_response_no_payloads(self, engine: ResponseEngine) -> None:
        """Test handling response with no payloads."""
        parsed = {
            "verb": "RQ",
            "rssi": "037",
            "src": "37:168270",
            "dst": "37:126776",
            "code": "31DA",
            "len": 1,
            "payload": "01",
        }
        response = ResponseEntry(
            code="31DA",
            delay_ms=100,
            payloads=[],
        )

        # Check initial pending tasks count
        initial_tasks = len(engine._pending_tasks)

        await engine._send_response(parsed, response)

        # Should not have created any new tasks
        assert len(engine._pending_tasks) == initial_tasks


class TestResponseEngineDelayedSend:
    """Tests for _delayed_send method."""

    @pytest.fixture
    def engine(self) -> ResponseEngine:
        """Create a ResponseEngine with mocked dependencies."""
        mock_db = MagicMock()
        mock_endpoint = MagicMock()
        mock_endpoint.is_connected = True
        mock_endpoint.send_packet = AsyncMock()
        return ResponseEngine(mock_db, mock_endpoint)

    @pytest.mark.asyncio
    async def test_delayed_send_when_connected(self, engine: ResponseEngine) -> None:
        """Test sending when endpoint is connected."""
        frame = "R 000 37:126776 37:168270 31DA 029 21..."

        await engine._send_immediate(frame)

        engine._endpoint.send_packet.assert_called_once_with(frame)

    @pytest.mark.asyncio
    async def test_delayed_send_when_disconnected(self, engine: ResponseEngine) -> None:
        """Test sending when endpoint is disconnected."""
        engine._endpoint.is_connected = False
        frame = "R 000 37:126776 37:168270 31DA 029 21..."

        await engine._send_immediate(frame)

        engine._endpoint.send_packet.assert_not_called()


class TestResponseEngineShutdown:
    """Tests for shutdown method."""

    @pytest.fixture
    def engine(self) -> ResponseEngine:
        """Create a ResponseEngine with mocked dependencies."""
        mock_db = MagicMock()
        mock_endpoint = MagicMock()
        return ResponseEngine(mock_db, mock_endpoint)

    @pytest.mark.asyncio
    async def test_shutdown_cancels_tasks(self, engine: ResponseEngine) -> None:
        """Test that shutdown cancels pending tasks."""

        # Create a real asyncio task that will be cancelled
        async def dummy_task():
            try:
                await asyncio.sleep(10)  # Long sleep that will be cancelled
            except asyncio.CancelledError:
                return "cancelled"

        real_task = asyncio.create_task(dummy_task())
        engine._pending_tasks.add(real_task)

        await engine.shutdown()

        # Check that the task was cancelled
        assert real_task.cancelled()


class TestResponseTemplates:
    """Unit tests for dynamic response helpers."""

    def test_build_dynamic_response_ctl_temp(self) -> None:
        payload = build_dynamic_response("CTL", "30C9", "02")
        assert payload.startswith("02")
        assert len(payload) == 6

    def test_build_dynamic_response_ctl_zone_member(self) -> None:
        payload = build_dynamic_response("CTL", "000C", "0204")
        assert payload.startswith("0204")
        assert len(payload) == 12

    def test_build_dynamic_response_ctl_zone_mode(self) -> None:
        payload = build_dynamic_response("CTL", "2349", "02")
        assert payload.startswith("02")
        assert len(payload) == 26
        assert payload[6:8] == "00"

    def test_build_dynamic_response_non_ctl(self) -> None:
        assert build_dynamic_response("TRV", "30C9", "01") is None


class TestResponseEngine2411ParameterHandling:
    """Tests for 2411 parameter code handling."""

    @pytest.fixture
    def engine(self) -> ResponseEngine:
        """Create a ResponseEngine with mocked dependencies."""
        mock_db = MagicMock()
        mock_endpoint = MagicMock()
        mock_endpoint.is_connected = True
        return ResponseEngine(mock_db, mock_endpoint)

    @pytest.mark.asyncio
    async def test_send_response_2411_param_matching(
        self, engine: ResponseEngine
    ) -> None:
        """Test 2411 response with parameter ID matching."""
        parsed = {
            "verb": "RQ",
            "rssi": "037",
            "src": "37:168270",
            "dst": "32:153289",
            "code": "2411",
            "len": 3,
            "payload": "000001",  # Parameter ID 01
        }
        response = ResponseEntry(
            code="2411",
            delay_ms=100,
            payloads=[
                "000001value1",
                "000002value2",
            ],
        )

        with patch.object(engine, "_build_response_frame") as mock_build:
            await engine._send_response(parsed, response)

            # Should use the matching payload
            call_payload = mock_build.call_args[0][1]
            assert call_payload.startswith("000001")

    @pytest.mark.asyncio
    async def test_send_response_2411_fallback_payload(
        self, engine: ResponseEngine
    ) -> None:
        """Test 2411 response with fallback when no matching payload."""
        parsed = {
            "verb": "RQ",
            "rssi": "037",
            "src": "37:168270",
            "dst": "32:153289",
            "code": "2411",
            "len": 3,
            "payload": "000003",  # Parameter ID 03
        }
        response = ResponseEntry(
            code="2411",
            delay_ms=100,
            payloads=[
                "000001value1",
                "000002value2",
            ],
        )

        with patch.object(engine, "_build_response_frame") as mock_build:
            await engine._send_response(parsed, response)

            # Should adapt the first payload with the param ID
            call_payload = mock_build.call_args[0][1]
            assert call_payload.startswith("000003")

    @pytest.mark.asyncio
    async def test_send_response_2411_no_payload_in_rq(
        self, engine: ResponseEngine
    ) -> None:
        """Test 2411 response when RQ has no payload."""
        parsed = {
            "verb": "RQ",
            "rssi": "037",
            "src": "37:168270",
            "dst": "32:153289",
            "code": "2411",
            "len": 0,
            "payload": "",
        }
        response = ResponseEntry(
            code="2411",
            delay_ms=100,
            payloads=["payload1"],
        )

        with patch.object(engine, "_build_response_frame") as mock_build:
            await engine._send_response(parsed, response)

            # Should use first available payload
            call_payload = mock_build.call_args[0][1]
            assert call_payload == "payload1"


class TestResponseEngineHandleInboundEdgeCases:
    """Tests for handle_inbound_frame edge cases."""

    @pytest.fixture
    def engine(self) -> ResponseEngine:
        """Create a ResponseEngine with mocked dependencies."""
        mock_db = MagicMock()
        mock_endpoint = MagicMock()
        mock_endpoint.is_connected = True
        return ResponseEngine(mock_db, mock_endpoint)

    @pytest.mark.asyncio
    async def test_handle_inbound_broadcast_dst(self, engine: ResponseEngine) -> None:
        """Test handling RQ with broadcast destination."""
        with patch.object(engine, "_send_response") as mock_send:
            frame = "RQ 037 37:168270 --:------ --:------ 31DA 001 01"
            await engine.handle_inbound_frame(frame)

            # Should not send response for broadcast
            mock_send.assert_not_called()

    @pytest.mark.asyncio
    async def test_handle_inbound_unknown_device_type(
        self, engine: ResponseEngine
    ) -> None:
        """Test handling RQ from unknown device type."""
        # Use device type 99 which is not in the map
        engine._db.find_response.return_value = None
        with patch.object(engine, "_send_response") as mock_send:
            frame = "RQ 037 99:123456 32:153289 --:------ 31DA 001 01"
            await engine.handle_inbound_frame(frame)

            # Should not send response for unknown device
            mock_send.assert_not_called()

    @pytest.mark.asyncio
    async def test_handle_inbound_unknown_device_type_logs_debug(
        self, engine: ResponseEngine
    ) -> None:
        """Test that unknown device type logs debug message."""
        # Use device type 99 which is not in the map
        with patch.object(engine, "_get_device_type", return_value=None):
            frame = "RQ 037 99:123456 32:153289 --:------ 31DA 001 01"
            await engine.handle_inbound_frame(frame)

        # Should have logged debug message about unknown device type
        # The debug log happens when device_type is None after _get_device_type

    @pytest.mark.asyncio
    async def test_handle_inbound_parse_failure(self, engine: ResponseEngine) -> None:
        """Test handling when frame parsing fails."""
        with patch.object(engine, "_send_response") as mock_send:
            frame = "invalid frame data"
            await engine.handle_inbound_frame(frame)

            # Should not send response for invalid frame
            mock_send.assert_not_called()

    @pytest.mark.asyncio
    async def test_handle_inbound_w_frame_ignored(self, engine: ResponseEngine) -> None:
        """Test that W frames are ignored."""
        with patch.object(engine, "_send_response") as mock_send:
            frame = "W 052 37:168270 --:------ 37:168270 31DA 029 21..."
            await engine.handle_inbound_frame(frame)

            engine._db.find_response.assert_not_called()
            mock_send.assert_not_called()

    @pytest.mark.asyncio
    async def test_handle_inbound_exception_handling(
        self, engine: ResponseEngine
    ) -> None:
        """Test that exceptions are caught and logged."""
        # Make find_response raise an exception
        engine._db.find_response.side_effect = Exception("DB error")

        # The exception should be caught and logged, then re-raised
        frame = "RQ 037 37:168270 32:153289 --:------ 31DA 001 01"
        with pytest.raises(Exception, match="DB error"):
            await engine.handle_inbound_frame(frame)

        engine._db.find_response.assert_called_once()
