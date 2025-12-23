from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.helpers import selector

from ...const import AVAILABLE_FEATURES, DOMAIN
from ...framework.helpers.device.filter import DeviceFilter
from .const import SUPPORTED_METRICS
from .device_types import DEVICE_TYPE_HANDLERS

_LOGGER = logging.getLogger(__name__)


def _device_key(device_id: str) -> str:
    return device_id.replace(":", "_")


def _get_device_type(flow: Any, device_id: str) -> str | None:
    """Best-effort lookup of device type for a given device_id.

    This mirrors the logic used by the websocket helpers, but is kept local to
    avoid adding hard dependencies between subsystems.
    """

    try:
        devices = flow.hass.data.get(DOMAIN, {}).get("devices", [])  # noqa: SLF001
        for device in devices:
            # Reuse the same device_id extraction strategy as the default
            # websocket helpers so we reliably match the selected device.
            extracted_id: str | None
            if isinstance(device, str):
                extracted_id = device
            else:
                extracted_id = None
                for attr in ("id", "device_id", "_id", "name"):
                    if hasattr(device, attr):
                        value = getattr(device, attr)
                        if value is not None:
                            extracted_id = str(value)
                            break

            if extracted_id != device_id:
                continue

            # We found the matching device; now derive a logical device type
            # using the central DeviceFilter slug logic (FAN, CO2, etc.).
            slugs = DeviceFilter._get_device_slugs(device)
            if not slugs:
                return None

            # Prefer a slug that matches a known handler key.
            for slug in slugs:
                key = str(slug).upper()
                if key in DEVICE_TYPE_HANDLERS:
                    return key

            # Fallback: return the first slug in uppercase so callers can
            # still make a reasonable decision.
            return str(slugs[0]).upper()
    except Exception:  # pragma: no cover - defensive best-effort lookup
        _LOGGER.exception("Failed to get device type for %s", device_id)

    return None


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
        # current sensor sources before picking a device. Only show
        # non-internal mappings to keep this readable, and include
        # abs_humidity_inputs for the abs humidity metrics.
        overview_lines: list[str] = []
        try:
            options = dict(flow._config_entry.options)  # noqa: SLF001
            sensor_control_options = options.get("sensor_control") or {}
            sources: dict[str, dict[str, dict[str, Any]]] = sensor_control_options.get(
                "sources", {}
            )
            abs_inputs: dict[str, dict[str, Any]] = sensor_control_options.get(
                "abs_humidity_inputs", {}
            )

            device_keys = set(sources.keys()) | set(abs_inputs.keys())

            if device_keys:
                overview_lines.append("Existing Sensor Control Mappings\n")
                for device_key in sorted(device_keys):
                    device_sources = sources.get(device_key) or {}
                    device_abs_inputs = abs_inputs.get(device_key) or {}
                    device_id = device_key.replace("_", ":")

                    device_lines: list[str] = []

                    for metric in SUPPORTED_METRICS:
                        if metric in ("indoor_abs_humidity", "outdoor_abs_humidity"):
                            metric_cfg = device_abs_inputs.get(metric) or {}
                            temp_cfg = metric_cfg.get("temperature") or {}
                            hum_cfg = metric_cfg.get("humidity") or {}
                            temp_kind = str(temp_cfg.get("kind") or "internal")
                            hum_kind = str(hum_cfg.get("kind") or "internal")

                            abs_parts: list[str] = []
                            if temp_kind == "external_abs":
                                ent = temp_cfg.get("entity_id")
                                if ent:
                                    abs_parts.append(f"external abs  {ent}")
                                else:
                                    abs_parts.append("external abs (no entity)")
                            else:
                                if temp_kind in ("external", "external_temp"):
                                    ent = temp_cfg.get("entity_id")
                                    if ent:
                                        abs_parts.append(f"temp: external  {ent}")
                                if hum_kind == "external":
                                    ent = hum_cfg.get("entity_id")
                                    if ent:
                                        abs_parts.append(f"humidity: external  {ent}")
                                if hum_kind == "none":
                                    abs_parts.append("humidity: none")

                            if not abs_parts:
                                continue

                            summary = "; ".join(abs_parts)
                            device_lines.append(f"- {metric}: {summary}")
                        else:
                            override = device_sources.get(metric) or {}
                            kind = str(override.get("kind") or "internal")
                            entity_id = override.get("entity_id")

                            if kind == "internal":
                                continue
                            if kind in ("external", "external_entity"):
                                if entity_id:
                                    summary = f"external  {entity_id}"
                                else:
                                    summary = "external (no entity)"
                            elif kind == "derived":
                                summary = "derived"
                            elif kind == "none":
                                summary = "disabled"
                            else:
                                summary = kind

                            device_lines.append(f"- {metric}: {summary}")

                    if not device_lines:
                        continue

                    overview_lines.append(f"**Device {device_id}** ({device_key}):")
                    overview_lines.extend(device_lines)
                    overview_lines.append("")
        except Exception:  # pragma: no cover - overview is best-effort only
            overview_lines = []

        info_text = ""
        if overview_lines:
            info_text += "\n".join(overview_lines) + "\n\n"

        info_text += "Sensor Control\n\n"
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

    # Resolve device type and select an appropriate handler. For now we support
    # FAN and CO2 explicitly; other types will fall back to the FAN handler so
    # they at least get a working UI.
    raw_device_type = _get_device_type(flow, selected_device_id) or "FAN"
    device_type = str(raw_device_type).upper()
    handler = DEVICE_TYPE_HANDLERS.get(device_type) or DEVICE_TYPE_HANDLERS["FAN"]

    _LOGGER.debug(
        "Sensor control handler for device %s (type=%s -> key=%s): %s",
        selected_device_id,
        raw_device_type,
        device_type,
        getattr(handler, "__name__", repr(handler)),
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
                # All changes are already saved when groups are submitted.
                # Return to the main options menu for the integration.
                flow._sensor_control_stage = "select_device"
                flow._sensor_control_group_stage = "select_group"
                return await flow.async_step_main_menu()

            # Switch to the selected group configuration step
            flow._sensor_control_group_stage = action
            return await async_step_sensor_control_config(flow, None)

        group_options = handler.get_group_options(selected_device_id)

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

        # Build a compact overview of non-internal mappings for this device,
        # including abs_humidity_inputs so users can see absolute humidity
        # wiring without going back to the global overview.
        device_overview: list[str] = []
        try:
            if device_sources or device_abs_inputs:
                device_overview.append("Current mappings for this device")
                for metric in SUPPORTED_METRICS:
                    if metric in ("indoor_abs_humidity", "outdoor_abs_humidity"):
                        metric_cfg = device_abs_inputs.get(metric) or {}
                        temp_cfg = metric_cfg.get("temperature") or {}
                        hum_cfg = metric_cfg.get("humidity") or {}
                        temp_kind = str(temp_cfg.get("kind") or "internal")
                        hum_kind = str(hum_cfg.get("kind") or "internal")

                        device_abs_parts: list[str] = []
                        if temp_kind == "external_abs":
                            ent = temp_cfg.get("entity_id")
                            if ent:
                                device_abs_parts.append(f"external abs  {ent}")
                            else:
                                device_abs_parts.append("external abs (no entity)")
                        else:
                            if temp_kind in ("external", "external_temp"):
                                ent = temp_cfg.get("entity_id")
                                if ent:
                                    device_abs_parts.append(f"temp: external  {ent}")
                            if hum_kind == "external":
                                ent = hum_cfg.get("entity_id")
                                if ent:
                                    device_abs_parts.append(
                                        f"humidity: external  {ent}"
                                    )
                            if hum_kind == "none":
                                device_abs_parts.append("humidity: none")

                        if not device_abs_parts:
                            continue

                        summary = "; ".join(device_abs_parts)
                        device_overview.append(f"- {metric}: {summary}")
                    else:
                        override = device_sources.get(metric) or {}
                        kind = str(override.get("kind") or "internal")
                        entity_id = override.get("entity_id")

                        if kind == "internal":
                            continue
                        if kind in ("external", "external_entity"):
                            if entity_id:
                                summary = f"external  {entity_id}"
                            else:
                                summary = "external (no entity)"
                        elif kind == "derived":
                            summary = "derived"
                        elif kind == "none":
                            summary = "disabled"
                        else:
                            summary = kind

                        device_overview.append(f"- {metric}: {summary}")
        except Exception:  # pragma: no cover - best-effort overview only
            device_overview = []

        info_text = ""
        if device_overview:
            info_text += "\n".join(device_overview) + "\n\n"

        info_text += (
            "Sensor Control\n\n"
            f"Configuring device: `{selected_device_id}`\n\n"
            "Select which group of sensors to configure. You can return here to "
            "configure other groups or choose Finish when done."
        )

        return flow.async_show_form(
            step_id="feature_config",
            data_schema=menu_schema,
            description_placeholders={"info": info_text},
        )

    # Handle submissions for each group step via the per-device-type handler
    if user_input is not None:
        device_sources, device_abs_inputs = handler.handle_group_submission(
            group_stage,
            user_input,
            device_sources,
            device_abs_inputs,
        )

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

        # async_update_entry is not a coroutine in this HA version; it returns a
        # bool and must not be awaited.
        flow.hass.config_entries.async_update_entry(  # noqa: SLF001
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

    # Per-group schemas via the per-device-type handler
    try:
        schema, info_suffix = handler.build_group_schema(
            group_stage,
            device_sources,
            device_abs_inputs,
            kind_options,
            kind_options_with_none,
            sensor_selector,
        )
    except Exception:
        # If the handler does not support this group (or any other error
        # occurs), fall back to the group menu to avoid breaking the flow.
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
