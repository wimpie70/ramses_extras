from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.helpers import selector

from ...const import AVAILABLE_FEATURES


def _device_key(device_id: str) -> str:
    return device_id.replace(":", "_")


async def async_step_sensor_control_config(
    flow: Any, user_input: dict[str, Any] | None
) -> Any:
    feature_id = "sensor_control"
    feature_config = AVAILABLE_FEATURES.get(feature_id, {})

    helper = flow._get_config_flow_helper()  # noqa: SLF001
    devices = flow._get_all_devices()  # noqa: SLF001
    filtered_devices = helper.get_devices_for_feature_selection(feature_config, devices)

    device_options = [
        selector.SelectOptionDict(
            value=device_id,
            label=flow._get_device_label(device),  # noqa: SLF001
        )
        for device in filtered_devices
        if (device_id := flow._extract_device_id(device))  # noqa: SLF001
    ]

    stage = getattr(flow, "_sensor_control_stage", "select_device")

    if stage == "select_device":
        if user_input is not None:
            flow._sensor_control_selected_device = user_input["device_id"]
            flow._sensor_control_stage = "configure_device"
            return await async_step_sensor_control_config(flow, None)

        schema = vol.Schema(
            {
                vol.Required("device_id"): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=device_options,
                        multiple=False,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                )
            }
        )

        info_text = (
            "🧭 **Sensor Control**\n\nSelect a device to configure sensor sources."
        )
        return flow.async_show_form(
            step_id="feature_config",
            data_schema=schema,
            description_placeholders={"info": info_text},
        )

    selected_device_id = getattr(flow, "_sensor_control_selected_device", None)
    if not selected_device_id:
        flow._sensor_control_stage = "select_device"
        return await async_step_sensor_control_config(flow, None)

    options = dict(flow._config_entry.options)  # noqa: SLF001
    sensor_control_options = dict(options.get(feature_id, {}))

    sources = dict(sensor_control_options.get("sources", {}))
    abs_inputs = dict(sensor_control_options.get("abs_humidity_inputs", {}))

    dkey = _device_key(selected_device_id)
    device_sources = dict(sources.get(dkey, {}))
    device_abs_inputs = dict(abs_inputs.get(dkey, {}))

    def _get_kind(metric: str, default: str = "internal") -> str:
        raw = device_sources.get(metric) or {}
        kind = raw.get("kind")
        return str(kind) if kind else default

    def _get_entity(metric: str) -> str | None:
        raw = device_sources.get(metric) or {}
        ent = raw.get("entity_id")
        return str(ent) if ent else None

    def _get_abs_part(metric: str, part: str) -> dict[str, Any]:
        metric_cfg = device_abs_inputs.get(metric) or {}
        part_cfg = metric_cfg.get(part) or {}
        if not isinstance(part_cfg, dict):
            return {}
        return part_cfg

    def _get_abs_kind(metric: str, part: str) -> str:
        return str(_get_abs_part(metric, part).get("kind") or "internal")

    def _get_abs_entity(metric: str, part: str) -> str | None:
        ent = _get_abs_part(metric, part).get("entity_id")
        return str(ent) if ent else None

    if user_input is not None:

        def _source_from_input(
            kind_key: str, ent_key: str, allow_none: bool
        ) -> dict[str, Any]:
            kind = str(user_input.get(kind_key) or "internal")
            if kind == "none" and allow_none:
                return {"kind": "none"}
            if kind == "external":
                ent = user_input.get(ent_key)
                if ent:
                    return {"kind": "external", "entity_id": str(ent)}
                return {"kind": "external", "entity_id": None}
            return {"kind": "internal"}

        new_sources = {
            "indoor_temperature": _source_from_input(
                "indoor_temperature_kind", "indoor_temperature_entity", False
            ),
            "indoor_humidity": _source_from_input(
                "indoor_humidity_kind", "indoor_humidity_entity", False
            ),
            "co2": _source_from_input("co2_kind", "co2_entity", True),
            "outdoor_temperature": _source_from_input(
                "outdoor_temperature_kind", "outdoor_temperature_entity", False
            ),
            "outdoor_humidity": _source_from_input(
                "outdoor_humidity_kind", "outdoor_humidity_entity", False
            ),
        }

        def _abs_part_from_input(kind_key: str, ent_key: str) -> dict[str, Any]:
            kind = str(user_input.get(kind_key) or "internal")
            if kind == "external":
                ent = user_input.get(ent_key)
                if ent:
                    return {"kind": "external", "entity_id": str(ent)}
                return {"kind": "external", "entity_id": None}
            return {"kind": "internal"}

        new_abs_inputs = {
            "indoor_abs_humidity": {
                "temperature": _abs_part_from_input(
                    "indoor_abs_humidity_temperature_kind",
                    "indoor_abs_humidity_temperature_entity",
                ),
                "humidity": _abs_part_from_input(
                    "indoor_abs_humidity_humidity_kind",
                    "indoor_abs_humidity_humidity_entity",
                ),
            },
            "outdoor_abs_humidity": {
                "temperature": _abs_part_from_input(
                    "outdoor_abs_humidity_temperature_kind",
                    "outdoor_abs_humidity_temperature_entity",
                ),
                "humidity": _abs_part_from_input(
                    "outdoor_abs_humidity_humidity_kind",
                    "outdoor_abs_humidity_humidity_entity",
                ),
            },
        }

        device_sources.update(new_sources)
        device_abs_inputs.update(new_abs_inputs)

        sources[dkey] = device_sources
        abs_inputs[dkey] = device_abs_inputs

        sensor_control_options["sources"] = sources
        sensor_control_options["abs_humidity_inputs"] = abs_inputs
        options[feature_id] = sensor_control_options

        await flow.hass.config_entries.async_update_entry(
            flow._config_entry,
            options=options,  # noqa: SLF001
        )

        flow._sensor_control_stage = "select_device"
        flow._sensor_control_selected_device = None
        return await async_step_sensor_control_config(flow, None)

    kind_options = [
        selector.SelectOptionDict(value="internal", label="Internal (default)"),
        selector.SelectOptionDict(value="external", label="External entity"),
    ]

    kind_options_with_none = kind_options + [
        selector.SelectOptionDict(value="none", label="None"),
    ]

    sensor_selector = selector.EntitySelector(
        selector.EntitySelectorConfig(domain=["sensor"])
    )

    schema = vol.Schema(
        {
            vol.Required(
                "indoor_temperature_kind", default=_get_kind("indoor_temperature")
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=kind_options,
                    multiple=False,
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            ),
            vol.Optional(
                "indoor_temperature_entity", default=_get_entity("indoor_temperature")
            ): sensor_selector,
            vol.Required(
                "indoor_humidity_kind", default=_get_kind("indoor_humidity")
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=kind_options,
                    multiple=False,
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            ),
            vol.Optional(
                "indoor_humidity_entity", default=_get_entity("indoor_humidity")
            ): sensor_selector,
            vol.Required("co2_kind", default=_get_kind("co2")): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=kind_options_with_none,
                    multiple=False,
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            ),
            vol.Optional("co2_entity", default=_get_entity("co2")): sensor_selector,
            vol.Required(
                "outdoor_temperature_kind", default=_get_kind("outdoor_temperature")
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=kind_options,
                    multiple=False,
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            ),
            vol.Optional(
                "outdoor_temperature_entity",
                default=_get_entity("outdoor_temperature"),
            ): sensor_selector,
            vol.Required(
                "outdoor_humidity_kind", default=_get_kind("outdoor_humidity")
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=kind_options,
                    multiple=False,
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            ),
            vol.Optional(
                "outdoor_humidity_entity",
                default=_get_entity("outdoor_humidity"),
            ): sensor_selector,
            vol.Required(
                "indoor_abs_humidity_temperature_kind",
                default=_get_abs_kind("indoor_abs_humidity", "temperature"),
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=kind_options,
                    multiple=False,
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            ),
            vol.Optional(
                "indoor_abs_humidity_temperature_entity",
                default=_get_abs_entity("indoor_abs_humidity", "temperature"),
            ): sensor_selector,
            vol.Required(
                "indoor_abs_humidity_humidity_kind",
                default=_get_abs_kind("indoor_abs_humidity", "humidity"),
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=kind_options,
                    multiple=False,
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            ),
            vol.Optional(
                "indoor_abs_humidity_humidity_entity",
                default=_get_abs_entity("indoor_abs_humidity", "humidity"),
            ): sensor_selector,
            vol.Required(
                "outdoor_abs_humidity_temperature_kind",
                default=_get_abs_kind("outdoor_abs_humidity", "temperature"),
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=kind_options,
                    multiple=False,
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            ),
            vol.Optional(
                "outdoor_abs_humidity_temperature_entity",
                default=_get_abs_entity("outdoor_abs_humidity", "temperature"),
            ): sensor_selector,
            vol.Required(
                "outdoor_abs_humidity_humidity_kind",
                default=_get_abs_kind("outdoor_abs_humidity", "humidity"),
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=kind_options,
                    multiple=False,
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            ),
            vol.Optional(
                "outdoor_abs_humidity_humidity_entity",
                default=_get_abs_entity("outdoor_abs_humidity", "humidity"),
            ): sensor_selector,
        }
    )

    info_text = (
        "🧭 **Sensor Control**\n\n"
        f"Configuring device: `{selected_device_id}`\n\n"
        "Leave as Internal to use the device defaults."
    )

    return flow.async_show_form(
        step_id="feature_config",
        data_schema=schema,
        description_placeholders={"info": info_text},
    )
