"""Tests for Hello World feature services."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.core import HomeAssistant

from custom_components.ramses_extras.features.hello_world.const import DOMAIN
from custom_components.ramses_extras.features.hello_world.services import (
    SERVICE_BULK_TOGGLE,
    SERVICE_GET_SWITCH_STATE,
    SERVICE_TOGGLE_SWITCH,
    async_bulk_toggle_service,
    async_get_switch_state_service,
    async_setup_services,
    async_toggle_switch_service,
    async_unload_services,
    get_registered_services,
    get_service_info,
    validate_service_call,
)


@pytest.fixture
def hass():
    """Mock Home Assistant."""
    hass = MagicMock(spec=HomeAssistant)
    hass.services = MagicMock()
    hass.states = MagicMock()
    return hass


@pytest.fixture
def config_entry():
    """Mock Config Entry."""
    return MagicMock()


async def test_async_setup_services(hass, config_entry):
    """Test service registration."""
    hass.services.async_service_exists.return_value = False

    await async_setup_services(hass, config_entry)

    assert hass.services.async_register.call_count == 3


async def test_async_unload_services(hass):
    """Test service unloading."""
    hass.services.async_service_exists.return_value = True

    await async_unload_services(hass)

    assert hass.services.async_remove.call_count == 3


async def test_async_toggle_switch_service(hass):
    """Test toggle switch service handler."""
    call = MagicMock()
    call.data = {"device_id": "32:123456", "state": True}

    with patch(
        "custom_components.ramses_extras.features.hello_world.services.EntityHelpers"
    ) as mock_helpers:
        mock_helpers.generate_entity_name_from_template.return_value = (
            "switch.hello_world_switch_32_123456"
        )

        await async_toggle_switch_service(hass, call)

        hass.services.async_call.assert_called_once_with(
            "switch", "turn_on", {"entity_id": "switch.hello_world_switch_32_123456"}
        )


async def test_async_get_switch_state_service(hass):
    """Test get switch state service handler."""
    call = MagicMock()
    call.data = {"device_id": "32:123456"}

    with patch(
        "custom_components.ramses_extras.features.hello_world.services.EntityHelpers"
    ) as mock_helpers:
        mock_helpers.generate_entity_name_from_template.side_effect = [
            "switch.hello_world_switch_32_123456",
            "binary_sensor.hello_world_status_32_123456",
        ]

        await async_get_switch_state_service(hass, call)

        assert hass.states.get.call_count == 2


async def test_async_bulk_toggle_service(hass):
    """Test bulk toggle service handler."""
    call = MagicMock()
    call.data = {
        "entity_ids": ["switch.hello_world_switch_32_123456"],
        "state": True,
    }

    with patch(
        "custom_components.ramses_extras.features.hello_world.services.EntityHelpers"
    ) as mock_helpers:
        # Mock successful parsing for the specific entity ID
        mock_helpers.parse_entity_id.return_value = (
            "switch",
            "hello_world_switch",
            "32:123456",
        )

        await async_bulk_toggle_service(hass, call)

        hass.services.async_call.assert_called_once_with(
            "switch", "turn_on", {"entity_id": "switch.hello_world_switch_32_123456"}
        )


def test_get_service_info():
    """Test get_service_info returns correct metadata."""
    info = get_service_info()
    assert SERVICE_TOGGLE_SWITCH in info
    assert SERVICE_GET_SWITCH_STATE in info
    assert SERVICE_BULK_TOGGLE in info


def test_get_registered_services(hass):
    """Test get_registered_services list."""
    hass.services.async_services.return_value = {DOMAIN: {SERVICE_TOGGLE_SWITCH: None}}
    services = get_registered_services(hass)
    assert SERVICE_TOGGLE_SWITCH in services


def test_validate_service_call():
    """Test service call validation logic."""
    # Valid toggle
    valid, msg = validate_service_call(
        SERVICE_TOGGLE_SWITCH, {"device_id": "32:123456", "state": True}
    )
    assert valid is True

    # Invalid toggle - missing state
    valid, msg = validate_service_call(
        SERVICE_TOGGLE_SWITCH, {"device_id": "32:123456"}
    )
    assert valid is False
    assert "state" in msg.lower()

    # Valid bulk toggle
    valid, msg = validate_service_call(
        SERVICE_BULK_TOGGLE, {"entity_ids": ["switch.test"], "state": True}
    )
    assert valid is True

    # Invalid bulk toggle - not a list
    valid, msg = validate_service_call(
        SERVICE_BULK_TOGGLE, {"entity_ids": "not_a_list", "state": True}
    )
    assert valid is False
