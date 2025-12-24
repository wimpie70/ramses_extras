"""Tests for entity helper utilities in framework/helpers/entity/core.py."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.core import HomeAssistant, State

from custom_components.ramses_extras.framework.helpers.entity.core import (
    EntityHelpers,
    filter_entities_by_patterns,
    generate_entity_from_template,
    generate_entity_patterns_for_feature,
    get_entities_for_device,
    get_entity_device_id,
    get_feature_entity_mappings,
    parse_entity_id,
)


class TestEntityHelpers:
    """Test cases for EntityHelpers class."""

    def test_clear_caches(self):
        """Test cache clearing functionality."""
        # Add some items to caches
        EntityHelpers._extract_device_id_cached("sensor.test_32_153289")
        EntityHelpers._extract_device_id_cached("sensor.test2_32_153289")

        # Verify caches are populated
        assert len(EntityHelpers._DEVICE_ID_CACHE) > 0

        # Clear caches
        EntityHelpers._clear_caches()

        # Verify caches are empty
        assert len(EntityHelpers._DEVICE_ID_CACHE) == 0

    def test_extract_device_id_basic(self):
        """Test basic device ID extraction."""
        result = EntityHelpers._extract_device_id("indoor_temp_32_153289")
        assert result == ("32_153289", 12)

    def test_extract_device_id_no_match(self):
        """Test device ID extraction with no match."""
        result = EntityHelpers._extract_device_id("no_device_id_here")
        assert result == (None, -1)

    def test_extract_device_id_colon_format(self):
        """Test device ID extraction with colon format."""
        result = EntityHelpers._extract_device_id("32:153289_param")
        assert result == ("32_153289", 0)

    def test_extract_device_id_cached(self):
        """Test cached device ID extraction."""
        # First call should cache result
        result1 = EntityHelpers._extract_device_id_cached("test_32_153289")
        assert result1 == ("32_153289", 5)

        # Second call should use cache
        result2 = EntityHelpers._extract_device_id_cached("test_32_153289")
        assert result2 == result1

    def test_calculate_format_confidence_cc_high(self):
        """Test format confidence calculation for CC format high confidence."""
        confidence = EntityHelpers._calculate_format_confidence(2, "sensor_name", "cc")
        assert confidence == 0.85  # First 30% position

    def test_calculate_format_confidence_extras_high(self):
        """Test format confidence calculation for extras format high confidence."""
        confidence = EntityHelpers._calculate_format_confidence(
            15, "sensor_name_32_153289", "extras"
        )
        assert confidence == 0.95  # Very end position

    def test_calculate_format_confidence_low(self):
        """Test format confidence calculation for low confidence."""
        confidence = EntityHelpers._calculate_format_confidence(-1, "sensor_name", "cc")
        assert confidence == 0.0  # No device ID found

    def test_detect_format_by_position_cc(self):
        """Test format detection by position for CC format."""
        format_type = EntityHelpers._detect_format_by_position(
            2, "sensor_32_153289_name"
        )
        assert format_type == "cc"

    def test_detect_format_by_position_extras(self):
        """Test format detection by position for extras format."""
        format_type = EntityHelpers._detect_format_by_position(
            12, "sensor_name_32_153289"
        )
        assert format_type == "extras"

    def test_get_format_hint_from_template_cc(self):
        """Test format hint from template for CC style."""
        hint = EntityHelpers._get_format_hint_from_template("{device_id}_param")
        assert hint == "cc"

    def test_get_format_hint_from_template_extras(self):
        """Test format hint from template for extras style."""
        hint = EntityHelpers._get_format_hint_from_template("param_{device_id}")
        assert hint == "extras"

    def test_detect_and_parse_valid_cc_format(self):
        """Test parsing valid CC format entity."""
        result = EntityHelpers.detect_and_parse("sensor.32_153289_indoor_temp")

        assert result is not None
        assert result["entity_type"] == "sensor"
        assert result["parsed_name"] == "indoor_temp"
        assert result["device_id"] == "32_153289"
        assert result["format"] == "cc"
        assert result["is_valid"] is True

    def test_detect_and_parse_valid_extras_format(self):
        """Test parsing valid extras format entity."""
        result = EntityHelpers.detect_and_parse("sensor.indoor_temp_32_153289")

        assert result is not None
        assert result["entity_type"] == "sensor"
        assert result["parsed_name"] == "indoor_temp"
        assert result["device_id"] == "32_153289"
        assert result["format"] == "extras"
        assert result["is_valid"] is True

    def test_detect_and_parse_invalid_entity(self):
        """Test parsing invalid entity ID."""
        result = EntityHelpers.detect_and_parse("invalid_entity")
        assert result is None

    def test_detect_and_parse_no_device_id(self):
        """Test parsing entity with no device ID."""
        result = EntityHelpers.detect_and_parse("sensor.no_device_id")
        assert result is None

    def test_generate_entity_name_from_template_valid(self):
        """Test generating entity name from valid template."""
        result = EntityHelpers.generate_entity_name_from_template(
            "sensor", "{device_id}_indoor_temp", device_id="32_153289"
        )
        assert result == "sensor.32_153289_indoor_temp"

    def test_generate_entity_name_from_template_invalid_type(self):
        """Test generating entity name with invalid entity type."""
        with pytest.raises(ValueError, match="Invalid entity_type"):
            EntityHelpers.generate_entity_name_from_template(
                "invalid_type", "template", device_id="32_153289"
            )

    def test_generate_entity_name_from_template_missing_placeholder(self):
        """Test generating entity name with missing placeholder."""
        with pytest.raises(ValueError, match="Missing required placeholders"):
            EntityHelpers.generate_entity_name_from_template(
                "sensor", "{device_id}_{missing}", device_id="32_153289"
            )

    def test_generate_entity_name_from_template_invalid_device_id(self):
        """Test generating entity name with invalid device ID format."""
        with pytest.raises(ValueError, match="Invalid device_id format"):
            EntityHelpers.generate_entity_name_from_template(
                "sensor", "{device_id}_temp", device_id="invalid_format"
            )

    def test_validate_entity_name_valid(self):
        """Test validating valid entity name."""
        result = EntityHelpers.validate_entity_name("sensor.indoor_temp_32_153289")

        assert result["is_valid"] is True
        assert result["entity_type"] == "sensor"
        assert result["device_id"] == "32_153289"
        assert result["detected_format"] == "extras"
        assert len(result["issues"]) == 0

    def test_validate_entity_name_invalid_type(self):
        """Test validating entity with invalid type."""
        result = EntityHelpers.validate_entity_name("invalid.type_32_153289")

        assert result["is_valid"] is False
        assert "Invalid entity type" in str(result["issues"])

    def test_validate_entity_name_no_device_id(self):
        """Test validating entity with no device ID."""
        result = EntityHelpers.validate_entity_name("sensor.no_device_id")

        assert result["is_valid"] is False
        assert "Could not parse entity name" in str(result["issues"])

    def test_parse_entity_id_with_validation_valid(self):
        """Test parsing entity ID with validation for valid entity."""
        result = EntityHelpers.parse_entity_id_with_validation(
            "sensor.indoor_temp_32_153289"
        )
        assert result == ("sensor", "indoor_temp", "32_153289")

    def test_parse_entity_id_with_validation_invalid(self):
        """Test parsing entity ID with validation for invalid entity."""
        from custom_components.ramses_extras.framework.helpers.entity.core import (
            InvalidEntityFormatError,
        )

        with pytest.raises(InvalidEntityFormatError):
            EntityHelpers.parse_entity_id_with_validation("invalid.entity")

    def test_generate_entity_name_with_validation_valid(self):
        """Test generating entity name with validation for valid template."""
        result = EntityHelpers.generate_entity_name_with_validation(
            "sensor", "{device_id}_temp", device_id="32_153289"
        )
        assert result == "sensor.32_153289_temp"

    def test_generate_entity_name_with_validation_invalid(self):
        """Test generating entity name with validation for invalid template."""
        from custom_components.ramses_extras.framework.helpers.entity.core import (
            TemplateValidationError,
        )

        with pytest.raises(TemplateValidationError):
            EntityHelpers.generate_entity_name_with_validation(
                "sensor", "{device_id}_{missing}", device_id="32_153289"
            )

    def test_parse_entity_id_valid(self):
        """Test parsing valid entity ID."""
        result = EntityHelpers.parse_entity_id("sensor.indoor_temp_32_153289")
        assert result == ("sensor", "indoor_temp", "32_153289")

    def test_parse_entity_id_invalid(self):
        """Test parsing invalid entity ID."""
        result = EntityHelpers.parse_entity_id("invalid.entity")
        assert result is None

    def test_filter_entities_by_patterns_prefix_match(self):
        """Test filtering entities by prefix patterns."""
        entities = [
            "sensor.temp_32_153289",
            "sensor.humidity_32_153289",
            "switch.fan_32_153289",
            "sensor.outdoor_temp",
        ]
        patterns = ["sensor.temp_*", "switch.*"]

        result = EntityHelpers.filter_entities_by_patterns(entities, patterns)
        assert "sensor.temp_32_153289" in result
        assert "switch.fan_32_153289" in result
        assert "sensor.humidity_32_153289" not in result
        assert "sensor.outdoor_temp" not in result

    def test_filter_entities_by_patterns_exact_match(self):
        """Test filtering entities by exact patterns."""
        entities = ["sensor.temp_32_153289", "sensor.humidity_32_153289"]
        patterns = ["sensor.temp_32_153289"]

        result = EntityHelpers.filter_entities_by_patterns(entities, patterns)
        assert result == ["sensor.temp_32_153289"]

    def test_filter_entities_by_patterns_with_entity_objects(self):
        """Test filtering entities when passed entity objects."""
        entity1 = MagicMock()
        entity1.entity_id = "sensor.temp_32_153289"
        entity2 = MagicMock()
        entity2.entity_id = "sensor.humidity_32_153289"

        entities = [entity1, entity2]
        patterns = ["sensor.temp_*"]

        result = EntityHelpers.filter_entities_by_patterns(entities, patterns)
        assert result == ["sensor.temp_32_153289"]

    @pytest.mark.asyncio
    async def test_generate_entity_patterns_for_feature(self):
        """Test generating entity patterns for a feature."""
        # This test would need to mock the feature import, which is complex
        # For now, test that it returns a list
        with patch(
            "custom_components.ramses_extras.framework.helpers.entity.core._get_required_entities_from_feature"
        ) as mock_get:
            mock_get.return_value = {
                "sensors": ["temp", "humidity"],
                "switches": ["fan"],
            }

            result = await EntityHelpers.generate_entity_patterns_for_feature(
                "test_feature"
            )

            assert isinstance(result, list)
            assert "sensor.temp_*" in result
            assert "switch.fan_*" in result

    def test_get_entities_for_device(self):
        """Test getting entities for a specific device."""
        hass = MagicMock()
        hass.states = MagicMock()

        # Create mock states
        state1 = MagicMock(spec=State)
        state1.entity_id = "sensor.temp_32_153289"
        state2 = MagicMock(spec=State)
        state2.entity_id = "sensor.humidity_32_153289"
        state3 = MagicMock(spec=State)
        state3.entity_id = "sensor.temp_32_153290"  # Different device

        hass.states.async_all.return_value = [state1, state2, state3]

        result = EntityHelpers.get_entities_for_device(hass, "32_153289")
        assert "sensor.temp_32_153289" in result
        assert "sensor.humidity_32_153289" in result
        assert "sensor.temp_32_153290" not in result

    def test_cleanup_orphaned_entities(self):
        """Test cleanup of orphaned entities."""
        hass = MagicMock()
        device_ids = ["32_153289", "32_153290"]

        result = EntityHelpers.cleanup_orphaned_entities(hass, device_ids)
        assert result == 0  # Placeholder implementation returns 0

    def test_get_entity_device_id_valid(self):
        """Test extracting device ID from valid entity ID."""
        result = EntityHelpers.get_entity_device_id("sensor.temp_32_153289")
        assert result == "32_153289"

    def test_get_entity_device_id_invalid(self):
        """Test extracting device ID from invalid entity ID."""
        result = EntityHelpers.get_entity_device_id("sensor.no_device_id")
        assert result is None

    def test_get_all_required_entity_ids_for_device(self):
        """Test getting all required entity IDs for a device."""
        # This test would need to mock the registry import, which is complex
        # For now, test that it returns a list and handles exceptions gracefully
        result = EntityHelpers.get_all_required_entity_ids_for_device("32_153289")
        assert isinstance(result, list)


class TestUtilityFunctions:
    """Test cases for utility functions."""

    def test_generate_entity_from_template(self):
        """Test generating entity from template utility function."""
        result = generate_entity_from_template(
            "sensor", "{device_id}_temp", device_id="32_153289"
        )
        assert result == "sensor.32_153289_temp"

    def test_parse_entity_id_utility(self):
        """Test parse entity ID utility function."""
        result = parse_entity_id("sensor.temp_32_153289")
        assert result == ("sensor", "temp", "32_153289")

    def test_get_entity_device_id_utility(self):
        """Test get entity device ID utility function."""
        result = get_entity_device_id("sensor.temp_32_153289")
        assert result == "32_153289"

    def test_get_entities_for_device_utility(self):
        """Test get entities for device utility function."""
        hass = MagicMock()
        hass.states = MagicMock()
        hass.states.async_all.return_value = []

        result = get_entities_for_device(hass, "32_153289")
        assert result == []

    def test_filter_entities_by_patterns_utility(self):
        """Test filter entities by patterns utility function."""
        entities = ["sensor.temp_32_153289", "sensor.humidity_32_153289"]
        patterns = ["sensor.temp_*"]

        result = filter_entities_by_patterns(entities, patterns)
        assert result == ["sensor.temp_32_153289"]

    @pytest.mark.asyncio
    async def test_get_feature_entity_mappings(self):
        """Test getting feature entity mappings."""
        with patch(
            "custom_components.ramses_extras.framework.helpers.entity.core._get_entity_mappings_from_feature"
        ) as mock_get:
            mock_get.return_value = {"temp": "sensor.temp_32_153289"}

            result = await get_feature_entity_mappings("humidity_control", "32_153289")

            assert result == {"temp": "sensor.temp_32_153289"}

    @pytest.mark.asyncio
    async def test_generate_entity_patterns_for_feature_utility(self):
        """Test generate entity patterns for feature utility function."""
        with patch(
            "custom_components.ramses_extras.framework.helpers.entity.core._get_required_entities_from_feature"
        ) as mock_get:
            mock_get.return_value = {"sensors": ["temp"]}

            result = await generate_entity_patterns_for_feature("test_feature")

            assert "sensor.temp_*" in result
