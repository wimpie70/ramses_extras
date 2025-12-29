from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.core import HomeAssistant, ServiceCall

from custom_components.ramses_extras.const import DOMAIN
from custom_components.ramses_extras.features.default.services import (
    SVC_GET_QUEUE_STATISTICS,
    SVC_SEND_FAN_COMMAND,
    SVC_SET_FAN_PARAMETER,
    async_setup_services,
)


@pytest.fixture
def hass():
    """Mock Home Assistant."""
    hass = MagicMock(spec=HomeAssistant)
    hass.services = MagicMock()
    hass.data = {}
    return hass


async def test_async_setup_services(hass):
    """Test service registration."""
    hass.services.has_service.return_value = False

    await async_setup_services(hass)

    assert hass.services.async_register.call_count == 3
    registered_services = [
        call.args[1] for call in hass.services.async_register.call_args_list
    ]
    assert SVC_SEND_FAN_COMMAND in registered_services
    assert SVC_SET_FAN_PARAMETER in registered_services
    assert SVC_GET_QUEUE_STATISTICS in registered_services


async def test_send_fan_command_service(hass):
    """Test send_fan_command service call."""
    hass.services.has_service.return_value = False
    await async_setup_services(hass)

    # Get the registered function
    send_command_func = None
    for call in hass.services.async_register.call_args_list:
        if call.args[1] == SVC_SEND_FAN_COMMAND:
            send_command_func = call.args[2]
            break

    assert send_command_func is not None

    call = MagicMock()
    call.data = {"device_id": "32:123456", "command": "fan_high"}

    with patch(
        "custom_components.ramses_extras.features.default.services.RamsesCommands"
    ) as mock_commands_class:
        mock_commands = MagicMock()
        mock_commands.send_command = AsyncMock()
        mock_commands_class.return_value = mock_commands

        await send_command_func(call)

        mock_commands.send_command.assert_called_once_with("32:123456", "fan_high")


async def test_set_fan_parameter_service(hass):
    """Test set_fan_parameter service call."""
    hass.services.has_service.return_value = False
    await async_setup_services(hass)

    set_param_func = None
    for call in hass.services.async_register.call_args_list:
        if call.args[1] == SVC_SET_FAN_PARAMETER:
            set_param_func = call.args[2]
            break

    assert set_param_func is not None

    # Test without from_id
    call = MagicMock()
    call.data = {"device_id": "32:123456", "param_id": "01", "value": "10"}

    hass.services.async_call = AsyncMock()
    await set_param_func(call)

    hass.services.async_call.assert_called_with(
        "ramses_cc",
        "set_fan_param",
        {"device_id": "32:123456", "param_id": "01", "value": "10"},
    )

    # Test with from_id
    call_with_from = MagicMock()
    call_with_from.data = {
        "device_id": "32:123456",
        "param_id": "01",
        "value": "10",
        "from_id": "18:123456",
    }
    await set_param_func(call_with_from)
    hass.services.async_call.assert_called_with(
        "ramses_cc",
        "set_fan_param",
        {
            "device_id": "32:123456",
            "param_id": "01",
            "value": "10",
            "from_id": "18:123456",
        },
    )


async def test_get_queue_statistics_service(hass):
    """Test get_queue_statistics service call."""
    hass.services.has_service.return_value = False
    await async_setup_services(hass)

    get_stats_func = None
    for call in hass.services.async_register.call_args_list:
        if call.args[1] == SVC_GET_QUEUE_STATISTICS:
            get_stats_func = call.args[2]
            break

    assert get_stats_func is not None

    call = MagicMock()
    call.data = {}

    with patch(
        "custom_components.ramses_extras.features.default.services.RamsesCommands"
    ) as mock_commands_class:
        mock_commands = MagicMock()
        mock_commands.get_queue_statistics.return_value = {"sent": 10, "queued": 2}
        mock_commands_class.return_value = mock_commands

        await get_stats_func(call)

        assert hass.data[DOMAIN]["queue_statistics"] == {"sent": 10, "queued": 2}
