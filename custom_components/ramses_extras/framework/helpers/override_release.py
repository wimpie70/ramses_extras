"""Timed release of temporary manual fan overrides.

Shared machinery for "temporary manual control" sources: observed REM/DIS
button presses, card ``send_fan_command`` service calls, and (planned)
switch/contact demand inputs (issue 289).

A release clears the ``manual_override`` arbiter demand, clears the
originating source's zone demands, re-runs zone actuation, and applies
the requested revert mode:

- ``extras_auto``: re-enable extras automation and resume feature control.
- ``fan_auto``:    leave extras automation disabled (unit's own auto).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from ...const import DOMAIN
from .fan_speed_arbiter import get_fan_speed_arbiter
from .zone_demand import DemandSource, get_zone_demand_registry

_LOGGER = logging.getLogger(__name__)

REVERT_EXTRAS_AUTO = "extras_auto"
REVERT_FAN_AUTO = "fan_auto"
REVERT_MODES = {REVERT_EXTRAS_AUTO, REVERT_FAN_AUTO}

# Duration encoded in each fan_timer_* command (seconds).  The boost
# itself runs on the unit's own 22F3 timer; the release only governs
# when the recorded override state is reverted.
_BOOST_DURATION_S = {
    "fan_timer_15min": 15 * 60,
    "fan_timer_30min": 30 * 60,
    "fan_timer_60min": 60 * 60,
}

# Extra delay so the unit's own timer finishes before extras automation
# resumes and can steer the fan again.
_BOOST_RELEASE_MARGIN_S = 30.0


def boost_release_delay(command: str) -> float | None:
    """Return the release delay for a fan_timer_* command, or None."""
    duration = _BOOST_DURATION_S.get(command)
    if duration is None:
        return None
    return duration + _BOOST_RELEASE_MARGIN_S


def clear_source_zone_demands(hass: Any, device_id: str, source: DemandSource) -> None:
    """Clear all zone demands held by ``source`` for ``device_id``."""
    normalized = str(device_id).replace("_", ":").strip()
    demand_registry = get_zone_demand_registry(hass)
    for zone_id, sources in demand_registry.get_all_demands_for_fan(normalized).items():
        if source in sources:
            demand_registry.clear_demand(normalized, zone_id, source)


async def async_resume_feature_control(hass: Any, device_id: str) -> None:
    """Re-run feature evaluations after a manual override is released."""
    domain_data = hass.data.get(DOMAIN, {})
    features = domain_data.get("features", {})
    if not isinstance(features, dict):
        return

    humidity_feature = features.get("humidity_control")
    if isinstance(humidity_feature, dict):
        automation = humidity_feature.get("automation")
        if automation is not None and hasattr(automation, "_reconcile_startup_states"):
            await automation._reconcile_startup_states()

    co2_feature = features.get("co2_control")
    if isinstance(co2_feature, dict):
        automation = co2_feature.get("automation")
        if automation is not None and hasattr(automation, "_evaluate_co2_control"):
            await automation._evaluate_co2_control(device_id)

    temp_feature = features.get("temp_control")
    if isinstance(temp_feature, dict):
        automation = temp_feature.get("automation")
        if automation is not None and hasattr(automation, "_reconcile_startup_states"):
            await automation._reconcile_startup_states(device_id)


class OverrideReleaseManager:
    """Schedule and execute timed releases of manual overrides."""

    def __init__(self, hass: Any) -> None:
        """Initialize the release manager.

        :param hass: Home Assistant instance
        """
        self._hass = hass
        self._handles: dict[str, asyncio.Handle] = {}

    @staticmethod
    def _normalize(device_id: str) -> str:
        return str(device_id).replace("_", ":").strip()

    def cancel_release(self, device_id: str) -> None:
        """Cancel any pending release for a device."""
        handle = self._handles.pop(self._normalize(device_id), None)
        if handle is not None and not handle.cancelled():
            handle.cancel()

    def schedule_release(
        self,
        device_id: str,
        delay_s: float,
        *,
        revert_mode: str = REVERT_EXTRAS_AUTO,
        clear_zone_source: DemandSource | None = DemandSource.REM,
    ) -> None:
        """Schedule a timed release for a device.

        Replaces any pending release — a repeated boost or speed press
        restarts the timer, matching the unit's own behaviour.

        :param device_id: FAN device identifier
        :param delay_s: Seconds until the release fires
        :param revert_mode: ``extras_auto`` or ``fan_auto``
        :param clear_zone_source: Zone demand source to clear on release,
               or None to leave zone demands untouched
        """
        normalized = self._normalize(device_id)
        self.cancel_release(normalized)

        def _callback() -> None:
            self._handles.pop(normalized, None)
            self._hass.async_create_task(
                self.async_release(
                    normalized,
                    revert_mode=revert_mode,
                    clear_zone_source=clear_zone_source,
                )
            )

        self._handles[normalized] = self._hass.loop.call_later(delay_s, _callback)

    async def async_release(
        self,
        device_id: str,
        *,
        revert_mode: str = REVERT_EXTRAS_AUTO,
        clear_zone_source: DemandSource | None = DemandSource.REM,
    ) -> None:
        """Release a manual override and apply the revert mode."""
        normalized = self._normalize(device_id)
        self.cancel_release(normalized)
        try:
            arbiter = get_fan_speed_arbiter(self._hass)
            arbiter.clear_manual_override_state(normalized)
            arbiter.set_extras_control_enabled(
                normalized, revert_mode != REVERT_FAN_AUTO
            )
            await arbiter.async_commit_state(normalized, apply=False)
            if clear_zone_source is not None:
                clear_source_zone_demands(self._hass, normalized, clear_zone_source)
            from .zone_coordinator import get_zone_coordinator

            coordinator = get_zone_coordinator(self._hass, normalized)
            await coordinator.async_run_zone_actuation_cycle()
            if revert_mode != REVERT_FAN_AUTO:
                await async_resume_feature_control(self._hass, normalized)
        except Exception as err:
            _LOGGER.exception(
                "Error releasing manual override for %s: %s",
                normalized,
                err,
            )


def get_override_release_manager(hass: Any) -> OverrideReleaseManager:
    """Get or create the override release manager."""
    domain_data = hass.data.setdefault(DOMAIN, {})
    if "override_release_manager" not in domain_data:
        domain_data["override_release_manager"] = OverrideReleaseManager(hass)
    return domain_data["override_release_manager"]  # type: ignore[no-any-return]


__all__ = [
    "REVERT_EXTRAS_AUTO",
    "REVERT_FAN_AUTO",
    "REVERT_MODES",
    "OverrideReleaseManager",
    "async_resume_feature_control",
    "boost_release_delay",
    "clear_source_zone_demands",
    "get_override_release_manager",
]
