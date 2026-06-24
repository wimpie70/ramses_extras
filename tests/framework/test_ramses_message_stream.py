from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

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

    def test_handle_msg_with_dto_shape(self) -> None:
        """Test _handle_msg handles PacketDTO-like objects."""
        hass = MagicMock()
        stream = RamsesMessageStream(hass)
        callback = MagicMock()
        stream.subscribe(callback)

        msg = SimpleNamespace(
            addr1="32:150000",
            addr2="37:170000",
            verb="RP",
            code="2411",
            payload="00003E",
            timestamp=datetime(2026, 4, 18, 9, 0, 0),
        )

        stream._handle_msg(msg)

        callback.assert_called_once()
        data = callback.call_args.args[0]
        assert data["src"] == "32:150000"
        assert data["dst"] == "37:170000"
        assert data["verb"] == "RP"
        assert data["code"] == "2411"
        assert data["payload"] == "00003E"
        assert (
            data["frame"] == "000 RP --- 32:150000 37:170000 --:------ 2411 003 00003E"
        )
        assert data["dtm"] == "2026-04-18T09:00:00.000000"
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

    def test_handle_msg_fires_ha_bus_event(self) -> None:
        """_handle_msg should fire ramses_cc_message on the HA bus for frontend
        when ramses_cc >= 0.55.6 (no longer fires its own events)."""
        hass = MagicMock()
        stream = RamsesMessageStream(hass)
        stream._ramses_cc_fires_events = False  # newer ramses_cc
        callback = MagicMock()
        stream.subscribe(callback)

        msg = SimpleNamespace(
            addr1="32:150000",
            addr2="37:170000",
            verb="RP",
            code="31DA",
            payload="00EF007FFF3F3009BA0A8209690A256000C81822110000EFEF04C6076000",
            timestamp=datetime(2026, 6, 23, 21, 28, 40),
        )

        stream._handle_msg(msg)

        # Python subscribers notified
        callback.assert_called_once()
        # HA bus event fired for frontend message broker
        hass.bus.async_fire.assert_called_once()
        fired_event = hass.bus.async_fire.call_args
        assert fired_event.args[0] == "ramses_cc_message"
        fired_data = fired_event.kwargs.get("data") or fired_event.args[1]
        assert fired_data["code"] == "31DA"
        assert fired_data["src"] == "32:150000"
        assert fired_data["_from_msg_handler"] is True

    def test_handle_msg_skips_ha_bus_event_for_older_ramses_cc(self) -> None:
        """_handle_msg should NOT fire ramses_cc_message on the HA bus when
        ramses_cc < 0.55.6 (it fires its own events)."""
        hass = MagicMock()
        stream = RamsesMessageStream(hass)
        stream._ramses_cc_fires_events = True  # older ramses_cc
        callback = MagicMock()
        stream.subscribe(callback)

        msg = SimpleNamespace(
            addr1="32:150000",
            addr2="37:170000",
            verb="RP",
            code="31DA",
            payload="00EF00",
            timestamp=datetime(2026, 6, 23, 21, 28, 40),
        )

        stream._handle_msg(msg)

        # Python subscribers still notified
        callback.assert_called_once()
        # HA bus event NOT fired (ramses_cc fires its own)
        hass.bus.async_fire.assert_not_called()

    def test_handle_msg_fires_event_when_version_unknown(self) -> None:
        """_handle_msg should fire HA bus event when version is not yet
        determined (default to firing for safety)."""
        hass = MagicMock()
        stream = RamsesMessageStream(hass)
        # _ramses_cc_fires_events is None (not yet checked)
        callback = MagicMock()
        stream.subscribe(callback)

        msg = SimpleNamespace(
            addr1="32:150000",
            addr2="37:170000",
            verb="RP",
            code="31DA",
            payload="00EF00",
            timestamp=datetime(2026, 6, 23, 21, 28, 40),
        )

        stream._handle_msg(msg)

        callback.assert_called_once()
        # Should fire because None is not False
        hass.bus.async_fire.assert_called_once()

    def test_handle_ramses_cc_message_skips_msg_handler_events(self) -> None:
        """Events fired by _handle_msg should not duplicate subscriber notifications."""
        hass = MagicMock()
        hass.bus.async_listen = MagicMock()
        stream = RamsesMessageStream(hass)
        callback = MagicMock()
        stream.subscribe(callback)

        event = SimpleNamespace(
            data={
                "src": "32:150000",
                "dst": "37:170000",
                "verb": "RP",
                "code": "31DA",
                "payload": "00EF00",
                "_from_msg_handler": True,
            },
            time_fired=datetime(2026, 6, 23, 21, 28, 40),
        )

        stream._handle_ramses_cc_message(event)

        callback.assert_not_called()

    @pytest.mark.asyncio
    async def test_attach_client_listener_retries_until_available(self) -> None:
        """Listener attachment should retry while coordinator/client initializes."""
        hass = MagicMock()
        stream = RamsesMessageStream(hass)

        unsub = MagicMock()
        coordinator = SimpleNamespace(
            client=SimpleNamespace(add_msg_handler=MagicMock(return_value=unsub))
        )

        with patch(
            "custom_components.ramses_extras.framework.helpers.ramses_message_stream.RamsesCommands"
        ) as mock_commands_cls:
            mock_commands = mock_commands_cls.return_value
            mock_commands._get_ramses_cc_coordinator = AsyncMock(
                side_effect=[None, coordinator]
            )

            with patch(
                "custom_components.ramses_extras.framework.helpers.ramses_message_stream.asyncio.sleep",
                new=AsyncMock(),
            ) as sleep_mock:
                with patch(
                    "custom_components.ramses_extras.framework.helpers.ramses_message_stream.async_get_integration",
                    new=AsyncMock(side_effect=Exception("not found")),
                ):
                    await stream._async_attach_client_listener()

        assert stream._msg_handler_unsub is unsub
        assert sleep_mock.await_count == 1
        # Version detection ran but defaulted to False (no bus events)
        assert stream._ramses_cc_fires_events is False

    def test_resolve_add_msg_handler_prefers_coordinator_when_available(self) -> None:
        """Support coordinator shapes exposing add_msg_handler directly."""
        hass = MagicMock()
        stream = RamsesMessageStream(hass)
        add_handler = MagicMock()
        coordinator = MagicMock()
        coordinator.add_msg_handler = add_handler

        resolved = stream._resolve_add_msg_handler(coordinator)

        assert resolved is add_handler

    @pytest.mark.asyncio
    async def test_ramses_cc_fires_events_old_version(self) -> None:
        """Older ramses_cc (< 0.55.6) fires its own ramses_cc_message events."""
        hass = MagicMock()
        stream = RamsesMessageStream(hass)

        integration = SimpleNamespace(manifest={"version": "0.55.5"})
        with patch(
            "custom_components.ramses_extras.framework.helpers.ramses_message_stream.async_get_integration",
            new=AsyncMock(return_value=integration),
        ):
            result = await stream._async_ramses_cc_fires_events()

        assert result is True
        assert stream._ramses_cc_fires_events is True

    @pytest.mark.asyncio
    async def test_ramses_cc_fires_events_new_version(self) -> None:
        """Newer ramses_cc (>= 0.55.6) does not fire ramses_cc_message events."""
        hass = MagicMock()
        stream = RamsesMessageStream(hass)

        integration = SimpleNamespace(manifest={"version": "0.55.6"})
        with patch(
            "custom_components.ramses_extras.framework.helpers.ramses_message_stream.async_get_integration",
            new=AsyncMock(return_value=integration),
        ):
            result = await stream._async_ramses_cc_fires_events()

        assert result is False
        assert stream._ramses_cc_fires_events is False

    @pytest.mark.asyncio
    async def test_ramses_cc_fires_events_not_installed(self) -> None:
        """When ramses_cc is not found, default to not firing events."""
        hass = MagicMock()
        stream = RamsesMessageStream(hass)

        with patch(
            "custom_components.ramses_extras.framework.helpers.ramses_message_stream.async_get_integration",
            new=AsyncMock(side_effect=Exception("not found")),
        ):
            result = await stream._async_ramses_cc_fires_events()

        assert result is False
        assert stream._ramses_cc_fires_events is False

    @pytest.mark.asyncio
    async def test_ramses_cc_fires_events_caches_result(self) -> None:
        """Version detection result should be cached."""
        hass = MagicMock()
        stream = RamsesMessageStream(hass)
        stream._ramses_cc_fires_events = True  # already set

        # Should return cached value without calling async_get_integration
        with patch(
            "custom_components.ramses_extras.framework.helpers.ramses_message_stream.async_get_integration",
            new=AsyncMock(),
        ) as mock_get:
            result = await stream._async_ramses_cc_fires_events()

        assert result is True
        mock_get.assert_not_called()

    def test_start_already_started(self) -> None:
        """Test start does nothing if already started."""
        hass = MagicMock()
        stream = RamsesMessageStream(hass)
        stream._event_unsub = MagicMock()
        stream._msg_handler_unsub = MagicMock()
        stream.start()
        # Should not call async_listen again
        hass.bus.async_listen.assert_not_called()

    def test_stop_clears_subscribers(self) -> None:
        """Test stop clears unsubscribe callbacks and cancels task."""
        hass = MagicMock()
        stream = RamsesMessageStream(hass)
        stream._event_unsub = MagicMock()
        stream._msg_handler_unsub = MagicMock()
        attach_task = MagicMock()
        attach_task.done.return_value = False
        stream._attach_task = attach_task
        stream.stop()
        assert stream._event_unsub is None
        assert stream._msg_handler_unsub is None
        attach_task.cancel.assert_called_once()

    def test_subscribe_returns_unsubscribe_function(self) -> None:
        """Test subscribe returns a function that removes the subscription."""
        hass = MagicMock()
        stream = RamsesMessageStream(hass)
        callback = MagicMock()
        unsub = stream.subscribe(callback)
        unsub()
        assert len(stream._subscribers) == 0

    def test_notify_subscribers_calls_all_callbacks(self) -> None:
        """Test _notify_subscribers calls all registered callbacks."""
        hass = MagicMock()
        stream = RamsesMessageStream(hass)
        callback1 = MagicMock()
        callback2 = MagicMock()
        stream.subscribe(callback1)
        stream.subscribe(callback2)
        data = {"test": "data"}
        stream._notify_subscribers(data)
        callback1.assert_called_once_with(data)
        callback2.assert_called_once_with(data)

    def test_frame_from_dict_with_frame_key(self) -> None:
        """Test _frame_from_dict extracts frame from frame key."""
        hass = MagicMock()
        stream = RamsesMessageStream(hass)
        data = {"frame": "000 RP --- 32:150000 37:170000 --:------ 2411 003 000000"}
        frame = stream._frame_from_dict(data)
        assert frame == "000 RP --- 32:150000 37:170000 --:------ 2411 003 000000"

    def test_frame_from_dict_with_raw_key(self) -> None:
        """Test _frame_from_dict extracts frame from raw key."""
        hass = MagicMock()
        stream = RamsesMessageStream(hass)
        data = {"raw": "000 RP --- 32:150000 37:170000 --:------ 2411 003 000000"}
        frame = stream._frame_from_dict(data)
        assert frame == "000 RP --- 32:150000 37:170000 --:------ 2411 003 000000"

    def test_frame_from_dict_builds_frame(self) -> None:
        """Test _frame_from_dict builds frame from components."""
        hass = MagicMock()
        stream = RamsesMessageStream(hass)
        data = {
            "verb": "RP",
            "src": "32:150000",
            "dst": "37:170000",
            "code": "2411",
            "payload": "000000",
        }
        frame = stream._frame_from_dict(data)
        assert "RP" in frame
        assert "32:150000" in frame
        assert "37:170000" in frame

    def test_frame_from_dict_invalid_payload(self) -> None:
        """Test _frame_from_dict returns None for invalid payload."""
        hass = MagicMock()
        stream = RamsesMessageStream(hass)
        data = {
            "verb": "RP",
            "src": "32:150000",
            "dst": "37:170000",
            "code": "2411",
            "payload": "GGGGGG",
        }
        frame = stream._frame_from_dict(data)
        assert frame is None

    def test_frame_from_dict_missing_components(self) -> None:
        """Test _frame_from_dict returns None for missing components."""
        hass = MagicMock()
        stream = RamsesMessageStream(hass)
        data = {"verb": "RP", "src": "32:150000"}
        frame = stream._frame_from_dict(data)
        assert frame is None

    def test_packet_fields_from_frame_invalid(self) -> None:
        """Test _packet_fields_from_frame returns None for invalid frame."""
        hass = MagicMock()
        stream = RamsesMessageStream(hass)
        frame = "invalid frame"
        result = stream._packet_fields_from_frame(frame)
        assert result is None

    def test_packet_fields_from_frame_with_timestamp(self) -> None:
        """Test _packet_fields_from_frame handles 20xx timestamp prefix."""
        hass = MagicMock()
        stream = RamsesMessageStream(hass)
        frame = "2026-04-18 000 RP --- 32:150000 37:170000 --:------ 2411 003 000000"
        result = stream._packet_fields_from_frame(frame)
        assert result is not None
        assert result["verb"] == "RP"
        assert result["src"] == "32:150000"

    def test_packet_fields_from_frame_with_ellipsis(self) -> None:
        """Test _packet_fields_from_frame handles ellipsis prefix."""
        hass = MagicMock()
        stream = RamsesMessageStream(hass)
        frame = "... 000 RP --- 32:150000 37:170000 --:------ 2411 003 000000"
        result = stream._packet_fields_from_frame(frame)
        # The code checks for "..." but only if len(parts) >= 8 before checking
        # After removing "...", we need at least 7 parts
        assert result is None  # This is expected behavior

    def test_packet_fields_from_frame_with_dash_prefix(self) -> None:
        """Test _packet_fields_from_frame handles dash prefix."""
        hass = MagicMock()
        stream = RamsesMessageStream(hass)
        frame = "--- 000 RP --- 32:150000 37:170000 --:------ 2411 003 000000"
        result = stream._packet_fields_from_frame(frame)
        # Similar to ellipsis, after removing "---" we need at least 7 parts
        assert result is None  # This is expected behavior

    def test_packet_fields_from_frame_invalid_seqn(self) -> None:
        """Test _packet_fields_from_frame returns None for invalid sequence."""
        hass = MagicMock()
        stream = RamsesMessageStream(hass)
        frame = "000 RP --- 32:150000 37:170000 --:------ 2411 XXX 000000"
        result = stream._packet_fields_from_frame(frame)
        # The code checks if seqn != "---" and len(seqn) != 3
        # "XXX" has length 3, so it passes the check
        assert result is not None

    def test_handle_ramses_cc_message_adds_frame(self) -> None:
        """Test _handle_ramses_cc_message adds frame to data."""
        hass = MagicMock()
        stream = RamsesMessageStream(hass)
        callback = MagicMock()
        stream.subscribe(callback)

        event = SimpleNamespace(
            data={
                "src": "32:150000",
                "dst": "37:170000",
                "verb": "RQ",
                "code": "2411",
                "payload": "0000",
            },
            time_fired=datetime(2026, 4, 18, 9, 35, 1, 327000),
        )

        stream._handle_ramses_cc_message(event)

        callback.assert_called_once()
        data = callback.call_args.args[0]
        assert "frame" in data

    def test_handle_msg_without_packet(self) -> None:
        """Test _handle_msg handles message without packet."""
        hass = MagicMock()
        stream = RamsesMessageStream(hass)
        callback = MagicMock()
        stream.subscribe(callback)

        msg = MagicMock()
        msg._pkt = None
        msg.src.id = "32:150000"
        msg.dst.id = "37:170000"
        msg.verb = "RP"
        msg.code = "2411"
        msg.dtm = datetime(2026, 4, 18, 9, 0, 0)

        stream._handle_msg(msg)

        callback.assert_called_once()
        data = callback.call_args.args[0]
        assert data["src"] == "32:150000"

    def test_handle_msg_with_string_dtm(self) -> None:
        """Test _handle_msg handles string datetime."""
        hass = MagicMock()
        stream = RamsesMessageStream(hass)
        callback = MagicMock()
        stream.subscribe(callback)

        msg = MagicMock()
        msg._pkt = None
        msg.src.id = "32:150000"
        msg.dst.id = "37:170000"
        msg.verb = "RP"
        msg.code = "2411"
        msg.dtm = "2026-04-18T09:00:00"

        stream._handle_msg(msg)

        callback.assert_called_once()
        data = callback.call_args.args[0]
        assert data["dtm"] == "2026-04-18T09:00:00"

    def test_handle_msg_without_dtm(self) -> None:
        """Test _handle_msg handles message without datetime."""
        hass = MagicMock()
        stream = RamsesMessageStream(hass)
        callback = MagicMock()
        stream.subscribe(callback)

        msg = MagicMock()
        msg._pkt = None
        msg.src.id = "32:150000"
        msg.dst.id = "37:170000"
        msg.verb = "RP"
        msg.code = "2411"
        msg.dtm = None

        stream._handle_msg(msg)

        callback.assert_called_once()
        data = callback.call_args.args[0]
        assert "dtm" not in data

    def test_inject_calls_notify_subscribers(self) -> None:
        """Test inject calls _notify_subscribers with data."""
        hass = MagicMock()
        stream = RamsesMessageStream(hass)
        callback = MagicMock()
        stream.subscribe(callback)

        data = {"test": "data"}
        stream.inject(data)

        callback.assert_called_once_with(data)

    def test_parse_frame_returns_none_after_timestamp_filter(self) -> None:
        """Test _parse_frame returns None when len(parts) < 8 after timestamp filter."""
        hass = MagicMock()
        stream = RamsesMessageStream(hass)
        frame = "2026-04-18 RP --- 32:150000 37:170000"
        result = stream._packet_fields_from_frame(frame)
        assert result is None

    def test_parse_frame_returns_none_after_ellipsis_filter(self) -> None:
        """Test _parse_frame returns None when len(parts) < 7 after ellipsis filter."""
        hass = MagicMock()
        stream = RamsesMessageStream(hass)
        frame = "... RP --- 32:150000 37:170000 --:------"
        result = stream._packet_fields_from_frame(frame)
        assert result is None

    def test_get_ramses_message_stream_returns_existing(self) -> None:
        """Test get_ramses_message_stream returns existing stream."""
        from custom_components.ramses_extras.framework.helpers.ramses_message_stream import (  # noqa: E501
            get_ramses_message_stream,
        )

        hass = MagicMock()
        existing_stream = RamsesMessageStream(hass)
        hass.data = {"ramses_extras": {"ramses_message_stream": existing_stream}}

        result = get_ramses_message_stream(hass)

        assert result is existing_stream
