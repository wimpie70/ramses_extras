"""Tests for Ramses Commands helper."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.ramses_extras.framework.helpers.ramses_commands import (
    CommandResult,
    DeviceCommandManager,
    RamsesCommands,
    create_ramses_commands,
)


@pytest.fixture
def hass():
    """Mock Home Assistant."""
    return MagicMock()


@pytest.fixture
def ramses_commands(hass):
    """RamsesCommands instance."""
    patch_path = (
        "custom_components.ramses_extras.framework.helpers."
        "ramses_commands.get_command_registry"
    )
    with patch(patch_path) as mock_registry:
        mock_reg = MagicMock()
        mock_registry.return_value = mock_reg
        # Setup common commands
        mock_reg.get_command.side_effect = lambda cmd: {
            "fan_high": {
                "code": "22F1",
                "verb": "I",
                "payload": "000307",
                "description": "High",
            },
            "fan_low": {
                "code": "22F1",
                "verb": "I",
                "payload": "000107",
                "description": "Low",
            },
        }.get(cmd)
        mock_reg.get_registered_commands.return_value = {"fan_high": {}, "fan_low": {}}
        return RamsesCommands(hass)


class TestCommandResult:
    """Test CommandResult dataclass."""

    def test_init(self):
        """Test initialization."""
        result = CommandResult(
            success=True,
            error_message="none",
            response_data={"val": 1},
            queued=False,
            execution_time=0.1,
        )
        assert result.success is True
        assert result.error_message == "none"
        assert result.response_data == {"val": 1}
        assert result.queued is False
        assert result.execution_time == 0.1


class TestDeviceCommandManager:
    """Test DeviceCommandManager class."""

    @pytest.mark.asyncio
    async def test_send_command_to_device_immediate(self, ramses_commands):
        """Test immediate command execution."""
        manager = DeviceCommandManager(ramses_commands)
        ramses_commands._send_packet = AsyncMock(return_value=True)

        cmd_def = {"code": "1234", "verb": "W", "payload": "00", "description": "Test"}
        result = await manager.send_command_to_device("32_123456", cmd_def)

        assert result.success is True
        assert result.queued is False
        assert manager._command_stats["total_commands"] == 1
        assert manager._command_stats["successful_commands"] == 1

    @pytest.mark.asyncio
    async def test_send_command_to_device_queued(self, ramses_commands):
        """Test command queuing due to rate limiting."""
        manager = DeviceCommandManager(ramses_commands)
        manager._min_interval = 10.0  # Force queuing
        ramses_commands._send_packet = AsyncMock(return_value=True)

        cmd_def = {"code": "1234", "verb": "W", "payload": "00", "description": "Test"}

        # First command - immediate
        await manager.send_command_to_device("32_123456", cmd_def)

        # Second command - should be queued
        result = await manager.send_command_to_device("32_123456", cmd_def)

        assert result.success is True
        assert result.queued is True
        assert manager._command_stats["queued_commands"] == 1
        assert "32_123456" in manager._queues
        assert manager._queues["32_123456"].qsize() == 1

    @pytest.mark.asyncio
    async def test_execute_command_error(self, ramses_commands):
        """Test command execution error handling."""
        manager = DeviceCommandManager(ramses_commands)
        ramses_commands._send_packet = AsyncMock(
            side_effect=Exception("Execution failed")
        )

        cmd_def = {"code": "1234", "verb": "W", "payload": "00", "description": "Test"}
        result = await manager._execute_command("32_123456", cmd_def, 10.0)

        assert result.success is False
        assert "Execution failed" in result.error_message

    def test_get_queue_statistics(self, ramses_commands):
        """Test statistics generation."""
        manager = DeviceCommandManager(ramses_commands)
        manager._command_stats = {
            "total_commands": 10,
            "successful_commands": 8,
            "failed_commands": 2,
            "queued_commands": 5,
            "total_execution_time": 1.0,
        }
        stats = manager.get_queue_statistics()
        assert stats["command_statistics"]["total_commands"] == 10
        assert stats["command_statistics"]["success_rate_percent"] == 80.0
        assert stats["command_statistics"]["average_execution_time"] == 0.1


class TestRamsesCommands:
    """Test RamsesCommands class."""

    @pytest.mark.asyncio
    async def test_send_fan_command_success(self, ramses_commands, hass):
        """Test successful fan command."""
        ramses_commands._send_packet = AsyncMock(return_value=True)
        result = await ramses_commands.send_fan_command("32_123456", "fan_high")

        assert result.success is True
        ramses_commands._send_packet.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_fan_command_not_found(self, ramses_commands):
        """Test fan command not found in registry."""
        result = await ramses_commands.send_fan_command("32_123456", "invalid_command")
        assert result.success is False
        assert "not found" in result.error_message

    @pytest.mark.asyncio
    async def test_send_command(self, ramses_commands):
        """Test generic send_command."""
        ramses_commands._device_manager.send_command_to_device = AsyncMock(
            return_value=CommandResult(success=True)
        )
        result = await ramses_commands.send_command("32_123456", "fan_low")

        assert result.success is True
        ramses_commands._device_manager.send_command_to_device.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_packet_success(self, ramses_commands, hass):
        """Test low-level packet sending via coordinator."""
        # Mock the coordinator and client
        mock_coordinator = MagicMock()
        mock_client = MagicMock()
        mock_cmd = MagicMock()
        mock_client.create_cmd = MagicMock(return_value=mock_cmd)
        mock_client.async_send_cmd = AsyncMock()
        mock_client.hgi.id = "18:000001"
        mock_coordinator.client = mock_client

        cmd_def = {
            "code": "22F1",
            "verb": "I",
            "payload": "000307",
            "description": "High",
        }

        # Mock helper methods
        with (
            patch.object(
                ramses_commands,
                "_get_ramses_cc_coordinator",
                return_value=mock_coordinator,
            ),
            patch.object(
                ramses_commands, "_get_bound_rem_device", return_value="18:111111"
            ),
        ):
            success = await ramses_commands._send_packet("32_123456", cmd_def)
            assert success is True
            mock_client.create_cmd.assert_called_once_with(
                device_id="32:123456",
                verb="I",
                code="22F1",
                payload="000307",
                from_id="18:111111",
            )
            mock_client.async_send_cmd.assert_called_once_with(mock_cmd)

    @pytest.mark.asyncio
    async def test_send_packet_failure(self, ramses_commands, hass):
        """Test packet sending failure."""
        # Mock coordinator with failing client
        mock_coordinator = MagicMock()
        mock_client = MagicMock()
        mock_client.create_cmd = MagicMock(
            side_effect=Exception("Command creation failed")
        )
        mock_coordinator.client = mock_client

        cmd_def = {
            "code": "22F1",
            "verb": "I",
            "payload": "000307",
            "description": "High",
        }

        with patch.object(
            ramses_commands, "_get_ramses_cc_coordinator", return_value=mock_coordinator
        ):
            success = await ramses_commands._send_packet("32_123456", cmd_def)
            assert success is False

    @pytest.mark.asyncio
    async def test_send_packet_coordinator_not_found(self, ramses_commands, hass):
        """Test packet sending when ramses_cc coordinator is not available."""
        cmd_def = {
            "code": "22F1",
            "verb": "I",
            "payload": "000307",
            "description": "High",
        }

        with patch.object(
            ramses_commands, "_get_ramses_cc_coordinator", return_value=None
        ):
            success = await ramses_commands._send_packet("32_123456", cmd_def)
            assert success is False

    @pytest.mark.asyncio
    async def test_get_bound_rem_device(self, ramses_commands, hass):
        """Test getting bound REM device."""
        mock_device = MagicMock()
        mock_device.get_bound_rem.return_value = "18:123456"

        mock_broker = MagicMock()
        mock_broker._get_device.return_value = mock_device

        hass.data = {"ramses_cc": {"entry_id": mock_broker}}

        result = await ramses_commands._get_bound_rem_device("32:153289")
        assert result == "18:123456"

    def test_get_available_commands(self, ramses_commands):
        """Test getting available commands."""
        commands = ramses_commands.get_available_commands()
        assert "fan_high" in commands

    def test_get_command_description(self, ramses_commands):
        """Test getting command description."""
        desc = ramses_commands.get_command_description("fan_high")
        assert desc == "High"

        assert ramses_commands.get_command_description("invalid") == ""

    def test_get_queue_statistics(self, ramses_commands):
        """Test statistics delegation."""
        ramses_commands._device_manager.get_queue_statistics = MagicMock(
            return_value={"stat": 1}
        )
        assert ramses_commands.get_queue_statistics() == {"stat": 1}


@pytest.mark.asyncio
async def test_update_fan_params_success(ramses_commands, hass):
    """Test successful fan params update."""
    mock_broker = MagicMock()
    mock_broker.get_all_fan_params = MagicMock()
    hass.data = {"ramses_cc": {"entry_id": mock_broker}}

    result = await ramses_commands.update_fan_params("32_123456", "18_654321")

    assert result.success is True
    mock_broker.get_all_fan_params.assert_called_once_with(
        {"device_id": "32:123456", "from_id": "18_654321"}
    )


@pytest.mark.asyncio
async def test_update_fan_params_no_broker(ramses_commands, hass):
    """Test fan params update when broker not found."""
    hass.data = {"ramses_cc": {}}

    result = await ramses_commands.update_fan_params("32_123456")

    assert result.success is False
    assert "broker not found" in result.error_message


@pytest.mark.asyncio
async def test_update_fan_params_error(ramses_commands, hass):
    """Test fan params update error handling."""
    mock_broker = MagicMock()
    mock_broker.get_all_fan_params.side_effect = RuntimeError("Update failed")
    hass.data = {"ramses_cc": {"entry_id": mock_broker}}

    result = await ramses_commands.update_fan_params("32_123456")

    assert result.success is False
    assert "Update failed" in result.error_message


@pytest.mark.asyncio
async def test_set_fan_param_success(ramses_commands, hass):
    """Test successful fan param setting."""
    mock_broker = MagicMock()
    mock_broker.async_set_fan_param = AsyncMock()
    hass.data = {"ramses_cc": {"entry_id": mock_broker}}

    result = await ramses_commands.set_fan_param(
        "32_123456", "01", "value", "18_654321"
    )

    assert result.success is True
    mock_broker.async_set_fan_param.assert_called_once_with(
        {
            "device_id": "32:123456",
            "param_id": "01",
            "value": "value",
            "from_id": "18_654321",
        }
    )


@pytest.mark.asyncio
async def test_set_fan_param_no_broker(ramses_commands, hass):
    """Test fan param setting when broker not found."""
    hass.data = {"ramses_cc": {}}

    result = await ramses_commands.set_fan_param("32_123456", "01", "value")

    assert result.success is False
    assert "broker not found" in result.error_message


@pytest.mark.asyncio
async def test_set_fan_param_error(ramses_commands, hass):
    """Test fan param setting error handling."""
    mock_broker = MagicMock()
    mock_broker.async_set_fan_param = AsyncMock(side_effect=RuntimeError("Set failed"))
    hass.data = {"ramses_cc": {"entry_id": mock_broker}}

    result = await ramses_commands.set_fan_param("32_123456", "01", "value")

    assert result.success is False
    assert "Set failed" in result.error_message


def test_create_ramses_commands(hass):
    """Test factory function."""
    patch_path = (
        "custom_components.ramses_extras.framework.helpers."
        "ramses_commands.get_command_registry"
    )
    with patch(patch_path):
        instance = create_ramses_commands(hass)
        assert isinstance(instance, RamsesCommands)
