"""Tests for commands/registry.py."""

import sys

import pytest

from custom_components.ramses_extras.framework.helpers.commands.registry import (
    CommandRegistry,
    get_command_registry,
)


class TestCommandRegistryInit:
    """Test CommandRegistry initialization."""

    def test_init(self):
        """Test basic initialization."""
        registry = CommandRegistry()
        assert registry._commands == {}
        assert registry._device_commands == {}


class TestRegisterCommands:
    """Test register_commands method."""

    def test_register_single_command(self):
        """Test registering a single command."""
        registry = CommandRegistry()
        commands = {
            "fan_high": {
                "code": "22F1",
                "verb": "I",
                "payload": "000307",
                "description": "Set fan to high speed",
            }
        }

        registry.register_commands("test_feature", commands)

        assert "fan_high" in registry._commands
        assert registry._commands["fan_high"]["definition"] == commands["fan_high"]
        assert registry._commands["fan_high"]["feature_id"] == "test_feature"

    def test_register_multiple_commands(self):
        """Test registering multiple commands."""
        registry = CommandRegistry()
        commands = {
            "fan_high": {"code": "22F1", "verb": "I", "payload": "000307"},
            "fan_low": {"code": "22F2", "verb": "I", "payload": "000302"},
        }

        registry.register_commands("test_feature", commands)

        assert len(registry._commands) == 2
        assert "fan_high" in registry._commands
        assert "fan_low" in registry._commands

    def test_register_duplicate_same_feature(self):
        """Test registering duplicate command from same feature."""
        registry = CommandRegistry()
        commands = {"fan_high": {"code": "22F1", "verb": "I", "payload": "000307"}}

        registry.register_commands("test_feature", commands)
        registry.register_commands("test_feature", commands)

        # Should only register once
        assert len(registry._commands) == 1

    def test_register_duplicate_different_feature(self):
        """Test registering duplicate command from different feature."""
        registry = CommandRegistry()
        commands1 = {"fan_high": {"code": "22F1", "verb": "I", "payload": "000307"}}
        commands2 = {"fan_high": {"code": "22F1", "verb": "I", "payload": "000307"}}

        registry.register_commands("feature1", commands1)
        registry.register_commands("feature2", commands2)

        # First feature wins
        assert registry._commands["fan_high"]["feature_id"] == "feature1"
        assert len(registry._commands) == 1


class TestRegisterDeviceCommands:
    """Test register_device_commands method."""

    def test_register_device_commands(self):
        """Test registering device-type specific commands."""
        registry = CommandRegistry()
        commands = {"high": {"code": "22F1"}, "low": {"code": "22F2"}}

        registry.register_device_commands("HvacVentilator", "fan_speeds", commands)

        assert "HvacVentilator" in registry._device_commands
        assert "fan_speeds" in registry._device_commands["HvacVentilator"]
        assert registry._device_commands["HvacVentilator"]["fan_speeds"] == commands

    def test_register_device_commands_new_device_type(self):
        """Test registering commands for new device type."""
        registry = CommandRegistry()
        commands = {"high": {"code": "22F1"}}

        registry.register_device_commands("NewDevice", "category", commands)

        assert "NewDevice" in registry._device_commands
        assert "category" in registry._device_commands["NewDevice"]

    def test_register_device_commands_new_category(self):
        """Test registering commands for new category."""
        registry = CommandRegistry()
        commands1 = {"high": {"code": "22F1"}}
        commands2 = {"low": {"code": "22F2"}}

        registry.register_device_commands("HvacVentilator", "fan_speeds", commands1)
        registry.register_device_commands("HvacVentilator", "bypass", commands2)

        assert "fan_speeds" in registry._device_commands["HvacVentilator"]
        assert "bypass" in registry._device_commands["HvacVentilator"]


class TestGetCommand:
    """Test get_command method."""

    def test_get_command_exists(self):
        """Test getting an existing command."""
        registry = CommandRegistry()
        commands = {"fan_high": {"code": "22F1", "verb": "I", "payload": "000307"}}

        registry.register_commands("test_feature", commands)
        result = registry.get_command("fan_high")

        assert result == commands["fan_high"]

    def test_get_command_not_exists(self):
        """Test getting a non-existent command."""
        registry = CommandRegistry()
        result = registry.get_command("nonexistent")

        assert result is None


class TestGetDeviceCommands:
    """Test get_device_commands method."""

    def test_get_device_commands_exists(self):
        """Test getting commands for existing device type and category."""
        registry = CommandRegistry()
        commands = {"high": {"code": "22F1"}}

        registry.register_device_commands("HvacVentilator", "fan_speeds", commands)
        result = registry.get_device_commands("HvacVentilator", "fan_speeds")

        assert result == commands

    def test_get_device_commands_not_exists(self):
        """Test getting commands for non-existent device type."""
        registry = CommandRegistry()
        result = registry.get_device_commands("NonExistent", "category")

        assert result == {}

    def test_get_device_commands_category_not_exists(self):
        """Test getting commands for non-existent category."""
        registry = CommandRegistry()
        registry.register_device_commands("HvacVentilator", "fan_speeds", {})
        result = registry.get_device_commands("HvacVentilator", "nonexistent")

        assert result == {}


class TestListCommandsByFeature:
    """Test list_commands_by_feature method."""

    def test_list_commands_by_feature(self):
        """Test listing commands by feature."""
        registry = CommandRegistry()
        commands = {
            "fan_high": {"code": "22F1"},
            "fan_low": {"code": "22F2"},
        }

        registry.register_commands("test_feature", commands)
        result = registry.list_commands_by_feature("test_feature")

        assert set(result) == {"fan_high", "fan_low"}

    def test_list_commands_by_feature_no_commands(self):
        """Test listing commands when feature has no commands."""
        registry = CommandRegistry()
        result = registry.list_commands_by_feature("nonexistent")

        assert result == []

    def test_list_commands_by_feature_multiple_features(self):
        """Test listing commands with multiple features."""
        registry = CommandRegistry()
        commands1 = {"fan_high": {"code": "22F1"}}
        commands2 = {"fan_low": {"code": "22F2"}}

        registry.register_commands("feature1", commands1)
        registry.register_commands("feature2", commands2)

        result1 = registry.list_commands_by_feature("feature1")
        result2 = registry.list_commands_by_feature("feature2")

        assert result1 == ["fan_high"]
        assert result2 == ["fan_low"]


class TestGetRegisteredCommands:
    """Test get_registered_commands method."""

    def test_get_registered_commands(self):
        """Test getting all registered commands."""
        registry = CommandRegistry()
        commands = {"fan_high": {"code": "22F1"}}

        registry.register_commands("test_feature", commands)
        result = registry.get_registered_commands()

        assert "fan_high" in result
        assert result["fan_high"]["definition"] == commands["fan_high"]
        assert result["fan_high"]["feature_id"] == "test_feature"

    def test_get_registered_commands_empty(self):
        """Test getting commands when none registered."""
        registry = CommandRegistry()
        result = registry.get_registered_commands()

        assert result == {}


class TestGetDeviceTypes:
    """Test get_device_types method."""

    def test_get_device_types(self):
        """Test getting all device types."""
        registry = CommandRegistry()
        registry.register_device_commands("HvacVentilator", "fan_speeds", {})
        registry.register_device_commands("Controller", "category", {})

        result = registry.get_device_types()

        assert set(result) == {"HvacVentilator", "Controller"}

    def test_get_device_types_empty(self):
        """Test getting device types when none registered."""
        registry = CommandRegistry()
        result = registry.get_device_types()

        assert result == []


class TestClearFeatureCommands:
    """Test clear_feature_commands method."""

    def test_clear_feature_commands(self):
        """Test clearing commands for a feature."""
        registry = CommandRegistry()
        commands = {"fan_high": {"code": "22F1"}, "fan_low": {"code": "22F2"}}

        registry.register_commands("test_feature", commands)
        removed_count = registry.clear_feature_commands("test_feature")

        assert removed_count == 2
        assert len(registry._commands) == 0

    def test_clear_feature_commands_no_commands(self):
        """Test clearing when feature has no commands."""
        registry = CommandRegistry()
        removed_count = registry.clear_feature_commands("nonexistent")

        assert removed_count == 0

    def test_clear_feature_commands_partial(self):
        """Test clearing one feature's commands among multiple."""
        registry = CommandRegistry()
        commands1 = {"fan_high": {"code": "22F1"}}
        commands2 = {"fan_low": {"code": "22F2"}}

        registry.register_commands("feature1", commands1)
        registry.register_commands("feature2", commands2)
        removed_count = registry.clear_feature_commands("feature1")

        assert removed_count == 1
        assert "fan_low" in registry._commands
        assert "fan_high" not in registry._commands


class TestGetCommandRegistry:
    """Test get_command_registry singleton function."""

    def test_get_command_registry_singleton(self):
        """Test that get_command_registry returns singleton."""
        registry1 = get_command_registry()
        registry2 = get_command_registry()

        assert registry1 is registry2

    def test_get_command_registry_initializes(self):
        """Test that get_command_registry initializes on first call."""
        # Reset the global registry for testing
        module_path = (
            "custom_components.ramses_extras.framework.helpers.commands.registry"
        )
        sys.modules[module_path]._command_registry = None

        registry = get_command_registry()

        assert isinstance(registry, CommandRegistry)
        assert sys.modules[module_path]._command_registry is registry
