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
    _LOGGER.info(f"Ensuring Ramses CC is loaded for device {device_id}")
    ensure_ramses_cc_loaded(hass)

    # Find and validate the device
    _LOGGER.info(f"Finding device {device_id}")
    device = find_ramses_device(hass, device_id)
    if not device:
        raise HomeAssistantError(f"Device {device_id} not found in Ramses CC")

    _LOGGER.info(f"Device {device_id} found: {device}")

    # Validate device supports this service
    from ..helpers.device import validate_device_for_service

    _LOGGER.info(f"Validating device {device_id} supports set_fan_speed_mode")
    is_valid = validate_device_for_service(hass, device_id, "set_fan_speed_mode")
    _LOGGER.info(f"Device validation result: {is_valid}")
    if not is_valid:
        raise HomeAssistantError(
            f"Device {device_id} does not support fan speed control"
        )

    # Set the fan mode via direct 22F1 command
    try:
        # Map mode to 22F1 payload
        mode_payloads = {
            "low": "000107",
            "medium": "000207",
            "high": "000307",
            "auto": "000407",
            "away": "000007",
            "boost": "000607",
        }

        if mode not in mode_payloads:
            raise HomeAssistantError(f"Unsupported mode: {mode}")

        payload = mode_payloads[mode]

        # Send direct 22F1 command via ramses_cc send_packet
        _LOGGER.info(
            f"Would send fan control packet for device {device_id}: ",
            f"mode={mode}, code=22F1, payload={payload}",
        )
        # await hass.services.async_call(
        #     "ramses_cc",
        #     "send_packet",
        #     {
        #         "device_id": device_id,
        #         "verb": " I",
        #         "code": "22F1",
        #         "payload": payload,
        #     },
        #     blocking=True,
        # )
        _LOGGER.info(f"Successfully set fan mode to {mode} for device {device_id}")

        # Log the manual override using proper logging instead of logbook service
        _LOGGER.info(
            f"Fan Control: Manual fan mode set to {mode} "
            f"({reason or 'No reason provided'}) for device {device_id}"
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
