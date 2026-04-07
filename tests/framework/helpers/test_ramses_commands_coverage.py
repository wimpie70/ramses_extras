"""Tests for ramses_commands to improve coverage."""

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.ramses_extras.framework.helpers.ramses_commands import (
    CommandResult,
    RamsesCommands,
    create_ramses_commands,
)


@pytest.fixture
def hass():
    """Mock Home Assistant."""
    hass = MagicMock()
    hass.data = {}
    return hass


@pytest.fixture
def commands(hass):
    """Create a RamsesCommands instance."""
    return RamsesCommands(hass)


class TestRamsesCommandsCoverage:
    """Additional tests for RamsesCommands."""

    def test_get_failed_commands_empty(self, commands):
        """Test get_failed_commands when no failures."""
        result = commands.get_failed_commands()
        assert result == {}

    def test_get_failed_commands_with_data(self, commands):
        """Test get_failed_commands returns failures."""
        commands._failed_commands = {
            "32:123456": {
                "command": {"code": "22F1", "verb": "I", "payload": "0003"},
                "timestamp": time.time(),
                "error": "Timeout error",
            }
        }

        result = commands.get_failed_commands()
        assert "32:123456" in result
        assert result["32:123456"]["error"] == "Timeout error"

    def test_get_failed_commands_cleans_old(self, commands):
        """Test get_failed_commands cleans up old failures."""
        old_time = time.time() - 400  # 400 seconds ago (older than 5 min)
        commands._failed_commands = {
            "32:123456": {
                "command": {"code": "22F1"},
                "timestamp": old_time,
                "error": "Old error",
            },
            "32:789012": {
                "command": {"code": "22F1"},
                "timestamp": time.time(),  # Recent
                "error": "New error",
            },
        }

        result = commands.get_failed_commands()
        assert "32:123456" not in result  # Cleaned up
        assert "32:789012" in result  # Kept

    def test_get_failed_commands_invalid_timestamp(self, commands):
        """Test get_failed_commands handles invalid timestamps."""
        commands._failed_commands = {
            "32:123456": {
                "command": {"code": "22F1"},
                "timestamp": "invalid",  # Not a number
                "error": "Error",
            }
        }

        result = commands.get_failed_commands()
        assert "32:123456" not in result  # Cleaned up due to invalid timestamp

    def test_clear_failed_commands_all(self, commands):
        """Test clear_failed_commands clears all."""
        commands._failed_commands = {
            "32:123456": {"command": {"code": "22F1"}, "timestamp": time.time()},
            "32:789012": {"command": {"code": "22F1"}, "timestamp": time.time()},
        }

        commands.clear_failed_commands()
        assert commands._failed_commands == {}

    def test_clear_failed_commands_specific_device(self, commands):
        """Test clear_failed_commands clears specific device."""
        commands._failed_commands = {
            "32:123456": {"command": {"code": "22F1"}, "timestamp": time.time()},
            "32:789012": {"command": {"code": "22F1"}, "timestamp": time.time()},
        }

        commands.clear_failed_commands("32:123456")
        assert "32:123456" not in commands._failed_commands
        assert "32:789012" in commands._failed_commands

    def test_clear_failed_commands_normalize_id(self, commands):
        """Test clear_failed_commands normalizes device_id."""
        commands._failed_commands = {
            "32:123456": {"command": {"code": "22F1"}, "timestamp": time.time()},
        }

        commands.clear_failed_commands("32_123456")  # With underscore
        assert "32:123456" not in commands._failed_commands

    def test_clear_failed_commands_no_attr(self, commands):
        """Test clear_failed_commands when _failed_commands not set."""
        # Should not crash
        commands.clear_failed_commands()

    def test_get_available_commands(self, commands):
        """Test get_available_commands."""
        with patch.object(
            commands._command_registry,
            "get_registered_commands",
            return_value={"fan_high": {"code": "22F1"}},
        ):
            result = commands.get_available_commands()
            assert "fan_high" in result

    def test_get_available_commands_not_dict(self, commands):
        """Test get_available_commands when registry returns non-dict."""
        with patch.object(
            commands._command_registry,
            "get_registered_commands",
            return_value="not_a_dict",
        ):
            result = commands.get_available_commands()
            assert result == {}

    def test_get_command_description_found(self, commands):
        """Test get_command_description when command exists."""
        with patch.object(
            commands._command_registry,
            "get_command",
            return_value={"description": "Fan high speed"},
        ):
            result = commands.get_command_description("fan_high")
            assert result == "Fan high speed"

    def test_get_command_description_not_found(self, commands):
        """Test get_command_description when command not found."""
        with patch.object(commands._command_registry, "get_command", return_value=None):
            result = commands.get_command_description("unknown")
            assert result == ""

    def test_get_queue_statistics(self, commands):
        """Test get_queue_statistics delegates to device_manager."""
        expected = {"queue_size": 5, "pending": 2}
        commands._device_manager.get_queue_statistics = MagicMock(return_value=expected)

        result = commands.get_queue_statistics()
        assert result == expected

    @pytest.mark.asyncio
    async def test_send_fan_command_not_found(self, commands):
        """Test send_fan_command when command not in registry."""
        with patch.object(commands._command_registry, "get_command", return_value=None):
            result = await commands.send_fan_command("32:123456", "unknown_command")
            assert result.success is False
            assert "not found" in result.error_message

    @pytest.mark.asyncio
    async def test_send_command_not_found(self, commands):
        """Test send_command when command not in registry."""
        with patch.object(commands._command_registry, "get_command", return_value=None):
            result = await commands.send_command("32:123456", "unknown")
            assert result.success is False
            assert "not found" in result.error_message

    @pytest.mark.asyncio
    async def test_set_fan_param_no_broker(self, commands):
        """Test set_fan_param when no broker found."""
        commands.hass.data = {"ramses_cc": {}}

        result = await commands.set_fan_param("32:123456", "7C00", "value")
        assert result.success is False
        assert "broker not found" in result.error_message


class TestCreateRamsesCommands:
    """Test create_ramses_commands factory."""

    def test_creates_instance(self, hass):
        """Test factory creates RamsesCommands."""
        result = create_ramses_commands(hass)
        assert isinstance(result, RamsesCommands)
        assert result.hass == hass
