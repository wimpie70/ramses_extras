import logging
from collections import Counter
from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING, Any

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.core import Event, HomeAssistant

from custom_components.ramses_extras.const import DOMAIN

from .const import DOMAIN as RAMSES_DEBUGGER_DOMAIN
from .log_backend import (
    discover_log_files,
    get_configured_log_path,
    get_configured_packet_log_path,
    search_with_context,
    tail_text,
)
from .messages_provider import get_messages_from_sources
from .traffic_collector import TrafficCollector

if TYPE_CHECKING:
    from homeassistant.components.websocket_api import WebSocket

_LOGGER = logging.getLogger(__name__)


def _resolve_log_file(base: Path, file_id: str) -> Path | None:
    allowed = {f.path.name: f.path for f in discover_log_files(base)}
    p = allowed.get(file_id)
    if p is None:
        return None

    try:
        resolved = p.resolve()
        base_dir = base.expanduser().resolve().parent
        if base_dir not in resolved.parents and resolved != base_dir:
            return None
    except OSError:
        return None

    return p


def _resolve_packet_log_file(base: Path, file_id: str) -> Path | None:
    allowed = {f.path.name: f.path for f in discover_log_files(base)}
    p = allowed.get(file_id)
    if p is None:
        return None

    try:
        resolved = p.resolve()
        base_dir = base.expanduser().resolve().parent
        if base_dir not in resolved.parents and resolved != base_dir:
            return None
    except OSError:
        return None

    return p


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
        vol.Optional("traffic_source", default="live"): vol.In(
            ["live", "packet_log", "ha_log"]
        ),
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

    traffic_source = msg.get("traffic_source", "live")
    limit = msg.get("limit", 200)

    if traffic_source == "live":
        stats = collector.get_stats(
            device_id=msg.get("device_id"),
            src=msg.get("src"),
            dst=msg.get("dst"),
            code=msg.get("code"),
            verb=msg.get("verb"),
            limit=limit,
        )
        connection.send_result(msg["id"], stats)
        return

    if traffic_source == "packet_log":
        sources = ["packet_log"]
    elif traffic_source == "ha_log":
        sources = ["ha_log"]
    else:
        sources = ["traffic_buffer"]

    messages = await get_messages_from_sources(
        hass,
        sources,
        src=msg.get("src"),
        dst=msg.get("dst"),
        verb=msg.get("verb"),
        code=msg.get("code"),
        limit=max(0, min(5000, int(limit))),
        dedupe=True,
    )

    by_code: Counter[str] = Counter()
    by_verb: Counter[str] = Counter()
    flows: dict[tuple[str, str], dict[str, Any]] = {}
    started_at: str | None = None

    for m in messages:
        src = m.get("src")
        dst = m.get("dst")
        if not isinstance(src, str) or not isinstance(dst, str):
            continue

        dtm = m.get("dtm")
        if isinstance(dtm, str) and dtm:
            started_at = dtm if started_at is None else min(started_at, dtm)

        code = m.get("code")
        if isinstance(code, str) and code:
            by_code[code] += 1

        verb = m.get("verb")
        if isinstance(verb, str) and verb:
            by_verb[verb] += 1

        key = (src, dst)
        flow = flows.get(key)
        if flow is None:
            flow = {
                "src": src,
                "dst": dst,
                "count_total": 0,
                "last_seen": None,
                "verbs": Counter(),
                "codes": Counter(),
            }
            flows[key] = flow

        flow["count_total"] += 1

        if isinstance(dtm, str) and dtm:
            last_seen = flow.get("last_seen")
            if not isinstance(last_seen, str) or dtm > last_seen:
                flow["last_seen"] = dtm

        if isinstance(verb, str) and verb:
            flow["verbs"][verb] += 1
        if isinstance(code, str) and code:
            flow["codes"][code] += 1

    flow_list = list(flows.values())
    flow_list.sort(key=lambda f: int(f.get("count_total", 0)), reverse=True)

    connection.send_result(
        msg["id"],
        {
            "started_at": started_at or "",
            "total_count": sum(by_code.values()) or sum(by_verb.values()) or 0,
            "by_code": dict(by_code),
            "by_verb": dict(by_verb),
            "flows": [
                {
                    "src": f.get("src", ""),
                    "dst": f.get("dst", ""),
                    "count_total": f.get("count_total", 0),
                    "last_seen": f.get("last_seen"),
                    "verbs": dict(f.get("verbs", {})),
                    "codes": dict(f.get("codes", {})),
                }
                for f in flow_list[: max(0, int(limit))]
            ],
        },
    )


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


@websocket_api.websocket_command(  # type: ignore[untyped-decorator]
    {
        vol.Required("type"): "ramses_extras/ramses_debugger/log/list_files",
    }
)
@websocket_api.async_response  # type: ignore[untyped-decorator]
async def ws_log_list_files(
    hass: HomeAssistant,
    connection: "WebSocket",
    msg: dict[str, Any],
) -> None:
    base = get_configured_log_path(hass)
    files = await hass.async_add_executor_job(discover_log_files, base)
    connection.send_result(
        msg["id"],
        {
            "base": str(base),
            "files": [
                {
                    "file_id": f.file_id,
                    "size": f.size,
                    "modified_at": f.modified_at,
                }
                for f in files
            ],
        },
    )


@websocket_api.websocket_command(  # type: ignore[untyped-decorator]
    {
        vol.Required("type"): "ramses_extras/ramses_debugger/packet_log/list_files",
    }
)
@websocket_api.async_response  # type: ignore[untyped-decorator]
async def ws_packet_log_list_files(
    hass: HomeAssistant,
    connection: "WebSocket",
    msg: dict[str, Any],
) -> None:
    base = get_configured_packet_log_path(hass)
    if base is None:
        connection.send_result(msg["id"], {"base": None, "files": []})
        return

    files = await hass.async_add_executor_job(discover_log_files, base)
    connection.send_result(
        msg["id"],
        {
            "base": str(base),
            "files": [
                {
                    "file_id": f.file_id,
                    "size": f.size,
                    "modified_at": f.modified_at,
                }
                for f in files
            ],
        },
    )


@websocket_api.websocket_command(  # type: ignore[untyped-decorator]
    {
        vol.Required("type"): "ramses_extras/ramses_debugger/packet_log/get_messages",
        vol.Required("file_id"): str,
        vol.Optional("src"): str,
        vol.Optional("dst"): str,
        vol.Optional("verb"): str,
        vol.Optional("code"): str,
        vol.Optional("since"): str,
        vol.Optional("until"): str,
        vol.Optional("limit", default=200): vol.All(int, vol.Range(min=0, max=5000)),
    }
)
@websocket_api.async_response  # type: ignore[untyped-decorator]
async def ws_packet_log_get_messages(
    hass: HomeAssistant,
    connection: "WebSocket",
    msg: dict[str, Any],
) -> None:
    file_id = msg.get("file_id")
    if not isinstance(file_id, str) or not file_id:
        connection.send_error(msg["id"], "invalid_file_id", "Missing file_id")
        return

    base = get_configured_packet_log_path(hass)
    if base is None:
        connection.send_error(
            msg["id"], "packet_log_not_configured", "No packet log configured"
        )
        return

    path = await hass.async_add_executor_job(_resolve_packet_log_file, base, file_id)
    if path is None:
        connection.send_error(
            msg["id"],
            "file_not_allowed",
            "Requested file_id is not available",
        )
        return

    from .messages_provider import PacketLogParser

    messages = await PacketLogParser.get_messages(
        hass,
        log_path=path,
        src=msg.get("src"),
        dst=msg.get("dst"),
        verb=msg.get("verb"),
        code=msg.get("code"),
        since=msg.get("since"),
        until=msg.get("until"),
        limit=msg.get("limit", 200),
    )

    connection.send_result(
        msg["id"],
        {
            "file_id": path.name,
            "messages": [m.__dict__ for m in messages],
        },
    )


@websocket_api.websocket_command(  # type: ignore[untyped-decorator]
    {
        vol.Required("type"): "ramses_extras/ramses_debugger/log/get_tail",
        vol.Required("file_id"): str,
        vol.Optional("max_lines", default=200): vol.All(
            int,
            vol.Range(min=0, max=10_000),
        ),
        vol.Optional("max_chars", default=200_000): vol.All(
            int,
            vol.Range(min=0, max=2_000_000),
        ),
    }
)
@websocket_api.async_response  # type: ignore[untyped-decorator]
async def ws_log_get_tail(
    hass: HomeAssistant,
    connection: "WebSocket",
    msg: dict[str, Any],
) -> None:
    file_id = msg.get("file_id")
    if not isinstance(file_id, str) or not file_id:
        connection.send_error(msg["id"], "invalid_file_id", "Missing file_id")
        return

    base = get_configured_log_path(hass)
    path = await hass.async_add_executor_job(_resolve_log_file, base, file_id)
    if path is None:
        connection.send_error(
            msg["id"],
            "file_not_allowed",
            "Requested file_id is not available",
        )
        return

    max_lines = msg.get("max_lines", 200)
    max_chars = msg.get("max_chars", 200_000)
    text = await hass.async_add_executor_job(
        partial(tail_text, path, max_lines=max_lines, max_chars=max_chars)
    )
    connection.send_result(
        msg["id"],
        {
            "file_id": path.name,
            "text": text,
        },
    )


@websocket_api.websocket_command(  # type: ignore[untyped-decorator]
    {
        vol.Required("type"): "ramses_extras/ramses_debugger/messages/get_messages",
        vol.Optional(
            "sources",
            default=["traffic_buffer", "packet_log", "ha_log"],
        ): [str],
        vol.Optional("src"): str,
        vol.Optional("dst"): str,
        vol.Optional("verb"): str,
        vol.Optional("code"): str,
        vol.Optional("since"): str,
        vol.Optional("until"): str,
        vol.Optional("limit", default=200): vol.All(int, vol.Range(min=0, max=5000)),
        vol.Optional("dedupe", default=True): bool,
        vol.Optional("decode", default=False): bool,
    }
)
@websocket_api.async_response  # type: ignore[untyped-decorator]
async def ws_messages_get_messages(
    hass: HomeAssistant,
    connection: "WebSocket",
    msg: dict[str, Any],
) -> None:
    sources = msg.get("sources", ["traffic_buffer", "packet_log", "ha_log"])
    src = msg.get("src")
    dst = msg.get("dst")
    verb = msg.get("verb")
    code = msg.get("code")
    since = msg.get("since")
    until = msg.get("until")
    limit = msg.get("limit", 200)
    dedupe = msg.get("dedupe", True)
    decode = bool(msg.get("decode", False))

    try:
        messages = await get_messages_from_sources(
            hass,
            sources,
            src=src,
            dst=dst,
            verb=verb,
            code=code,
            since=since,
            until=until,
            limit=limit,
            dedupe=dedupe,
        )

        if decode:
            from .messages_provider import decode_message_with_ramses_rf

            for m in messages:
                decoded = decode_message_with_ramses_rf(m)
                if decoded is not None:
                    m["decoded"] = decoded

        connection.send_result(msg["id"], {"messages": messages})
    except Exception as exc:
        _LOGGER.warning("Error in messages/get_messages: %s", exc)
        connection.send_error(msg["id"], "error", str(exc))


@websocket_api.websocket_command(  # type: ignore[untyped-decorator]
    {
        vol.Required("type"): "ramses_extras/ramses_debugger/log/search",
        vol.Required("file_id"): str,
        vol.Required("query"): str,
        vol.Optional("before", default=3): vol.All(int, vol.Range(min=0, max=200)),
        vol.Optional("after", default=3): vol.All(int, vol.Range(min=0, max=200)),
        vol.Optional("max_matches", default=200): vol.All(
            int,
            vol.Range(min=0, max=5000),
        ),
        vol.Optional("max_chars", default=400_000): vol.All(
            int,
            vol.Range(min=0, max=2_000_000),
        ),
        vol.Optional("case_sensitive", default=False): bool,
    }
)
@websocket_api.async_response  # type: ignore[untyped-decorator]
async def ws_log_search(
    hass: HomeAssistant,
    connection: "WebSocket",
    msg: dict[str, Any],
) -> None:
    file_id = msg.get("file_id")
    if not isinstance(file_id, str) or not file_id:
        connection.send_error(msg["id"], "invalid_file_id", "Missing file_id")
        return

    base = get_configured_log_path(hass)
    path = await hass.async_add_executor_job(_resolve_log_file, base, file_id)
    if path is None:
        connection.send_error(
            msg["id"],
            "file_not_allowed",
            "Requested file_id is not available",
        )
        return

    query = msg.get("query")
    if not isinstance(query, str) or not query:
        connection.send_error(msg["id"], "invalid_query", "Missing query")
        return

    before = msg.get("before", 3)
    after = msg.get("after", 3)
    max_matches = msg.get("max_matches", 200)
    max_chars = msg.get("max_chars", 400_000)
    case_sensitive = bool(msg.get("case_sensitive", False))
    result = await hass.async_add_executor_job(
        partial(
            search_with_context,
            path,
            query=query,
            before=before,
            after=after,
            max_matches=max_matches,
            max_chars=max_chars,
            case_sensitive=case_sensitive,
        )
    )

    connection.send_result(
        msg["id"],
        {
            "file_id": path.name,
            **result,
        },
    )
