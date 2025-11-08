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
    broker = get_ramses_broker(hass)
    if not broker:
        _LOGGER.warning("No Ramses broker available for device %s", device_id)
        return None

    # Try different ways to access devices from the broker
    devices = None

    if hasattr(broker, "_devices"):
        devices = broker._devices
    elif hasattr(broker, "devices"):
        devices = broker.devices
    elif hasattr(broker, "client") and hasattr(broker.client, "devices"):
        devices = broker.client.devices
    elif hasattr(broker, "get_devices"):
        devices = broker.get_devices()

    if devices is None:
        _LOGGER.warning("No devices found in broker")
        return None

    # Handle devices as a list of objects
    if isinstance(devices, list | set):
        devices_list = list(devices)

        for device in devices_list:
            try:
                # Try to get the device ID - catch AttributeError if accessing .id fails
                try:
                    device_id_from_device = device.id
                    if device_id_from_device == device_id:
                        _LOGGER.info(
                            "Found device %s (%s)", device_id, device.__class__.__name__
                        )
                        return device
                except AttributeError as ex:
                    # Log the error for debugging
                    _LOGGER.warning("Error checking device: %s", str(ex), exc_info=True)
                    continue

            except Exception as ex:
                _LOGGER.warning("Error checking device: %s", str(ex), exc_info=True)

        _LOGGER.warning("Device %s not found in device list", device_id)
        return None

    # Handle devices as a dictionary
    if isinstance(devices, dict):
        # Try direct lookup first
        device = devices.get(device_id)
        if device:
            _LOGGER.info(
                "Found device %s in dict (%s)", device_id, device.__class__.__name__
            )
            return device

        # Try case-insensitive lookup
        device_id_lower = str(device_id).lower()
        for dev_id, dev in devices.items():
            if str(dev_id).lower() == device_id_lower:
                _LOGGER.info("Found device %s (as %s) in dict", device_id, dev_id)
                return dev

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

    # Check if ramses_data is the broker itself
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

                    # Also check for devices attribute which
                    # indicates it might be a broker
                    if hasattr(value, "devices"):
                        _LOGGER.debug(
                            "Found broker-like object with devices attribute in %s",
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

    devices = getattr(broker, "devices", {})

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


def generate_entity_id(entity_type: str, entity_name: str, device_id: str) -> str:
    """Generate a consistent entity ID from type, name, and device ID.

    Args:
        entity_type: Type of entity ("sensor", "switch", "number", "binary_sensor")
        entity_name: Name of the entity from config (e.g., "indoor_absolute_humidity")
        device_id: Device ID in underscore format (e.g., "32_153289")

    Returns:
        Full entity ID (e.g., "sensor.indoor_absolute_humidity_32_153289")
    """
    # Map entity types to their prefixes
    type_to_prefix = {
        "sensor": "sensor",
        "switch": "switch",
        "number": "number",
        "binary_sensor": "binary_sensor",
    }

    prefix = type_to_prefix.get(entity_type, entity_type)
    return f"{prefix}.{entity_name}_{device_id}"


def get_entity_template(entity_type: str, entity_name: str) -> str | None:
    """Get the entity template for a specific entity type and name.

    Args:
        entity_type: Type of entity ("sensor", "switch", "number", "binary_sensor")
        entity_name: Name of the entity from config (e.g., "indoor_absolute_humidity")

    Returns:
        Entity template string with {device_id} placeholder, or None if not found
    """
    configs = ENTITY_TYPE_CONFIGS.get(entity_type, {})
    entity_config = configs.get(entity_name, {})
    template = entity_config.get("entity_template")
    return template if template is not None else None


def generate_entity_name_from_template(
    entity_type: str, entity_name: str, device_id: str
) -> str | None:
    """Generate a full entity ID using the configured template.

    Args:
        entity_type: Type of entity ("sensor", "switch", "number", "binary_sensor")
        entity_name: Name of the entity from config (e.g., "indoor_absolute_humidity")
        device_id: Device ID in underscore format (e.g., "32_153289")

    Returns:
        Full entity ID using the template, or None if template not found
    """
    template = get_entity_template(entity_type, entity_name)
    if not template:
        return None

    # Replace {device_id} placeholder with actual device ID
    entity_id_part = template.format(device_id=device_id)

    # Add the entity type prefix
    type_to_prefix = {
        "sensor": "sensor",
        "switch": "switch",
        "number": "number",
        "binary_sensor": "binary_sensor",
    }

    prefix = type_to_prefix.get(entity_type, entity_type)
    return f"{prefix}.{entity_id_part}"


def get_all_required_entity_ids_for_device(device_id: str) -> list[str]:
    """Get all entity IDs required for a device based on its capabilities.

    Args:
        device_id: Device ID in underscore format (e.g., "32_153289")

    Returns:
        List of all required entity IDs for this device
    """
    entity_ids = []

    # For each entity type configuration
    for entity_type, configs in ENTITY_TYPE_CONFIGS.items():
        # For each entity in that type
        for entity_name in configs.keys():
            entity_id = generate_entity_name_from_template(
                entity_type, entity_name, device_id
            )
            if entity_id:
                entity_ids.append(entity_id)

    return entity_ids


def parse_entity_id(entity_id: str) -> tuple[str, str, str] | None:
    """Parse an entity ID to extract entity type, name, and device ID.

    Args:
        entity_id: Full entity ID (e.g., "sensor.indoor_absolute_humidity_32_153289")

    Returns:
        Tuple of (entity_type, entity_name, device_id) or None if parsing fails
    """
    try:
        # Split on first dot to get type and rest
        if "." not in entity_id:
            return None

        entity_type, rest = entity_id.split(".", 1)

        # Device ID patterns we expect: 32_153289, 10_456789, etc.
        # These have the pattern: digits_underscore_digits
        # We need to find this pattern at the end of the string

        import re

        # Look for device ID pattern: _ followed by digits,
        # underscore, digits at the end
        device_id_match = re.search(r"_(\d+_\d+)$", rest)
        if device_id_match:
            device_id = device_id_match.group(
                1
            )  # The actual device ID part (e.g., "32_153289")
            # Remove the device ID and underscore from the entity name
            entity_name = rest[: device_id_match.start(0)]
        else:
            # No device ID found, return as is
            return entity_type, rest, ""

        # Validate entity type
        valid_types = {"sensor", "switch", "number", "binary_sensor"}
        if entity_type not in valid_types:
            return None

        return entity_type, entity_name, device_id

    except (ValueError, IndexError):
        return None


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

                    entity_id = generate_entity_name_from_template(
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
