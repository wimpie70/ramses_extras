import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from custom_components.ramses_extras.const import DOMAIN

from .const import DOMAIN as RAMSES_DEBUGGER_DOMAIN
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

    traffic_collector = debugger_data.get("traffic_collector")
    if not isinstance(traffic_collector, TrafficCollector):
        traffic_collector = TrafficCollector(hass)
        debugger_data["traffic_collector"] = traffic_collector
        config_entry.async_on_unload(traffic_collector.stop)

    traffic_collector.start()

    return {
        "feature_name": RAMSES_DEBUGGER_DOMAIN,
        "traffic_collector": traffic_collector,
    }


__all__ = ["create_ramses_debugger_feature"]
