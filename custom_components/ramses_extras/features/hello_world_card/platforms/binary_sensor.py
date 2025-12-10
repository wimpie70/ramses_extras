# Part of the Ramses Extra integration
# See https://github.com/wimpie70/ramses_extras for more information
#
"""Binary sensor platform for Hello World Switch Card feature."""

import logging
from typing import TYPE_CHECKING, Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from custom_components.ramses_extras.framework.base_classes.platform_entities import (
    ExtrasBinarySensorEntity,
)

from ..const import HELLO_WORLD_BINARY_SENSOR_CONFIGS
from ..entities import HelloWorldEntities

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: "HomeAssistant",
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Hello World binary sensor platform."""
    from custom_components.ramses_extras.framework.helpers import platform

    await platform.PlatformSetup.async_create_and_add_platform_entities(
        platform="binary_sensor",
        hass=hass,
        config_entry=config_entry,
        async_add_entities=async_add_entities,
        entity_configs=HELLO_WORLD_BINARY_SENSOR_CONFIGS,
        entity_factory=create_hello_world_binary_sensor,
    )


async def create_hello_world_binary_sensor(
    hass: "HomeAssistant", device_id: str, config_entry: ConfigEntry | None = None
) -> list[ExtrasBinarySensorEntity]:
    """Create Hello World binary sensor for a device.

    Args:
        hass: Home Assistant instance
        device_id: Device identifier
        config_entry: Configuration entry

    Returns:
        List of binary sensor entities
    """
    sensor_list = []

    for sensor_type, config in HELLO_WORLD_BINARY_SENSOR_CONFIGS.items():
        supported_types = config.get("device_types", [])
        if supported_types and "HvacVentilator" in supported_types:
            sensor_entity = HelloWorldBinarySensor(hass, device_id, sensor_type, config)
            sensor_list.append(sensor_entity)

    return sensor_list


class HelloWorldBinarySensor(ExtrasBinarySensorEntity):
    """Hello World Binary Sensor entity controlled by automation.

    This binary sensor is triggered by automation, not direct switch mirroring.
    It demonstrates the automation-driven architecture pattern.
    """

    def __init__(
        self,
        hass: "HomeAssistant",
        device_id: str,
        sensor_type: str,
        config: dict[str, Any],
    ):
        """Initialize Hello World binary sensor entity."""
        super().__init__(hass, device_id, sensor_type, config)

        # Initialize state - will be updated by automation
        self._is_on = False

    def _get_entities_manager(self, hass: "HomeAssistant") -> HelloWorldEntities:
        """Get the shared entities manager instance."""
        # Try to get the global entities manager from hass.data
        if hasattr(hass, "data") and "ramses_extras" in hass.data:
            registry = hass.data["ramses_extras"]
            if "hello_world_entities" in registry:
                _LOGGER.debug("Binary sensor got entities manager from hass.data")
                return registry["hello_world_entities"]  # type: ignore[no-any-return]

        # Fallback: create a new instance (should not happen in normal operation)
        _LOGGER.warning("Using fallback entities manager - state may not sync properly")
        return HelloWorldEntities(hass, None)

    async def async_added_to_hass(self) -> None:
        """Initialize Hello World binary sensor."""
        await super().async_added_to_hass()
        _LOGGER.info("Hello World binary sensor %s added to hass", self._attr_name)

        # Store reference to this entity for automation access
        # This enables the automation to trigger binary sensor updates
        try:
            if not hasattr(self.hass, "data"):
                self.hass.data = {}
            if "ramses_extras" not in self.hass.data:
                self.hass.data["ramses_extras"] = {}
            if "entities" not in self.hass.data["ramses_extras"]:
                self.hass.data["ramses_extras"]["entities"] = {}

            entity_id = (
                f"binary_sensor.hello_world_status_{self.device_id.replace(':', '_')}"
            )
            self.hass.data["ramses_extras"]["entities"][entity_id] = self
            _LOGGER.info(
                f"Binary sensor {self._attr_name} stored for automation access "
                f"at {entity_id}"
            )
        except Exception as e:
            _LOGGER.error(
                f"Binary sensor {self._attr_name} failed to store reference: {e}"
            )

        # Register for entities manager state change notifications
        try:
            entities_manager = self._get_entities_manager(self.hass)
            if entities_manager:
                binary_sensor_entity_key = (
                    f"{self.device_id}_binary_sensor_hello_world_status"
                )
                entities_manager.register_state_change_callback(
                    binary_sensor_entity_key, self._on_entity_state_change
                )
                _LOGGER.info(
                    f"Binary sensor registered callback for {binary_sensor_entity_key}"
                )
        except Exception as e:
            _LOGGER.warning(
                "Could not register binary sensor for state change notifications: %s", e
            )

        # Also listen to the HA event for state changes
        self.hass.bus.async_listen(
            "hello_world_entity_state_changed", self._on_entity_state_changed_event
        )
        _LOGGER.info(
            "Binary sensor listening to hello_world_entity_state_changed event"
        )

    async def async_will_remove_from_hass(self) -> None:
        """Clean up when entity is removed."""
        await super().async_will_remove_from_hass()

        # Clean up stored reference
        try:
            entity_id = (
                f"binary_sensor.hello_world_status_{self.device_id.replace(':', '_')}"
            )
            if (
                hasattr(self.hass, "data")
                and "ramses_extras" in self.hass.data
                and "entities" in self.hass.data["ramses_extras"]
                and entity_id in self.hass.data["ramses_extras"]["entities"]
            ):
                del self.hass.data["ramses_extras"]["entities"][entity_id]
                _LOGGER.debug(
                    f"Removed binary sensor {self._attr_name} from stored references"
                )
        except Exception as e:
            _LOGGER.debug("Could not clean up binary sensor reference: %s", e)

        # Unregister state change callback
        try:
            entities_manager = self._get_entities_manager(self.hass)
            if entities_manager:
                binary_sensor_entity_key = (
                    f"{self.device_id}_binary_sensor_hello_world_status"
                )
                entities_manager.unregister_state_change_callback(
                    binary_sensor_entity_key, self._on_entity_state_change
                )
                _LOGGER.debug(
                    "Binary sensor unregistered from entities manager "
                    "state change notifications"
                )
        except Exception as e:
            _LOGGER.debug("Could not unregister binary sensor callback: %s", e)

    async def _handle_update(self, *args: Any, **kwargs: Any) -> None:
        """Handle updates from Ramses RF."""
        _LOGGER.debug(
            "Device update for Hello World binary sensor %s received", self._attr_name
        )
        self.async_write_ha_state()

    @property
    def is_on(self) -> bool:
        """Return true if Hello World binary sensor is active."""
        # Get current state from entities manager
        try:
            entities_manager = self._get_entities_manager(self.hass)
            current_state = entities_manager.get_entity_state(
                self.device_id, "binary_sensor", "hello_world_status"
            )
            result = bool(current_state)
            _LOGGER.debug(
                f"Binary sensor {self._attr_name} is_on: {result} "
                f"(from entities manager)"
            )
            return result
        except Exception as e:
            # Fallback to cached state
            _LOGGER.debug(
                f"Binary sensor {self._attr_name} is_on fallback: {self._is_on} "
                f"(error: {e})"
            )
            return self._is_on

    def set_state(self, is_on: bool) -> None:
        """Set the binary sensor state (used by automation triggers)."""
        self._is_on = is_on
        self.async_write_ha_state()
        _LOGGER.info(
            "Binary sensor %s state set to %s by automation",
            self._attr_name,
            is_on,
        )

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
            entity_type == "binary_sensor"
            and entity_key == "hello_world_status"
            and device_id == self.device_id
        ):
            _LOGGER.info(
                f"Binary sensor {self._attr_name} received state change: "
                f"{old_state} -> {new_state}"
            )
            self._is_on = bool(new_state)
            # Write state to Home Assistant to trigger UI updates
            self.async_write_ha_state()
            _LOGGER.info(
                f"Binary sensor {self._attr_name} state updated to {new_state}, "
                f"HA state written"
            )

    def _on_entity_state_changed_event(self, event: Any) -> None:
        """Handle HA event for entity state changes.

        Args:
            event: The event data
        """
        event_data = event.data
        if (
            event_data.get("entity_type") == "binary_sensor"
            and event_data.get("entity_key") == "hello_world_status"
            and event_data.get("device_id") == self.device_id
        ):
            _LOGGER.info(
                f"Binary sensor {self._attr_name} received HA event for state change"
            )
            # Write state to Home Assistant to trigger UI updates
            self.async_write_ha_state()
            _LOGGER.info(f"Binary sensor {self._attr_name} HA state updated via event")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        base_attrs = super().extra_state_attributes or {}
        return {
            **base_attrs,
            "automation_controlled": True,
            "controlled_by": "hello_world_automation",
            "switch_entity": (
                f"switch.hello_world_switch_{self.device_id.replace(':', '_')}"
            ),
            "demo_feature": True,
            "pattern": "switch → automation → binary_sensor",
        }


# Register this platform with the global registry
from custom_components.ramses_extras.const import (  # noqa: E402
    register_feature_platform,  # noqa: E402
)

register_feature_platform("binary_sensor", "hello_world_card", async_setup_entry)

__all__ = [
    "HelloWorldBinarySensor",
    "async_setup_entry",
    "create_hello_world_binary_sensor",
]
