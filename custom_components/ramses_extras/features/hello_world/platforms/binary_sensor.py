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

import logging
from typing import TYPE_CHECKING, Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from custom_components.ramses_extras.framework.base_classes.platform_entities import (
    ExtrasBinarySensorEntity,
)
from custom_components.ramses_extras.framework.helpers.entity.core import EntityHelpers

from ..const import HELLO_WORLD_BINARY_SENSOR_CONFIGS

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)


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
    """Create Hello World binary sensor for a device.

    Args:
        hass: Home Assistant instance
        device_id: Device identifier
        config_entry: Configuration entry

    Returns:
        List of binary sensor entities
    """
    sensor_list = []

    device_type: str | None = None
    try:
        devices = hass.data.get("ramses_extras", {}).get("devices", [])
        for device in devices:
            if isinstance(device, dict):
                raw_id = device.get("device_id")
                dev_type = device.get("type")
            else:
                raw_id = device
                dev_type = getattr(device, "type", None)

            if raw_id is None:
                continue
            raw_str = str(raw_id)
            if raw_str in {
                device_id,
                device_id.replace(":", "_"),
                device_id.replace("_", ":"),
            }:
                device_type = str(dev_type) if dev_type is not None else None
                break
    except Exception:
        device_type = None

    for sensor_type, config in HELLO_WORLD_BINARY_SENSOR_CONFIGS.items():
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

    def __init__(
        self,
        hass: "HomeAssistant",
        device_id: str,
        sensor_type: str,
        config: dict[str, Any],
    ):
        """Initialize Hello World binary sensor entity."""
        super().__init__(hass, device_id, sensor_type, config)

        # Initialize state - will be updated by automation
        self._is_on = False

    async def async_added_to_hass(self) -> None:
        """Initialize Hello World binary sensor."""
        await super().async_added_to_hass()
        _LOGGER.info("Hello World binary sensor %s added to hass", self._attr_name)

        # Note: SimpleEntityManager handles state coordination automatically
        # No custom entity storage needed - framework handles coordination

    async def async_will_remove_from_hass(self) -> None:
        """Clean up when entity is removed."""
        await super().async_will_remove_from_hass()

        # Note: SimpleEntityManager handles cleanup automatically
        # No custom cleanup needed - framework handles coordination

    def set_state(self, is_on: bool) -> None:
        """Set the binary sensor state (used by automation triggers)."""
        self._is_on = is_on
        self.async_write_ha_state()
        _LOGGER.info(
            "Binary sensor %s state set to %s by automation",
            self._attr_name,
            is_on,
        )

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
