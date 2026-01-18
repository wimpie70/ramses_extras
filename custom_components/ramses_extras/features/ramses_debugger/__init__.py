import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN as RAMSES_DEBUGGER_DOMAIN

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
    return {
        "feature_name": RAMSES_DEBUGGER_DOMAIN,
    }


__all__ = ["create_ramses_debugger_feature"]
