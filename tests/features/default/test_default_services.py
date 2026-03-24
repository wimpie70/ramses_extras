from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.core import HomeAssistant, ServiceCall

from custom_components.ramses_extras.const import DOMAIN
from custom_components.ramses_extras.features.default.services import (
    SVC_GET_QUEUE_STATISTICS,
    SVC_SEND_FAN_COMMAND,
    SVC_SET_FAN_PARAMETER,
    SVC_UPDATE_FAN_PARAMS,
    async_setup_services,
)


@pytest.fixture
def hass():
    """Mock Home Assistant."""
    hass = MagicMock(spec=HomeAssistant)
    hass.bus = MagicMock()
    hass.bus.async_listen = MagicMock(return_value=MagicMock())
    hass.services = MagicMock()
    hass.data = {}
    return hass


async def test_async_setup_services(hass):
    """Test service registration."""
    hass.services.has_service.return_value = False

    await async_setup_services(hass)

    assert hass.services.async_register.call_count == 4
    registered_services = [
        call.args[1] for call in hass.services.async_register.call_args_list
    ]
    assert SVC_SEND_FAN_COMMAND in registered_services
    assert SVC_SET_FAN_PARAMETER in registered_services
    assert SVC_UPDATE_FAN_PARAMS in registered_services
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
        "custom_components.ramses_extras.features.default.services.get_fan_speed_arbiter"
    ) as mock_get_arbiter:
        mock_arbiter = MagicMock()
        mock_arbiter.set_extras_control_enabled = MagicMock()
        mock_arbiter.set_manual_override_state = MagicMock()
        mock_arbiter.clear_demand_state = MagicMock()
        mock_arbiter.async_commit_state = AsyncMock()
        mock_get_arbiter.return_value = mock_arbiter

        await send_command_func(call)

        mock_arbiter.set_extras_control_enabled.assert_called_once_with(
            "32:123456", True
        )
        mock_arbiter.set_manual_override_state.assert_called_once_with(
            "32:123456",
            source_id="default_service",
            requested_speed="fan_high",
            reason="manual_card_command",
            metadata={"origin": "service"},
        )
        assert mock_arbiter.clear_demand_state.call_count == 2
        mock_arbiter.clear_demand_state.assert_any_call(
            "32:123456", feature_id="humidity_control"
        )
        mock_arbiter.clear_demand_state.assert_any_call(
            "32:123456", feature_id="co2_control"
        )
        mock_arbiter.async_commit_state.assert_awaited_once_with("32:123456")


async def test_send_fan_command_service_auto_clears_manual_override(hass):
    """Test fan_auto from manual mode clears override and resumes extras."""
    hass.services.has_service.return_value = False
    await async_setup_services(hass)
    hass.data[DOMAIN] = {
        "features": {
            "humidity_control": {
                "automation": MagicMock(
                    _reconcile_startup_states=AsyncMock(),
                )
            },
            "co2_control": {
                "automation": MagicMock(
                    _evaluate_co2_control=AsyncMock(),
                )
            },
        }
    }

    send_command_func = None
    for call in hass.services.async_register.call_args_list:
        if call.args[1] == SVC_SEND_FAN_COMMAND:
            send_command_func = call.args[2]
            break

    assert send_command_func is not None

    call = MagicMock()
    call.data = {"device_id": "32:123456", "command": "fan_auto"}

    with patch(
        "custom_components.ramses_extras.features.default.services.get_fan_speed_arbiter"
    ) as mock_get_arbiter:
        mock_arbiter = MagicMock()
        mock_arbiter.is_manual_override_active.return_value = True
        mock_arbiter.set_extras_control_enabled = MagicMock()
        mock_arbiter.clear_manual_override_state = MagicMock()
        mock_arbiter.async_commit_state = AsyncMock()
        mock_get_arbiter.return_value = mock_arbiter

        await send_command_func(call)

        mock_arbiter.set_extras_control_enabled.assert_called_once_with(
            "32:123456", True
        )
        mock_arbiter.clear_manual_override_state.assert_called_once_with("32:123456")
        mock_arbiter.async_commit_state.assert_awaited_once_with("32:123456")
        humidity_automation = hass.data[DOMAIN]["features"]["humidity_control"][
            "automation"
        ]
        co2_automation = hass.data[DOMAIN]["features"]["co2_control"]["automation"]
        humidity_automation._reconcile_startup_states.assert_awaited_once()
        co2_automation._evaluate_co2_control.assert_awaited_once_with("32:123456")


async def test_send_fan_command_service_auto_disables_extras_when_already_auto(hass):
    """Test fan_auto toggles extras control off when already in auto mode."""
    hass.services.has_service.return_value = False
    await async_setup_services(hass)

    send_command_func = None
    for call in hass.services.async_register.call_args_list:
        if call.args[1] == SVC_SEND_FAN_COMMAND:
            send_command_func = call.args[2]
            break

    assert send_command_func is not None

    call = MagicMock()
    call.data = {"device_id": "32:123456", "command": "fan_auto"}

    with patch(
        "custom_components.ramses_extras.features.default.services.get_fan_speed_arbiter"
    ) as mock_get_arbiter:
        mock_arbiter = MagicMock()
        mock_arbiter.is_manual_override_active.return_value = False
        mock_arbiter.is_extras_control_enabled.return_value = True
        mock_arbiter.set_extras_control_enabled = MagicMock()
        mock_arbiter.clear_manual_override_state = MagicMock()
        mock_arbiter.async_commit_state = AsyncMock()
        mock_get_arbiter.return_value = mock_arbiter

        await send_command_func(call)

        mock_arbiter.set_extras_control_enabled.assert_called_once_with(
            "32:123456", False
        )
        mock_arbiter.clear_manual_override_state.assert_called_once_with("32:123456")
        mock_arbiter.async_commit_state.assert_awaited_once_with("32:123456")


async def test_send_fan_command_service_away_disables_extras_before_direct_send(hass):
    """Test away command updates shared control state before direct send."""
    hass.services.has_service.return_value = False
    await async_setup_services(hass)

    send_command_func = None
    for call in hass.services.async_register.call_args_list:
        if call.args[1] == SVC_SEND_FAN_COMMAND:
            send_command_func = call.args[2]
            break

    assert send_command_func is not None

    call = MagicMock()
    call.data = {"device_id": "32:123456", "command": "fan_away"}

    with (
        patch(
            "custom_components.ramses_extras.features.default.services.get_fan_speed_arbiter"
        ) as mock_get_arbiter,
        patch(
            "custom_components.ramses_extras.features.default.services.RamsesCommands"
        ) as mock_commands_class,
    ):
        mock_arbiter = MagicMock()
        mock_arbiter.set_extras_control_enabled = MagicMock()
        mock_arbiter.clear_manual_override_state = MagicMock()
        mock_arbiter.async_commit_state = AsyncMock()
        mock_get_arbiter.return_value = mock_arbiter

        mock_commands = MagicMock()
        mock_commands.send_command = AsyncMock()
        mock_commands_class.return_value = mock_commands

        await send_command_func(call)

        mock_arbiter.set_extras_control_enabled.assert_called_once_with(
            "32:123456", False
        )
        mock_arbiter.clear_manual_override_state.assert_called_once_with("32:123456")
        mock_arbiter.async_commit_state.assert_awaited_once_with(
            "32:123456", apply=False
        )
        mock_commands.send_command.assert_awaited_once_with("32:123456", "fan_away")


async def test_send_fan_command_service_requests_still_use_direct_path(hass):
    """Test non-speed commands still use the direct command path."""
    hass.services.has_service.return_value = False
    await async_setup_services(hass)

    send_command_func = None
    for call in hass.services.async_register.call_args_list:
        if call.args[1] == SVC_SEND_FAN_COMMAND:
            send_command_func = call.args[2]
            break

    assert send_command_func is not None

    call = MagicMock()
    call.data = {"device_id": "32:123456", "command": "fan_request31DA"}

    with patch(
        "custom_components.ramses_extras.features.default.services.RamsesCommands"
    ) as mock_commands_class:
        mock_commands = MagicMock()
        mock_commands.send_command = AsyncMock()
        mock_commands_class.return_value = mock_commands

        await send_command_func(call)

        mock_commands.send_command.assert_called_once_with(
            "32:123456", "fan_request31DA"
        )


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

    with patch(
        "custom_components.ramses_extras.features.default.services.RamsesCommands"
    ) as mock_commands_class:
        mock_commands = MagicMock()
        mock_commands.set_fan_param = AsyncMock()
        mock_commands_class.return_value = mock_commands

        await set_param_func(call)

        mock_commands.set_fan_param.assert_called_with("32:123456", "01", "10", None)

    # Test with from_id
    call_with_from = MagicMock()
    call_with_from.data = {
        "device_id": "32:123456",
        "param_id": "01",
        "value": "10",
        "from_id": "18:123456",
    }
    with patch(
        "custom_components.ramses_extras.features.default.services.RamsesCommands"
    ) as mock_commands_class:
        mock_commands = MagicMock()
        mock_commands.set_fan_param = AsyncMock()
        mock_commands_class.return_value = mock_commands

        await set_param_func(call_with_from)

        mock_commands.set_fan_param.assert_called_with(
            "32:123456", "01", "10", "18:123456"
        )


async def test_update_fan_params_service(hass):
    """Test update_fan_params service call."""
    hass.services.has_service.return_value = False
    await async_setup_services(hass)

    update_params_func = None
    for call in hass.services.async_register.call_args_list:
        if call.args[1] == SVC_UPDATE_FAN_PARAMS:
            update_params_func = call.args[2]
            break

    assert update_params_func is not None

    call = MagicMock()
    call.data = {"device_id": "32:123456"}

    with patch(
        "custom_components.ramses_extras.features.default.services.RamsesCommands"
    ) as mock_commands_class:
        mock_commands = MagicMock()
        mock_commands.update_fan_params = AsyncMock()
        mock_commands_class.return_value = mock_commands

        await update_params_func(call)

        mock_commands.update_fan_params.assert_called_once_with("32:123456", None)

    # Test with from_id
    call_with_from = MagicMock()
    call_with_from.data = {"device_id": "32:123456", "from_id": "18:123456"}
    with patch(
        "custom_components.ramses_extras.features.default.services.RamsesCommands"
    ) as mock_commands_class:
        mock_commands = MagicMock()
        mock_commands.update_fan_params = AsyncMock()
        mock_commands_class.return_value = mock_commands

        await update_params_func(call_with_from)

        mock_commands.update_fan_params.assert_called_once_with(
            "32:123456", "18:123456"
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
