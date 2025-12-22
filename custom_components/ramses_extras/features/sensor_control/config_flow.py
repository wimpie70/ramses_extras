from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.helpers import selector

from ...const import AVAILABLE_FEATURES
from .const import SUPPORTED_METRICS

_LOGGER = logging.getLogger(__name__)


def _device_key(device_id: str) -> str:
    return device_id.replace(":", "_")


async def async_step_sensor_control_config(
    flow: Any, user_input: dict[str, Any] | None
) -> Any:
    feature_id = "sensor_control"
    feature_config = AVAILABLE_FEATURES.get(feature_id, {})

    # Make sure we work with the latest config entry/options state
    refresh = getattr(flow, "_refresh_config_entry", None)
    if callable(refresh):  # noqa: SIM108
        refresh()

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

        # Build a compact overview of existing mappings so the user can see
        # current sensor sources before picking a device.
        overview_lines: list[str] = []
        try:
            options = dict(flow._config_entry.options)  # noqa: SLF001
            sensor_control_options = options.get("sensor_control") or {}
            sources: dict[str, dict[str, dict[str, Any]]] = sensor_control_options.get(
                "sources", {}
            )

            if sources:
                overview_lines.append("📡 **Existing Sensor Control Mappings**\n")
                for device_key in sorted(sources.keys()):
                    device_sources = sources.get(device_key) or {}
                    device_id = device_key.replace("_", ":")
                    overview_lines.append(f"**Device {device_id}** ({device_key}):")

                    for metric in SUPPORTED_METRICS:
                        override = device_sources.get(metric) or {}
                        kind = str(override.get("kind") or "internal")
                        entity_id = override.get("entity_id")

                        if kind == "internal":
                            summary = "internal"
                        elif kind in ("external", "external_entity"):
                            summary = (
                                f"external → {entity_id}" if entity_id else "external"
                            )
                        elif kind == "derived":
                            summary = "derived"
                        elif kind == "none":
                            summary = "disabled"
                        else:
                            summary = kind

                        overview_lines.append(f"- {metric}: {summary}")

                    overview_lines.append("")
        except Exception:  # pragma: no cover - overview is best-effort only
            overview_lines = []

        info_text = ""
        if overview_lines:
            info_text += "\n".join(overview_lines) + "\n\n"

        info_text += "🧭 **Sensor Control**\n\n"
        info_text += "Select a device to configure sensor sources."
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

    _LOGGER.debug(
        "Loaded raw sensor_control options from config_entry for %s: %s",
        selected_device_id,
        sensor_control_options,
    )

    sources = dict(sensor_control_options.get("sources", {}))
    abs_inputs = dict(sensor_control_options.get("abs_humidity_inputs", {}))

    dkey = _device_key(selected_device_id)
    device_sources = dict(sources.get(dkey, {}))
    device_abs_inputs = dict(abs_inputs.get(dkey, {}))

    _LOGGER.debug(
        "Loaded device_sources for %s (key=%s): %s",
        selected_device_id,
        dkey,
        device_sources,
    )

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

    def _source_from_input(
        data: dict[str, Any], kind_key: str, ent_key: str, allow_none: bool
    ) -> dict[str, Any]:
        kind = str(data.get(kind_key) or "internal")
        if kind == "none" and allow_none:
            return {"kind": "none"}
        if kind == "external":
            ent = data.get(ent_key)
            if ent:
                return {"kind": "external", "entity_id": str(ent)}
            # No valid external entity selected, fall back to internal
            return {"kind": "internal"}
        return {"kind": "internal"}

    def _abs_part_from_input(
        data: dict[str, Any], kind_key: str, ent_key: str
    ) -> dict[str, Any]:
        kind = str(data.get(kind_key) or "internal")
        if kind == "external":
            ent = data.get(ent_key)
            if ent:
                return {"kind": "external", "entity_id": str(ent)}
            # No valid external entity selected, fall back to internal
            return {"kind": "internal"}
        return {"kind": "internal"}

    # Submenu-style grouping: select which group of metrics to configure
    group_stage = getattr(flow, "_sensor_control_group_stage", "select_group")

    # Handle group selection menu
    if group_stage == "select_group":
        if user_input is not None:
            action = str(user_input.get("group_action") or "")
            if action == "done":
                # Go back to device selection for this feature
                flow._sensor_control_stage = "select_device"
                flow._sensor_control_group_stage = "select_group"
                return await async_step_sensor_control_config(flow, None)

            # Switch to the selected group configuration step
            flow._sensor_control_group_stage = action
            return await async_step_sensor_control_config(flow, None)

        group_options = [
            selector.SelectOptionDict(
                value="indoor_basic", label="Indoor temperature & humidity"
            ),
            selector.SelectOptionDict(
                value="outdoor_basic", label="Outdoor temperature & humidity"
            ),
            selector.SelectOptionDict(value="co2", label="CO2"),
            selector.SelectOptionDict(
                value="indoor_abs", label="Indoor absolute humidity inputs"
            ),
            selector.SelectOptionDict(
                value="outdoor_abs", label="Outdoor absolute humidity inputs"
            ),
            selector.SelectOptionDict(value="done", label="Finish editing device"),
        ]

        menu_schema = vol.Schema(
            {
                vol.Required("group_action"): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=group_options,
                        multiple=False,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                )
            }
        )

        info_text = (
            "🧭 **Sensor Control**\n\n"
            f"Configuring device: `{selected_device_id}`\n\n"
            "Select which group of sensors to configure. You can return here to "
            "configure other groups or choose Finish when done."
        )

        return flow.async_show_form(
            step_id="feature_config",
            data_schema=menu_schema,
            description_placeholders={"info": info_text},
        )

    # Handle submissions for each group step
    if user_input is not None:
        if group_stage == "indoor_basic":
            # Indoor temperature and humidity
            device_sources["indoor_temperature"] = _source_from_input(
                user_input,
                "indoor_temperature_kind",
                "indoor_temperature_entity",
                False,
            )
            device_sources["indoor_humidity"] = _source_from_input(
                user_input,
                "indoor_humidity_kind",
                "indoor_humidity_entity",
                False,
            )
        elif group_stage == "outdoor_basic":
            # Outdoor temperature and humidity
            device_sources["outdoor_temperature"] = _source_from_input(
                user_input,
                "outdoor_temperature_kind",
                "outdoor_temperature_entity",
                False,
            )
            device_sources["outdoor_humidity"] = _source_from_input(
                user_input,
                "outdoor_humidity_kind",
                "outdoor_humidity_entity",
                False,
            )
        elif group_stage == "co2":
            # CO2 source
            device_sources["co2"] = _source_from_input(
                user_input,
                "co2_kind",
                "co2_entity",
                True,
            )
        elif group_stage == "indoor_abs":
            # Indoor absolute humidity inputs
            device_abs_inputs["indoor_abs_humidity"] = {
                "temperature": _abs_part_from_input(
                    user_input,
                    "indoor_abs_humidity_temperature_kind",
                    "indoor_abs_humidity_temperature_entity",
                ),
                "humidity": _abs_part_from_input(
                    user_input,
                    "indoor_abs_humidity_humidity_kind",
                    "indoor_abs_humidity_humidity_entity",
                ),
            }
        elif group_stage == "outdoor_abs":
            # Outdoor absolute humidity inputs
            device_abs_inputs["outdoor_abs_humidity"] = {
                "temperature": _abs_part_from_input(
                    user_input,
                    "outdoor_abs_humidity_temperature_kind",
                    "outdoor_abs_humidity_temperature_entity",
                ),
                "humidity": _abs_part_from_input(
                    user_input,
                    "outdoor_abs_humidity_humidity_kind",
                    "outdoor_abs_humidity_humidity_entity",
                ),
            }

        # Persist updates for this device
        sources[dkey] = device_sources
        abs_inputs[dkey] = device_abs_inputs

        sensor_control_options["sources"] = sources
        sensor_control_options["abs_humidity_inputs"] = abs_inputs
        options[feature_id] = sensor_control_options

        _LOGGER.debug(
            "Saving sensor_control overrides for %s (group=%s): %s",
            selected_device_id,
            group_stage,
            sensor_control_options,
        )

        await flow.hass.config_entries.async_update_entry(  # noqa: SLF001
            flow._config_entry,  # noqa: SLF001
            options=options,
        )

        # After saving this group, return to the group selection menu
        flow._sensor_control_group_stage = "select_group"
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

    # Per-group schemas
    if group_stage == "indoor_basic":
        schema = vol.Schema(
            {
                vol.Required(
                    "indoor_temperature_kind",
                    default=_get_kind("indoor_temperature"),
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=kind_options,
                        multiple=False,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Optional(
                    "indoor_temperature_entity",
                    default=_get_entity("indoor_temperature"),
                ): sensor_selector,
                vol.Required(
                    "indoor_humidity_kind",
                    default=_get_kind("indoor_humidity"),
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=kind_options,
                        multiple=False,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Optional(
                    "indoor_humidity_entity",
                    default=_get_entity("indoor_humidity"),
                ): sensor_selector,
            }
        )
        info_suffix = "Indoor temperature and humidity sources."
    elif group_stage == "outdoor_basic":
        schema = vol.Schema(
            {
                vol.Required(
                    "outdoor_temperature_kind",
                    default=_get_kind("outdoor_temperature"),
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
                    "outdoor_humidity_kind",
                    default=_get_kind("outdoor_humidity"),
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
            }
        )
        info_suffix = "Outdoor temperature and humidity sources."
    elif group_stage == "co2":
        schema = vol.Schema(
            {
                vol.Required(
                    "co2_kind", default=_get_kind("co2")
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=kind_options_with_none,
                        multiple=False,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Optional("co2_entity", default=_get_entity("co2")): sensor_selector,
            }
        )
        info_suffix = "CO2 sensor source."
    elif group_stage == "indoor_abs":
        schema = vol.Schema(
            {
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
            }
        )
        info_suffix = "Indoor absolute humidity input sensors."
    elif group_stage == "outdoor_abs":
        schema = vol.Schema(
            {
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
        info_suffix = "Outdoor absolute humidity input sensors."
    else:
        # Fallback to group menu if something unexpected happens
        flow._sensor_control_group_stage = "select_group"
        return await async_step_sensor_control_config(flow, None)

    info_text = (
        "🧭 **Sensor Control**\n\n"
        f"Configuring device: `{selected_device_id}`\n\n"
        f"{info_suffix}"
    )

    return flow.async_show_form(
        step_id="feature_config",
        data_schema=schema,
        description_placeholders={"info": info_text},
    )
