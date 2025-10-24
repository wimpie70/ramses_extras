"""Device finding and validation helpers for Ramses Extras."""

import logging
from typing import Any, List, Optional

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from ..const import DEVICE_SERVICE_MAPPING, DOMAIN

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
        _LOGGER.debug(f"No Ramses broker available for device {device_id}")
        return None

    devices = getattr(broker, "devices", {})
    device = devices.get(device_id)

    if device:
        _LOGGER.debug(f"Found device {device_id} ({device.__class__.__name__})")
        return device
    _LOGGER.debug(f"Device {device_id} not found in Ramses broker")
    return None


def get_ramses_broker(hass: HomeAssistant) -> Any | None:
    """Get the Ramses CC broker safely.

    Args:
        hass: Home Assistant instance

    Returns:
        The Ramses broker object or None if not available
    """
    ramses_data = hass.data.get("ramses_cc")
    if not ramses_data:
        _LOGGER.debug("Ramses CC integration not loaded")
        return None

    # Handle the case where ramses_data contains broker objects directly
    # (this happens when there's a single entry)
    if hasattr(ramses_data, "client") and hasattr(ramses_data, "devices"):
        _LOGGER.debug("Found Ramses broker directly in data")
        return ramses_data

    # Get the first available broker (handle multiple entries)
    # If ramses_data is a dict, iterate through entries
    if isinstance(ramses_data, dict):
        for entry_id, data in ramses_data.items():
            # If data is a broker object (has client attribute), use it directly
            if hasattr(data, "client") and hasattr(data, "devices"):
                _LOGGER.debug(f"Found Ramses broker for entry {entry_id}")
                return data
            # Otherwise, try to get broker from nested dict structure
            if isinstance(data, dict):
                broker = data.get("broker")
                if broker:
                    _LOGGER.debug(f"Found Ramses broker for entry {entry_id}")
                    return broker

    _LOGGER.debug("No Ramses broker found in any entry")
    return None


def get_device_type(device: Any) -> str:
    """Get device type name safely.

    Args:
        device: The Ramses device object

    Returns:
        Device type name (e.g., "HvacVentilator")
    """
    try:
        device_type = device.__class__.__name__
        _LOGGER.debug(f"Device type for {device.id}: {device_type}")
        return device_type
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

    _LOGGER.debug(f"Device {device_id} ({device_type}) supports service {service_name}")
    return True


def get_all_device_ids(hass: HomeAssistant) -> list[str]:
    """Get all Ramses device IDs.

    Args:
        hass: Home Assistant instance

    Returns:
        List of all device IDs found in Ramses CC
    """
    broker = get_ramses_broker(hass)
    if not broker:
        _LOGGER.debug("No Ramses broker available, returning empty device list")
        return []

    devices = getattr(broker, "devices", {})
    device_ids = list(devices.keys())

    _LOGGER.debug(f"Found {len(device_ids)} Ramses devices: {device_ids}")
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
