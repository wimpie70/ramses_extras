"""Tests for CO2 Control services."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.ramses_extras.features.co2_control.services import CO2Services


@pytest.fixture
def hass():
    """Mock Home Assistant instance."""
    hass = MagicMock()
    hass.services.async_register = MagicMock()
    return hass


@pytest.fixture
def config_entry():
    """Mock config entry."""
    return MagicMock()


def test_co2_services_init(hass, config_entry):
    """Test CO2Services initialization."""
    services = CO2Services(hass, config_entry)

    assert services.hass == hass
    assert services.config_entry == config_entry


@pytest.mark.asyncio
async def test_co2_services_async_register_services(hass, config_entry):
    """Test registering CO2 services."""
    services = CO2Services(hass, config_entry)

    await services.async_register_services()

    # Check all services were registered
    assert hass.services.async_register.call_count == 4

    # Check specific service registrations
    calls = hass.services.async_register.call_args_list
    # Each call has: ("ramses_extras", "service_name", handler)
    assert calls[0][0] == (
        "ramses_extras",
        "enable_co2_control",
        services._handle_enable_co2_control,
    )
    assert calls[1][0] == (
        "ramses_extras",
        "disable_co2_control",
        services._handle_disable_co2_control,
    )
    assert calls[2][0] == (
        "ramses_extras",
        "set_zone_threshold",
        services._handle_set_zone_threshold,
    )
    assert calls[3][0] == (
        "ramses_extras",
        "trigger_co2_boost",
        services._handle_trigger_co2_boost,
    )


@pytest.mark.asyncio
async def test_handle_enable_co2_control(hass, config_entry):
    """Test handling enable CO2 control service."""
    services = CO2Services(hass, config_entry)

    # Create mock service call
    call = MagicMock()
    call.data = {"device_id": "test_device"}

    # Handle the service call
    await services._handle_enable_co2_control(call)

    # The method should log the call
    # Implementation would update config entry


@pytest.mark.asyncio
async def test_handle_disable_co2_control(hass, config_entry):
    """Test handling disable CO2 control service."""
    services = CO2Services(hass, config_entry)

    # Create mock service call
    call = MagicMock()
    call.data = {"device_id": "test_device"}

    # Handle the service call
    await services._handle_disable_co2_control(call)

    # The method should log the call
    # Implementation would update config entry


@pytest.mark.asyncio
async def test_handle_set_zone_threshold(hass, config_entry):
    """Test handling set zone threshold service."""
    services = CO2Services(hass, config_entry)

    # Create mock service call
    call = MagicMock()
    call.data = {
        "device_id": "test_device",
        "zone_id": "living_room",
        "threshold": 1200,
    }

    # Handle the service call
    await services._handle_set_zone_threshold(call)

    # The method should log the call with all parameters
    # Implementation would update zone configuration


@pytest.mark.asyncio
async def test_handle_trigger_co2_boost(hass, config_entry):
    """Test handling trigger CO2 boost service."""
    services = CO2Services(hass, config_entry)

    # Create mock service call with duration
    call = MagicMock()
    call.data = {
        "device_id": "test_device",
        "duration_minutes": 45,
    }

    # Handle the service call
    await services._handle_trigger_co2_boost(call)

    # The method should log the call with duration
    # Implementation would trigger boost mode


@pytest.mark.asyncio
async def test_handle_trigger_co2_boost_default_duration(hass, config_entry):
    """Test handling trigger CO2 boost service with default duration."""
    services = CO2Services(hass, config_entry)

    # Create mock service call without duration
    call = MagicMock()
    call.data = MagicMock()
    call.data.get.side_effect = lambda key, default=None: {
        "device_id": "test_device",
        "duration_minutes": None,
    }.get(key, default)

    # Handle the service call
    await services._handle_trigger_co2_boost(call)

    # The method should use default duration of 30 minutes
    # Implementation would trigger boost mode with default duration


@pytest.mark.asyncio
async def test_handle_enable_co2_control_no_device_id(hass, config_entry):
    """Test handling enable CO2 control service without device_id."""
    services = CO2Services(hass, config_entry)

    # Create mock service call without device_id
    call = MagicMock()
    call.data = MagicMock()
    call.data.get.return_value = None

    # Handle the service call
    await services._handle_enable_co2_control(call)

    # Should handle gracefully even without device_id


@pytest.mark.asyncio
async def test_handle_set_zone_threshold_missing_params(hass, config_entry):
    """Test handling set zone threshold service with missing parameters."""
    services = CO2Services(hass, config_entry)

    # Create mock service call with missing parameters
    call = MagicMock()
    call.data = MagicMock()
    call.data.get.side_effect = lambda key, default=None: {
        "device_id": "test_device",
        "zone_id": None,
        "threshold": None,
    }.get(key, default)

    # Handle the service call
    await services._handle_set_zone_threshold(call)

    # Should handle gracefully even with missing parameters


@pytest.mark.asyncio
async def test_service_handlers_are_async(hass, config_entry):
    """Test that all service handlers are async methods."""
    services = CO2Services(hass, config_entry)

    # Check that handlers are async methods
    import inspect

    assert inspect.iscoroutinefunction(services._handle_enable_co2_control)
    assert inspect.iscoroutinefunction(services._handle_disable_co2_control)
    assert inspect.iscoroutinefunction(services._handle_set_zone_threshold)
    assert inspect.iscoroutinefunction(services._handle_trigger_co2_boost)
