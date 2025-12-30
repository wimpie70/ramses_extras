"""Tests for framework/helpers/ramses_commands.py."""

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.ramses_extras.framework.helpers.ramses_commands import (
    CommandResult,
    DeviceCommandManager,
    RamsesCommands,
    create_ramses_commands,
)


@pytest.fixture
def mock_hass():
    """Return a mock HomeAssistant instance."""
    hass = MagicMock()
    hass.services.async_call = AsyncMock()
    return hass


@pytest.fixture
def ramses_commands(mock_hass):
    """Return a RamsesCommands instance."""
    with patch(
        "custom_components.ramses_extras.framework.helpers.ramses_commands.get_command_registry"
    ):
        return RamsesCommands(mock_hass)


@pytest.mark.asyncio
async def test_command_result_dataclass():
    """Test CommandResult dataclass."""
    result = CommandResult(success=True, error_message="none", execution_time=1.0)
    assert result.success is True
    assert result.error_message == "none"
    assert result.execution_time == 1.0
    assert result.queued is False


@pytest.mark.asyncio
async def test_device_command_manager_init(ramses_commands):
    """Test DeviceCommandManager initialization."""
    manager = DeviceCommandManager(ramses_commands)
    stats = manager.get_queue_statistics()
    assert stats["command_statistics"]["total_commands"] == 0
    assert stats["queue_status"]["active_queues"] == 0


@pytest.mark.asyncio
async def test_send_command_to_device_immediate(ramses_commands):
    """Test sending command immediately (no rate limiting)."""
    manager = DeviceCommandManager(ramses_commands)
    device_id = "32:111111"
    command_def = {"code": "1060", "verb": "W", "payload": "00"}

    with patch.object(ramses_commands, "_send_packet", return_value=True) as mock_send:
        result = await manager.send_command_to_device(device_id, command_def)
        assert result.success is True
        assert result.queued is False
        mock_send.assert_called_once_with(device_id, command_def)


@pytest.mark.asyncio
async def test_send_command_to_device_queued(ramses_commands):
    """Test queuing command when rate limited."""
    manager = DeviceCommandManager(ramses_commands)
    manager._min_interval = 10.0  # Large interval to trigger rate limiting
    device_id = "32:111111"
    command_def = {"code": "1060", "verb": "W", "payload": "00"}

    # Set last command time to now
    manager._last_command_time[device_id] = time.time()

    with patch.object(ramses_commands, "_send_packet", return_value=True):
        result = await manager.send_command_to_device(device_id, command_def)
        assert result.success is True
        assert result.queued is True
        assert device_id in manager._queues
        assert manager._queue_depths[device_id] == 1


@pytest.mark.asyncio
async def test_ramses_commands_send_fan_command(ramses_commands):
    """Test sending fan command."""
    device_id = "32:111111"
    command_name = "fan_high"
    cmd_def = {"code": "22F1", "verb": "W", "payload": "03", "description": "High"}

    ramses_commands._command_registry.get_command.return_value = cmd_def

    with patch.object(ramses_commands, "_send_packet", return_value=True) as mock_send:
        result = await ramses_commands.send_fan_command(device_id, command_name)
        assert result.success is True
        mock_send.assert_called_once_with(device_id, cmd_def)


@pytest.mark.asyncio
async def test_ramses_commands_send_fan_command_not_found(ramses_commands):
    """Test sending fan command when not in registry."""
    ramses_commands._command_registry.get_command.return_value = None
    result = await ramses_commands.send_fan_command("32:111111", "invalid")
    assert result.success is False
    assert "not found" in result.error_message


@pytest.mark.asyncio
async def test_send_packet_success(ramses_commands, mock_hass):
    """Test _send_packet successful service call."""
    device_id = "32_111111"
    cmd_def = {"code": "1060", "verb": "W", "payload": "00", "description": "Test"}

    with patch.object(
        ramses_commands, "_get_bound_rem_device", return_value="30:111111"
    ):
        success = await ramses_commands._send_packet(device_id, cmd_def)
        assert success is True
        mock_hass.services.async_call.assert_awaited_once()
        args = mock_hass.services.async_call.call_args[0]
        assert args[0] == "ramses_cc"
        assert args[1] == "send_packet"
        assert args[2]["device_id"] == "32:111111"
        assert args[2]["from_id"] == "30:111111"


@pytest.mark.asyncio
async def test_send_packet_failure(ramses_commands, mock_hass):
    """Test _send_packet exception handling."""
    device_id = "32:111111"
    cmd_def = {"code": "1060", "verb": "W", "payload": "00", "description": "Test"}

    mock_hass.services.async_call.side_effect = Exception("Service error")

    success = await ramses_commands._send_packet(device_id, cmd_def)
    assert success is False


@pytest.mark.asyncio
async def test_send_command_success(ramses_commands):
    """Test send_command success."""
    device_id = "32:111111"
    command_name = "test_cmd"
    cmd_def = {"code": "1060", "verb": "W", "payload": "00"}

    ramses_commands._command_registry.get_command.return_value = cmd_def

    with patch.object(
        ramses_commands._device_manager,
        "send_command_to_device",
        return_value=CommandResult(success=True),
    ) as mock_send:
        result = await ramses_commands.send_command(device_id, command_name)
        assert result.success is True
        mock_send.assert_called_once_with(device_id, cmd_def, "normal", 30.0)


@pytest.mark.asyncio
async def test_send_command_not_found(ramses_commands):
    """Test send_command when not in registry."""
    ramses_commands._command_registry.get_command.return_value = None
    result = await ramses_commands.send_command("32:111111", "invalid")
    assert result.success is False
    assert "not found" in result.error_message


@pytest.mark.asyncio
async def test_get_command_description(ramses_commands):
    """Test get_command_description."""
    ramses_commands._command_registry.get_command.return_value = {
        "description": "Test Desc"
    }
    assert ramses_commands.get_command_description("cmd") == "Test Desc"

    ramses_commands._command_registry.get_command.return_value = None
    assert ramses_commands.get_command_description("cmd") == ""


@pytest.mark.asyncio
async def test_device_command_manager_queue_processing(ramses_commands):
    """Test queue processing logic including success and failure."""
    manager = DeviceCommandManager(ramses_commands)
    device_id = "32:111111"
    command_def = {"code": "1060"}

    # Mock _execute_command to succeed for first call and fail for second
    with patch.object(manager, "_execute_command") as mock_exec:
        mock_exec.side_effect = [
            CommandResult(success=True, execution_time=0.1),
            CommandResult(success=False, error_message="Failed", execution_time=0.1),
            TimeoutError(),  # To break the loop
        ]

        # Put items in queue
        queue = manager._get_device_queue(device_id)
        await queue.put({"command_def": command_def, "timeout": 30.0})
        await queue.put({"command_def": command_def, "timeout": 30.0})

        # Run processor
        await manager._process_device_queue(device_id)

        assert manager._command_stats["successful_commands"] == 1
        assert manager._command_stats["failed_commands"] == 1


@pytest.mark.asyncio
async def test_execute_command_exception(ramses_commands):
    """Test _execute_command handles exceptions."""
    manager = DeviceCommandManager(ramses_commands)
    with patch.object(
        ramses_commands, "_send_packet", side_effect=Exception("Packet error")
    ):
        result = await manager._execute_command("32:111111", {}, 30.0)
        assert result.success is False
        assert "Packet error" in result.error_message


@pytest.mark.asyncio
async def test_get_bound_rem_device_variations(ramses_commands, mock_hass):
    """Test _get_bound_rem_device with various scenarios."""
    device_id = "32:111111"

    # Scenario 1: No broker
    mock_hass.data = {}
    assert await ramses_commands._get_bound_rem_device(device_id) is None

    # Scenario 2: Broker with no _get_device
    mock_hass.data = {"ramses_cc": {"entry": MagicMock(spec=[])}}
    assert await ramses_commands._get_bound_rem_device(device_id) is None

    # Scenario 3: Device not found
    mock_broker = MagicMock()
    mock_broker._get_device.return_value = None
    mock_hass.data = {"ramses_cc": {"entry": mock_broker}}
    assert await ramses_commands._get_bound_rem_device(device_id) is None

    # Scenario 4: Device found but no get_bound_rem method
    mock_device = MagicMock(spec=[])
    mock_broker._get_device.return_value = mock_device
    assert await ramses_commands._get_bound_rem_device(device_id) is None

    # Scenario 5: Device found, has method, returns None
    mock_device = MagicMock()
    mock_device.get_bound_rem.return_value = None
    mock_broker._get_device.return_value = mock_device
    assert await ramses_commands._get_bound_rem_device(device_id) is None

    # Scenario 6: Exception
    mock_broker._get_device.side_effect = Exception("Lookup error")
    assert await ramses_commands._get_bound_rem_device(device_id) is None


@pytest.mark.asyncio
async def test_get_bound_rem_device(ramses_commands, mock_hass):
    """Test retrieving bound REM device."""
    device_id = "32:111111"
    mock_broker = MagicMock()
    mock_device = MagicMock()
    mock_rem = "30:222222"

    mock_hass.data = {"ramses_cc": {"entry_id": mock_broker}}
    mock_broker._get_device.return_value = mock_device
    mock_device.get_bound_rem.return_value = mock_rem

    rem = await ramses_commands._get_bound_rem_device(device_id)
    assert rem == mock_rem
    mock_broker._get_device.assert_called_with(device_id)


@pytest.mark.asyncio
async def test_create_ramses_commands(mock_hass):
    """Test factory function."""
    with patch(
        "custom_components.ramses_extras.framework.helpers.ramses_commands.get_command_registry"
    ):
        instance = create_ramses_commands(mock_hass)
        assert isinstance(instance, RamsesCommands)
