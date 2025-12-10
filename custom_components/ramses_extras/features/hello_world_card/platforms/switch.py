# Part of the Ramses Extra integration
# See https://github.com/wimpie70/ramses_extras for more information
#
"""Switch platform for Hello World Switch Card feature."""

import logging
from typing import TYPE_CHECKING, Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from custom_components.ramses_extras.framework.base_classes.platform_entities import (
    ExtrasSwitchEntity,
)

from ..const import HELLO_WORLD_SWITCH_CONFIGS
from ..entities import HelloWorldEntities

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: "HomeAssistant",
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Hello World switch platform."""
    from custom_components.ramses_extras.framework.helpers import platform

    await platform.PlatformSetup.async_create_and_add_platform_entities(
        platform="switch",
        hass=hass,
        config_entry=config_entry,
        async_add_entities=async_add_entities,
        entity_configs=HELLO_WORLD_SWITCH_CONFIGS,
        entity_factory=create_hello_world_switch,
    )


async def create_hello_world_switch(
    hass: "HomeAssistant", device_id: str, config_entry: ConfigEntry | None = None
) -> list[ExtrasSwitchEntity]:
    """Create Hello World switch for a device.

    Args:
        hass: Home Assistant instance
        device_id: Device identifier
        config_entry: Configuration entry

    Returns:
        List of switch entities
    """
    switch_list = []

    for switch_type, config in HELLO_WORLD_SWITCH_CONFIGS.items():
        supported_types = config.get("device_types", [])
        if supported_types and "HvacVentilator" in supported_types:
            switch_entity = HelloWorldSwitch(hass, device_id, switch_type, config)
            switch_list.append(switch_entity)

    return switch_list


class HelloWorldSwitch(ExtrasSwitchEntity):
    """Hello World Switch entity for demonstration purposes."""

    def __init__(
        self,
        hass: "HomeAssistant",
        device_id: str,
        switch_type: str,
        config: dict[str, Any],
    ):
        """Initialize Hello World switch entity."""
        super().__init__(hass, device_id, switch_type, config)

        # Initialize state - will be updated when entities manager becomes available
        self._is_on = False

    async def async_added_to_hass(self) -> None:
        """Subscribe to Ramses RF device updates."""
        await super().async_added_to_hass()
        _LOGGER.info("Hello World switch %s added to hass", self._attr_name)

        # Store reference to this entity for WebSocket access
        try:
            if not hasattr(self.hass, "data"):
                self.hass.data = {}
            if "ramses_extras" not in self.hass.data:
                self.hass.data["ramses_extras"] = {}
            if "entities" not in self.hass.data["ramses_extras"]:
                self.hass.data["ramses_extras"]["entities"] = {}

            entity_id = f"switch.hello_world_switch_{self.device_id.replace(':', '_')}"
            self.hass.data["ramses_extras"]["entities"][entity_id] = self
            _LOGGER.info(f"Switch stored for WebSocket access at {entity_id}")
        except Exception as e:
            _LOGGER.error(f"Switch failed to store reference: {e}")

        # Register for entities manager state change notifications
        try:
            entities_manager = self._get_entities_manager(self.hass)
            if entities_manager:
                switch_entity_key = f"{self.device_id}_switch_hello_world_switch"
                entities_manager.register_state_change_callback(
                    switch_entity_key, self._on_entity_state_change
                )
                _LOGGER.info(f"Switch registered callback for {switch_entity_key}")
        except Exception as e:
            _LOGGER.warning(
                "Could not register switch for state change notifications: %s", e
            )

    async def _handle_update(self, *args: Any, **kwargs: Any) -> None:
        """Handle updates from Ramses RF."""
        _LOGGER.debug(
            "Device update for Hello World switch %s received", self._attr_name
        )
        self.async_write_ha_state()

    @property
    def is_on(self) -> bool:
        """Return true if Hello World switch is active."""
        # Try to get current state from entities manager
        try:
            entities_manager = self._get_entities_manager(self.hass)
            current_state = entities_manager.get_entity_state(
                self.device_id, "switch", "hello_world_switch"
            )
            _LOGGER.debug(
                f"Switch {self._attr_name} is_on property: {bool(current_state)}"
            )
            return bool(current_state)
        except Exception as e:
            # Fallback to cached state
            _LOGGER.debug(
                f"Switch {self._attr_name} is_on property fallback: "
                f"{self._is_on} (error: {e})"
            )
            return self._is_on

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Activate Hello World switch."""
        _LOGGER.info("Activating Hello World switch for %s", self._attr_name)

        # Get entities manager (lazy load)
        entities_manager = self._get_entities_manager(self.hass)

        # Update state in entities manager
        entities_manager.set_entity_state(
            self.device_id, "switch", "hello_world_switch", True
        )

        self._is_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Deactivate Hello World switch."""
        _LOGGER.info("Deactivating Hello World switch for %s", self._attr_name)

        # Get entities manager (lazy load)
        entities_manager = self._get_entities_manager(self.hass)

        # Update state in entities manager
        entities_manager.set_entity_state(
            self.device_id, "switch", "hello_world_switch", False
        )

        self._is_on = False
        self.async_write_ha_state()

    def _get_entities_manager(self, hass: "HomeAssistant") -> HelloWorldEntities:
        """Get the shared entities manager instance."""
        # Try to get the global entities manager from hass.data
        if hasattr(hass, "data") and "ramses_extras" in hass.data:
            registry = hass.data["ramses_extras"]
            if "hello_world_entities" in registry:
                _LOGGER.debug("Switch got entities manager from hass.data")
                return registry["hello_world_entities"]  # type: ignore[no-any-return]

        # Fallback: create a new instance (should not happen in normal operation)
        _LOGGER.warning("Using fallback entities manager - state may not sync properly")
        return HelloWorldEntities(hass, None)

    async def async_will_remove_from_hass(self) -> None:
        """Clean up when entity is removed."""
        await super().async_will_remove_from_hass()

        # Clean up stored reference
        try:
            entity_id = f"switch.hello_world_switch_{self.device_id.replace(':', '_')}"
            if (
                hasattr(self.hass, "data")
                and "ramses_extras" in self.hass.data
                and "entities" in self.hass.data["ramses_extras"]
                and entity_id in self.hass.data["ramses_extras"]["entities"]
            ):
                del self.hass.data["ramses_extras"]["entities"][entity_id]
                _LOGGER.debug(
                    f"Removed switch {self._attr_name} from stored references"
                )
        except Exception as e:
            _LOGGER.debug("Could not clean up switch reference: %s", e)

        # Unregister state change callback
        try:
            entities_manager = self._get_entities_manager(self.hass)
            if entities_manager:
                switch_entity_key = f"{self.device_id}_switch_hello_world_switch"
                entities_manager.unregister_state_change_callback(
                    switch_entity_key, self._on_entity_state_change
                )
                _LOGGER.debug(
                    "Switch unregistered from entities manager "
                    "state change notifications"
                )
        except Exception as e:
            _LOGGER.debug("Could not unregister switch callback: %s", e)

    def _on_entity_state_change(
        self,
        device_id: str,
        entity_type: str,
        entity_key: str,
        old_state: Any,
        new_state: Any,
    ) -> None:
        """Handle entities manager state change notifications.

        Args:
            device_id: Device identifier
            entity_type: Type of entity that changed
            entity_key: Specific entity key
            old_state: Previous state
            new_state: New state
        """
        if (
            entity_type == "switch"
            and entity_key == "hello_world_switch"
            and device_id == self.device_id
        ):
            _LOGGER.info(
                f"Switch {self._attr_name} received state change: "
                f"{old_state} -> {new_state}"
            )
            self._is_on = bool(new_state)
            # Write state to Home Assistant to trigger UI updates
            self.async_write_ha_state()
            _LOGGER.info(f"Switch {self._attr_name} state updated to {new_state}")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        base_attrs = super().extra_state_attributes or {}
        return {
            **base_attrs,
            "hello_world_active": self.is_on,
            "demo_feature": True,
        }


# Register this platform with the global registry
from custom_components.ramses_extras.const import (  # noqa: E402
    register_feature_platform,  # noqa: E402
)

register_feature_platform("switch", "hello_world_card", async_setup_entry)

__all__ = [
    "HelloWorldSwitch",
    "async_setup_entry",
    "create_hello_world_switch",
]
