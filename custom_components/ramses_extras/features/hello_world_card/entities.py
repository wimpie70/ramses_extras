# Part of the Ramses Extra integration
# See https://github.com/wimpie70/ramses_extras for more information
#
"""Entity management and state handling for Hello World Switch Card feature."""

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import HELLO_WORLD_DEVICE_ENTITY_MAPPING


class HelloWorldEntities:
    """Manages entity state and device linking for Hello World feature."""

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry) -> None:
        """Initialize entity manager."""
        self.hass = hass
        self.config_entry = config_entry
        self._entity_states: dict[str, dict[str, Any]] = {}

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
        """Set state for an entity."""
        key = f"{device_id}_{entity_type}_{entity_key}"
        if key not in self._entity_states:
            self._entity_states[key] = {}
        self._entity_states[key]["state"] = state

        # Synchronize binary sensor with switch state
        if entity_type == "switch" and entity_key == "hello_world_switch":
            self._sync_binary_sensor_state(device_id, state)

    def get_entity_states_for_device(self, device_id: str) -> dict[str, Any]:
        """Get all entity states for a device."""
        return {
            key: value
            for key, value in self._entity_states.items()
            if key.startswith(f"{device_id}_")
        }

    def _sync_binary_sensor_state(self, device_id: str, switch_state: bool) -> None:
        """Synchronize binary sensor state with switch state."""
        binary_sensor_key = f"{device_id}_binary_sensor_hello_world_status"
        if binary_sensor_key not in self._entity_states:
            self._entity_states[binary_sensor_key] = {}
        self._entity_states[binary_sensor_key]["state"] = switch_state
