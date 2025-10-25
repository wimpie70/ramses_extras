"""Helper functions for Ramses Extras platforms.

This module contains reusable helper functions used across all platform modules
(sensor, switch, binary_sensor) to avoid code duplication and improve maintainability.
"""

import logging
from typing import TYPE_CHECKING, Any, Optional

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers import entity_registry as er

from ..const import AVAILABLE_FEATURES, DEVICE_ENTITY_MAPPING, DOMAIN
from .device import find_ramses_device, get_device_type

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)


def get_enabled_features(
    hass: "HomeAssistant", config_entry: ConfigEntry
) -> dict[str, bool]:
    """Get enabled features from config entry with fallback logic.

    Args:
        hass: Home Assistant instance
        config_entry: Config entry object

    Returns:
        Dictionary of enabled features
    """
    # Get enabled features from config entry
    enabled_features: dict[str, bool] = config_entry.data.get("enabled_features", {})

    # Fallback: try to get from hass.data if config_entry doesn't have it
    if not enabled_features and DOMAIN in hass.data:
        entry_id = hass.data[DOMAIN].get("entry_id")
        if entry_id:
            entry = hass.config_entries.async_get_entry(entry_id)
            if entry:
                enabled_features = entry.data.get("enabled_features", {})

    return enabled_features


def get_entity_registry(hass: "HomeAssistant") -> er.EntityRegistry | None:
    """Get entity registry with error handling.

    Args:
        hass: Home Assistant instance

    Returns:
        Entity registry or None if not available
    """
    if "entity_registry" not in hass.data:
        _LOGGER.warning("Entity registry not available")
        return None

    return hass.data["entity_registry"]


def calculate_required_entities(
    platform: str,
    enabled_features: dict[str, bool],
    devices: list[str],
    hass: Optional["HomeAssistant"] = None,
) -> set[str]:
    """Calculate which entities are required by the enabled features.

    Args:
        platform: Platform type ('sensor', 'switch', 'binary_sensor')
        enabled_features: Dictionary of enabled features
        devices: List of device IDs
        hass: Home Assistant instance (optional, for device lookup)

    Returns:
        Set of required entity IDs
    """
    required_entities: set[str] = set()

    for device_id in devices:
        device = find_ramses_device(hass, device_id)
        if not device:
            continue

        device_type = get_device_type(device)
        if device_type not in DEVICE_ENTITY_MAPPING:
            continue

        entity_mapping = DEVICE_ENTITY_MAPPING[device_type]
        platform_key = f"{platform}s"  # Convert 'sensor' -> 'sensors', etc.

        for feature_key, is_enabled in enabled_features.items():
            if not is_enabled or feature_key not in AVAILABLE_FEATURES:
                continue

            feature_config = AVAILABLE_FEATURES[feature_key]

            # Check if this device type is supported
            supported_types = feature_config.get("supported_device_types", [])
            if (
                not isinstance(supported_types, list)
                or device_type not in supported_types
            ):
                continue

            # Add required entities for this platform
            required_entities_dict = feature_config.get("required_entities", {})
            if isinstance(required_entities_dict, dict):
                entity_types = required_entities_dict.get(platform_key, [])
                if isinstance(entity_types, list):
                    for entity_type in entity_types:
                        if isinstance(
                            entity_type, str
                        ) and entity_type in entity_mapping.get(platform_key, []):
                            required_entities.add(
                                f"{platform}.{device_id}_{entity_type}"
                            )

            # Add optional entities for this platform
            optional_entities_dict = feature_config.get("optional_entities", {})
            if isinstance(optional_entities_dict, dict):
                entity_types = optional_entities_dict.get(platform_key, [])
                if isinstance(entity_types, list):
                    for entity_type in entity_types:
                        if isinstance(
                            entity_type, str
                        ) and entity_type in entity_mapping.get(platform_key, []):
                            required_entities.add(
                                f"{platform}.{device_id}_{entity_type}"
                            )

    return required_entities


def convert_device_id_format(device_id: str) -> str:
    """Convert device ID from colon format to underscore format.

    Args:
        device_id: Device ID in format 32:153289

    Returns:
        Device ID in format 32_153289
    """
    return device_id.replace(":", "_")


def find_orphaned_entities(
    platform: str,
    hass: "HomeAssistant",
    devices: list[str],
    required_entities: set[str],
    all_possible_types: list[str],
) -> list[str]:
    """Find entities that should be removed (orphaned).

    Args:
        platform: Platform type ('sensor', 'switch', 'binary_sensor')
        hass: Home Assistant instance
        devices: List of device IDs
        required_entities: Set of currently required entity IDs
        all_possible_types: List of all possible entity types for this platform

    Returns:
        List of orphaned entity IDs to remove
    """
    entity_registry = get_entity_registry(hass)
    if not entity_registry:
        return []

    orphaned_entities: list[str] = []

    for entity_id, _entity_entry in entity_registry.entities.items():
        if not entity_id.startswith(f"{platform}."):
            continue

        # Extract device_id from entity_id
        # Format: {platform}.{entity_type}_{device_id} where device_id is 32_153289
        parts = entity_id.split(".")
        if len(parts) >= 2:
            entity_name_and_device = parts[1]  # entity_type_device_id

            # Check if this entity belongs to one of our devices
            for device_id in devices:
                # Convert device_id from colon format (32:153289)
                # to underscore format (32_153289)
                device_id_underscore = convert_device_id_format(device_id)

                # Check if the entity belongs to this device (device_id at the end)
                if entity_name_and_device.endswith(f"_{device_id_underscore}"):
                    # This entity belongs to our device, check if it's still needed
                    entity_type = entity_name_and_device[
                        : -len(f"_{device_id_underscore}") - 1
                    ]  # Remove "_32_153289"

                    # Check if this entity_type is still required
                    expected_entity_id = (
                        f"{platform}.{entity_type}_" + f"{device_id_underscore}"
                    )
                    if expected_entity_id not in required_entities:
                        # Never remove absolute humidity sensors -
                        # they are fundamental device data
                        if platform == "sensor" and entity_type in [
                            "indoor_abs_humid",
                            "outdoor_abs_humid",
                        ]:
                            _LOGGER.debug(
                                "Keeping fundamental sensor: %s (always needed)",
                                entity_id,
                            )
                            continue

                        orphaned_entities.append(entity_id)
                        _LOGGER.info(
                            "Will remove orphaned %s: %s (type: %s)",
                            platform,
                            entity_id,
                            entity_type,
                        )
                    break

    return orphaned_entities


async def remove_orphaned_entities(
    platform: str,
    hass: "HomeAssistant",
    devices: list[str],
    required_entities: set[str],
    all_possible_types: list[str],
) -> int:
    """Remove orphaned entities from the registry.

    Args:
        platform: Platform type ('sensor', 'switch', 'binary_sensor')
        hass: Home Assistant instance
        devices: List of device IDs
        required_entities: Set of currently required entity IDs
        all_possible_types: List of all possible entity types for this platform

    Returns:
        Number of entities removed
    """
    _LOGGER.info(f"Starting {platform} cleanup for devices: {devices}")
    _LOGGER.info(f"Entity registry available: {get_entity_registry(hass) is not None}")

    # Get the current config entry properly
    config_entry = None
    if DOMAIN in hass.data and "entry_id" in hass.data[DOMAIN]:
        entry_id = hass.data[DOMAIN]["entry_id"]
        config_entry = hass.config_entries.async_get_entry(entry_id)

    if config_entry is None:
        _LOGGER.warning(f"No config entry available for {platform} cleanup")
        return 0

    current_required_entities = calculate_required_entities(
        platform, get_enabled_features(hass, config_entry), devices, hass
    )
    _LOGGER.info(f"Required {platform} entities: {current_required_entities}")

    entity_registry = get_entity_registry(hass)
    if not entity_registry:
        _LOGGER.warning(f"Entity registry not available for {platform} cleanup")
        return 0

    _LOGGER.info(f"Found {len(entity_registry.entities)} entities in registry")

    # Debug: Log all entities for this platform
    platform_entities = [
        eid for eid in entity_registry.entities.keys() if eid.startswith(f"{platform}.")
    ]
    _LOGGER.info(f"All {platform} entities in registry: {platform_entities}")

    orphaned_entities = find_orphaned_entities(
        platform, hass, devices, current_required_entities, all_possible_types
    )
    _LOGGER.info(
        f"Found {len(orphaned_entities)} orphaned {platform} entities to remove"
    )

    removed_count = 0
    for entity_id in orphaned_entities:
        try:
            entity_registry.async_remove(entity_id)
            _LOGGER.info(f"Removed orphaned {platform} entity: {entity_id}")
            removed_count += 1
        except Exception as e:
            _LOGGER.warning(f"Failed to remove {platform} entity {entity_id}: {e}")

    return removed_count
