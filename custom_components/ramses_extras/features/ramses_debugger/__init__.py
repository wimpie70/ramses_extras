import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from custom_components.ramses_extras.const import DOMAIN

from .const import DOMAIN as RAMSES_DEBUGGER_DOMAIN
from .debugger_cache import DebuggerCache
from .traffic_collector import TrafficCollector

_LOGGER = logging.getLogger(__name__)


def create_ramses_debugger_feature(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    skip_automation_setup: bool = False,
) -> dict[str, Any]:
    _LOGGER.debug(
        "Created feature '%s' (skip_automation_setup=%s)",
        RAMSES_DEBUGGER_DOMAIN,
        skip_automation_setup,
    )

    registry = hass.data.setdefault(DOMAIN, {})
    debugger_data = registry.setdefault(RAMSES_DEBUGGER_DOMAIN, {})

    cache = debugger_data.get("cache")
    if not isinstance(cache, DebuggerCache):
        debugger_data["cache"] = DebuggerCache()
        cache = debugger_data.get("cache")

    cache_max_entries = config_entry.options.get("ramses_debugger_cache_max_entries")
    if isinstance(cache_max_entries, int) and cache_max_entries > 0:
        debugger_data["cache"] = DebuggerCache(max_entries=cache_max_entries)

    traffic_collector = debugger_data.get("traffic_collector")
    if not isinstance(traffic_collector, TrafficCollector):
        traffic_collector = TrafficCollector(hass)
        debugger_data["traffic_collector"] = traffic_collector
        config_entry.async_on_unload(traffic_collector.stop)

    traffic_collector.configure(
        max_flows=config_entry.options.get("ramses_debugger_max_flows"),
        buffer_max_global=config_entry.options.get("ramses_debugger_buffer_max_global"),
        buffer_max_per_flow=config_entry.options.get(
            "ramses_debugger_buffer_max_per_flow"
        ),
        buffer_max_flows=config_entry.options.get("ramses_debugger_buffer_max_flows"),
    )

    traffic_collector.start()

    return {
        "feature_name": RAMSES_DEBUGGER_DOMAIN,
        "traffic_collector": traffic_collector,
    }


__all__ = ["create_ramses_debugger_feature"]
