# tests/framework/base_classes/test_base_entity.py
"""Test base entity classes."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from custom_components.ramses_extras.framework.base_classes.base_entity import (
    ExtrasBaseEntity,
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

    def test_unique_id_from_entity_id(self, hass):
        entity = ExtrasBaseEntity(hass, "32:153289")
        entity.entity_id = "sensor.some_entity"
        assert entity.unique_id == "some_entity"

    def test_unique_id_fallback_from_entity_type_and_device_id(self, hass):
        entity = ExtrasBaseEntity(hass, "32:153289", "sensor")
        assert entity.unique_id == "sensor_32_153289"

    @pytest.mark.parametrize(
        ("device", "expected"),
        [
            (SimpleNamespace(id="32:153289"), "32:153289"),
            (SimpleNamespace(device_id="32:153289"), "32:153289"),
            (SimpleNamespace(_id="32:153289"), "32:153289"),
        ],
    )
    def test_get_device_id_str_variants(self, hass, device, expected):
        entity = ExtrasBaseEntity(hass, device)
        assert entity._get_device_id_str() == expected

    def test_device_info_fallback_when_attr_missing(self, hass):
        entity = ExtrasBaseEntity(hass, "32:153289")
        entity._attr_device_info = None

        info = entity.device_info
        assert ("ramses_extras", "32:153289") in info["identifiers"]

    def test_device_info_uses_detected_device_type(self, hass):
        with (
            patch(
                "custom_components.ramses_extras.framework.helpers.device.core.find_ramses_device"
            ) as find_ramses_device,
            patch(
                "custom_components.ramses_extras.framework.helpers.device.core.get_device_type"
            ) as get_device_type,
        ):
            find_ramses_device.return_value = object()
            get_device_type.return_value = "HvacVentilator"

            entity = ExtrasBaseEntity(hass, "32:153289")
            info = entity.device_info

            assert info["model"] == "HvacVentilator"
            assert info["name"] == "HvacVentilator 32:153289"
