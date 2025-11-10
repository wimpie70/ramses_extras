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
    """Calculate required entities for a platform based on enabled features.

    Args:
        platform: Platform type (sensor, switch, etc.)
        enabled_features: Dictionary of enabled features
        devices: List of device IDs
        hass: Home Assistant instance

    Returns:
        List of required entity types
    """
    required_entities = []

    from custom_components.ramses_extras.const import (
        AVAILABLE_FEATURES,
        FEATURE_ID_HUMIDITY_CONTROL,
    )

    for feature_key, is_enabled in enabled_features.items():
        if not is_enabled or feature_key not in AVAILABLE_FEATURES:
            continue

        feature_config = AVAILABLE_FEATURES[feature_key]
        feature_required = feature_config.get("required_entities", {})
        feature_optional = feature_config.get("optional_entities", {})

        # Get required entities for this platform
        if isinstance(feature_required, dict):
            platform_key = _get_platform_key(platform)
            required_for_platform = feature_required.get(platform_key, [])
        else:
            required_for_platform = []

        # Get optional entities for this platform (treat as required for now)
        if isinstance(feature_optional, dict):
            platform_key = _get_platform_key(platform)
            optional_for_platform = feature_optional.get(platform_key, [])
        else:
            optional_for_platform = []

        # Add all entities (required and optional)
        all_entities = required_for_platform + optional_for_platform
        for entity in all_entities:
            if entity not in required_entities:
                required_entities.append(entity)

    _LOGGER.info(
        f"Platform {platform}: calculated {len(required_entities)} "
        f"required entities for {len(devices)} devices: {required_entities}"
    )

    # Debug: Log detailed feature information
    if platform in ["switch", "binary_sensor", "number", "sensor"]:
        _LOGGER.info(f"Debug: {platform} platform analysis:")
        platform_key = _get_platform_key(platform)
        for feature_key, is_enabled in enabled_features.items():
            if not is_enabled or feature_key not in AVAILABLE_FEATURES:
                continue

            feature_config = AVAILABLE_FEATURES[feature_key]
            _LOGGER.info(f"  Feature {feature_key}: {feature_config}")

            # Get required entities for this platform
            required_entities_for_feature = feature_config.get("required_entities", {})
            if isinstance(required_entities_for_feature, dict):
                _LOGGER.info(f"    Required entities: {required_entities_for_feature}")
                _LOGGER.info(f"    Looking for key: {platform_key}")
                _LOGGER.info(
                    f"    Found: {required_entities_for_feature.get(platform_key, [])}"
                )
            else:
                _LOGGER.info(
                    f"    Required entities: "
                    f"{required_entities_for_feature} (not a dict)"
                )
                _LOGGER.info(f"    Looking for key: {platform_key}")
                _LOGGER.info("    Found: [] (invalid format)")

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
