"""Platform reload service for dynamic device support."""

import logging
from typing import TYPE_CHECKING

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from ..const import DOMAIN

if TYPE_CHECKING:
    pass

_LOGGER = logging.getLogger(__name__)


class PlatformReloader:
    """Handle dynamic platform reloading when devices change."""

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry) -> None:
        """Initialize platform reloader."""
        self.hass = hass
        self.config_entry = config_entry
        self._setup_listeners()

    def _setup_listeners(self) -> None:
        """Set up event listeners for device changes."""
        # Listen for new devices
        async_dispatcher_connect(
            self.hass, f"{DOMAIN}_devices_added", self._handle_devices_added
        )

        # Listen for removed devices (manual removal from HA)
        async_dispatcher_connect(
            self.hass, f"{DOMAIN}_devices_removed", self._handle_devices_removed
        )

        # Listen for initial device discovery
        async_dispatcher_connect(
            self.hass, f"{DOMAIN}_devices_discovered", self._handle_devices_discovered
        )

    async def _handle_devices_added(self, device_ids: list[str]) -> None:
        """Handle newly discovered devices."""
        _LOGGER.info(f"Handling newly discovered devices: {device_ids}")

        try:
            # Update the device list in hass.data
            current_devices = self.hass.data.get(DOMAIN, {}).get("devices", [])
            updated_devices = list(set(current_devices + device_ids))

            self.hass.data[DOMAIN]["devices"] = updated_devices
            _LOGGER.info(f"Updated device list: {updated_devices}")

            # Reload platforms to include new devices
            await self._reload_platforms()

        except Exception as e:
            _LOGGER.error(f"Error handling new devices: {e}")

    async def _handle_devices_removed(self, device_ids: list[str]) -> None:
        """Handle manually removed devices."""
        _LOGGER.info(f"Handling removed devices: {device_ids}")

        try:
            # Update the device list in hass.data
            current_devices = self.hass.data.get(DOMAIN, {}).get("devices", [])
            updated_devices = [d for d in current_devices if d not in device_ids]

            self.hass.data[DOMAIN]["devices"] = updated_devices
            _LOGGER.info(f"Updated device list: {updated_devices}")

            # Clean up entities for removed devices
            await self._cleanup_removed_devices(device_ids)

            # Reload platforms to reflect changes
            await self._reload_platforms()

        except Exception as e:
            _LOGGER.error(f"Error handling removed devices: {e}")

    async def _handle_devices_discovered(self, device_ids: list[str]) -> None:
        """Handle initial device discovery."""
        _LOGGER.info(f"Initial device discovery: {device_ids}")

        # Update device list
        self.hass.data.setdefault(DOMAIN, {})["devices"] = device_ids

    async def _reload_platforms(self) -> None:
        """Reload all platforms with updated device list."""
        _LOGGER.info("Reloading platforms for updated device list")

        platforms_to_reload = ["sensor", "number", "switch", "binary_sensor"]

        for platform_name in platforms_to_reload:
            try:
                _LOGGER.debug(f"Reloading platform: {platform_name}")

                # Reload the platform
                await self.hass.config_entries.async_reload_platform_entry(
                    self.config_entry, platform_name
                )

                _LOGGER.info(f"Successfully reloaded platform: {platform_name}")

            except Exception as e:
                _LOGGER.error(f"Failed to reload platform {platform_name}: {e}")

    async def _cleanup_removed_devices(self, device_ids: list[str]) -> None:
        """Clean up entities for removed devices."""
        _LOGGER.info(f"Cleaning up entities for removed devices: {device_ids}")

        try:
            # Remove entities from entity registry
            from homeassistant.helpers import entity_registry

            entity_reg = entity_registry.async_get(self.hass)

            # Find entities for removed devices
            entities_to_remove = []
            for entity_id, entity_entry in entity_reg.entities.items():
                if entity_entry.platform != DOMAIN:
                    continue

                # Check if entity belongs to removed device
                for device_id in device_ids:
                    device_pattern = f"_{device_id}_"
                    pattern_in_entity = device_pattern in entity_id
                    ends_with_device = entity_id.endswith(f"_{device_id}")
                    if pattern_in_entity or ends_with_device:
                        entities_to_remove.append(entity_id)
                        break

            # Remove the entities
            for entity_id in entities_to_remove:
                try:
                    entity_reg.async_remove(entity_id)
                    _LOGGER.info(f"Removed entity for removed device: {entity_id}")
                except Exception as e:
                    _LOGGER.warning(f"Failed to remove entity {entity_id}: {e}")

        except Exception as e:
            _LOGGER.error(f"Error cleaning up removed devices: {e}")
