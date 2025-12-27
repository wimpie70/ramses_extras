"""Comprehensive tests for Default Feature Sensor Platform.

This module provides comprehensive tests for the default feature sensor platform,
combining focused unit tests with platform-level integration testing.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.ramses_extras.features.default.const import (
    DEFAULT_SENSOR_CONFIGS,
    ENTITY_PATTERNS,
)
from custom_components.ramses_extras.features.default.platforms.sensor import (
    DefaultHumiditySensor,
    async_setup_entry,
    create_default_sensor,
)


class TestDefaultSensorPlatform:
    """Test cases for default feature sensor platform integration."""

    @pytest.fixture
    def hass(self):
        """Create a mock Home Assistant instance."""
        hass = MagicMock(spec=dict)  # Use dict spec to avoid MagicMock issues
        hass.data = {
            "ramses_extras": {
                "devices": ["32:153289", "37:126776"],
                "entity_manager": MagicMock(),
            }
        }
        hass.states = MagicMock()
        return hass

    @pytest.fixture
    def config_entry(self):
        """Create a mock config entry."""
        config_entry = MagicMock(spec=dict)
        config_entry.data = {
            "device_feature_matrix": {
                "32:153289": {"default": True},
                "37:126776": {"default": False},
            }
        }
        config_entry.options = {}
        return config_entry

    @pytest.fixture
    def async_add_entities(self):
        """Create a mock async_add_entities callback."""
        return MagicMock()

    async def test_async_setup_entry_creates_sensors_for_enabled_devices(
        self, hass, config_entry, async_add_entities
    ):
        """Test that async_setup_entry creates sensors for enabled devices.

        Verifies that when a device is enabled for the default feature,
        sensors are created and added to Home Assistant.
        """
        # Mock the entity manager to return device enablement status
        mock_entity_manager = MagicMock()
        # Mock the device enablement check to return True for first device,
        # False for second
        mock_entity_manager.device_feature_matrix.is_device_enabled_for_feature.side_effect = [  # noqa: E501
            True,
            False,
        ]
        hass.data["ramses_extras"]["entity_manager"] = mock_entity_manager

        # Mock create_default_sensor to return test sensors
        with patch(
            "custom_components.ramses_extras.features.default.platforms.sensor.create_default_sensor",  # noqa: E501
            new_callable=AsyncMock,
        ) as mock_create_sensor:
            mock_create_sensor.return_value = [MagicMock(), MagicMock()]  # 2 sensors

            await async_setup_entry(hass, config_entry, async_add_entities)

            # Verify create_default_sensor was called for enabled device
            assert mock_create_sensor.call_count >= 1
            # Check that at least one call was with the correct device ID
            device_ids_called = [
                call[0][1] for call in mock_create_sensor.call_args_list
            ]
            assert "32:153289" in device_ids_called

            # Verify sensors were added
            async_add_entities.assert_called_once()
            args, kwargs = async_add_entities.call_args
            assert len(args[0]) == 2  # 2 sensors created
            assert args[1] is True  # update_before_add

    async def test_async_setup_entry_skips_disabled_devices(
        self, hass, config_entry, async_add_entities
    ):
        """Test that async_setup_entry skips disabled devices."""
        # Mock the entity manager to return device enablement status
        mock_entity_manager = MagicMock()
        # Mock the device enablement check to return False for both devices
        mock_entity_manager.device_feature_matrix.is_device_enabled_for_feature.return_value = False  # noqa: E501
        hass.data["ramses_extras"]["entity_manager"] = mock_entity_manager

        with patch(
            "custom_components.ramses_extras.features.default.platforms.sensor.create_default_sensor",  # noqa: E501
            new_callable=AsyncMock,
        ) as mock_create_sensor:
            await async_setup_entry(hass, config_entry, async_add_entities)

            # Verify create_default_sensor was not called
            mock_create_sensor.assert_not_called()

            # Verify async_add_entities was called with empty list
            async_add_entities.assert_called_once()
            args, kwargs = async_add_entities.call_args
            assert len(args[0]) == 0  # No sensors created
            assert args[1] is True  # update_before_add

    async def test_async_setup_entry_handles_missing_entity_manager(
        self, hass, config_entry, async_add_entities
    ):
        """Test that async_setup_entry handles missing entity manager gracefully."""
        # Remove entity manager from hass data
        hass.data["ramses_extras"]["entity_manager"] = None

        with patch(
            "custom_components.ramses_extras.framework.helpers.entity.simple_entity_manager.SimpleEntityManager"  # noqa: E501
        ) as mock_manager_class:
            mock_manager = MagicMock()
            mock_manager_class.return_value = mock_manager
            # Mock the device enablement check to return True for both devices
            mock_manager.device_feature_matrix.is_device_enabled_for_feature.return_value = True  # noqa: E501

            with patch(
                "custom_components.ramses_extras.features.default.platforms.sensor.create_default_sensor",  # noqa: E501
                new_callable=AsyncMock,
            ) as mock_create_sensor:
                mock_create_sensor.return_value = [MagicMock()]

                await async_setup_entry(hass, config_entry, async_add_entities)

                # Verify SimpleEntityManager was created
                mock_manager_class.assert_called_once_with(hass)
                # Verify create_default_sensor was called for both devices
                assert mock_create_sensor.call_count == 2
                # Verify sensors were added
                async_add_entities.assert_called()


class TestDefaultHumiditySensor:
    """Test cases for DefaultHumiditySensor class."""

    @pytest.fixture
    def hass(self):
        """Create a mock Home Assistant instance."""
        hass = MagicMock()
        hass.states = MagicMock()
        return hass

    @pytest.fixture
    def sensor_config(self):
        """Create a sensor configuration."""
        return {
            "name_template": "Test Humidity {device_id}",
            "unit": "g/m³",
            "icon": "mdi:water-percent",
            "device_class": None,
        }

    def test_sensor_initialization(self, hass, sensor_config):
        """Test sensor initialization."""
        sensor = DefaultHumiditySensor(
            hass, "32:153289", "indoor_absolute_humidity", sensor_config
        )

        assert sensor._device_id == "32:153289"
        assert sensor._sensor_type == "indoor_absolute_humidity"
        assert sensor._attr_native_unit_of_measurement == "g/m³"
        assert sensor._attr_icon == "mdi:water-percent"
        assert sensor.unique_id == "indoor_absolute_humidity_32_153289"
        assert "32_153289" in sensor.name

    def test_sensor_name_property(self, hass, sensor_config):
        """Test sensor name property."""
        sensor = DefaultHumiditySensor(
            hass, "32:153289", "indoor_absolute_humidity", sensor_config
        )
        assert "32_153289" in sensor.name

    def test_extra_state_attributes(self, hass, sensor_config):
        """Test extra state attributes."""
        sensor = DefaultHumiditySensor(
            hass, "32:153289", "indoor_absolute_humidity", sensor_config
        )
        attrs = sensor.extra_state_attributes
        assert attrs is not None
        assert attrs.get("sensor_type") == "indoor_absolute_humidity"

    def test_calculate_abs_humidity(self, hass, sensor_config):
        """Test absolute humidity calculation."""
        sensor = DefaultHumiditySensor(
            hass, "32:153289", "indoor_absolute_humidity", sensor_config
        )

        # Test valid inputs
        result = sensor._calculate_abs_humidity(20.0, 50.0)
        assert result is not None
        assert isinstance(result, float)
        assert result > 0

        # Test invalid inputs
        assert sensor._calculate_abs_humidity(None, 50.0) is None
        assert sensor._calculate_abs_humidity(20.0, None) is None

    def test_get_temp_and_humidity_missing_entities(self, hass, sensor_config):
        """Test temperature and humidity retrieval with missing entities.

        Verifies that when the underlying temperature and humidity entities
        are not found, the method returns (None, None).
        """
        sensor = DefaultHumiditySensor(
            hass, "32:153289", "indoor_absolute_humidity", sensor_config
        )

        # Mock hass.states.get to return None (missing entities)
        hass.states.get.return_value = None

        temp, humidity = sensor._get_temp_and_humidity()
        assert temp is None
        assert humidity is None

    def test_get_temp_and_humidity_invalid_states(self, hass, sensor_config):
        """Test temperature and humidity retrieval with invalid states.

        Verifies that when the underlying entities exist but have unavailable
        or unknown states, the method returns (None, None).
        """
        sensor = DefaultHumiditySensor(
            hass, "32:153289", "indoor_absolute_humidity", sensor_config
        )

        # Mock hass.states.get to return unavailable states
        mock_state = MagicMock()
        mock_state.state = "unavailable"
        hass.states.get.return_value = mock_state

        temp, humidity = sensor._get_temp_and_humidity()
        assert temp is None
        assert humidity is None

    def test_get_temp_and_humidity_valid_values(self, hass, sensor_config):
        """Test temperature and humidity retrieval with valid values."""
        sensor = DefaultHumiditySensor(
            hass, "32:153289", "indoor_absolute_humidity", sensor_config
        )

        # Mock hass.states.get to return valid states
        temp_state = MagicMock()
        temp_state.state = "20.0"
        humidity_state = MagicMock()
        humidity_state.state = "50.0"

        def mock_get(entity_id):
            if "indoor_temp" in entity_id:
                return temp_state
            if "indoor_humidity" in entity_id:
                return humidity_state
            return None

        hass.states.get = mock_get

        temp, humidity = sensor._get_temp_and_humidity()
        assert temp == 20.0
        assert humidity == 50.0

    def test_get_temp_and_humidity_invalid_humidity_range(self, hass, sensor_config):
        """Test temperature and humidity retrieval with invalid humidity range."""
        sensor = DefaultHumiditySensor(
            hass, "32:153289", "indoor_absolute_humidity", sensor_config
        )

        # Mock hass.states.get to return invalid humidity value
        temp_state = MagicMock()
        temp_state.state = "20.0"
        humidity_state = MagicMock()
        humidity_state.state = "150.0"  # Invalid: > 100%

        def mock_get(entity_id):
            if "indoor_temp" in entity_id:
                return temp_state
            if "indoor_humidity" in entity_id:
                return humidity_state
            return None

        hass.states.get = mock_get

        temp, humidity = sensor._get_temp_and_humidity()
        assert temp is None  # Should be None due to invalid humidity
        assert humidity is None  # Should be None due to invalid range


class TestCreateDefaultSensor:
    """Test cases for create_default_sensor function."""

    @pytest.fixture
    def hass(self):
        """Create a mock Home Assistant instance."""
        return MagicMock()

    async def test_create_default_sensor_for_fan_device(self, hass):
        """Test sensor creation for FAN devices."""
        sensors = await create_default_sensor(hass, "32:153289")

        # Should create 2 sensors (indoor and outdoor absolute humidity)
        assert len(sensors) == 2

        # Verify sensor types
        sensor_types = {sensor._sensor_type for sensor in sensors}
        assert sensor_types == {"indoor_absolute_humidity", "outdoor_absolute_humidity"}

        # Verify sensor configuration
        for sensor in sensors:
            assert isinstance(sensor, DefaultHumiditySensor)
            assert sensor._device_id == "32:153289"
            assert sensor._attr_native_unit_of_measurement == "g/m³"


class TestEntityPatterns:
    """Test entity pattern configurations."""

    def test_entity_patterns_structure(self):
        """Test that entity patterns have correct structure."""
        assert isinstance(ENTITY_PATTERNS, dict)

        # Should contain expected sensor types
        expected_sensors = ["indoor_absolute_humidity", "outdoor_absolute_humidity"]
        for sensor in expected_sensors:
            assert sensor in ENTITY_PATTERNS, f"Missing entity pattern for: {sensor}"

            pattern = ENTITY_PATTERNS[sensor]
            assert isinstance(pattern, tuple)
            assert len(pattern) == 2  # Should have (temp_type, humidity_type)

            temp_type, humidity_type = pattern
            assert isinstance(temp_type, str)
            assert isinstance(humidity_type, str)

    def test_entity_patterns_content(self):
        """Test that entity patterns contain expected content."""
        indoor_pattern = ENTITY_PATTERNS["indoor_absolute_humidity"]
        assert indoor_pattern == ("indoor_temp", "indoor_humidity")

        outdoor_pattern = ENTITY_PATTERNS["outdoor_absolute_humidity"]
        assert outdoor_pattern == ("outdoor_temp", "outdoor_humidity")


class TestPlatformRegistration:
    """Test platform registration functionality."""

    def test_platform_registration(self):
        """Test that the default sensor platform is properly registered."""
        from custom_components.ramses_extras.const import PLATFORM_REGISTRY

        # Check that the platform is registered
        assert "sensor" in PLATFORM_REGISTRY
        assert "default" in PLATFORM_REGISTRY["sensor"]

        # Check that the registered function is the correct one
        from custom_components.ramses_extras.features.default.platforms.sensor import (
            async_setup_entry,
        )

        registered_func = PLATFORM_REGISTRY["sensor"]["default"]
        assert registered_func == async_setup_entry

    def test_feature_import_registers_platform(self):
        """Test that importing the default feature registers the platform."""
        # This test verifies that the import in __init__.py works
        from custom_components.ramses_extras.features.default import (
            sensor_async_setup_entry,
        )
        from custom_components.ramses_extras.features.default.platforms.sensor import (
            async_setup_entry,
        )

        assert sensor_async_setup_entry == async_setup_entry
