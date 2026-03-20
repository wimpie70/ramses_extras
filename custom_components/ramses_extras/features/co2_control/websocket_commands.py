"""CO2 Control WebSocket Commands."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback

from custom_components.ramses_extras.const import DOMAIN

_LOGGER = logging.getLogger(__name__)


@callback  # type: ignore[untyped-decorator]
def async_register_websocket_commands(hass: HomeAssistant) -> None:
    """Register CO2 control WebSocket commands.

    Args:
        hass: Home Assistant instance
    """
    websocket_api.async_register_command(hass, handle_get_co2_status)
    websocket_api.async_register_command(hass, handle_get_zone_details)
    websocket_api.async_register_command(hass, handle_update_zone_config)
    websocket_api.async_register_command(hass, handle_get_co2_history)

    _LOGGER.debug("CO2 control WebSocket commands registered")


@websocket_api.websocket_command(  # type: ignore[untyped-decorator]
    {
        "type": "ramses_extras/co2/get_status",
        "device_id": str,
    }
)
@callback  # type: ignore[untyped-decorator]
def handle_get_co2_status(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Handle get CO2 status WebSocket command.

    Args:
        hass: Home Assistant instance
        connection: WebSocket connection
        msg: Message data
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


@websocket_api.websocket_command(  # type: ignore[untyped-decorator]
    {
        "type": "ramses_extras/co2/get_zone_details",
        "device_id": str,
        "zone_id": str,
    }
)
@callback  # type: ignore[untyped-decorator]
def handle_get_zone_details(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Handle get zone details WebSocket command.

    Args:
        hass: Home Assistant instance
        connection: WebSocket connection
        msg: Message data
    """
    device_id = msg.get("device_id")
    zone_id = msg.get("zone_id")

    try:
        domain_data = hass.data.get(DOMAIN, {})
        co2_automation = domain_data.get("co2_automation")

        if not co2_automation:
            connection.send_error(msg["id"], "not_found", "CO2 automation not found")
            return

        zone_manager = co2_automation._zone_managers.get(device_id)
        if not zone_manager:
            connection.send_error(
                msg["id"], "not_found", f"Zone manager not found for device {device_id}"
            )
            return

        zone = zone_manager.zones.get(zone_id)
        if not zone:
            connection.send_error(msg["id"], "not_found", f"Zone {zone_id} not found")
            return

        zone_details = {
            "zone_id": zone.zone_id,
            "zone_name": zone.zone_name,
            "sensor_entity": zone.sensor_entity,
            "threshold": zone.threshold,
            "enabled": zone.enabled,
            "current_co2": zone.current_co2,
            "is_triggered": zone.is_triggered,
            "trigger_count": zone.trigger_count,
            "last_update": zone.last_update.isoformat() if zone.last_update else None,
            "valve_entity": zone.valve_entity,
        }

        connection.send_result(msg["id"], zone_details)

    except Exception as e:
        _LOGGER.error("Error getting zone details: %s", e)
        connection.send_error(msg["id"], "unknown_error", str(e))


@websocket_api.websocket_command(  # type: ignore[untyped-decorator]
    {
        "type": "ramses_extras/co2/update_zone",
        "device_id": str,
        "zone_id": str,
        "updates": dict,
    }
)
@callback  # type: ignore[untyped-decorator]
def handle_update_zone_config(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Handle update zone config WebSocket command.

    Args:
        hass: Home Assistant instance
        connection: WebSocket connection
        msg: Message data
    """
    device_id = msg.get("device_id")
    zone_id = msg.get("zone_id")
    updates = msg.get("updates", {})

    try:
        domain_data = hass.data.get(DOMAIN, {})
        co2_automation = domain_data.get("co2_automation")

        if not co2_automation:
            connection.send_error(msg["id"], "not_found", "CO2 automation not found")
            return

        zone_manager = co2_automation._zone_managers.get(device_id)
        if not zone_manager:
            connection.send_error(
                msg["id"], "not_found", f"Zone manager not found for device {device_id}"
            )
            return

        success = zone_manager.update_zone_config(zone_id, updates)
        if not success:
            connection.send_error(msg["id"], "not_found", f"Zone {zone_id} not found")
            return

        connection.send_result(msg["id"], {"success": True})

    except Exception as e:
        _LOGGER.error("Error updating zone config: %s", e)
        connection.send_error(msg["id"], "unknown_error", str(e))


@websocket_api.websocket_command(  # type: ignore[untyped-decorator]
    {
        "type": "ramses_extras/co2/get_history",
        "device_id": str,
        "hours": int,
    }
)
@callback  # type: ignore[untyped-decorator]
def handle_get_co2_history(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Handle get CO2 history WebSocket command.

    Args:
        hass: Home Assistant instance
        connection: WebSocket connection
        msg: Message data
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
