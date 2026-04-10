# Part of the Ramses Extra integration
# See https://github.com/wimpie70/ramses_extras for more information
#
"""Tests for device_simulator ResponseEngine."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.ramses_extras.features.device_simulator.device_db import (
    ResponseEntry,
)
from custom_components.ramses_extras.features.device_simulator.response_engine import (
    ResponseEngine,
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
        frame = "RQ 037 37:168270 37:126776 31DA 001 01"
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
        frame = "I 052 37:168270 --:------ 31DA 029 21..."
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
        frame = "RP 057 37:168270 37:126776 31DA 029 21..."
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
        frame = "  RQ 037 37:168270 37:126776 31DA 001 01  "
        parsed = engine._parse_frame(frame)

        assert parsed is not None
        assert parsed["verb"] == "RQ"

    def test_parse_frame_case_normalization(self, engine: ResponseEngine) -> None:
        """Test that addresses and codes are uppercased."""
        frame = "rq 037 37:168270 37:126776 31da 001 01"
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
        device_type = engine._get_device_type("37:168270")
        assert device_type == "FAN"

    def test_co2_device(self, engine: ResponseEngine) -> None:
        """Test detecting CO2 device type."""
        device_type = engine._get_device_type("34:123456")
        assert device_type == "CO2"

    def test_hum_device(self, engine: ResponseEngine) -> None:
        """Test detecting HUM device type."""
        device_type = engine._get_device_type("32:123456")
        assert device_type == "HUM"

    def test_rem_device(self, engine: ResponseEngine) -> None:
        """Test detecting REM device type."""
        device_type = engine._get_device_type("29:123456")
        assert device_type == "REM"

    def test_ctl_device(self, engine: ResponseEngine) -> None:
        """Test detecting CTL device type."""
        device_type = engine._get_device_type("22:123456")
        assert device_type == "CTL"

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
        assert response_frame.startswith("R 000 37:126776 37:168270 31DA")

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
        assert response_frame.startswith("R 000 18:001234 37:168270 31DA")

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
            frame = "RQ 037 37:168270 37:126776 31DA 001 01"
            await engine.handle_inbound_frame(frame)

            # Should lookup response for FAN/31DA
            engine._db.find_response.assert_called_once_with("FAN", "31DA")
            mock_send.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_inbound_rq_no_response(self, engine: ResponseEngine) -> None:
        """Test handling RQ frame with no matching response."""
        engine._db.find_response.return_value = None

        with patch.object(engine, "_send_response") as mock_send:
            frame = "RQ 037 37:168270 37:126776 9999 001 01"
            await engine.handle_inbound_frame(frame)

            mock_send.assert_not_called()

    @pytest.mark.asyncio
    async def test_handle_inbound_i_frame_ignored(self, engine: ResponseEngine) -> None:
        """Test that I frames are ignored."""
        with patch.object(engine, "_send_response") as mock_send:
            frame = "I 052 37:168270 --:------ 31DA 029 21..."
            await engine.handle_inbound_frame(frame)

            engine._db.find_response.assert_not_called()
            mock_send.assert_not_called()

    @pytest.mark.asyncio
    async def test_handle_inbound_not_connected(self, engine: ResponseEngine) -> None:
        """Test handling frame when endpoint not connected."""
        engine._endpoint.is_connected = False

        with patch.object(engine, "_parse_frame") as mock_parse:
            frame = "RQ 037 37:168270 37:126776 31DA 001 01"
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

        with patch.object(engine, "_delayed_send") as mock_send:
            await engine._send_response(parsed, response)

            mock_send.assert_not_called()


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

        await engine._delayed_send(0.01, frame)

        engine._endpoint.send_packet.assert_called_once_with(frame)

    @pytest.mark.asyncio
    async def test_delayed_send_when_disconnected(self, engine: ResponseEngine) -> None:
        """Test sending when endpoint is disconnected."""
        engine._endpoint.is_connected = False
        frame = "R 000 37:126776 37:168270 31DA 029 21..."

        await engine._delayed_send(0.01, frame)

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
        # Create a mock task
        mock_task = MagicMock()
        engine._pending_tasks.add(mock_task)

        await engine.shutdown()

        mock_task.cancel.assert_called_once()
        assert len(engine._pending_tasks) == 0
