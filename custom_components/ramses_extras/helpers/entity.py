"""Base entity class for Ramses entities with common functionality."""

import logging
from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_connect

_LOGGER = logging.getLogger(__name__)


class RamsesBaseEntity(ABC):
    """Base entity class for all Ramses entities with common functionality."""

    def __init__(
        self,
        hass: HomeAssistant,
        device_id: str,
        entity_type: str,
        config: dict[str, Any],
    ):
        """Initialize base Ramses entity."""
        self.hass = hass
        self._device_id = device_id  # Store device ID as string
        self._entity_type = entity_type
        self._config = config

        # Set common attributes from configuration
        self._attr_name = f"{config['name_template']} ({device_id})"
        self._attr_unique_id = f"{entity_type}_{device_id.replace(':', '_')}"
        self._attr_icon = config.get("icon")
        self._attr_entity_category = config.get("entity_category")

        self._unsub: Callable[[], None] | None = None

    async def async_added_to_hass(self) -> None:
        """Subscribe to Ramses RF device updates."""
        signal = f"ramses_rf_device_update_{self._device_id}"
        self._unsub = async_dispatcher_connect(self.hass, signal, self._handle_update)
        _LOGGER.debug("Subscribed to %s for %s", signal, self._attr_name)

    async def async_will_remove_from_hass(self) -> None:
        """Unsubscribe when removed."""
        if self._unsub is not None:
            self._unsub()
            self._unsub = None

    async def _handle_update(self, *args: Any, **kwargs: Any) -> None:
        """Handle updates from Ramses RF."""
        _LOGGER.debug("Device update for %s received", self._attr_name)
        self.async_write_ha_state()

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return common state attributes."""
        return {
            "device_id": self._device_id,
            "entity_type": self._entity_type,
        }

    @abstractmethod
    def async_write_ha_state(self) -> None:
        """Write state to Home Assistant - implemented by subclasses."""
