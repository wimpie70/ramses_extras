"""Enhanced platform setup framework for Ramses Extras.

This module provides reusable platform setup patterns that extract common
functionality from platform implementations across all features.

Key components:
- PlatformSetup: Generic platform setup utilities
- Entity factory patterns for consistent entity creation
- Device filtering and validation
- Configuration-driven entity generation
"""

import importlib
import logging
from typing import TYPE_CHECKING, Any, Awaitable, Callable, Optional, cast

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


def calculate_required_entities(
    platform: str,
    enabled_features: dict[str, bool],
    devices: list[str],
    hass: "HomeAssistant",
) -> list[str]:
    """Calculate required entities for a platform based on device mappings.

    Args:
        platform: Platform type (sensor, switch, etc.)
        enabled_features: Dictionary of enabled features
        devices: List of device IDs
        hass: Home Assistant instance

    Returns:
        List of required entity types
    """
    required_entities = []

    # Get device mappings from extras_registry
    from custom_components.ramses_extras.extras_registry import extras_registry
    from custom_components.ramses_extras.framework.helpers.device.core import (
        find_ramses_device,
        get_device_type,
    )

    platform_key = _get_platform_key(platform)
    device_mappings = extras_registry.get_all_device_mappings()

    # For each device, check what entities it should have
    for device_id in devices:
        device = find_ramses_device(hass, device_id)
        if not device:
            continue

        device_type = get_device_type(device)
        if device_type not in device_mappings:
            continue

        entity_mapping = device_mappings[device_type]
        entities_for_platform = entity_mapping.get(platform_key, [])

        # Add entities that aren't already in the list
        for entity in entities_for_platform:
            if entity not in required_entities:
                required_entities.append(entity)

    _LOGGER.info(
        f"Platform {platform}: calculated {len(required_entities)} "
        f"required entities for {len(devices)} devices: {required_entities}"
    )

    # Debug: Log device mapping information
    if platform in ["switch", "binary_sensor", "number", "sensor"]:
        _LOGGER.info(f"Debug: {platform} platform analysis from device mappings:")
        for device_id in devices:
            device = find_ramses_device(hass, device_id)
            if device:
                device_type = get_device_type(device)
                if device_type in device_mappings:
                    entity_mapping = device_mappings[device_type]
                    entities = entity_mapping.get(platform_key, [])
                    _LOGGER.info(f"  Device {device_id} ({device_type}): {entities}")

    return required_entities


async def async_setup_platform(
    platform: str,
    hass: "HomeAssistant",
    config_entry: ConfigEntry,
    async_add_entities: Any,
) -> None:
    """Generic platform setup function.

    Args:
        hass: Home Assistant instance
        config_entry: Configuration entry
        platform: Platform type (sensor, switch, etc.)
        async_add_entities: Async add entities callback
    """
    _LOGGER.info(f"Setting up {platform} platform")

    if not config_entry:
        _LOGGER.warning(f"Config entry not available, skipping {platform} setup")
        return

    devices = hass.data.get("ramses_extras", {}).get("devices", [])
    if not devices:
        _LOGGER.warning(f"No devices available for {platform}")
        return

    # Get enabled features
    enabled_features = get_enabled_features(hass, config_entry)
    _LOGGER.info(f"Enabled features for {platform}: {enabled_features}")

    # Calculate required entities for this platform
    required_entities = calculate_required_entities(
        platform, enabled_features, devices, hass
    )

    if not required_entities:
        _LOGGER.info(f"No required {platform} entities, skipping setup")
        return

    # This is a generic function - specific platforms should override
    # The actual entity creation is handled by the specific platform files
    _LOGGER.info(
        f"Platform {platform} setup completed with {len(required_entities)} "
        f"required entity types: {required_entities}"
    )


class PlatformSetup:
    """Enhanced platform setup utilities for all features.

    This class provides reusable platform setup patterns that extract common
    functionality from platform implementations, reducing code duplication
    and ensuring consistency across all features.
    """

    @staticmethod
    async def async_setup_platform(
        platform: str,
        hass: "HomeAssistant",
        config_entry: ConfigEntry,
        async_add_entities: AddEntitiesCallback,
        entity_configs: dict[str, Any],
        entity_factory: Callable[
            ["HomeAssistant", str, ConfigEntry | None], Awaitable[list[Entity]]
        ],
        store_entities_for_automation: bool = False,
    ) -> None:
        """Generic platform setup with entity creation.

        This method extracts the common platform setup pattern used across
        all platform files, providing a reusable foundation for new features.

        Args:
            platform: Platform type (sensor, switch, binary_sensor, number)
            hass: Home Assistant instance
            config_entry: Configuration entry
            async_add_entities: Add entities callback
            entity_configs: Dictionary of entity configurations
            entity_factory: Factory function to create entities
            store_entities_for_automation: Whether to store entities in hass.data
                for automation access (default: False)
        """
        _LOGGER.info("Setting up %s platform with generic setup", platform)

        # Get devices from Home Assistant data
        devices = hass.data.get("ramses_extras", {}).get("devices", [])
        _LOGGER.info(
            "%s platform: found %d devices: %s", platform, len(devices), devices
        )

        if not devices:
            _LOGGER.warning("No devices found for %s platform", platform)
            return

        entities = []
        for device_id in devices:
            try:
                # Create entities for this device using the provided factory
                device_entities = await entity_factory(hass, device_id, config_entry)
                entities.extend(device_entities)
                _LOGGER.info(
                    "Created %d %s entities for device %s",
                    len(device_entities),
                    platform,
                    device_id,
                )
            except Exception as e:
                _LOGGER.error(
                    "Failed to create %s entities for device %s: %e",
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
    def create_entities_for_device(
        device_id: str,
        entity_configs: dict[str, Any],
        entity_factory: Callable[["HomeAssistant", str, dict[str, Any]], Entity],
        hass: Optional["HomeAssistant"] = None,
    ) -> list[Entity]:
        """Create entities for a specific device.

        This method provides a consistent way to create multiple entities
        for a device based on configuration.

        Args:
            device_id: Device identifier
            entity_configs: Dictionary of entity configurations
            entity_factory: Factory function to create individual entities
            hass: Optional Home Assistant instance

        Returns:
            List of created entities
        """
        entities = []

        for entity_type, config in entity_configs.items():
            try:
                # Check if device supports this entity type
                if not PlatformSetup._is_entity_supported_for_device(device_id, config):
                    _LOGGER.debug(
                        "Entity type %s not supported for device %s",
                        entity_type,
                        device_id,
                    )
                    continue

                # Create entity using the factory
                entity = entity_factory(hass, device_id, config)
                if entity:
                    entities.append(entity)
                    _LOGGER.debug(
                        "Created %s entity for device %s", entity_type, device_id
                    )
            except Exception as e:
                _LOGGER.error(
                    "Failed to create %s entity for device %s: %e",
                    entity_type,
                    device_id,
                    e,
                )

        return entities

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
                await PlatformSetup.async_setup_platform(
                    platform=platform,
                    hass=hass,
                    config_entry=config_entry,
                    async_add_entities=async_add_entities_callbacks[platform],
                    entity_configs=entity_configs,
                    entity_factory=PlatformSetup._default_entity_factory,
                )
            except Exception as e:
                _LOGGER.error(
                    "Failed to setup %s platform for feature %s: %e",
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
        hass: "HomeAssistant", device_id: str, config_entry: ConfigEntry | None = None
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
        devices = hass.data.get("ramses_extras", {}).get("devices", [])

        # Get entity manager for device filtering
        entity_manager = hass.data.get("ramses_extras", {}).get("entity_manager")
        if entity_manager is None:
            # Create a temporary entity manager for device enablement checking
            from custom_components.ramses_extras.framework.helpers.entity.simple_entity_manager import (  # noqa: E501
                SimpleEntityManager,
            )

            entity_manager = SimpleEntityManager(hass)

            # Restore matrix state from config entry if available
            matrix_state = config_entry.data.get("device_feature_matrix", {})
            if matrix_state:
                entity_manager.restore_device_feature_matrix_state(matrix_state)
                _LOGGER.debug(f"Restored matrix state with {len(matrix_state)} devices")

        # Filter devices to only include those enabled for this feature
        filtered_devices = []
        for device_id in devices:
            device_id_str = extract_device_id_as_string(device_id)
            if entity_manager.is_device_enabled_for_feature(device_id_str, feature_id):
                filtered_devices.append(device_id_str)
            else:
                _LOGGER.debug(
                    f"Skipping disabled device for {feature_id} feature: "
                    f"{device_id_str}"
                )

        _LOGGER.info(
            "Filtered %d devices to %d enabled devices for feature %s",
            len(devices),
            len(filtered_devices),
            feature_id,
        )

        return filtered_devices
