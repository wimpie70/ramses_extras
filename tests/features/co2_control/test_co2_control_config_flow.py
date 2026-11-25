"""Tests for CO2 Control config flow."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import voluptuous as vol

from custom_components.ramses_extras.features.co2_control.config_flow import (
    _get_section_defaults,
    _persist_co2_control_settings,
    _sync_settings_to_number_entities,
    async_step_co2_control_config,
    async_validate_co2_config,
    get_co2_control_schema,
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
