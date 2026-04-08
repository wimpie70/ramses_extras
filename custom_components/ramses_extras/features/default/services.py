"""Home Assistant services exposed by the default feature.

The default feature is always enabled, and hosts common services used by cards
and other features (e.g. sending fan commands and managing 2411 parameters).
"""

from __future__ import annotations

import ast
import asyncio
import logging
import time

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv

from ...const import DOMAIN
from ...framework.helpers.fan_speed_arbiter import get_fan_speed_arbiter
from ...framework.helpers.ramses_commands import RamsesCommands
from ...framework.helpers.zone_coordinator import get_zone_coordinator
from ...framework.helpers.zone_demand import DemandSource, get_zone_demand_registry

_LOGGER = logging.getLogger(__name__)

SVC_SEND_FAN_COMMAND = "send_fan_command"
SVC_SET_FAN_PARAMETER = "set_fan_parameter"
SVC_UPDATE_FAN_PARAMS = "update_fan_params"
SVC_GET_QUEUE_STATISTICS = "get_queue_statistics"
SVC_SET_ZONE_DEMAND = "set_zone_demand"
SVC_CLEAR_ZONE_DEMAND = "clear_zone_demand"
SVC_RUN_ZONE_ACTUATION = "run_zone_actuation"
SVC_CALIBRATE_ALL_VALVES = "calibrate_all_valves"
SVC_FORCE_ZONE_VENTILATION = "force_zone_ventilation"


async def async_setup_services(hass: HomeAssistant) -> None:
    async def _async_clear_feature_fan_demands(device_id: str) -> None:
        arbiter = get_fan_speed_arbiter(hass)
        for feature_id in ("humidity_control", "co2_control"):
            arbiter.clear_demand_state(device_id, feature_id=feature_id)

    def _normalize_id(value: object) -> str | None:
        if not isinstance(value, str):
            return None
        normalized = value.replace("_", ":").strip()
        return normalized if normalized else None

    def _observed_command_from_packet(code: object, payload: object) -> str | None:
        """Extract fan command from RAMSES packet.

        Handles both raw hex payload strings and pre-parsed dict payloads.
        """
        _LOGGER.info(
            "Packet parser: code=%s (type=%s), payload=%s (type=%s)",
            code,
            type(code).__name__,
            payload,
            type(payload).__name__,
        )

        if not isinstance(code, str):
            _LOGGER.info("Parser rejected: code is not string")
            return None

        normalized_code = code.strip().upper()

        # Handle dict payloads (from ramses_cc parsed messages)
        if isinstance(payload, dict):
            _LOGGER.info("Parser handling dict payload: %s", payload)
            # For 22F1/22F3, look for fan_mode or similar keys
            if normalized_code == "22F1":
                fan_mode = (
                    payload.get("fan_mode")
                    or payload.get("FAN_MODE")
                    or payload.get("mode")
                    or payload.get("MODE")
                )
                mode_idx = payload.get("_mode_idx") or payload.get("_MODE_IDX")
                if fan_mode is not None:
                    fan_mode_s = str(fan_mode).strip().lower()
                    mode_by_name = {
                        "low": "fan_low",
                        "medium": "fan_medium",
                        "mid": "fan_medium",
                        "high": "fan_high",
                        "auto": "fan_auto",
                        "away": "fan_away",
                    }
                    result = mode_by_name.get(fan_mode_s)
                    if result:
                        _LOGGER.info("Parser found command from fan_mode: %s", result)
                        return result

                    mode_by_idx = {
                        "01": "fan_low",
                        "02": "fan_medium",
                        "03": "fan_high",
                        "04": "fan_auto",
                        "00": "fan_away",
                    }
                    result = mode_by_idx.get(str(fan_mode).strip())
                    if result:
                        _LOGGER.info("Parser found command from fan_mode: %s", result)
                        return result

                if mode_idx is not None:
                    mode_by_idx = {
                        "01": "fan_low",
                        "02": "fan_medium",
                        "03": "fan_high",
                        "04": "fan_auto",
                        "00": "fan_away",
                    }
                    result = mode_by_idx.get(str(mode_idx).strip())
                    if result:
                        _LOGGER.info("Parser found command from _mode_idx: %s", result)
                        return result
                # Also check for speed-related keys
                speed = (
                    payload.get("speed")
                    or payload.get("SPEED")
                    or payload.get("fan_speed")
                    or payload.get("FAN_SPEED")
                )
                if speed:
                    speed_map = {
                        "low": "fan_low",
                        "medium": "fan_medium",
                        "high": "fan_high",
                        "auto": "fan_auto",
                        "away": "fan_away",
                    }
                    result = speed_map.get(str(speed).lower())
                    if result:
                        _LOGGER.info("Parser found command from speed: %s", result)
                        return result
            _LOGGER.info("Parser: no command found in dict payload")
            return None

        # Handle string payloads (raw hex)
        if not isinstance(payload, str):
            _LOGGER.info("Parser rejected: payload is not string or dict")
            return None

        normalized_payload = payload.strip().upper()
        _LOGGER.info("Parser string payload: '%s'", normalized_payload)

        if normalized_payload.startswith("{") and normalized_payload.endswith("}"):
            try:
                parsed = ast.literal_eval(payload)
            except Exception:
                parsed = None
            if isinstance(parsed, dict):
                return _observed_command_from_packet(code, parsed)

        if normalized_code == "22F1":
            # Payload format: 00 0X YY where X=speed (1-4), YY varies (04 or 07 seen)
            if len(normalized_payload) >= 6:
                speed_byte = normalized_payload[3:5]
                _LOGGER.info("Parser extracted speed_byte: '%s'", speed_byte)
                result = {
                    "01": "fan_low",
                    "02": "fan_medium",
                    "03": "fan_high",
                    "04": "fan_auto",
                    "00": "fan_away",
                }.get(speed_byte)
                if result:
                    _LOGGER.info("Parser found command from speed_byte: %s", result)
                    return result
                _LOGGER.info("Parser: speed_byte '%s' not in map", speed_byte)
            else:
                _LOGGER.info(
                    "Parser: payload too short (%s < 6)", len(normalized_payload)
                )
            # Fallback to full payload match for backward compatibility
            result = {
                "000107": "fan_low",
                "000207": "fan_medium",
                "000307": "fan_high",
                "000407": "fan_auto",
                "000007": "fan_away",
                "000104": "fan_low",
                "000204": "fan_medium",
                "000304": "fan_high",
                "000404": "fan_auto",
                "000004": "fan_away",
            }.get(normalized_payload)
            if result:
                _LOGGER.info("Parser found command from full match: %s", result)
                return result
            _LOGGER.info("Parser: no full payload match for '%s'", normalized_payload)
            return None

        if normalized_code == "22F3":
            result = {
                "00120F03040404": "fan_timer_15min",
                "00121E03040404": "fan_timer_30min",
                "00123C03040404": "fan_timer_60min",
            }.get(normalized_payload)
            if result:
                return result

        _LOGGER.info("Parser: unhandled code %s", normalized_code)
        return None

    async def _async_apply_observed_remote_command(
        device_id: str,
        command: str,
        source_id: str,
        zone_id: str | None,
    ) -> None:
        _LOGGER.info(
            "REM command processing: device=%s command=%s rem=%s zone=%s",
            device_id,
            command,
            source_id,
            zone_id,
        )
        arbiter = get_fan_speed_arbiter(hass)
        demand_registry = get_zone_demand_registry(hass)

        domain_data = hass.data.setdefault(DOMAIN, {})
        release_handles: dict[str, asyncio.Handle] = domain_data.setdefault(
            "_remote_override_release_handles", {}
        )

        def _get_rem_timeout_seconds() -> int:
            """Get timeout for REM binding (0=no timeout, default=60s)."""
            from ...framework.helpers.config.core import ExtrasConfigManager
            from ...framework.helpers.remote_binding import get_remote_binding_registry

            registry = get_remote_binding_registry(hass)
            config_manager = registry._get_config_manager()
            if config_manager is None:
                return 60

            bindings = config_manager.get_fan_remote_bindings(device_id)
            normalized_source = source_id.replace("_", ":").strip()
            for binding in bindings:
                binding_rem_id = (
                    str(binding.get("rem_id") or "").replace("_", ":").strip()
                )
                if binding_rem_id == normalized_source:
                    timeout = binding.get("manual_timeout")
                    # 0 = no timeout (persist until other demand)
                    if isinstance(timeout, int) and timeout >= 0:
                        return timeout
                    # Legacy: check for override_timeout
                    legacy_timeout = binding.get("override_timeout")
                    if isinstance(legacy_timeout, int) and legacy_timeout > 0:
                        return legacy_timeout
            return 60

        def _cancel_remote_override_release() -> None:
            handle = release_handles.pop(device_id, None)
            if handle is not None and not handle.cancelled():
                handle.cancel()

        async def _async_release_remote_override() -> None:
            _cancel_remote_override_release()
            arbiter.clear_manual_override_state(device_id)
            await arbiter.async_commit_state(device_id, apply=False)
            _clear_rem_zone_demands()
            coordinator = get_zone_coordinator(hass, device_id)
            await coordinator.async_run_zone_actuation_cycle()
            await _async_resume_feature_control(device_id)

        def _schedule_remote_override_release(
            timeout_seconds: int | None = None,
        ) -> None:
            if timeout_seconds is not None:
                effective_timeout = timeout_seconds
            else:
                effective_timeout = _get_rem_timeout_seconds()
            _cancel_remote_override_release()

            # 0 = no timeout (persist until other demand takes over)
            if effective_timeout == 0:
                return

            def _callback() -> None:
                hass.async_create_task(_async_release_remote_override())

            release_handles[device_id] = hass.loop.call_later(
                effective_timeout,
                _callback,
            )

        def _clear_rem_zone_demands() -> None:
            for zid, sources in demand_registry.get_all_demands_for_fan(
                device_id
            ).items():
                if DemandSource.REM in sources:
                    demand_registry.clear_demand(device_id, zid, DemandSource.REM)

        if command == "fan_auto":
            _cancel_remote_override_release()
            arbiter.set_extras_control_enabled(device_id, True)
            arbiter.clear_manual_override_state(device_id)
            await arbiter.async_commit_state(device_id, apply=False)
            _clear_rem_zone_demands()
            coordinator = get_zone_coordinator(hass, device_id)
            await coordinator.async_run_zone_actuation_cycle()
            await _async_resume_feature_control(device_id)
            return

        if command in {"fan_low", "fan_medium", "fan_high"}:
            timeout = _get_rem_timeout_seconds()
            _LOGGER.info(
                "Applying REM speed command: %s for %s (zone=%s, timeout=%ss)",
                command,
                device_id,
                zone_id,
                timeout,
            )
            _schedule_remote_override_release()
            arbiter.set_extras_control_enabled(device_id, True)
            arbiter.set_manual_override_state(
                device_id,
                source_id=source_id,
                requested_speed=command,
                reason="manual_remote_command",
                metadata={"origin": "remote"},
            )
            await arbiter.async_commit_state(device_id, apply=False)

            _clear_rem_zone_demands()
            if zone_id:
                _LOGGER.info(
                    "Setting zone demand for REM: %s:%s = True", device_id, zone_id
                )
                demand_registry.set_demand(
                    device_id,
                    zone_id,
                    DemandSource.REM,
                    True,
                    metadata={"rem_id": source_id, "command": command},
                )
                coordinator = get_zone_coordinator(hass, device_id)
                from ...framework.helpers.zones import get_zone_registry

                zone_registry = get_zone_registry(hass)
                zone_cfg = zone_registry.get_zone(device_id, zone_id)
                _LOGGER.info(
                    "Zone config lookup: %s:%s -> %s", device_id, zone_id, zone_cfg
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
                        min_position=int(min_position)
                        if isinstance(min_position, int)
                        else None,
                        max_position=int(max_position)
                        if isinstance(max_position, int)
                        else None,
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
                _LOGGER.info("Running zone actuation cycle for %s", device_id)
                await coordinator.async_run_zone_actuation_cycle()
            else:
                _LOGGER.warning("No zone_id bound for REM command on %s", device_id)
            return

        if command == "fan_away" or command.startswith("fan_timer_"):
            _cancel_remote_override_release()
            arbiter.set_extras_control_enabled(device_id, False)
            arbiter.clear_manual_override_state(device_id)
            await arbiter.async_commit_state(device_id, apply=False)
            _clear_rem_zone_demands()

    async def _async_handle_observed_remote_packet(
        src: object,
        dst: object,
        code: object,
        payload: object,
        verb: object = None,
    ) -> None:
        _LOGGER.info(
            "REM packet received: src=%s dst=%s code=%s payload=%s verb=%s",
            src,
            dst,
            code,
            payload,
            verb,
        )
        if isinstance(verb, str) and verb.strip().upper() == "RQ":
            _LOGGER.debug("Ignoring RQ (request) packet")
            return

        normalized_src = _normalize_id(src)
        normalized_dst = _normalize_id(dst)
        command = _observed_command_from_packet(code, payload)
        _LOGGER.info(
            "REM packet parsed: src=%s dst=%s command=%s",
            normalized_src,
            normalized_dst,
            command,
        )
        if not normalized_src or not normalized_dst or not command:
            return

        from ...framework.helpers.remote_binding import get_remote_binding_registry

        registry = get_remote_binding_registry(hass)

        # Get all REMs bound to this FAN for multi-remote support
        all_bound_rems = registry.get_all_rem_ids_for_fan(normalized_dst)

        # Record activity for diagnostics
        is_matched = normalized_src in all_bound_rems if all_bound_rems else False
        registry.record_remote_activity(
            rem_id=normalized_src,
            fan_id=normalized_dst,
            command=command,
            matched=is_matched,
        )

        if not is_matched:
            return

        bound_zone_id: str | None = None
        for binding in registry.get_bindings_for_fan(normalized_dst):
            if (
                str(binding.get("rem_id") or "").replace("_", ":").strip()
                != normalized_src
            ):
                continue
            zone_candidate = str(binding.get("zone_id") or "").strip()
            if zone_candidate:
                bound_zone_id = zone_candidate
            break

        domain_data = hass.data.setdefault(DOMAIN, {})
        recent = domain_data.setdefault("_fan_remote_last_seen", {})
        key = (normalized_dst, command)
        now = time.monotonic()
        last_seen = recent.get(key, 0.0)
        if now - last_seen < 1.5:
            return
        recent[key] = now

        await _async_apply_observed_remote_command(
            normalized_dst,
            command,
            normalized_src,
            bound_zone_id,
        )

    def _handle_remote_event(event: object) -> None:
        data = getattr(event, "data", None)
        if not isinstance(data, dict):
            return

        hass.async_create_task(
            _async_handle_observed_remote_packet(
                data.get("src"),
                data.get("dst"),
                data.get("code"),
                data.get("payload"),
                data.get("verb"),
            )
        )

    def _handle_remote_msg(msg: object, *args: object, **kwargs: object) -> None:
        src = getattr(getattr(msg, "src", None), "id", None)
        dst = getattr(getattr(msg, "dst", None), "id", None)
        code = getattr(msg, "code", None)
        payload = getattr(msg, "payload", None)
        verb = getattr(msg, "verb", None)
        hass.async_create_task(
            _async_handle_observed_remote_packet(
                src,
                dst,
                str(code) if code is not None else None,
                payload,
                str(verb) if verb is not None else None,
            )
        )

    async def _async_resume_feature_control(device_id: str) -> None:
        domain_data = hass.data.get(DOMAIN, {})
        features = domain_data.get("features", {})
        if not isinstance(features, dict):
            return

        humidity_feature = features.get("humidity_control")
        if isinstance(humidity_feature, dict):
            automation = humidity_feature.get("automation")
            if automation is not None and hasattr(
                automation, "_reconcile_startup_states"
            ):
                await automation._reconcile_startup_states()

        co2_feature = features.get("co2_control")
        if isinstance(co2_feature, dict):
            automation = co2_feature.get("automation")
            if automation is not None and hasattr(automation, "_evaluate_co2_control"):
                await automation._evaluate_co2_control(device_id)

    async def _async_send_fan_command(call: ServiceCall) -> None:
        data = dict(call.data)
        device_id = data["device_id"]
        command = data["command"]
        arbiter = get_fan_speed_arbiter(hass)

        if command == "fan_auto":
            if arbiter.is_manual_override_active(device_id):
                arbiter.set_extras_control_enabled(device_id, True)
                arbiter.clear_manual_override_state(device_id)
                await arbiter.async_commit_state(device_id)
                await _async_resume_feature_control(device_id)
                return

            if arbiter.is_extras_control_enabled(device_id):
                arbiter.set_extras_control_enabled(device_id, False)
                arbiter.clear_manual_override_state(device_id)
                await arbiter.async_commit_state(device_id)
                return

            arbiter.set_extras_control_enabled(device_id, True)
            arbiter.clear_manual_override_state(device_id)
            await arbiter.async_commit_state(device_id)
            await _async_resume_feature_control(device_id)
            return

        if command in {"fan_low", "fan_medium", "fan_high"}:
            arbiter.set_extras_control_enabled(device_id, True)
            arbiter.set_manual_override_state(
                device_id,
                source_id="default_service",
                requested_speed=command,
                reason="manual_card_command",
                metadata={"origin": "service"},
            )
            await _async_clear_feature_fan_demands(device_id)
            await arbiter.async_commit_state(device_id)
            return

        if command == "fan_away" or command.startswith("fan_timer_"):
            arbiter.set_extras_control_enabled(device_id, False)
            arbiter.clear_manual_override_state(device_id)
            await arbiter.async_commit_state(device_id, apply=False)
            commands = RamsesCommands(hass)
            await commands.send_command(device_id, command)
            return

        commands = RamsesCommands(hass)
        await commands.send_command(device_id, command)

    async def _async_set_fan_parameter(call: ServiceCall) -> None:
        data = dict(call.data)
        device_id = data["device_id"]
        param_id = str(data["param_id"]).upper()
        value = data["value"]
        from_id = data.get("from_id")

        commands = RamsesCommands(hass)
        await commands.set_fan_param(device_id, param_id, value, from_id)

    async def _async_update_fan_params(call: ServiceCall) -> None:
        data = dict(call.data)
        device_id = data["device_id"]
        from_id = data.get("from_id")

        commands = RamsesCommands(hass)
        await commands.update_fan_params(device_id, from_id)

    async def _async_get_queue_statistics(call: ServiceCall) -> None:
        commands = RamsesCommands(hass)
        stats = commands.get_queue_statistics()
        hass.data.setdefault(DOMAIN, {})["queue_statistics"] = stats
        _LOGGER.info("Queue statistics updated: %s", stats)

    domain_data = hass.data.setdefault(DOMAIN, {})
    if not domain_data.get("_fan_remote_listener_started"):
        event_unsub = hass.bus.async_listen("ramses_cc_message", _handle_remote_event)
        unsubs = [event_unsub]

        coordinator = await RamsesCommands(hass)._get_ramses_cc_coordinator()
        client = (
            getattr(coordinator, "client", None) if coordinator is not None else None
        )
        add_msg_handler = getattr(client, "add_msg_handler", None)
        if callable(add_msg_handler):
            msg_unsub = add_msg_handler(_handle_remote_msg)
            if callable(msg_unsub):
                unsubs.append(msg_unsub)

        domain_data["_fan_remote_listener_unsubs"] = unsubs
        domain_data["_fan_remote_listener_started"] = True

    if not hass.services.has_service(DOMAIN, SVC_SEND_FAN_COMMAND):
        hass.services.async_register(
            DOMAIN,
            SVC_SEND_FAN_COMMAND,
            _async_send_fan_command,
            schema=vol.Schema(
                {
                    vol.Required("device_id"): cv.string,
                    vol.Required("command"): cv.string,
                },
                extra=vol.PREVENT_EXTRA,
            ),
        )

    if not hass.services.has_service(DOMAIN, SVC_SET_FAN_PARAMETER):
        hass.services.async_register(
            DOMAIN,
            SVC_SET_FAN_PARAMETER,
            _async_set_fan_parameter,
            schema=vol.Schema(
                {
                    vol.Required("device_id"): cv.string,
                    vol.Required("param_id"): cv.string,
                    vol.Required("value"): cv.string,
                    vol.Optional("from_id"): cv.string,
                },
                extra=vol.PREVENT_EXTRA,
            ),
        )

    if not hass.services.has_service(DOMAIN, SVC_UPDATE_FAN_PARAMS):
        hass.services.async_register(
            DOMAIN,
            SVC_UPDATE_FAN_PARAMS,
            _async_update_fan_params,
            schema=vol.Schema(
                {
                    vol.Required("device_id"): cv.string,
                    vol.Optional("from_id"): cv.string,
                },
                extra=vol.PREVENT_EXTRA,
            ),
        )

    if not hass.services.has_service(DOMAIN, SVC_GET_QUEUE_STATISTICS):
        hass.services.async_register(
            DOMAIN,
            SVC_GET_QUEUE_STATISTICS,
            _async_get_queue_statistics,
            schema=vol.Schema({}, extra=vol.PREVENT_EXTRA),
        )

    # Zone testing services (Phase 5 hardware testing)
    if not hass.services.has_service(DOMAIN, SVC_SET_ZONE_DEMAND):

        async def _async_set_zone_demand(call: ServiceCall) -> None:
            """Set manual zone demand for testing."""
            fan_id = call.data["device_id"]
            zone_id = call.data["zone_id"]
            has_demand = call.data.get("has_demand", True)

            demand_registry = get_zone_demand_registry(hass)
            demand_registry.set_demand(
                fan_id=fan_id,
                zone_id=zone_id,
                source=DemandSource.MANUAL,
                has_demand=has_demand,
            )
            _LOGGER.info(
                "Manual zone demand set: %s:%s = %s", fan_id, zone_id, has_demand
            )

        hass.services.async_register(
            DOMAIN,
            SVC_SET_ZONE_DEMAND,
            _async_set_zone_demand,
            schema=vol.Schema(
                {
                    vol.Required("device_id"): cv.string,
                    vol.Required("zone_id"): cv.string,
                    vol.Optional("has_demand", default=True): cv.boolean,
                },
                extra=vol.PREVENT_EXTRA,
            ),
        )

    if not hass.services.has_service(DOMAIN, SVC_CLEAR_ZONE_DEMAND):

        async def _async_clear_zone_demand(call: ServiceCall) -> None:
            """Clear manual zone demand for testing."""
            fan_id = call.data["device_id"]
            zone_id = call.data.get("zone_id")

            demand_registry = get_zone_demand_registry(hass)
            if zone_id:
                demand_registry.clear_demand(fan_id, zone_id, DemandSource.MANUAL)
            else:
                # Clear all manual demands for this FAN
                zones = demand_registry.get_all_demands_for_fan(fan_id)
                for zid in zones:
                    demand_registry.clear_demand(fan_id, zid, DemandSource.MANUAL)
            _LOGGER.info("Manual zone demand cleared: %s:%s", fan_id, zone_id or "all")

        hass.services.async_register(
            DOMAIN,
            SVC_CLEAR_ZONE_DEMAND,
            _async_clear_zone_demand,
            schema=vol.Schema(
                {
                    vol.Required("device_id"): cv.string,
                    vol.Optional("zone_id"): cv.string,
                },
                extra=vol.PREVENT_EXTRA,
            ),
        )

    if not hass.services.has_service(DOMAIN, SVC_RUN_ZONE_ACTUATION):

        async def _async_run_zone_actuation(call: ServiceCall) -> None:
            """Run zone actuation cycle for testing."""
            fan_id = call.data["device_id"]

            coordinator = get_zone_coordinator(hass, fan_id)
            results = await coordinator.async_run_zone_actuation_cycle()

            _LOGGER.info("Zone actuation cycle completed for %s: %s", fan_id, results)

            # Return results via event for UI feedback
            hass.bus.fire(
                "ramses_extras_zone_actuation_completed",
                {"fan_id": fan_id, "results": results},
            )

        hass.services.async_register(
            DOMAIN,
            SVC_RUN_ZONE_ACTUATION,
            _async_run_zone_actuation,
            schema=vol.Schema(
                {
                    vol.Required("device_id"): cv.string,
                },
                extra=vol.PREVENT_EXTRA,
            ),
        )

    if not hass.services.has_service(DOMAIN, SVC_CALIBRATE_ALL_VALVES):

        async def _async_calibrate_all_valves(call: ServiceCall) -> None:
            """Calibrate all zone valves sequentially.

            1. Set FAN to low mode
            2. Save current valve positions
            3. Calibrate each valve one by one with delays (gets IP from device)
            4. Restore original valve positions
            """
            fan_id = call.data["device_id"]

            # Get coordinator
            coordinator = get_zone_coordinator(hass, fan_id)

            # Get all zones for this FAN from coordinator's _zone_configs
            zones = list(coordinator._zone_configs.keys())
            _LOGGER.info(
                "Starting valve calibration for %s with %s zones", fan_id, len(zones)
            )

            # Fire event to indicate calibration started
            hass.bus.fire(
                "ramses_extras_valve_calibration_started",
                {"fan_id": fan_id, "zone_count": len(zones)},
            )

            # Step 1: Set FAN to low mode
            _LOGGER.info("Setting FAN %s to low mode for calibration", fan_id)
            commands = RamsesCommands(hass)
            await commands.send_command(fan_id, "fan_low")
            await asyncio.sleep(2)

            # Step 2: Save current valve positions
            original_positions: dict[str, dict[str, int | None]] = {}
            for zone_id in zones:
                zone_config = coordinator.get_zone_config(zone_id)
                if not zone_config or not zone_config.is_controllable:
                    continue

                inlet_entity = zone_config.inlet_valve_entity
                outlet_entity = zone_config.outlet_valve_entity

                inlet_pos = None
                outlet_pos = None

                if inlet_entity:
                    state = hass.states.get(inlet_entity)
                    if state:
                        # Try different attribute names Shelly might use
                        for attr in ["current_position", "position"]:
                            val = state.attributes.get(attr)
                            if val is not None:
                                inlet_pos = int(val)
                                break
                        _LOGGER.info(
                            "Saved inlet %s position: %s (state=%s, attrs=%s)",
                            inlet_entity,
                            inlet_pos,
                            state.state,
                            dict(state.attributes),
                        )

                if outlet_entity:
                    state = hass.states.get(outlet_entity)
                    if state:
                        for attr in ["current_position", "position"]:
                            val = state.attributes.get(attr)
                            if val is not None:
                                outlet_pos = int(val)
                                break
                        _LOGGER.info(
                            "Saved outlet %s position: %s (state=%s)",
                            outlet_entity,
                            outlet_pos,
                            state.state,
                        )

                original_positions[zone_id] = {
                    "inlet": inlet_pos,
                    "outlet": outlet_pos,
                }
                _LOGGER.info(
                    "Saved positions for zone %s: inlet=%s, outlet=%s",
                    zone_id,
                    inlet_pos,
                    outlet_pos,
                )

            # Helper to check if Shelly is online
            async def _is_shelly_available(ip: str, timeout: int = 5) -> bool:
                """Check if Shelly device is reachable via HTTP."""
                import aiohttp

                try:
                    async with aiohttp.ClientSession() as session:
                        async with session.get(
                            f"http://{ip}/rpc/Shelly.GetStatus",
                            timeout=aiohttp.ClientTimeout(total=timeout),
                        ):
                            return True
                except Exception:
                    return False

            # Helper to get IP from entity's device
            async def _get_shelly_ip(entity_id: str | None) -> str | None:
                """Get IP address from Shelly device entity."""
                if not entity_id:
                    return None

                state = hass.states.get(entity_id)
                if not state:
                    return None

                ip = state.attributes.get("ip_address") or state.attributes.get("ip")
                if ip:
                    return str(ip)

                try:
                    from homeassistant.helpers import device_registry as dr
                    from homeassistant.helpers import entity_registry as er

                    entity_reg = er.async_get(hass)
                    entity_entry = entity_reg.async_get(entity_id)

                    if entity_entry and entity_entry.device_id:
                        device_reg = dr.async_get(hass)
                        device = device_reg.async_get(entity_entry.device_id)

                        if device and device.connections:
                            for conn_type, conn_id in device.connections:
                                if conn_type == "ip":
                                    return str(conn_id)

                        if device and device.configuration_url:
                            import re

                            match = re.search(
                                r"https?://([^/]+)", device.configuration_url
                            )
                            if match:
                                return match.group(1)
                except Exception as err:
                    _LOGGER.debug("Could not get device IP for %s: %s", entity_id, err)

                return None

            # Step 3: Calibrate each valve sequentially
            calibration_results = {}
            for zone_id in zones:
                zone_config = coordinator.get_zone_config(zone_id)
                if not zone_config or not zone_config.is_controllable:
                    continue

                _LOGGER.info("Calibrating zone %s:%s", fan_id, zone_id)

                inlet_entity = zone_config.inlet_valve_entity
                outlet_entity = zone_config.outlet_valve_entity

                inlet_ip = await _get_shelly_ip(inlet_entity)
                outlet_ip = await _get_shelly_ip(outlet_entity)

                if inlet_entity and not inlet_ip:
                    _LOGGER.warning("Could not determine IP for inlet %s", inlet_entity)
                    calibration_results[f"{zone_id}_inlet"] = "ip_not_found"

                if outlet_entity and not outlet_ip:
                    _LOGGER.warning(
                        "Could not determine IP for outlet %s", outlet_entity
                    )
                    calibration_results[f"{zone_id}_outlet"] = "ip_not_found"

                # Check availability before attempting calibration
                inlet_available = inlet_ip and await _is_shelly_available(inlet_ip)
                outlet_available = outlet_ip and await _is_shelly_available(outlet_ip)

                if inlet_ip and not inlet_available:
                    _LOGGER.warning(
                        "Inlet Shelly at %s is offline, skipping calibration", inlet_ip
                    )
                    calibration_results[f"{zone_id}_inlet"] = "device_offline"

                if outlet_ip and not outlet_available:
                    _LOGGER.warning(
                        "Outlet Shelly at %s is offline, skipping calibration",
                        outlet_ip,
                    )
                    calibration_results[f"{zone_id}_outlet"] = "device_offline"

                # Calibrate inlet valve
                if inlet_available:
                    try:
                        _LOGGER.debug("Calibrating inlet valve at %s", inlet_ip)
                        await hass.services.async_call(
                            "rest_command",
                            "shelly_calibrate_cover_0",
                            {"ip": inlet_ip},
                            blocking=False,
                        )
                        await asyncio.sleep(5)
                        calibration_results[f"{zone_id}_inlet"] = "ok"
                    except Exception as err:
                        _LOGGER.warning(
                            "Failed to calibrate inlet %s: %s", inlet_ip, err
                        )
                        calibration_results[f"{zone_id}_inlet"] = str(err)

                # Calibrate outlet valve
                if outlet_available:
                    try:
                        _LOGGER.debug("Calibrating outlet valve at %s", outlet_ip)
                        await hass.services.async_call(
                            "rest_command",
                            "shelly_calibrate_cover_0",
                            {"ip": outlet_ip},
                            blocking=False,
                        )
                        await asyncio.sleep(5)
                        calibration_results[f"{zone_id}_outlet"] = "ok"
                    except Exception as err:
                        _LOGGER.warning(
                            "Failed to calibrate outlet %s: %s", outlet_ip, err
                        )
                        calibration_results[f"{zone_id}_outlet"] = str(err)

            # Step 4: Wait for calibration to complete (Shelly can take 60+ seconds)
            _LOGGER.info(
                "Waiting 90 seconds for calibration to complete "
                "before restoring positions..."
            )
            await asyncio.sleep(90)

            # Fire completion event when calibration is expected to be complete.
            # Valve restoration happens after this and should not show as "calibrating".
            hass.bus.fire(
                "ramses_extras_valve_calibration_completed",
                {"fan_id": fan_id, "results": calibration_results},
            )
            _LOGGER.info(
                "Valve calibration completed for %s: %s", fan_id, calibration_results
            )

            # Step 5: Restore original valve positions
            _LOGGER.info(
                "Restoring original valve positions after calibration: %s",
                original_positions,
            )

            async def _restore_position(
                entity_id: str, position: int, attempts: int = 5
            ) -> bool:
                for attempt in range(attempts):
                    try:
                        await asyncio.sleep(2)  # Small delay before each attempt
                        _LOGGER.info(
                            "Restoring %s to position %s (attempt %s/%s)",
                            entity_id,
                            position,
                            attempt + 1,
                            attempts,
                        )
                        await hass.services.async_call(
                            "cover",
                            "set_cover_position",
                            {"entity_id": entity_id, "position": position},
                            blocking=True,
                        )
                        # Wait and verify the position was set
                        await asyncio.sleep(3)
                        valve_state = hass.states.get(entity_id)
                        current_pos = (
                            valve_state.attributes.get("current_position")
                            if valve_state
                            else None
                        )
                        if current_pos is None:
                            current_pos = (
                                valve_state.attributes.get("position")
                                if valve_state
                                else None
                            )
                        _LOGGER.info(
                            "Valve %s position after restore: %s (target: %s)",
                            entity_id,
                            current_pos,
                            position,
                        )
                        return True
                    except Exception as err:
                        _LOGGER.warning(
                            "Failed to restore %s (attempt %s/%s): %s",
                            entity_id,
                            attempt + 1,
                            attempts,
                            err,
                        )
                        if attempt < attempts - 1:
                            await asyncio.sleep(5)  # Wait before retry
                return False

            for zone_id, positions in original_positions.items():
                zone_config = coordinator.get_zone_config(zone_id)
                if not zone_config:
                    continue

                inlet_entity = zone_config.inlet_valve_entity
                outlet_entity = zone_config.outlet_valve_entity

                if inlet_entity and positions["inlet"] is not None:
                    success = await _restore_position(inlet_entity, positions["inlet"])
                    if not success:
                        _LOGGER.error(
                            "Failed to restore inlet valve %s after all attempts",
                            inlet_entity,
                        )
                    await asyncio.sleep(2)  # Delay between valves

                if outlet_entity and positions["outlet"] is not None:
                    success = await _restore_position(
                        outlet_entity, positions["outlet"]
                    )
                    if not success:
                        _LOGGER.error(
                            "Failed to restore outlet valve %s after all attempts",
                            outlet_entity,
                        )
                    await asyncio.sleep(2)  # Delay between zones

            _LOGGER.info("Valve position restoration completed for %s", fan_id)

        hass.services.async_register(
            DOMAIN,
            SVC_CALIBRATE_ALL_VALVES,
            _async_calibrate_all_valves,
            schema=vol.Schema(
                {
                    vol.Required("device_id"): cv.string,
                },
                extra=vol.PREVENT_EXTRA,
            ),
        )

    if not hass.services.has_service(DOMAIN, SVC_FORCE_ZONE_VENTILATION):

        async def _async_force_zone_ventilation(call: ServiceCall) -> None:
            """Force zone ventilation on/off by directly setting valve positions.

            This bypasses the demand/actuation cycle and directly controls the valves.
            """
            fan_id = call.data["device_id"]
            zone_id = call.data["zone_id"]
            state = call.data[
                "state"
            ]  # "on" or "off" (can also use "open" or "closed")

            # Normalize state
            state_norm = str(state).lower().strip()
            is_ventilation_on = state_norm in ("on", "open", "true", "yes", "1")

            coordinator = get_zone_coordinator(hass, fan_id)
            zone_config = coordinator.get_zone_config(zone_id)

            if not zone_config:
                _LOGGER.warning("Zone %s:%s not found", fan_id, zone_id)
                return

            if not zone_config.is_controllable:
                _LOGGER.warning("Zone %s:%s is not controllable", fan_id, zone_id)
                return

            inlet_entity = zone_config.inlet_valve_entity
            outlet_entity = zone_config.outlet_valve_entity

            if is_ventilation_on:
                target_position = int(zone_config.max_position)
            elif state_norm in ("min", "close", "closed", "off", "false", "no", "0"):
                target_position = int(zone_config.min_position)
            else:
                target_position = int(zone_config.min_position)

            _LOGGER.info(
                "Forcing zone %s:%s ventilation %s (position=%s)",
                fan_id,
                zone_id,
                "ON" if is_ventilation_on else "OFF",
                target_position,
            )

            results = {}

            # Set inlet valve
            if inlet_entity:
                try:
                    await hass.services.async_call(
                        "cover",
                        "set_cover_position",
                        {"entity_id": inlet_entity, "position": target_position},
                        blocking=True,
                    )
                    results["inlet"] = "ok"
                    _LOGGER.debug("Set inlet %s to %s", inlet_entity, target_position)
                except Exception as err:
                    results["inlet"] = str(err)
                    _LOGGER.warning("Failed to set inlet %s: %s", inlet_entity, err)

            # Set outlet valve
            if outlet_entity:
                try:
                    await hass.services.async_call(
                        "cover",
                        "set_cover_position",
                        {"entity_id": outlet_entity, "position": target_position},
                        blocking=True,
                    )
                    results["outlet"] = "ok"
                    _LOGGER.debug("Set outlet %s to %s", outlet_entity, target_position)
                except Exception as err:
                    results["outlet"] = str(err)
                    _LOGGER.warning("Failed to set outlet %s: %s", outlet_entity, err)

            # Fire event for UI feedback
            hass.bus.fire(
                "ramses_extras_zone_ventilation_forced",
                {
                    "fan_id": fan_id,
                    "zone_id": zone_id,
                    "state": "on" if is_ventilation_on else "off",
                    "position": target_position,
                    "results": results,
                },
            )

            _LOGGER.info(
                "Zone %s:%s ventilation forced %s: %s",
                fan_id,
                zone_id,
                "ON" if is_ventilation_on else "OFF",
                results,
            )

        hass.services.async_register(
            DOMAIN,
            SVC_FORCE_ZONE_VENTILATION,
            _async_force_zone_ventilation,
            schema=vol.Schema(
                {
                    vol.Required("device_id"): cv.string,
                    vol.Required("zone_id"): cv.string,
                    vol.Required("state"): cv.string,  # "on", "off", "open", "closed"
                },
                extra=vol.PREVENT_EXTRA,
            ),
        )
