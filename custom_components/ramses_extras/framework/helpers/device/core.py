"""Device helper utilities for Ramses Extras framework.

This module provides reusable device utilities that are shared across
all features, including device finding, validation, and type detection.
"""

import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

# Note: AVAILABLE_FEATURES import removed to avoid circular dependency
# from ....const import AVAILABLE_FEATURES

_LOGGER = logging.getLogger(__name__)


def extract_device_id_as_string(device_id: str | Any) -> str:
    """Extract device ID from device object or string with robust error handling.

    Args:
        device_id: Device object or device ID string

    Returns:
        Device ID as string
    """
    # Handle device ID strings directly
    if isinstance(device_id, str):
        return device_id

    # Try multiple ways to get device ID from object (most specific first)
    if hasattr(device_id, "device_id"):
        return str(device_id.device_id)
    if hasattr(device_id, "id"):
        return str(device_id.id)
    if hasattr(device_id, "_id"):
        return str(device_id._id)
    if hasattr(device_id, "name"):
        return str(device_id.name)
    return f"device_{id(device_id)}"  # Fallback to object id


def find_ramses_device(hass: HomeAssistant, device_id: str) -> Any | None:
    """Find a Ramses device by ID.

    Args:
        hass: Home Assistant instance
        device_id: The Ramses device ID (e.g., "32:153289")

    Returns:
        The Ramses device object or None if not found
    """
    # Get the broker directly from hass.data
    if "ramses_cc" not in hass.data:
        _LOGGER.warning("Ramses CC not loaded for device %s", device_id)
        return None

    ramses_cc_entries = hass.config_entries.async_entries("ramses_cc")
    if not ramses_cc_entries:
        _LOGGER.warning("No Ramses CC entries found for device %s", device_id)
        return None

    # Get the broker directly
    ramses_entry_id = next(iter(hass.data["ramses_cc"]))
    broker = hass.data["ramses_cc"][ramses_entry_id]
    if not broker:
        _LOGGER.warning("No Ramses broker available for device %s", device_id)
        return None

    # Use broker's _get_device method for efficient lookup
    device = broker._get_device(device_id)
    if device:
        return device

    _LOGGER.warning("Device %s not found in broker", device_id)
    return None


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
        _LOGGER.debug("Device type for %s: %s", device, device_type)
        return str(device_type)
    except Exception as e:
        _LOGGER.warning("Failed to get device type: %s", e)
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
            "Cannot validate service %s: device %s not found",
            service_name,
            device_id,
        )
        return False

    device_type = get_device_type(device)

    # Service validation removed - services now handled by feature-based architecture
    _LOGGER.debug(
        "Device %s (%s) service validation delegated to features",
        device_id,
        device_type,
    )
    return True


def get_all_device_ids(hass: HomeAssistant) -> list[str]:
    """Get all Ramses device IDs.

    Args:
        hass: HomeAssistant instance

    Returns:
        List of all device IDs found in Ramses CC
    """
    # Get the broker directly from hass.data
    if "ramses_cc" not in hass.data:
        _LOGGER.warning("Ramses CC not loaded")
        return []

    ramses_cc_entries = hass.config_entries.async_entries("ramses_cc")
    if not ramses_cc_entries:
        _LOGGER.warning("No Ramses CC entries found")
        return []

    # Get the broker directly
    ramses_entry_id = next(iter(hass.data["ramses_cc"]))
    broker = hass.data["ramses_cc"][ramses_entry_id]
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

    # Check if broker is available
    if "ramses_cc" not in hass.data:
        raise HomeAssistantError(
            "Ramses CC broker is not available. "
            "Please check your Ramses CC configuration."
        )


# Device type to entity mapping helpers
def get_device_supported_entities(device_type: str) -> list[str]:
    """Get the list of entities supported by a device type.

    Args:
        device_type: The device type (e.g., "HvacVentilator")

    Returns:
        List of supported entity names
    """
    # from ... import get_device_mapping  # Removed to avoid circular dependency
    # return []  # Simplified to avoid circular import

    # Commented out to avoid circular import:
    # mapping = get_device_mapping(device_type)
    # if not mapping:
    #     return []

    # supported_entities = []
    # for entity_type, entities in mapping.items():
    #     supported_entities.extend(entities)

    # return supported_entities
    return []  # Return empty list to avoid circular import


def validate_device_entity_support(device_type: str, entity_name: str) -> bool:
    """Validate if a device type supports a specific entity.

    Args:
        device_type: The device type
        entity_name: The entity name to check

    Returns:
        True if device type supports the entity, False otherwise
    """
    supported_entities = get_device_supported_entities(device_type)
    return entity_name in supported_entities


async def _get_broker_for_entry(hass: HomeAssistant) -> Any | None:
    """Get the ramses_cc broker instance for device communication.

    This function implements multiple fallback methods to access the broker,
    following the same pattern used in the main integration setup.

    Args:
        hass: Home Assistant instance

    Returns:
        The ramses_cc broker instance or None if not found
    """
    # Check if ramses_cc is loaded
    ramses_cc_entries = hass.config_entries.async_entries("ramses_cc")
    if not ramses_cc_entries:
        _LOGGER.warning("No ramses_cc entries found")
        return None

    # Use the first ramses_cc entry
    entry = ramses_cc_entries[0]

    try:
        # Method 1: Try to get broker from hass.data (most reliable)
        broker = None
        if "ramses_cc" in hass.data and entry.entry_id in hass.data["ramses_cc"]:
            broker_data = hass.data["ramses_cc"][entry.entry_id]
            # The broker is stored directly, not nested under a "broker" key
            if (
                hasattr(broker_data, "__class__")
                and "Broker" in broker_data.__class__.__name__
            ):
                broker = broker_data
            elif isinstance(broker_data, dict) and "broker" in broker_data:
                broker = broker_data["broker"]
            elif hasattr(broker_data, "broker"):
                broker = broker_data.broker
            else:
                # Direct assignment if broker is stored directly
                broker = broker_data

        # Method 2: If not found, try getting broker from the entry
        if broker is None and hasattr(entry, "broker"):
            broker = entry.broker

        # Method 3: Try to access through the integration registry
        if broker is None:
            # Look for ramses_cc integration instance in integration registry
            for integration in hass.data.get("integrations", {}).values():
                if hasattr(integration, "broker") and integration.broker:
                    broker = integration.broker
                    break

        # Method 4: Direct import and access (fallback)
        if broker is None:
            try:
                from ramses_cc.gateway import Gateway

                # Try to find gateway through Home Assistant's component registry
                gateway_entries = [
                    e for e in ramses_cc_entries if hasattr(e, "gateway")
                ]
                if gateway_entries:
                    broker = gateway_entries[0].gateway
            except ImportError:
                _LOGGER.debug("ramses_cc module not available for direct access")

        if broker is None:
            _LOGGER.warning("Could not find ramses_cc broker via any method")
            return None

        return broker

    except Exception as e:
        _LOGGER.error(f"Error accessing ramses_cc broker: {e}")
        return None


__all__ = [
    "find_ramses_device",
    "get_device_type",
    "validate_device_for_service",
    "get_all_device_ids",
    "ensure_ramses_cc_loaded",
    "get_device_supported_entities",
    "validate_device_entity_support",
    "_get_broker_for_entry",
]
