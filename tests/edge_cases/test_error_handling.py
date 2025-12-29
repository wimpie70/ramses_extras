"""Edge cases and error handling tests for Ramses Extras."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from custom_components.ramses_extras.features.sensor_control.resolver import (
    SensorControlResolver,
)
from custom_components.ramses_extras.framework.helpers.config.core import (
    ExtrasConfigManager,
)
from custom_components.ramses_extras.framework.helpers.device.core import (
    ensure_ramses_cc_loaded,
    extract_device_id_as_string,
    find_ramses_device,
)
from custom_components.ramses_extras.framework.helpers.entity.core import (
    EntityHelpers,
)


class TestConfigManagerEdgeCases:
    """Test edge cases for ExtrasConfigManager."""

    def setup_method(self):
        """Set up test fixtures."""
        self.hass = MagicMock(spec=HomeAssistant)
        self.config_entry = MagicMock(spec=ConfigEntry)

    @pytest.mark.asyncio
    async def test_load_config_with_exception(self):
        """Test loading config when exceptions occur."""
        manager = ExtrasConfigManager(
            self.hass, self.config_entry, "test_feature", {"enabled": True}
        )

        # Mock config entry to raise exception
        self.config_entry.options = MagicMock(side_effect=Exception("Config error"))

        # Should handle exception gracefully
        await manager.async_load()

        # Should fall back to defaults
        assert manager._config == {"enabled": True}

    @pytest.mark.asyncio
    async def test_save_config_with_validation_failure(self):
        """Test saving config when validation fails."""
        manager = ExtrasConfigManager(
            self.hass, self.config_entry, "test_feature", {"enabled": True}
        )
        await manager.async_load()

        # Set invalid config
        manager._config["enabled"] = "not_boolean"

        result = await manager.async_save()
        assert result is False

    def test_get_with_invalid_key(self):
        """Test getting config value with various invalid keys."""
        manager = ExtrasConfigManager(
            self.hass, self.config_entry, "test_feature", {"enabled": True}
        )

        # Test None key
        assert manager.get(None) is None

        # Test empty string key
        assert manager.get("") is None

        # Test numeric key
        assert manager.get(123) is None

    def test_set_invalid_values(self):
        """Test setting invalid config values."""
        manager = ExtrasConfigManager(
            self.hass, self.config_entry, "test_feature", {"enabled": True}
        )

        # Should handle any value type
        manager.set("test_key", None)
        assert manager._config["test_key"] is None

        manager.set("complex_key", {"nested": [1, 2, 3]})
        assert manager._config["complex_key"] == {"nested": [1, 2, 3]}

    @pytest.mark.asyncio
    async def test_update_with_invalid_data(self):
        """Test updating config with invalid data types."""
        manager = ExtrasConfigManager(
            self.hass, self.config_entry, "test_feature", {"enabled": True}
        )

        await manager.async_load()

        # Update with None should not crash
        manager.update(None)
        assert manager._config == {"enabled": True}

        # Update with non-dict should not crash
        manager.update("not_a_dict")
        assert manager._config == {"enabled": True}

    def test_validation_with_extreme_values(self):
        """Test validation with extreme numeric values."""
        manager = ExtrasConfigManager(
            self.hass,
            self.config_entry,
            "test_feature",
            {"enabled": True, "min_value": 0, "max_value": 100},
        )
        manager._config = {
            "min_value": float("-inf"),
            "max_value": float("inf"),
        }

        # Should handle infinite values - -inf < +inf so validation should pass
        result = manager.validate_config()
        assert result is True

    def test_numeric_validation_edge_cases(self):
        """Test numeric validation with edge cases."""
        manager = ExtrasConfigManager(
            self.hass, self.config_entry, "test_feature", {"enabled": True}
        )

        # Test None value
        result = manager.get_numeric_validation("nonexistent", 0, 100)
        assert result is False

        # Test string value
        manager._config["test_value"] = "not_a_number"
        result = manager.get_numeric_validation("test_value", 0, 100)
        assert result is False

        # Test boundary values
        manager._config["boundary_min"] = 0
        result = manager.get_numeric_validation("boundary_min", 0, 100)
        assert result is True

        manager._config["boundary_max"] = 100
        result = manager.get_numeric_validation("boundary_max", 0, 100)
        assert result is True

    def test_boolean_validation_edge_cases(self):
        """Test boolean validation with edge cases."""
        manager = ExtrasConfigManager(
            self.hass, self.config_entry, "test_feature", {"enabled": True}
        )

        # Test None value
        result = manager.get_boolean_validation("nonexistent")
        assert result is False

        # Test various falsy/truthy values
        manager._config["test_bool"] = 0
        result = manager.get_boolean_validation("test_bool")
        assert result is False

        manager._config["test_bool"] = 1
        result = manager.get_boolean_validation("test_bool")
        assert result is False

        manager._config["test_bool"] = []
        result = manager.get_boolean_validation("test_bool")
        assert result is False

    def test_string_validation_edge_cases(self):
        """Test string validation with edge cases."""
        manager = ExtrasConfigManager(
            self.hass, self.config_entry, "test_feature", {"enabled": True}
        )

        # Test None value
        result = manager.get_string_validation("nonexistent")
        assert result is False

        # Test empty string
        manager._config["empty_string"] = ""
        result = manager.get_string_validation("empty_string", min_length=1)
        assert result is False

        # Test choices validation
        manager._config["choice_string"] = "invalid_choice"
        result = manager.get_string_validation(
            "choice_string", choices=["option1", "option2"]
        )
        assert result is False

        # Test length limits
        manager._config["long_string"] = "a" * 1000
        result = manager.get_string_validation("long_string", max_length=10)
        assert result is False


class TestEntityHelpersEdgeCases:
    """Test edge cases for EntityHelpers."""

    def test_detect_and_parse_invalid_entity_ids(self):
        """Test parsing various invalid entity ID formats."""
        # Empty string
        result = EntityHelpers.detect_and_parse("")
        assert result is None

        # No dot
        result = EntityHelpers.detect_and_parse("invalid_entity_id")
        assert result is None

        # Multiple dots
        result = EntityHelpers.detect_and_parse("sensor.temp.extra.invalid")
        assert result is None

        # Invalid entity type
        result = EntityHelpers.detect_and_parse("invalid_type.entity_name")
        assert result is None  # No device ID found

    def test_generate_entity_name_with_invalid_templates(self):
        """Test entity generation with invalid templates."""
        # Empty template
        with pytest.raises(ValueError, match="Template must be a non-empty string"):
            EntityHelpers.generate_entity_name_from_template("sensor", "")

        # None template
        with pytest.raises(ValueError, match="Template must be a non-empty string"):
            EntityHelpers.generate_entity_name_from_template("sensor", None)

        # Template without device_id placeholder when device_id provided
        with pytest.raises(ValueError, match="Missing required placeholders"):
            EntityHelpers.generate_entity_name_from_template(
                "sensor", "static_template", device_id="32_153289"
            )

    def test_generate_entity_name_with_invalid_device_ids(self):
        """Test entity generation with invalid device ID formats."""
        # Invalid device ID format
        with pytest.raises(ValueError, match="Invalid device_id format"):
            EntityHelpers.generate_entity_name_from_template(
                "sensor", "{device_id}_temp", device_id="invalid-format"
            )

        # Empty device ID
        with pytest.raises(ValueError, match="Invalid device_id format"):
            EntityHelpers.generate_entity_name_from_template(
                "sensor", "{device_id}_temp", device_id=""
            )

        # Device ID with invalid characters
        with pytest.raises(ValueError, match="Invalid device_id format"):
            EntityHelpers.generate_entity_name_from_template(
                "sensor", "{device_id}_temp", device_id="invalid@chars"
            )

    def test_parse_entity_id_with_malformed_ids(self):
        """Test parsing entity IDs with various edge cases."""
        # Entity ID without device ID - should return None
        result = EntityHelpers.parse_entity_id("sensor.no_device_id")
        assert result is None

        # Entity ID with device ID pattern in middle
        #  - parser finds "123" but confidence is low
        result = EntityHelpers.parse_entity_id("sensor.malformed_123_temp")
        # The parser finds "123" as a device ID pattern, but with low confidence
        # Since confidence < 0.7, is_valid=False, so result should be None
        assert result is None

        # Entity ID with valid device ID but unusual format - parser finds "32_153289"
        result = EntityHelpers.parse_entity_id("sensor.temp_32_153289_extra")
        # Parser finds valid device ID "32_153289" with reasonable confidence
        # This actually gets parsed successfully
        assert result is not None
        assert result[0] == "sensor"  # entity_type
        assert "32_153289" in result[2]  # device_id

    def test_filter_entities_with_invalid_patterns(self):
        """Test filtering entities with invalid pattern formats."""
        entities = ["sensor.temp_32_153289", "sensor.humidity_32_153289"]

        # Empty pattern list
        result = EntityHelpers.filter_entities_by_patterns(entities, [])
        assert result == []

        # None patterns
        result = EntityHelpers.filter_entities_by_patterns(entities, None)
        assert result == []

        # Invalid pattern format
        result = EntityHelpers.filter_entities_by_patterns(entities, ["*"])
        assert result == []  # Invalid wildcard pattern

    def test_get_entities_for_device_with_no_states(self):
        """Test getting entities for device when no states exist."""
        hass = MagicMock()
        hass.states = MagicMock()
        hass.states.async_all.return_value = []

        result = EntityHelpers.get_entities_for_device(hass, "32_153289")
        assert result == []

    def test_get_entities_for_device_with_invalid_states(self):
        """Test getting entities for device with invalid state objects."""
        hass = MagicMock()
        hass.states = MagicMock()

        # Mock states with missing entity_id
        state1 = MagicMock()
        del state1.entity_id  # Remove entity_id attribute
        state2 = MagicMock()
        state2.entity_id = None

        hass.states.async_all.return_value = [state1, state2]

        result = EntityHelpers.get_entities_for_device(hass, "32_153289")
        assert result == []

    @pytest.mark.asyncio
    async def test_generate_entity_patterns_for_invalid_feature(self):
        """Test generating entity patterns for invalid feature."""
        with patch(
            "custom_components.ramses_extras.framework.helpers.entity.core."
            "_get_required_entities_from_feature"
        ) as mock_get:
            mock_get.return_value = {}

            result = await EntityHelpers.generate_entity_patterns_for_feature(
                "invalid_feature"
            )
            assert result == []


class TestDeviceHelpersEdgeCases:
    """Test edge cases for device helpers."""

    def setup_method(self):
        """Set up test fixtures."""
        self.hass = MagicMock(spec=HomeAssistant)

    def test_extract_device_id_edge_cases(self):
        """Test device ID extraction with edge cases."""
        # Object without any known attributes
        obj = object()
        result = extract_device_id_as_string(obj)
        assert result.startswith("device_")

        # Object with conflicting attributes
        class ConflictingObject:
            def __init__(self):
                self.device_id = "device_attr"
                self.id = "id_attr"
                self._id = "_id_attr"
                self.name = "name_attr"

        obj = ConflictingObject()
        result = extract_device_id_as_string(obj)
        assert result == "device_attr"  # device_id takes precedence

    def test_find_ramses_device_edge_cases(self):
        """Test finding Ramses device with edge cases."""
        self.hass.data = {}

        # Test with None device_id
        result = find_ramses_device(self.hass, None)
        assert result is None

        # Test with empty device_id
        result = find_ramses_device(self.hass, "")
        assert result is None

        # Test with invalid device_id format
        result = find_ramses_device(self.hass, "invalid_format")
        assert result is None

    def test_ensure_ramses_cc_loaded_edge_cases(self):
        """Test ensuring ramses_cc loaded with edge cases."""
        # Test with corrupted hass.config
        self.hass.config = None
        with pytest.raises(AttributeError):
            ensure_ramses_cc_loaded(self.hass)

        # Reset hass
        self.hass = MagicMock()
        self.hass.config = MagicMock()
        self.hass.data = {}

        # Test with corrupted data
        self.hass.config.components = {"ramses_cc"}
        self.hass.data = None
        with pytest.raises(TypeError):
            ensure_ramses_cc_loaded(self.hass)


class TestSensorControlResolverEdgeCases:
    """Test edge cases for SensorControlResolver."""

    def setup_method(self):
        """Set up test fixtures."""
        self.hass = MagicMock(spec=HomeAssistant)
        self.resolver = SensorControlResolver(self.hass)

    @pytest.mark.asyncio
    async def test_resolve_with_invalid_device_id(self):
        """Test resolving with invalid device ID."""
        result = await self.resolver.resolve_entity_mappings(
            "invalid_device", "INVALID"
        )
        assert "mappings" in result
        assert "sources" in result
        # Should still return valid structure even with invalid inputs

    @pytest.mark.asyncio
    async def test_resolve_with_corrupted_config(self):
        """Test resolving with corrupted configuration."""
        # Mock corrupted config entry
        config_entry = MagicMock()
        config_entry.options = "not_a_dict"  # Invalid options
        self.hass.data = {"ramses_extras": {"config_entry": config_entry}}

        result = await self.resolver.resolve_entity_mappings("32:153:08", "FAN")
        assert "mappings" in result  # Should handle corrupted config gracefully

    def test_apply_override_edge_cases(self):
        """Test applying overrides with edge cases."""
        # Test with None internal_entity_id
        entity_id, source = self.resolver._apply_override(
            metric="indoor_temperature",
            internal_entity_id=None,
            override_kind="internal",
            override_entity_id=None,
        )
        assert entity_id is None
        assert source["kind"] == "internal"

        # Test with invalid override kinds for derived metrics
        entity_id, source = self.resolver._apply_override(
            metric="indoor_abs_humidity",
            internal_entity_id=None,
            override_kind="external_entity",
            override_entity_id="sensor.test",
        )
        assert entity_id is None
        assert source["valid"] is False

    def test_entity_exists_edge_cases(self):
        """Test entity existence checking with edge cases."""
        self.hass.states = MagicMock()

        # Test with None entity_id
        result = self.resolver._entity_exists(None)
        assert result is False

        # Test with empty entity_id
        result = self.resolver._entity_exists("")
        assert result is False

        # Test with exception during state access
        self.hass.states.get.side_effect = Exception("State access error")
        result = self.resolver._entity_exists("sensor.test")
        assert result is False
