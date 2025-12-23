# tests/helpers/framework/test_entity_core.py
"""Test entity core helper functions."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.ramses_extras.framework.helpers.entity.core import (
    EntityHelpers,
    EntityNamingError,
    InvalidEntityFormatError,
    TemplateValidationError,
    _get_required_entities_from_feature,
    _import_required_entities_sync,
    _singularize_entity_type,
)


class TestExceptions:
    """Test exception classes."""

    def test_entity_naming_error(self):
        """Test EntityNamingError base exception."""
        error = EntityNamingError("Test error")
        assert str(error) == "Test error"
        assert isinstance(error, Exception)

    def test_invalid_entity_format_error(self):
        """Test InvalidEntityFormatError."""
        error = InvalidEntityFormatError("Invalid format")
        assert str(error) == "Invalid format"
        assert isinstance(error, EntityNamingError)

    def test_template_validation_error(self):
        """Test TemplateValidationError."""
        error = TemplateValidationError("Template validation failed")
        assert str(error) == "Template validation failed"
        assert isinstance(error, EntityNamingError)


class TestSingularizeEntityType:
    """Test _singularize_entity_type function."""

    def test_singularize_common_types(self):
        """Test singularization of common entity types."""
        assert _singularize_entity_type("sensor") == "sensor"
        assert _singularize_entity_type("switch") == "switch"
        assert _singularize_entity_type("binary_sensor") == "binary_sensor"
        assert _singularize_entity_type("number") == "number"

    def test_singularize_plural_types(self):
        """Test singularization of plural entity types."""
        assert _singularize_entity_type("devices") == "device"
        assert _singularize_entity_type("entities") == "entity"

    def test_singularize_unknown_type(self):
        """Test singularization of unknown entity types."""
        assert _singularize_entity_type("unknown") == "unknown"
        assert _singularize_entity_type("custom_type") == "custom_type"


class TestImportRequiredEntities:
    """Test required entities import functions."""

    @pytest.mark.asyncio
    async def test_get_required_entities_from_feature_success(self):
        """Test successful import of required entities."""
        with patch(
            "custom_components.ramses_extras.framework.helpers.entity.core._import_required_entities_sync"
        ) as mock_import:
            mock_import.return_value = {"sensor": ["temp", "humidity"]}

            result = await _get_required_entities_from_feature("humidity_control")

            assert result == {"sensor": ["temp", "humidity"]}
            mock_import.assert_called_once_with("humidity_control")

    @pytest.mark.asyncio
    async def test_get_required_entities_from_feature_exception(self):
        """Test handling of exceptions during import."""
        with patch(
            "custom_components.ramses_extras.framework.helpers.entity.core._import_required_entities_sync"
        ) as mock_import:
            mock_import.side_effect = Exception("Import failed")

            result = await _get_required_entities_from_feature("humidity_control")

            assert result == {}

    def test_import_required_entities_sync_success(self):
        """Test successful synchronous import."""
        mock_module = MagicMock()
        mock_const_data = {"required_entities": {"sensor": ["temp", "humidity"]}}
        mock_module.HUMIDITY_CONTROL_CONST = mock_const_data

        with patch("importlib.import_module", return_value=mock_module):
            result = _import_required_entities_sync("humidity_control")

            assert result == {"sensor": ["temp", "humidity"]}

    def test_import_required_entities_sync_no_const(self):
        """Test import when const data is not found."""
        mock_module = MagicMock()
        del mock_module.HUMIDITY_CONTROL_CONST  # Remove the const attribute

        with patch("importlib.import_module", return_value=mock_module):
            result = _import_required_entities_sync("humidity_control")

            assert result == {}

    def test_import_required_entities_sync_no_required_entities(self):
        """Test import when required_entities key is missing."""
        mock_module = MagicMock()
        mock_module.HUMIDITY_CONTROL_CONST = {}  # Empty const data

        with patch("importlib.import_module", return_value=mock_module):
            result = _import_required_entities_sync("humidity_control")

            assert result == {}


class TestEntityHelpers:
    """Test EntityHelpers class methods."""

    def test_clear_caches(self):
        """Test cache clearing functionality."""
        # Import the global caches
        from custom_components.ramses_extras.framework.helpers.entity.core import (
            _DEVICE_ID_CACHE,
            _FORMAT_CACHE,
        )

        # Add some items to caches
        _DEVICE_ID_CACHE["test"] = ("device", 0)
        _FORMAT_CACHE["test"] = "format"

        # Call as static method
        EntityHelpers._clear_caches()

        assert _DEVICE_ID_CACHE == {}
        assert _FORMAT_CACHE == {}

    def test_extract_device_id_success(self):
        """Test successful device ID extraction."""
        result = EntityHelpers._extract_device_id("sensor.temp_32_153289")
        assert result == ("32_153289", 12)  # Position after "sensor.temp_"

    def test_extract_device_id_colon_format(self):
        """Test device ID extraction with colon format."""
        result = EntityHelpers._extract_device_id("sensor.temp_32:153289")
        assert result == ("32_153289", 12)  # Position after "sensor.temp_"

    def test_extract_device_id_no_match(self):
        """Test device ID extraction when no pattern matches."""
        result = EntityHelpers._extract_device_id("sensor.temperature")
        assert result == (None, -1)

    def test_extract_device_id_cached(self):
        """Test cached device ID extraction."""
        # Import the global caches
        from custom_components.ramses_extras.framework.helpers.entity.core import (
            _DEVICE_ID_CACHE,
        )

        # Clear cache first
        EntityHelpers._clear_caches()

        # First call should cache result
        result1 = EntityHelpers._extract_device_id_cached("sensor.temp_32_153289")
        assert result1 == ("32_153289", 12)

        # Second call should use cache
        result2 = EntityHelpers._extract_device_id_cached("sensor.temp_32_153289")
        assert result2 == ("32_153289", 12)

        # Verify cache contains the entry
        assert "sensor.temp_32_153289" in _DEVICE_ID_CACHE

    def test_calculate_format_confidence_cc_high(self):
        """Test confidence calculation for CC format at beginning."""
        confidence = EntityHelpers._calculate_format_confidence(
            0, "32_153289_temp", "cc"
        )
        assert confidence == 0.95

    def test_calculate_format_confidence_extras_high(self):
        """Test confidence calculation for extras format at end."""
        confidence = EntityHelpers._calculate_format_confidence(
            10, "temp_32_153289", "extras"
        )
        assert confidence == 0.95

    def test_calculate_format_confidence_cc_medium(self):
        """Test confidence calculation for CC format in first 30%."""
        confidence = EntityHelpers._calculate_format_confidence(
            5, "sensor_32_153289_temp", "cc"
        )
        assert confidence == 0.85

    def test_calculate_format_confidence_extras_medium(self):
        """Test confidence calculation for extras format in last 70%."""
        # For extras format, confidence is high when position >= 0.3 * length
        entity_name = "temp_32_153289"  # length = 14, position = 5 (0.36 * 14)
        confidence = EntityHelpers._calculate_format_confidence(
            5, entity_name, "extras"
        )
        assert confidence == 0.85

    def test_calculate_format_confidence_no_match(self):
        """Test confidence calculation when position is -1."""
        confidence = EntityHelpers._calculate_format_confidence(-1, "sensor.temp", "cc")
        assert confidence == 0.0

    def test_detect_format_by_position_cc(self):
        """Test format detection for CC format (device_id at beginning)."""
        format_type = EntityHelpers._detect_format_by_position(
            2, "32_153289_temp_sensor"
        )
        assert format_type == "cc"

    def test_detect_format_by_position_extras(self):
        """Test format detection for extras format (device_id at end)."""
        format_type = EntityHelpers._detect_format_by_position(
            15, "temp_sensor_32_153289"
        )
        assert format_type == "extras"

    def test_get_format_hint_from_template_cc(self):
        """Test format hint for CC format template."""
        hint = EntityHelpers._get_format_hint_from_template("{device_id}_temp")
        assert hint == "cc"

    def test_get_format_hint_from_template_extras(self):
        """Test format hint for extras format template."""
        hint = EntityHelpers._get_format_hint_from_template("temp_{device_id}")
        assert hint == "extras"

    def test_get_format_hint_from_template_unknown(self):
        """Test format hint for unknown template format."""
        hint = EntityHelpers._get_format_hint_from_template("sensor_{device_id}_extra")
        assert hint == "unknown"

    def test_detect_and_parse_cc_format(self):
        """Test entity detection and parsing for CC format."""
        result = EntityHelpers.detect_and_parse("sensor.32_153289_temp")

        # Check basic structure - device ID is at position 0 in the
        # entity_name part
        assert result is not None
        assert result["entity_type"] == "sensor"
        assert result["device_id"] == "32_153289"
        assert result["format"] == "cc"
        assert result["position"] == 0  # device_id starts at position 0
        assert "parsed_name" in result
        assert "confidence" in result
        assert "is_valid" in result

    def test_detect_and_parse_extras_format(self):
        """Test entity detection and parsing for extras format."""
        result = EntityHelpers.detect_and_parse("sensor.temp_32_153289")

        # Check basic structure - device ID starts after "temp_"
        assert result is not None
        assert result["entity_type"] == "sensor"
        assert result["device_id"] == "32_153289"
        assert result["format"] == "extras"
        assert result["position"] == 5  # device_id starts at position 5 (after "temp_")
        assert "parsed_name" in result
        assert "confidence" in result
        assert "is_valid" in result

    def test_detect_and_parse_invalid_entity_id(self):
        """Test detection and parsing with invalid entity ID."""
        # Missing dot separator
        result = EntityHelpers.detect_and_parse("sensor_temp_32_153289")
        assert result is None

        # Empty entity ID
        result = EntityHelpers.detect_and_parse("")
        assert result is None

        # No device ID found
        result = EntityHelpers.detect_and_parse("sensor.temperature")
        assert result is None
