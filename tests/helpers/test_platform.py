"""Tests for helpers/platform.py functions."""

import pytest
from unittest.mock import Mock

# Import the helpers - this will work when running in HA environment
try:
    from custom_components.ramses_extras.helpers.platform import (
        convert_fan_id_format,
        calculate_required_entities,
        get_entity_registry,
        find_orphaned_entities,
    )
except ImportError:
    # For standalone testing without HA
    pytest.skip("Home Assistant not available for testing", allow_module_level=True)


class TestFanIdConversion:
    """Test fan ID format conversion."""

    def test_convert_colon_to_underscore(self):
        """Test converting colon format to underscore format."""
        assert convert_fan_id_format("32:153289") == "32_153289"
        assert convert_fan_id_format("01:123456") == "01_123456"
        assert convert_fan_id_format("99:000001") == "99_000001"

    def test_already_underscore_format(self):
        """Test handling already underscore format."""
        assert convert_fan_id_format("32_153289") == "32_153289"

    def test_empty_string(self):
        """Test handling empty string."""
        assert convert_fan_id_format("") == ""


class TestRequiredEntitiesCalculation:
    """Test required entities calculation."""

    def test_no_features_enabled(self):
        """Test with no features enabled."""
        enabled_features = {
            'hvac_fan_card': False,
            'humidity_automation': False,
        }
        fans = ['32:153289']

        result = calculate_required_entities("sensor", enabled_features, fans)
        assert result == set()

    def test_with_features_enabled(self, mock_available_features, mock_device_mapping):
        """Test with features enabled."""
        enabled_features = {
            'hvac_fan_card': True,
            'humidity_automation': False,
        }
        fans = ['32:153289']

        # Mock the required constants
        import custom_components.ramses_extras.const as const_module
        const_module.AVAILABLE_FEATURES = mock_available_features
        const_module.DEVICE_ENTITY_MAPPING = mock_device_mapping

        result = calculate_required_entities("sensor", enabled_features, fans)
        assert len(result) > 0
        assert any("32:153289" in entity for entity in result)


class TestEntityRegistry:
    """Test entity registry functions."""

    def test_get_entity_registry_available(self):
        """Test getting entity registry when available."""
        mock_hass = Mock()
        mock_hass.data = {"entity_registry": Mock()}

        result = get_entity_registry(mock_hass)
        assert result is not None

    def test_get_entity_registry_unavailable(self, caplog):
        """Test getting entity registry when not available."""
        mock_hass = Mock()
        mock_hass.data = {}

        result = get_entity_registry(mock_hass)
        assert result is None
        assert "Entity registry not available" in caplog.text


class TestOrphanedEntities:
    """Test finding orphaned entities."""

    def test_find_orphaned_entities_no_registry(self):
        """Test finding orphaned entities when no registry."""
        mock_hass = Mock()
        mock_hass.data = {}

        result = find_orphaned_entities("sensor", mock_hass, [], set(), [])
        assert result == []

    def test_find_orphaned_entities_with_matches(self):
        """Test finding orphaned entities with matches."""
        # Mock entity registry with actual entity IDs
        mock_entity_registry = Mock()
        mock_entity_registry.entities = {
            'sensor.indoor_absolute_humidity_32_153289': Mock(),
            'sensor.outdoor_absolute_humidity_32_153289': Mock(),
            'sensor.different_device_99_123456': Mock(),
        }

        mock_hass = Mock()
        mock_hass.data = {"entity_registry": mock_entity_registry}

        fans = ['32:153289']
        required_entities = set()  # No entities required
        all_possible_types = ['indoor_abs_humid', 'outdoor_abs_humid']

        result = find_orphaned_entities("sensor", mock_hass, fans, required_entities, all_possible_types)

        # Should find the two entities for 32:153289
        assert len(result) == 2
        assert all('32_153289' in entity for entity in result)


# Fixtures for testing
@pytest.fixture
def mock_available_features():
    """Mock AVAILABLE_FEATURES constant."""
    return {
        'hvac_fan_card': {
            'supported_device_types': ['HvacVentilator'],
            'required_entities': {'sensors': ['indoor_abs_humid']},
            'optional_entities': {'sensors': ['outdoor_abs_humid']},
        }
    }


@pytest.fixture
def mock_device_mapping():
    """Mock DEVICE_ENTITY_MAPPING constant."""
    return {
        'HvacVentilator': {
            'sensors': ['indoor_abs_humid', 'outdoor_abs_humid'],
            'switches': ['dehumidify'],
            'booleans': ['dehumidifying'],
        }
    }
