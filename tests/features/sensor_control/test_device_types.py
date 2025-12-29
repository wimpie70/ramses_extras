"""Tests for sensor_control device type handlers."""

from unittest.mock import MagicMock

import pytest
import voluptuous as vol
from homeassistant.helpers import selector

from custom_components.ramses_extras.features.sensor_control.device_types import (
    DEVICE_TYPE_HANDLERS,
    co2,
    fan,
)


class TestFanHandler:
    """Test cases for FAN device type handler."""

    def test_get_group_options(self):
        """Test get_group_options returns expected options."""
        options = fan.get_group_options("32:123456")
        values = [opt["value"] for opt in options]
        assert "indoor_basic" in values
        assert "outdoor_basic" in values
        assert "co2" in values
        assert "indoor_abs" in values
        assert "outdoor_abs" in values
        assert "done" in values

    def test_source_from_input(self):
        """Test _source_from_input helper."""
        # Internal
        data = {"temp_kind": "internal"}
        result = fan._source_from_input(data, "temp_kind", "temp_ent", False)
        assert result == {"kind": "internal"}

        # External with entity
        data = {"temp_kind": "external", "temp_ent": "sensor.test"}
        result = fan._source_from_input(data, "temp_kind", "temp_ent", False)
        assert result == {"kind": "external", "entity_id": "sensor.test"}

        # External without entity (falls back to internal)
        data = {"temp_kind": "external", "temp_ent": None}
        result = fan._source_from_input(data, "temp_kind", "temp_ent", False)
        assert result == {"kind": "internal"}

        # None allowed
        data = {"temp_kind": "none"}
        result = fan._source_from_input(data, "temp_kind", "temp_ent", True)
        assert result == {"kind": "none"}

    def test_abs_temp_part_from_input(self):
        """Test _abs_temp_part_from_input helper."""
        # Internal
        data = {"kind": "internal"}
        assert fan._abs_temp_part_from_input(data, "kind", "ent") == {
            "kind": "internal"
        }

        # External temp
        data = {"kind": "external_temp", "ent": "sensor.t"}
        assert fan._abs_temp_part_from_input(data, "kind", "ent") == {
            "kind": "external_temp",
            "entity_id": "sensor.t",
        }

        # External abs
        data = {"kind": "external_abs", "ent": "sensor.a"}
        assert fan._abs_temp_part_from_input(data, "kind", "ent") == {
            "kind": "external_abs",
            "entity_id": "sensor.a",
        }

        # Old "external" mapping
        data = {"kind": "external", "ent": "sensor.t"}
        assert fan._abs_temp_part_from_input(data, "kind", "ent") == {
            "kind": "external_temp",
            "entity_id": "sensor.t",
        }

    def test_abs_humidity_part_from_input(self):
        """Test _abs_humidity_part_from_input helper."""
        # Internal
        data = {"kind": "internal"}
        assert fan._abs_humidity_part_from_input(data, "kind", "ent") == {
            "kind": "internal"
        }

        # External
        data = {"kind": "external", "ent": "sensor.h"}
        assert fan._abs_humidity_part_from_input(data, "kind", "ent") == {
            "kind": "external",
            "entity_id": "sensor.h",
        }

        # None
        data = {"kind": "none"}
        assert fan._abs_humidity_part_from_input(data, "kind", "ent") == {
            "kind": "none"
        }

    def test_get_helpers(self):
        """Test data retrieval helpers."""
        sources = {"indoor_temperature": {"kind": "external", "entity_id": "sensor.t"}}
        assert fan._get_kind(sources, "indoor_temperature") == "external"
        assert fan._get_entity(sources, "indoor_temperature") == "sensor.t"
        assert fan._get_kind(sources, "missing") == "internal"
        assert fan._get_entity(sources, "missing") is None

        abs_inputs = {"indoor_abs": {"temperature": {"kind": "internal"}}}
        assert fan._get_abs_kind(abs_inputs, "indoor_abs", "temperature") == "internal"
        assert fan._get_abs_entity(abs_inputs, "indoor_abs", "temperature") is None

    def test_handle_group_submission(self):
        """Test handle_group_submission for different stages."""
        sources = {}
        abs_in = {}

        # Indoor basic
        user_in = {
            "indoor_temperature_kind": "external",
            "indoor_temperature_entity": "sensor.t",
            "indoor_humidity_kind": "internal",
        }
        s, a = fan.handle_group_submission("indoor_basic", user_in, sources, abs_in)
        assert s["indoor_temperature"]["kind"] == "external"
        assert s["indoor_humidity"]["kind"] == "internal"

        # CO2
        user_in = {"co2_kind": "none"}
        s, a = fan.handle_group_submission("co2", user_in, sources, abs_in)
        assert s["co2"]["kind"] == "none"

        # Indoor ABS
        user_in = {
            "indoor_abs_humidity_temperature_kind": "external_abs",
            "indoor_abs_humidity_temperature_entity": "sensor.abs",
            "indoor_abs_humidity_humidity_kind": "internal",
        }
        s, a = fan.handle_group_submission("indoor_abs", user_in, sources, abs_in)
        # Should force humidity to none if external_abs is chosen
        assert a["indoor_abs_humidity"]["temperature"]["kind"] == "external_abs"
        assert a["indoor_abs_humidity"]["humidity"]["kind"] == "none"

    def test_build_group_schema(self):
        """Test build_group_schema for different stages."""
        sources = {}
        abs_in = {}
        kind_opts = []
        kind_opts_none = []
        sel = MagicMock()

        # Just verify it returns a schema and text for valid stages
        for stage in [
            "indoor_basic",
            "outdoor_basic",
            "co2",
            "indoor_abs",
            "outdoor_abs",
        ]:
            schema, text = fan.build_group_schema(
                stage, sources, abs_in, kind_opts, kind_opts_none, sel
            )
            assert isinstance(schema, vol.Schema)
            assert isinstance(text, str)

        with pytest.raises(ValueError):
            fan.build_group_schema(
                "invalid", sources, abs_in, kind_opts, kind_opts_none, sel
            )


class TestCo2Handler:
    """Test cases for CO2 device type handler."""

    def test_get_group_options(self):
        """Test get_group_options."""
        options = co2.get_group_options("co2_dev")
        values = [opt["value"] for opt in options]
        assert "co2" in values
        assert "done" in values

    def test_handle_group_submission(self):
        """Test handle_group_submission is no-op."""
        s = {"test": 1}
        a = {"test": 2}
        s2, a2 = co2.handle_group_submission("co2", {}, s, a)
        assert s2 == s
        assert a2 == a

    def test_build_group_schema(self):
        """Test build_group_schema."""
        schema, text = co2.build_group_schema("co2", {}, {}, [], [], MagicMock())
        assert isinstance(schema, vol.Schema)
        assert "preview" in text

        with pytest.raises(ValueError):
            co2.build_group_schema("invalid", {}, {}, [], [], MagicMock())


def test_device_type_handlers_registry():
    """Test registry mapping."""
    assert "FAN" in DEVICE_TYPE_HANDLERS
    assert "CO2" in DEVICE_TYPE_HANDLERS
    assert DEVICE_TYPE_HANDLERS["FAN"] == fan
    assert DEVICE_TYPE_HANDLERS["CO2"] == co2
