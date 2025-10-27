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
    _LOGGER.debug("Looking up device %s", device_id)

    if "ramses_cc" in hass.data:
        _LOGGER.debug("ramses_cc keys: %s", list(hass.data["ramses_cc"].keys()))

    broker = get_ramses_broker(hass)
    if not broker:
        _LOGGER.warning("No Ramses broker available for device %s", device_id)
        return None

    _LOGGER.debug("Found broker: %s", broker.__class__.__name__)

    # Try different ways to access devices from the broker
    devices = None
    source = ""

    if hasattr(broker, "_devices"):
        devices = broker._devices
        source = "_devices"
    elif hasattr(broker, "devices"):
        devices = broker.devices
        source = "devices"
    elif hasattr(broker, "client") and hasattr(broker.client, "devices"):
        devices = broker.client.devices
        source = "client.devices"
    elif hasattr(broker, "get_devices"):
        devices = broker.get_devices()
        source = "get_devices()"

    if devices is not None:
        _LOGGER.debug(
            "Found %d devices via %s",
            len(devices) if hasattr(devices, "__len__") else "?",
            source,
        )

    if devices is None:
        _LOGGER.warning("No devices found in broker")
        return None

    _LOGGER.debug("Devices container type: %s", type(devices).__name__)

    # Handle devices as a list of objects
    if isinstance(devices, list | set):
        devices_list = list(devices)
        _LOGGER.debug("Checking %d devices", len(devices_list))

        for device in devices_list:
            try:
                # Try different ways to get the device ID
                device_id_attr = None
                if hasattr(device, "id"):
                    device_id_attr = device.id
                elif hasattr(device, "device_id"):
                    device_id_attr = device.device_id
                elif hasattr(device, "device"):
                    device_id_attr = getattr(device, "device", None)

                if device_id_attr is not None and str(device_id_attr) == str(device_id):
                    _LOGGER.info(
                        "Found device %s (%s)", device_id, device.__class__.__name__
                    )
                    return device

            except Exception as ex:
                _LOGGER.debug("Error checking device: %s", str(ex), exc_info=True)

        _LOGGER.warning("Device %s not found in device list", device_id)
        return None

    # Handle devices as a dictionary
    if isinstance(devices, dict):
        _LOGGER.debug("Checking %d devices in dict", len(devices))

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
    if _LOGGER.isEnabledFor(logging.DEBUG):
        _LOGGER.debug(
            "Available devices: %s",
            [getattr(d, "id", str(d)) for d in devices]
            if hasattr(devices, "__iter__")
            else "N/A",
        )
    return None


def get_ramses_broker(hass: HomeAssistant) -> Any | None:
    """Get the Ramses CC broker safely.

    Args:
        hass: Home Assistant instance

    Returns:
        The Ramses broker object or None if not available
    """
    _LOGGER.debug("Starting broker lookup")

    if not hasattr(hass, "data") or not isinstance(hass.data, dict):
        _LOGGER.error("Invalid hass.data structure")
        return None

    ramses_data = hass.data.get("ramses_cc")

    if not ramses_data:
        _LOGGER.warning("Ramses CC integration not loaded in hass.data")
        if _LOGGER.isEnabledFor(logging.DEBUG):
            _LOGGER.debug("Available top-level keys: %s", list(hass.data.keys()))
        return None

    # Check if ramses_data is the broker itself
    if ramses_data.__class__.__name__ == "RamsesBroker":
        _LOGGER.debug("Found RamsesBroker instance directly")
        return ramses_data

    # Handle the case where ramses_data is a dictionary of entries
    if isinstance(ramses_data, dict):
        _LOGGER.debug("Checking ramses_data dict with %d entries", len(ramses_data))

        for entry_id, data in ramses_data.items():
            _LOGGER.debug(
                "Checking entry %s (type: %s)", entry_id, data.__class__.__name__
            )

            # If data is a RamsesBroker instance
            if data.__class__.__name__ == "RamsesBroker":
                _LOGGER.debug("Found RamsesBroker in entry %s", entry_id)
                return data

            # If data is a dictionary, look for a broker inside it
            if isinstance(data, dict):
                # Check for direct broker reference
                if (
                    broker := data.get("broker")
                ) and broker.__class__.__name__ == "RamsesBroker":
                    _LOGGER.debug("Found RamsesBroker in entry %s dict", entry_id)
                    return broker

                # Check all values in the nested dict
                for key, value in data.items():
                    if (
                        hasattr(value, "__class__")
                        and value.__class__.__name__ == "RamsesBroker"
                    ):
                        _LOGGER.debug(
                            "Found RamsesBroker in entry %s at key %s", entry_id, key
                        )
                        return value

                    # Also check for devices attribute which
                    #  indicates it might be a broker
                    if hasattr(value, "devices"):
                        _LOGGER.debug(
                            "Found object with 'devices' in entry %s at %s",
                            entry_id,
                            key,
                        )
                        return value

    _LOGGER.warning("No Ramses broker found in ramses_data")
    if _LOGGER.isEnabledFor(logging.DEBUG):
        _LOGGER.debug("ramses_data content type: %s", type(ramses_data).__name__)
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
        hass: HomeAssistant instance

    Returns:
        List of all device IDs found in Ramses CC
    """
    _LOGGER.debug("Starting device ID discovery")

    broker = get_ramses_broker(hass)
    if not broker:
        _LOGGER.warning("No Ramses broker available to get device IDs")
        return []

    _LOGGER.debug("Found broker, getting devices")
    devices = getattr(broker, "devices", {})

    device_ids = []

    if isinstance(devices, list):
        _LOGGER.debug("Processing %d devices from list", len(devices))
        device_ids = [str(d.id) for d in devices if hasattr(d, "id")]
    elif isinstance(devices, dict):
        _LOGGER.debug("Processing %d devices from dict", len(devices))
        device_ids = [str(k) for k in devices.keys()]
    else:
        _LOGGER.warning("Unexpected devices type: %s", type(devices).__name__)

    _LOGGER.info("Found %d Ramses devices", len(device_ids))
    if _LOGGER.isEnabledFor(logging.DEBUG):
        _LOGGER.debug("Device IDs: %s", device_ids)
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
