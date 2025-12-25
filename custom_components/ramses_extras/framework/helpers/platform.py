"""Enhanced platform setup framework for Ramses Extras.

This module provides reusable platform setup patterns that extract common
functionality from platform implementations across all features.

Key components:
- PlatformSetup: Generic platform setup utilities
- Entity factory patterns for consistent entity creation
- Device filtering and validation
- Configuration-driven entity generation
"""

import logging
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Awaitable, Callable, cast

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from custom_components.ramses_extras.framework.helpers.device.core import (
    extract_device_id_as_string,
)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)


def _get_platform_key(platform: str) -> str:
    """Convert platform name to the correct entity key in the configuration.

    Args:
        platform: Platform name (sensor, switch, binary_sensor, number)

    Returns:
        Correct key for required_entities configuration
    """
    # Convert platform name to plural form for configuration lookup
    platform_to_key = {
        "sensor": "sensor",
        "switch": "switch",
        "binary_sensor": "binary_sensor",
        "number": "number",
    }
    return platform_to_key.get(platform, f"{platform}s")


def _get_devices_ready_for_entities(hass: "HomeAssistant") -> list[str]:
    """Get devices that are ready for entity creation.

    Args:
        hass: Home Assistant instance

    Returns:
        List of device IDs ready for entities
    """
    return cast(list[str], hass.data.get("ramses_extras", {}).get("devices", []))


def get_enabled_features(
    hass: "HomeAssistant", config_entry: ConfigEntry
) -> dict[str, bool]:
    """Get enabled features from config entry.

    Args:
        hass: Home Assistant instance
        config_entry: Configuration entry

    Returns:
        Dictionary of feature names to enabled status
    """
    if not config_entry:
        return {}
    data = config_entry.data or {}
    enabled_features = data.get("enabled_features", {})
    return dict(enabled_features) if isinstance(enabled_features, dict) else {}


class PlatformSetup:
    """Enhanced platform setup utilities for all features.

    This class provides reusable platform setup patterns that extract common
    functionality from platform implementations, reducing code duplication
    and ensuring consistency across all features.
    """

    @staticmethod
    async def async_create_and_add_platform_entities(
        platform: str,
        hass: "HomeAssistant",
        config_entry: ConfigEntry,
        async_add_entities: AddEntitiesCallback,
        entity_configs: dict[str, Any],
        entity_factory: Callable[
            ["HomeAssistant", str, dict[str, Any], ConfigEntry | None],
            Awaitable[list[Entity]],
        ],
        store_entities_for_automation: bool = False,
        feature_id: str | None = None,
    ) -> None:
        """Create and add entities for a platform.

        This method extracts the common platform setup pattern used across
        all platform files, providing a reusable foundation for new features.
        It creates entities using the provided factory and adds them to Home Assistant.

        Args:
            platform: Platform type (sensor, switch, binary_sensor, number)
            hass: Home Assistant instance
            config_entry: Configuration entry
            async_add_entities: Add entities callback
            entity_configs: Dictionary of entity configurations
            entity_factory: Factory function to create entities
            store_entities_for_automation: Whether to store entities in hass.data
                for automation access (default: False)
            feature_id: Feature identifier for device filtering (optional)
        """
        _LOGGER.debug("Setting up %s platform with generic setup", platform)

        # Get devices ready for entities
        if feature_id and feature_id != "default":
            devices = PlatformSetup.get_filtered_devices_for_feature(
                hass=hass,
                feature_id=feature_id,
                config_entry=config_entry,
                devices=_get_devices_ready_for_entities(hass),
            )
            _LOGGER.debug(
                "%s platform: filtered %d devices for feature %s",
                platform,
                len(devices),
                feature_id,
            )
        else:
            devices = _get_devices_ready_for_entities(hass)
            _LOGGER.debug(
                "%s platform: found %d devices: %s", platform, len(devices), devices
            )

        if not devices:
            _LOGGER.warning("No devices found for %s platform", platform)
            return

        entities = []
        for device_id in devices:
            try:
                # Create entities for device using factory
                device_entities = await entity_factory(
                    hass, device_id, entity_configs, config_entry
                )
                entities.extend(device_entities)
                _LOGGER.debug(
                    "Created %d %s entities for device %s",
                    len(device_entities),
                    platform,
                    device_id,
                )
            except Exception as e:
                _LOGGER.error(
                    "Failed to create %s entities for device %s: %s",
                    platform,
                    device_id,
                    e,
                )

        _LOGGER.info("Total %s entities created: %d", platform, len(entities))
        if entities:
            async_add_entities(entities, True)
            _LOGGER.info("%s entities added to Home Assistant", platform)

            # Optionally store entities for automation access
            if store_entities_for_automation:
                PlatformSetup._store_entities_for_automation(hass, entities)

    @staticmethod
    def _is_entity_supported_for_device(device_id: str, config: dict[str, Any]) -> bool:
        """Check if an entity type is supported for a device.

        Args:
            device_id: Device identifier
            config: Entity configuration

        Returns:
            True if entity is supported for the device
        """
        supported_device_types = config.get("supported_device_types", [])

        # If no specific device types are required, entity is supported
        if not supported_device_types:
            return True

        # Check if device matches any of the supported types
        # This is a simple implementation - can be enhanced with actual
        # device type detection from device metadata
        for supported_type in supported_device_types:
            if supported_type in device_id:
                return True

        return False

    @staticmethod
    def filter_configs_by_device(
        entity_configs: dict[str, Any], device_id: str
    ) -> dict[str, Any]:
        """Filter entity configurations to only include supported entities for a device.

        Args:
            entity_configs: All entity configurations
            device_id: Device identifier

        Returns:
            Filtered configuration dictionary
        """
        filtered_configs = {}

        for entity_type, config in entity_configs.items():
            if PlatformSetup._is_entity_supported_for_device(device_id, config):
                filtered_configs[entity_type] = config

        return filtered_configs

    @staticmethod
    def get_platform_key(platform: str) -> str:
        """Convert platform name to the correct entity key in the configuration.

        This method provides a consistent way to map platform names to
        configuration keys across the framework.

        Args:
            platform: Platform name (sensor, switch, binary_sensor, number)

        Returns:
            Correct key for configuration lookup
        """
        # Convert platform name to plural form for configuration lookup
        platform_to_key = {
            "sensor": "sensor",
            "switch": "switch",
            "binary_sensor": "binary_sensor",
            "number": "number",
        }
        return platform_to_key.get(platform, f"{platform}s")

    @staticmethod
    async def setup_feature_platforms(
        hass: "HomeAssistant",
        config_entry: ConfigEntry,
        feature_id: str,
        platform_mappings: dict[str, dict[str, Any]],
        async_add_entities_callbacks: dict[str, AddEntitiesCallback],
    ) -> None:
        """Setup all platforms for a feature.

        This method provides a comprehensive way to setup multiple platforms
        for a feature with consistent error handling and logging.

        Args:
            hass: Home Assistant instance
            config_entry: Configuration entry
            feature_id: Feature identifier
            platform_mappings: Mapping of platform names to entity configurations
            async_add_entities_callbacks: Mapping of platform names to add callbacks
        """
        _LOGGER.info("Setting up all platforms for feature: %s", feature_id)

        for platform, entity_configs in platform_mappings.items():
            if platform not in async_add_entities_callbacks:
                _LOGGER.warning(
                    "No async_add_entities callback found for platform %s "
                    "in feature %s",
                    platform,
                    feature_id,
                )
                continue

            try:
                await PlatformSetup.async_create_and_add_platform_entities(
                    platform=platform,
                    hass=hass,
                    config_entry=config_entry,
                    async_add_entities=async_add_entities_callbacks[platform],
                    entity_configs=entity_configs,
                    entity_factory=PlatformSetup._default_entity_factory,
                )
            except Exception as e:
                _LOGGER.error(
                    "Failed to setup %s platform for feature %s: %s",
                    platform,
                    feature_id,
                    e,
                )

    @staticmethod
    def _store_entities_for_automation(
        hass: "HomeAssistant", entities: list[Entity]
    ) -> None:
        """Store entities in hass.data for automation access.

        This method stores created entities in the hass.data structure so that
        automation code can access them directly by entity_id.

        Args:
            hass: Home Assistant instance
            entities: List of entities to store
        """
        if "ramses_extras" not in hass.data:
            hass.data["ramses_extras"] = {}
        if "entities" not in hass.data["ramses_extras"]:
            hass.data["ramses_extras"]["entities"] = {}

        stored_count = 0
        for entity in entities:
            hass.data["ramses_extras"]["entities"][entity.entity_id] = entity
            stored_count += 1

        _LOGGER.debug(
            "Stored %d entities for automation access in hass.data", stored_count
        )

    @staticmethod
    async def _default_entity_factory(
        hass: "HomeAssistant",
        device_id: str,
        entity_configs: dict[str, Any],
        config_entry: ConfigEntry | None = None,
    ) -> list[Entity]:
        """Default entity factory for basic entity creation.

        This is a placeholder factory that features can override with
        their specific entity creation logic.

        Args:
            hass: Home Assistant instance
            device_id: Device identifier
            config: Entity configuration

        Returns:
            Created entity or None
        """
        # This should be overridden by features with their specific logic
        _LOGGER.warning(
            "Default entity factory called - feature should provide custom factory. "
            "Device: %s, ConfigEntry: %s",
            device_id,
            config_entry,
        )
        return []

    @staticmethod
    def get_filtered_devices_for_feature(
        hass: "HomeAssistant",
        feature_id: str,
        config_entry: ConfigEntry,
        devices: list[str] | None = None,
    ) -> list[str]:
        """Get devices filtered by feature enablement.

        Args:
            hass: Home Assistant instance
            feature_id: Feature identifier for filtering
            config_entry: Configuration entry for matrix state

        Returns:
            List of device IDs enabled for the specified feature
        """
        # Get all devices
        device_ids = (
            devices
            if devices is not None
            else hass.data.get("ramses_extras", {}).get("devices", [])
        )

        # Use the config entry as the source of truth for per-device enablement.
        # Avoid depending on an in-memory entity_manager, which can be stale across
        # reloads/option changes.
        data = getattr(config_entry, "data", {}) or {}
        matrix_state = (
            data.get("device_feature_matrix", {}) if isinstance(data, Mapping) else {}
        )

        # If there is no per-device matrix configured, fall back to global enablement.
        # Otherwise we risk filtering out *all* devices and creating no entities.
        matrix_is_empty = not isinstance(matrix_state, Mapping) or not matrix_state

        config_data = getattr(config_entry, "data", {}) or {}
        config_opts = getattr(config_entry, "options", {}) or {}
        enabled_features = {}
        if isinstance(config_data, Mapping):
            enabled_features = config_data.get("enabled_features", {})
        if (not enabled_features) and isinstance(config_opts, Mapping):
            enabled_features = config_opts.get("enabled_features", {})

        feature_globally_enabled = feature_id == "default" or (
            isinstance(enabled_features, Mapping)
            and enabled_features.get(feature_id) is True
        )

        if matrix_is_empty and feature_globally_enabled:
            return [extract_device_id_as_string(device_id) for device_id in device_ids]

        # Filter devices to only include those enabled for this feature.
        # We accept both `32:153289` and `32_153289` forms for robustness.
        filtered_devices = []
        for device_id in device_ids:
            device_id_str = extract_device_id_as_string(device_id)
            if not isinstance(matrix_state, Mapping):
                continue

            candidates = {
                device_id_str,
                device_id_str.replace(":", "_"),
                device_id_str.replace("_", ":"),
            }
            is_enabled = False
            for candidate in candidates:
                features_for_device = matrix_state.get(candidate)
                if isinstance(features_for_device, Mapping) and (
                    features_for_device.get(feature_id) is True
                ):
                    is_enabled = True
                    break
            if is_enabled:
                filtered_devices.append(device_id_str)
                continue

            _LOGGER.debug(
                "Skipping disabled device for %s feature: %s",
                feature_id,
                device_id_str,
            )

        _LOGGER.info(
            "Filtered %d devices to %d enabled devices for feature %s",
            len(device_ids),
            len(filtered_devices),
            feature_id,
        )

        return filtered_devices
