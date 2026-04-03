"""Tests for commands.py"""

from unittest.mock import MagicMock, patch

import pytest

from custom_components.ramses_extras.features.default.commands import (
    FAN_COMMANDS,
    register_default_commands,
)


def test_fan_commands_structure():
    """Test FAN_COMMANDS has expected structure"""
    assert isinstance(FAN_COMMANDS, dict)
    assert len(FAN_COMMANDS) > 0

    # Check a few expected commands exist
    expected_commands = ["fan_high", "fan_low", "fan_auto", "fan_away"]
    for cmd in expected_commands:
        assert cmd in FAN_COMMANDS


def test_fan_command_format():
    """Test each fan command has required fields"""
    for cmd_name, cmd_def in FAN_COMMANDS.items():
        assert "code" in cmd_def
        assert "verb" in cmd_def
        assert "payload" in cmd_def
        assert "description" in cmd_def

        # All fields should be strings
        assert isinstance(cmd_def["code"], str)
        assert isinstance(cmd_def["verb"], str)
        assert isinstance(cmd_def["payload"], str)
        assert isinstance(cmd_def["description"], str)


def test_register_default_commands():
    """Test register_default_commands"""
    with patch(
        "custom_components.ramses_extras.features.default.commands.get_command_registry"
    ) as mock_get_registry:
        mock_registry = MagicMock()
        mock_get_registry.return_value = mock_registry

        register_default_commands()

        # Verify commands were registered
        assert mock_registry.register_device_commands.called
        assert mock_registry.register_commands.called


def test_fan_high_command():
    """Test fan_high command definition"""
    cmd = FAN_COMMANDS["fan_high"]
    assert cmd["code"] == "22F1"
    assert cmd["payload"] == "000307"


def test_fan_auto_command():
    """Test fan_auto command definition"""
    cmd = FAN_COMMANDS["fan_auto"]
    assert cmd["code"] == "22F1"
    assert cmd["payload"] == "000407"


def test_bypass_commands():
    """Test bypass commands exist"""
    assert "fan_bypass_open" in FAN_COMMANDS
    assert "fan_bypass_close" in FAN_COMMANDS
    assert "fan_bypass_auto" in FAN_COMMANDS


def test_timer_commands():
    """Test timer commands exist"""
    assert "fan_timer_15min" in FAN_COMMANDS
    assert "fan_timer_30min" in FAN_COMMANDS
    assert "fan_timer_60min" in FAN_COMMANDS
