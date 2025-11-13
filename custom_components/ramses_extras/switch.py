import logging
from typing import TYPE_CHECKING, Any

from homeassistant.config_entries import ConfigEntry

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

_LOGGER = logging.getLogger(__name__)


def _get_feature_platform_setups(platform: str) -> list[Any]:
    """Get registered feature platform setup functions."""
    from .const import get_feature_platform_setups

    return get_feature_platform_setups(platform)


async def async_setup_entry(
    hass: "HomeAssistant",
    config_entry: ConfigEntry | None,
    async_add_entities: "AddEntitiesCallback",
) -> None:
    """Set up the switch platform - dynamically discover and call feature platforms."""
    # Get registered feature switch platforms
    feature_setups = _get_feature_platform_setups("switch")

    # Call each discovered feature platform
    for setup_func in feature_setups:
        try:
            await setup_func(hass, config_entry, async_add_entities)
        except Exception as e:
            _LOGGER.error(f"Error setting up switch platform: {e}")
