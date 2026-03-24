"""Shared fan speed arbitration helper for cross-feature control."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from custom_components.ramses_extras.const import DOMAIN

from .ramses_commands import RamsesCommands

_LOGGER = logging.getLogger(__name__)

_MANUAL_OVERRIDE_FEATURE_ID = "manual_override"
_MANUAL_OVERRIDE_PRIORITY = 1000

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
        self._extras_control_enabled: dict[str, bool] = {}
        self._callbacks: dict[str, tuple[str, Any]] = {}

    @staticmethod
    def _normalize_device_id(device_id: str) -> str:
        """Normalize device IDs to colon format for internal storage."""
        return str(device_id).replace("_", ":")

    def register_callback(self, name: str, callback: Any, device_id: str) -> None:
        """Register a callback for control-mode changes on a device."""
        normalized_device_id = self._normalize_device_id(device_id)
        self._callbacks[name] = (normalized_device_id, callback)

    def unregister_callback(self, name: str) -> None:
        """Unregister a control-mode callback."""
        self._callbacks.pop(name, None)

    def _notify_control_mode_changed(self, device_id: str) -> None:
        """Notify device-scoped callbacks that control mode may have changed."""
        control_mode = self.get_control_mode(device_id)
        for callback_device_id, callback in self._callbacks.values():
            if callback_device_id != device_id:
                continue
            try:
                callback(control_mode)
            except Exception as err:
                _LOGGER.error(
                    "Error in fan control callback for %s: %s",
                    device_id,
                    err,
                )

    def get_control_mode(self, device_id: str) -> str:
        """Return the current coarse control mode for a device."""
        normalized_device_id = self._normalize_device_id(device_id)
        if self.is_manual_override_active(normalized_device_id):
            return "manual_override"
        if not self.is_extras_control_enabled(normalized_device_id):
            return "auto_by_fan"
        if self.get_active_demands(normalized_device_id):
            return "auto_by_extras"
        return "auto_by_fan"

    def is_extras_control_enabled(self, device_id: str) -> bool:
        """Return whether extras automation is currently allowed to control a device."""
        normalized_device_id = self._normalize_device_id(device_id)
        return self._extras_control_enabled.get(normalized_device_id, True)

    def set_extras_control_enabled(self, device_id: str, enabled: bool) -> None:
        """Update whether extras automation may control a device."""
        normalized_device_id = self._normalize_device_id(device_id)
        self._extras_control_enabled[normalized_device_id] = enabled

    def set_manual_override_state(
        self,
        device_id: str,
        *,
        source_id: str,
        requested_speed: str | int,
        reason: str = "manual_override",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Update manual override demand state without applying commands."""
        override_metadata = dict(metadata or {})
        override_metadata.setdefault("manual", True)
        self._set_demand_state(
            device_id,
            feature_id=_MANUAL_OVERRIDE_FEATURE_ID,
            source_id=source_id,
            requested_speed=requested_speed,
            priority=_MANUAL_OVERRIDE_PRIORITY,
            reason=reason,
            metadata=override_metadata,
        )

    def clear_manual_override_state(self, device_id: str) -> None:
        """Clear manual override state without applying commands."""
        self._clear_demand_state(
            device_id,
            feature_id=_MANUAL_OVERRIDE_FEATURE_ID,
        )

    def clear_demand_state(
        self,
        device_id: str,
        *,
        feature_id: str,
        source_id: str | None = None,
    ) -> None:
        """Clear demand state without applying commands."""
        self._clear_demand_state(device_id, feature_id=feature_id, source_id=source_id)

    async def async_commit_state(self, device_id: str, *, apply: bool = True) -> bool:
        """Apply and publish pending state changes for a device."""
        normalized_device_id = self._normalize_device_id(device_id)
        result = True
        if apply:
            result = await self.async_apply(normalized_device_id)
        self._notify_control_mode_changed(normalized_device_id)
        return result

    def _set_demand_state(
        self,
        device_id: str,
        *,
        feature_id: str,
        source_id: str,
        requested_speed: str | int,
        priority: int = 0,
        reason: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        normalized_device_id = self._normalize_device_id(device_id)
        command_name = self.normalize_speed(requested_speed)
        demand = FanSpeedDemand(
            feature_id=feature_id,
            source_id=source_id,
            requested_speed=command_name,
            priority=priority,
            reason=reason,
            metadata=metadata or {},
        )
        device_demands = self._demands.setdefault(normalized_device_id, {})
        device_demands[(feature_id, source_id)] = demand

    def _clear_demand_state(
        self,
        device_id: str,
        *,
        feature_id: str,
        source_id: str | None = None,
    ) -> None:
        normalized_device_id = self._normalize_device_id(device_id)
        device_demands = self._demands.get(normalized_device_id, {})
        if source_id is None:
            keys_to_remove = [key for key in device_demands if key[0] == feature_id]
            for key in keys_to_remove:
                device_demands.pop(key, None)
        else:
            device_demands.pop((feature_id, source_id), None)

        if not device_demands:
            self._demands.pop(normalized_device_id, None)

    async def async_set_manual_override(
        self,
        device_id: str,
        *,
        source_id: str,
        requested_speed: str | int,
        reason: str = "manual_override",
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        """Create or update a manual override demand and apply it immediately."""
        override_metadata = dict(metadata or {})
        override_metadata.setdefault("manual", True)
        return await self.async_set_demand(
            device_id,
            feature_id=_MANUAL_OVERRIDE_FEATURE_ID,
            source_id=source_id,
            requested_speed=requested_speed,
            priority=_MANUAL_OVERRIDE_PRIORITY,
            reason=reason,
            metadata=override_metadata,
        )

    async def async_clear_manual_override(self, device_id: str) -> bool:
        """Clear any manual override demands for a device."""
        return await self.async_clear_demand(
            device_id,
            feature_id=_MANUAL_OVERRIDE_FEATURE_ID,
        )

    def is_manual_override_active(self, device_id: str) -> bool:
        """Return whether a device currently has a manual override demand."""
        return any(
            demand.feature_id == _MANUAL_OVERRIDE_FEATURE_ID
            for demand in self.get_active_demands(device_id)
        )

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
        self._set_demand_state(
            device_id,
            feature_id=feature_id,
            source_id=source_id,
            requested_speed=requested_speed,
            priority=priority,
            reason=reason,
            metadata=metadata,
        )
        return await self.async_commit_state(device_id)

    async def async_clear_demand(
        self,
        device_id: str,
        *,
        feature_id: str,
        source_id: str | None = None,
    ) -> bool:
        """Clear one or more feature demands and apply the resolved command."""
        self._clear_demand_state(device_id, feature_id=feature_id, source_id=source_id)
        return await self.async_commit_state(device_id)

    def get_active_demands(self, device_id: str) -> list[FanSpeedDemand]:
        """Return active demands for a device."""
        normalized_device_id = self._normalize_device_id(device_id)
        return list(self._demands.get(normalized_device_id, {}).values())

    def get_all_devices_with_demands(self) -> list[str]:
        """Return list of all device IDs that have active demands."""
        return list(self._demands.keys())

    def resolve(self, device_id: str) -> ResolvedFanSpeed:
        """Resolve the current fan command for a device."""
        normalized_device_id = self._normalize_device_id(device_id)
        active_demands = self.get_active_demands(normalized_device_id)
        if not active_demands:
            return ResolvedFanSpeed(
                device_id=normalized_device_id,
                command_name="fan_auto",
                winning_demand=None,
                active_demands=[],
            )

        manual_demands = [
            demand
            for demand in active_demands
            if demand.feature_id == _MANUAL_OVERRIDE_FEATURE_ID
        ]
        if manual_demands:
            winning_demand = max(
                manual_demands,
                key=lambda demand: (
                    demand.priority,
                    demand.updated_at,
                    self.speed_rank(demand.requested_speed),
                ),
            )
            return ResolvedFanSpeed(
                device_id=normalized_device_id,
                command_name=winning_demand.requested_speed,
                winning_demand=winning_demand,
                active_demands=active_demands,
            )

        if not self.is_extras_control_enabled(normalized_device_id):
            return ResolvedFanSpeed(
                device_id=normalized_device_id,
                command_name="fan_auto",
                winning_demand=None,
                active_demands=active_demands,
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
            device_id=normalized_device_id,
            command_name=winning_demand.requested_speed,
            winning_demand=winning_demand,
            active_demands=active_demands,
        )

    async def async_apply(self, device_id: str) -> bool:
        """Apply the resolved command for a device."""
        # Filter out HGI gateway devices - they're not controllable
        normalized_device_id = self._normalize_device_id(device_id)
        if normalized_device_id.startswith("18:"):
            _LOGGER.debug(
                "Skipping fan command for %s - HGI gateway is not controllable",
                normalized_device_id,
            )
            return False

        resolved = self.resolve(normalized_device_id)
        command_name = resolved.command_name

        _LOGGER.debug(
            "Arbiter applying command for %s: %s (priority=%s, source=%s)",
            normalized_device_id,
            command_name,
            resolved.winning_demand.priority if resolved.winning_demand else "none",
            resolved.winning_demand.source_id if resolved.winning_demand else "none",
        )

        # Check transport state before sending command
        from .transport_monitor import get_transport_monitor

        transport_monitor = get_transport_monitor()
        is_monitoring = transport_monitor.is_monitoring
        is_available = transport_monitor.is_device_available(normalized_device_id)

        if is_monitoring and not is_available:
            _LOGGER.debug(
                "Skipping fan command %s for %s - transport unavailable",
                command_name,
                normalized_device_id,
            )
            return False

        result = await self.ramses_commands.send_command(
            normalized_device_id,
            command_name,
        )
        if not result.success:
            _LOGGER.warning(
                "Failed to apply resolved fan command %s for %s",
                command_name,
                normalized_device_id,
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
                    "control_mode": self.get_control_mode(device_id),
                    "extras_control_enabled": self.is_extras_control_enabled(device_id),
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
        normalized_device_id = self._normalize_device_id(device_id)
        resolved = self.resolve(normalized_device_id)
        return {
            "control_mode": self.get_control_mode(normalized_device_id),
            "extras_control_enabled": self.is_extras_control_enabled(
                normalized_device_id
            ),
            "resolved_command": resolved.command_name,
            "manual_override_active": self.is_manual_override_active(
                normalized_device_id
            ),
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
