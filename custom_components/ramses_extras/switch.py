import logging
from typing import TYPE_CHECKING

from homeassistant.config_entries import ConfigEntry

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: "HomeAssistant",
    config_entry: ConfigEntry | None,
    async_add_entities: "AddEntitiesCallback",
) -> None:
    """Set up the switch platform - thin wrapper forwarding to feature platforms."""
    # Forward to humidity control feature switch platform
    from .features.humidity_control.platforms.switch import (
        async_setup_entry as humidity_switch_setup,
    )

    await humidity_switch_setup(hass, config_entry, async_add_entities)
