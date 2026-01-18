import logging
from typing import TYPE_CHECKING, Any

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.core import Event, HomeAssistant

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
        vol.Optional("device_id"): str,
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
        device_id=msg.get("device_id"),
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


@websocket_api.websocket_command(  # type: ignore[untyped-decorator]
    {
        vol.Required("type"): "ramses_extras/ramses_debugger/traffic/subscribe_stats",
        vol.Optional("device_id"): str,
        vol.Optional("src"): str,
        vol.Optional("dst"): str,
        vol.Optional("code"): str,
        vol.Optional("verb"): str,
        vol.Optional("limit", default=200): vol.All(int, vol.Range(min=0, max=5000)),
        vol.Optional("throttle_ms", default=1000): vol.All(
            int,
            vol.Range(min=0, max=30000),
        ),
    }
)
@websocket_api.async_response  # type: ignore[untyped-decorator]
async def ws_traffic_subscribe_stats(
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

    device_id = msg.get("device_id")
    src = msg.get("src")
    dst = msg.get("dst")
    code = msg.get("code")
    verb = msg.get("verb")
    limit = msg.get("limit", 200)
    throttle_ms = msg.get("throttle_ms", 1000)

    throttle_s = max(0.0, float(throttle_ms) / 1000.0)
    last_sent: float = 0.0

    def _send_snapshot() -> None:
        snapshot = collector.get_stats(
            device_id=device_id,
            src=src,
            dst=dst,
            code=code,
            verb=verb,
            limit=limit,
        )
        connection.send_message(websocket_api.event_message(msg["id"], snapshot))

    def _on_message(event: Event[dict[str, Any]]) -> None:
        nonlocal last_sent

        payload = event.data or {}
        ev_src = payload.get("src")
        ev_dst = payload.get("dst")
        if device_id and device_id not in (ev_src, ev_dst):
            return

        if src and ev_src != src:
            return
        if dst and ev_dst != dst:
            return

        ev_code = payload.get("code")
        if code and ev_code != code:
            return

        ev_verb = payload.get("verb")
        if verb and ev_verb != verb:
            return

        if throttle_s == 0:
            _send_snapshot()
            return

        loop = getattr(hass, "loop", None)
        now = loop.time() if loop is not None else 0.0
        if now - last_sent < throttle_s:
            return

        last_sent = now
        _send_snapshot()

    unsub = hass.bus.async_listen("ramses_cc_message", _on_message)

    if not hasattr(connection, "subscriptions"):
        connection.subscriptions = {}
    connection.subscriptions[msg["id"]] = unsub

    connection.send_result(msg["id"], {"success": True})
    _send_snapshot()
