"""Floorplan Helper binary sensor platform.

Creates derived ``binary_sensor.<device>_heat_demand`` entities that
mirror ramses_cc ``sensor.*_heat_demand`` percentage sensors as an
on/off signal — so a floorplan rule can be a plain
``class_set: rx-heat-demand`` without templating.

Entities are registry-driven: for every ``sensor.<x>_heat_demand``
entity provided by ``ramses_cc`` (System, TrvActuator, ZoneBase,
UfhController/UfhCircuit, OtbGateway), one binary sensor is created
and attached to the same HA device.

:platform: Home Assistant
:feature: Floorplan Helper
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event

from custom_components.ramses_extras.const import register_feature_platform

_LOGGER = logging.getLogger(__name__)

SOURCE_SUFFIX = "_heat_demand"
SOURCE_DOMAIN = "sensor"
SOURCE_PLATFORM = "ramses_cc"


class FloorplanHeatDemandBinarySensor(BinarySensorEntity):
    """On/off mirror of a ``sensor.*_heat_demand`` percentage sensor."""

    _attr_should_poll = False
    _attr_device_class = BinarySensorDeviceClass.HEAT
    _attr_icon = "mdi:radiator"

    def __init__(
        self,
        hass: HomeAssistant,
        source_entity_id: str,
        device_entry: dr.DeviceEntry | None,
    ) -> None:
        """Initialize the derived binary sensor.

        :param hass: Home Assistant instance
        :param source_entity_id: ``sensor.<x>_heat_demand`` to mirror
        :param device_entry: HA device to attach to (may be None)
        """
        self.hass = hass
        self._source_entity_id = source_entity_id
        suffix = source_entity_id.split(".", 1)[-1]
        self._attr_unique_id = f"floorplan_helper_{suffix}"
        self.entity_id = f"binary_sensor.{suffix}"
        self._attr_name = f"Heat demand {suffix.removesuffix('_heat_demand')}"
        # Attach to the source entity's device entry directly rather than
        # via DeviceInfo: device-registry lookup by identifiers is scoped
        # to this config entry, so redeclaring the ramses_cc identifiers
        # would create a nameless duplicate device under ramses_extras
        # that shadows the real device.
        self.device_entry = device_entry
        self._demand_pct: float | None = None
        self._is_on = False

    @property
    def is_on(self) -> bool:
        return self._is_on

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "source_entity_id": self._source_entity_id,
            "heat_demand_pct": self._demand_pct,
        }

    async def async_added_to_hass(self) -> None:
        """Subscribe to the source sensor's state changes."""
        self._sync_from_source()
        self.async_on_remove(
            async_track_state_change_event(
                self.hass,
                [self._source_entity_id],
                self._handle_source_change,
            )
        )

    @callback
    def _handle_source_change(self, event: Event[EventStateChangedData]) -> None:
        self._sync_from_source()
        self.async_write_ha_state()

    def _sync_from_source(self) -> None:
        state = self.hass.states.get(self._source_entity_id)
        try:
            self._demand_pct = (
                float(state.state)
                if state is not None
                and state.state not in ("unknown", "unavailable", "none")
                else None
            )
        except TypeError, ValueError:
            self._demand_pct = None
        self._is_on = self._demand_pct is not None and self._demand_pct > 0


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up derived heat-demand binary sensors."""
    entity_registry = er.async_get(hass)
    device_registry = dr.async_get(hass)

    entities: list[BinarySensorEntity] = []
    for entry in entity_registry.entities.values():
        if entry.platform != SOURCE_PLATFORM:
            continue
        if entry.domain != SOURCE_DOMAIN or not entry.entity_id.endswith(SOURCE_SUFFIX):
            continue
        raw_device = (
            device_registry.async_get(entry.device_id) if entry.device_id else None
        )
        device_entry = raw_device if isinstance(raw_device, dr.DeviceEntry) else None
        entities.append(
            FloorplanHeatDemandBinarySensor(hass, entry.entity_id, device_entry)
        )

    if entities:
        async_add_entities(entities)
        _LOGGER.info(
            "Floorplan Helper: created %d derived heat-demand binary sensors",
            len(entities),
        )


# Platform registration happens at module import (framework convention).
register_feature_platform("binary_sensor", "floorplan_helper", async_setup_entry)


__all__ = ["FloorplanHeatDemandBinarySensor", "async_setup_entry"]
