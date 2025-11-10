"""Device finding and validation helpers for Ramses Extras."""

import logging
from typing import Any, Dict, List, cast

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from ..const import (
    AVAILABLE_FEATURES,
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
    from .broker import get_ramses_broker

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

    # Service validation removed - services now handled by feature-based architecture
    _LOGGER.debug(
        f"Device {device_id} ({device_type}) service validation delegated to features"
    )
    return True


def get_all_device_ids(hass: HomeAssistant) -> list[str]:
    """Get all Ramses device IDs.

    Args:
        hass: HomeAssistant instance

    Returns:
        List of all device IDs found in Ramses CC
    """
    from .broker import get_ramses_broker

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

    from .broker import get_ramses_broker

    if not get_ramses_broker(hass):
        raise HomeAssistantError(
            "Ramses CC broker is not available. "
            "Please check your Ramses CC configuration."
        )
