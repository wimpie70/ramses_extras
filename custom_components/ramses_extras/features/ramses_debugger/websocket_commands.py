import logging
from collections import Counter
from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.core import Event, HomeAssistant

from custom_components.ramses_extras.const import DOMAIN

from .const import DOMAIN as RAMSES_DEBUGGER_DOMAIN
from .debugger_cache import DebuggerCache, freeze_for_key
from .log_backend import (
    discover_log_files,
    get_configured_log_path,
    get_configured_packet_log_path,
    resolve_log_file_id,
    search_with_context,
    tail_text,
)
from .messages_provider import get_messages_from_sources
from .traffic_collector import TrafficCollector

if TYPE_CHECKING:
    from homeassistant.components.websocket_api import WebSocket

_LOGGER = logging.getLogger(__name__)


def _get_cache(hass: HomeAssistant) -> DebuggerCache | None:
    domain_data = hass.data.get(DOMAIN)
    if not isinstance(domain_data, dict):
        return None

    debugger_data = domain_data.get(RAMSES_DEBUGGER_DOMAIN)
    if not isinstance(debugger_data, dict):
        return None

    cache = debugger_data.get("cache")
    if not isinstance(cache, DebuggerCache):
        return None

    return cache


def _get_cache_ttl_s(hass: HomeAssistant) -> float:
    domain_data = hass.data.get(DOMAIN)
    if not isinstance(domain_data, dict):
        return 1.0

    entry = domain_data.get("config_entry")
    options = getattr(entry, "options", {}) if entry else {}
    ttl_ms = options.get("ramses_debugger_cache_ttl_ms")
    if isinstance(ttl_ms, int):
        return max(0.0, float(ttl_ms) / 1000.0)

    return 1.0


def _file_state(path: Path) -> tuple[int, int] | None:
    try:
        st = path.stat()
    except OSError:
        return None
    return (int(st.st_mtime_ns), int(st.st_size))


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
    device_id = msg.get("device_id")

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

    # For log sources, `limit` is the number of flows to return, not how many
    # messages we should scan to build the stats.
    message_limit = 20_000

    cache = _get_cache(hass)
    backing_path: Path | None = None
    if traffic_source == "packet_log":
        backing_path = get_configured_packet_log_path(hass)
    elif traffic_source == "ha_log":
        backing_path = get_configured_log_path(hass)
    state = _file_state(backing_path) if isinstance(backing_path, Path) else None

    async def _build_stats() -> dict[str, Any]:
        messages = await get_messages_from_sources(
            hass,
            sources,
            src=msg.get("src"),
            dst=msg.get("dst"),
            verb=msg.get("verb"),
            code=msg.get("code"),
            limit=message_limit,
            dedupe=True,
        )

        by_code: Counter[str] = Counter()
        by_verb: Counter[str] = Counter()
        flows: dict[tuple[str, str], dict[str, Any]] = {}
        started_at: str | None = None
        total_count = 0

        for m in messages:
            src_ = m.get("src")
            dst_ = m.get("dst")
            if not isinstance(src_, str) or not isinstance(dst_, str):
                continue

            if (
                isinstance(device_id, str)
                and device_id
                and device_id not in (src_, dst_)
            ):
                continue

            total_count += 1

            dtm = m.get("dtm")
            if isinstance(dtm, str) and dtm:
                started_at = dtm if started_at is None else min(started_at, dtm)

            code_ = m.get("code")
            if isinstance(code_, str) and code_:
                by_code[code_] += 1

            verb_ = m.get("verb")
            if isinstance(verb_, str) and verb_:
                by_verb[verb_] += 1

            key = (src_, dst_)
            flow = flows.get(key)
            if flow is None:
                flow = {
                    "src": src_,
                    "dst": dst_,
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

            if isinstance(verb_, str) and verb_:
                flow["verbs"][verb_] += 1
            if isinstance(code_, str) and code_:
                flow["codes"][code_] += 1

        flow_list = list(flows.values())
        flow_list.sort(key=lambda f: int(f.get("count_total", 0)), reverse=True)

        return {
            "started_at": started_at or "",
            "total_count": total_count,
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
        }

    cache_key = (
        "traffic_get_stats",
        traffic_source,
        str(backing_path) if backing_path else None,
        state,
        freeze_for_key(
            {
                "device_id": device_id,
                "src": msg.get("src"),
                "dst": msg.get("dst"),
                "verb": msg.get("verb"),
                "code": msg.get("code"),
                "limit": int(limit),
                "message_limit": int(message_limit),
            }
        ),
    )

    if cache is not None and state is not None:
        ttl_s = _get_cache_ttl_s(hass)
        stats = await cache.get_or_create(
            cache_key,
            ttl_s=ttl_s,
            create_fn=_build_stats,
        )
    else:
        stats = await _build_stats()

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
        vol.Optional("decode", default=False): bool,
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

    path = await hass.async_add_executor_job(resolve_log_file_id, base, file_id)
    if path is None:
        connection.send_error(
            msg["id"],
            "file_not_allowed",
            "Requested file_id is not available",
        )
        return

    from .messages_provider import PacketLogParser

    cache = _get_cache(hass)
    state = _file_state(path)
    decode = bool(msg.get("decode"))

    async def _load_result() -> dict[str, Any]:
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

        message_dicts = [m.__dict__ for m in messages]
        if decode:
            from .messages_provider import decode_message_with_ramses_rf

            for message in message_dicts:
                decoded = decode_message_with_ramses_rf(message)
                if decoded is not None:
                    message["decoded"] = decoded

        return {"file_id": path.name, "messages": message_dicts}

    cache_key = (
        "packet_log_get_messages",
        str(path),
        state,
        freeze_for_key(
            {
                "src": msg.get("src"),
                "dst": msg.get("dst"),
                "verb": msg.get("verb"),
                "code": msg.get("code"),
                "since": msg.get("since"),
                "until": msg.get("until"),
                "limit": int(msg.get("limit", 200)),
                "decode": decode,
            }
        ),
    )

    if cache is not None and state is not None:
        ttl_s = _get_cache_ttl_s(hass)
        result = await cache.get_or_create(
            cache_key,
            ttl_s=ttl_s,
            create_fn=_load_result,
        )
    else:
        result = await _load_result()

    connection.send_result(msg["id"], result)


@websocket_api.websocket_command(  # type: ignore[untyped-decorator]
    {
        vol.Required("type"): "ramses_extras/ramses_debugger/log/get_tail",
        vol.Required("file_id"): str,
        vol.Optional("max_lines", default=200): vol.All(
            int,
            vol.Range(min=0, max=10_000),
        ),
        vol.Optional("offset_lines", default=0): vol.All(
            int,
            vol.Range(min=0, max=100_000),
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
    path = await hass.async_add_executor_job(resolve_log_file_id, base, file_id)
    if path is None:
        connection.send_error(
            msg["id"],
            "file_not_allowed",
            "Requested file_id is not available",
        )
        return

    max_lines = msg.get("max_lines", 200)
    offset_lines = msg.get("offset_lines", 0)
    max_chars = msg.get("max_chars", 200_000)

    cache = _get_cache(hass)
    state = _file_state(path)

    async def _read_tail() -> str:
        if offset_lines:
            text = cast(
                str,
                await hass.async_add_executor_job(
                    partial(
                        tail_text,
                        path,
                        max_lines=max_lines + offset_lines,
                        max_chars=max_chars,
                    )
                ),
            )
            lines = text.splitlines(keepends=True)
            if offset_lines >= len(lines):
                return ""
            return "".join(lines[:-offset_lines])

        return cast(
            str,
            await hass.async_add_executor_job(
                partial(tail_text, path, max_lines=max_lines, max_chars=max_chars)
            ),
        )

    cache_key = (
        "log_get_tail",
        str(path),
        state,
        freeze_for_key(
            {
                "max_lines": int(max_lines),
                "offset_lines": int(offset_lines),
                "max_chars": int(max_chars),
            }
        ),
    )

    if cache is not None and state is not None:
        ttl_s = _get_cache_ttl_s(hass)
        text = await cache.get_or_create(cache_key, ttl_s=ttl_s, create_fn=_read_tail)
    else:
        text = await _read_tail()
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
    path = await hass.async_add_executor_job(resolve_log_file_id, base, file_id)
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

    cache = _get_cache(hass)
    state = _file_state(path)

    async def _do_search() -> dict[str, Any]:
        return cast(
            dict[str, Any],
            await hass.async_add_executor_job(
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
            ),
        )

    cache_key = (
        "log_search",
        str(path),
        state,
        freeze_for_key(
            {
                "query": query,
                "before": int(before),
                "after": int(after),
                "max_matches": int(max_matches),
                "max_chars": int(max_chars),
                "case_sensitive": bool(case_sensitive),
            }
        ),
    )

    if cache is not None and state is not None:
        ttl_s = _get_cache_ttl_s(hass)
        result = await cache.get_or_create(cache_key, ttl_s=ttl_s, create_fn=_do_search)
    else:
        result = await _do_search()

    connection.send_result(
        msg["id"],
        {
            "file_id": path.name,
            **result,
        },
    )


@websocket_api.websocket_command(  # type: ignore[untyped-decorator]
    {
        vol.Required("type"): "ramses_extras/ramses_debugger/cache/get_stats",
    }
)
@websocket_api.async_response  # type: ignore[untyped-decorator]
async def ws_cache_get_stats(
    hass: HomeAssistant,
    connection: "WebSocket",
    msg: dict[str, Any],
) -> None:
    cache = _get_cache(hass)
    if cache is None:
        connection.send_result(
            msg["id"],
            {
                "available": False,
                "stats": None,
            },
        )
        return

    connection.send_result(
        msg["id"],
        {
            "available": True,
            "stats": cache.stats(),
        },
    )


@websocket_api.websocket_command(  # type: ignore[untyped-decorator]
    {
        vol.Required("type"): "ramses_extras/ramses_debugger/cache/clear",
    }
)
@websocket_api.async_response  # type: ignore[untyped-decorator]
async def ws_cache_clear(
    hass: HomeAssistant,
    connection: "WebSocket",
    msg: dict[str, Any],
) -> None:
    cache = _get_cache(hass)
    if cache is None:
        connection.send_result(msg["id"], {"available": False, "cleared": False})
        return

    cache.clear()
    connection.send_result(msg["id"], {"available": True, "cleared": True})
