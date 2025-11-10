"""Device helper utilities for Ramses Extras framework.

This module provides reusable device utilities that are shared across
all features, including device finding, validation, and type detection.
"""

import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from ....const import (
    AVAILABLE_FEATURES,
    DEVICE_SERVICE_MAPPING,
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
    from ....helpers.broker import get_ramses_broker

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
    from ....helpers.broker import get_ramses_broker

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

    from ....helpers.broker import get_ramses_broker

    if not get_ramses_broker(hass):
        raise HomeAssistantError(
            "Ramses CC broker is not available. "
            "Please check your Ramses CC configuration."
        )


def get_device_capabilities(device: Any) -> list[str]:
    """Get the capabilities of a device based on its type.

    Args:
        device: The Ramses device object

    Returns:
        List of capability strings
    """
    device_type = get_device_type(device)

    # Map device types to their capabilities
    capability_mapping = {
        "HvacVentilator": [
            "fan_speed_control",
            "humidity_monitoring",
            "dehumidification",
            "ventilation_levels",
        ],
        "HvacSystem": ["temperature_control", "zone_management", "schedule_control"],
        "Remote": ["temperature_sensing", "humidity_sensing", "occupancy_detection"],
    }

    return capability_mapping.get(device_type, [])


def filter_devices_by_capability(hass: HomeAssistant, capability: str) -> list[str]:
    """Get all devices that support a specific capability.

    Args:
        hass: Home Assistant instance
        capability: The capability to filter by

    Returns:
        List of device IDs that support the capability
    """
    device_ids = get_all_device_ids(hass)
    capable_devices = []

    for device_id in device_ids:
        device = find_ramses_device(hass, device_id)
        if device:
            capabilities = get_device_capabilities(device)
            if capability in capabilities:
                capable_devices.append(device_id)

    return capable_devices


# Device type to entity mapping helpers
def get_device_supported_entities(device_type: str) -> list[str]:
    """Get the list of entities supported by a device type.

    Args:
        device_type: The device type (e.g., "HvacVentilator")

    Returns:
        List of supported entity names
    """
    from ... import get_device_mapping

    mapping = get_device_mapping(device_type)
    if not mapping:
        return []

    supported_entities = []
    for entity_type, entities in mapping.items():
        supported_entities.extend(entities)

    return supported_entities


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


__all__ = [
    "find_ramses_device",
    "get_device_type",
    "validate_device_for_service",
    "get_all_device_ids",
    "ensure_ramses_cc_loaded",
    "get_device_capabilities",
    "filter_devices_by_capability",
    "get_device_supported_entities",
    "validate_device_entity_support",
]
