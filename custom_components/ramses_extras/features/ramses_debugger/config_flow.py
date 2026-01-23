from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from ...const import AVAILABLE_FEATURES

_LOGGER = logging.getLogger(__name__)


async def async_step_ramses_debugger_config(
    flow: Any,
    user_input: dict[str, Any] | None,
) -> Any:
    feature_id = "ramses_debugger"
    feature_config = AVAILABLE_FEATURES.get(feature_id, {})

    refresh = getattr(flow, "_refresh_config_entry", None)
    if callable(refresh):
        hass = getattr(flow, "hass", None)
        if hass is not None:
            refresh(hass)
        else:
            refresh()

    if user_input is not None:
        new_options = dict(flow._config_entry.options)  # noqa: SLF001

        log_path = user_input.get("ramses_debugger_log_path")
        if isinstance(log_path, str):
            new_options["ramses_debugger_log_path"] = log_path.strip()

        packet_log_path = user_input.get("ramses_debugger_packet_log_path")
        if isinstance(packet_log_path, str):
            new_options["ramses_debugger_packet_log_path"] = packet_log_path.strip()

        cache_max_entries = user_input.get("ramses_debugger_cache_max_entries")
        if isinstance(cache_max_entries, int):
            new_options["ramses_debugger_cache_max_entries"] = int(cache_max_entries)

        cache_ttl_ms = user_input.get("ramses_debugger_cache_ttl_ms")
        if isinstance(cache_ttl_ms, int):
            new_options["ramses_debugger_cache_ttl_ms"] = int(cache_ttl_ms)

        max_flows = user_input.get("ramses_debugger_max_flows")
        if isinstance(max_flows, int):
            new_options["ramses_debugger_max_flows"] = int(max_flows)

        buffer_max_global = user_input.get("ramses_debugger_buffer_max_global")
        if isinstance(buffer_max_global, int):
            new_options["ramses_debugger_buffer_max_global"] = int(buffer_max_global)

        buffer_max_per_flow = user_input.get("ramses_debugger_buffer_max_per_flow")
        if isinstance(buffer_max_per_flow, int):
            new_options["ramses_debugger_buffer_max_per_flow"] = int(
                buffer_max_per_flow
            )

        buffer_max_flows = user_input.get("ramses_debugger_buffer_max_flows")
        if isinstance(buffer_max_flows, int):
            new_options["ramses_debugger_buffer_max_flows"] = int(buffer_max_flows)

        default_poll_ms = user_input.get("ramses_debugger_default_poll_ms")
        if isinstance(default_poll_ms, int):
            new_options["ramses_debugger_default_poll_ms"] = int(default_poll_ms)

        flow.hass.config_entries.async_update_entry(
            flow._config_entry,  # noqa: SLF001
            options=new_options,
        )
        return await flow.async_step_main_menu()

    current_options = dict(flow._config_entry.options)  # noqa: SLF001

    log_path_default_raw = current_options.get("ramses_debugger_log_path")
    if isinstance(log_path_default_raw, str) and log_path_default_raw.strip():
        log_path_default = log_path_default_raw.strip()
    else:
        log_path_default = flow.hass.config.path("home-assistant.log")

    packet_log_path_default_raw = current_options.get("ramses_debugger_packet_log_path")
    if (
        isinstance(packet_log_path_default_raw, str)
        and packet_log_path_default_raw.strip()
    ):
        packet_log_path_default = packet_log_path_default_raw.strip()
    else:
        packet_log_path_default = ""

    cache_max_entries_default_raw = current_options.get(
        "ramses_debugger_cache_max_entries"
    )
    cache_max_entries_default = (
        int(cache_max_entries_default_raw)
        if isinstance(cache_max_entries_default_raw, int)
        else 256
    )

    cache_ttl_ms_default_raw = current_options.get("ramses_debugger_cache_ttl_ms")
    cache_ttl_ms_default = (
        int(cache_ttl_ms_default_raw)
        if isinstance(cache_ttl_ms_default_raw, int)
        else 1000
    )

    max_flows_default_raw = current_options.get("ramses_debugger_max_flows")
    max_flows_default = (
        int(max_flows_default_raw) if isinstance(max_flows_default_raw, int) else 2000
    )

    buffer_max_global_default_raw = current_options.get(
        "ramses_debugger_buffer_max_global"
    )
    buffer_max_global_default = (
        int(buffer_max_global_default_raw)
        if isinstance(buffer_max_global_default_raw, int)
        else 5000
    )

    buffer_max_per_flow_default_raw = current_options.get(
        "ramses_debugger_buffer_max_per_flow"
    )
    buffer_max_per_flow_default = (
        int(buffer_max_per_flow_default_raw)
        if isinstance(buffer_max_per_flow_default_raw, int)
        else 500
    )

    buffer_max_flows_default_raw = current_options.get(
        "ramses_debugger_buffer_max_flows"
    )
    buffer_max_flows_default = (
        int(buffer_max_flows_default_raw)
        if isinstance(buffer_max_flows_default_raw, int)
        else 2000
    )

    default_poll_ms_default_raw = current_options.get("ramses_debugger_default_poll_ms")
    default_poll_ms_default = (
        int(default_poll_ms_default_raw)
        if isinstance(default_poll_ms_default_raw, int)
        else 1000
    )

    data_schema = vol.Schema(
        {
            vol.Optional(
                "ramses_debugger_log_path",
                default=log_path_default,
            ): str,
            vol.Optional(
                "ramses_debugger_packet_log_path",
                default=packet_log_path_default,
            ): str,
            vol.Optional(
                "ramses_debugger_cache_ttl_ms",
                default=cache_ttl_ms_default,
            ): vol.All(int, vol.Range(min=0, max=30_000)),
            vol.Optional(
                "ramses_debugger_cache_max_entries",
                default=cache_max_entries_default,
            ): vol.All(int, vol.Range(min=1, max=10_000)),
            vol.Optional(
                "ramses_debugger_max_flows",
                default=max_flows_default,
            ): vol.All(int, vol.Range(min=1, max=50_000)),
            vol.Optional(
                "ramses_debugger_buffer_max_global",
                default=buffer_max_global_default,
            ): vol.All(int, vol.Range(min=1, max=200_000)),
            vol.Optional(
                "ramses_debugger_buffer_max_per_flow",
                default=buffer_max_per_flow_default,
            ): vol.All(int, vol.Range(min=1, max=50_000)),
            vol.Optional(
                "ramses_debugger_buffer_max_flows",
                default=buffer_max_flows_default,
            ): vol.All(int, vol.Range(min=1, max=50_000)),
            vol.Optional(
                "ramses_debugger_default_poll_ms",
                default=default_poll_ms_default,
            ): vol.All(int, vol.Range(min=250, max=60_000)),
        }
    )

    info_text = "🧰 **" + str(feature_config.get("name", feature_id)) + "**\n\n"
    info_text += "Configure options for the Ramses Debugger cards and backend."

    return flow.async_show_form(
        step_id="feature_ramses_debugger",
        data_schema=data_schema,
        description_placeholders={"info": info_text},
    )
