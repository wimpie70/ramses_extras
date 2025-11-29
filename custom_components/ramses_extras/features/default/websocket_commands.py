"""WebSocket Commands for Default Feature.

This module provides WebSocket commands for device control that are available
to all features. These commands use the new command framework with queuing
and rate limiting.
"""

import logging
import time
from typing import TYPE_CHECKING, Any

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant

from ...framework.helpers.ramses_commands import CommandResult, RamsesCommands

if TYPE_CHECKING:
    from homeassistant.components.websocket_api import WebSocket

_LOGGER = logging.getLogger(__name__)


@websocket_api.websocket_command(  # type: ignore[untyped-decorator]
    {
        vol.Required("type"): "ramses_extras/get_bound_rem",
        vol.Required("device_id"): str,
    }
)
@websocket_api.async_response  # type: ignore[untyped-decorator]
async def ws_get_bound_rem(
    hass: HomeAssistant, connection: "WebSocket", msg: dict[str, Any]
) -> None:
    """Get bound REM device information for a device.

    This command retrieves information about the bound REM device
    that is needed for proper communication with FAN devices.
    """
    device_id = msg["device_id"]

    _LOGGER.debug(f"Getting bound REM device for {device_id}")

    try:
        # Get RamsesCommands instance
        ramses_commands = RamsesCommands(hass)

        # Get bound REM device
        bound_rem = await ramses_commands._get_bound_rem_device(device_id)

        connection.send_result(
            msg["id"],
            {
                "bound_rem": bound_rem,
                "device_id": device_id,
            },
        )
        _LOGGER.debug(f"Bound REM device for {device_id}: {bound_rem}")

    except Exception as error:
        _LOGGER.error(f"Error getting bound REM device for {device_id}: {error}")
        connection.send_error(
            msg["id"],
            "bound_rem_error",
            f"Failed to get bound REM device: {str(error)}",
        )


@websocket_api.websocket_command(  # type: ignore[untyped-decorator]
    {
        vol.Required("type"): "ramses_extras/get_2411_schema",
        vol.Required("device_id"): str,
    }
)
@websocket_api.async_response  # type: ignore[untyped-decorator]
async def ws_get_2411_schema(
    hass: HomeAssistant, connection: "WebSocket", msg: dict[str, Any]
) -> None:
    """Get 2411 parameter schema for a device.

    This command retrieves the parameter schema information for device
    configuration and parameter editing.
    """
    device_id = msg["device_id"]

    _LOGGER.debug(f"Getting 2411 schema for device {device_id}")

    try:
        # Get the actual 2411 parameter schema from ramses_rf
        from ramses_tx.ramses import _2411_PARAMS_SCHEMA

        # Convert ramses_rf schema format to our UI format
        schema = {}
        for param_id, param_info in _2411_PARAMS_SCHEMA.items():
            # Convert parameter ID to string for JSON compatibility
            param_key = str(param_id)

            # Map ramses_rf schema to our UI schema format
            schema[param_key] = {
                "name": param_info.get("name", f"Parameter {param_id}"),
                "description": param_info.get(
                    "description", param_info.get("name", f"Parameter {param_id}")
                ),
                "unit": param_info.get("unit", ""),
                "min_value": param_info.get("min_value", param_info.get("min", 0)),
                "max_value": param_info.get("max_value", param_info.get("max", 100)),
                "default_value": param_info.get(
                    "default_value", param_info.get("default", 0)
                ),
                "data_type": param_info.get("data_type", "01"),
                "precision": param_info.get("precision", param_info.get("step", 1)),
            }

        connection.send_result(
            msg["id"],
            {
                "schema": schema,
                "device_id": device_id,
            },
        )
        _LOGGER.debug(f"2411 schema retrieved for device {device_id}")

    except Exception as error:
        _LOGGER.error(f"Error getting 2411 schema for device {device_id}: {error}")
        connection.send_error(
            msg["id"],
            "schema_error",
            f"Failed to get parameter schema: {str(error)}",
        )


@websocket_api.websocket_command(  # type: ignore[untyped-decorator]
    {
        vol.Required("type"): "ramses_extras/default/send_fan_command",
        vol.Required("device_id"): str,
        vol.Required("command"): str,
    }
)
@websocket_api.async_response  # type: ignore[untyped-decorator]
async def ws_send_fan_command(
    hass: HomeAssistant, connection: "WebSocket", msg: dict[str, Any]
) -> None:
    """Send a fan command using the new command framework with queuing.

    This WebSocket command uses the registry-based command system with
    per-device queuing to prevent overwhelming the communication layer.
    Available for all features that need fan control.
    """
    device_id = msg["device_id"]
    command = msg["command"]

    _LOGGER.info(
        f"🔌 WebSocket command received: send_fan_command '{command}' "
        f"to device {device_id}"
    )

    try:
        # Get RamsesCommands instance with registry support
        ramses_commands = RamsesCommands(hass)

        # Use the command name directly (JavaScript now sends correct names)
        registry_command = command

        # Check if this is a hardcoded fan command or a registry command
        available_commands = ramses_commands.get_available_commands()
        if registry_command in available_commands:
            # Use the direct fan command method for hardcoded commands
            result = await ramses_commands.send_fan_command(device_id, registry_command)
        else:
            # Use the registry-based command method
            result = await ramses_commands.send_command(device_id, registry_command)

        if result.success:
            # Provide detailed feedback about command processing
            feedback_message = (
                f"Command '{command}' sent successfully"
                if not result.queued
                else f"Command '{command}' queued for device {device_id}"
            )

            connection.send_result(
                msg["id"],
                {
                    "success": True,
                    "command": command,
                    "registry_command": registry_command,
                    "device_id": device_id,
                    "queued": result.queued,
                    "message": feedback_message,
                    "execution_time": result.execution_time,
                },
            )
            _LOGGER.info(f"✅ {feedback_message}")
        else:
            connection.send_error(
                msg["id"],
                "command_failed",
                f"Failed to send command '{command}' to device {device_id}: "
                f"{result.error_message}",
            )

    except Exception as error:
        _LOGGER.error(
            f"Error sending fan command '{command}' to device {device_id}: {error}"
        )
        connection.send_error(
            msg["id"],
            "command_error",
            f"Failed to send fan command '{command}': {str(error)}",
        )


@websocket_api.websocket_command(  # type: ignore[untyped-decorator]
    {
        vol.Required("type"): "ramses_extras/default/set_fan_parameter",
        vol.Required("device_id"): str,
        vol.Required("param_id"): str,
        vol.Required("value"): str,
    }
)
@websocket_api.async_response  # type: ignore[untyped-decorator]
async def ws_set_fan_parameter(
    hass: HomeAssistant, connection: "WebSocket", msg: dict[str, Any]
) -> None:
    """Set a fan parameter using the command framework.

    This provides a queued alternative to direct ramses_cc.set_fan_param calls.
    Available for all features that need parameter control.
    """
    device_id = msg["device_id"]
    param_id = msg["param_id"]
    value = msg["value"]

    _LOGGER.debug(f"Setting fan parameter {param_id}={value} for device {device_id}")

    try:
        # For now, use direct service call since parameter setting
        #  is different from commands
        # TODO: Consider if parameter setting should also use the command framework
        await hass.services.async_call(
            "ramses_cc",
            "set_fan_param",
            {
                "device_id": device_id,
                "param_id": param_id,
                "value": value,
            },
        )

        connection.send_result(
            msg["id"],
            {
                "success": True,
                "device_id": device_id,
                "param_id": param_id,
                "value": value,
            },
        )
        _LOGGER.debug(f"Fan parameter {param_id} set to {value} for device {device_id}")

    except Exception as error:
        _LOGGER.error(
            f"Error setting fan parameter {param_id} for device {device_id}: {error}"
        )
        connection.send_error(
            msg["id"],
            "parameter_error",
            f"Failed to set parameter {param_id}: {str(error)}",
        )


@websocket_api.websocket_command(  # type: ignore[untyped-decorator]
    {
        vol.Required("type"): "ramses_extras/default/get_queue_statistics",
    }
)
@websocket_api.async_response  # type: ignore[untyped-decorator]
async def ws_get_queue_statistics(
    hass: HomeAssistant, connection: "WebSocket", msg: dict[str, Any]
) -> None:
    """Get command queue statistics for monitoring and debugging.

    This provides real-time statistics about command queue performance,
    success rates, and current queue depths for all devices.
    """
    _LOGGER.debug("Getting command queue statistics")

    try:
        # Get RamsesCommands instance
        ramses_commands = RamsesCommands(hass)

        # Get queue statistics
        stats = ramses_commands.get_queue_statistics()

        connection.send_result(
            msg["id"],
            {
                "statistics": stats,
                "timestamp": time.time(),
            },
        )
        _LOGGER.debug("Queue statistics retrieved successfully")

    except Exception as error:
        _LOGGER.error(f"Error getting queue statistics: {error}")
        connection.send_error(
            msg["id"],
            "statistics_error",
            f"Failed to get queue statistics: {str(error)}",
        )


def get_command_info() -> dict[str, dict]:
    """Get information about available commands for this feature.

    Returns:
        Dictionary containing command information
    """
    return {
        "get_bound_rem": {
            "name": "get_bound_rem",
            "type": "ramses_extras/get_bound_rem",
            "description": "Get bound REM device for proper FAN communication",
            "feature": "default",
            "parameters": {
                "device_id": "Device ID (e.g., '32:153289')",
            },
        },
        "get_2411_schema": {
            "name": "get_2411_schema",
            "type": "ramses_extras/get_2411_schema",
            "description": "Get parameter schema for device configuration",
            "feature": "default",
            "parameters": {
                "device_id": "Device ID (e.g., '32:153289')",
            },
        },
        "send_fan_command": {
            "name": "send_fan_command",
            "type": "ramses_extras/default/send_fan_command",
            "description": "Send a fan command using the queued command framework",
            "feature": "default",
            "parameters": {
                "device_id": "Device ID (e.g., '32:153289')",
                "command": "Command name (fan_high, fan_low, fan_auto, bypass_open, "
                "request31DA, etc.)",
            },
        },
        "set_fan_parameter": {
            "name": "set_fan_parameter",
            "type": "ramses_extras/default/set_fan_parameter",
            "description": "Set a fan parameter value",
            "feature": "default",
            "parameters": {
                "device_id": "Device ID (e.g., '32:153289')",
                "param_id": "Parameter ID",
                "value": "Parameter value",
            },
        },
        "get_queue_statistics": {
            "name": "get_queue_statistics",
            "type": "ramses_extras/default/get_queue_statistics",
            "description": "Get command queue statistics for monitoring",
            "feature": "default",
            "parameters": {},
        },
    }
