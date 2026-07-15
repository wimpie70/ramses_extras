"""Tests for ramses_cc config validation helper."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from custom_components.ramses_extras.framework.helpers.rf_config_validation import (
    _check_bound_rem,
    _check_message_events,
    _check_recorder,
    _check_send_packet,
    log_validation_results,
    validate_ramses_cc_config,
)


class TestCheckBoundRem:
    """Tests for _check_bound_rem."""

    def test_no_known_list(self) -> None:
        assert _check_bound_rem({}) is False

    def test_empty_known_list(self) -> None:
        assert _check_bound_rem({"known_list": {}}) is False

    def test_device_without_bound(self) -> None:
        assert (
            _check_bound_rem({"known_list": {"32:153289": {"class": "FAN"}}}) is False
        )

    def test_device_with_bound(self) -> None:
        assert (
            _check_bound_rem({"known_list": {"32:153289": {"bound": "29:176861"}}})
            is True
        )

    def test_device_with_none_bound(self) -> None:
        assert _check_bound_rem({"known_list": {"32:153289": {"bound": None}}}) is False

    def test_device_with_remotes_list(self) -> None:
        assert (
            _check_bound_rem({"known_list": {"32:153289": {"remotes": ["37:168270"]}}})
            is True
        )

    def test_device_with_empty_remotes_list(self) -> None:
        assert _check_bound_rem({"known_list": {"32:153289": {"remotes": []}}}) is False

    def test_schema_with_bound(self) -> None:
        """Schema uses _bound (SZ_TR_BOUND), not bound."""
        assert (
            _check_bound_rem({"schema": {"32:153289": {"_bound": "37:168270"}}}) is True
        )

    def test_schema_without_bound(self) -> None:
        assert _check_bound_rem({"schema": {"32:153289": {"_class": "FAN"}}}) is False

    def test_known_list_bound_takes_precedence(self) -> None:
        """Both known_list and schema present — known_list checked first."""
        assert (
            _check_bound_rem(
                {
                    "known_list": {"32:153289": {"bound": "29:176861"}},
                    "schema": {"32:153289": {"_bound": "37:168270"}},
                }
            )
            is True
        )

    def test_schema_bound_when_known_list_empty(self) -> None:
        """Schema _bound detected even when known_list has no binding."""
        assert (
            _check_bound_rem(
                {
                    "known_list": {"32:153289": {"class": "FAN"}},
                    "schema": {"32:153289": {"_bound": "37:168270"}},
                }
            )
            is True
        )

    def test_known_list_not_dict(self) -> None:
        assert _check_bound_rem({"known_list": "not_a_dict"}) is False


class TestCheckMessageEvents:
    """Tests for _check_message_events."""

    def test_no_advanced_features(self) -> None:
        enabled, matches = _check_message_events({})
        assert enabled is False
        assert matches is False

    def test_no_message_events_key(self) -> None:
        enabled, matches = _check_message_events({"advanced_features": {}})
        assert enabled is False
        assert matches is False

    def test_message_events_none(self) -> None:
        enabled, matches = _check_message_events(
            {"advanced_features": {"message_events": None}}
        )
        assert enabled is False
        assert matches is False

    def test_message_events_with_31da(self) -> None:
        enabled, matches = _check_message_events(
            {"advanced_features": {"message_events": "31DA|10D0"}}
        )
        assert enabled is True
        assert matches is True

    def test_message_events_with_only_31da(self) -> None:
        enabled, matches = _check_message_events(
            {"advanced_features": {"message_events": "31DA"}}
        )
        assert enabled is True
        assert matches is True

    def test_message_events_with_only_10d0(self) -> None:
        enabled, matches = _check_message_events(
            {"advanced_features": {"message_events": "10D0"}}
        )
        assert enabled is True
        assert matches is True

    def test_message_events_without_required_codes(self) -> None:
        enabled, matches = _check_message_events(
            {"advanced_features": {"message_events": "30C9|1F09"}}
        )
        assert enabled is True
        assert matches is False

    def test_advanced_features_not_dict(self) -> None:
        enabled, matches = _check_message_events({"advanced_features": "not_a_dict"})
        assert enabled is False
        assert matches is False


class TestCheckSendPacket:
    """Tests for _check_send_packet."""

    def test_no_advanced_features(self) -> None:
        assert _check_send_packet({}) is False

    def test_send_packet_false(self) -> None:
        assert (
            _check_send_packet({"advanced_features": {"send_packet": False}}) is False
        )

    def test_send_packet_true(self) -> None:
        assert _check_send_packet({"advanced_features": {"send_packet": True}}) is True

    def test_send_packet_missing(self) -> None:
        assert _check_send_packet({"advanced_features": {}}) is False


class TestCheckRecorder:
    """Tests for _check_recorder."""

    def test_recorder_loaded(self) -> None:
        hass = MagicMock()
        hass.config.components = {"recorder", "homeassistant"}
        assert _check_recorder(hass) is True

    def test_recorder_not_loaded(self) -> None:
        hass = MagicMock()
        hass.config.components = {"homeassistant"}
        assert _check_recorder(hass) is False


class TestValidateRamsesCcConfig:
    """Tests for validate_ramses_cc_config."""

    @pytest.mark.asyncio
    async def test_ramses_cc_not_loaded(self) -> None:
        hass = MagicMock()
        hass.config_entries.async_entries.return_value = []
        hass.config.components = {"homeassistant"}
        hass.data = {}

        result = await validate_ramses_cc_config(hass)

        assert result["ramses_cc_loaded"] is False
        assert result["has_bound_rem"] is False
        assert result["send_packet_enabled"] is False
        assert result["recorder_loaded"] is False

    @pytest.mark.asyncio
    async def test_all_checks_pass(self) -> None:
        hass = MagicMock()
        entry = MagicMock()
        entry.options = {
            "known_list": {"32:153289": {"bound": "29:176861"}},
            "advanced_features": {
                "message_events": "31DA|10D0",
                "send_packet": True,
            },
        }
        hass.config_entries.async_entries.return_value = [entry]
        hass.config.components = {"recorder", "homeassistant"}
        hass.data = {"ramses_cc": {}}

        result = await validate_ramses_cc_config(hass)

        assert result["ramses_cc_loaded"] is True
        assert result["has_bound_rem"] is True
        assert result["message_events_enabled"] is True
        assert result["message_events_matches"] is True
        assert result["send_packet_enabled"] is True
        assert result["recorder_loaded"] is True

    @pytest.mark.asyncio
    async def test_uses_coordinator_options_when_available(self) -> None:
        """Coordinator.options should be preferred over entry.options."""
        hass = MagicMock()
        entry = MagicMock()
        entry.options = {"advanced_features": {"send_packet": False}}
        coordinator = MagicMock()
        coordinator.options = {
            "known_list": {"32:153289": {"bound": "29:176861"}},
            "advanced_features": {
                "message_events": "31DA|10D0",
                "send_packet": True,
            },
        }
        hass.config_entries.async_entries.return_value = [entry]
        hass.config.components = {"recorder"}
        hass.data = {"ramses_cc": {"entry_id": coordinator}}

        result = await validate_ramses_cc_config(hass)

        assert result["send_packet_enabled"] is True
        assert result["has_bound_rem"] is True


class TestLogValidationResults:
    """Tests for log_validation_results."""

    def test_ramses_cc_not_loaded_skips_warnings(self) -> None:
        # Should not log additional warnings when ramses_cc not loaded
        log_validation_results({"ramses_cc_loaded": False})

    def test_all_pass_no_warnings(self, caplog: pytest.LogCaptureFixture) -> None:
        caplog.set_level("WARNING")
        log_validation_results(
            {
                "ramses_cc_loaded": True,
                "has_bound_rem": True,
                "message_events_enabled": True,
                "message_events_matches": True,
                "send_packet_enabled": True,
                "recorder_loaded": True,
            }
        )
        assert "not enabled" not in caplog.text
        assert "not loaded" not in caplog.text

    def test_send_packet_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        caplog.set_level("WARNING")
        log_validation_results(
            {
                "ramses_cc_loaded": True,
                "has_bound_rem": True,
                "message_events_enabled": True,
                "message_events_matches": True,
                "send_packet_enabled": False,
                "recorder_loaded": True,
            }
        )
        assert "Send Packet" in caplog.text

    def test_message_events_not_enabled_warning(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        caplog.set_level("WARNING")
        log_validation_results(
            {
                "ramses_cc_loaded": True,
                "has_bound_rem": True,
                "message_events_enabled": False,
                "message_events_matches": False,
                "send_packet_enabled": True,
                "recorder_loaded": True,
            }
        )
        assert "Message Events" in caplog.text

    def test_message_events_no_match_warning(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        caplog.set_level("WARNING")
        log_validation_results(
            {
                "ramses_cc_loaded": True,
                "has_bound_rem": True,
                "message_events_enabled": True,
                "message_events_matches": False,
                "send_packet_enabled": True,
                "recorder_loaded": True,
            }
        )
        assert "31DA|10D0" in caplog.text

    def test_no_bound_rem_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        caplog.set_level("WARNING")
        log_validation_results(
            {
                "ramses_cc_loaded": True,
                "has_bound_rem": False,
                "message_events_enabled": True,
                "message_events_matches": True,
                "send_packet_enabled": True,
                "recorder_loaded": True,
            }
        )
        assert "bound REM" in caplog.text

    def test_recorder_not_loaded_warning(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        caplog.set_level("WARNING")
        log_validation_results(
            {
                "ramses_cc_loaded": True,
                "has_bound_rem": True,
                "message_events_enabled": True,
                "message_events_matches": True,
                "send_packet_enabled": True,
                "recorder_loaded": False,
            }
        )
        assert "recorder" in caplog.text.lower()
