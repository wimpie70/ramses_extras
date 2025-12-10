"""Platform reloader for Ramses Extras integration.

This module provides the PlatformReloader class that handles reloading
Home Assistant platforms when entities need to be created or removed
as part of configuration changes.

DEPRECATED: This complex PlatformReloader has been replaced by the simpler
direct_platform_setup.py approach. This file is kept for backward
compatibility but should not be used for new development.
"""

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from ..const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class PlatformReloader:
    """Manages platform reloading for Ramses Extras integration.

    This class handles the reloading of Home Assistant platforms when
    entities need to be created or removed after configuration changes.
    It provides a centralized way to trigger platform reloads that
    will cause the actual entity creation/deletion in Home Assistant.
    """

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry) -> None:
        """Initialize PlatformReloader.

        Args:
            hass: Home Assistant instance
            config_entry: The Ramses Extras config entry
        """
        self.hass = hass
        self.config_entry = config_entry

        # Set up event listeners for device changes
        self._setup_listeners()

    def _setup_listeners(self) -> None:
        """Set up event listeners for device discovery and changes."""
        try:
            # Listen for device discovery events
            from homeassistant.helpers.dispatcher import async_dispatcher_connect

            # Connect to device discovery signals
            async_dispatcher_connect(
                self.hass,
                "ramses_extras_devices_discovered",
                self._handle_devices_discovered,
            )

            async_dispatcher_connect(
                self.hass,
                "ramses_extras_devices_added",
                self._handle_devices_added,
            )

            async_dispatcher_connect(
                self.hass,
                "ramses_extras_devices_removed",
                self._handle_devices_removed,
            )

            _LOGGER.debug("PlatformReloader: Event listeners set up successfully")

        except Exception as e:
            _LOGGER.error(f"PlatformReloader: Failed to set up event listeners: {e}")

    async def _handle_devices_discovered(self, device_ids: list[str]) -> None:
        """Handle initial device discovery.

        Args:
            device_ids: List of discovered device IDs
        """
        _LOGGER.info(
            f"PlatformReloader: Handling discovery of {len(device_ids)} devices"
        )

        # Update device list in hass data
        if DOMAIN not in self.hass.data:
            self.hass.data[DOMAIN] = {}
        self.hass.data[DOMAIN]["devices"] = device_ids

        # Reload platforms to create entities for discovered devices
        await self._reload_platforms()

    async def _handle_devices_added(self, device_ids: list[str]) -> None:
        """Handle new devices added.

        Args:
            device_ids: List of added device IDs
        """
        _LOGGER.info(
            f"PlatformReloader: Handling addition of {len(device_ids)} devices"
        )

        # Only process if there are actually devices to add
        if not device_ids:
            _LOGGER.debug("PlatformReloader: No devices to add, skipping")
            return

        # Update device list
        if DOMAIN in self.hass.data and "devices" in self.hass.data[DOMAIN]:
            current_devices = self.hass.data[DOMAIN]["devices"]
            for device_id in device_ids:
                if device_id not in current_devices:
                    current_devices.append(device_id)

        # Reload platforms to create entities for new devices
        await self._reload_platforms()

    async def _handle_devices_removed(self, device_ids: list[str]) -> None:
        """Handle devices removed.

        Args:
            device_ids: List of removed device IDs
        """
        _LOGGER.info(f"PlatformReloader: Handling removal of {len(device_ids)} devices")

        # Only process if there are actually devices to remove
        if not device_ids:
            _LOGGER.debug("PlatformReloader: No devices to remove, skipping")
            return

        # Update device list
        if DOMAIN in self.hass.data and "devices" in self.hass.data[DOMAIN]:
            current_devices = self.hass.data[DOMAIN]["devices"]
            for device_id in device_ids:
                if device_id in current_devices:
                    current_devices.remove(device_id)

        # Clean up entities for removed devices
        await self._cleanup_removed_devices(device_ids)

        # Reload platforms
        await self._reload_platforms()

    async def _cleanup_removed_devices(self, device_ids: list[str]) -> None:
        """Clean up entities for removed devices.

        Args:
            device_ids: List of removed device IDs
        """
        _LOGGER.info(
            f"PlatformReloader: Cleaning up entities for "
            f"{len(device_ids)} removed devices"
        )

        try:
            from homeassistant.helpers import entity_registry

            entity_registry_instance = entity_registry.async_get(self.hass)

            # Find and remove entities that belong to the removed devices
            entities_to_remove = []
            for entity in entity_registry_instance.entities.values():
                if (
                    entity.platform == DOMAIN
                    and hasattr(entity, "device_id")
                    and entity.device_id in device_ids
                ):
                    entities_to_remove.append(entity.entity_id)

            # Remove the entities
            for entity_id in entities_to_remove:
                try:
                    entity_registry_instance.async_remove(entity_id)
                    _LOGGER.debug(f"PlatformReloader: Removed entity {entity_id}")
                except Exception as e:
                    _LOGGER.warning(
                        f"PlatformReloader: Failed to remove entity {entity_id}: {e}"
                    )

            _LOGGER.info(
                f"PlatformReloader: Cleaned up {len(entities_to_remove)} entities"
            )

        except Exception as e:
            _LOGGER.error(
                f"PlatformReloader: Error during cleanup of removed devices: {e}"
            )

    async def _reload_platforms(self) -> None:
        """Reload all platforms that can create entities.

        This method triggers the reloading of all platforms that might
        create entities, ensuring that new entities are actually created
        in Home Assistant after configuration changes.
        """
        _LOGGER.info("PlatformReloader: Reloading platforms for entity creation")

        try:
            # Reload each platform individually using async_reload_platform_entry
            platforms_to_reload = ["sensor", "number", "switch", "binary_sensor"]

            for platform in platforms_to_reload:
                await self.hass.config_entries.async_reload_platform_entry(
                    self.config_entry, platform
                )

            _LOGGER.info(
                "PlatformReloader: ✅ Successfully reloaded platforms: %s",
                platforms_to_reload,
            )

            # Additionally, directly trigger sensor platform setup for new devices
            # This ensures entities are actually created for newly discovered devices
            await self._trigger_sensor_platform_setup_for_new_devices()

        except Exception as e:
            _LOGGER.error(f"PlatformReloader: ❌ Error during platform reload: {e}")
            # Don't re-raise - platform reload failure shouldn't break the flow

    async def _trigger_sensor_platform_setup_for_new_devices(self) -> None:
        """Directly trigger sensor platform setup for new devices.

        This method ensures that sensor entities are actually created for
        newly discovered devices by calling the sensor platform setup functions
        directly, rather than relying solely on platform reloading.
        """
        _LOGGER.info(
            "PlatformReloader: Triggering direct sensor platform setup for new devices"
        )

        try:
            # Import the sensor platform setup function
            from custom_components.ramses_extras.sensor import async_setup_entry

            # Get the platform registry to access feature platform setups
            platform_registry = self.hass.data.get("ramses_extras", {}).get(
                "PLATFORM_REGISTRY", {}
            )
            sensor_platforms = platform_registry.get("sensor", {})

            _LOGGER.debug(
                f"PlatformReloader: Found {len(sensor_platforms)} "
                f"sensor platform setups"
            )

            # Call each sensor platform setup function
            for feature_name, setup_func in sensor_platforms.items():
                try:
                    _LOGGER.debug(
                        f"PlatformReloader: Calling sensor platform setup for feature: "
                        f"{feature_name}"
                    )
                    await setup_func(
                        self.hass, self.config_entry, lambda entities: None
                    )
                    _LOGGER.info(
                        f"PlatformReloader: ✅ Successfully triggered sensor platform "
                        f"setup for {feature_name}"
                    )
                except Exception as e:
                    _LOGGER.warning(
                        f"PlatformReloader: ⚠️ Failed to trigger sensor platform setup "
                        f"for {feature_name}: {e}"
                    )

            _LOGGER.info(
                "PlatformReloader: ✅ Direct sensor platform setup completed "
                "for all features"
            )

        except ImportError as e:
            _LOGGER.warning(f"PlatformReloader: Could not import sensor platform: {e}")
        except Exception as e:
            _LOGGER.error(
                f"PlatformReloader: ❌ Error during direct sensor platform setup: {e}"
            )

    async def async_reload_platforms_for_entity_creation(self) -> None:
        """Public method to reload platforms for entity creation.

        This is the main entry point for triggering platform reloads
        when entities need to be created after configuration changes.
        """
        _LOGGER.info("PlatformReloader: Triggering platform reload for entity creation")
        await self._reload_platforms()


# Export PlatformReloader class
__all__ = ["PlatformReloader"]
