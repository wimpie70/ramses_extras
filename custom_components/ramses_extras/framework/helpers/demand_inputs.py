"""Demand inputs: switch/contact bindings as ventilation demand sources.

Issue 289: non-REM inputs — a toilet push switch, a window/door
contact, or another simple sender — create ventilation demand on top of
the zone/demand/arbiter machinery.

Two input sources share this module's apply logic:

- **HA entities** (binary_sensor/switch/input_boolean): state listeners
  attached by :func:`async_attach_demand_input_listeners`.
- **RAMSES senders**: observed packets in the default feature's remote
  listener; any packet from a bound switch/contact sender counts as an
  activation.

Two semantics per binding (``role`` field):

- ``switch`` (momentary): activation starts a timed demand; the release
  is governed by the binding's ``manual_timeout`` and ``revert_mode``,
  via :class:`OverrideReleaseManager` — the same machinery as REM
  overrides (issue 290).
- ``contact`` (latching): demand is held while the input is active and
  cleared on deactivate.  Over RAMSES a contact behaves like a switch:
  every packet re-arms the timed demand (positive latching over RF
  needs per-device packet semantics we don't have yet).

Demand target per binding (``demand_target``):

- ``fan``: a ``manual_override`` arbiter demand at ``demand_speed``.
- ``zone``: a zone demand on the binding's ``zone_id`` (valve
  actuation via the zone coordinator).
- ``both``: both of the above.

Note: this models *positive* demand only.  "Window open → close this
zone's valve / stop ventilating it" is an inhibit/veto primitive and is
deliberately out of scope here.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from .fan_speed_arbiter import get_fan_speed_arbiter
from .override_release import (
    REVERT_EXTRAS_AUTO,
    async_resume_feature_control,
    get_override_release_manager,
)
from .zone_coordinator import get_zone_coordinator
from .zone_demand import DemandSource, get_zone_demand_registry

_LOGGER = logging.getLogger(__name__)

ROLE_REMOTE = "remote"
ROLE_SWITCH = "switch"
ROLE_CONTACT = "contact"
DEMAND_INPUT_ROLES = {ROLE_SWITCH, ROLE_CONTACT}

TARGET_FAN = "fan"
TARGET_ZONE = "zone"
TARGET_BOTH = "both"
DEMAND_TARGETS = {TARGET_FAN, TARGET_ZONE, TARGET_BOTH}

# Entity states treated as "active".  Everything else — including
# "unavailable"/"unknown" — deactivates, so a dead sensor cannot leave
# a stale demand behind.
_ACTIVE_STATES = {"on", "open", "true", "1", "home", "occupied", "detected"}

_MANUAL_OVERRIDE_FEATURE_ID = "manual_override"
_REMOTE_BINDING_FEATURE = "remote_binding"


def role_of_binding(binding: dict[str, Any]) -> str:
    """Return the binding's role, defaulting to ``remote``."""
    return str(binding.get("role") or ROLE_REMOTE).strip().lower()


def is_demand_input_binding(binding: dict[str, Any]) -> bool:
    """Return True if the binding is a switch/contact demand input."""
    return role_of_binding(binding) in DEMAND_INPUT_ROLES


def demand_source_for_role(role: str) -> DemandSource:
    """Map a binding role to a zone DemandSource."""
    return DemandSource.CONTACT if role == ROLE_CONTACT else DemandSource.SWITCH


def input_id_for_binding(binding: dict[str, Any]) -> str:
    """Stable identifier for this input (entity_id or RF sender id)."""
    entity_id = str(binding.get("entity_id") or "").strip()
    if entity_id:
        return entity_id
    return str(binding.get("rem_id") or "").replace("_", ":").strip()


def _targets(binding: dict[str, Any]) -> set[str]:
    target = str(binding.get("demand_target") or TARGET_FAN).strip().lower()
    if target == TARGET_BOTH:
        return {TARGET_FAN, TARGET_ZONE}
    if target in DEMAND_TARGETS:
        return {target}
    return {TARGET_FAN}


async def async_apply_zone_demand(
    hass: Any,
    device_id: str,
    zone_id: str,
    source: DemandSource,
    source_id: str,
    command_label: str,
    *,
    demand_registry: Any | None = None,
    coordinator: Any | None = None,
) -> None:
    """Set a zone demand, (re)configure the zone and run actuation.

    Shared by the observed-REM path (DemandSource.REM) and demand
    inputs (DemandSource.SWITCH / CONTACT).  Callers may inject the
    registry/coordinator (tests patch them at the caller's module).
    """
    if demand_registry is None:
        demand_registry = get_zone_demand_registry(hass)
    _LOGGER.info(
        "Setting zone demand for %s: %s:%s = True",
        source_id,
        device_id,
        zone_id,
    )
    demand_registry.set_demand(
        device_id,
        zone_id,
        source,
        True,
        metadata={"input_id": source_id, "command": command_label},
    )
    if coordinator is None:
        coordinator = get_zone_coordinator(hass, device_id)
    from .zones import get_zone_registry

    zone_registry = get_zone_registry(hass)
    zone_cfg = zone_registry.get_zone(device_id, zone_id)
    _LOGGER.info(
        "Zone config lookup: %s:%s -> %s",
        device_id,
        zone_id,
        zone_cfg,
    )
    if isinstance(zone_cfg, dict):
        zone_type = str(
            zone_cfg.get("type") or zone_cfg.get("source_type") or ""
        ).strip()
        inlet_entity = zone_cfg.get("inlet_valve_entity")
        outlet_entity = zone_cfg.get("outlet_valve_entity")
        min_position = zone_cfg.get("min_position")
        max_position = zone_cfg.get("max_position")
        actuation_priority = zone_cfg.get("actuation_priority")

        _LOGGER.info(
            "Configuring zone %s: type=%s inlet=%s outlet=%s min=%s max=%s",
            zone_id,
            zone_type,
            inlet_entity,
            outlet_entity,
            min_position,
            max_position,
        )

        coordinator.configure_zone(
            zone_id=zone_id,
            zone_type=zone_type or None,
            inlet_valve_entity=str(inlet_entity).strip()
            if isinstance(inlet_entity, str) and inlet_entity.strip()
            else None,
            outlet_valve_entity=str(outlet_entity).strip()
            if isinstance(outlet_entity, str) and outlet_entity.strip()
            else None,
            min_position=int(min_position) if isinstance(min_position, int) else None,
            max_position=int(max_position) if isinstance(max_position, int) else None,
            is_controllable=True,
            actuation_priority=int(actuation_priority)
            if isinstance(actuation_priority, int)
            else None,
        )
    else:
        _LOGGER.warning(
            "Zone %s:%s not found in registry, using bare config",
            device_id,
            zone_id,
        )
        coordinator.configure_zone(zone_id)
    _LOGGER.debug("Running zone actuation cycle for %s", device_id)
    await coordinator.async_run_zone_actuation_cycle()


async def async_apply_demand_input(
    hass: Any,
    device_id: str,
    binding: dict[str, Any],
    *,
    active: bool = True,
    timed: bool | None = None,
) -> None:
    """Apply (or clear, for contacts) a demand input on a FAN.

    :param hass: Home Assistant instance
    :param device_id: FAN device id the input is bound to
    :param binding: the binding dict (role/entity_id/rem_id/zone_id/...)
    :param active: True on activation; False only for contact release
    :param timed: True forces momentary semantics (timed demand via
           ``manual_timeout``); False forces latching; None derives it
           from the role (switch = timed, contact = latching).  RAMSES
           senders are always treated as timed since an RF packet has no
           "released" edge.
    """
    role = role_of_binding(binding)
    if role not in DEMAND_INPUT_ROLES:
        return
    if timed is None:
        timed = role == ROLE_SWITCH

    source = demand_source_for_role(role)
    source_id = input_id_for_binding(binding) or "demand_input"
    targets = _targets(binding)
    zone_id = str(binding.get("zone_id") or "").strip()
    speed = str(binding.get("demand_speed") or "fan_high").strip()
    revert_mode = str(binding.get("revert_mode") or REVERT_EXTRAS_AUTO)
    arbiter = get_fan_speed_arbiter(hass)
    release_mgr = get_override_release_manager(hass)

    if timed and not active:
        return  # momentary inputs only act on activation

    _LOGGER.info(
        "Demand input %s: role=%s device=%s active=%s target=%s zone=%s",
        source_id,
        role,
        device_id,
        active,
        targets,
        zone_id or "-",
    )

    if not active:
        # Latching release: clear this input's own demands.  Scoped by
        # source_id so a REM override issued while the contact was
        # active is left alone.
        if TARGET_FAN in targets:
            arbiter.clear_demand_state(
                device_id,
                feature_id=_MANUAL_OVERRIDE_FEATURE_ID,
                source_id=source_id,
            )
            await arbiter.async_commit_state(device_id, apply=False)
        if TARGET_ZONE in targets and zone_id:
            demand_registry = get_zone_demand_registry(hass)
            demand_registry.clear_demand(device_id, zone_id, source)
            coordinator = get_zone_coordinator(hass, device_id)
            await coordinator.async_run_zone_actuation_cycle()
        await async_resume_feature_control(hass, device_id)
        return

    if TARGET_FAN in targets:
        arbiter.set_extras_control_enabled(device_id, True)
        arbiter.set_manual_override_state(
            device_id,
            source_id=source_id,
            requested_speed=speed,
            reason=f"demand_input_{role}",
            metadata={"origin": "demand_input", "input": source_id},
        )
        await arbiter.async_commit_state(device_id, apply=False)

    if TARGET_ZONE in targets:
        if zone_id:
            await async_apply_zone_demand(
                hass, device_id, zone_id, source, source_id, role
            )
        else:
            _LOGGER.warning(
                "Demand input %s on %s has no zone_id; zone target skipped",
                source_id,
                device_id,
            )

    if timed:
        timeout = binding.get("manual_timeout")
        if isinstance(timeout, int) and timeout > 0:
            release_mgr.schedule_release(
                device_id,
                timeout,
                revert_mode=revert_mode,
                clear_zone_source=source,
                override_source_id=source_id,
            )
        else:
            release_mgr.cancel_release(device_id)


def iter_demand_input_bindings(hass: Any) -> list[tuple[str, dict[str, Any]]]:
    """Return [(fan_id, binding)] for enabled switch/contact bindings."""
    from .config.model import get_fan_ids
    from .remote_binding import get_remote_binding_registry

    registry = get_remote_binding_registry(hass)
    manager = registry._get_config_manager()
    if manager is None:
        return []

    section = manager.get_feature_section(_REMOTE_BINDING_FEATURE, canonical=True)
    results: list[tuple[str, dict[str, Any]]] = []
    for fan_id in get_fan_ids(section):
        for binding in registry.get_bindings_for_fan(fan_id):
            if is_demand_input_binding(binding):
                results.append((fan_id, binding))
    return results


def async_attach_demand_input_listeners(
    hass: Any, domain_data: dict[str, Any]
) -> list[Callable[[], None]]:
    """Attach HA-entity state listeners for switch/contact bindings.

    Returns the unsubscribe callbacks (empty when no entity-based
    inputs are configured).  The caller stores them on domain_data so
    re-registration replaces the old listeners.
    """
    from homeassistant.helpers.event import async_track_state_change_event

    entity_bindings: dict[str, list[tuple[str, dict[str, Any]]]] = {}
    for fan_id, binding in iter_demand_input_bindings(hass):
        entity_id = str(binding.get("entity_id") or "").strip()
        if entity_id:
            entity_bindings.setdefault(entity_id, []).append((fan_id, binding))

    if not entity_bindings:
        return []

    def _make_handler(entity_id: str) -> Callable[[Any], None]:
        def _on_change(event: Any) -> None:
            new_state = event.data.get("new_state")
            state_str = str(getattr(new_state, "state", "") or "").lower()
            active = state_str in _ACTIVE_STATES
            for fan_id, binding in entity_bindings.get(entity_id, []):
                if role_of_binding(binding) == ROLE_SWITCH and not active:
                    continue  # momentary: only the active edge matters
                hass.async_create_task(
                    async_apply_demand_input(hass, fan_id, binding, active=active)
                )

        return _on_change

    unsubs = [
        async_track_state_change_event(hass, [entity_id], _make_handler(entity_id))
        for entity_id in entity_bindings
    ]

    _LOGGER.info(
        "Demand input listeners attached for %d entit%s: %s",
        len(entity_bindings),
        "y" if len(entity_bindings) == 1 else "ies",
        ", ".join(sorted(entity_bindings)),
    )
    return unsubs
