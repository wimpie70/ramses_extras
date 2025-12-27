"""Default feature command definitions.

This module defines standard commands for device types that are available
to all features. Commands are registered with the command registry during
feature initialization.
"""

from ...framework.helpers.commands.registry import get_command_registry

# FAN command definitions
# These are the standard fan/ventilation commands available to all features
FAN_COMMANDS = {
    # Fan speed commands
    "fan_high": {
        "code": "22F1",
        "verb": " I",
        "payload": "000307",
        "description": "Set fan to high speed",
    },
    "fan_medium": {
        "code": "22F1",
        "verb": " I",
        "payload": "000207",
        "description": "Set fan to medium speed",
    },
    "fan_low": {
        "code": "22F1",
        "verb": " I",
        "payload": "000107",
        "description": "Set fan to low speed",
    },
    "fan_auto": {
        "code": "22F1",
        "verb": " I",
        "payload": "000407",
        "description": "Set fan to auto mode",
    },
    "fan_boost": {
        "code": "22F1",
        "verb": " I",
        "payload": "000607",
        "description": "Set fan to boost mode",
    },
    "fan_away": {
        "code": "22F1",
        "verb": " I",
        "payload": "000007",
        "description": "Set fan to away mode",
    },
    "fan_disable": {
        "code": "22F1",
        "verb": " I",
        "payload": "000707",
        "description": "Disable fan",
    },
    # Bypass commands
    "fan_bypass_open": {
        "code": "22F7",
        "verb": " W",
        "payload": "00C8EF",
        "description": "Open bypass",
    },
    "fan_bypass_close": {
        "code": "22F7",
        "verb": " W",
        "payload": "0000EF",
        "description": "Close bypass",
    },
    "fan_bypass_auto": {
        "code": "22F7",
        "verb": " W",
        "payload": "00FFEF",
        "description": "Set bypass to auto mode",
    },
    # Maintenance commands
    "fan_filter_reset": {
        "code": "10D0",
        "verb": " W",
        "payload": "00FF",
        "description": "Reset filter timer",
    },
    # Status request commands
    "fan_request10D0": {
        "code": "10D0",
        "verb": "RQ",
        "payload": "00",
        "description": "Request system status",
    },
    "fan_request31DA": {
        "code": "31DA",
        "verb": "RQ",
        "payload": "00",
        "description": "Request 31DA status",
    },
    # Timer commands
    "fan_timer_15min": {
        "code": "22F3",
        "verb": " I",
        "payload": "00120F03040404",
        "description": "Set 15 minute timer",
    },
    "fan_timer_30min": {
        "code": "22F3",
        "verb": " I",
        "payload": "00121E03040404",
        "description": "Set 30 minute timer",
    },
    "fan_timer_60min": {
        "code": "22F3",
        "verb": " I",
        "payload": "00123C03040404",
        "description": "Set 60 minute timer",
    },
}


def register_default_commands() -> None:
    """Register default device type commands with the command registry.

    This function is called during integration setup to make standard
    device commands available to all features.
    """
    registry = get_command_registry()

    # Register FAN commands by device type
    registry.register_device_commands(
        device_type="FAN",
        category="standard",
        commands=FAN_COMMANDS,
    )

    # Register commands globally for easy access
    registry.register_commands("default", FAN_COMMANDS)


__all__ = [
    "FAN_COMMANDS",
    "register_default_commands",
]
