"""Helper functions for Ramses Extras platforms.

This module contains reusable helper functions used across all platform modules
(sensor, switch, binary_sensor) to avoid code duplication and improve maintainability.
"""

import logging
from typing import TYPE_CHECKING, Any, Optional

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.components.number import NumberEntity
from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.restore_state import RestoreEntity

from ..const import (
    AVAILABLE_FEATURES,
    DEVICE_ENTITY_MAPPING,
    DOMAIN,
    ENTITY_TYPE_CONFIGS,
)
from .device import find_ramses_device, get_device_type
from .entity import EntityHelpers, ExtrasBaseEntity

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

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
        # Try to find the actual device if hass is available
        device = None
        device_type = "Unknown"

        if hass:
            device = find_ramses_device(hass, device_id)
            if device:
                device_type = get_device_type(device)
            else:
                continue  # Skip if device not found and hass is available
        else:
            # For testing or when hass is not available, assume HvacVentilator
            # This allows tests to work without actual device lookup
            device_type = "HvacVentilator"

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
                        orphaned_entities.append(entity_id)
                        _LOGGER.info(
                            "Will remove orphaned %s: %s (type: %s)",
                            platform,
                            entity_id,
                            entity_type,
                        )
                    break

    return orphaned_entities


async def async_setup_platform(
    platform: str,
    hass: "HomeAssistant",
    config_entry: ConfigEntry | None,
    async_add_entities: "AddEntitiesCallback",
) -> None:
    """Generic setup function for all platforms
    (sensor, switch, binary_sensor, number)."""
    try:
        devices = hass.data.get(DOMAIN, {}).get("devices", [])
        _LOGGER.info(f"Setting up {platform} platform for {len(devices)} devices")

        if not config_entry:
            _LOGGER.warning(f"Config entry not available, skipping {platform} setup")
            return

        if not devices:
            _LOGGER.debug(f"No devices available for {platform}s")
            return

        entities = []

        # Get enabled features from config entry
        enabled_features = get_enabled_features(hass, config_entry)
        _LOGGER.info(f"Enabled features: {enabled_features}")
        _LOGGER.info(f"Config entry data: {config_entry.data}")

        # Create entities based on enabled features and their requirements
        for device_id in devices:
            device = find_ramses_device(hass, device_id)
            if not device:
                _LOGGER.warning(
                    f"Device {device_id} not found, skipping {platform} creation"
                )
                continue

            device_type = get_device_type(device)
            _LOGGER.debug(
                f"Creating {platform}s for device {device_id} of type {device_type}"
            )
            _LOGGER.debug(
                f"DEVICE_ENTITY_MAPPING keys: {list(DEVICE_ENTITY_MAPPING.keys())}"
            )
            _LOGGER.debug(
                f"device_type in DEVICE_ENTITY_MAPPING: "
                f"{device_type in DEVICE_ENTITY_MAPPING}"
            )

            if device_type in DEVICE_ENTITY_MAPPING:
                entity_mapping = DEVICE_ENTITY_MAPPING[device_type]

                # Get all possible entity types for this device
                # Map platform names to their plural forms used in DEVICE_ENTITY_MAPPING
                platform_to_plural = {
                    "sensor": "sensors",
                    "switch": "switches",
                    "binary_sensor": "binary_sensors",
                    "number": "numbers",
                }
                platform_key = platform_to_plural.get(platform, f"{platform}s")
                all_possible_entities = entity_mapping.get(platform_key, [])

            # Check each possible entity type
            for entity_type in all_possible_entities:
                if entity_type not in ENTITY_TYPE_CONFIGS[platform]:
                    continue

                # Check if this entity is needed by any enabled feature
                is_needed = False
                _LOGGER.debug(
                    f"Checking if {entity_type} is needed for "
                    f"{device_id} ({device_type})"
                )
                _LOGGER.debug(f"Available features: {list(AVAILABLE_FEATURES.keys())}")
                _LOGGER.debug(f"Enabled features: {enabled_features}")

                for feature_key, is_enabled in enabled_features.items():
                    _LOGGER.debug(
                        f"Checking feature {feature_key}: enabled={is_enabled}"
                    )
                    if not is_enabled or feature_key not in AVAILABLE_FEATURES:
                        continue

                    feature_config = AVAILABLE_FEATURES[feature_key]
                    _LOGGER.debug(f"Feature config: {feature_config}")
                    supported_types = feature_config.get("supported_device_types", [])
                    _LOGGER.debug(
                        f"Supported types for {feature_key}: {supported_types}"
                    )

                    if (
                        isinstance(supported_types, list)
                        and device_type in supported_types
                    ):
                        # Check if this entity is required or optional for this feature
                        required_entities = feature_config.get("required_entities", {})
                        optional_entities = feature_config.get("optional_entities", {})

                        if isinstance(required_entities, dict):
                            required_list = required_entities.get(platform_key, [])
                        else:
                            required_list = []

                        if isinstance(optional_entities, dict):
                            optional_list = optional_entities.get(platform_key, [])
                        else:
                            optional_list = []

                        _LOGGER.debug(
                            f"Required {platform_key} for {feature_key}: "
                            f"{required_list}"
                        )
                        _LOGGER.debug(
                            f"Optional {platform_key} for {feature_key}: "
                            f"{optional_list}"
                        )

                        if (
                            isinstance(required_list, list)
                            and entity_type in required_list
                        ) or (
                            isinstance(optional_list, list)
                            and entity_type in optional_list
                        ):
                            is_needed = True
                            _LOGGER.debug(
                                f"Entity {entity_type} needed for feature {feature_key}"
                            )
                            break

                if not is_needed:
                    _LOGGER.debug(
                        f"Entity {entity_type} not needed by any enabled feature"
                    )

                if is_needed:
                    # Entity is needed - create it
                    config = ENTITY_TYPE_CONFIGS[platform][entity_type]

                    # Create appropriate entity class based on platform
                    if platform == "number":
                        from ..number import RamsesNumberEntity

                        entity_class: Any = RamsesNumberEntity
                    elif platform == "switch":
                        from ..switch import RamsesDehumidifySwitch

                        entity_class = RamsesDehumidifySwitch
                    elif platform == "binary_sensor":
                        from ..binary_sensor import RamsesBinarySensor

                        entity_class = RamsesBinarySensor
                    else:
                        _LOGGER.warning(f"Unsupported platform: {platform}")
                        continue

                    entities.append(entity_class(hass, device_id, entity_type, config))
                    entity_id = EntityHelpers.generate_entity_name_from_template(
                        platform, entity_type, device_id
                    )
                    _LOGGER.debug(f"Creating {platform}: {entity_id}")

        async_add_entities(entities, True)
    except Exception as e:
        _LOGGER.error(f"Error setting up {platform} platform: {e}")
        import traceback

        _LOGGER.error(f"Full traceback: {traceback.format_exc()}")
