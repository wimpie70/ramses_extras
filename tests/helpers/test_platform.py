"""Tests for helpers/platform.py functions."""

import sys
from unittest import mock
from unittest.mock import AsyncMock, Mock

import pytest

# Add the custom_components to the path for testing
sys.path.insert(0, "custom_components")

# Import the helpers - this will work when running in development
try:
    from ramses_extras.helpers.platform import (
        calculate_required_entities,
        convert_device_id_format,
        find_orphaned_entities,
        get_entity_registry,
    )
except ImportError:
    # For standalone testing without proper installation
    pytest.skip(
        "Integration not properly installed for testing",
        allow_module_level=True,
    )


class TestFanIdConversion:
    """Test fan ID format conversion."""

    def test_convert_colon_to_underscore(self) -> None:
        """Test converting colon format to underscore format."""
        assert convert_device_id_format("32:153289") == "32_153289"
        assert convert_device_id_format("01:123456") == "01_123456"
        assert convert_device_id_format("99:000001") == "99_000001"

    def test_already_underscore_format(self) -> None:
        """Test handling already underscore format."""
        assert convert_device_id_format("32_153289") == "32_153289"

    def test_empty_string(self) -> None:
        """Test handling empty string."""
        assert convert_device_id_format("") == ""


class TestRequiredEntitiesCalculation:
    """Test required entities calculation."""

    def test_no_features_enabled(self) -> None:
        """Test with no features enabled."""
        enabled_features = {
            "hvac_fan_card": False,
            "humidity_automation": False,
        }
        fans = ["32:153289"]

        result = calculate_required_entities("sensor", enabled_features, fans, None)
        assert result == set()

    def test_with_features_enabled(
        self, mock_available_features: dict, mock_device_mapping: dict
    ) -> None:
        """Test with features enabled."""
        enabled_features = {
            "hvac_fan_card": True,
            "humidity_automation": False,
        }
        fans = ["32:153289"]

        # Mock the required constants
        import ramses_extras.const as const_module

        const_module.AVAILABLE_FEATURES = mock_available_features
        const_module.DEVICE_ENTITY_MAPPING = mock_device_mapping

        result = calculate_required_entities("sensor", enabled_features, fans, None)
        assert len(result) > 0
        assert any("32:153289" in entity for entity in result)


class TestEntityRegistry:
    """Test entity registry functions."""

    def test_get_entity_registry_available(self) -> None:
        """Test getting entity registry when available."""
        mock_hass = Mock()
        mock_hass.data = {"entity_registry": Mock()}

        result = get_entity_registry(mock_hass)
        assert result is not None

    def test_get_entity_registry_unavailable(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test getting entity registry when not available."""
        mock_hass = Mock()
        mock_hass.data = {}

        result = get_entity_registry(mock_hass)
        assert result is None
        assert "Entity registry not available" in caplog.text


class TestOrphanedEntities:
    """Test finding orphaned entities."""

    def test_find_orphaned_entities_no_registry(self) -> None:
        """Test finding orphaned entities when no registry."""
        mock_hass = Mock()
        mock_hass.data = {}

        result = find_orphaned_entities("sensor", mock_hass, [], set(), [])
        assert result == []

    def test_find_orphaned_entities_with_matches(self) -> None:
        """Test finding orphaned entities with matches."""
        # Mock entity registry with actual entity IDs
        mock_entity_registry = Mock()
        mock_entity_registry.entities = {
            "sensor.indoor_absolute_humidity_32_153289": Mock(),
            "sensor.outdoor_absolute_humidity_32_153289": Mock(),
            "sensor.different_device_99_123456": Mock(),
        }

        mock_hass = Mock()
        mock_hass.data = {"entity_registry": mock_entity_registry}

        fans = ["32:153289"]
        required_entities: set[str] = set()  # No entities required
        all_possible_types = ["indoor_abs_humid", "outdoor_abs_humid"]

        result = find_orphaned_entities(
            "sensor", mock_hass, fans, required_entities, all_possible_types
        )

        # Should find the two entities for 32:153289
        assert len(result) == 2
        assert all("32_153289" in entity for entity in result)


class TestPlatformEntityCreation:
    """Test entity creation for each platform."""

    def test_switch_entity_instantiation(self) -> None:
        """Test that switch entities can be instantiated correctly."""
        from ramses_extras.const import SWITCH_CONFIGS
        from ramses_extras.switch import RamsesDehumidifySwitch

        # Mock HASS
        mock_hass = Mock()

        # Test entity instantiation
        device_id = "32:153289"
        switch_type = "dehumidify"
        config = SWITCH_CONFIGS[switch_type]

        switch_entity = RamsesDehumidifySwitch(
            mock_hass, device_id, switch_type, config
        )

        # Verify entity properties
        assert switch_entity.__class__.__name__ == "RamsesDehumidifySwitch"
        assert switch_entity._device_id == device_id
        assert switch_entity._switch_type == switch_type
        assert switch_entity._attr_name == f"{config['name_template']} ({device_id})"
        assert (
            switch_entity._attr_unique_id == f"dehumidify_{device_id.replace(':', '_')}"
        )

    def test_number_entity_instantiation(self) -> None:
        """Test that number entities can be instantiated correctly."""
        from ramses_extras.const import NUMBER_CONFIGS
        from ramses_extras.number import RamsesNumberEntity

        # Mock HASS
        mock_hass = Mock()

        # Test entity instantiation
        device_id = "32:153289"
        number_type = "relative_humidity_minimum"
        config = NUMBER_CONFIGS[number_type]

        number_entity = RamsesNumberEntity(mock_hass, device_id, number_type, config)

        # Verify entity properties
        assert number_entity.__class__.__name__ == "RamsesNumberEntity"
        assert number_entity._device_id == device_id
        assert number_entity._number_type == number_type
        assert number_entity._attr_native_min_value == config["min_value"]
        assert number_entity._attr_native_max_value == config["max_value"]
        assert number_entity._attr_native_step == config["step"]

    def test_binary_sensor_entity_instantiation(self) -> None:
        """Test that binary sensor entities can be instantiated correctly."""
        from ramses_extras.binary_sensor import RamsesBinarySensor
        from ramses_extras.const import BOOLEAN_CONFIGS

        # Mock HASS
        mock_hass = Mock()

        # Test entity instantiation
        device_id = "32:153289"
        boolean_type = "dehumidifying_active"
        config = BOOLEAN_CONFIGS[boolean_type]

        binary_sensor_entity = RamsesBinarySensor(
            mock_hass, device_id, boolean_type, config
        )

        # Verify entity properties
        assert binary_sensor_entity.__class__.__name__ == "RamsesBinarySensor"
        assert binary_sensor_entity._device_id == device_id
        assert binary_sensor_entity._boolean_type == boolean_type
        assert (
            binary_sensor_entity._attr_name
            == f"{config['name_template']} ({device_id})"
        )

    def test_sensor_entity_instantiation(self) -> None:
        """Test that sensor entities can be instantiated correctly."""
        from ramses_extras.const import SENSOR_CONFIGS
        from ramses_extras.sensor import RamsesExtraHumiditySensor

        # Mock HASS
        mock_hass = Mock()

        # Test entity instantiation
        device_id = "32:153289"
        sensor_type = "indoor_absolute_humidity"
        config = SENSOR_CONFIGS[sensor_type]

        sensor_entity = RamsesExtraHumiditySensor(
            mock_hass, device_id, sensor_type, config
        )

        # Verify entity properties
        assert sensor_entity.__class__.__name__ == "RamsesExtraHumiditySensor"
        assert sensor_entity._device_id == device_id
        assert sensor_entity._sensor_type == sensor_type
        assert sensor_entity._attr_native_unit_of_measurement == config["unit"]
        assert sensor_entity._attr_device_class == config["device_class"]


# Fixtures for testing
@pytest.fixture  # type: ignore[misc]
def mock_available_features() -> dict:
    """Mock AVAILABLE_FEATURES constant."""
    return {
        "hvac_fan_card": {
            "supported_device_types": ["HvacVentilator"],
            "required_entities": {"sensors": ["indoor_abs_humid"]},
            "optional_entities": {"sensors": ["outdoor_abs_humid"]},
        }
    }


@pytest.fixture  # type: ignore[misc]
def mock_device_mapping() -> dict:
    """Mock DEVICE_ENTITY_MAPPING constant."""
    return {
        "HvacVentilator": {
            "sensors": ["indoor_abs_humid", "outdoor_abs_humid"],
            "switches": ["dehumidify"],
            "booleans": ["dehumidifying"],
        }
    }
