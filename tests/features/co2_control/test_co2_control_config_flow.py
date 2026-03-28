"""Tests for CO2 Control config flow."""

from unittest.mock import MagicMock

import pytest
import voluptuous as vol

from custom_components.ramses_extras.features.co2_control.config_flow import (
    async_validate_co2_config,
    get_co2_control_schema,
    get_zone_config_schema,
)


@pytest.fixture
def hass():
    """Mock Home Assistant instance."""
    hass = MagicMock()
    hass.states.get.return_value = MagicMock()
    return hass


def test_get_co2_control_schema(hass):
    """Test CO2 control schema generation."""
    schema = get_co2_control_schema(hass, "test_device")

    # Test default values
    assert schema({})["enabled"] is False
    assert schema({})["automation_enabled"] is False
    assert schema({})["default_threshold"] == 1000
    assert schema({})["activation_hysteresis"] == 100
    assert schema({})["deactivation_hysteresis"] == -100

    # Test custom values
    data = {
        "enabled": True,
        "automation_enabled": True,
        "default_threshold": 1200,
        "activation_hysteresis": 150,
        "deactivation_hysteresis": -150,
    }
    result = schema(data)
    assert result["enabled"] is True
    assert result["automation_enabled"] is True
    assert result["default_threshold"] == 1200
    assert result["activation_hysteresis"] == 150
    assert result["deactivation_hysteresis"] == -150


def test_get_co2_control_schema_validation(hass):
    """Test CO2 control schema validation."""
    schema = get_co2_control_schema(hass, "test_device")

    # Test threshold validation
    with pytest.raises(vol.Invalid):
        schema({"default_threshold": 300})  # Below min

    with pytest.raises(vol.Invalid):
        schema({"default_threshold": 2500})  # Above max

    # Test activation hysteresis validation
    with pytest.raises(vol.Invalid):
        schema({"activation_hysteresis": -10})  # Negative not allowed

    # Test deactivation hysteresis validation
    with pytest.raises(vol.Invalid):
        schema({"deactivation_hysteresis": 10})  # Positive not allowed


def test_get_zone_config_schema(hass):
    """Test zone configuration schema."""
    schema = get_zone_config_schema(hass)

    # Test required fields
    data = {
        "zone_id": "test_zone",
        "zone_name": "Test Zone",
        "sensor_entity": "sensor.test_co2",
    }
    result = schema(data)
    assert result["zone_id"] == "test_zone"
    assert result["zone_name"] == "Test Zone"
    assert result["sensor_entity"] == "sensor.test_co2"
    assert result["threshold"] == 1000  # Default
    assert result["enabled"] is True  # Default

    # Test with optional fields
    data = {
        "zone_id": "test_zone",
        "zone_name": "Test Zone",
        "sensor_entity": "sensor.test_co2",
        "threshold": 1200,
        "enabled": False,
    }
    result = schema(data)
    assert result["threshold"] == 1200
    assert result["enabled"] is False


def test_get_zone_config_schema_validation(hass):
    """Test zone configuration schema validation."""
    schema = get_zone_config_schema(hass)

    # Test threshold validation
    with pytest.raises(vol.Invalid):
        schema(
            {
                "zone_id": "test_zone",
                "zone_name": "Test Zone",
                "sensor_entity": "sensor.test_co2",
                "threshold": 300,  # Below min
            }
        )

    with pytest.raises(vol.Invalid):
        schema(
            {
                "zone_id": "test_zone",
                "zone_name": "Test Zone",
                "sensor_entity": "sensor.test_co2",
                "threshold": 2500,  # Above max
            }
        )


@pytest.mark.asyncio
async def test_async_validate_co2_config_valid(hass):
    """Test validation of valid CO2 config."""
    config = {
        "default_threshold": 1000,
        "activation_hysteresis": 100,
        "deactivation_hysteresis": -100,
        "zones": [],
    }

    errors = await async_validate_co2_config(hass, config)
    assert errors == {}


@pytest.mark.asyncio
async def test_async_validate_co2_config_threshold_out_of_range(hass):
    """Test validation with threshold out of range."""
    config = {
        "default_threshold": 300,  # Below min
        "activation_hysteresis": 100,
        "deactivation_hysteresis": -100,
    }

    errors = await async_validate_co2_config(hass, config)
    assert errors["default_threshold"] == "threshold_out_of_range"


@pytest.mark.asyncio
async def test_async_validate_co2_config_activation_hysteresis_negative(hass):
    """Test validation with negative activation hysteresis."""
    config = {
        "default_threshold": 1000,
        "activation_hysteresis": -10,  # Should be positive
        "deactivation_hysteresis": -100,
    }

    errors = await async_validate_co2_config(hass, config)
    assert errors["activation_hysteresis"] == "must_be_positive"


@pytest.mark.asyncio
async def test_async_validate_co2_config_deactivation_hysteresis_positive(hass):
    """Test validation with positive deactivation hysteresis."""
    config = {
        "default_threshold": 1000,
        "activation_hysteresis": 100,
        "deactivation_hysteresis": 10,  # Should be negative
    }

    errors = await async_validate_co2_config(hass, config)
    assert errors["deactivation_hysteresis"] == "must_be_negative"


@pytest.mark.asyncio
async def test_async_validate_co2_config_zone_entity_not_found(hass):
    """Test validation with zone entity not found."""
    hass.states.get.return_value = None  # Entity not found

    config = {
        "default_threshold": 1000,
        "activation_hysteresis": 100,
        "deactivation_hysteresis": -100,
        "zones": [
            {
                "zone_id": "test_zone",
                "zone_name": "Test Zone",
                "sensor_entity": "sensor.nonexistent",
            }
        ],
    }

    errors = await async_validate_co2_config(hass, config)
    assert errors["zone_0_sensor"] == "entity_not_found"


@pytest.mark.asyncio
async def test_async_validate_co2_config_zone_entity_found(hass):
    """Test validation with zone entity found."""
    hass.states.get.return_value = MagicMock()  # Entity found

    config = {
        "default_threshold": 1000,
        "activation_hysteresis": 100,
        "deactivation_hysteresis": -100,
        "zones": [
            {
                "zone_id": "test_zone",
                "zone_name": "Test Zone",
                "sensor_entity": "sensor.existing",
            }
        ],
    }

    errors = await async_validate_co2_config(hass, config)
    assert errors == {}


@pytest.mark.asyncio
async def test_async_validate_co2_config_multiple_errors(hass):
    """Test validation with multiple errors."""
    hass.states.get.return_value = None  # Entity not found

    config = {
        "default_threshold": 300,  # Out of range
        "activation_hysteresis": -10,  # Negative
        "deactivation_hysteresis": 10,  # Positive
        "zones": [
            {
                "zone_id": "test_zone",
                "zone_name": "Test Zone",
                "sensor_entity": "sensor.nonexistent",
            }
        ],
    }

    errors = await async_validate_co2_config(hass, config)
    assert len(errors) == 4
    assert errors["default_threshold"] == "threshold_out_of_range"
    assert errors["activation_hysteresis"] == "must_be_positive"
    assert errors["deactivation_hysteresis"] == "must_be_negative"
    assert errors["zone_0_sensor"] == "entity_not_found"


@pytest.mark.asyncio
async def test_async_validate_co2_config_empty_config(hass):
    """Test validation with empty config."""
    errors = await async_validate_co2_config(hass, {})
    assert errors == {}  # Empty config should be valid
