"""Ramses CC broker helper functions."""

import logging
from typing import Any, Optional

from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

# Module-level cache for broker lookups to avoid repeated broker finding
_broker_cache: Any | None = None


def get_ramses_broker(hass: HomeAssistant) -> Any | None:
    """Get the Ramses CC broker safely.

    Args:
        hass: Home Assistant instance

    Returns:
        The Ramses broker object or None if not available
    """
    global _broker_cache

    # Return cached broker if available
    if _broker_cache is not None:
        return _broker_cache

    if not hasattr(hass, "data") or not isinstance(hass.data, dict):
        _LOGGER.error("Invalid hass.data structure")
        return None

    ramses_data = hass.data.get("ramses_cc")

    if not ramses_data:
        _LOGGER.warning("Ramses CC integration not loaded in hass.data")
        return None

    # Since we know broker._devices is valid, check if ramses_data is the broker itself
    if ramses_data.__class__.__name__ == "RamsesBroker":
        _LOGGER.debug("Found RamsesBroker instance directly")
        _broker_cache = ramses_data
        return ramses_data

    # Handle the case where ramses_data is a dictionary of entries
    if isinstance(ramses_data, dict):
        for entry_id, data in ramses_data.items():
            # If data is a RamsesBroker instance
            if data.__class__.__name__ == "RamsesBroker":
                _LOGGER.debug("Found RamsesBroker in data")
                _broker_cache = data
                return data

    _LOGGER.warning("No Ramses broker found in ramses_data")
    return None


def clear_broker_cache() -> None:
    """Clear the broker cache. Call this when broker may have changed."""
    global _broker_cache
    _broker_cache = None
    _LOGGER.debug("Cleared broker cache")
