# Part of the Ramses Extra integration
# See https://github.com/wimpie70/ramses_extras for more information
#
"""Binary sensor platform for Hello World Switch Card feature."""

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
        feature_id="hello_world_card",
    )


async def create_hello_world_binary_sensor(
    hass: "HomeAssistant", device_id: str, config_entry: ConfigEntry | None = None
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

    for sensor_type, config in HELLO_WORLD_BINARY_SENSOR_CONFIGS.items():
        supported_types = config.get("device_types", [])
        if supported_types and "HvacVentilator" in supported_types:
            sensor_entity = HelloWorldBinarySensor(hass, device_id, sensor_type, config)
            sensor_list.append(sensor_entity)

    return sensor_list


class HelloWorldBinarySensor(ExtrasBinarySensorEntity):
    """Hello World Binary Sensor entity controlled by automation.

    This binary sensor is triggered by automation, not direct switch mirroring.
    It demonstrates the automation-driven architecture pattern.
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
        return {
            **base_attrs,
            "automation_controlled": True,
            "controlled_by": "hello_world_automation",
            "switch_entity": EntityHelpers.generate_entity_name_from_template(
                "switch", "hello_world_switch_{device_id}", device_id=self.device_id
            ),
            "demo_feature": True,
            "pattern": "switch → automation → binary_sensor",
        }


# Register this platform with the global registry
from custom_components.ramses_extras.const import (  # noqa: E402
    register_feature_platform,  # noqa: E402
)

register_feature_platform("binary_sensor", "hello_world_card", async_setup_entry)

__all__ = [
    "HelloWorldBinarySensor",
    "async_setup_entry",
    "create_hello_world_binary_sensor",
]
