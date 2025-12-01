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

from ..const import HELLO_WORLD_BINARY_SENSOR_CONFIGS
from ..entities import HelloWorldEntities

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

    await platform.PlatformSetup.async_setup_platform(
        platform="binary_sensor",
        hass=hass,
        config_entry=config_entry,
        async_add_entities=async_add_entities,
        entity_configs=HELLO_WORLD_BINARY_SENSOR_CONFIGS,
        entity_factory=create_hello_world_binary_sensor,
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
    """Hello World Binary Sensor entity that mirrors the switch state."""

    def __init__(
        self,
        hass: "HomeAssistant",
        device_id: str,
        sensor_type: str,
        config: dict[str, Any],
    ):
        """Initialize Hello World binary sensor entity."""
        super().__init__(hass, device_id, sensor_type, config)

        # Initialize with state from entities manager
        entities_manager = HelloWorldEntities(hass, None)
        self._is_on = bool(
            entities_manager.get_entity_state(device_id, "switch", "hello_world_switch")
        )

    async def async_added_to_hass(self) -> None:
        """Subscribe to Ramses RF device updates."""
        await super().async_added_to_hass()
        _LOGGER.info("Hello World binary sensor %s added to hass", self._attr_name)

    async def _handle_update(self, *args: Any, **kwargs: Any) -> None:
        """Handle updates from Ramses RF."""
        _LOGGER.debug(
            "Device update for Hello World binary sensor %s received", self._attr_name
        )
        self.async_write_ha_state()

    @property
    def is_on(self) -> bool:
        """Return true if Hello World switch is active (mirrored state)."""
        # Mirror the switch state
        entities_manager = HelloWorldEntities(self.hass, None)
        switch_state = entities_manager.get_entity_state(
            self.device_id, "switch", "hello_world_switch"
        )
        return bool(switch_state)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        base_attrs = super().extra_state_attributes or {}
        return {
            **base_attrs,
            "mirrors_switch": True,
            "switch_entity": (
                f"switch.hello_world_switch_{self.device_id.replace(':', '_')}"
            ),
            "demo_feature": True,
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
