# Part of the Ramses Extra integration
# See https://github.com/wimpie70/ramses_extras for more information
#
"""Binary sensor platform for Hello World Switch Card feature.

This module provides the binary sensor platform implementation for the
 Hello World feature,
demonstrating automation-driven binary sensor entities that respond to switch changes.

:platform: Home Assistant
:feature: Hello World Binary Sensor
:components: Binary Sensor Entity, Automation Integration, State Management
:entity_type: Binary Sensor
:pattern: Switch → Automation → Binary Sensor
"""

from typing import TYPE_CHECKING, Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from custom_components.ramses_extras.framework.base_classes.platform_entities import (
    ExtrasBinarySensorEntity,
)
from custom_components.ramses_extras.framework.helpers.device.core import (
    find_ramses_device,
    get_device_type,
)
from custom_components.ramses_extras.framework.helpers.entity.core import EntityHelpers

from ..const import HELLO_WORLD_BINARY_SENSOR_CONFIGS

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant


async def async_setup_entry(
    hass: "HomeAssistant",
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Hello World binary sensor platform."""
    from custom_components.ramses_extras.framework.helpers import platform

    await platform.PlatformSetup.async_create_and_add_platform_entities(
        platform="binary_sensor",
        hass=hass,
        config_entry=config_entry,
        async_add_entities=async_add_entities,
        entity_configs=HELLO_WORLD_BINARY_SENSOR_CONFIGS,
        entity_factory=create_hello_world_binary_sensor,
        feature_id="hello_world",
        store_entities_for_automation=True,
    )


async def create_hello_world_binary_sensor(
    hass: "HomeAssistant",
    device_id: str,
    entity_configs: dict[str, Any],
    config_entry: ConfigEntry | None = None,
) -> list[ExtrasBinarySensorEntity]:
    """Create Hello World binary sensor entities for a device.

    :param hass: Home Assistant instance
    :param device_id: Device identifier
    :param entity_configs: Binary sensor entity configuration mapping
    :param config_entry: Configuration entry
    :return: List of binary sensor entities
    """
    sensor_list = []

    device_type: str | None = None
    try:
        device = find_ramses_device(hass, device_id)
        if device is not None:
            device_type = get_device_type(device)
    except Exception:
        device_type = None

    for sensor_type, config in entity_configs.items():
        supported_types = config.get("device_types", [])
        if (
            supported_types
            and device_type is not None
            and device_type not in supported_types
        ):
            continue

        sensor_entity = HelloWorldBinarySensor(hass, device_id, sensor_type, config)
        sensor_list.append(sensor_entity)

    return sensor_list


class HelloWorldBinarySensor(ExtrasBinarySensorEntity):
    """Hello World Binary Sensor entity controlled by automation.

    This binary sensor is triggered by automation, not direct switch mirroring.
    It demonstrates the automation-driven architecture pattern where the binary
    sensor state is controlled by the HelloWorldAutomationManager rather than
    directly mirroring the switch state.

    The binary sensor responds to switch changes through the automation system,
    showcasing how complex logic can be implemented in the automation layer
    while keeping entities simple and focused.

    Attributes:
        _is_on (bool): Current state of the binary sensor (True for ON, False for OFF).

    Inherits from:
        ExtrasBinarySensorEntity: Base class providing common binary sensor
         functionality.

    Note:
        This entity is designed to work with the HelloWorldAutomationManager which
        calls the set_state() method to update the sensor state based on automation
         logic.
    """

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        base_attrs = super().extra_state_attributes or {}
        device_id_underscore = self.device_id.replace(":", "_")
        return {
            **base_attrs,
            "automation_controlled": True,
            "controlled_by": "hello_world_automation",
            "switch_entity": EntityHelpers.generate_entity_name_from_template(
                "switch",
                "hello_world_switch_{device_id}",
                device_id=device_id_underscore,
            ),
            "demo_feature": True,
            "pattern": "switch → automation → binary_sensor",
        }


# Register this platform with the global registry
from custom_components.ramses_extras.const import (  # noqa: E402
    register_feature_platform,  # noqa: E402
)

register_feature_platform("binary_sensor", "hello_world", async_setup_entry)

__all__ = [
    "HelloWorldBinarySensor",
    "async_setup_entry",
    "create_hello_world_binary_sensor",
]
