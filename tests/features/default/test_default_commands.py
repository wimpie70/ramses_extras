"""Tests for default feature commands."""

from custom_components.ramses_extras.features.default.commands import (
    FAN_COMMANDS,
    register_default_commands,
)
from custom_components.ramses_extras.framework.helpers.commands.registry import (
    get_command_registry,
)


def test_fan_commands_structure():
    """Test that FAN_COMMANDS has expected structure."""
    assert isinstance(FAN_COMMANDS, dict)
    assert "fan_high" in FAN_COMMANDS
    assert "fan_low" in FAN_COMMANDS

    for _cmd_id, cmd_def in FAN_COMMANDS.items():
        assert "code" in cmd_def
        assert "verb" in cmd_def
        assert "payload" in cmd_def
        assert "description" in cmd_def


def test_register_default_commands():
    """Test that default commands are registered correctly."""
    registry = get_command_registry()

    # Register commands
    register_default_commands()

    # Verify FAN commands are registered in the "standard" category
    fan_cmds = registry.get_device_commands("FAN", "standard")
    assert fan_cmds is not None
    assert "fan_high" in fan_cmds
    assert fan_cmds["fan_high"] == FAN_COMMANDS["fan_high"]

    # Verify default commands are registered globally
    assert registry.get_command("fan_high") == FAN_COMMANDS["fan_high"]

    # Verify they are associated with the "default" feature
    assert "fan_high" in registry.list_commands_by_feature("default")
