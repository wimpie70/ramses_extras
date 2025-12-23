# tests/framework/base_classes/test_platform_entities.py
"""Test platform entity base classes."""

from unittest.mock import MagicMock, patch

import pytest

from custom_components.ramses_extras.framework.base_classes.platform_entities import (
    ExtrasBinarySensorEntity,
    ExtrasNumberEntity,
    ExtrasPlatformEntity,
    ExtrasSensorEntity,
    ExtrasSwitchEntity,
)


class TestExtrasPlatformEntity:
    """Test ExtrasPlatformEntity class."""

    @patch(
        "custom_components.ramses_extras.framework.base_classes.platform_entities.EntityHelpers"
    )
    def test_init_basic(self, mock_entity_helpers, hass):
        """Test basic initialization of ExtrasPlatformEntity."""
        device_id = "32:153289"
        entity_type = "sensor"
        config = {"test": "value"}
        platform_type = "sensor"

        mock_entity_helpers.generate_entity_name_from_template.return_value = (
            "sensor.test_32_153289"
        )

        entity = ExtrasPlatformEntity(
            hass, device_id, entity_type, config, platform_type
        )

        # Check base entity initialization
        assert entity.hass == hass
        assert entity.device_id == device_id
        assert entity._entity_type == entity_type
        assert entity._entity_config == config
        assert entity._platform_type == platform_type

        # Check entity identity setup was called
        mock_entity_helpers.generate_entity_name_from_template.assert_called_once()

    @patch(
        "custom_components.ramses_extras.framework.base_classes.platform_entities.EntityHelpers"
    )
    def test_setup_entity_identity(self, mock_entity_helpers, hass):
        """Test entity identity setup."""
        # Create entity with config that has entity_template
        config = {"entity_template": "custom_{entity_type}_{device_id}"}
        entity = ExtrasPlatformEntity(hass, "32:153289", "sensor", config, "sensor")

        # Reset the mock to clear calls from __init__
        mock_entity_helpers.generate_entity_name_from_template.reset_mock()

        # Mock the entity helpers methods
        mock_entity_helpers.generate_entity_name_from_template.return_value = (
            "sensor.test_32_153289"
        )

        entity._setup_entity_identity()

        mock_entity_helpers.generate_entity_name_from_template.assert_called_once_with(
            "sensor",
            "custom_{entity_type}_{device_id}",
            device_id="32_153289",
        )

    @patch(
        "custom_components.ramses_extras.framework.base_classes.platform_entities.EntityHelpers"
    )
    def test_name_property(self, mock_entity_helpers, hass):
        """Test name property."""
        mock_entity_helpers.generate_entity_name_from_template.return_value = (
            "sensor.test_32_153289"
        )

        entity = ExtrasPlatformEntity(hass, "32:153289", "sensor", {}, "sensor")

        # Test with default name template
        assert entity.name == "sensor 32_153289"

        # Test with custom name template
        entity._entity_config = {"name_template": "Test {device_id}"}
        entity._setup_entity_identity()  # Re-run setup with new config
        assert entity.name == "Test 32_153289"

    @patch(
        "custom_components.ramses_extras.framework.base_classes.platform_entities.EntityHelpers"
    )
    def test_extra_state_attributes(self, mock_entity_helpers, hass):
        """Test extra state attributes."""
        mock_entity_helpers.generate_entity_name_from_template.return_value = (
            "sensor.test_32_153289"
        )

        entity = ExtrasPlatformEntity(hass, "32:153289", "sensor", {}, "sensor")

        attributes = entity.extra_state_attributes

        expected = {
            "entity_type": "sensor",
            "platform_type": "sensor",
            "device_id": "32:153289",
        }
        assert attributes == expected


class TestExtrasSwitchEntity:
    """Test ExtrasSwitchEntity class."""

    @patch(
        "custom_components.ramses_extras.framework.base_classes.platform_entities.EntityHelpers"
    )
    def test_init(self, mock_entity_helpers, hass):
        """Test initialization of ExtrasSwitchEntity."""
        device_id = "32:153289"
        switch_type = "power_switch"
        config = {"test": "value"}

        mock_entity_helpers.generate_entity_name_from_template.return_value = (
            "switch.power_switch_32_153289"
        )

        entity = ExtrasSwitchEntity(hass, device_id, switch_type, config)

        assert entity.device_id == device_id
        assert entity._entity_type == switch_type
        assert entity._entity_config == config
        assert entity._platform_type == "switch"
        assert entity._is_on is False

    @patch(
        "custom_components.ramses_extras.framework.base_classes.platform_entities.EntityHelpers"
    )
    def test_is_on_property(self, mock_entity_helpers, hass):
        """Test is_on property."""
        mock_entity_helpers.generate_entity_name_from_template.return_value = (
            "switch.power_switch_32_153289"
        )

        entity = ExtrasSwitchEntity(hass, "32:153289", "power_switch", {})

        # Test default state
        assert entity.is_on is False

        # Test with state set
        entity._is_on = True
        assert entity.is_on is True


class TestExtrasNumberEntity:
    """Test ExtrasNumberEntity class."""

    @patch(
        "custom_components.ramses_extras.framework.base_classes.platform_entities.EntityHelpers"
    )
    def test_init(self, mock_entity_helpers, hass):
        """Test initialization of ExtrasNumberEntity."""
        device_id = "32:153289"
        number_type = "temperature_setpoint"
        config = {
            "min_value": 15.0,
            "max_value": 30.0,
            "step": 0.5,
            "unit": "°C",
            "default_value": 20.0,
        }

        mock_entity_helpers.generate_entity_name_from_template.return_value = (
            "number.temperature_setpoint_32_153289"
        )

        entity = ExtrasNumberEntity(hass, device_id, number_type, config)

        assert entity.device_id == device_id
        assert entity._entity_type == number_type
        assert entity._entity_config == config
        assert entity._platform_type == "number"
        assert entity._native_value == 20.0  # default_value from config
        assert entity._attr_native_min_value == 15.0
        assert entity._attr_native_max_value == 30.0
        assert entity._attr_native_step == 0.5
        assert entity._attr_native_unit_of_measurement == "°C"

    @patch(
        "custom_components.ramses_extras.framework.base_classes.platform_entities.EntityHelpers"
    )
    def test_native_value_property(self, mock_entity_helpers, hass):
        """Test native_value property."""
        mock_entity_helpers.generate_entity_name_from_template.return_value = (
            "number.temp_setpoint_32_153289"
        )

        entity = ExtrasNumberEntity(hass, "32:153289", "temp_setpoint", {})

        # Test default state
        assert entity.native_value == 50.0  # Default value

        # Test with value set
        entity._native_value = 22.5
        assert entity.native_value == 22.5

    @pytest.mark.asyncio
    @patch(
        "custom_components.ramses_extras.framework.base_classes.platform_entities.EntityHelpers"
    )
    async def test_async_set_native_value(self, mock_entity_helpers, hass):
        """Test async_set_native_value method."""
        mock_entity_helpers.generate_entity_name_from_template.return_value = (
            "number.temp_setpoint_32_153289"
        )

        entity = ExtrasNumberEntity(hass, "32:153289", "temp_setpoint", {})

        await entity.async_set_native_value(25.0)

        assert entity._native_value == 25.0

    @patch(
        "custom_components.ramses_extras.framework.base_classes.platform_entities.EntityHelpers"
    )
    def test_extra_state_attributes_number(self, mock_entity_helpers, hass):
        """Test extra state attributes for number entity."""
        mock_entity_helpers.generate_entity_name_from_template.return_value = (
            "number.temp_setpoint_32_153289"
        )

        entity = ExtrasNumberEntity(
            hass,
            "32:153289",
            "temp_setpoint",
            {
                "min_value": 15.0,
                "max_value": 30.0,
                "step": 0.5,
            },
        )

        attributes = entity.extra_state_attributes

        expected = {
            "entity_type": "temp_setpoint",
            "platform_type": "number",
            "device_id": "32:153289",
            "number_type": "temp_setpoint",
            "min_value": 15.0,
            "max_value": 30.0,
            "step": 0.5,
        }
        assert attributes == expected


class TestExtrasBinarySensorEntity:
    """Test ExtrasBinarySensorEntity class."""

    @patch(
        "custom_components.ramses_extras.framework.base_classes.platform_entities.EntityHelpers"
    )
    def test_init(self, mock_entity_helpers, hass):
        """Test initialization of ExtrasBinarySensorEntity."""
        device_id = "32:153289"
        binary_type = "motion_sensor"
        config = {"device_class": "motion"}

        mock_entity_helpers.generate_entity_name_from_template.return_value = (
            "binary_sensor.motion_sensor_32_153289"
        )

        entity = ExtrasBinarySensorEntity(hass, device_id, binary_type, config)

        assert entity.device_id == device_id
        assert entity._entity_type == binary_type
        assert entity._entity_config == config
        assert entity._platform_type == "binary_sensor"
        assert entity._attr_device_class == "motion"
        assert entity._is_on is False

    @patch(
        "custom_components.ramses_extras.framework.base_classes.platform_entities.EntityHelpers"
    )
    def test_is_on_property_binary_sensor(self, mock_entity_helpers, hass):
        """Test is_on property for binary sensor."""
        mock_entity_helpers.generate_entity_name_from_template.return_value = (
            "binary_sensor.motion_sensor_32_153289"
        )

        entity = ExtrasBinarySensorEntity(hass, "32:153289", "motion_sensor", {})

        # Test default state
        assert entity.is_on is False

        # Test with state set
        entity._is_on = True
        assert entity.is_on is True

    @patch(
        "custom_components.ramses_extras.framework.base_classes.platform_entities.EntityHelpers"
    )
    def test_set_state(self, mock_entity_helpers, hass):
        """Test set_state method."""
        mock_entity_helpers.generate_entity_name_from_template.return_value = (
            "binary_sensor.motion_sensor_32_153289"
        )

        entity = ExtrasBinarySensorEntity(hass, "32:153289", "motion_sensor", {})

        entity.set_state(True)
        assert entity._is_on is True

        entity.set_state(False)
        assert entity._is_on is False

    @patch(
        "custom_components.ramses_extras.framework.base_classes.platform_entities.EntityHelpers"
    )
    def test_extra_state_attributes_binary_sensor(self, mock_entity_helpers, hass):
        """Test extra state attributes for binary sensor."""
        mock_entity_helpers.generate_entity_name_from_template.return_value = (
            "binary_sensor.motion_sensor_32_153289"
        )

        entity = ExtrasBinarySensorEntity(hass, "32:153289", "motion_sensor", {})

        attributes = entity.extra_state_attributes

        expected = {
            "entity_type": "motion_sensor",
            "platform_type": "binary_sensor",
            "device_id": "32:153289",
            "binary_type": "motion_sensor",
        }
        assert attributes == expected


class TestExtrasSensorEntity:
    """Test ExtrasSensorEntity class."""

    @patch(
        "custom_components.ramses_extras.framework.base_classes.platform_entities.EntityHelpers"
    )
    def test_init(self, mock_entity_helpers, hass):
        """Test initialization of ExtrasSensorEntity."""
        device_id = "32:153289"
        sensor_type = "indoor_temperature"
        config = {
            "unit": "°C",
            "device_class": "temperature",
            "icon": "mdi:thermometer",
        }

        mock_entity_helpers.generate_entity_name_from_template.return_value = (
            "sensor.indoor_temperature_32_153289"
        )

        entity = ExtrasSensorEntity(hass, device_id, sensor_type, config)

        assert entity.device_id == device_id
        assert entity._entity_type == sensor_type
        assert entity._entity_config == config
        assert entity._platform_type == "sensor"
        assert entity._attr_unit_of_measurement == "°C"
        assert entity._attr_device_class == "temperature"
        assert entity._attr_icon == "mdi:thermometer"
        assert entity._attr_native_value is None

    @patch(
        "custom_components.ramses_extras.framework.base_classes.platform_entities.EntityHelpers"
    )
    def test_state_property_sensor(self, mock_entity_helpers, hass):
        """Test state property for sensor."""
        mock_entity_helpers.generate_entity_name_from_template.return_value = (
            "sensor.temperature_32_153289"
        )

        entity = ExtrasSensorEntity(hass, "32:153289", "temperature", {})

        # Test default state
        assert entity.state is None

        # Test with native value set
        entity._attr_native_value = 25.5
        assert entity.state == 25.5
