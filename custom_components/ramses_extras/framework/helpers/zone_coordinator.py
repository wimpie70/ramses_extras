"""Zone coordinator for FAN-level zone demand aggregation.

This module provides the ZoneCoordinator class that monitors zone states,
converts them into FAN-level speed demands, and feeds them to the arbiter
with proper conflict resolution rules.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any

from homeassistant.core import HomeAssistant

from ...const import DOMAIN
from .fan_speed_arbiter import get_fan_speed_arbiter
from .zone_adapters import ZoneAdapterRegistry, get_zone_adapter_registry

if TYPE_CHECKING:
    from datetime import datetime

_LOGGER = logging.getLogger(__name__)

# Feature ID for zone coordination in arbiter
_ZONES_FEATURE_ID = "zones"

# Default zone priorities (higher = wins)
_DEFAULT_ZONE_PRIORITY = 50
_HUMIDITY_ZONE_PRIORITY = 70
_CO2_ZONE_PRIORITY = 60
_MANUAL_ZONE_PRIORITY = 100


class ZoneDemandSource(Enum):
    """Source of zone demand."""

    AUTO = "auto"  # Automatic based on sensors
    HUMIDITY = "humidity"  # Humidity-driven demand
    CO2 = "co2"  # CO2-driven demand
    MANUAL = "manual"  # Manual override
    SCHEDULE = "schedule"  # Schedule-based


@dataclass
class ZoneState:
    """Current state of a zone."""

    zone_id: str
    fan_id: str
    position: int  # 0-100
    is_available: bool
    is_controllable: bool
    demand_source: ZoneDemandSource
    demand_reason: str
    timestamp: datetime


@dataclass
class ZoneConfig:
    """Configuration for zone coordination."""

    zone_id: str
    priority: int = _DEFAULT_ZONE_PRIORITY
    min_position_for_demand: int = 10  # Position threshold to trigger fan demand
    demand_mapping: dict[int, str] | None = None  # Map position ranges to fan speeds


class ZoneCoordinator:
    """Coordinates zone states into FAN-level fan speed demands.

    This class monitors all zones for a FAN, converts their positions into
    fan speed demands, and feeds them to the arbiter. It handles conflict
    resolution with humidity/CO2/manual override through priority settings.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        fan_id: str,
    ) -> None:
        """Initialize the zone coordinator.

        Args:
            hass: Home Assistant instance
            fan_id: FAN device ID this coordinator manages
        """
        self._hass = hass
        self._fan_id = fan_id
        self._adapter_registry = get_zone_adapter_registry(hass)
        self._zone_configs: dict[str, ZoneConfig] = {}
        self._last_states: dict[str, ZoneState] = {}
        self._enabled = True

    @property
    def fan_id(self) -> str:
        """Return the FAN device ID."""
        return self._fan_id

    @property
    def is_enabled(self) -> bool:
        """Return whether coordinator is enabled."""
        return self._enabled

    def set_enabled(self, enabled: bool) -> None:
        """Enable or disable the coordinator.

        When disabled, all zone demands are cleared from the arbiter.
        """
        if enabled == self._enabled:
            return

        self._enabled = enabled
        if not enabled:
            # Clear all zone demands when disabled
            self._clear_all_demands()
        _LOGGER.debug(
            "Zone coordinator for %s %s",
            self._fan_id,
            "enabled" if enabled else "disabled",
        )

    def configure_zone(
        self,
        zone_id: str,
        priority: int | None = None,
        min_position_for_demand: int | None = None,
        demand_mapping: dict[int, str] | None = None,
    ) -> None:
        """Configure zone coordination parameters.

        Args:
            zone_id: Zone identifier
            priority: Priority for this zone's demands (higher wins)
            min_position_for_demand: Minimum position to trigger fan demand
            demand_mapping: Dict mapping position thresholds to fan speeds
                          e.g., {20: "fan_low", 50: "fan_medium", 80: "fan_high"}
        """
        existing = self._zone_configs.get(zone_id)
        self._zone_configs[zone_id] = ZoneConfig(
            zone_id=zone_id,
            priority=priority
            if priority is not None
            else (existing.priority if existing else _DEFAULT_ZONE_PRIORITY),
            min_position_for_demand=min_position_for_demand
            if min_position_for_demand is not None
            else (existing.min_position_for_demand if existing else 10),
            demand_mapping=demand_mapping
            if demand_mapping is not None
            else (existing.demand_mapping if existing else None),
        )
        _LOGGER.debug(
            "Configured zone %s:%s with priority %s",
            self._fan_id,
            zone_id,
            self._zone_configs[zone_id].priority,
        )

    def _get_default_demand_mapping(self) -> dict[int, str]:
        """Get default position to fan speed mapping.

        Returns:
            Dict mapping position thresholds to fan speeds
        """
        return {
            0: "fan_auto",  # Zone closed - let FAN decide
            20: "fan_low",  # Low opening - low speed
            50: "fan_medium",  # Medium opening - medium speed
            80: "fan_high",  # High opening - high speed
        }

    def _position_to_fan_speed(
        self, position: int, mapping: dict[int, str] | None = None
    ) -> str:
        """Convert zone position to fan speed demand.

        Args:
            position: Zone position (0-100)
            mapping: Optional custom position to speed mapping

        Returns:
            Fan speed command name
        """
        effective_mapping = mapping or self._get_default_demand_mapping()

        # Sort thresholds in descending order
        thresholds = sorted(effective_mapping.keys(), reverse=True)

        # Find the highest threshold that position meets or exceeds
        for threshold in thresholds:
            if position >= threshold:
                return effective_mapping[threshold]

        return "fan_auto"

    async def async_update_zone_state(self, zone_id: str) -> ZoneState | None:
        """Update and return the current state for a zone.

        Args:
            zone_id: Zone identifier

        Returns:
            ZoneState or None if zone not available
        """
        from datetime import datetime

        # Get the zone adapter
        adapter = self._adapter_registry.get_or_create_adapter(self._fan_id, zone_id)
        if adapter is None:
            _LOGGER.debug("No adapter available for zone %s:%s", self._fan_id, zone_id)
            return None

        # Get current position
        position_data = await adapter.async_get_position()

        # Determine demand source based on configuration or heuristics
        # zone_config = self._zone_configs.get(zone_id, ZoneConfig(zone_id=zone_id))

        # Build zone state
        state = ZoneState(
            zone_id=zone_id,
            fan_id=self._fan_id,
            position=position_data.position,
            is_available=adapter.is_available and position_data.is_available,
            is_controllable=zone_id
            in self._zone_configs,  # Only if explicitly configured
            demand_source=ZoneDemandSource.AUTO,  # Default, can be overridden
            demand_reason=f"Zone position: {position_data.position}%",
            timestamp=datetime.now(),
        )

        self._last_states[zone_id] = state
        return state

    async def async_evaluate_and_apply(self) -> bool:
        """Evaluate all zones and apply demands to arbiter.

        Returns:
            True if any demands were applied
        """
        if not self._enabled:
            return False

        # Get all zone adapters for this FAN
        adapters = self._adapter_registry.get_all_adapters_for_fan(self._fan_id)

        applied = False
        for adapter in adapters:
            zone_id = adapter.zone_id
            state = await self.async_update_zone_state(zone_id)

            if state is None or not state.is_available:
                # Clear demand for unavailable zone
                await self._clear_zone_demand(zone_id)
                continue

            # Check if position meets threshold for demand
            zone_config = self._zone_configs.get(zone_id)
            if zone_config is None:
                # Zone not configured for coordination
                continue

            min_position = zone_config.min_position_for_demand
            if state.position < min_position:
                # Position below threshold, clear demand
                await self._clear_zone_demand(zone_id)
                continue

            # Convert position to fan speed
            fan_speed = self._position_to_fan_speed(
                state.position, zone_config.demand_mapping
            )

            # Apply demand through arbiter
            await self._apply_zone_demand(
                zone_id=zone_id,
                fan_speed=fan_speed,
                priority=zone_config.priority,
                reason=state.demand_reason,
                source=state.demand_source,
            )
            applied = True

        return applied

    async def _apply_zone_demand(
        self,
        zone_id: str,
        fan_speed: str,
        priority: int,
        reason: str,
        source: ZoneDemandSource,
    ) -> bool:
        """Apply a zone demand to the fan speed arbiter.

        Args:
            zone_id: Zone identifier
            fan_speed: Requested fan speed
            priority: Demand priority
            reason: Human-readable reason
            source: Source of demand

        Returns:
            True if demand was applied
        """
        arbiter = get_fan_speed_arbiter(self._hass)

        # Adjust priority based on demand source
        effective_priority = priority
        if source == ZoneDemandSource.HUMIDITY:
            effective_priority = max(priority, _HUMIDITY_ZONE_PRIORITY)
        elif source == ZoneDemandSource.CO2:
            effective_priority = max(priority, _CO2_ZONE_PRIORITY)
        elif source == ZoneDemandSource.MANUAL:
            effective_priority = max(priority, _MANUAL_ZONE_PRIORITY)

        # Set the demand - use _set_demand_state + commit for atomic operation
        arbiter._set_demand_state(
            self._fan_id,
            feature_id=_ZONES_FEATURE_ID,
            source_id=zone_id,
            requested_speed=fan_speed,
            priority=effective_priority,
            reason=reason,
            metadata={
                "zone_id": zone_id,
                "fan_id": self._fan_id,
                "source": source.value,
                "original_priority": priority,
            },
        )

        # Commit the demand (without immediate apply - let arbiter batch)
        result: bool = await arbiter.async_commit_state(self._fan_id, apply=True)
        return result

    async def _clear_zone_demand(self, zone_id: str) -> bool:
        """Clear a zone's demand from the arbiter.

        Args:
            zone_id: Zone identifier

        Returns:
            True if demand was cleared
        """
        arbiter = get_fan_speed_arbiter(self._hass)

        # Check if there's an active demand for this zone
        active_demands = arbiter.get_active_demands(self._fan_id)
        has_demand = any(
            d.feature_id == _ZONES_FEATURE_ID and d.source_id == zone_id
            for d in active_demands
        )

        if not has_demand:
            return False

        # Clear the demand
        arbiter.clear_demand_state(
            self._fan_id,
            feature_id=_ZONES_FEATURE_ID,
            source_id=zone_id,
        )

        result: bool = await arbiter.async_commit_state(self._fan_id, apply=True)
        return result

    def _clear_all_demands(self) -> None:
        """Clear all zone demands from the arbiter."""
        arbiter = get_fan_speed_arbiter(self._hass)

        arbiter.clear_demand_state(
            self._fan_id,
            feature_id=_ZONES_FEATURE_ID,
        )

        # Fire-and-forget commit
        if hasattr(self._hass, "async_create_task"):
            self._hass.async_create_task(
                arbiter.async_commit_state(self._fan_id, apply=True)
            )

    def get_zone_states(self) -> dict[str, ZoneState]:
        """Get current states for all monitored zones.

        Returns:
            Dict mapping zone_id to ZoneState
        """
        return dict(self._last_states)

    def get_zone_config(self, zone_id: str) -> ZoneConfig | None:
        """Get configuration for a zone.

        Args:
            zone_id: Zone identifier

        Returns:
            ZoneConfig or None if not configured
        """
        return self._zone_configs.get(zone_id)

    def get_diagnostics(self) -> dict[str, Any]:
        """Return diagnostic information for this coordinator.

        Returns:
            Dictionary with coordinator state
        """
        # Get arbiter state for this FAN
        arbiter = get_fan_speed_arbiter(self._hass)
        zone_demands = [
            d
            for d in arbiter.get_active_demands(self._fan_id)
            if d.feature_id == _ZONES_FEATURE_ID
        ]

        return {
            "fan_id": self._fan_id,
            "enabled": self._enabled,
            "configured_zones": {
                zone_id: {
                    "priority": config.priority,
                    "min_position": config.min_position_for_demand,
                    "demand_mapping": config.demand_mapping,
                }
                for zone_id, config in self._zone_configs.items()
            },
            "zone_states": {
                zone_id: {
                    "position": state.position,
                    "available": state.is_available,
                    "controllable": state.is_controllable,
                    "source": state.demand_source.value,
                    "reason": state.demand_reason,
                }
                for zone_id, state in self._last_states.items()
            },
            "active_demands": [
                {
                    "zone_id": d.source_id,
                    "fan_speed": d.requested_speed,
                    "priority": d.priority,
                    "reason": d.reason,
                }
                for d in zone_demands
            ],
        }

    async def async_set_manual_zone_demand(
        self,
        zone_id: str,
        fan_speed: str,
        reason: str = "Manual zone demand",
    ) -> bool:
        """Set a manual demand for a zone (e.g., from UI or automation).

        Args:
            zone_id: Zone identifier
            fan_speed: Requested fan speed
            reason: Human-readable reason

        Returns:
            True if demand was applied
        """
        zone_config = self._zone_configs.get(zone_id)
        priority = zone_config.priority if zone_config else _DEFAULT_ZONE_PRIORITY

        return await self._apply_zone_demand(
            zone_id=zone_id,
            fan_speed=fan_speed,
            priority=priority,
            reason=reason,
            source=ZoneDemandSource.MANUAL,
        )

    async def async_clear_manual_zone_demand(self, zone_id: str) -> bool:
        """Clear manual demand for a zone.

        Args:
            zone_id: Zone identifier

        Returns:
            True if demand was cleared
        """
        return await self._clear_zone_demand(zone_id)


class ZoneCoordinatorRegistry:
    """Registry for zone coordinators per FAN."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the coordinator registry."""
        self._hass = hass
        self._coordinators: dict[str, ZoneCoordinator] = {}

    def get_or_create_coordinator(self, fan_id: str) -> ZoneCoordinator:
        """Get or create a coordinator for a FAN.

        Args:
            fan_id: FAN device ID

        Returns:
            ZoneCoordinator instance
        """
        normalized_id = fan_id.replace("_", ":").strip()

        if normalized_id not in self._coordinators:
            self._coordinators[normalized_id] = ZoneCoordinator(
                self._hass, normalized_id
            )
            _LOGGER.debug("Created zone coordinator for %s", normalized_id)

        return self._coordinators[normalized_id]

    def get_coordinator(self, fan_id: str) -> ZoneCoordinator | None:
        """Get existing coordinator for a FAN.

        Args:
            fan_id: FAN device ID

        Returns:
            ZoneCoordinator or None if not found
        """
        normalized_id = fan_id.replace("_", ":").strip()
        return self._coordinators.get(normalized_id)

    def remove_coordinator(self, fan_id: str) -> None:
        """Remove a coordinator from the registry.

        Args:
            fan_id: FAN device ID
        """
        normalized_id = fan_id.replace("_", ":").strip()
        coordinator = self._coordinators.pop(normalized_id, None)
        if coordinator:
            coordinator.set_enabled(False)
            _LOGGER.debug("Removed zone coordinator for %s", normalized_id)

    def get_all_coordinators(self) -> list[ZoneCoordinator]:
        """Get all registered coordinators.

        Returns:
            List of ZoneCoordinator instances
        """
        return list(self._coordinators.values())

    def clear(self) -> None:
        """Clear all coordinators."""
        for coordinator in self._coordinators.values():
            coordinator.set_enabled(False)
        self._coordinators.clear()

    def get_diagnostics(self) -> dict[str, Any]:
        """Return diagnostic information for all coordinators.

        Returns:
            Dictionary with registry state
        """
        return {
            "coordinator_count": len(self._coordinators),
            "coordinators": {
                fan_id: coord.get_diagnostics()
                for fan_id, coord in self._coordinators.items()
            },
        }


# Singleton registry instance
_zone_coordinator_registry: ZoneCoordinatorRegistry | None = None


def get_zone_coordinator_registry(hass: HomeAssistant) -> ZoneCoordinatorRegistry:
    """Get or create the zone coordinator registry.

    Args:
        hass: Home Assistant instance

    Returns:
        ZoneCoordinatorRegistry instance
    """
    global _zone_coordinator_registry

    if _zone_coordinator_registry is None:
        _zone_coordinator_registry = ZoneCoordinatorRegistry(hass)
        _LOGGER.debug("Created zone coordinator registry")

    return _zone_coordinator_registry


def get_zone_coordinator(hass: HomeAssistant, fan_id: str) -> ZoneCoordinator:
    """Get or create a zone coordinator for a FAN.

    Args:
        hass: Home Assistant instance
        fan_id: FAN device ID

    Returns:
        ZoneCoordinator instance
    """
    registry = get_zone_coordinator_registry(hass)
    return registry.get_or_create_coordinator(fan_id)


def async_setup_zone_coordinators(hass: HomeAssistant) -> None:
    """Set up zone coordinator infrastructure.

    Args:
        hass: Home Assistant instance
    """
    get_zone_coordinator_registry(hass)
    _LOGGER.info("Zone coordinator infrastructure initialized")


__all__ = [
    "ZoneCoordinator",
    "ZoneCoordinatorRegistry",
    "ZoneState",
    "ZoneConfig",
    "ZoneDemandSource",
    "get_zone_coordinator",
    "get_zone_coordinator_registry",
    "async_setup_zone_coordinators",
]
