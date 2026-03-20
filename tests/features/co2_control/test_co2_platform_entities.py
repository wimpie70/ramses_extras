"""Tests for CO2 platform entity metadata behavior."""

from unittest.mock import MagicMock, patch

from homeassistant.core import HomeAssistant

from custom_components.ramses_extras.features.co2_control.platforms import (
    CO2ControlBinarySensor,
)
from custom_components.ramses_extras.features.co2_control.platforms.sensor import (
    CO2ControlSensor,
)


def test_co2_binary_sensor_set_state_with_attrs() -> None:
    """Binary sensor should persist metadata attrs from automation."""
    hass = MagicMock(spec=HomeAssistant)
    hass.data = {}
    entity = CO2ControlBinarySensor(
        hass,
        "32:123456",
        "co2_active",
        {
            "name_template": "CO2 Active {device_id}",
            "entity_template": "co2_active_{device_id}",
        },
    )

    attrs = {"active_trigger_source_id": "bathroom"}
    with patch.object(entity, "async_write_ha_state"):
        entity.set_state(True, attrs)

    assert entity.is_on is True
    assert entity.extra_state_attributes == attrs


def test_co2_sensor_set_zone_status_with_attrs() -> None:
    """Status sensor should expose metadata attrs and zone text."""
    hass = MagicMock(spec=HomeAssistant)
    hass.data = {}
    entity = CO2ControlSensor(
        hass,
        "32:123456",
        "co2_zone_status",
        {
            "name_template": "CO2 Zone Status {device_id}",
            "entity_template": "co2_zone_status_{device_id}",
        },
    )

    attrs = {"active_trigger_source_ids": ["bathroom", "internal_co2"]}
    with patch.object(entity, "async_write_ha_state"):
        entity.set_zone_status("active: Bathroom (1200ppm)", attrs)

    assert entity.native_value == "active: Bathroom (1200ppm)"
    assert entity.extra_state_attributes == attrs
