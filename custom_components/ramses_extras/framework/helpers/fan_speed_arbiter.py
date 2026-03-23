"""Shared fan speed arbitration helper for cross-feature control."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from custom_components.ramses_extras.const import DOMAIN

from .ramses_commands import RamsesCommands

_LOGGER = logging.getLogger(__name__)

_SPEED_ORDER = {
    "fan_auto": 0,
    "fan_low": 1,
    "fan_medium": 2,
    "fan_high": 3,
}

_SPEED_NORMALIZATION = {
    "auto": "fan_auto",
    "low": "fan_low",
    "medium": "fan_medium",
    "high": "fan_high",
    "fan_auto": "fan_auto",
    "fan_low": "fan_low",
    "fan_medium": "fan_medium",
    "fan_high": "fan_high",
    0: "fan_auto",
    1: "fan_low",
    2: "fan_low",
    3: "fan_medium",
    4: "fan_high",
    5: "fan_high",
}


@dataclass(slots=True)
class FanSpeedDemand:
    """A single feature demand for a device fan speed."""

    feature_id: str
    source_id: str
    requested_speed: str
    priority: int = 0
    reason: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(slots=True)
class ResolvedFanSpeed:
    """Resolved fan speed for a device."""

    device_id: str
    command_name: str
    winning_demand: FanSpeedDemand | None
    active_demands: list[FanSpeedDemand]


class FanSpeedArbiter:
    """Resolve multiple feature fan demands into a single command."""

    def __init__(self, hass: Any) -> None:
        self.hass = hass
        self.ramses_commands = RamsesCommands(hass)
        self._demands: dict[str, dict[tuple[str, str], FanSpeedDemand]] = {}

    async def async_set_demand(
        self,
        device_id: str,
        *,
        feature_id: str,
        source_id: str,
        requested_speed: str | int,
        priority: int = 0,
        reason: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        """Create or update a feature demand and apply the resolved command."""
        command_name = self.normalize_speed(requested_speed)
        demand = FanSpeedDemand(
            feature_id=feature_id,
            source_id=source_id,
            requested_speed=command_name,
            priority=priority,
            reason=reason,
            metadata=metadata or {},
        )
        device_demands = self._demands.setdefault(device_id, {})
        device_demands[(feature_id, source_id)] = demand
        return await self.async_apply(device_id)

    async def async_clear_demand(
        self,
        device_id: str,
        *,
        feature_id: str,
        source_id: str | None = None,
    ) -> bool:
        """Clear one or more feature demands and apply the resolved command."""
        device_demands = self._demands.get(device_id, {})
        if source_id is None:
            keys_to_remove = [key for key in device_demands if key[0] == feature_id]
            for key in keys_to_remove:
                device_demands.pop(key, None)
        else:
            device_demands.pop((feature_id, source_id), None)

        if not device_demands:
            self._demands.pop(device_id, None)

        return await self.async_apply(device_id)

    def get_active_demands(self, device_id: str) -> list[FanSpeedDemand]:
        """Return active demands for a device."""
        return list(self._demands.get(device_id, {}).values())

    def get_all_devices_with_demands(self) -> list[str]:
        """Return list of all device IDs that have active demands."""
        return list(self._demands.keys())

    def resolve(self, device_id: str) -> ResolvedFanSpeed:
        """Resolve the current fan command for a device."""
        active_demands = self.get_active_demands(device_id)
        if not active_demands:
            return ResolvedFanSpeed(
                device_id=device_id,
                command_name="fan_auto",
                winning_demand=None,
                active_demands=[],
            )

        winning_demand = max(
            active_demands,
            key=lambda demand: (
                self.speed_rank(demand.requested_speed),
                demand.priority,
                demand.updated_at,
            ),
        )
        return ResolvedFanSpeed(
            device_id=device_id,
            command_name=winning_demand.requested_speed,
            winning_demand=winning_demand,
            active_demands=active_demands,
        )

    async def async_apply(self, device_id: str) -> bool:
        """Apply the resolved command for a device."""
        # Filter out HGI gateway devices - they're not controllable
        normalized_device_id = device_id.replace("_", ":")
        if normalized_device_id.startswith("18:"):
            _LOGGER.debug(
                "Skipping fan command for %s - HGI gateway is not controllable",
                device_id,
            )
            return False

        resolved = self.resolve(device_id)
        command_name = resolved.command_name

        _LOGGER.debug(
            "Arbiter applying command for %s: %s (priority=%s, source=%s)",
            device_id,
            command_name,
            resolved.winning_demand.priority if resolved.winning_demand else "none",
            resolved.winning_demand.source_id if resolved.winning_demand else "none",
        )

        # Check transport state before sending command
        from .transport_monitor import get_transport_monitor

        transport_monitor = get_transport_monitor()
        is_monitoring = transport_monitor.is_monitoring
        is_available = transport_monitor.is_device_available(device_id)

        if is_monitoring and not is_available:
            _LOGGER.debug(
                "Skipping fan command %s for %s - transport unavailable",
                command_name,
                device_id,
            )
            return False

        result = await self.ramses_commands.send_command(device_id, command_name)
        if not result.success:
            _LOGGER.warning(
                "Failed to apply resolved fan command %s for %s",
                command_name,
                device_id,
            )
            return False

        return True

    @staticmethod
    def normalize_speed(requested_speed: str | int) -> str:
        """Normalize an input speed or level to a command name."""
        normalized = _SPEED_NORMALIZATION.get(requested_speed)
        if normalized is not None:
            return normalized

        if isinstance(requested_speed, str):
            normalized = _SPEED_NORMALIZATION.get(requested_speed.strip().lower())
            if normalized is not None:
                return normalized

        raise ValueError(f"Unsupported fan speed: {requested_speed}")

    @staticmethod
    def speed_rank(command_name: str) -> int:
        """Return rank for a normalized command name."""
        return _SPEED_ORDER.get(command_name, -1)

    def get_debug_state(self) -> dict[str, Any]:
        """Return current arbiter state for diagnostics."""
        return {
            "devices": {
                device_id: {
                    "active_demands": [
                        {
                            "feature_id": demand.feature_id,
                            "source_id": demand.source_id,
                            "requested_speed": demand.requested_speed,
                            "priority": demand.priority,
                            "reason": demand.reason,
                            "metadata": demand.metadata,
                        }
                        for demand in demands.values()
                    ],
                }
                for device_id, demands in self._demands.items()
            }
        }

    def get_device_debug_state(self, device_id: str) -> dict[str, Any]:
        """Return current arbiter state for a single device."""
        resolved = self.resolve(device_id)
        return {
            "resolved_command": resolved.command_name,
            "winning_demand": (
                {
                    "feature_id": resolved.winning_demand.feature_id,
                    "source_id": resolved.winning_demand.source_id,
                    "requested_speed": resolved.winning_demand.requested_speed,
                    "priority": resolved.winning_demand.priority,
                    "reason": resolved.winning_demand.reason,
                    "metadata": resolved.winning_demand.metadata,
                }
                if resolved.winning_demand is not None
                else None
            ),
            "active_demands": [
                {
                    "feature_id": demand.feature_id,
                    "source_id": demand.source_id,
                    "requested_speed": demand.requested_speed,
                    "priority": demand.priority,
                    "reason": demand.reason,
                    "metadata": demand.metadata,
                }
                for demand in resolved.active_demands
            ],
        }


def get_fan_speed_arbiter(hass: Any) -> FanSpeedArbiter:
    """Return the shared fan speed arbiter singleton."""
    hass_data = getattr(hass, "data", None)
    if isinstance(hass_data, dict):
        domain_data = hass_data.setdefault(DOMAIN, {})
        if isinstance(domain_data, dict):
            arbiter = domain_data.get("fan_speed_arbiter")
            if isinstance(arbiter, FanSpeedArbiter):
                return arbiter

            arbiter = FanSpeedArbiter(hass)
            domain_data["fan_speed_arbiter"] = arbiter
            return arbiter

    fallback_attr = "_ramses_extras_fan_speed_arbiter"
    arbiter = getattr(hass, fallback_attr, None)
    if isinstance(arbiter, FanSpeedArbiter):
        return arbiter

    arbiter = FanSpeedArbiter(hass)
    setattr(hass, fallback_attr, arbiter)
    return arbiter
