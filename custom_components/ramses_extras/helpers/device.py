"""Device finding and validation helpers for Ramses Extras."""

import logging
from typing import Any, List, Optional

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from ..const import DEVICE_SERVICE_MAPPING, DOMAIN, SERVICE_REGISTRY

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
