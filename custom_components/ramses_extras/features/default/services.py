"""Home Assistant services exposed by the default feature.

The default feature is always enabled, and hosts common services used by cards
and other features (e.g. sending fan commands and managing 2411 parameters).
"""

from __future__ import annotations

import logging
import time

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv

from ...const import DOMAIN
from ...framework.helpers.fan_speed_arbiter import get_fan_speed_arbiter
from ...framework.helpers.ramses_commands import RamsesCommands

_LOGGER = logging.getLogger(__name__)

SVC_SEND_FAN_COMMAND = "send_fan_command"
SVC_SET_FAN_PARAMETER = "set_fan_parameter"
SVC_UPDATE_FAN_PARAMS = "update_fan_params"
SVC_GET_QUEUE_STATISTICS = "get_queue_statistics"


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
        if not isinstance(code, str) or not isinstance(payload, str):
            return None

        normalized_code = code.strip().upper()
        normalized_payload = payload.strip().upper()

        if normalized_code == "22F1":
            return {
                "000107": "fan_low",
                "000207": "fan_medium",
                "000307": "fan_high",
                "000407": "fan_auto",
                "000007": "fan_away",
            }.get(normalized_payload)

        if normalized_code == "22F3":
            return {
                "00120F03040404": "fan_timer_15min",
                "00121E03040404": "fan_timer_30min",
                "00123C03040404": "fan_timer_60min",
            }.get(normalized_payload)

        return None

    async def _async_apply_observed_remote_command(
        device_id: str, command: str, source_id: str
    ) -> None:
        arbiter = get_fan_speed_arbiter(hass)

        if command == "fan_auto":
            arbiter.set_extras_control_enabled(device_id, True)
            arbiter.clear_manual_override_state(device_id)
            await arbiter.async_commit_state(device_id, apply=False)
            await _async_resume_feature_control(device_id)
            return

        if command in {"fan_low", "fan_medium", "fan_high"}:
            arbiter.set_extras_control_enabled(device_id, True)
            arbiter.set_manual_override_state(
                device_id,
                source_id=source_id,
                requested_speed=command,
                reason="manual_remote_command",
                metadata={"origin": "remote"},
            )
            await arbiter.async_commit_state(device_id, apply=False)
            return

        if command == "fan_away" or command.startswith("fan_timer_"):
            arbiter.set_extras_control_enabled(device_id, False)
            arbiter.clear_manual_override_state(device_id)
            await arbiter.async_commit_state(device_id, apply=False)

    async def _async_handle_observed_remote_packet(
        src: object,
        dst: object,
        code: object,
        payload: object,
        verb: object = None,
    ) -> None:
        if isinstance(verb, str) and verb.strip().upper() == "RQ":
            return

        normalized_src = _normalize_id(src)
        normalized_dst = _normalize_id(dst)
        command = _observed_command_from_packet(code, payload)
        if not normalized_src or not normalized_dst or not command:
            return

        commands = RamsesCommands(hass)
        bound_rem = await commands._get_bound_rem_device(normalized_dst)
        if bound_rem != normalized_src:
            return

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
                str(payload) if payload is not None else None,
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
