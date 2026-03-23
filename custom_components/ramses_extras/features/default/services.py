"""Home Assistant services exposed by the default feature.

The default feature is always enabled, and hosts common services used by cards
and other features (e.g. sending fan commands and managing 2411 parameters).
"""

from __future__ import annotations

import logging

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
            await arbiter.async_clear_demand(device_id, feature_id=feature_id)

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

        if command == "fan_auto":
            arbiter = get_fan_speed_arbiter(hass)
            await arbiter.async_clear_manual_override(device_id)
            await _async_resume_feature_control(device_id)
            return

        if command in {"fan_low", "fan_medium", "fan_high"}:
            arbiter = get_fan_speed_arbiter(hass)
            await arbiter.async_set_manual_override(
                device_id,
                source_id="default_service",
                requested_speed=command,
                reason="manual_card_command",
                metadata={"origin": "service"},
            )
            await _async_clear_feature_fan_demands(device_id)
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
