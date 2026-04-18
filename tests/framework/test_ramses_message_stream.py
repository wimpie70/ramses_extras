from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

from custom_components.ramses_extras.framework.helpers.ramses_message_stream import (
    RamsesMessageStream,
)


class TestRamsesMessageStream:
    def test_handle_msg_includes_frame(self) -> None:
        hass = MagicMock()
        stream = RamsesMessageStream(hass)
        callback = MagicMock()
        stream.subscribe(callback)

        pkt = MagicMock()
        pkt.payload = "00003E"
        packet = (
            "000 RP --- 32:150000 37:170000 --:------ "
            "2411 003 00003E # 2411|RP|37:170000|00"
        )
        pkt.__str__.return_value = packet

        msg = MagicMock()
        msg._pkt = pkt
        msg.src.id = "32:150000"
        msg.dst.id = "37:170000"
        msg.verb = "RP"
        msg.code = "2411"
        msg.dtm = datetime(2026, 4, 18, 9, 0, 0)

        stream._handle_msg(msg)

        callback.assert_called_once()
        data = callback.call_args.args[0]
        assert data["frame"] == packet
        assert data["packet"] == packet
        assert data["src"] == "32:150000"
        assert data["dst"] == "37:170000"
        assert data["verb"] == "RP"
        assert data["code"] == "2411"
        assert data["payload"] == "00003E"

    def test_handle_msg_uses_packet_addresses_over_application_addresses(self) -> None:
        hass = MagicMock()
        stream = RamsesMessageStream(hass)
        callback = MagicMock()
        stream.subscribe(callback)

        pkt = MagicMock()
        pkt.payload = "000001"
        pkt.__str__.return_value = (
            "000 RP --- 32:150000 37:170000 --:------ 2411 003 000001"
        )

        msg = MagicMock()
        msg._pkt = pkt
        msg.src.id = "32:150000"
        msg.dst.id = "18:001234"
        msg.verb = "RP"
        msg.code = "2411"
        msg.dtm = datetime(2026, 4, 18, 9, 0, 1)

        stream._handle_msg(msg)

        data = callback.call_args.args[0]
        assert data["src"] == "32:150000"
        assert data["dst"] == "37:170000"

    def test_event_path_kept_for_requests_when_handler_attached(self) -> None:
        hass = MagicMock()
        hass.bus.async_listen = MagicMock()
        stream = RamsesMessageStream(hass)
        stream._msg_handler_unsub = MagicMock()
        callback = MagicMock()
        stream.subscribe(callback)

        event = SimpleNamespace(
            data={
                "src": "37:170000",
                "dst": "32:150000",
                "verb": "RQ",
                "code": "2411",
                "payload": "0000",
            },
            time_fired=datetime(2026, 4, 18, 9, 35, 1, 327000),
        )

        stream._handle_ramses_cc_message(event)

        callback.assert_called_once()

    def test_event_path_skips_rp_when_handler_attached(self) -> None:
        hass = MagicMock()
        hass.bus.async_listen = MagicMock()
        stream = RamsesMessageStream(hass)
        stream._msg_handler_unsub = MagicMock()
        callback = MagicMock()
        stream.subscribe(callback)

        event = SimpleNamespace(
            data={
                "src": "32:150000",
                "dst": "37:170000",
                "verb": "RP",
                "code": "2411",
                "payload": "0000",
            },
            time_fired=datetime(2026, 4, 18, 9, 35, 1, 434000),
        )

        stream._handle_ramses_cc_message(event)

        callback.assert_not_called()
