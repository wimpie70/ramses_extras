"""Zone coordinator for FAN-level zone demand aggregation.

This module provides the ZoneCoordinator class that monitors zone states,
converts them into FAN-level speed demands, and feeds them to the arbiter
with proper conflict resolution rules.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any

from homeassistant.core import HomeAssistant

from ...const import DOMAIN
from .fan_speed_arbiter import get_fan_speed_arbiter
from .zone_adapters import ZoneAdapterRegistry, get_zone_adapter_registry
from .zone_demand import DemandSource, ZoneDemandRegistry, get_zone_demand_registry

if TYPE_CHECKING:
    pass

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
    priority: int = _DEFAULT_ZONE_PRIORITY  # For FAN-level demand arbitration
    min_position_for_demand: int = 10  # Position threshold to trigger fan demand
    demand_mapping: dict[int, str] | None = None  # Map position ranges to fan speeds
    # Phase 5a: Actuator min/max positions for demand-driven actuation
    min_position: int = 0  # Actuator position when no demand (e.g., 0% = closed)
    max_position: int = 100  # Actuator position when demand (e.g., 100% = open)
    is_controllable: bool = False  # Whether zone has controllable actuators
    # Phase 5b: Priority for demand resolution when max_open_zones limits active zones
    actuation_priority: int = 100  # Higher = more likely to be selected (default 100)
    # Hardware actuator configuration
    zone_type: str = "paired_valves"  # Type of zone adapter
    inlet_valve_entity: str | None = None  # Inlet valve entity ID
    outlet_valve_entity: str | None = None  # Outlet valve entity ID


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
        self._demand_registry = get_zone_demand_registry(hass)
        self._zone_configs: dict[str, ZoneConfig] = {}
        self._last_states: dict[str, ZoneState] = {}
        self._enabled = True
        # Phase 5b: Max open zones cap for demand resolution
        self._max_open_zones: int | None = None  # None = no limit
        # Track last actuator commands for diagnostics
        self._last_actuator_commands: dict[str, dict[str, Any]] = {}

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
        min_position: int | None = None,
        max_position: int | None = None,
        is_controllable: bool | None = None,
        actuation_priority: int | None = None,
        zone_type: str | None = None,
        inlet_valve_entity: str | None = None,
        outlet_valve_entity: str | None = None,
    ) -> None:
        """Configure zone coordination parameters.

        Args:
            zone_id: Zone identifier
            priority: Priority for this zone's demands (higher wins)
            min_position_for_demand: Minimum position to trigger fan demand
            demand_mapping: Dict mapping position thresholds to fan speeds
                          e.g., {20: "fan_low", 50: "fan_medium", 80: "fan_high"}
            min_position: Actuator position when zone has no demand (0-100)
            max_position: Actuator position when zone has demand (0-100)
            is_controllable: Whether this zone has controllable actuators
            actuation_priority: Priority for demand resolution (higher = selected first
                               when max_open_zones limits active zones)
            zone_type: Type of zone adapter (e.g., "paired_valves")
            inlet_valve_entity: Entity ID for inlet valve
            outlet_valve_entity: Entity ID for outlet valve
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
            min_position=min_position
            if min_position is not None
            else (existing.min_position if existing else 0),
            max_position=max_position
            if max_position is not None
            else (existing.max_position if existing else 100),
            is_controllable=is_controllable
            if is_controllable is not None
            else (existing.is_controllable if existing else False),
            actuation_priority=actuation_priority
            if actuation_priority is not None
            else (existing.actuation_priority if existing else 100),
            zone_type=zone_type
            if zone_type is not None
            else (existing.zone_type if existing else "paired_valves"),
            inlet_valve_entity=inlet_valve_entity
            if inlet_valve_entity is not None
            else (existing.inlet_valve_entity if existing else None),
            outlet_valve_entity=outlet_valve_entity
            if outlet_valve_entity is not None
            else (existing.outlet_valve_entity if existing else None),
        )
        _LOGGER.debug(
            "Configured zone %s:%s with priority %s, min=%s, max=%s, controllable=%s",
            self._fan_id,
            zone_id,
            self._zone_configs[zone_id].priority,
            self._zone_configs[zone_id].min_position,
            self._zone_configs[zone_id].max_position,
            self._zone_configs[zone_id].is_controllable,
        )

    def set_max_open_zones(self, max_open_zones: int | None) -> None:
        """Set maximum number of zones that can be open simultaneously.

        Args:
            max_open_zones: Maximum number of zones to open (None = no limit)
        """
        self._max_open_zones = max_open_zones
        _LOGGER.debug(
            "Set max_open_zones for %s to %s",
            self._fan_id,
            max_open_zones if max_open_zones is not None else "unlimited",
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
            Dictionary with coordinator state including actuator commands
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
            "max_open_zones": self._max_open_zones,
            "configured_zones": {
                zone_id: {
                    "priority": config.priority,
                    "min_position_for_demand": config.min_position_for_demand,
                    "min_position": config.min_position,
                    "max_position": config.max_position,
                    "is_controllable": config.is_controllable,
                    "actuation_priority": config.actuation_priority,
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
            "last_actuator_commands": self._last_actuator_commands,
            "demand_registry": self._demand_registry.get_diagnostics(),
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

    async def async_run_zone_actuation_cycle(self) -> dict[str, Any]:
        """Run one zone actuation cycle: check demands and drive actuators.

        This is Phase 5a/5b: demand-driven min/max actuation with priority.
        - If zone has demand (from humidity/CO2/etc): eligible for max_position
        - With max_open_zones: highest priority zones selected for max_position
        - Otherwise: drive to min_position

        Returns:
            Dict with results per zone {zone_id: {"target": pos, "actual": pos}}
        """
        if not self._enabled:
            return {}

        results: dict[str, Any] = {}

        # Get all zone configs for this FAN
        all_zone_ids = list(self._zone_configs.keys())
        if not all_zone_ids:
            _LOGGER.debug("No zones configured for FAN %s", self._fan_id)
            return results

        _LOGGER.debug(
            "Running actuation cycle for FAN %s with %s zones",
            self._fan_id,
            len(all_zone_ids),
        )

        # Phase 5b: First pass - collect zones with demand and their priorities
        zones_with_demand: list[tuple[str, int]] = []  # (zone_id, actuation_priority)

        for zone_id in all_zone_ids:
            # Get zone config
            zone_config = self._zone_configs.get(zone_id)
            if zone_config is None or not zone_config.is_controllable:
                continue

            # Check if zone has demand
            if self._demand_registry.has_demand(self._fan_id, zone_id):
                zones_with_demand.append((zone_id, zone_config.actuation_priority))
                _LOGGER.debug(
                    "Zone %s:%s has demand (priority=%s)",
                    self._fan_id,
                    zone_id,
                    zone_config.actuation_priority,
                )

        # Phase 5b: Select zones to open based on priority if max_open_zones is set
        selected_for_max: set[str] = set()
        if zones_with_demand:
            # Sort by actuation_priority descending (higher = more important)
            zones_with_demand.sort(key=lambda x: x[1], reverse=True)

            # If max_open_zones is set, limit selection
            if self._max_open_zones is not None:
                selected_count = min(len(zones_with_demand), self._max_open_zones)
                selected_for_max = {
                    zone_id for zone_id, _ in zones_with_demand[:selected_count]
                }
                _LOGGER.debug(
                    "Phase 5b: Selected %s/%s zones for max_position (cap=%s)",
                    selected_count,
                    len(zones_with_demand),
                    self._max_open_zones,
                )
            else:
                # No limit - all demanding zones go to max
                selected_for_max = {zone_id for zone_id, _ in zones_with_demand}

        # Second pass - actuate each zone
        for zone_id in all_zone_ids:
            # Get zone config for safety limits
            zone_config = self._zone_configs.get(zone_id)
            if zone_config is None or not zone_config.is_controllable:
                continue

            # Get or create adapter for this zone
            adapter = self._adapter_registry.get_or_create_adapter(
                fan_id=self._fan_id,
                zone_id=zone_id,
                zone_type=zone_config.zone_type,
                inlet_entity=zone_config.inlet_valve_entity,
                outlet_entity=zone_config.outlet_valve_entity,
            )

            if adapter is None:
                _LOGGER.warning(
                    "Failed to get/create adapter for zone %s:%s", self._fan_id, zone_id
                )
                continue

            # Check if zone is available
            if not adapter.is_available:
                _LOGGER.debug(
                    "Zone %s:%s adapter not available, skipping", self._fan_id, zone_id
                )
                continue

            # Determine target position based on demand and priority selection
            is_selected = zone_id in selected_for_max
            has_demand = self._demand_registry.has_demand(self._fan_id, zone_id)

            if is_selected:
                target_position = zone_config.max_position
                reason = "Zone has demand (selected for max)"
            elif has_demand:
                target_position = zone_config.min_position
                reason = "Zone has demand but not selected (priority/cap)"
            else:
                target_position = zone_config.min_position
                reason = "Zone has no demand"

            try:
                # Get current position before commanding
                position_data = await adapter.async_get_position()
                current_position = position_data.position

                # Only command if position differs significantly
                if abs(current_position - target_position) >= 5:
                    success = await adapter.async_set_position(target_position)

                    # Track for diagnostics
                    self._last_actuator_commands[zone_id] = {
                        "timestamp": datetime.now(),
                        "target_position": target_position,
                        "previous_position": current_position,
                        "has_demand": has_demand,
                        "is_selected": is_selected,
                        "reason": reason,
                        "success": success,
                    }

                    results[zone_id] = {
                        "target": target_position,
                        "previous": current_position,
                        "success": success,
                        "has_demand": has_demand,
                        "is_selected": is_selected,
                    }

                    _LOGGER.debug(
                        "Zone %s:%s actuated to %s%% (demand=%s, selected=%s)",
                        self._fan_id,
                        zone_id,
                        target_position,
                        has_demand,
                        is_selected,
                    )
                else:
                    # Position already close enough
                    results[zone_id] = {
                        "target": target_position,
                        "current": current_position,
                        "success": True,
                        "has_demand": has_demand,
                        "is_selected": is_selected,
                        "skipped": True,
                    }

            except Exception as e:
                _LOGGER.warning(
                    "Failed to actuate zone %s:%s: %s", self._fan_id, zone_id, e
                )
                results[zone_id] = {
                    "error": str(e),
                    "target": target_position,
                    "has_demand": has_demand,
                    "is_selected": is_selected,
                }

        return results

    def has_zone_demand(self, zone_id: str) -> bool:
        """Check if a zone has active demand from any source.

        Args:
            zone_id: Zone identifier

        Returns:
            True if zone has demand from humidity/CO2/manual sources
        """
        return self._demand_registry.has_demand(self._fan_id, zone_id)

    def get_zone_demand_breakdown(self, zone_id: str) -> dict[str, bool]:
        """Get demand breakdown by source for a zone.

        Returns dict mapping source name to demand state.
        """
        breakdown = self._demand_registry.get_demand_breakdown(self._fan_id, zone_id)
        return {source.name: state for source, state in breakdown.items()}


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
