from __future__ import annotations

import asyncio
import json
import logging
import re
from pathlib import Path
from typing import Any

import voluptuous as vol
from homeassistant.helpers import selector

from ...const import AVAILABLE_FEATURES, DOMAIN
from ...framework.helpers.device.filter import DeviceFilter
from .const import SUPPORTED_METRICS
from .device_types import DEVICE_TYPE_HANDLERS

_LOGGER = logging.getLogger(__name__)

_FEATURE_DIR = Path(__file__).resolve().parent


async def _async_load_sensor_control_info_suffix_translations(
    hass: Any,
) -> dict[str, str]:
    language = getattr(getattr(hass, "config", None), "language", "en") or "en"
    cache = hass.data.setdefault(DOMAIN, {}).setdefault("_sc_info_suffix", {})
    cached = cache.get(language)
    if isinstance(cached, dict):
        return cached

    translations_dir = _FEATURE_DIR / "translations"

    def _load(lang: str) -> dict[str, str]:
        path = translations_dir / f"{lang}.json"
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}
        except Exception:
            return {}

        info_suffix = raw.get("info_suffix") if isinstance(raw, dict) else None
        if not isinstance(info_suffix, dict):
            return {}
        return {
            str(k): str(v)
            for k, v in info_suffix.items()
            if isinstance(k, str) and isinstance(v, str)
        }

    loaded = await asyncio.to_thread(_load, language)
    if not loaded and language != "en":
        loaded = await asyncio.to_thread(_load, "en")

    cache[language] = loaded
    return loaded


def _device_key(device_id: str) -> str:
    return device_id.replace(":", "_")


def _slugify_area_sensor_id(label: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", label.strip().lower())
    slug = slug.strip("_")
    return slug or "area_sensor"


def _unique_area_sensor_id(
    label: str, existing_area_sensors: list[dict[str, Any]]
) -> str:
    base = _slugify_area_sensor_id(label)
    existing_ids = {
        str(item.get("source_id"))
        for item in existing_area_sensors
        if isinstance(item, dict) and item.get("source_id")
    }
    if base not in existing_ids:
        return base

    suffix = 2
    while f"{base}_{suffix}" in existing_ids:
        suffix += 1
    return f"{base}_{suffix}"


def _get_area_sensor_by_id(
    area_sensors: list[dict[str, Any]], source_id: str | None
) -> dict[str, Any] | None:
    if not source_id:
        return None
    for item in area_sensors:
        if isinstance(item, dict) and str(item.get("source_id") or "") == source_id:
            return item
    return None


def _describe_area_sensor(area_sensor: dict[str, Any]) -> str:
    label = str(area_sensor.get("label") or area_sensor.get("source_id") or "Unnamed")
    temp_entity = str(area_sensor.get("temperature_entity") or "missing")
    humidity_entity = str(area_sensor.get("humidity_entity") or "missing")
    spike_rise = area_sensor.get("spike_rise_percent")
    spike_window = area_sensor.get("spike_window_minutes")
    check_interval = area_sensor.get("check_interval_minutes")
    enabled = bool(area_sensor.get("enabled", True))

    details = [
        f"temp: {temp_entity}",
        f"humidity: {humidity_entity}",
    ]
    if spike_rise is not None and spike_window is not None:
        details.append(f"spike: {spike_rise}%/{spike_window}m")
    if check_interval is not None:
        details.append(f"check: {check_interval}m")
    details.append("enabled" if enabled else "disabled")

    zone_id = str(area_sensor.get("zone_id") or "").strip()
    if zone_id:
        details.append(f"zone: {zone_id}")

    return f"- area sensor {label}: " + "; ".join(details)


def _validate_area_sensor_entries(area_sensors: Any) -> list[dict[str, Any]]:
    if not isinstance(area_sensors, list):
        return []
    return [item for item in area_sensors if isinstance(item, dict)]


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
        hass = getattr(flow, "hass", None)
        if hass is not None:
            refresh(hass)
        else:
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
            device_id = user_input.get("device_id")
            if not device_id:
                _LOGGER.error("No device_id provided in sensor_control config flow")
                flow._sensor_control_stage = "select_device"
                return await async_step_sensor_control_config(flow, None)
            flow._sensor_control_selected_device = device_id
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
            area_sensor_cfgs: dict[str, list[dict[str, Any]]] = (
                sensor_control_options.get("area_sensors") or {}
            )

            device_keys = (
                set(sources.keys())
                | set(abs_inputs.keys())
                | set(area_sensor_cfgs.keys())
            )

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
                        area_sensor_list = _validate_area_sensor_entries(
                            area_sensor_cfgs.get(device_key)
                        )
                        if not area_sensor_list:
                            continue
                    else:
                        area_sensor_list = _validate_area_sensor_entries(
                            area_sensor_cfgs.get(device_key)
                        )

                    for area_sensor in area_sensor_list:
                        device_lines.append(_describe_area_sensor(area_sensor))

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
    area_sensors = dict(sensor_control_options.get("area_sensors", {}))

    dkey = _device_key(selected_device_id)
    device_sources = dict(sources.get(dkey, {}))
    device_abs_inputs = dict(abs_inputs.get(dkey, {}))
    device_area_sensors = _validate_area_sensor_entries(area_sensors.get(dkey))

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
            flow._sensor_control_group_stage = (
                "area_sensors_menu" if action == "area_sensors" else action
            )
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
            for area_sensor in device_area_sensors:
                if not device_overview:
                    device_overview.append("Current mappings for this device")
                device_overview.append(_describe_area_sensor(area_sensor))
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

    if group_stage == "area_sensors_menu":
        if user_input is not None:
            action = str(user_input.get("area_sensor_action") or "")
            if action == "back":
                flow._sensor_control_group_stage = "select_group"
                return await async_step_sensor_control_config(flow, None)
            if action == "add":
                flow._sensor_control_area_sensor_id = None
                flow._sensor_control_group_stage = "area_sensors_edit"
                return await async_step_sensor_control_config(flow, None)
            if action.startswith("edit:"):
                flow._sensor_control_area_sensor_id = action.split(":", 1)[1]
                flow._sensor_control_group_stage = "area_sensors_edit"
                return await async_step_sensor_control_config(flow, None)
            if action.startswith("delete:"):
                delete_id = action.split(":", 1)[1]
                device_area_sensors = [
                    item
                    for item in device_area_sensors
                    if str(item.get("source_id") or "") != delete_id
                ]
                area_sensors[dkey] = device_area_sensors
                sensor_control_options["area_sensors"] = area_sensors
                options[feature_id] = sensor_control_options
                flow.hass.config_entries.async_update_entry(  # noqa: SLF001
                    flow._config_entry,  # noqa: SLF001
                    options=options,
                )
                return await async_step_sensor_control_config(flow, None)

        area_sensor_options = [
            selector.SelectOptionDict(value="add", label="Add area sensor")
        ]
        for area_sensor in device_area_sensors:
            source_id = str(area_sensor.get("source_id") or "")
            label = str(area_sensor.get("label") or source_id or "Unnamed")
            if not source_id:
                continue
            area_sensor_options.append(
                selector.SelectOptionDict(
                    value=f"edit:{source_id}",
                    label=f"Edit: {label}",
                )
            )
            area_sensor_options.append(
                selector.SelectOptionDict(
                    value=f"delete:{source_id}",
                    label=f"Delete: {label}",
                )
            )
        area_sensor_options.append(
            selector.SelectOptionDict(value="back", label="Back to device groups")
        )

        menu_schema = vol.Schema(
            {
                vol.Required("area_sensor_action"): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=area_sensor_options,
                        multiple=False,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                )
            }
        )

        info_lines = [
            "Sensor Control",
            "",
            f"Configuring area sensors for device: `{selected_device_id}`",
            "",
            (
                "Area sensors provide localized temperature + humidity inputs "
                "for spike detection."
            ),
        ]
        if device_area_sensors:
            info_lines.extend(["", "Current area sensors:"])
            info_lines.extend(
                _describe_area_sensor(item) for item in device_area_sensors
            )
        else:
            info_lines.extend(["", "No area sensors configured yet."])

        return flow.async_show_form(
            step_id="feature_config",
            data_schema=menu_schema,
            description_placeholders={"info": "\n".join(info_lines)},
        )

    if group_stage == "area_sensors_edit":
        selected_area_sensor = _get_area_sensor_by_id(
            device_area_sensors,
            getattr(flow, "_sensor_control_area_sensor_id", None),
        )
        if user_input is not None:
            label = str(user_input.get("area_sensor_label") or "").strip()
            source_id = (
                str(selected_area_sensor.get("source_id"))
                if selected_area_sensor and selected_area_sensor.get("source_id")
                else _unique_area_sensor_id(label, device_area_sensors)
            )

            updated_area_sensor: dict[str, Any] = {
                "source_id": source_id,
                "label": label,
                "enabled": bool(user_input.get("area_sensor_enabled", True)),
                "temperature_entity": str(user_input.get("temperature_entity") or ""),
                "humidity_entity": str(user_input.get("humidity_entity") or ""),
                "spike_rise_percent": float(user_input.get("spike_rise_percent") or 0),
                "spike_window_minutes": int(
                    user_input.get("spike_window_minutes") or 1
                ),
                "check_interval_minutes": int(
                    user_input.get("check_interval_minutes") or 1
                ),
            }
            zone_id = str(user_input.get("zone_id") or "").strip()
            if zone_id:
                updated_area_sensor["zone_id"] = zone_id

            replaced = False
            new_area_sensors: list[dict[str, Any]] = []
            for item in device_area_sensors:
                if str(item.get("source_id") or "") == source_id:
                    new_area_sensors.append(updated_area_sensor)
                    replaced = True
                else:
                    new_area_sensors.append(item)
            if not replaced:
                new_area_sensors.append(updated_area_sensor)

            area_sensors[dkey] = new_area_sensors
            sensor_control_options["area_sensors"] = area_sensors
            options[feature_id] = sensor_control_options
            flow.hass.config_entries.async_update_entry(  # noqa: SLF001
                flow._config_entry,  # noqa: SLF001
                options=options,
            )
            flow._sensor_control_area_sensor_id = None
            flow._sensor_control_group_stage = "area_sensors_menu"
            return await async_step_sensor_control_config(flow, None)

        label_default = (
            str(selected_area_sensor.get("label"))
            if selected_area_sensor and selected_area_sensor.get("label")
            else "Bathroom"
        )
        zone_default = (
            str(selected_area_sensor.get("zone_id"))
            if selected_area_sensor and selected_area_sensor.get("zone_id")
            else ""
        )
        temp_default = (
            str(selected_area_sensor.get("temperature_entity"))
            if selected_area_sensor and selected_area_sensor.get("temperature_entity")
            else None
        )
        humidity_default = (
            str(selected_area_sensor.get("humidity_entity"))
            if selected_area_sensor and selected_area_sensor.get("humidity_entity")
            else None
        )
        area_sensor_selector = selector.EntitySelector(
            selector.EntitySelectorConfig(domain=["sensor"])
        )
        temp_key = (
            vol.Required("temperature_entity")
            if temp_default is None
            else vol.Required("temperature_entity", default=temp_default)
        )
        humidity_key = (
            vol.Required("humidity_entity")
            if humidity_default is None
            else vol.Required("humidity_entity", default=humidity_default)
        )
        zone_key = (
            vol.Optional("zone_id")
            if not zone_default
            else vol.Optional("zone_id", default=zone_default)
        )

        schema = vol.Schema(
            {
                vol.Required("area_sensor_label", default=label_default): vol.All(
                    str, vol.Length(min=1)
                ),
                vol.Required(
                    "area_sensor_enabled",
                    default=bool(
                        selected_area_sensor.get("enabled", True)
                        if selected_area_sensor
                        else True
                    ),
                ): bool,
                zone_key: str,
                temp_key: area_sensor_selector,
                humidity_key: area_sensor_selector,
                vol.Required(
                    "spike_rise_percent",
                    default=float(
                        selected_area_sensor.get("spike_rise_percent", 10.0)
                        if selected_area_sensor
                        else 10.0
                    ),
                ): vol.All(vol.Coerce(float), vol.Range(min=1, max=100)),
                vol.Required(
                    "spike_window_minutes",
                    default=int(
                        selected_area_sensor.get("spike_window_minutes", 3)
                        if selected_area_sensor
                        else 3
                    ),
                ): vol.All(vol.Coerce(int), vol.Range(min=1, max=60)),
                vol.Required(
                    "check_interval_minutes",
                    default=int(
                        selected_area_sensor.get("check_interval_minutes", 1)
                        if selected_area_sensor
                        else 1
                    ),
                ): vol.All(vol.Coerce(int), vol.Range(min=1, max=30)),
            }
        )

        info_text = (
            "🧭 **Sensor Control**\n\n"
            f"Configuring device: `{selected_device_id}`\n\n"
            "Define one local area sensor using temperature + humidity inputs. "
            "This will later drive derived absolute humidity and spike detection."
        )
        return flow.async_show_form(
            step_id="feature_config",
            data_schema=schema,
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

    info_suffix_translations = (
        await _async_load_sensor_control_info_suffix_translations(flow.hass)
    )

    def _t(key: str, default: str) -> str:
        val = info_suffix_translations.get(key)
        return val if isinstance(val, str) and val else default

    # Per-group schemas via the per-device-type handler
    try:
        schema, info_suffix = handler.build_group_schema(
            group_stage,
            device_sources,
            device_abs_inputs,
            kind_options,
            kind_options_with_none,
            sensor_selector,
            translate=_t,
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
