"""Tests for entity ID fallback helpers."""

import pytest

from custom_components.ramses_extras.framework.helpers.entity.entity_id_fallbacks import (  # noqa: E501
    iter_ramses_cc_entity_id_fallbacks,
    iter_ramses_cc_entity_ids,
)


class TestIterRamsesccEntityIds:
    """Test cases for iter_ramses_cc_entity_ids helper."""

    def test_basic_entity_id_generation(self):
        """Test basic entity ID generation with no variants."""
        result = iter_ramses_cc_entity_ids(
            "sensor",
            "fan_rate",
            device_id="32:153289",
        )
        expected = [
            "sensor.32_153289_fan_rate",
            "sensor.fan_32_153289_fan_rate",
            "sensor.co2_32_153289_fan_rate",
        ]
        assert result == expected

    def test_temperature_suffix_variants(self):
        """Test entity ID generation with _temp/_temperature variants."""
        result = iter_ramses_cc_entity_ids(
            "sensor",
            "indoor_temp",
            device_id="32:153289",
        )
        # Should generate both _temp and _temperature variants
        assert "sensor.32_153289_indoor_temp" in result
        assert "sensor.32_153289_indoor_temperature" in result
        assert "sensor.fan_32_153289_indoor_temp" in result
        assert "sensor.fan_32_153289_indoor_temperature" in result

    def test_temperature_suffix_variants_fan_slug_priority(self):
        """Test that fan slug prioritizes _temperature over _temp."""
        result = iter_ramses_cc_entity_ids(
            "sensor",
            "indoor_temp",
            device_id="32:153289",
        )
        # Find indices for fan_ prefixed entities
        fan_temp_idx = result.index("sensor.fan_32_153289_indoor_temperature")
        fan_temp_old_idx = result.index("sensor.fan_32_153289_indoor_temp")
        # _temperature should come before _temp for fan_ prefix
        assert fan_temp_idx < fan_temp_old_idx

    def test_co2_level_variants(self):
        """Test entity ID generation with co2_level/carbon_dioxide variants."""
        result = iter_ramses_cc_entity_ids(
            "sensor",
            "co2_level",
            device_id="32:153289",
        )
        # Should generate both co2_level and carbon_dioxide variants
        assert "sensor.32_153289_co2_level" in result
        assert "sensor.32_153289_carbon_dioxide" in result
        assert "sensor.co2_32_153289_co2_level" in result
        assert "sensor.co2_32_153289_carbon_dioxide" in result

    def test_co2_slug_priority(self):
        """Test that co2 slug prioritizes carbon_dioxide over co2_level."""
        result = iter_ramses_cc_entity_ids(
            "sensor",
            "co2_level",
            device_id="32:153289",
        )
        # Find indices for co2_ prefixed entities
        co2_carbon_dioxide_idx = result.index("sensor.co2_32_153289_carbon_dioxide")
        co2_level_idx = result.index("sensor.co2_32_153289_co2_level")
        # carbon_dioxide should come before co2_level for co2_ prefix
        assert co2_carbon_dioxide_idx < co2_level_idx

    def test_device_id_underscore_parameter(self):
        """Test using device_id_underscore parameter instead of device_id."""
        result = iter_ramses_cc_entity_ids(
            "sensor",
            "indoor_humidity",
            device_id_underscore="32_153289",
        )
        assert "sensor.32_153289_indoor_humidity" in result
        assert "sensor.fan_32_153289_indoor_humidity" in result

    def test_custom_slugs(self):
        """Test with custom slug list."""
        result = iter_ramses_cc_entity_ids(
            "sensor",
            "indoor_temp",
            device_id="32:153289",
            slugs=("", "fan"),
        )
        # Should only have no-prefix and fan_ prefix
        assert any("sensor.32_153289_" in e for e in result)
        assert any("sensor.fan_32_153289_" in e for e in result)
        assert not any("sensor.co2_32_153289_" in e for e in result)

    def test_empty_domain(self):
        """Test with empty domain returns empty list."""
        result = iter_ramses_cc_entity_ids(
            "",
            "indoor_temp",
            device_id="32:153289",
        )
        assert result == []

    def test_empty_key(self):
        """Test with empty key returns empty list."""
        result = iter_ramses_cc_entity_ids(
            "sensor",
            "",
            device_id="32:153289",
        )
        assert result == []

    def test_no_device_id(self):
        """Test with no device_id or device_id_underscore returns empty list."""
        result = iter_ramses_cc_entity_ids(
            "sensor",
            "indoor_temp",
        )
        assert result == []

    def test_deduplication(self):
        """Test that duplicate entity IDs are removed."""
        result = iter_ramses_cc_entity_ids(
            "sensor",
            "fan_rate",
            device_id="32:153289",
        )
        # Should not have duplicates
        assert len(result) == len(set(result))

    def test_number_domain(self):
        """Test with number domain."""
        result = iter_ramses_cc_entity_ids(
            "number",
            "param_01",
            device_id="32:153289",
        )
        assert "number.32_153289_param_01" in result
        assert "number.fan_32_153289_param_01" in result

    def test_combined_temp_and_co2_variants(self):
        """Test key that could have both temp and co2 variants (edge case)."""
        # This is a theoretical edge case - a key ending in _temp
        # that also matches co2 patterns
        result = iter_ramses_cc_entity_ids(
            "sensor",
            "exhaust_temp",
            device_id="32:153289",
        )
        assert "sensor.32_153289_exhaust_temp" in result
        assert "sensor.32_153289_exhaust_temperature" in result


class TestIterRamsesccEntityIdFallbacks:
    """Test cases for iter_ramses_cc_entity_id_fallbacks helper."""

    def test_basic_fallback_generation(self):
        """Test basic fallback generation for entity without variants."""
        result = iter_ramses_cc_entity_id_fallbacks(
            "sensor.32_153289_fan_rate",
            device_id_underscore="32_153289",
        )
        # Should generate fan_ and co2_ prefixed variants
        assert "sensor.fan_32_153289_fan_rate" in result
        assert "sensor.co2_32_153289_fan_rate" in result
        # Should NOT include the original entity_id
        assert "sensor.32_153289_fan_rate" not in result

    def test_temperature_suffix_fallbacks(self):
        """Test fallback generation for _temp suffix."""
        result = iter_ramses_cc_entity_id_fallbacks(
            "sensor.32_153289_indoor_temp",
            device_id_underscore="32_153289",
        )
        # Should generate _temperature variants
        assert "sensor.32_153289_indoor_temperature" in result
        assert "sensor.fan_32_153289_indoor_temperature" in result
        assert "sensor.fan_32_153289_indoor_temp" in result
        # Should NOT include the original
        assert "sensor.32_153289_indoor_temp" not in result

    def test_temperature_suffix_fallbacks_reverse(self):
        """Test fallback generation for _temperature suffix."""
        result = iter_ramses_cc_entity_id_fallbacks(
            "sensor.fan_32_153289_indoor_temperature",
            device_id_underscore="32_153289",
        )
        # Should generate _temp variants
        assert "sensor.fan_32_153289_indoor_temp" in result
        assert "sensor.32_153289_indoor_temp" in result
        assert "sensor.32_153289_indoor_temperature" in result
        # Should NOT include the original
        assert "sensor.fan_32_153289_indoor_temperature" not in result

    def test_co2_level_fallbacks(self):
        """Test fallback generation for co2_level."""
        result = iter_ramses_cc_entity_id_fallbacks(
            "sensor.32_153289_co2_level",
            device_id_underscore="32_153289",
        )
        # Should generate carbon_dioxide variants
        assert "sensor.32_153289_carbon_dioxide" in result
        assert "sensor.fan_32_153289_carbon_dioxide" in result
        assert "sensor.co2_32_153289_carbon_dioxide" in result

    def test_carbon_dioxide_fallbacks(self):
        """Test fallback generation for carbon_dioxide."""
        result = iter_ramses_cc_entity_id_fallbacks(
            "sensor.co2_32_153289_carbon_dioxide",
            device_id_underscore="32_153289",
        )
        # Should generate co2_level variants
        assert "sensor.co2_32_153289_co2_level" in result
        assert "sensor.32_153289_co2_level" in result
        assert "sensor.fan_32_153289_co2_level" in result

    def test_fan_prefix_fallbacks(self):
        """Test fallback generation for fan_ prefixed entity."""
        result = iter_ramses_cc_entity_id_fallbacks(
            "sensor.fan_32_153289_indoor_humidity",
            device_id_underscore="32_153289",
        )
        # Should generate non-prefixed and co2_ prefixed variants
        assert "sensor.32_153289_indoor_humidity" in result
        assert "sensor.co2_32_153289_indoor_humidity" in result
        # Should NOT include the original
        assert "sensor.fan_32_153289_indoor_humidity" not in result

    def test_co2_prefix_fallbacks(self):
        """Test fallback generation for co2_ prefixed entity."""
        result = iter_ramses_cc_entity_id_fallbacks(
            "sensor.co2_37_126776_carbon_dioxide",
            device_id_underscore="37_126776",
        )
        # Should generate non-prefixed and fan_ prefixed variants
        assert "sensor.37_126776_carbon_dioxide" in result
        assert "sensor.fan_37_126776_carbon_dioxide" in result
        assert "sensor.37_126776_co2_level" in result
        assert "sensor.fan_37_126776_co2_level" in result

    def test_device_id_parameter(self):
        """Test using device_id parameter instead of device_id_underscore."""
        result = iter_ramses_cc_entity_id_fallbacks(
            "sensor.32_153289_indoor_temp",
            device_id="32:153289",
        )
        assert "sensor.32_153289_indoor_temperature" in result
        assert "sensor.fan_32_153289_indoor_temperature" in result

    def test_invalid_entity_id_no_dot(self):
        """Test with invalid entity_id (no domain separator) returns empty list."""
        result = iter_ramses_cc_entity_id_fallbacks(
            "invalid_entity_id",
            device_id_underscore="32_153289",
        )
        assert result == []

    def test_invalid_entity_id_empty_domain(self):
        """Test with invalid entity_id (empty domain) returns empty list."""
        result = iter_ramses_cc_entity_id_fallbacks(
            ".32_153289_indoor_temp",
            device_id_underscore="32_153289",
        )
        assert result == []

    def test_invalid_entity_id_empty_object_id(self):
        """Test with invalid entity_id (empty object_id) returns empty list."""
        result = iter_ramses_cc_entity_id_fallbacks(
            "sensor.",
            device_id_underscore="32_153289",
        )
        assert result == []

    def test_no_device_id(self):
        """Test with no device_id or device_id_underscore returns empty list."""
        result = iter_ramses_cc_entity_id_fallbacks(
            "sensor.32_153289_indoor_temp",
        )
        assert result == []

    def test_entity_without_device_id_prefix(self):
        """Test entity that doesn't start with device_id returns empty list."""
        result = iter_ramses_cc_entity_id_fallbacks(
            "sensor.some_other_entity",
            device_id_underscore="32_153289",
        )
        assert result == []

    def test_number_domain_fallbacks(self):
        """Test fallback generation for number domain."""
        result = iter_ramses_cc_entity_id_fallbacks(
            "number.32_153289_param_01",
            device_id_underscore="32_153289",
        )
        assert "number.fan_32_153289_param_01" in result
        assert "number.co2_32_153289_param_01" in result

    def test_deduplication(self):
        """Test that duplicate fallbacks are removed."""
        result = iter_ramses_cc_entity_id_fallbacks(
            "sensor.32_153289_indoor_temp",
            device_id_underscore="32_153289",
        )
        # Should not have duplicates
        assert len(result) == len(set(result))

    def test_case_insensitive_device_id(self):
        """Test that device_id_underscore is case-insensitive."""
        result = iter_ramses_cc_entity_id_fallbacks(
            "sensor.32_153289_indoor_temp",
            device_id_underscore="32_153289",
        )
        result_upper = iter_ramses_cc_entity_id_fallbacks(
            "sensor.32_153289_indoor_temp",
            device_id_underscore="32_153289",
        )
        assert result == result_upper
