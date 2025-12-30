"""Tests for fan device type handler in sensor_control."""

import pytest
import voluptuous as vol
from homeassistant.helpers import selector

from custom_components.ramses_extras.features.sensor_control.device_types.fan import (
    _abs_humidity_part_from_input,
    _abs_temp_part_from_input,
    _source_from_input,
    build_group_schema,
    get_group_options,
    handle_group_submission,
)


def test_get_group_options():
    """Test getting group options for FAN."""
    options = get_group_options("01:123456")
    assert isinstance(options, list)
    values = [opt["value"] for opt in options]
    assert "indoor_basic" in values
    assert "outdoor_basic" in values
    assert "co2" in values
    assert "indoor_abs" in values
    assert "outdoor_abs" in values
    assert "done" in values


def test_source_from_input():
    """Test building source from input."""
    # Internal
    assert _source_from_input({}, "kind", "ent", False) == {"kind": "internal"}
    # External with entity
    user_input = {"k": "external", "e": "sensor.test"}
    assert _source_from_input(user_input, "k", "e", False) == {
        "kind": "external",
        "entity_id": "sensor.test",
    }
    # External without entity
    assert _source_from_input({"k": "external"}, "k", "e", False) == {
        "kind": "internal"
    }
    # None allowed
    assert _source_from_input({"k": "none"}, "k", "e", True) == {"kind": "none"}
    # None not allowed
    assert _source_from_input({"k": "none"}, "k", "e", False) == {"kind": "internal"}


def test_abs_temp_part_from_input():
    """Test absolute humidity temperature part from input."""
    assert _abs_temp_part_from_input({"k": "internal"}, "k", "e") == {
        "kind": "internal"
    }
    user_input = {"k": "external_temp", "e": "s.t"}
    assert _abs_temp_part_from_input(user_input, "k", "e") == {
        "kind": "external_temp",
        "entity_id": "s.t",
    }
    user_input = {"k": "external_abs", "e": "s.a"}
    assert _abs_temp_part_from_input(user_input, "k", "e") == {
        "kind": "external_abs",
        "entity_id": "s.a",
    }
    # Legacy "external" becomes "external_temp"
    user_input = {"k": "external", "e": "s.t"}
    assert _abs_temp_part_from_input(user_input, "k", "e") == {
        "kind": "external_temp",
        "entity_id": "s.t",
    }
    assert _abs_temp_part_from_input({"k": "external"}, "k", "e") == {
        "kind": "internal"
    }


def test_abs_humidity_part_from_input():
    """Test absolute humidity humidity part from input."""
    assert _abs_humidity_part_from_input({"k": "internal"}, "k", "e") == {
        "kind": "internal"
    }
    user_input = {"k": "external", "e": "s.h"}
    assert _abs_humidity_part_from_input(user_input, "k", "e") == {
        "kind": "external",
        "entity_id": "s.h",
    }
    assert _abs_humidity_part_from_input({"k": "none"}, "k", "e") == {"kind": "none"}
    assert _abs_humidity_part_from_input({"k": "external"}, "k", "e") == {
        "kind": "internal"
    }


def test_handle_group_submission_indoor_basic():
    """Test handling indoor_basic group submission."""
    sources = {}
    abs_inputs = {}
    user_input = {
        "indoor_temperature_kind": "external",
        "indoor_temperature_entity": "sensor.temp",
        "indoor_humidity_kind": "internal",
    }
    new_sources, new_abs = handle_group_submission(
        "indoor_basic", user_input, sources, abs_inputs
    )
    assert new_sources["indoor_temperature"] == {
        "kind": "external",
        "entity_id": "sensor.temp",
    }
    assert new_sources["indoor_humidity"] == {"kind": "internal"}


def test_handle_group_submission_outdoor_basic():
    """Test handling outdoor_basic group submission."""
    sources = {}
    abs_inputs = {}
    user_input = {
        "outdoor_temperature_kind": "internal",
        "outdoor_humidity_kind": "external",
        "outdoor_humidity_entity": "sensor.hum",
    }
    new_sources, new_abs = handle_group_submission(
        "outdoor_basic", user_input, sources, abs_inputs
    )
    assert new_sources["outdoor_temperature"] == {"kind": "internal"}
    assert new_sources["outdoor_humidity"] == {
        "kind": "external",
        "entity_id": "sensor.hum",
    }


def test_handle_group_submission_co2():
    """Test handling co2 group submission."""
    sources = {}
    abs_inputs = {}
    user_input = {"co2_kind": "none"}
    new_sources, new_abs = handle_group_submission(
        "co2", user_input, sources, abs_inputs
    )
    assert new_sources["co2"] == {"kind": "none"}


def test_handle_group_submission_indoor_abs():
    """Test handling indoor_abs group submission."""
    sources = {}
    abs_inputs = {}
    user_input = {
        "indoor_abs_humidity_temperature_kind": "external_temp",
        "indoor_abs_humidity_temperature_entity": "sensor.t",
        "indoor_abs_humidity_humidity_kind": "external",
        "indoor_abs_humidity_humidity_entity": "sensor.h",
    }
    new_sources, new_abs = handle_group_submission(
        "indoor_abs", user_input, sources, abs_inputs
    )
    assert new_abs["indoor_abs_humidity"]["temperature"] == {
        "kind": "external_temp",
        "entity_id": "sensor.t",
    }
    assert new_abs["indoor_abs_humidity"]["humidity"] == {
        "kind": "external",
        "entity_id": "sensor.h",
    }


def test_handle_group_submission_outdoor_abs():
    """Test handling outdoor_abs group submission."""
    sources = {}
    abs_inputs = {}
    user_input = {
        "outdoor_abs_humidity_temperature_kind": "external_abs",
        "outdoor_abs_humidity_temperature_entity": "sensor.abs",
        "outdoor_abs_humidity_humidity_kind": "internal",
    }
    new_sources, new_abs = handle_group_submission(
        "outdoor_abs", user_input, sources, abs_inputs
    )
    # If external_abs is selected, humidity should be forced to none
    assert new_abs["outdoor_abs_humidity"]["temperature"] == {
        "kind": "external_abs",
        "entity_id": "sensor.abs",
    }
    assert new_abs["outdoor_abs_humidity"]["humidity"] == {"kind": "none"}


def test_handle_group_submission_indoor_abs_none_humidity():
    """Test handling indoor_abs group submission with none humidity."""
    sources = {}
    abs_inputs = {}
    user_input = {
        "indoor_abs_humidity_temperature_kind": "internal",
        "indoor_abs_humidity_humidity_kind": "none",
    }
    new_sources, new_abs = handle_group_submission(
        "indoor_abs", user_input, sources, abs_inputs
    )
    # If humidity is none, temperature should also be forced to none
    assert new_abs["indoor_abs_humidity"]["temperature"] == {"kind": "none"}
    assert new_abs["indoor_abs_humidity"]["humidity"] == {"kind": "none"}


def test_build_group_schema_indoor_basic():
    """Test building schema for indoor_basic."""
    schema, info = build_group_schema(
        "indoor_basic", {}, {}, [], [], selector.EntitySelector({})
    )
    assert isinstance(schema, vol.Schema)
    assert "indoor_temperature_kind" in schema.schema
    assert "indoor_humidity_kind" in schema.schema


def test_build_group_schema_outdoor_basic():
    """Test building schema for outdoor_basic."""
    schema, info = build_group_schema(
        "outdoor_basic", {}, {}, [], [], selector.EntitySelector({})
    )
    assert isinstance(schema, vol.Schema)
    assert "outdoor_temperature_kind" in schema.schema
    assert "outdoor_humidity_kind" in schema.schema


def test_build_group_schema_co2():
    """Test building schema for co2."""
    schema, info = build_group_schema(
        "co2", {}, {}, [], [], selector.EntitySelector({})
    )
    assert isinstance(schema, vol.Schema)
    assert "co2_kind" in schema.schema


def test_build_group_schema_indoor_abs():
    """Test building schema for indoor_abs."""
    schema, info = build_group_schema(
        "indoor_abs", {}, {}, [], [], selector.EntitySelector({})
    )
    assert isinstance(schema, vol.Schema)
    assert "indoor_abs_humidity_temperature_kind" in schema.schema
    assert "indoor_abs_humidity_humidity_kind" in schema.schema


def test_build_group_schema_outdoor_abs():
    """Test building schema for outdoor_abs."""
    schema, info = build_group_schema(
        "outdoor_abs", {}, {}, [], [], selector.EntitySelector({})
    )
    assert isinstance(schema, vol.Schema)
    assert "outdoor_abs_humidity_temperature_kind" in schema.schema
    assert "outdoor_abs_humidity_humidity_kind" in schema.schema


def test_build_group_schema_invalid():
    """Test building schema for invalid group."""
    with pytest.raises(ValueError, match="Unsupported group_stage"):
        build_group_schema("invalid", {}, {}, [], [], selector.EntitySelector({}))
