# Part of the Ramses Extra integration
# See https://github.com/wimpie70/ramses_extras for more information
#
"""Number platform for Hello World Switch Card feature."""

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant


async def async_setup_entry(
    hass: HomeAssistant, config_entry: ConfigEntry, async_add_entities: Any
) -> None:
    """Set up Hello World number platform."""
    # Placeholder implementation - not functional by default
    # Extend ExtrasNumberEntity when adding numeric controls
    pass  # noqa: PIE790
