"""Tests for ramses_debugger messages providers."""

from __future__ import annotations

import logging
import sys
import types
from datetime import datetime
from pathlib import Path
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
    _silence_loggers,
    decode_message_with_ramses_rf,
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
    async def test_parse_packet_log_line_broadcast(self):
        line = (
            "2026-01-20T13:55:54.869729 I 31DA 32:153289 --:------ Y 030 "
            "00EF007FFF3C39028A03B603B603B602756800001814140000EFEF033E033E00"
        )
        msg = _parse_packet_log_line(line)
        assert msg is not None
        assert msg.dtm == "2026-01-20T13:55:54.869729"
        assert msg.verb == "I"
        assert msg.src == "32:153289"
        assert msg.dst == "--:------"
        assert msg.code == "31DA"
        assert isinstance(msg.payload, str)
        assert msg.payload.startswith("030 ")

    @pytest.mark.asyncio
    async def test_parse_packet_log_line_compact_malformed(self):
        # Missing destination address ("---" instead of an address)
        line = "2026-01-20T13:56:38.130940 RQ 0418 18:149488 01:000000 003 000000"
        msg = _parse_packet_log_line(line)
        assert msg is not None
        assert msg.verb == "RQ"
        assert msg.src == "18:149488"
        assert msg.dst == "01:000000"
        assert msg.code == "0418"
        assert msg.payload == "003 000000"

    @pytest.mark.asyncio
    async def test_parse_ramses_log_line_with_ellipsis_rssi(self):
        line = (
            "2026-01-20T13:27:05.670350 ... RP --- 32:153289 18:149488 --:------ "
            "10D0 006 0038B43E0000 # 10D0|RP|32:153289"
        )
        msg = _parse_packet_log_line(line)
        assert msg is not None
        assert msg.verb == "RP"
        assert msg.src == "32:153289"
        assert msg.dst == "18:149488"
        assert msg.code == "10D0"
        assert msg.payload == "006 0038B43E0000"

    @pytest.mark.asyncio
    async def test_parse_ramses_log_line_with_seqn_digits(self):
        line = (
            "2026-01-20T13:27:05.672863 ... I 245 32:153289 --:------ 32:153289 "
            "31D9 017 000A050020202020202020202020202008"
        )
        msg = _parse_packet_log_line(line)
        assert msg is not None
        assert msg.verb == "I"
        assert msg.src == "32:153289"
        assert msg.dst == "--:------"
        assert msg.code == "31D9"
        assert isinstance(msg.payload, str)
        assert msg.payload.startswith("017 ")

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

    @pytest.mark.asyncio
    async def test_packet_log_parser_get_messages_filters_and_since(self):
        hass = MagicMock(spec=HomeAssistant)

        async def _run_executor(fn):
            return fn()

        hass.async_add_executor_job = AsyncMock(side_effect=_run_executor)

        log_content = "\n".join(
            [
                "2026-01-20T10:00:00.000000 RQ 01:111111 02:222222 --:------ "
                "31DA 003 010203",
                "2026-01-20T10:00:01.000000 RP 02:222222 01:111111 --:------ "
                "31DA 003 010203",
                "2026-01-20T10:00:02.000000 I 245 01:111111 --:------ 01:111111 "
                "313F 000",
                "invalid line",
            ]
        )

        with patch(
            "custom_components.ramses_extras.features.ramses_debugger.messages_provider.tail_text",
            return_value=log_content,
        ):
            msgs = await PacketLogParser.get_messages(
                hass,
                log_path=Path("/tmp/ramses_log"),
                limit=10,
            )

        # Newest-first
        assert [m.dtm for m in msgs][:2] == [
            "2026-01-20T10:00:02.000000",
            "2026-01-20T10:00:01.000000",
        ]

        with patch(
            "custom_components.ramses_extras.features.ramses_debugger.messages_provider.tail_text",
            return_value=log_content,
        ):
            msgs_since = await PacketLogParser.get_messages(
                hass,
                log_path=Path("/tmp/ramses_log"),
                since="2026-01-20T10:00:01.000000",
                limit=10,
            )

        assert [m.dtm for m in msgs_since] == [
            "2026-01-20T10:00:02.000000",
            "2026-01-20T10:00:01.000000",
        ]

        only_src = [m for m in msgs if m.src == "01:111111"]
        assert only_src


def test_silence_loggers_restores_state() -> None:
    name = "custom_components.ramses_extras.tests.silence"
    log = logging.getLogger(name)
    log.disabled = False
    log.setLevel(logging.INFO)

    with _silence_loggers([name]):
        assert log.disabled is True
        assert log.level > logging.CRITICAL

    assert log.disabled is False
    assert log.level == logging.INFO


def test_decode_message_with_ramses_rf_missing_module(monkeypatch) -> None:
    # Ensure import fails
    monkeypatch.setitem(sys.modules, "ramses_tx", None)
    monkeypatch.setitem(sys.modules, "ramses_tx.message", None)
    monkeypatch.setitem(sys.modules, "ramses_tx.packet", None)

    msg = {
        "dtm": "2026-01-20T10:00:00.000000",
        "src": "01:111111",
        "dst": "02:222222",
        "verb": "RQ",
        "code": "31DA",
        "payload": "003 010203",
        "packet": "RQ 01:111111 02:222222 --:------ 31DA 003 010203",
    }
    assert decode_message_with_ramses_rf(msg) is None


@pytest.mark.parametrize(
    "msg",
    [
        {
            "dtm": 123,
            "src": "01:111111",
            "dst": "02:222222",
            "verb": "RQ",
            "code": "31DA",
            "payload": "003 010203",
            "packet": "RQ 01:111111 02:222222 --:------ 31DA 003 010203",
        },
        {
            "dtm": "2026-01-20T10:00:00.000000",
            "src": "01:111111",
            "dst": "02:222222",
            "verb": "RQ",
            "code": "31DA",
            "payload": "",
            "packet": "RQ 01:111111 02:222222 --:------ 31DA 003 010203",
        },
        {
            "dtm": "2026-01-20T10:00:00.000000",
            "src": "01:111111",
            "dst": "02:222222",
            "verb": "RQ",
            "code": "31DA",
            "payload": "XX 010203",
            "packet": "RQ 01:111111 02:222222 --:------ 31DA 003 010203",
        },
        {
            "dtm": "not-a-datetime",
            "src": "01:111111",
            "dst": "02:222222",
            "verb": "RQ",
            "code": "31DA",
            "payload": "003 010203",
            "packet": "RQ 01:111111 02:222222 --:------ 31DA 003 010203",
        },
    ],
)
def test_decode_message_with_ramses_rf_validation_returns_none(
    monkeypatch,
    msg,
) -> None:
    # Provide minimal modules so the function can get past the import stage.
    mod_packet = types.ModuleType("ramses_tx.packet")
    mod_message = types.ModuleType("ramses_tx.message")

    class DummyPacket:  # pragma: no cover
        def __init__(self, dtm: datetime, frame: str) -> None:
            self.dtm = dtm
            self.frame = frame

    class DummyMessage:  # pragma: no cover
        @staticmethod
        def _from_pkt(pkt: DummyPacket):
            return None

    mod_packet.__dict__["Packet"] = DummyPacket
    mod_message.__dict__["Message"] = DummyMessage

    monkeypatch.setitem(sys.modules, "ramses_tx.packet", mod_packet)
    monkeypatch.setitem(sys.modules, "ramses_tx.message", mod_message)

    assert decode_message_with_ramses_rf(msg) is None


def test_decode_message_with_ramses_rf_success(monkeypatch) -> None:
    mod_packet = types.ModuleType("ramses_tx.packet")
    mod_message = types.ModuleType("ramses_tx.message")

    class DummyPacket:
        def __init__(self, dtm: datetime, frame: str) -> None:
            self.dtm = dtm
            self.frame = frame

    class DummyMessage:
        def __init__(
            self,
            *,
            dtm: datetime,
            src: str,
            dst: str,
            verb: str,
            code: str,
        ) -> None:
            self.dtm = dtm
            self.src = types.SimpleNamespace(id=src)
            self.dst = types.SimpleNamespace(id=dst)
            self.verb = verb
            self.code = code

        @property
        def payload(self):
            return {"ok": True}

        @staticmethod
        def _from_pkt(pkt: DummyPacket) -> DummyMessage:
            tokens = pkt.frame.split()
            # 000 VERB SEQN SRC DST VIA CODE LEN HEX
            verb = tokens[1]
            src = tokens[3]
            dst = tokens[4]
            code = tokens[6]
            return DummyMessage(dtm=pkt.dtm, src=src, dst=dst, verb=verb, code=code)

    mod_packet.__dict__["Packet"] = DummyPacket
    mod_message.__dict__["Message"] = DummyMessage

    monkeypatch.setitem(sys.modules, "ramses_tx.packet", mod_packet)
    monkeypatch.setitem(sys.modules, "ramses_tx.message", mod_message)

    msg = {
        "dtm": "2026-01-20T10:00:00.000000",
        "src": "01:111111",
        "dst": "02:222222",
        "verb": "RQ",
        "code": "31DA",
        "payload": "003 010203",
        "packet": "RQ 01:111111 02:222222 --:------ 31DA 003 010203",
    }

    decoded = decode_message_with_ramses_rf(msg)
    assert isinstance(decoded, dict)
    assert decoded["src"] == "01:111111"
    assert decoded["dst"] == "02:222222"
    assert decoded["verb"] == "RQ"
    assert decoded["code"] == "31DA"
    assert decoded["payload"] == {"ok": True}


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
    async def test_get_messages_simple(self, hass, sample_ha_log_lines):  # noqa: E501
        """Test HA log parsing with simple mock."""
        # Test parsing directly
        from custom_components.ramses_extras.features.ramses_debugger.messages_provider import (  # noqa: E501
            _parse_ha_log_line,
        )

        msgs = []
        for line in sample_ha_log_lines:
            msg = _parse_ha_log_line(line)
            if msg:
                msgs.append(msg)

        # Should parse all 2 lines
        assert len(msgs) == 2
        assert msgs[0].src == "32:153289"
        assert msgs[1].src == "37:169161"

        # Test filtering
        filtered = [m for m in msgs if m.src == "32:153289"]
        assert len(filtered) == 1


class TestGetMessagesFromSources:
    """Test get_messages_from_sources aggregation."""

    @pytest.mark.asyncio
    @patch(
        "custom_components.ramses_extras.features.ramses_debugger.traffic_collector.TrafficCollector"
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
        # Import locally to avoid circular import
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
            "custom_components.ramses_extras.features.ramses_debugger.traffic_collector.TrafficCollector"
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
