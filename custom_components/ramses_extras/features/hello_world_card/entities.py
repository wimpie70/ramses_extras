# Part of the Ramses Extra integration
# See https://github.com/wimpie70/ramses_extras for more information
#
"""Entity management and state handling for Hello World Switch Card feature."""

import logging
from typing import Any, Callable

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import HELLO_WORLD_DEVICE_ENTITY_MAPPING

_LOGGER = logging.getLogger(__name__)


class HelloWorldEntities:
    """Manages entity state and device linking for Hello World feature."""

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry) -> None:
        """Initialize entity manager."""
        self.hass = hass
        self.config_entry = config_entry
        self._entity_states: dict[str, dict[str, Any]] = {}
        self._state_change_callbacks: dict[str, list] = {}

    def register_state_change_callback(
        self, entity_key: str, callback: Callable[[str, str, str, Any, Any], None]
    ) -> None:
        """Register a callback for state changes.

        Args:
            entity_key: The entity key to listen for
            callback: Callback function to call on state changes
        """
        if entity_key not in self._state_change_callbacks:
            self._state_change_callbacks[entity_key] = []
        self._state_change_callbacks[entity_key].append(callback)
        _LOGGER.debug(f"Registered state change callback for {entity_key}")

    def unregister_state_change_callback(
        self, entity_key: str, callback: Callable[[str, str, str, Any, Any], None]
    ) -> None:
        """Unregister a state change callback.

        Args:
            entity_key: The entity key
            callback: Callback function to remove
        """
        if (
            entity_key in self._state_change_callbacks
            and callback in self._state_change_callbacks[entity_key]
        ):
            self._state_change_callbacks[entity_key].remove(callback)
            _LOGGER.debug(f"Unregistered state change callback for {entity_key}")

    def _notify_state_change(
        self,
        device_id: str,
        entity_type: str,
        entity_key: str,
        old_state: Any,
        new_state: Any,
    ) -> None:
        """Notify registered callbacks of state changes.

        Args:
            device_id: Device identifier
            entity_type: Type of entity (switch, binary_sensor, etc.)
            entity_key: Specific entity key
            old_state: Previous state
            new_state: New state
        """
        entity_full_key = f"{device_id}_{entity_type}_{entity_key}"
        callbacks = self._state_change_callbacks.get(entity_full_key, [])

        for callback in callbacks:
            try:
                callback(device_id, entity_type, entity_key, old_state, new_state)
                _LOGGER.info(
                    f"Called state change callback for {entity_full_key} "
                    f"({len(callbacks)} total)"
                )
            except Exception as err:
                _LOGGER.error(
                    f"Error in state change callback for {entity_full_key}: {err}"
                )

    def get_entity_configs(self) -> dict[str, dict[str, Any]]:
        """Return entity configurations for this feature."""
        return {
            "switch": {
                "hello_world_switch": {
                    "name_template": "Hello World Switch {device_id}",
                    "entity_template": "hello_world_switch_{device_id}",
                    "icon": "mdi:lightbulb",
                    "device_types": ["HvacVentilator"],
                    "default_enabled": True,
                }
            },
            "binary_sensor": {
                "hello_world_status": {
                    "name_template": "Hello World Status {device_id}",
                    "entity_template": "hello_world_status_{device_id}",
                    "device_class": "connectivity",
                    "device_types": ["HvacVentilator"],
                    "default_enabled": True,
                }
            },
        }

    def get_device_entity_mapping(self) -> dict[str, dict[str, list[str]]]:
        """Return device to entity mapping."""
        return HELLO_WORLD_DEVICE_ENTITY_MAPPING

    def get_entity_state(
        self, device_id: str, entity_type: str, entity_key: str
    ) -> Any:
        """Get current state for an entity."""
        key = f"{device_id}_{entity_type}_{entity_key}"
        return self._entity_states.get(key, {}).get("state", False)

    def set_entity_state(
        self, device_id: str, entity_type: str, entity_key: str, state: Any
    ) -> None:
        """Set state for an entity and notify listeners.

        Args:
            device_id: Device identifier
            entity_type: Type of entity (switch, binary_sensor, etc.)
            entity_key: Specific entity key
            state: New state value
        """
        _LOGGER.info(
            f"EntitiesManager.set_entity_state called: {device_id}, {entity_type}, "
            f"{entity_key}, {state}"
        )
        key = f"{device_id}_{entity_type}_{entity_key}"
        old_state = self._entity_states.get(key, {}).get("state", False)

        # Only update if state actually changed
        if bool(old_state) == bool(state):
            _LOGGER.debug(f"State unchanged for {key}, skipping update")
            return

        if key not in self._entity_states:
            self._entity_states[key] = {}
        self._entity_states[key]["state"] = state

        _LOGGER.info(f"Updated entity state: {key} -> {state}")

        # Notify registered callbacks
        _LOGGER.info(
            f"Notifying {len(self._state_change_callbacks.get(key, []))} "
            f"callbacks for {key}"
        )
        self._notify_state_change(device_id, entity_type, entity_key, old_state, state)

        # Fire Home Assistant event for real-time updates
        self._fire_state_change_event(
            device_id, entity_type, entity_key, old_state, state
        )

        # Synchronize binary sensor with switch state
        if entity_type == "switch" and entity_key == "hello_world_switch":
            _LOGGER.info(f"Syncing binary sensor state for {device_id}")
            self._sync_binary_sensor_state(device_id, state)

    def _fire_state_change_event(
        self,
        device_id: str,
        entity_type: str,
        entity_key: str,
        old_state: Any,
        new_state: Any,
    ) -> None:
        """Fire a Home Assistant event for state changes.

        Args:
            device_id: Device identifier
            entity_type: Type of entity
            entity_key: Specific entity key
            old_state: Previous state
            new_state: New state
        """
        try:
            entity_id = (
                f"{entity_type}.hello_world_{entity_key}_{device_id.replace(':', '_')}"
            )

            event_data = {
                "device_id": device_id,
                "entity_type": entity_type,
                "entity_key": entity_key,
                "entity_id": entity_id,
                "old_state": old_state,
                "new_state": new_state,
                "source": "hello_world_entities",
                "timestamp": self.hass.loop.time()
                if self.hass and self.hass.loop
                else None,
            }

            self.hass.bus.async_fire("hello_world_entity_state_changed", event_data)

            _LOGGER.debug(
                f"Fired state change event for {entity_id}: {old_state} -> {new_state}"
            )

        except Exception as err:
            _LOGGER.error(f"Failed to fire state change event: {err}")

    def _sync_binary_sensor_state(self, device_id: str, switch_state: bool) -> None:
        """Synchronize binary sensor state with switch state."""
        binary_sensor_key = f"{device_id}_binary_sensor_hello_world_status"
        old_sensor_state = self._entity_states.get(binary_sensor_key, {}).get(
            "state", False
        )

        # Only update if different from current state
        if bool(old_sensor_state) != bool(switch_state):
            self._entity_states[binary_sensor_key] = {"state": switch_state}
            _LOGGER.info(
                f"Synced binary sensor state for {device_id}: "
                f"{old_sensor_state} -> {switch_state}"
            )

            # Notify binary sensor state change
            self._notify_state_change(
                device_id,
                "binary_sensor",
                "hello_world_status",
                old_sensor_state,
                switch_state,
            )
            _LOGGER.info(
                f"Binary sensor state change notification sent for {device_id}"
            )

            # Fire event for binary sensor change
            entity_id = (
                f"binary_sensor.hello_world_status_{device_id.replace(':', '_')}"
            )
            self.hass.bus.async_fire(
                "hello_world_entity_state_changed",
                {
                    "device_id": device_id,
                    "entity_type": "binary_sensor",
                    "entity_key": "hello_world_status",
                    "entity_id": entity_id,
                    "old_state": old_sensor_state,
                    "new_state": switch_state,
                    "source": "binary_sensor_sync",
                    "timestamp": self.hass.loop.time()
                    if self.hass and self.hass.loop
                    else None,
                },
            )

    def get_entity_states_for_device(self, device_id: str) -> dict[str, Any]:
        """Get all entity states for a device."""
        return {
            key: value
            for key, value in self._entity_states.items()
            if key.startswith(f"{device_id}_")
        }
