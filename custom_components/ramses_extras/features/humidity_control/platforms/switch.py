"""Humidity Control Switch Platform.

This module provides Home Assistant switch platform integration
for humidity control feature.
"""

import logging
from typing import TYPE_CHECKING, Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from custom_components.ramses_extras.framework.base_classes.base_entity import (
    ExtrasBaseEntity,
)
from custom_components.ramses_extras.framework.helpers.entity_core import EntityHelpers

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: "HomeAssistant",
    config_entry: ConfigEntry,
    async_add_entities: "AddEntitiesCallback",
) -> None:
    """Set up humidity control switch platform."""
    _LOGGER.info("Setting up humidity control switches")

    # Get devices from Home Assistant data
    devices = hass.data.get("ramses_extras", {}).get("devices", [])
    _LOGGER.info(
        f"Humidity control switch platform: found {len(devices)} devices: {devices}"
    )

    switches = []
    for device_id in devices:
        # Create humidity-specific switches
        device_switches = await create_humidity_switch(hass, device_id, config_entry)
        switches.extend(device_switches)
        _LOGGER.info(f"Created {len(device_switches)} switches for device {device_id}")

    _LOGGER.info(f"Total switches created: {len(switches)}")
    async_add_entities(switches, True)


async def create_humidity_switch(
    hass: "HomeAssistant", device_id: str, config_entry: ConfigEntry | None = None
) -> list[SwitchEntity]:
    """Create humidity switches for a device.

    Args:
        hass: Home Assistant instance
        device_id: Device identifier
        config_entry: Configuration entry

    Returns:
        List of switch entities
    """
    # Import entity configurations from management layer
    from ..entities import HumidityEntities

    entity_manager = HumidityEntities(hass, config_entry)
    switches = []

    for switch_type in ["dehumidify"]:
        config = entity_manager.get_entity_config("switches", switch_type)
        if config:
            switch = HumidityControlSwitch(hass, device_id, switch_type, config)
            switches.append(switch)

    return switches


class HumidityControlSwitch(SwitchEntity, ExtrasBaseEntity):
    """Switch to toggle dehumidify mode."""

    def __init__(
        self,
        hass: "HomeAssistant",
        device_id: str,
        switch_type: str,
        config: dict[str, Any],
    ):
        # Initialize base entity
        ExtrasBaseEntity.__init__(self, hass, device_id, switch_type, config)

        # Set switch-specific attributes
        self._switch_type = switch_type

        # Convert device_id to underscore format for entity generation
        device_id_underscore = device_id.replace(":", "_")

        # Generate proper entity name using template system
        entity_name = EntityHelpers.generate_entity_name_from_template(
            "switch", switch_type, device_id_underscore
        )

        if entity_name:
            # Set entity name and unique_id using proper template
            name_template = (
                config.get("name_template", "Dehumidify {device_id}")
                or "Dehumidify {device_id}"
            )
            self._attr_name = name_template.format(device_id=device_id_underscore)
            self._attr_unique_id = entity_name.replace("switch.", "")
        else:
            # Fallback to hardcoded format (legacy)
            name_template = (
                config.get("name_template", "Dehumidify {device_id}")
                or "Dehumidify {device_id}"
            )
            self._attr_name = name_template.format(device_id=device_id_underscore)
            self._attr_unique_id = f"dehumidify_{device_id_underscore}"

        self._is_on = False

    @property
    def name(self) -> str:
        """Return the name of the entity."""
        return self._attr_name or "Dehumidify"

    async def async_added_to_hass(self) -> None:
        """Subscribe to Ramses RF device updates."""
        # Call base class method first
        await super().async_added_to_hass()
        _LOGGER.info("switch added to hass")

    async def _handle_update(self, *args: Any, **kwargs: Any) -> None:
        """Handle updates from Ramses RF."""
        _LOGGER.debug("Device update for %s received", self._attr_name)
        self.async_write_ha_state()

    @property
    def is_on(self) -> bool:
        """Return true if dehumidify is active."""
        # For now, return stored state since we don't have access to device object
        return self._is_on

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Activate dehumidify mode."""
        _LOGGER.info("Activating dehumidify mode for %s", self._attr_name)
        self._is_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Deactivate dehumidify mode."""
        _LOGGER.info("Deactivating dehumidify mode for %s", self._attr_name)
        self._is_on = False
        self.async_write_ha_state()

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        base_attrs = super().extra_state_attributes or {}
        return {**base_attrs, "dehumidifying": self.is_on}


# Register this platform with the global registry
from custom_components.ramses_extras.const import (  # noqa: E402
    register_feature_platform,  # noqa: E402
)

register_feature_platform("switch", "humidity_control", async_setup_entry)

__all__ = [
    "HumidityControlSwitch",
    "async_setup_entry",
    "create_humidity_switch",
]
