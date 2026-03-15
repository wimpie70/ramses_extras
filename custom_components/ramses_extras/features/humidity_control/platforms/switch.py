"""Humidity Control Switch Platform.

This module provides Home Assistant switch platform integration
for humidity control feature.
"""

import logging
from typing import TYPE_CHECKING, Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_ON
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from custom_components.ramses_extras.framework.base_classes.platform_entities import (
    ExtrasSwitchEntity,
)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: "HomeAssistant",
    config_entry: ConfigEntry,
    async_add_entities: "AddEntitiesCallback",
) -> None:
    """Set up humidity control switch platform."""
    from custom_components.ramses_extras.framework.helpers import platform

    # Use the framework's device filtering helper
    filtered_devices = platform.PlatformSetup.get_filtered_devices_for_feature(
        hass, "humidity_control", config_entry
    )

    if not filtered_devices:
        _LOGGER.info("No enabled devices for humidity control switch platform")
        return

    entities = []
    for device_id in filtered_devices:
        # Create humidity switch entities for this device
        try:
            device_entities = await create_humidity_switch(
                hass, device_id, config_entry
            )
            entities.extend(device_entities)
            _LOGGER.info(
                "Created %d humidity switch entities for device %s",
                len(device_entities),
                device_id,
            )
        except Exception as e:
            _LOGGER.error(
                "Failed to create humidity switch entities for device %s: %s",
                device_id,
                e,
            )

    _LOGGER.info("Total humidity switch entities created: %d", len(entities))
    if entities:
        async_add_entities(entities, True)
        _LOGGER.info("Humidity switch entities added to Home Assistant")


async def create_humidity_switch(
    hass: "HomeAssistant", device_id: str, config_entry: ConfigEntry | None = None
) -> list[ExtrasSwitchEntity]:
    """Create humidity switch for a device.

    Args:
        hass: Home Assistant instance
        device_id: Device identifier
        config_entry: Configuration entry

    Returns:
        List of switch entities
    """
    # Import entity configurations from registry
    from custom_components.ramses_extras.extras_registry import extras_registry

    from ..const import HUMIDITY_SWITCH_CONFIGS

    switch_list = []

    for switch_type, config in HUMIDITY_SWITCH_CONFIGS.items():
        if config.get("supported_device_types") and "HvacVentilator" in config.get(
            "supported_device_types", []
        ):
            switch_entity = HumidityControlSwitch(hass, device_id, switch_type, config)
            switch_list.append(switch_entity)

    return switch_list


class HumidityControlSwitch(ExtrasSwitchEntity, RestoreEntity):
    """Switch to toggle dehumidify mode."""

    def __init__(
        self,
        hass: "HomeAssistant",
        device_id: str,
        switch_type: str,
        config: dict[str, Any],
    ):
        # Initialize base entity with platform type
        super().__init__(hass, device_id, switch_type, config)

    async def async_added_to_hass(self) -> None:
        """Subscribe to Ramses RF device updates."""
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state is not None:
            self._is_on = last_state.state == STATE_ON
            self.async_write_ha_state()

    async def _handle_update(self, *args: Any, **kwargs: Any) -> None:
        """Handle updates from Ramses RF."""
        _LOGGER.debug("Device update for %s received", self._attr_name)
        self.async_write_ha_state()

    @property
    def is_on(self) -> bool:
        """Return true if dehumidify is active."""
        return self._is_on

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Activate dehumidify mode."""
        _LOGGER.info("Activating humidity balance mode for %s", self._attr_name)
        self._is_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Deactivate dehumidify mode."""
        _LOGGER.info("Deactivating humidity balance mode for %s", self._attr_name)
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
