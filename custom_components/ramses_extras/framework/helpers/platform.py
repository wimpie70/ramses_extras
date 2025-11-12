"""Platform helper functions for Ramses Extras."""

import logging
from typing import TYPE_CHECKING, Any, cast

from homeassistant.config_entries import ConfigEntry

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
        "sensor": "sensors",
        "switch": "switches",
        "binary_sensor": "binary_sensors",
        "number": "numbers",
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
