"""Binary sensor entities for the default feature.

This module provides binary sensor entities for system-wide status monitoring,
including transport state for each fan device.
"""

import logging
from typing import TYPE_CHECKING, Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from ....const import DOMAIN, register_feature_platform
from ....framework.base_classes.platform_entities import ExtrasBinarySensorEntity
from ....framework.helpers.device.core import (
    extract_device_id_as_string,
    find_ramses_device,
    get_device_type,
)
from ....framework.helpers.transport_monitor import get_transport_monitor

if TYPE_CHECKING:
    from typing import Any

_LOGGER = logging.getLogger(__name__)


def _legacy_transport_entity_id(device_id: str) -> str:
    normalized_device_id = device_id.replace(":", "_")
    return f"binary_sensor.{normalized_device_id}_transport_state"


def _transport_entity_id(device_id: str) -> str:
    normalized_device_id = device_id.replace(":", "_")
    return f"binary_sensor.transport_state_{normalized_device_id}"


def _migrate_legacy_transport_entity_id(hass: HomeAssistant, device_id: str) -> None:
    registry = entity_registry.async_get(hass)
    legacy_entity_id = _legacy_transport_entity_id(device_id)
    new_entity_id = _transport_entity_id(device_id)

    if registry.async_get(new_entity_id) is not None:
        return

    if registry.async_get(legacy_entity_id) is None:
        return

    try:
        registry.async_update_entity(
            legacy_entity_id,
            new_entity_id=new_entity_id,
        )
        _LOGGER.info(
            "Migrated legacy transport entity ID from %s to %s",
            legacy_entity_id,
            new_entity_id,
        )
    except ValueError as err:
        _LOGGER.warning(
            "Failed to migrate transport entity ID from %s to %s: %s",
            legacy_entity_id,
            new_entity_id,
            err,
        )


async def _get_ramses_cc_coordinator(hass: HomeAssistant) -> Any | None:
    try:
        ramses_cc_data = hass.data.get("ramses_cc", {})
        for coordinator_instance in ramses_cc_data.values():
            if hasattr(coordinator_instance, "client"):
                return coordinator_instance
    except Exception as err:
        _LOGGER.debug("Could not get ramses_cc coordinator: %s", err)

    return None


async def _start_transport_monitoring(hass: HomeAssistant) -> None:
    coordinator = await _get_ramses_cc_coordinator(hass)
    if not coordinator or not getattr(coordinator, "client", None):
        _LOGGER.debug("ramses_cc coordinator not available for transport monitoring")
        return

    transport_monitor = get_transport_monitor()
    await transport_monitor.start_monitoring(coordinator, hass)
    await transport_monitor.force_check()


class TransportStateBinarySensor(ExtrasBinarySensorEntity):
    """Binary sensor for transport state of a Ramses device."""

    _attr_should_poll = False
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def __init__(self, hass: HomeAssistant, device_id: str) -> None:
        """Initialize the transport state binary sensor."""
        config = {
            "entity_template": "transport_state_{device_id}",
            "name_template": "Transport State {device_id}",
            "device_class": BinarySensorDeviceClass.CONNECTIVITY,
        }
        super().__init__(hass, device_id, "transport_state", config)

        self.hass = hass
        self._device_id = device_id
        self._attr_entity_category = EntityCategory.DIAGNOSTIC

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

        # Initialize as offline - will be set online when device replies
        self._is_on = False

        # Register for transport state changes
        transport_monitor = get_transport_monitor()
        transport_monitor.register_callback(
            f"transport_sensor_{device_id}",
            self._on_transport_state_changed,
            device_id,
        )

    def _on_transport_state_changed(self, available: bool) -> None:
        """Handle transport state changes."""
        self._is_on = available
        if available:
            _LOGGER.debug("Transport state for %s: Online", self._device_id)
        else:
            _LOGGER.warning("Transport state for %s: Offline", self._device_id)
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
    try:
        devices_data = hass.data.get(DOMAIN, {}).get("devices", [])
        # Ensure devices_data is a list, not an async generator
        if hasattr(devices_data, "__aiter__"):
            devices_data = [device async for device in devices_data]
        elif not isinstance(devices_data, list):
            devices_data = list(devices_data)

        devices = []
        for device in devices_data:
            try:
                device_id = extract_device_id_as_string(device)
                if await _device_has_fan(hass, device_id):
                    devices.append(device_id)
            except Exception as err:
                _LOGGER.debug("Error checking device %s for fan: %s", device, err)
                continue

        if not devices:
            _LOGGER.debug("No fan devices found for transport state sensors")
            return

        for device_id in devices:
            _migrate_legacy_transport_entity_id(hass, device_id)

        await _start_transport_monitoring(hass)

        # Create binary sensors for each device
        entities = [
            TransportStateBinarySensor(hass, device_id) for device_id in devices
        ]

        if entities:
            async_add_entities(entities, True)
            _LOGGER.info("Added %d transport state binary sensors", len(entities))

    except Exception as err:
        _LOGGER.error("Error setting up transport state binary sensors: %s", err)


async def _device_has_fan(hass: HomeAssistant, device_id: str) -> bool:
    """Check if a device has fan entities."""
    try:
        normalized_device_id = extract_device_id_as_string(device_id).replace("_", ":")
        device = find_ramses_device(hass, normalized_device_id)
        return get_device_type(device) == "HvacVentilator"
    except Exception as err:
        _LOGGER.debug("Error checking if device %s has fan: %s", device_id, err)
        return False


register_feature_platform("binary_sensor", "default", async_setup_entry)
