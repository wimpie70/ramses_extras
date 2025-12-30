"""Tests for CO2 device type handler in sensor_control."""

import pytest
import voluptuous as vol
from homeassistant.helpers import selector

from custom_components.ramses_extras.features.sensor_control.device_types.co2 import (
    build_group_schema,
    get_group_options,
    handle_group_submission,
)


def test_get_group_options():
    """Test getting group options for CO2."""
    options = get_group_options("01:123456")
    assert isinstance(options, list)
    values = [opt["value"] for opt in options]
    assert "co2" in values
    assert "done" in values


def test_handle_group_submission():
    """Test handling group submission for CO2."""
    sources = {"existing": "data"}
    abs_inputs = {"abs": "data"}
    user_input = {"some": "input"}

    # CO2 handler is currently a no-op
    new_sources, new_abs = handle_group_submission(
        "co2", user_input, sources, abs_inputs
    )
    assert new_sources == sources
    assert new_abs == abs_inputs


def test_build_group_schema():
    """Test building schema for CO2."""
    schema, info = build_group_schema(
        "co2", {}, {}, [], [], selector.EntitySelector({})
    )
    assert isinstance(schema, vol.Schema)
    assert schema.schema == {}
    assert "preview only" in info or "not yet implemented" in info


def test_build_group_schema_invalid():
    """Test building schema for invalid group."""
    with pytest.raises(ValueError, match="Unsupported group_stage"):
        build_group_schema("invalid", {}, {}, [], [], selector.EntitySelector({}))
