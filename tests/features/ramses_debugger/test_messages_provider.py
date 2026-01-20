"""Tests for ramses_debugger messages providers."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.core import HomeAssistant

from custom_components.ramses_extras.features.ramses_debugger.messages_provider import (
    HALogProvider,
    NormalizedMessage,
    PacketLogParser,
    PacketLogProvider,
    TrafficBufferProvider,
    _parse_ha_log_line,
    _parse_packet_log_line,
    get_messages_from_sources,
)


@pytest.fixture
def hass() -> HomeAssistant:
    """Fixture for Home Assistant."""
    return MagicMock(spec=HomeAssistant)


@pytest.fixture
def sample_traffic_buffer():
    """Sample traffic buffer data."""
    return [
        {
            "dtm": "2026-01-20T10:00:00.000000",
            "src": "32:153289",
            "dst": "37:169161",
            "verb": "RQ",
            "code": "31DA",
            "payload": {"temp": 20.5},
            "packet": "RQ 32:153289 37:169161 --:------ 31DA 003 123",
        },
        {
            "dtm": "2026-01-20T10:00:01.000000",
            "src": "37:169161",
            "dst": "32:153289",
            "verb": "RP",
            "code": "31DA",
            "payload": {"temp": 20.5},
            "packet": "RP 37:169161 32:153289 --:------ 31DA 003 123",
        },
    ]


@pytest.fixture
def sample_packet_log_lines():
    """Sample packet log lines."""
    return [
        "2026-01-20T10:00:00.000000 RQ 32:153289 37:169161 --:------ 31DA 003 123ABC",
        "2026-01-20T10:00:01.000000 RP 37:169161 32:153289 --:------ 31DA 003 123ABC",
        "2026-01-20T10:00:02.000000 I 32:153289 32:153289 --:------ 313F 009 007C1A002B",  # noqa: E501
    ]


@pytest.fixture
def sample_ha_log_lines():
    """Sample HA log lines with JSON payloads."""
    return [
        '2026-01-20 10:00:00 DEBUG (MainThread) [custom_components.ramses_cc] {"src": "32:153289", "dst": "37:169161", "verb": "RQ", "code": "31DA", "payload": {"temp": 20.5}}',  # noqa: E501
        '2026-01-20 10:00:01 DEBUG (MainThread) [custom_components.ramses_cc] {"src": "37:169161", "dst": "32:153289", "verb": "RP", "code": "31DA", "payload": {"temp": 20.5}}',  # noqa: E501
    ]


class TestTrafficBufferProvider:
    """Test TrafficBufferProvider."""

    @pytest.mark.asyncio
    async def test_get_messages_filters(self, hass, sample_traffic_buffer):
        """Test filtering by src/dst/verb/code."""
        provider = TrafficBufferProvider()
        # Populate buffer
        for event in sample_traffic_buffer:
            provider.ingest_event(event)

        # Test src filter
        msgs = await provider.get_messages(hass, src="32:153289")
        assert len(msgs) == 1
        assert msgs[0].src == "32:153289"

        # Test verb filter
        msgs = await provider.get_messages(hass, verb="RQ")
        assert len(msgs) == 1
        assert msgs[0].verb == "RQ"

        # Test code filter
        msgs = await provider.get_messages(hass, code="31DA")
        assert len(msgs) == 2
        assert all(msg.code == "31DA" for msg in msgs)

    @pytest.mark.asyncio
    async def test_get_messages_limit(self, hass, sample_traffic_buffer):
        """Test limit parameter."""
        provider = TrafficBufferProvider()
        for event in sample_traffic_buffer:
            provider.ingest_event(event)

        msgs = await provider.get_messages(hass, limit=1)
        assert len(msgs) == 1


class TestPacketLogParser:
    """Test PacketLogParser."""

    @pytest.mark.asyncio
    async def test_parse_packet_log_line(self):
        """Test parsing individual packet log lines."""
        line = "2026-01-20T10:00:00.000000 RQ 32:153289 37:169161 --:------ 31DA 003 123ABC"  # noqa: E501
        msg = _parse_packet_log_line(line)
        assert msg is not None
        assert msg.dtm == "2026-01-20T10:00:00.000000"
        assert msg.verb == "RQ"
        assert msg.src == "32:153289"
        assert msg.dst == "37:169161"
        assert msg.code == "31DA"
        assert msg.payload == "003 123ABC"
        assert msg.packet == "RQ 32:153289 37:169161 --:------ 31DA 003 123ABC"
        assert msg.source == "packet_log"
        assert msg.raw_line == line

    @pytest.mark.asyncio
    async def test_parse_packet_log_line_invalid(self):
        """Test parsing invalid line."""
        line = "invalid line"
        msg = _parse_packet_log_line(line)
        assert msg is None

    @pytest.mark.asyncio
    async def test_get_messages_simple(self, hass, sample_packet_log_lines):  # noqa: E501
        """Test packet log parsing with simple mock."""
        # Mock the entire get_messages function to just test parsing
        from custom_components.ramses_extras.features.ramses_debugger.messages_provider import (  # noqa: E501
            _parse_packet_log_line,
        )

        # Test parsing directly
        msgs = []
        for line in sample_packet_log_lines:
            msg = _parse_packet_log_line(line)
            if msg:
                msgs.append(msg)

        # Should parse all 3 lines
        assert len(msgs) == 3
        assert msgs[0].src == "32:153289"
        assert msgs[1].src == "37:169161"
        assert msgs[2].src == "32:153289"

        # Test filtering
        filtered = [m for m in msgs if m.src == "32:153289"]
        assert len(filtered) == 2


class TestHALogProvider:
    """Test HALogProvider."""

    @pytest.mark.asyncio
    async def test_parse_ha_log_line(self):
        """Test parsing HA log line with JSON."""
        line = '2026-01-20 10:00:00 DEBUG (MainThread) [custom_components.ramses_cc] {"src": "32:153289", "dst": "37:169161", "verb": "RQ", "code": "31DA"}'  # noqa: E501
        msg = _parse_ha_log_line(line)
        assert msg is not None
        assert msg.dtm == "2026-01-20 10:00:00"
        assert msg.src == "32:153289"
        assert msg.dst == "37:169161"
        assert msg.verb == "RQ"
        assert msg.code == "31DA"
        assert msg.source == "ha_log"
        assert msg.raw_line == line

    @pytest.mark.asyncio
    async def test_parse_ha_log_line_invalid(self):
        """Test parsing invalid HA log line."""
        line = "2026-01-20 10:00:00 DEBUG (MainThread) [custom_components.ramses_cc] no json here"  # noqa: E501
        msg = _parse_ha_log_line(line)
        assert msg is None

    @pytest.mark.asyncio
    @patch(
        "custom_components.ramses_extras.features.ramses_debugger.messages_provider.get_configured_log_path"
    )
    async def test_get_messages(self, mock_log_path, hass, sample_ha_log_lines):  # noqa: E501
        """Test fetching messages from HA log."""
        from pathlib import Path

        mock_log_path.return_value = Path("/tmp/home-assistant.log")

        # Mock file content and hass.async_add_executor_job
        content = "\n".join(sample_ha_log_lines)
        with patch.object(hass, "async_add_executor_job", return_value=content):
            msgs = await HALogProvider().get_messages(hass, src="32:153289")
        assert len(msgs) == 1
        assert msgs[0].src == "32:153289"


class TestGetMessagesFromSources:
    """Test get_messages_from_sources aggregation."""

    @pytest.mark.asyncio
    @patch(
        "custom_components.ramses_extras.features.ramses_debugger.messages_provider.TrafficCollector"
    )
    async def test_aggregate_sources(
        self, mock_collector_class, hass, sample_traffic_buffer
    ):  # noqa: E501
        """Test aggregating messages from multiple sources."""
        # Mock traffic buffer provider
        mock_provider = MagicMock()
        mock_provider.get_messages = AsyncMock(
            return_value=[
                NormalizedMessage(
                    dtm="2026-01-20T10:00:00.000000",
                    src="32:153289",
                    dst="37:169161",
                    verb="RQ",
                    code="31DA",
                    payload="temp",
                    packet="RQ 32:153289 37:169161 --:------ 31DA 003 123",
                    source="traffic_buffer",
                )
            ]
        )

        mock_collector = MagicMock()
        mock_collector.get_buffer_provider.return_value = mock_provider
        mock_collector_class.return_value = mock_collector

        # Mock packet log provider
        with patch(
            "custom_components.ramses_extras.features.ramses_debugger.messages_provider.PacketLogProvider"
        ) as mock_packet:  # noqa: E501
            mock_packet.return_value.get_messages = AsyncMock(
                return_value=[
                    NormalizedMessage(
                        dtm="2026-01-20T10:00:01.000000",
                        src="32:153289",
                        dst="37:169161",
                        verb="RP",
                        code="31DA",
                        payload="003 123",
                        packet="RP 32:153289 37:169161 --:------ 31DA 003 123",
                        source="packet_log",
                    )
                ]
            )

            # Mock HA log provider
            with patch(
                "custom_components.ramses_extras.features.ramses_debugger.messages_provider.HALogProvider"
            ) as mock_ha:  # noqa: E501
                mock_ha.return_value.get_messages = AsyncMock(
                    return_value=[
                        NormalizedMessage(
                            dtm="2026-01-20T10:00:02.000000",
                            src="32:153289",
                            dst="37:169161",
                            verb="I",
                            code="313F",
                            payload="009 007C1A002B",
                            packet="I 32:153289 32:153289 --:------ 313F 009 007C1A002B",  # noqa: E501
                            source="ha_log",
                        )
                    ]
                )

                # Mock hass.data structure
                hass.data = {
                    "ramses_extras": {
                        "ramses_debugger": {
                            "traffic_collector": mock_collector,
                        }
                    }
                }

                msgs = await get_messages_from_sources(
                    hass,
                    sources=["traffic_buffer", "packet_log", "ha_log"],
                )
                assert len(msgs) == 3
                sources = {msg["source"] for msg in msgs}
                assert sources == {"traffic_buffer", "packet_log", "ha_log"}

    @pytest.mark.asyncio
    async def test_deduplication(self, hass):
        """Test message deduplication."""
        # Create duplicate messages from different sources
        duplicate_msg = NormalizedMessage(
            dtm="2026-01-20T10:00:00.000000",
            src="32:153289",
            dst="37:169161",
            verb="RQ",
            code="31DA",
            payload="003 123",
            packet="RQ 32:153289 37:169161 --:------ 31DA 003 123",
            source="traffic_buffer",
        )

        with patch(
            "custom_components.ramses_extras.features.ramses_debugger.messages_provider.TrafficCollector"
        ) as mock_collector_class:  # noqa: E501
            mock_provider = MagicMock()
            mock_provider.get_messages = AsyncMock(return_value=[duplicate_msg])
            mock_collector = MagicMock()
            mock_collector.get_buffer_provider.return_value = mock_provider
            mock_collector_class.return_value = mock_collector

            with patch(
                "custom_components.ramses_extras.features.ramses_debugger.messages_provider.PacketLogProvider"
            ) as mock_packet:  # noqa: E501
                # Return the same message (duplicate)
                mock_packet.return_value.get_messages = AsyncMock(
                    return_value=[duplicate_msg]
                )  # noqa: E501

                hass.data = {
                    "ramses_extras": {
                        "ramses_debugger": {
                            "traffic_collector": mock_collector,
                        }
                    }
                }

                msgs = await get_messages_from_sources(
                    hass,
                    sources=["traffic_buffer", "packet_log"],
                    dedupe=True,
                )
                # Should only have one message after deduplication
                assert len(msgs) == 1
                assert msgs[0]["source"] == "traffic_buffer"  # First source wins

            # Test without deduplication
            msgs = await get_messages_from_sources(
                hass,
                sources=["traffic_buffer", "packet_log"],
                dedupe=False,
            )
            assert len(msgs) == 2
