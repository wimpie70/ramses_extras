"""CO2 Control WebSocket Commands."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback

from custom_components.ramses_extras.const import DOMAIN

_LOGGER = logging.getLogger(__name__)


@callback
def async_register_websocket_commands(hass: HomeAssistant) -> None:
    """Register CO2 control WebSocket commands.

    :param hass: Home Assistant instance
    """
    websocket_api.async_register_command(hass, handle_get_co2_status)
    websocket_api.async_register_command(hass, handle_get_co2_history)

    _LOGGER.debug("CO2 control WebSocket commands registered")


@websocket_api.websocket_command(
    {
        "type": "ramses_extras/co2/get_status",
        "device_id": str,
    }
)
@callback
def handle_get_co2_status(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Handle get CO2 status WebSocket command.

    :param hass: Home Assistant instance
    :param connection: WebSocket connection
    :param msg: Message data
    """
    try:
        # Get CO2 automation manager from hass.data
        domain_data = hass.data.get(DOMAIN, {})
        co2_automation = domain_data.get("co2_automation")

        if not co2_automation:
            connection.send_error(msg["id"], "not_found", "CO2 automation not found")
            return

        status = co2_automation.get_status()

        connection.send_result(msg["id"], status)

    except Exception as e:
        _LOGGER.error("Error getting CO2 status: %s", e)
        connection.send_error(msg["id"], "unknown_error", str(e))


@websocket_api.websocket_command(
    {
        "type": "ramses_extras/co2/get_history",
        "device_id": str,
        "hours": int,
    }
)
@callback
def handle_get_co2_history(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Handle get CO2 history WebSocket command.

    :param hass: Home Assistant instance
    :param connection: WebSocket connection
    :param msg: Message data
    """
    device_id = msg.get("device_id")
    hours = msg.get("hours", 24)

    try:
        # This would integrate with HA's history component
        # For now, return placeholder
        history = {
            "device_id": device_id,
            "hours": hours,
            "data": [],
            "message": "History integration not yet implemented",
        }

        connection.send_result(msg["id"], history)

    except Exception as e:
        _LOGGER.error("Error getting CO2 history: %s", e)
        connection.send_error(msg["id"], "unknown_error", str(e))


__all__ = ["async_register_websocket_commands"]
