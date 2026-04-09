# Part of the Ramses Extra integration
# See https://github.com/wimpie70/ramses_extras for more information
#
"""Sensor platform for Device Simulator.

Provides status sensors:
  - Active devices count
  - Messages sent count
  - Simulator state (idle/running)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.sensor import SensorEntity

from ..const import DOMAIN, LOGGER
from ..scenario_engine import ScenarioEngine

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: object,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Device Simulator sensor platform."""
    async_add_entities(
        [
            SimulatorStatusSensor(hass),
            SimulatorMessagesSensor(hass),
            SimulatorDevicesSensor(hass),
        ]
    )


class SimulatorBaseSensor(SensorEntity):
    """Base class for Device Simulator sensors."""

    def __init__(self, hass: HomeAssistant, name: str, unique_id: str) -> None:
        """Initialize the sensor.

        :param hass: Home Assistant instance.
        :param name: Sensor name.
        :param unique_id: Unique entity ID.
        """
        self.hass = hass
        self._attr_name = f"Device Simulator {name}"
        self._attr_unique_id = f"{DOMAIN}_{unique_id}"
        self._attr_should_poll = True
        self._unsub = None

    @property
    def available(self) -> bool:
        """Return True if simulator is initialized."""
        registry = self.hass.data.get("ramses_extras", {})
        return "device_simulator_engine" in registry

    def _get_engine(self) -> ScenarioEngine | None:
        """Get the scenario engine if available."""
        from typing import cast

        registry = self.hass.data.get("ramses_extras", {})
        return cast(ScenarioEngine | None, registry.get("device_simulator_engine"))


class SimulatorStatusSensor(SimulatorBaseSensor):
    """Sensor showing simulator state (idle/running)."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize status sensor."""
        super().__init__(hass, "Status", "status")
        self._attr_native_unit_of_measurement = None

    @property
    def native_value(self) -> str:
        """Return current simulator state."""
        engine = self._get_engine()
        if not engine:
            return "unavailable"
        return engine.state

    @property
    def extra_state_attributes(self) -> dict:
        """Return additional state info."""
        engine = self._get_engine()
        if not engine:
            return {}
        return {
            "connected": engine._endpoint.is_connected,
            "active_devices": len(engine.active_device_ids),
        }


class SimulatorMessagesSensor(SimulatorBaseSensor):
    """Sensor showing total messages sent."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize messages sensor."""
        super().__init__(hass, "Messages Sent", "messages_sent")
        self._attr_native_unit_of_measurement = "msgs"
        self._attr_state_class = "total"

    @property
    def native_value(self) -> int:
        """Return total messages sent."""
        engine = self._get_engine()
        if not engine:
            return 0
        return engine.messages_sent


class SimulatorDevicesSensor(SimulatorBaseSensor):
    """Sensor showing active device IDs."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize devices sensor."""
        super().__init__(hass, "Active Devices", "active_devices")
        self._attr_native_unit_of_measurement = "devices"

    @property
    def native_value(self) -> int:
        """Return count of active devices."""
        engine = self._get_engine()
        if not engine:
            return 0
        return len(engine.active_device_ids)

    @property
    def extra_state_attributes(self) -> dict:
        """Return list of active device IDs."""
        engine = self._get_engine()
        if not engine:
            return {}
        return {"device_ids": engine.active_device_ids}
