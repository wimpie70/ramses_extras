"""Binary sensor entities for the default feature.

This module provides binary sensor entities for system-wide status monitoring,
including transport state for each fan device.
"""

import logging
from typing import TYPE_CHECKING

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from ....const import DOMAIN, register_feature_platform
from ....framework.helpers.device.core import (
    extract_device_id_as_string,
    find_ramses_device,
    get_device_type,
)
from ....framework.helpers.transport_monitor import get_transport_monitor

if TYPE_CHECKING:
    from typing import Any

_LOGGER = logging.getLogger(__name__)


class TransportStateBinarySensor(BinarySensorEntity):
    """Binary sensor for transport state of a Ramses device."""

    _attr_should_poll = False
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def __init__(self, hass: HomeAssistant, device_id: str) -> None:
        """Initialize the transport state binary sensor."""
        self.hass = hass
        self._device_id = device_id
        normalized_device_id = device_id.replace(":", "_")
        self.entity_id = f"binary_sensor.transport_state_{normalized_device_id}"
        self._attr_unique_id = f"{DOMAIN}_{normalized_device_id}_transport_state"
        self._attr_name = f"Transport State {normalized_device_id}"

        # Find the Ramses device for device info
        device = find_ramses_device(hass, device_id.replace("_", ":"))
        if device:
            device_name = (
                getattr(device, "friendly_name", None) or f"Device {device_id}"
            )
            self._attr_device_info = DeviceInfo(
                identifiers={(DOMAIN, device_id)},
                name=device_name,
                manufacturer="Ramses",
                model=(
                    device.__class__.__name__
                    if hasattr(device, "__class__")
                    else "Unknown"
                ),
            )
        else:
            self._attr_device_info = DeviceInfo(
                identifiers={(DOMAIN, device_id)},
                name=f"Device {device_id}",
                manufacturer="Ramses",
                model="Unknown",
            )

        # Get initial state
        transport_monitor = get_transport_monitor()
        self._attr_is_on = transport_monitor.is_transport_available

        # Register for transport state changes
        transport_monitor.register_callback(
            f"transport_sensor_{device_id}", self._on_transport_state_changed
        )

    def _on_transport_state_changed(self, available: bool) -> None:
        """Handle transport state changes."""
        if self._attr_is_on != available:
            self._attr_is_on = available
            _LOGGER.debug(
                "Transport state changed for %s: %s",
                self._device_id,
                "Online" if available else "Offline",
            )
            self.schedule_update_ha_state()

    @property
    def icon(self) -> str:
        """Return the icon to use in the frontend."""
        if self.is_on:
            return "mdi:network-strength-outline"
        return "mdi:network-strength-off-outline"

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return True  # This sensor should always be available

    async def async_will_remove_from_hass(self) -> None:
        """Clean up when entity is removed."""
        transport_monitor = get_transport_monitor()
        transport_monitor.unregister_callback(f"transport_sensor_{self._device_id}")
        await super().async_will_remove_from_hass()


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up transport state binary sensors."""
    devices = []
    for device in hass.data.get(DOMAIN, {}).get("devices", []):
        device_id = extract_device_id_as_string(device)
        if _device_has_fan(hass, device_id):
            devices.append(device_id)

    if not devices:
        _LOGGER.debug("No fan devices found for transport state sensors")
        return

    # Create binary sensors for each device
    entities = [TransportStateBinarySensor(hass, device_id) for device_id in devices]

    if entities:
        async_add_entities(entities, True)
        _LOGGER.info("Added %d transport state binary sensors", len(entities))


def _device_has_fan(hass: HomeAssistant, device_id: str) -> bool:
    """Check if a device has fan entities."""
    normalized_device_id = extract_device_id_as_string(device_id).replace("_", ":")
    device = find_ramses_device(hass, normalized_device_id)
    return get_device_type(device) == "HvacVentilator"


register_feature_platform("binary_sensor", "default", async_setup_entry)
