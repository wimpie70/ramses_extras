from __future__ import annotations

import asyncio
import json
import logging
import re
from copy import deepcopy
from pathlib import Path
from typing import Any

import voluptuous as vol
from homeassistant.helpers import selector

from ...const import AVAILABLE_FEATURES, DOMAIN
from ...framework.helpers.config.migration import get_migrated_feature_section
from ...framework.helpers.config.model import (
    CONFIG_DEVICES_KEY,
    SENSOR_CONTROL_ABS_HUMIDITY_INPUTS_KEY,
    SENSOR_CONTROL_AREA_SENSORS_KEY,
    SENSOR_CONTROL_SOURCES_KEY,
    get_zones_for_fan,
    legacy_device_key,
    normalize_device_id,
    set_fan_section,
    set_feature_section,
)
from ...framework.helpers.config.validation import (
    FEATURE_SENSOR_CONTROL,
    FEATURE_ZONES,
)
from ...framework.helpers.device.filter import DeviceFilter
from .const import SUPPORTED_METRICS
from .device_types import DEVICE_TYPE_HANDLERS
from .zones_yaml import (
    export_zones_to_yaml,
    merge_zones_config,
    parse_zones_yaml,
)

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


def _build_legacy_sensor_control_section(
    sensor_control_section: dict[str, Any],
) -> dict[str, Any]:
    legacy_section: dict[str, dict[str, Any]] = {
        SENSOR_CONTROL_SOURCES_KEY: {},
        SENSOR_CONTROL_ABS_HUMIDITY_INPUTS_KEY: {},
        SENSOR_CONTROL_AREA_SENSORS_KEY: {},
    }
    devices = sensor_control_section.get(CONFIG_DEVICES_KEY)
    if not isinstance(devices, dict):
        return {}

    for device_id, device_section in devices.items():
        if not isinstance(device_section, dict):
            continue
        device_key = legacy_device_key(normalize_device_id(str(device_id)))
        for section_key in (
            SENSOR_CONTROL_SOURCES_KEY,
            SENSOR_CONTROL_ABS_HUMIDITY_INPUTS_KEY,
            SENSOR_CONTROL_AREA_SENSORS_KEY,
        ):
            value = device_section.get(section_key)
            if value is not None:
                legacy_section[section_key][device_key] = deepcopy(value)

    return {key: value for key, value in legacy_section.items() if value}


def _persist_sensor_control_section(
    flow: Any,
    options: dict[str, Any],
    sensor_control_section: dict[str, Any],
) -> None:
    canonical_section = deepcopy(sensor_control_section)
    options[FEATURE_SENSOR_CONTROL] = _build_legacy_sensor_control_section(
        canonical_section
    )
    set_feature_section(options, FEATURE_SENSOR_CONTROL, canonical_section)
    flow.hass.config_entries.async_update_entry(  # noqa: SLF001
        flow._config_entry,  # noqa: SLF001
        options=options,
    )


def _persist_zones_section(
    flow: Any,
    options: dict[str, Any],
    zones_section: dict[str, Any],
) -> None:
    """Persist zones section to config options using canonical structure."""
    # Create a writable copy of options to avoid mappingproxy error
    options = dict(options)

    # Use set_fan_section to store zones in the canonical structure
    # where get_zones_for_fan expects to find them

    # Get the selected device ID from the flow
    selected_device_id = getattr(flow, "_sensor_control_selected_device", None)
    if selected_device_id:
        # Store zones using the canonical structure in the options dict
        set_fan_section(options, selected_device_id, zones_section.get("zones", []))

    flow.hass.config_entries.async_update_entry(  # noqa: SLF001
        flow._config_entry,  # noqa: SLF001
        options=options,
    )


def _describe_area_sensor(area_sensor: dict[str, Any]) -> str:
    label = str(area_sensor.get("label") or area_sensor.get("source_id") or "Unnamed")
    temp_entity = str(area_sensor.get("temperature_entity") or "missing")
    humidity_entity = str(area_sensor.get("humidity_entity") or "missing")
    spike_rise = area_sensor.get("spike_rise_percent")
    spike_window = area_sensor.get("spike_window_minutes")
    trigger_on_high_humidity = bool(area_sensor.get("trigger_on_high_humidity", False))
    enabled = bool(area_sensor.get("enabled", True))
    area_co2_enabled = bool(area_sensor.get("area_co2_enabled", False))
    co2_entity = str(area_sensor.get("co2_entity") or "missing")
    co2_threshold_entity = str(area_sensor.get("co2_threshold_entity") or "").strip()
    co2_threshold = area_sensor.get("co2_threshold", 1000)

    details = [
        f"temp: {temp_entity}",
        f"humidity: {humidity_entity}",
    ]
    if spike_rise is not None and spike_window is not None:
        details.append(f"spike: {spike_rise}%/{spike_window}m")
    if trigger_on_high_humidity:
        details.append("max RH trigger")
    if area_co2_enabled:
        threshold_desc = f"{co2_threshold}ppm"
        if co2_threshold_entity:
            threshold_desc = (
                f"entity {co2_threshold_entity} / fallback {co2_threshold}ppm"
            )
        details.append(f"CO2: {co2_entity} (threshold: {threshold_desc})")
    details.append("enabled" if enabled else "disabled")

    zone_id = str(area_sensor.get("zone_id") or "").strip()
    if zone_id:
        details.append(f"zone: {zone_id}")

    return f"- area sensor {label}: " + "; ".join(details)


def _validate_area_sensor_entries(area_sensors: Any) -> list[dict[str, Any]]:
    if not isinstance(area_sensors, list):
        return []
    return [item for item in area_sensors if isinstance(item, dict)]


def _unique_zone_id(label: str, existing_zones: list[dict[str, Any]]) -> str:
    """Generate a unique zone_id from a label."""
    base = re.sub(r"[^a-z0-9_]+", "_", label.strip().lower())
    base = base.strip("_")
    if not base:
        base = "zone"

    existing_ids = {
        str(item.get("zone_id"))
        for item in existing_zones
        if isinstance(item, dict) and item.get("zone_id")
    }
    if base not in existing_ids:
        return base

    suffix = 2
    while f"{base}_{suffix}" in existing_ids:
        suffix += 1
    return f"{base}_{suffix}"


def _get_zone_by_id(
    zones: list[dict[str, Any]], zone_id: str | None
) -> dict[str, Any] | None:
    """Find a zone by its zone_id."""
    if not zone_id:
        return None
    for item in zones:
        if isinstance(item, dict) and str(item.get("zone_id") or "") == zone_id:
            return item
    return None


def _describe_zone(zone: dict[str, Any]) -> str:
    """Generate a description string for a zone."""
    zone_id = str(zone.get("zone_id") or "Unnamed")
    zone_type = str(zone.get("type") or "unknown")
    enabled = bool(zone.get("enabled", True))

    details = [f"type: {zone_type}"]

    if zone_type == "orcon_native":
        native_id = str(zone.get("native_zone_id") or "")
        if native_id:
            details.append(f"native ID: {native_id}")
    elif zone_type == "paired_valves":
        inlet_entity = str(zone.get("inlet_valve_entity") or "")
        outlet_entity = str(zone.get("outlet_valve_entity") or "")
        if inlet_entity:
            details.append(f"inlet: {inlet_entity}")
        if outlet_entity:
            details.append(f"outlet: {outlet_entity}")
    elif zone_type in ("custom_valve", "shelly_2pm_gen3"):
        open_entity = str(zone.get("open_entity") or "")
        close_entity = str(zone.get("close_entity") or "")
        if open_entity:
            details.append(f"open: {open_entity}")
        if close_entity:
            details.append(f"close: {close_entity}")

    details.append("enabled" if enabled else "disabled")

    return f"- zone {zone_id}: " + "; ".join(details)


def _validate_zone_entries(zones: Any) -> list[dict[str, Any]]:
    if not isinstance(zones, list):
        return []
    return [item for item in zones if isinstance(item, dict)]


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
    _LOGGER.debug(
        "async_step_sensor_control_config called with user_input=%s", user_input
    )
    feature_id = FEATURE_SENSOR_CONTROL
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
            sensor_control_section = get_migrated_feature_section(
                options,
                "sensor_control",
            )
            devices = sensor_control_section.get(CONFIG_DEVICES_KEY)
            if not isinstance(devices, dict):
                devices = {}

            device_keys = set(devices.keys())

            if device_keys:
                overview_lines.append("Existing Sensor Control Mappings\n")
                for device_key in sorted(device_keys):
                    device_section = devices.get(device_key) or {}
                    if not isinstance(device_section, dict):
                        continue
                    device_sources = (
                        device_section.get(SENSOR_CONTROL_SOURCES_KEY) or {}
                    )
                    device_abs_inputs = (
                        device_section.get(SENSOR_CONTROL_ABS_HUMIDITY_INPUTS_KEY) or {}
                    )
                    area_sensor_cfgs = (
                        device_section.get(SENSOR_CONTROL_AREA_SENSORS_KEY) or []
                    )
                    if not isinstance(device_sources, dict):
                        device_sources = {}
                    if not isinstance(device_abs_inputs, dict):
                        device_abs_inputs = {}
                    if not isinstance(area_sensor_cfgs, list):
                        area_sensor_cfgs = []
                    device_id = device_key

                    device_lines: list[str] = []

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
                                        device_abs_parts.append(
                                            f"temp: external  {ent}"
                                        )
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
                        if not area_sensor_cfgs:
                            continue

                    for area_sensor in area_sensor_cfgs:
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
    sensor_control_section = get_migrated_feature_section(options, feature_id)
    devices_config = sensor_control_section.get(CONFIG_DEVICES_KEY)
    if not isinstance(devices_config, dict):
        devices_config = {}
    norm_device_id = normalize_device_id(selected_device_id)
    device_section = devices_config.get(norm_device_id)
    if not isinstance(device_section, dict):
        device_section = {}

    device_sources = dict(device_section.get(SENSOR_CONTROL_SOURCES_KEY) or {})
    device_abs_inputs = dict(
        device_section.get(SENSOR_CONTROL_ABS_HUMIDITY_INPUTS_KEY) or {}
    )
    device_area_sensors = _validate_area_sensor_entries(
        device_section.get(SENSOR_CONTROL_AREA_SENSORS_KEY)
    )

    # Resolve device type and select an appropriate handler. For now we support
    # FAN and CO2 explicitly; other types will fall back to the FAN handler so
    # they at least get a working UI.
    raw_device_type = _get_device_type(flow, selected_device_id) or "FAN"
    device_type = str(raw_device_type).upper()
    handler = DEVICE_TYPE_HANDLERS.get(device_type) or DEVICE_TYPE_HANDLERS["FAN"]

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
            if action == "area_sensors":
                flow._sensor_control_group_stage = "area_sensors_menu"
            elif action == "zones":
                flow._sensor_control_group_stage = "zones_menu"
            else:
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
                device_section = deepcopy(devices_config.get(norm_device_id) or {})
                device_section[SENSOR_CONTROL_SOURCES_KEY] = device_sources
                device_section[SENSOR_CONTROL_ABS_HUMIDITY_INPUTS_KEY] = (
                    device_abs_inputs
                )
                device_section[SENSOR_CONTROL_AREA_SENSORS_KEY] = device_area_sensors
                devices_config[norm_device_id] = device_section
                sensor_control_section[CONFIG_DEVICES_KEY] = devices_config
                _persist_sensor_control_section(
                    flow,
                    options,
                    sensor_control_section,
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
        info_suffix_translations = (
            await _async_load_sensor_control_info_suffix_translations(flow.hass)
        )

        def _t_area(key: str, default: str) -> str:
            val = info_suffix_translations.get(key)
            return val if isinstance(val, str) and val else default

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
                "trigger_on_high_humidity": bool(
                    user_input.get("trigger_on_high_humidity", False)
                ),
                "spike_rise_percent": float(user_input.get("spike_rise_percent") or 0),
                "spike_window_minutes": int(
                    user_input.get("spike_window_minutes") or 1
                ),
                "area_co2_enabled": bool(user_input.get("area_co2_enabled", False)),
                "co2_entity": str(user_input.get("co2_entity") or ""),
                "co2_threshold_entity": str(
                    user_input.get("co2_threshold_entity") or ""
                ).strip(),
                "co2_threshold": int(user_input.get("co2_threshold") or 1000),
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

            device_section = deepcopy(devices_config.get(norm_device_id) or {})
            device_section[SENSOR_CONTROL_SOURCES_KEY] = device_sources
            device_section[SENSOR_CONTROL_ABS_HUMIDITY_INPUTS_KEY] = device_abs_inputs
            device_section[SENSOR_CONTROL_AREA_SENSORS_KEY] = new_area_sensors
            devices_config[norm_device_id] = device_section
            sensor_control_section[CONFIG_DEVICES_KEY] = devices_config
            _persist_sensor_control_section(
                flow,
                options,
                sensor_control_section,
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
        co2_default = (
            str(selected_area_sensor.get("co2_entity"))
            if selected_area_sensor and selected_area_sensor.get("co2_entity")
            else None
        )
        co2_threshold_entity_default = (
            str(selected_area_sensor.get("co2_threshold_entity"))
            if selected_area_sensor and selected_area_sensor.get("co2_threshold_entity")
            else None
        )
        area_sensor_selector = selector.EntitySelector(
            selector.EntitySelectorConfig(domain=["sensor", "number", "input_number"])
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
        co2_key = (
            vol.Optional("co2_entity")
            if co2_default is None
            else vol.Optional("co2_entity", default=co2_default)
        )
        co2_threshold_entity_key = (
            vol.Optional("co2_threshold_entity")
            if co2_threshold_entity_default is None
            else vol.Optional(
                "co2_threshold_entity",
                default=co2_threshold_entity_default,
            )
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
                    "trigger_on_high_humidity",
                    default=bool(
                        selected_area_sensor.get("trigger_on_high_humidity", False)
                        if selected_area_sensor
                        else False
                    ),
                ): bool,
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
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=1,
                        max=60,
                        step=1,
                        mode=selector.NumberSelectorMode.BOX,
                    )
                ),
                vol.Required(
                    "area_co2_enabled",
                    default=bool(
                        selected_area_sensor.get("area_co2_enabled", False)
                        if selected_area_sensor
                        else False
                    ),
                ): bool,
                co2_key: area_sensor_selector,
                co2_threshold_entity_key: area_sensor_selector,
                vol.Required(
                    "co2_threshold",
                    default=int(
                        selected_area_sensor.get("co2_threshold", 1000)
                        if selected_area_sensor
                        else 1000
                    ),
                ): vol.All(vol.Coerce(int), vol.Range(min=400, max=2000)),
            }
        )

        info_text = (
            "🧭 **Sensor Control**\n\n"
            f"Configuring device: `{selected_device_id}`\n\n"
            f"{
                _t_area(
                    'area_sensors_edit',
                    'Define one local area sensor using temperature + humidity and/or '
                    'CO2 inputs. Humidity sensors drive spike detection. CO2 sensors '
                    'drive CO2 control. Both can share the same zone_id.',
                )
            } \
            \n\n"
            f"{
                _t_area(
                    'area_sensors_entity_note',
                    'Temperature and humidity entities should come from '
                    'the same device. Enable area_sensor_enabled '
                    'for humidity/temp, area_co2_enabled for CO2. '
                    'Multiple area sensors can share the same zone_id.',
                )
            }"
        )
        return flow.async_show_form(
            step_id="feature_config",
            data_schema=schema,
            description_placeholders={"info": info_text},
        )

    # ------------------------------------------------------------------
    # Zones menu: list zones for this FAN and allow add/edit/delete
    # ------------------------------------------------------------------
    if group_stage == "zones_menu":
        options = flow.hass.data[DOMAIN]["config_entry"].options
        zones_section = get_migrated_feature_section(options, FEATURE_ZONES)
        fan_zones = get_zones_for_fan(zones_section, selected_device_id)

        if user_input is not None:
            zones_action: str | None = user_input.get("action")

            if zones_action == "add":
                flow._sensor_control_editing_zone_id = None
                flow._sensor_control_group_stage = "zones_edit"
                return await async_step_sensor_control_config(flow, None)

            if zones_action == "edit":
                selected_zone_id: str | None = user_input.get("zone_id")
                if selected_zone_id:
                    flow._sensor_control_editing_zone_id = selected_zone_id
                    flow._sensor_control_group_stage = "zones_edit"
                    return await async_step_sensor_control_config(flow, None)

            if zones_action == "delete":
                delete_zone_id: str | None = user_input.get("zone_id")
                if delete_zone_id:
                    # Use canonical structure for delete
                    from ...framework.helpers.config.model import set_fan_section

                    existing_zones = get_zones_for_fan(
                        zones_section, selected_device_id
                    )
                    new_zones = [
                        z for z in existing_zones if z.get("zone_id") != delete_zone_id
                    ]
                    set_fan_section(zones_section, selected_device_id, new_zones)
                    # Create writable copy to avoid mappingproxy error
                    options = dict(options)
                    options[FEATURE_ZONES] = zones_section
                    _persist_zones_section(flow, options, zones_section)
                return await async_step_sensor_control_config(flow, None)

            if zones_action == "back":
                flow._sensor_control_group_stage = "select_group"
                return await async_step_sensor_control_config(flow, None)

        # Build zone list for display
        zone_descriptions = []
        zone_select_options = []
        for zone in fan_zones:
            zone_id = str(zone.get("zone_id") or "unnamed")
            zone_descriptions.append(_describe_zone(zone))
            zone_select_options.append(
                selector.SelectOptionDict(value=zone_id, label=f"Zone: {zone_id}")
            )

        zones_info = (
            "\n".join(zone_descriptions)
            if zone_descriptions
            else "No zones configured."
        )

        schema = vol.Schema(
            {
                vol.Required("action"): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            selector.SelectOptionDict(value="add", label="Add zone"),
                            selector.SelectOptionDict(value="edit", label="Edit zone"),
                            selector.SelectOptionDict(
                                value="delete", label="Delete zone"
                            ),
                            selector.SelectOptionDict(value="back", label="Back"),
                        ],
                        mode="list",
                    )
                ),
                vol.Optional("zone_id"): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=zone_select_options,
                        mode="dropdown",
                    )
                ),
            }
        )

        info_text = (
            "🧭 **Zone Configuration**\n\n"
            f"Configuring zones for FAN: `{selected_device_id}`\n\n"
            f"**Existing zones:**\n{zones_info}"
        )

        return flow.async_show_form(
            step_id="feature_config",
            data_schema=schema,
            description_placeholders={"info": info_text},
        )

    # ------------------------------------------------------------------
    # Zones edit: add or edit a specific zone
    # ------------------------------------------------------------------
    if group_stage == "zones_edit":
        options = flow.hass.data[DOMAIN]["config_entry"].options
        zones_section = get_migrated_feature_section(options, FEATURE_ZONES)
        fan_zones = get_zones_for_fan(zones_section, selected_device_id)

        editing_zone_id = getattr(flow, "_sensor_control_editing_zone_id", None)
        existing_zone = None
        if editing_zone_id:
            existing_zone = _get_zone_by_id(fan_zones, editing_zone_id)

        errors: dict[str, str] = {}

        # Set defaults for form fields
        zone_id_default = existing_zone.get("zone_id") if existing_zone else ""
        zone_type_default = (
            existing_zone.get("type") if existing_zone else "custom_valve"
        )
        enabled_default = existing_zone.get("enabled", True) if existing_zone else True

        if user_input is not None:
            zone_id = str(user_input.get("zone_id") or "").strip()
            zone_type = str(user_input.get("type") or "custom_valve")
            enabled = bool(user_input.get("enabled", True))

            if zone_type == "paired_valves":
                inlet_entity = user_input.get("inlet_valve_entity")
                outlet_entity = user_input.get("outlet_valve_entity")
                min_position = user_input.get("min_position", 0)
                max_position = user_input.get("max_position", 100)

                if inlet_entity:
                    # Validate entities exist (basic validation)
                    str(inlet_entity).strip()
                    str(outlet_entity).strip()
                    int(min_position)
                    int(max_position)

            # Validate unique zone_id within this FAN
            if not zone_id:
                errors["zone_id"] = "Zone ID is required"
            elif existing_zone is None or existing_zone.get("zone_id") != zone_id:
                # Check for duplicates
                if _get_zone_by_id(fan_zones, zone_id):
                    errors["zone_id"] = "Zone ID already exists for this FAN"

            if not errors:
                # Build zone entry and store for confirmation step
                zone_entry: dict[str, Any] = {
                    "zone_id": zone_id,
                    "type": zone_type,
                    "enabled": enabled,
                }

                if zone_type == "paired_valves":
                    inlet_entity = user_input.get("inlet_valve_entity")
                    outlet_entity = user_input.get("outlet_valve_entity")
                    min_position = user_input.get("min_position", 0)
                    max_position = user_input.get("max_position", 100)

                    if inlet_entity:
                        zone_entry["inlet_valve_entity"] = str(inlet_entity).strip()
                    if outlet_entity:
                        zone_entry["outlet_valve_entity"] = str(outlet_entity).strip()
                    zone_entry["min_position"] = int(min_position)
                    zone_entry["max_position"] = int(max_position)

                # Store pending zone for confirmation step
                flow._sensor_control_pending_zone = zone_entry
                flow._sensor_control_pending_zone_editing_id = editing_zone_id
                flow._sensor_control_group_stage = "zones_confirm"
                return await async_step_sensor_control_config(flow, None)

        type_options = [
            selector.SelectOptionDict(
                value="paired_valves", label="Paired Valves (Inlet+Outlet)"
            ),
        ]

        schema_fields: dict[Any, Any] = {
            vol.Required("zone_id", default=zone_id_default): selector.TextSelector(),
            vol.Required("type", default=zone_type_default): selector.SelectSelector(
                selector.SelectSelectorConfig(options=type_options, mode="dropdown")
            ),
            vol.Required(
                "enabled", default=enabled_default
            ): selector.BooleanSelector(),
        }

        # Build schema fields - only paired_valves with inlet/outlet
        cover_selector = selector.EntitySelector(
            selector.EntitySelectorConfig(domain=["cover"])
        )
        inlet_default = existing_zone.get("inlet_valve_entity") if existing_zone else ""
        outlet_default = (
            existing_zone.get("outlet_valve_entity") if existing_zone else ""
        )
        min_default = existing_zone.get("min_position", 0) if existing_zone else 0
        max_default = existing_zone.get("max_position", 100) if existing_zone else 100

        schema_fields[vol.Optional("inlet_valve_entity", default=inlet_default)] = (
            cover_selector
        )
        schema_fields[vol.Optional("outlet_valve_entity", default=outlet_default)] = (
            cover_selector
        )
        schema_fields[vol.Optional("min_position", default=min_default)] = (
            selector.NumberSelector(
                selector.NumberSelectorConfig(min=0, max=100, step=1)
            )
        )
        schema_fields[vol.Optional("max_position", default=max_default)] = (
            selector.NumberSelector(
                selector.NumberSelectorConfig(min=0, max=100, step=1)
            )
        )
        schema = vol.Schema(schema_fields)

        info_text = (
            f"{'Edit' if existing_zone else 'Add'} Zone\n\n"
            f"Configure a zone for FAN: `{selected_device_id}`\n\n"
            "Zone ID must be unique within this FAN.\n"
            "Select the zone type and configure the appropriate entities."
        )

        if errors:
            return flow.async_show_form(
                step_id="feature_config",
                data_schema=schema,
                errors=errors,
                description_placeholders={"info": info_text},
            )

        return flow.async_show_form(
            step_id="feature_config",
            data_schema=schema,
            description_placeholders={"info": info_text},
        )

    # ------------------------------------------------------------------
    # Zones confirm: confirm zone before saving
    # ------------------------------------------------------------------
    if group_stage == "zones_confirm":
        # Get pending zone data
        zone_entry = getattr(flow, "_sensor_control_pending_zone", None) or {}
        editing_zone_id = getattr(flow, "_sensor_control_pending_zone_editing_id", None)

        if not zone_entry:
            _LOGGER.error("No pending zone data in zones_confirm")
            flow._sensor_control_group_stage = "zones_menu"
            return await async_step_sensor_control_config(flow, None)

        if user_input is not None:
            confirm_action = user_input.get("confirm")

            if confirm_action == "save":
                # Actually save the zone
                options = flow.hass.data[DOMAIN]["config_entry"].options
                zones_section = get_migrated_feature_section(options, FEATURE_ZONES)

                # Get existing zones for this fan
                existing_zones = get_zones_for_fan(zones_section, selected_device_id)

                # Remove old version if editing
                new_zones = [
                    z for z in existing_zones if z.get("zone_id") != editing_zone_id
                ]
                new_zones.append(zone_entry)

                # Store using set_fan_section
                from ...framework.helpers.config.model import set_fan_section

                set_fan_section(zones_section, selected_device_id, new_zones)

                # Update options with modified section before persisting
                options = dict(options)  # Create a writable copy
                options[FEATURE_ZONES] = zones_section
                _persist_zones_section(flow, options, zones_section)

                # Clear pending zone
                flow._sensor_control_pending_zone = None
                flow._sensor_control_pending_zone_editing_id = None

                # Refresh config entry reference
                flow.hass.data[DOMAIN]["config_entry"] = (
                    flow.hass.config_entries.async_get_entry(
                        flow._config_entry.entry_id  # noqa: SLF001
                    )
                )

                flow._sensor_control_group_stage = "zones_menu"
                return await async_step_sensor_control_config(flow, None)

            if confirm_action == "edit":
                # Go back to edit
                flow._sensor_control_group_stage = "zones_edit"
                return await async_step_sensor_control_config(flow, None)

            if confirm_action == "cancel":
                # Cancel and go back to menu
                flow._sensor_control_pending_zone = None
                flow._sensor_control_pending_zone_editing_id = None
                flow._sensor_control_group_stage = "zones_menu"
                return await async_step_sensor_control_config(flow, None)

        # Build confirmation display
        zone_info_lines = ["**Zone Details:**"]
        for key, value in zone_entry.items():
            zone_info_lines.append(f"- {key}: `{value}`")
        zone_info = "\n".join(zone_info_lines)

        schema = vol.Schema(
            {
                vol.Required("confirm"): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            selector.SelectOptionDict(value="save", label="Save zone"),
                            selector.SelectOptionDict(value="edit", label="Edit again"),
                            selector.SelectOptionDict(value="cancel", label="Cancel"),
                        ],
                        mode="list",
                    )
                ),
            }
        )

        info_text = (
            "🧭 **Confirm Zone Configuration**\n\n"
            f"FAN: `{selected_device_id}`\n\n"
            f"{zone_info}\n\n"
            "Review the zone details above before saving."
        )

        return flow.async_show_form(
            step_id="feature_config",
            data_schema=schema,
            description_placeholders={"info": info_text},
        )

    # ------------------------------------------------------------------
    # Zones export: export current zones to YAML
    # ------------------------------------------------------------------
    if group_stage == "zones_export":
        options = flow.hass.data[DOMAIN]["config_entry"].options
        zones_section = get_migrated_feature_section(options, FEATURE_ZONES)
        fan_zones = get_zones_for_fan(zones_section, selected_device_id)

        if user_input is not None:
            export_action: str | None = user_input.get("action")
            if export_action == "back":
                flow._sensor_control_group_stage = "zones_menu"
                return await async_step_sensor_control_config(flow, None)

        # Generate YAML export
        normalized_fan_id = normalize_device_id(selected_device_id)
        yaml_content = export_zones_to_yaml(fan_zones, normalized_fan_id)

        schema = vol.Schema(
            {
                vol.Optional("yaml_preview"): selector.TextSelector(
                    selector.TextSelectorConfig(multiline=True)
                ),
                vol.Required("action"): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            selector.SelectOptionDict(
                                value="back", label="Back to zones menu"
                            ),
                        ],
                        mode="list",
                    )
                ),
            }
        )

        info_text = (
            "🧭 **Export Zones to YAML**\n\n"
            f"FAN: `{selected_device_id}`\n\n"
            "Copy the YAML below to save your zone configuration:\n\n"
            f"```yaml\n{yaml_content}\n```"
        )

        return flow.async_show_form(
            step_id="feature_config",
            data_schema=schema,
            description_placeholders={"info": info_text},
        )

    # ------------------------------------------------------------------
    # Zones import: import zones from YAML
    # ------------------------------------------------------------------
    if group_stage == "zones_import":
        options = flow.hass.data[DOMAIN]["config_entry"].options
        zones_section = get_migrated_feature_section(options, FEATURE_ZONES)

        import_errors: dict[str, str] = {}

        if user_input is not None:
            import_action: str | None = user_input.get("action")

            if import_action == "back":
                flow._sensor_control_group_stage = "zones_menu"
                return await async_step_sensor_control_config(flow, None)

            if import_action == "import":
                yaml_content = user_input.get("yaml_content", "")
                overwrite = user_input.get("overwrite_existing", False)

                if not yaml_content or not yaml_content.strip():
                    import_errors["yaml_content"] = "YAML content is required"
                else:
                    try:
                        parsed = parse_zones_yaml(yaml_content)
                        imported_zones = parsed.get("zones", [])

                        if not imported_zones:
                            import_errors["yaml_content"] = "No zones found in YAML"
                        else:
                            # Merge with existing zones
                            existing_zones = _validate_zone_entries(
                                zones_section.get("zones")
                            )
                            normalized_fan_id = normalize_device_id(selected_device_id)

                            merged_zones = merge_zones_config(
                                existing_zones,
                                imported_zones,
                                normalized_fan_id,
                                overwrite_existing=overwrite,
                            )

                            zones_section["zones"] = merged_zones
                            # Create writable copy to avoid mappingproxy error
                            options = dict(options)
                            options[FEATURE_ZONES] = zones_section
                            _persist_zones_section(flow, options, zones_section)

                            # Return to zones menu after successful import
                            flow._sensor_control_group_stage = "zones_menu"
                            return await async_step_sensor_control_config(flow, None)

                    except ValueError as e:
                        import_errors["yaml_content"] = str(e)

        schema = vol.Schema(
            {
                vol.Required("yaml_content"): selector.TextSelector(
                    selector.TextSelectorConfig(multiline=True)
                ),
                vol.Required(
                    "overwrite_existing", default=False
                ): selector.BooleanSelector(),
                vol.Required("action"): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            selector.SelectOptionDict(
                                value="import", label="Import zones"
                            ),
                            selector.SelectOptionDict(
                                value="back", label="Cancel / Back"
                            ),
                        ],
                        mode="list",
                    )
                ),
            }
        )

        info_text = (
            "🧭 **Import Zones from YAML**\n\n"
            f"FAN: `{selected_device_id}`\n\n"
            "Paste your YAML zone configuration below.\n\n"
            "The import will validate the YAML structure "
            "and merge zones with existing ones.\n"
            "Enable 'Overwrite existing' to replace zones with the same zone_id."
        )

        if import_errors:
            return flow.async_show_form(
                step_id="feature_config",
                data_schema=schema,
                errors=import_errors,
                description_placeholders={"info": info_text},
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
        device_section = deepcopy(devices_config.get(norm_device_id) or {})
        device_section[SENSOR_CONTROL_SOURCES_KEY] = device_sources
        device_section[SENSOR_CONTROL_ABS_HUMIDITY_INPUTS_KEY] = device_abs_inputs
        if device_area_sensors or SENSOR_CONTROL_AREA_SENSORS_KEY in device_section:
            device_section[SENSOR_CONTROL_AREA_SENSORS_KEY] = device_area_sensors
        devices_config[norm_device_id] = device_section
        sensor_control_section[CONFIG_DEVICES_KEY] = devices_config

        _LOGGER.debug(
            "Saving sensor_control overrides for %s (group=%s): %s",
            selected_device_id,
            group_stage,
            sensor_control_section,
        )

        # async_update_entry is not a coroutine in this HA version; it returns a
        # bool and must not be awaited.
        _persist_sensor_control_section(
            flow,
            options,
            sensor_control_section,
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
        selector.EntitySelectorConfig(domain=["sensor", "number", "input_number"])
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
