"""Device finding and validation helpers for Ramses Extras."""

import logging
from typing import Any, Dict, List, Optional, cast

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from ..const import (
    AVAILABLE_FEATURES,
    BOOLEAN_CONFIGS,
    DEVICE_SERVICE_MAPPING,
    DOMAIN,
    ENTITY_TYPE_CONFIGS,
    NUMBER_CONFIGS,
    SENSOR_CONFIGS,
    SERVICE_REGISTRY,
    SWITCH_CONFIGS,
)

_LOGGER = logging.getLogger(__name__)


def find_ramses_device(hass: HomeAssistant, device_id: str) -> Any | None:
    """Find a Ramses device by ID.

    Args:
        hass: Home Assistant instance
        device_id: The Ramses device ID (e.g., "32:153289")

    Returns:
        The Ramses device object or None if not found
    """
    # Get the broker
    broker = get_ramses_broker(hass)
    if not broker:
        _LOGGER.warning("No Ramses broker available for device %s", device_id)
        return None

    # Use broker's _get_device method for efficient lookup
    device = broker._get_device(device_id)
    if device:
        _LOGGER.info("Found device %s (%s)", device_id, device.__class__.__name__)
        return device

    _LOGGER.warning("Device %s not found in broker", device_id)
    return None


def get_ramses_broker(hass: HomeAssistant) -> Any | None:
    """Get the Ramses CC broker safely.

    Args:
        hass: Home Assistant instance

    Returns:
        The Ramses broker object or None if not available
    """
    if not hasattr(hass, "data") or not isinstance(hass.data, dict):
        _LOGGER.error("Invalid hass.data structure")
        return None

    ramses_data = hass.data.get("ramses_cc")

    if not ramses_data:
        _LOGGER.warning("Ramses CC integration not loaded in hass.data")
        return None

    # Since we know broker._devices is valid, check if ramses_data is the broker itself
    if ramses_data.__class__.__name__ == "RamsesBroker":
        _LOGGER.debug("Found RamsesBroker instance directly")
        return ramses_data

    # Handle the case where ramses_data is a dictionary of entries
    if isinstance(ramses_data, dict):
        for entry_id, data in ramses_data.items():
            # If data is a RamsesBroker instance
            if data.__class__.__name__ == "RamsesBroker":
                return data

            # If data is a dictionary, look for a broker inside it
            if isinstance(data, dict):
                # Check for direct broker reference
                if (
                    broker := data.get("broker")
                ) and broker.__class__.__name__ == "RamsesBroker":
                    return broker

                # Check all values in the nested dict
                for key, value in data.items():
                    if (
                        hasattr(value, "__class__")
                        and value.__class__.__name__ == "RamsesBroker"
                    ):
                        return value

                    # Since we know broker._devices is valid,
                    # check for _devices attribute
                    if hasattr(value, "_devices"):
                        _LOGGER.debug(
                            "Found broker-like object with _devices attribute in %s",
                            entry_id,
                        )
                        return value

    _LOGGER.warning("No Ramses broker found in ramses_data")
    return None


def get_feature_required_entities(feature_id: str) -> dict[str, list[str]]:
    """Get required entities for a specific feature.

    Args:
        feature_id: Feature ID (e.g., "humidity_control")

    Returns:
        Dictionary mapping entity types to lists of entity names
    """
    feature = AVAILABLE_FEATURES.get(feature_id, {})
    required_entities = feature.get("required_entities", {})
    # Ensure the return type is correct
    if isinstance(required_entities, dict):
        return dict(required_entities)
    return {}


def get_feature_entity_mappings(feature_id: str) -> dict[str, str]:
    """Get entity mappings for a feature by combining
     required entities with config names.

    Args:
        feature_id: Feature ID (e.g., "humidity_control")

    Returns:
        Dictionary mapping const entity names to actual entity names from configs
    """
    required_entities = get_feature_required_entities(feature_id)
    entity_mappings = {}

    # Flatten all entity names from all types
    all_entity_names = []
    for entity_type, entity_list in required_entities.items():
        all_entity_names.extend(entity_list)

    # Create mapping from const names to actual config names
    # Entity names in const.py ARE the actual entity names
    for entity_name in all_entity_names:
        entity_mappings[entity_name] = entity_name

    return entity_mappings


def get_state_to_entity_mappings(feature_id: str) -> dict[str, tuple[str, str]]:
    """Get state to entity mappings for a feature.

    This method provides the mapping between internal state names used in automations
    and the actual entity types and names from the feature configuration.

    Args:
        feature_id: Feature ID (e.g., "humidity_control")

    Returns:
        Dictionary mapping state names to (entity_type, entity_name) tuples
    """
    if feature_id == "humidity_control":
        return {
            "indoor_abs": ("sensor", "indoor_absolute_humidity"),
            "outdoor_abs": ("sensor", "outdoor_absolute_humidity"),
            "max_humidity": ("number", "relative_humidity_maximum"),
            "min_humidity": ("number", "relative_humidity_minimum"),
            "offset": ("number", "absolute_humidity_offset"),
        }

    # For other features, this would need to be implemented based on their needs
    # This is where you'd add mappings for other automations
    return {}


def get_device_type(device: Any) -> str:
    """Get device type name safely.

    Args:
        device: The Ramses device object

    Returns:
        Device type name (e.g., "HvacVentilator")
    """
    if device is None:
        return "None"

    try:
        device_type = device.__class__.__name__
        _LOGGER.debug(f"Device type for {device}: {device_type}")
        return str(device_type)
    except Exception as e:
        _LOGGER.warning(f"Failed to get device type: {e}")
        return "Unknown"


def validate_device_for_service(
    hass: HomeAssistant, device_id: str, service_name: str
) -> bool:
    """Validate that a device exists and supports a specific service.

    Args:
        hass: Home Assistant instance
        device_id: The Ramses device ID
        service_name: Name of the service to validate

    Returns:
        True if device exists and supports the service, False otherwise
    """
    device = find_ramses_device(hass, device_id)
    if not device:
        _LOGGER.warning(
            f"Cannot validate service {service_name}: device {device_id} not found"
        )
        return False

    device_type = get_device_type(device)

    # Check if device type supports this service
    supported_services = DEVICE_SERVICE_MAPPING.get(device_type, [])
    if service_name not in supported_services:
        _LOGGER.warning(
            f"Device {device_id} ({device_type}) does not support service "
            f"{service_name}. Supported services: {supported_services}"
        )
        return False

    return True


def get_all_device_ids(hass: HomeAssistant) -> list[str]:
    """Get all Ramses device IDs.

    Args:
        hass: HomeAssistant instance

    Returns:
        List of all device IDs found in Ramses CC
    """
    broker = get_ramses_broker(hass)
    if not broker:
        _LOGGER.warning("No Ramses broker available to get device IDs")
        return []

    # Since we know broker._devices is valid, use it directly
    devices = getattr(broker, "_devices", {})

    device_ids = []

    if isinstance(devices, list):
        for d in devices:
            try:
                # All devices should have an 'id' attribute
                if hasattr(d, "id"):
                    device_ids.append(str(d.id))
                else:
                    _LOGGER.debug("Device missing 'id' attribute: %s", d)
            except Exception as ex:
                _LOGGER.debug("Error getting device ID: %s", str(ex))
    elif isinstance(devices, dict):
        device_ids = [str(k) for k in devices.keys()]
    else:
        _LOGGER.warning("Unexpected devices type: %s", type(devices).__name__)

    _LOGGER.info("Found %d Ramses devices", len(device_ids))
    return device_ids


def ensure_ramses_cc_loaded(hass: HomeAssistant) -> None:
    """Ensure Ramses CC integration is loaded.

    Args:
        hass: Home Assistant instance

    Raises:
        HomeAssistantError: If Ramses CC is not loaded
    """
    if "ramses_cc" not in hass.config.components:
        raise HomeAssistantError(
            "Ramses CC integration is not loaded. "
            "Please ensure Ramses CC is installed and configured."
        )

    if not get_ramses_broker(hass):
        raise HomeAssistantError(
            "Ramses CC broker is not available. "
            "Please check your Ramses CC configuration."
        )


def get_state_to_entity_mappings_v2(feature_id: str, device_id: str) -> dict[str, str]:
    """Get state to entity mappings for a feature.

    Enhanced version that generates full entity IDs for a specific device.

    Args:
        feature_id: Feature ID (e.g., "humidity_control")
        device_id: Device identifier (e.g., "32_153289")

    Returns:
        Dictionary mapping state names to full entity IDs
    """
    if feature_id == "humidity_control":
        mappings = {
            # CC entity: relative humidity sensor (unchanged)
            "indoor_rh": f"sensor.{device_id}_indoor_humidity",
        }

        # Get humidity feature definition from AVAILABLE_FEATURES
        humidity_feature = cast(
            dict[str, Any], AVAILABLE_FEATURES.get("humidity_control", {})
        )
        required_entities = cast(
            dict[str, list[str]], humidity_feature.get("required_entities", {})
        )

        # Define state to entity name mapping for humidity logic
        state_to_entity_name_mapping = {
            "indoor_abs": "indoor_absolute_humidity",
            "outdoor_abs": "outdoor_absolute_humidity",
            "max_humidity": "relative_humidity_maximum",
            "min_humidity": "relative_humidity_minimum",
            "offset": "absolute_humidity_offset",
        }

        # Generate entity IDs using the helper methods
        for state_name, entity_name in state_to_entity_name_mapping.items():
            # Find which entity type this belongs to
            for entity_type, entity_list in required_entities.items():
                if entity_name in entity_list:
                    # Entity names in const.py ARE the actual entity names
                    actual_entity_name = entity_name

                    from .entity import EntityHelpers

                    entity_id = EntityHelpers.generate_entity_name_from_template(
                        entity_type.rstrip("s"),  # Remove 's' from plural
                        actual_entity_name,
                        device_id,
                    )
                    if entity_id:
                        mappings[state_name] = entity_id
                    break

        return mappings

    # For other features, this would need to be implemented based on their needs
    return {}
