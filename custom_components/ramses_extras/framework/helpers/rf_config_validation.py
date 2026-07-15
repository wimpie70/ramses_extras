"""Validate ramses_cc configuration required by ramses_extras features.

Checks at startup whether ramses_cc has the necessary settings enabled
for ramses_extras features to work correctly:

1. **Bound REM configured** — needed by remote_binding and hvac_fan_card
   to send commands to FAN devices via REM relays.
2. **Message Events with regex 31DA|10D0** — needed by the message
   stream / hvac_fan_card to receive real-time FAN status updates.
3. **Send Packet Service enabled** — needed by ramses_extras to send
   Ramses commands (bypass, fan speed, parameter updates) via the
   ramses_cc transport layer.

Also checks HA Core configuration:

4. **Recorder component loaded** — without the recorder, sensor history
   and long-term statistics are not stored.  This looks like a ramses_cc
   bug but is actually a missing HA Core config.
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

# ramses_cc config keys (imported lazily to avoid hard dependency)
_CONF_ADVANCED_FEATURES = "advanced_features"
_CONF_MESSAGE_EVENTS = "message_events"
_CONF_SEND_PACKET = "send_packet"
_CONF_SCHEMA = "schema"
_SZ_KNOWN_LIST = "known_list"
# known_list uses "bound" (SZ_BOUND_TO in ramses_rf), schema uses "_bound"
# (SZ_TR_BOUND in ramses_cc) — see fan_handler.setup_fan_bound_devices
_SZ_BOUND = "bound"
_SZ_TR_BOUND = "_bound"
_SZ_REMOTES = "remotes"

# Message codes that ramses_extras features rely on
_REQUIRED_MSG_CODES = ("31DA", "10D0")


def _get_ramses_cc_options(hass: HomeAssistant) -> dict[str, Any] | None:
    """Return the ramses_cc config entry options, or None if not loaded."""

    entries = hass.config_entries.async_entries("ramses_cc")
    if not entries:
        return None

    # Use the first (and typically only) ramses_cc entry
    entry = entries[0]
    options = dict(entry.options or {})

    # Also check hass.data for the coordinator's merged options
    ramses_cc_data = hass.data.get("ramses_cc", {})
    for _entry_id, coordinator in ramses_cc_data.items():
        if hasattr(coordinator, "options") and isinstance(coordinator.options, dict):
            # Coordinator.options is a deep merge of data + options
            return dict(coordinator.options)

    return options


def _check_bound_rem(options: dict[str, Any]) -> bool:
    """Check if any FAN device has a bound REM.

    Checks both the known_list (user override, key ``bound``) and the
    schema (SSOT, key ``_bound``) — mirroring fan_handler.setup_fan_bound_devices.
    Also recognises a non-empty ``remotes`` list on FAN entries.
    """

    def _entry_has_bound(device_config: Any) -> bool:
        if not isinstance(device_config, dict):
            return False
        if device_config.get(_SZ_BOUND):
            return True
        remotes = device_config.get(_SZ_REMOTES)
        if isinstance(remotes, list) and remotes:
            return True
        return False

    known_list = options.get(_SZ_KNOWN_LIST)
    if isinstance(known_list, dict):
        for _device_id, device_config in known_list.items():
            if _entry_has_bound(device_config):
                return True

    schema = options.get(_CONF_SCHEMA)
    if isinstance(schema, dict):
        for _device_id, device_config in schema.items():
            if isinstance(device_config, dict) and device_config.get(_SZ_TR_BOUND):
                return True

    return False


def _check_message_events(options: dict[str, Any]) -> tuple[bool, bool]:
    """Check if message events are enabled and match required codes.

    Returns (enabled, matches_required_codes).
    """

    advanced = options.get(_CONF_ADVANCED_FEATURES)
    if not isinstance(advanced, dict):
        return False, False

    regex_str = advanced.get(_CONF_MESSAGE_EVENTS)
    if not regex_str or not isinstance(regex_str, str):
        return False, False

    # Check if the regex contains the required message codes
    matches = any(code in regex_str for code in _REQUIRED_MSG_CODES)
    return True, matches


def _check_send_packet(options: dict[str, Any]) -> bool:
    """Check if the send_packet advanced feature is enabled."""

    advanced = options.get(_CONF_ADVANCED_FEATURES)
    if not isinstance(advanced, dict):
        return False

    return bool(advanced.get(_CONF_SEND_PACKET, False))


def _check_recorder(hass: HomeAssistant) -> bool:
    """Check if the HA recorder component is loaded."""

    return "recorder" in hass.config.components


async def validate_ramses_cc_config(hass: HomeAssistant) -> dict[str, bool]:
    """Validate ramses_cc configuration for ramses_extras requirements.

    Returns a dict with keys:
    - ramses_cc_loaded: True if ramses_cc config entry exists
    - has_bound_rem: True if at least one FAN has a bound REM
    - message_events_enabled: True if message events feature is on
    - message_events_matches: True if regex includes 31DA or 10D0
    - send_packet_enabled: True if send_packet is enabled
    - recorder_loaded: True if HA recorder component is loaded
    """

    result = {
        "ramses_cc_loaded": False,
        "has_bound_rem": False,
        "message_events_enabled": False,
        "message_events_matches": False,
        "send_packet_enabled": False,
        "recorder_loaded": False,
    }

    # Check recorder (HA Core config, not ramses_cc)
    result["recorder_loaded"] = _check_recorder(hass)

    # Get ramses_cc options
    options = _get_ramses_cc_options(hass)
    if options is None:
        _LOGGER.warning(
            "ramses_cc config entry not found — ramses_extras features "
            "that depend on ramses_cc (commands, message stream, FAN card) "
            "will not work until ramses_cc is configured"
        )
        return result

    result["ramses_cc_loaded"] = True

    # Run checks
    result["has_bound_rem"] = _check_bound_rem(options)
    result["message_events_enabled"], result["message_events_matches"] = (
        _check_message_events(options)
    )
    result["send_packet_enabled"] = _check_send_packet(options)

    return result


def log_validation_results(results: dict[str, bool]) -> None:
    """Log warnings for any missing ramses_cc configuration.

    Called after validation to inform the user of any settings that
    need to be adjusted in ramses_cc for ramses_extras to work correctly.
    """

    if not results.get("ramses_cc_loaded"):
        # Already logged in validate_ramses_cc_config
        return

    if not results.get("send_packet_enabled"):
        _LOGGER.warning(
            "ramses_cc 'Send Packet' advanced feature is not enabled — "
            "ramses_extras cannot send commands to FAN devices (bypass, "
            "fan speed, parameter updates). Enable it in ramses_cc "
            "configuration under Advanced Features."
        )

    if not results.get("message_events_enabled"):
        _LOGGER.warning(
            "ramses_cc 'Message Events' advanced feature is not enabled — "
            "the hvac_fan_card and message stream will not receive "
            "real-time FAN status updates. Enable it in ramses_cc "
            "configuration under Advanced Features with a regex that "
            "includes '31DA|10D0'."
        )
    elif not results.get("message_events_matches"):
        _LOGGER.warning(
            "ramses_cc 'Message Events' regex does not include required "
            "message codes 31DA|10D0 — the hvac_fan_card will not "
            "receive real-time FAN status updates. Update the regex in "
            "ramses_cc configuration under Advanced Features to include "
            "'31DA|10D0'."
        )

    if not results.get("has_bound_rem"):
        _LOGGER.warning(
            "No bound REM configured in ramses_cc known_list — "
            "remote_binding and FAN command relay will not work. "
            "Configure a bound REM for your FAN device in ramses_cc "
            "configuration under Known Devices."
        )

    if not results.get("recorder_loaded"):
        _LOGGER.warning(
            "HA recorder component is not loaded — sensor history and "
            "long-term statistics will not be stored. Add 'default_config:' "
            "or 'recorder:' to configuration.yaml."
        )
