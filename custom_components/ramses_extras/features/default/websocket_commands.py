"""WebSocket Commands for Default Feature.

This module contains WebSocket commands that are used by multiple features
or provide fundamental device management functionality.
Uses the exact same pattern as the old working implementation.
"""

import logging
from typing import TYPE_CHECKING, Any

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant

from .const import WS_CMD_GET_2411_SCHEMA, WS_CMD_GET_BOUND_REM

if TYPE_CHECKING:
    from homeassistant.components.websocket_api import WebSocket

_LOGGER = logging.getLogger(__name__)


@websocket_api.websocket_command(  # type: ignore[misc]
    {
        vol.Required("type"): WS_CMD_GET_BOUND_REM,
        vol.Required("device_id"): str,
    }
)
@websocket_api.async_response  # type: ignore[misc]
async def ws_get_bound_rem(
    hass: HomeAssistant, connection: "WebSocket", msg: dict[str, Any]
) -> None:
    """Return bound REM info for a Ramses device (Default feature)."""
    device_id = msg["device_id"]

    _LOGGER.debug(f"Executing get_bound_rem for device {device_id}")

    # Get Ramses data from hass.data
    ramses_data = hass.data.get("ramses_cc")
    if not ramses_data:
        connection.send_error(
            msg["id"], "ramses_cc_not_found", "Ramses CC integration not loaded"
        )
        return

    result = None
    try:
        # Find device and get bound REM (same logic as old implementation)
        for _entry_id, data in ramses_data.items():
            # Handle both direct broker storage and dict storage
            if hasattr(data, "__class__") and "Broker" in data.__class__.__name__:
                broker = data
            elif isinstance(data, dict) and "broker" in data:
                broker = data["broker"]
            else:
                continue
            if not broker:
                continue
            # Each broker has devices as a list (_devices)
            devices = getattr(broker, "_devices", None)
            if devices is None:
                devices = getattr(broker, "devices", [])
            if not devices:
                continue

            # Find device by ID
            for device in devices:
                device_id_attr = getattr(device, "id", str(device))
                if device_id_attr == device_id:
                    if hasattr(device, "get_bound_rem"):
                        bound = device.get_bound_rem()
                        result = bound.id if bound else None
                    else:
                        result = None
                    break
            if result is not None:
                break

        if result is None:
            response_data = {"device_id": device_id, "bound_rem": None}
            _LOGGER.debug(f"No bound REM found for device {device_id}")
        else:
            response_data = {"device_id": device_id, "bound_rem": result}
            _LOGGER.debug(f"Found bound REM {result} for device {device_id}")

        connection.send_result(msg["id"], response_data)

    except Exception as error:
        _LOGGER.error(f"Error getting bound REM for device {device_id}: {error}")
        connection.send_error(
            msg["id"],
            "get_bound_rem_failed",
            f"Failed to get bound REM for device {device_id}: {str(error)}",
        )


@websocket_api.websocket_command(  # type: ignore[misc]
    {
        vol.Required("type"): WS_CMD_GET_2411_SCHEMA,
        vol.Required("device_id"): str,
    }
)
@websocket_api.async_response  # type: ignore[misc]
async def ws_get_2411_schema(
    hass: HomeAssistant, connection: "WebSocket", msg: dict[str, Any]
) -> None:
    """Return 2411 parameter schema for a Ramses device (Default feature)."""
    device_id = msg["device_id"]

    _LOGGER.debug(f"Executing get_2411_schema for device {device_id}")

    # Get Ramses data from hass.data
    ramses_data = hass.data.get("ramses_cc")
    if not ramses_data:
        connection.send_error(
            msg["id"], "ramses_cc_not_found", "Ramses CC integration not loaded"
        )
        return

    try:
        # Find device
        device = None
        for _entry_id, data in ramses_data.items():
            # Handle both direct broker storage and dict storage
            if hasattr(data, "__class__") and "Broker" in data.__class__.__name__:
                broker = data
            elif isinstance(data, dict) and "broker" in data:
                broker = data["broker"]
            else:
                continue
            if not broker:
                continue
            # Each broker has devices as a list (_devices)
            devices = getattr(broker, "_devices", None)
            if devices is None:
                devices = getattr(broker, "devices", [])
            if not devices:
                continue

            # Find device by ID
            for dev in devices:
                device_id_attr = getattr(dev, "id", str(dev))
                if device_id_attr == device_id:
                    device = dev
                    break
            if device:
                break

        if not device:
            connection.send_error(
                msg["id"], "device_not_found", f"Device {device_id} not found"
            )
            return

        # Get 2411 schema from device
        if hasattr(device, "get_2411_schema"):
            schema = await device.get_2411_schema()
        else:
            # Fallback to device-type specific schema
            device_type = getattr(device, "type", "HvacVentilator")
            schema = get_2411_schema_for_device_type(device_type)

        connection.send_result(msg["id"], schema)
        _LOGGER.debug(f"Returned 2411 schema for device {device_id}")

    except Exception as error:
        _LOGGER.error(f"Error getting 2411 schema for device {device_id}: {error}")
        connection.send_error(
            msg["id"],
            "get_2411_schema_failed",
            f"Failed to get 2411 schema for device {device_id}: {str(error)}",
        )


# Default fallback schema parameters for HVAC devices
DEFAULT_2411_SCHEMA_PARAMS: list[str] = [
    "31",  # Temperature offset
    "75",  # Comfort temperature
    "89",  # Fan speed minimum
    "90",  # Fan speed maximum
]


def _get_fallback_2411_schema() -> dict[str, Any]:
    """Get fallback 2411 schema when device-specific schema is not available.

    Returns:
        Basic parameter schema for HVAC devices
    """
    schema = {}

    # Create schema for common parameters
    for param_id in DEFAULT_2411_SCHEMA_PARAMS:
        schema[param_id] = {
            "description": f"Parameter {param_id}",
            "name": f"Parameter {param_id}",
            "min_value": 0,
            "max_value": 100,
            "default_value": 50,
            "precision": 1,
            "data_type": "01",
            "unit": "",
        }

    return schema


def get_2411_schema_for_device_type(device_type: str) -> dict[str, Any]:
    """Get 2411 schema for a specific device type.

    Args:
        device_type: Type of device (e.g., "HvacVentilator")

    Returns:
        Device type specific parameter schema from ramses_tx
    """
    try:
        # Import the comprehensive schema from ramses_tx
        from ramses_tx.ramses import _2411_PARAMS_SCHEMA

        return dict(_2411_PARAMS_SCHEMA)  # Convert to dict[str, Any] explicitly
    except ImportError:
        _LOGGER.warning(
            "Could not import _2411_PARAMS_SCHEMA from ramses_tx, using fallback"
        )
        return _get_fallback_2411_schema()


def get_available_2411_parameters() -> list[str]:
    """Get list of available 2411 parameters.

    Returns:
        List of parameter IDs that are available in the schema
    """
    try:
        # Import the comprehensive schema from ramses_tx
        from ramses_tx.ramses import _2411_PARAMS_SCHEMA

        return list(_2411_PARAMS_SCHEMA.keys())
    except ImportError:
        _LOGGER.warning(
            "Could not import _2411_PARAMS_SCHEMA from ramses_tx, using fallback"
        )
        return DEFAULT_2411_SCHEMA_PARAMS.copy()


def register_ws_commands(hass: HomeAssistant) -> None:
    """Register all websocket commands for Ramses Extras default feature."""
    # Commands are automatically registered when functions are defined with decorators
    # This function exists for compatibility with the old architecture
    _LOGGER.info("Default feature WebSocket commands registered (using HA decorators)")


# For backwards compatibility with old approach
def get_default_websocket_commands() -> dict[str, Any]:
    """Get all WebSocket commands for the default feature.

    Returns:
        Dictionary mapping command names to handler functions
    """
    return {
        "get_bound_rem": ws_get_bound_rem,
        "get_2411_schema": ws_get_2411_schema,
    }


def get_command_info() -> dict[str, dict]:
    """Get information about available commands for this feature.

    Returns:
        Dictionary containing command information
    """
    return {
        "get_bound_rem": {
            "name": "get_bound_rem",
            "type": WS_CMD_GET_BOUND_REM,
            "description": "Get bound REM device for a device",
            "feature": "default",
        },
        "get_2411_schema": {
            "name": "get_2411_schema",
            "type": WS_CMD_GET_2411_SCHEMA,
            "description": "Get 2411 parameter schema for a device",
            "feature": "default",
        },
    }
