"""CO2 Zone Manager - Multi-sensor monitoring and zone management."""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from homeassistant.core import HomeAssistant, State

_LOGGER = logging.getLogger(__name__)


@dataclass
class CO2Zone:
    """Represents a CO2 monitoring zone."""

    zone_id: str
    zone_name: str
    sensor_entity: str
    threshold: int
    enabled: bool
    valve_entity: str | None = None  # Future: zone-specific valve

    # Runtime state
    current_co2: int | None = None
    is_triggered: bool = False
    last_update: datetime | None = None
    trigger_count: int = 0
    valve_position: int | None = None  # Future: valve control


class CO2ZoneManager:
    """Manages CO2 zones and multi-sensor monitoring."""

    def __init__(
        self, hass: HomeAssistant, device_id: str, config: dict[str, Any]
    ) -> None:
        """Initialize CO2 zone manager.

        :param hass: Home Assistant instance
        :param device_id: Device identifier
        :param config: Configuration dictionary
        """
        self.hass = hass
        self.device_id = device_id
        self.zones: dict[str, CO2Zone] = {}
        self._load_zones_from_config(config)

    def _load_zones_from_config(self, config: dict[str, Any]) -> None:
        """Load zones from configuration.

        :param config: Configuration dictionary
        """
        zones_config = config.get("zones", [])
        for zone_config in zones_config:
            zone = CO2Zone(
                zone_id=zone_config.get("zone_id", ""),
                zone_name=zone_config.get("zone_name", "Unknown"),
                sensor_entity=zone_config.get("sensor_entity", ""),
                threshold=zone_config.get("threshold", 1000),
                enabled=zone_config.get("enabled", True),
                valve_entity=zone_config.get("valve_entity"),
            )
            self.zones[zone.zone_id] = zone
            _LOGGER.debug(
                "Loaded CO2 zone %s (%s) for device %s",
                zone.zone_id,
                zone.zone_name,
                self.device_id,
            )

    async def update_zone_co2(self, zone_id: str, co2_value: int | None) -> None:
        """Update CO2 value for a zone.

        :param zone_id: Zone identifier
        :param co2_value: CO2 value in ppm (or None if unavailable)
        """
        if zone_id not in self.zones:
            _LOGGER.warning("Unknown zone %s for device %s", zone_id, self.device_id)
            return

        zone = self.zones[zone_id]
        zone.current_co2 = co2_value
        zone.last_update = datetime.now()

        _LOGGER.debug(
            "Updated CO2 for zone %s (%s): %s ppm",
            zone_id,
            zone.zone_name,
            co2_value,
        )

    async def check_zone_triggers(
        self, activation_hysteresis: int, deactivation_hysteresis: int
    ) -> list[str]:
        """Check which zones have exceeded thresholds.

        :param activation_hysteresis: Hysteresis for activation (positive)
        :param deactivation_hysteresis: Hysteresis for deactivation (negative)
        :return: List of triggered zone IDs
        """
        triggered_zones = []

        for zone_id, zone in self.zones.items():
            if not zone.enabled or zone.current_co2 is None:
                # Reset trigger state if zone disabled or no data
                if zone.is_triggered:
                    zone.is_triggered = False
                    _LOGGER.info(
                        "Zone %s (%s) trigger cleared (disabled or no data)",
                        zone_id,
                        zone.zone_name,
                    )
                continue

            # Calculate activation and deactivation thresholds
            activation_threshold = zone.threshold + activation_hysteresis
            deactivation_threshold = zone.threshold + deactivation_hysteresis

            # Check for trigger state changes
            if not zone.is_triggered:
                # Check if we should activate
                if zone.current_co2 >= activation_threshold:
                    zone.is_triggered = True
                    zone.trigger_count += 1
                    _LOGGER.info(
                        "Zone %s (%s) triggered: %s ppm >= %s ppm",
                        zone_id,
                        zone.zone_name,
                        zone.current_co2,
                        activation_threshold,
                    )
            else:
                # Check if we should deactivate
                if zone.current_co2 <= deactivation_threshold:
                    zone.is_triggered = False
                    _LOGGER.info(
                        "Zone %s (%s) deactivated: %s ppm <= %s ppm",
                        zone_id,
                        zone.zone_name,
                        zone.current_co2,
                        deactivation_threshold,
                    )

            if zone.is_triggered:
                triggered_zones.append(zone_id)

        return triggered_zones

    async def get_active_zones(self) -> list[CO2Zone]:
        """Get list of zones with active CO2 triggers.

        :return: List of active CO2Zone objects
        """
        return [zone for zone in self.zones.values() if zone.is_triggered]

    async def get_worst_zone(self) -> CO2Zone | None:
        """Get the zone with the highest CO2 level.

        :return: CO2Zone with highest CO2 or None if no zones have data
        """
        zones_with_data = [
            zone for zone in self.zones.values() if zone.current_co2 is not None
        ]

        if not zones_with_data:
            return None

        return max(zones_with_data, key=lambda z: z.current_co2 or 0)

    async def calculate_combined_fan_speed(
        self, base_speed: int, max_speed: int
    ) -> int:
        """Calculate fan speed based on worst zone.

        :param base_speed: Base fan speed when no zones triggered
        :param max_speed: Maximum fan speed
        :return: Calculated fan speed
        """
        active_zones = await self.get_active_zones()

        if not active_zones:
            return base_speed

        # Find zone with highest CO2 exceedance
        worst_zone = max(
            active_zones,
            key=lambda z: (z.current_co2 or 0) - z.threshold,
        )

        if worst_zone.current_co2 is None:
            return base_speed

        # Calculate fan speed based on CO2 exceedance
        exceedance = worst_zone.current_co2 - worst_zone.threshold
        exceedance_ratio = min(exceedance / 500, 1.0)  # Cap at 500 ppm over threshold

        # Linear interpolation between base and max speed
        calculated_speed = int(base_speed + (max_speed - base_speed) * exceedance_ratio)

        _LOGGER.debug(
            "Calculated fan speed %s based on zone %s "
            "(CO2: %s ppm, exceedance: %s ppm)",
            calculated_speed,
            worst_zone.zone_name,
            worst_zone.current_co2,
            exceedance,
        )

        return min(calculated_speed, max_speed)

    async def update_from_state(self, zone_id: str, state: State) -> None:
        """Update zone from Home Assistant state.

        :param zone_id: Zone identifier
        :param state: Home Assistant state object
        """
        if state.state in ("unknown", "unavailable"):
            await self.update_zone_co2(zone_id, None)
            return

        try:
            co2_value = int(float(state.state))
            await self.update_zone_co2(zone_id, co2_value)
        except ValueError, TypeError:
            _LOGGER.warning("Invalid CO2 value for zone %s: %s", zone_id, state.state)
            await self.update_zone_co2(zone_id, None)

    def get_zone_status(self) -> dict[str, Any]:
        """Get status of all zones.

        :return: Dictionary with zone status information
        """
        return {
            "zones": [
                {
                    "zone_id": zone.zone_id,
                    "zone_name": zone.zone_name,
                    "sensor_entity": zone.sensor_entity,
                    "threshold": zone.threshold,
                    "enabled": zone.enabled,
                    "current_co2": zone.current_co2,
                    "is_triggered": zone.is_triggered,
                    "trigger_count": zone.trigger_count,
                    "last_update": (
                        zone.last_update.isoformat() if zone.last_update else None
                    ),
                }
                for zone in self.zones.values()
            ],
            "active_zone_count": len(
                [z for z in self.zones.values() if z.is_triggered]
            ),
            "total_zone_count": len(self.zones),
        }

    def add_zone(self, zone_config: dict[str, Any]) -> None:
        """Add a new zone.

        :param zone_config: Zone configuration dictionary
        """
        zone = CO2Zone(
            zone_id=zone_config.get("zone_id", ""),
            zone_name=zone_config.get("zone_name", "Unknown"),
            sensor_entity=zone_config.get("sensor_entity", ""),
            threshold=zone_config.get("threshold", 1000),
            enabled=zone_config.get("enabled", True),
            valve_entity=zone_config.get("valve_entity"),
        )
        self.zones[zone.zone_id] = zone
        _LOGGER.info(
            "Added CO2 zone %s (%s) for device %s",
            zone.zone_id,
            zone.zone_name,
            self.device_id,
        )

    def remove_zone(self, zone_id: str) -> bool:
        """Remove a zone.

        :param zone_id: Zone identifier
        :return: True if zone was removed, False if not found
        """
        if zone_id in self.zones:
            del self.zones[zone_id]
            _LOGGER.info("Removed CO2 zone %s for device %s", zone_id, self.device_id)
            return True
        return False

    def update_zone_config(self, zone_id: str, updates: dict[str, Any]) -> bool:
        """Update zone configuration.

        :param zone_id: Zone identifier
        :param updates: Configuration updates
        :return: True if zone was updated, False if not found
        """
        if zone_id not in self.zones:
            return False

        zone = self.zones[zone_id]
        if "zone_name" in updates:
            zone.zone_name = updates["zone_name"]
        if "threshold" in updates:
            zone.threshold = updates["threshold"]
        if "enabled" in updates:
            zone.enabled = updates["enabled"]
        if "valve_entity" in updates:
            zone.valve_entity = updates["valve_entity"]

        _LOGGER.info(
            "Updated CO2 zone %s for device %s: %s", zone_id, self.device_id, updates
        )
        return True


__all__ = ["CO2Zone", "CO2ZoneManager"]
