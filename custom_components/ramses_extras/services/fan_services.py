"""Fan control services for Ramses Extras integration."""

import logging
from typing import Any, Optional

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError

from ..const import DOMAIN
from ..helpers.device import (
    ensure_ramses_cc_loaded,
    find_ramses_device,
    get_device_type,
)

_LOGGER = logging.getLogger(__name__)


async def async_set_fan_speed_mode(
    hass: HomeAssistant,
    device_id: str,
    mode: str,
    duration: int | None = None,
    reason: str | None = None,
) -> None:
    """Set fan speed mode for a Ramses device.

    Args:
        device_id: The Ramses device ID (e.g., "32:153289")
        mode: Fan mode ("low", "medium", "high", "auto", "away", "boost")
        duration: Optional duration in minutes after which to restore auto mode
        reason: Optional reason for the manual override
    """
    _LOGGER.info(
        f"Setting fan mode to {mode} for device {device_id} (reason: {reason})"
    )

    # Validate mode
    valid_modes = ["low", "medium", "high", "auto", "away", "boost"]
    if mode not in valid_modes:
        raise HomeAssistantError(
            f"Invalid fan mode: {mode}. Valid modes: {valid_modes}"
        )

    # Ensure Ramses CC is loaded
    ensure_ramses_cc_loaded(hass)

    # Find and validate the device
    device = find_ramses_device(hass, device_id)
    if not device:
        raise HomeAssistantError(f"Device {device_id} not found in Ramses CC")

    # Validate device supports this service
    from ..helpers.device import validate_device_for_service

    if not validate_device_for_service(hass, device_id, "set_fan_speed_mode"):
        raise HomeAssistantError(
            f"Device {device_id} does not support fan speed control"
        )

    # Set the fan mode via ramses_cc
    try:
        if hasattr(device, "set_fan_mode"):
            await device.set_fan_mode(mode)
            _LOGGER.info(f"Successfully set fan mode to {mode} for device {device_id}")
        else:
            # Try ramses_cc service call
            await hass.services.async_call(
                "ramses_cc",
                "set_fan_mode",
                {"device_id": device_id, "mode": mode},
                blocking=True,
            )
            _LOGGER.info(
                f"Successfully set fan mode via ramses_cc service "
                f"for device {device_id}"
            )

        # Log the manual override
        await hass.services.async_call(
            "logbook",
            "log",
            {
                "name": "Fan Control",
                "message": f"Manual fan mode set to {mode} "
                f"({reason or 'No reason provided'})",
                "entity_id": f"sensor.{device_id.replace(':', '_')}_fan_mode",
            },
        )

        # If duration specified, schedule restoration to auto mode
        if duration and mode != "auto":
            hass.async_create_task(
                _restore_auto_mode_after_delay(hass, device_id, duration)
            )

    except Exception as e:
        _LOGGER.error(f"Failed to set fan mode for device {device_id}: {e}")
        raise HomeAssistantError(f"Failed to set fan mode: {e}") from e


async def _restore_auto_mode_after_delay(
    hass: HomeAssistant, device_id: str, delay_minutes: int
) -> None:
    """Restore fan to auto mode after specified delay."""
    import asyncio

    await asyncio.sleep(delay_minutes * 60)  # Convert minutes to seconds

    try:
        await async_set_fan_speed_mode(
            hass,
            device_id,
            "auto",
            reason="Automatic restoration after manual override",
        )
        _LOGGER.info(
            f"Restored device {device_id} to auto mode after {delay_minutes} minutes"
        )
    except Exception as e:
        _LOGGER.error(f"Failed to restore auto mode for device {device_id}: {e}")


def register_fan_services(hass: HomeAssistant) -> None:
    """Register fan control services."""
    from homeassistant.helpers import service

    from ..const import SERVICE_SCHEMAS

    # Register the set_fan_speed_mode service
    service_schema = SERVICE_SCHEMAS["set_fan_speed_mode"]

    # Build voluptuous schema
    schema_dict = {}
    for param_name, param_config in service_schema.items():
        if param_config["required"]:
            if param_config.get("valid_values"):
                schema_dict[vol.Required(param_name)] = vol.In(
                    param_config["valid_values"]
                )
            else:
                schema_dict[vol.Required(param_name)] = (
                    str  # Default to string for required params
                )
        else:
            if param_config.get("valid_values"):
                schema_dict[vol.Optional(param_name)] = vol.In(
                    param_config["valid_values"]
                )
            else:
                schema_dict[vol.Optional(param_name)] = str

    async def handle_set_fan_speed_mode(call: ServiceCall) -> None:
        """Handle set_fan_speed_mode service call."""
        await async_set_fan_speed_mode(
            hass,
            call.data["device_id"],
            call.data["mode"],
            call.data.get("duration"),
            call.data.get("reason"),
        )

    # Register the service
    hass.services.async_register(
        DOMAIN,
        "set_fan_speed_mode",
        handle_set_fan_speed_mode,
        schema=vol.Schema(schema_dict),
    )

    _LOGGER.info("Registered set_fan_speed_mode service")
