# Part of the Ramses Extra integration
# See https://github.com/wimpie70/ramses_extras for more information
#
"""Switch platform for Hello World Switch Card feature."""

import logging
from typing import TYPE_CHECKING, Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from custom_components.ramses_extras.framework.base_classes.platform_entities import (
    ExtrasSwitchEntity,
)

from ..const import HELLO_WORLD_SWITCH_CONFIGS
from ..entities import HelloWorldEntities

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: "HomeAssistant",
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Hello World switch platform."""
    from custom_components.ramses_extras.framework.helpers import platform

    await platform.PlatformSetup.async_setup_platform(
        platform="switch",
        hass=hass,
        config_entry=config_entry,
        async_add_entities=async_add_entities,
        entity_configs=HELLO_WORLD_SWITCH_CONFIGS,
        entity_factory=create_hello_world_switch,
    )


async def create_hello_world_switch(
    hass: "HomeAssistant", device_id: str, config_entry: ConfigEntry | None = None
) -> list[ExtrasSwitchEntity]:
    """Create Hello World switch for a device.

    Args:
        hass: Home Assistant instance
        device_id: Device identifier
        config_entry: Configuration entry

    Returns:
        List of switch entities
    """
    switch_list = []

    for switch_type, config in HELLO_WORLD_SWITCH_CONFIGS.items():
        supported_types = config.get("device_types", [])
        if supported_types and "HvacVentilator" in supported_types:
            switch_entity = HelloWorldSwitch(hass, device_id, switch_type, config)
            switch_list.append(switch_entity)

    return switch_list


class HelloWorldSwitch(ExtrasSwitchEntity):
    """Hello World Switch entity for demonstration purposes."""

    def __init__(
        self,
        hass: "HomeAssistant",
        device_id: str,
        switch_type: str,
        config: dict[str, Any],
    ):
        """Initialize Hello World switch entity."""
        super().__init__(hass, device_id, switch_type, config)

        # Initialize with state from entities manager
        entities_manager = HelloWorldEntities(hass, None)
        self._is_on = bool(
            entities_manager.get_entity_state(device_id, "switch", switch_type)
        )

    async def async_added_to_hass(self) -> None:
        """Subscribe to Ramses RF device updates."""
        await super().async_added_to_hass()
        _LOGGER.info("Hello World switch %s added to hass", self._attr_name)

    async def _handle_update(self, *args: Any, **kwargs: Any) -> None:
        """Handle updates from Ramses RF."""
        _LOGGER.debug(
            "Device update for Hello World switch %s received", self._attr_name
        )
        self.async_write_ha_state()

    @property
    def is_on(self) -> bool:
        """Return true if Hello World switch is active."""
        return self._is_on

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Activate Hello World switch."""
        _LOGGER.info("Activating Hello World switch for %s", self._attr_name)

        # Update state in entities manager
        entities_manager = HelloWorldEntities(self.hass, None)
        entities_manager.set_entity_state(
            self.device_id, "switch", "hello_world_switch", True
        )

        self._is_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Deactivate Hello World switch."""
        _LOGGER.info("Deactivating Hello World switch for %s", self._attr_name)

        # Update state in entities manager
        entities_manager = HelloWorldEntities(self.hass, None)
        entities_manager.set_entity_state(
            self.device_id, "switch", "hello_world_switch", False
        )

        self._is_on = False
        self.async_write_ha_state()

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        base_attrs = super().extra_state_attributes or {}
        return {
            **base_attrs,
            "hello_world_active": self.is_on,
            "demo_feature": True,
        }


# Register this platform with the global registry
from custom_components.ramses_extras.const import (  # noqa: E402
    register_feature_platform,  # noqa: E402
)

register_feature_platform("switch", "hello_world_card", async_setup_entry)

__all__ = [
    "HelloWorldSwitch",
    "async_setup_entry",
    "create_hello_world_switch",
]
