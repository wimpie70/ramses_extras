import logging
from typing import TYPE_CHECKING, Any

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant

from custom_components.ramses_extras.const import DOMAIN

from .const import DOMAIN as RAMSES_DEBUGGER_DOMAIN
from .traffic_collector import TrafficCollector

if TYPE_CHECKING:
    from homeassistant.components.websocket_api import WebSocket

_LOGGER = logging.getLogger(__name__)


def _get_traffic_collector(hass: HomeAssistant) -> TrafficCollector | None:
    domain_data = hass.data.get(DOMAIN)
    if not isinstance(domain_data, dict):
        return None

    debugger_data = domain_data.get(RAMSES_DEBUGGER_DOMAIN)
    if not isinstance(debugger_data, dict):
        return None

    collector = debugger_data.get("traffic_collector")
    if not isinstance(collector, TrafficCollector):
        return None

    return collector


@websocket_api.websocket_command(  # type: ignore[untyped-decorator]
    {
        vol.Required("type"): "ramses_extras/ramses_debugger/traffic/get_stats",
        vol.Optional("src"): str,
        vol.Optional("dst"): str,
        vol.Optional("code"): str,
        vol.Optional("verb"): str,
        vol.Optional("limit", default=200): vol.All(int, vol.Range(min=0, max=5000)),
    }
)
@websocket_api.async_response  # type: ignore[untyped-decorator]
async def ws_traffic_get_stats(
    hass: HomeAssistant,
    connection: "WebSocket",
    msg: dict[str, Any],
) -> None:
    collector = _get_traffic_collector(hass)
    if collector is None:
        connection.send_error(
            msg["id"],
            "collector_not_ready",
            "Traffic collector is not available (is the feature enabled?)",
        )
        return

    stats = collector.get_stats(
        src=msg.get("src"),
        dst=msg.get("dst"),
        code=msg.get("code"),
        verb=msg.get("verb"),
        limit=msg.get("limit", 200),
    )

    connection.send_result(msg["id"], stats)


@websocket_api.websocket_command(  # type: ignore[untyped-decorator]
    {
        vol.Required("type"): "ramses_extras/ramses_debugger/traffic/reset_stats",
    }
)
@websocket_api.async_response  # type: ignore[untyped-decorator]
async def ws_traffic_reset_stats(
    hass: HomeAssistant,
    connection: "WebSocket",
    msg: dict[str, Any],
) -> None:
    collector = _get_traffic_collector(hass)
    if collector is None:
        connection.send_error(
            msg["id"],
            "collector_not_ready",
            "Traffic collector is not available (is the feature enabled?)",
        )
        return

    collector.reset()
    connection.send_result(msg["id"], {"success": True})
