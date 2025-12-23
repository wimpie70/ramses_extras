# tests/framework/base_classes/test_base_entity.py
"""Test base entity classes."""

from unittest.mock import MagicMock, patch

import pytest

from custom_components.ramses_extras.framework.base_classes.base_entity import (
    ExtrasBaseEntity,
    RamsesSensorEntity,
)


class TestExtrasBaseEntity:
    """Test ExtrasBaseEntity class."""

    def test_init_basic(self, hass):
        """Test basic initialization of ExtrasBaseEntity."""
        device_id = "32:153289"
        entity_type = "sensor"
        config = {"test": "value"}

        entity = ExtrasBaseEntity(hass, device_id, entity_type, config)

        assert entity.hass == hass
        assert entity.device_id == device_id
        assert entity._device_id == device_id
        assert entity._entity_type == entity_type
        assert entity._config == config
        assert entity._attr_name == ""

    def test_init_minimal(self, hass):
        """Test initialization with minimal parameters."""
        device_id = "32:153289"

        entity = ExtrasBaseEntity(hass, device_id)

        assert entity.hass == hass
        assert entity.device_id == device_id
        assert entity._entity_type is None
        assert entity._config == {}

    def test_unique_id_property(self, hass):
        """Test unique_id property."""
        entity = ExtrasBaseEntity(hass, "32:153289")

        # Initially empty
        assert entity.unique_id == ""

        # Can be set
        entity._attr_unique_id = "test_unique_id"
        assert entity.unique_id == "test_unique_id"


class TestRamsesSensorEntity:
    """Test RamsesSensorEntity class."""

    @patch(
        "custom_components.ramses_extras.framework.base_classes.base_entity.EntityHelpers"
    )
    def test_init_basic(self, mock_entity_helpers, hass):
        """Test basic initialization of RamsesSensorEntity."""
        device_id = "32:153289"
        device_type = "HvacVentilator"
        entity_name = "indoor_temperature"
        config = {
            "unit": "°C",
            "icon": "mdi:thermometer",
            "device_class": "temperature",
            "entity_category": "diagnostic",
        }

        mock_entity_helpers.generate_entity_name_from_template.return_value = (
            "sensor.indoor_temperature_32_153289"
        )

        entity = RamsesSensorEntity(device_id, device_type, entity_name, config)

        # Check initialization
        assert entity._device_id == device_id
        assert entity._device_type == device_type
        assert entity._entity_name == entity_name
        assert entity._config == config

        # Check entity ID generation
        mock_entity_helpers.generate_entity_name_from_template.assert_called_once_with(
            "sensor",
            entity_name + "_{device_id}",
            device_id=device_id,
        )
        assert entity.entity_id == "sensor.indoor_temperature_32_153289"
        assert entity._attr_unique_id == f"{device_id}_{entity_name}"

        # Check attributes
        assert entity._attr_unit_of_measurement == "°C"
        assert entity._attr_icon == "mdi:thermometer"
        assert entity._attr_device_class == "temperature"
        assert entity._attr_native_value is None

    @patch(
        "custom_components.ramses_extras.framework.base_classes.base_entity.EntityHelpers"
    )
    def test_init_with_name_template(self, mock_entity_helpers, hass):
        """Test initialization with name template."""
        device_id = "32:153289"
        device_type = "HvacVentilator"
        entity_name = "indoor_temperature"
        config = {
            "name_template": "Temperature {device_id}",
        }

        mock_entity_helpers.generate_entity_name_from_template.return_value = (
            "sensor.indoor_temperature_32_153289"
        )

        entity = RamsesSensorEntity(device_id, device_type, entity_name, config)

        # Check name generation
        assert entity._attr_name == "Temperature 32:153289"

    @patch(
        "custom_components.ramses_extras.framework.base_classes.base_entity.EntityHelpers"
    )
    def test_init_without_name_template(self, mock_entity_helpers, hass):
        """Test initialization without name template."""
        device_id = "32:153289"
        device_type = "HvacVentilator"
        entity_name = "indoor_temperature"
        config = {}

        mock_entity_helpers.generate_entity_name_from_template.return_value = (
            "sensor.indoor_temperature_32_153289"
        )

        entity = RamsesSensorEntity(device_id, device_type, entity_name, config)

        # Check default name generation
        assert entity._attr_name == "Indoor Temperature 32:153289"

    @patch(
        "custom_components.ramses_extras.framework.base_classes.base_entity.EntityHelpers"
    )
    def test_init_entity_name_generation_failure(
        self, mock_entity_helpers, hass, caplog
    ):
        """Test handling of entity name generation failure."""
        device_id = "32:153289"
        device_type = "HvacVentilator"
        entity_name = "indoor_temperature"
        config = {}

        mock_entity_helpers.generate_entity_name_from_template.side_effect = Exception(
            "Template error"
        )

        # Just create the entity, we don't need to use it since we're checking the log
        RamsesSensorEntity(device_id, device_type, entity_name, config)

        # Check that warning was logged
        assert "Entity name generation failed" in caplog.text
        assert "Template error" in caplog.text

    def test_state_property(self, hass):
        """Test state property."""
        device_id = "32:153289"
        device_type = "HvacVentilator"
        entity_name = "indoor_temperature"
        config = {}

        with patch(
            "custom_components.ramses_extras.framework.base_classes.base_entity.EntityHelpers"
        ):
            entity = RamsesSensorEntity(device_id, device_type, entity_name, config)

            # Initially None
            assert entity.state is None

            # Set value
            entity._attr_native_value = 25.5
            assert entity.state == 25.5

    @pytest.mark.asyncio
    async def test_async_update(self, hass):
        """Test async_update method."""
        device_id = "32:153289"
        device_type = "HvacVentilator"
        entity_name = "indoor_temperature"
        config = {}

        with patch(
            "custom_components.ramses_extras.framework.base_classes.base_entity.EntityHelpers"
        ):
            entity = RamsesSensorEntity(device_id, device_type, entity_name, config)

            # Initially None
            assert entity._attr_native_value is None

            # Update
            await entity.async_update()

            # Should set to 0.0 as placeholder
            assert entity._attr_native_value == 0.0

    @pytest.mark.asyncio
    async def test_async_update_existing_value(self, hass):
        """Test async_update when value already exists."""
        device_id = "32:153289"
        device_type = "HvacVentilator"
        entity_name = "indoor_temperature"
        config = {}

        with patch(
            "custom_components.ramses_extras.framework.base_classes.base_entity.EntityHelpers"
        ):
            entity = RamsesSensorEntity(device_id, device_type, entity_name, config)

            # Set existing value
            entity._attr_native_value = 23.5

            # Update
            await entity.async_update()

            # Should not change existing value
            assert entity._attr_native_value == 23.5
