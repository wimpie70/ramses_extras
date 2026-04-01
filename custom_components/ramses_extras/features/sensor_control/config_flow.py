from __future__ import annotations

import asyncio
import json
import logging
import re
from copy import deepcopy
from pathlib import Path
from typing import Any

import voluptuous as vol
from homeassistant.core import HomeAssistant
from homeassistant.helpers import selector

from ...const import AVAILABLE_FEATURES, DOMAIN
from ...framework.helpers.config.migration import get_migrated_feature_section
from ...framework.helpers.config.model import (
    CONFIG_DEVICES_KEY,
    SENSOR_CONTROL_ABS_HUMIDITY_INPUTS_KEY,
    SENSOR_CONTROL_AREA_SENSORS_KEY,
    SENSOR_CONTROL_SOURCES_KEY,
    get_remote_binding_rems,
    get_zones_for_fan,
    legacy_device_key,
    normalize_device_id,
    set_fan_section,
    set_feature_section,
)
from ...framework.helpers.config.validation import (
    FEATURE_REMOTE_BINDING,
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


def _persist_remote_binding_section(
    flow: Any,
    options: dict[str, Any],
    remote_binding_section: dict[str, Any],
) -> None:
    canonical_section = deepcopy(remote_binding_section)

    options = dict(options)
    options[FEATURE_REMOTE_BINDING] = canonical_section
    set_feature_section(options, FEATURE_REMOTE_BINDING, canonical_section)
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
    area_id = str(
        area_sensor.get("area_id") or area_sensor.get("source_id") or "Unnamed"
    )
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

    return f"- area sensor {area_id}: " + "; ".join(details)


def _describe_remote_binding(rem: dict[str, Any]) -> str:
    rem_id = str(rem.get("rem_id") or "missing")
    role = str(rem.get("role") or "unknown")
    enabled = bool(rem.get("enabled", True))
    zone_id = str(rem.get("zone_id") or "").strip()
    area_id = str(rem.get("area_id") or "").strip()

    parts = [
        f"rem_id: {rem_id}",
        f"role: {role}",
        "enabled" if enabled else "disabled",
    ]
    if zone_id:
        parts.append(f"zone_id: {zone_id}")
    if area_id:
        parts.append(f"area_id: {area_id}")
    return "- " + "; ".join(parts)


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
                overview_lines.append("Existing FAN Configuration Mappings\n")
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

        info_text += "FAN Configuration\n\n"
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
    device_section = devices_config.get(norm_device_id) or devices_config.get(
        selected_device_id
    )
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
            action = str(user_input.get("action") or "")
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
            elif action == "rems":
                flow._sensor_control_group_stage = "rems_menu"
            else:
                flow._sensor_control_group_stage = action
            return await async_step_sensor_control_config(flow, None)

        group_options = handler.get_group_options(selected_device_id)

        menu_schema = vol.Schema(
            {
                vol.Required("action"): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=group_options,
                        multiple=False,
                        mode="list",
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
            "FAN Configuration\n\n"
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
            action = str(user_input.get("action") or "")

            if action == "add":
                flow._sensor_control_area_sensor_id = None
                flow._sensor_control_group_stage = "area_sensors_edit"
                return await async_step_sensor_control_config(flow, None)

            if action == "edit":
                selected_area_id: str | None = user_input.get("area_id")
                if selected_area_id:
                    flow._sensor_control_area_sensor_id = selected_area_id
                    flow._sensor_control_group_stage = "area_sensors_edit"
                    return await async_step_sensor_control_config(flow, None)

            if action == "delete":
                delete_area_id: str | None = user_input.get("area_id")
                if delete_area_id:
                    device_area_sensors = [
                        item
                        for item in device_area_sensors
                        if str(item.get("source_id") or "") != delete_area_id
                    ]
                    device_section = deepcopy(devices_config.get(norm_device_id) or {})
                    device_section[SENSOR_CONTROL_SOURCES_KEY] = device_sources
                    device_section[SENSOR_CONTROL_ABS_HUMIDITY_INPUTS_KEY] = (
                        device_abs_inputs
                    )
                    device_section[SENSOR_CONTROL_AREA_SENSORS_KEY] = (
                        device_area_sensors
                    )
                    devices_config[norm_device_id] = device_section
                    sensor_control_section[CONFIG_DEVICES_KEY] = devices_config
                    _persist_sensor_control_section(
                        flow,
                        options,
                        sensor_control_section,
                    )
                return await async_step_sensor_control_config(flow, None)

            if action == "back":
                flow._sensor_control_group_stage = "select_group"
                return await async_step_sensor_control_config(flow, None)

        # Build area sensor list for display
        area_sensor_descriptions = []
        area_sensor_select_options = []
        for area_sensor in device_area_sensors:
            source_id = str(area_sensor.get("source_id") or "")
            area_id = str(area_sensor.get("area_id") or "")
            # Skip entries with neither source_id nor area_id
            if not source_id and not area_id:
                continue
            # Generate source_id from area_id if missing (legacy data support)
            if not source_id and area_id:
                source_id = _unique_area_sensor_id(area_id, device_area_sensors)
            area_sensor_descriptions.append(_describe_area_sensor(area_sensor))
            display_label = area_id if area_id else source_id
            area_sensor_select_options.append(
                selector.SelectOptionDict(
                    value=source_id,
                    label=f"Area sensor: {display_label}",
                )
            )

        # Add empty option if there are area sensors to select
        if area_sensor_select_options:
            area_sensor_select_options.insert(
                0, selector.SelectOptionDict(value="", label="(select area sensor)")
            )

        area_sensors_info = (
            "\n".join(area_sensor_descriptions)
            if area_sensor_descriptions
            else "No area sensors configured."
        )

        schema = vol.Schema(
            {
                vol.Required("action"): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            selector.SelectOptionDict(
                                value="add", label="Add area sensor"
                            ),
                            selector.SelectOptionDict(
                                value="edit", label="Edit area sensor"
                            ),
                            selector.SelectOptionDict(
                                value="delete", label="Delete area sensor"
                            ),
                            selector.SelectOptionDict(value="back", label="Back"),
                        ],
                        mode="list",
                    )
                ),
                vol.Optional("area_id"): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=area_sensor_select_options,
                        mode="dropdown",
                    )
                ),
            }
        )

        info_text = (
            "🧭 **Area Sensor Configuration**\n\n"
            f"Configuring area sensors for FAN: `{selected_device_id}`\n\n"
            f"**Existing area sensors:**\n{area_sensors_info}"
        )

        return flow.async_show_form(
            step_id="feature_config",
            data_schema=schema,
            description_placeholders={"info": info_text},
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
            area_id = str(user_input.get("area_id") or "").strip()
            source_id = (
                str(selected_area_sensor.get("source_id"))
                if selected_area_sensor and selected_area_sensor.get("source_id")
                else _unique_area_sensor_id(area_id, device_area_sensors)
            )

            updated_area_sensor: dict[str, Any] = {
                "source_id": source_id,
                "area_id": area_id,
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
            area_id = str(user_input.get("area_id") or "").strip()
            if area_id:
                updated_area_sensor["area_id"] = area_id

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

        area_id_default = (
            str(selected_area_sensor.get("area_id"))
            if selected_area_sensor and selected_area_sensor.get("area_id")
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
            vol.Optional("temperature_entity")
            if not temp_default
            else vol.Required("temperature_entity", default=temp_default)
        )
        humidity_key = (
            vol.Optional("humidity_entity")
            if not humidity_default
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
        # Get zones for this FAN to populate zone dropdown
        zones_section = get_migrated_feature_section(options, FEATURE_ZONES)
        fan_zones = get_zones_for_fan(zones_section, selected_device_id)
        zone_options = [
            selector.SelectOptionDict(
                value=str(z.get("zone_id")), label=str(z.get("zone_id"))
            )
            for z in fan_zones
            if z.get("zone_id")
        ]
        # Add empty option for no zone
        zone_options.insert(0, selector.SelectOptionDict(value="", label="(no zone)"))

        zone_key = (
            vol.Optional("zone_id")
            if not zone_default
            else vol.Optional("zone_id", default=zone_default)
        )

        schema = vol.Schema(
            {
                vol.Required("area_id", default=area_id_default): vol.All(
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
                zone_key: selector.SelectSelector(
                    selector.SelectSelectorConfig(options=zone_options, mode="dropdown")
                ),
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
            "🧭 **FAN Configuration**\n\n"
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
                    'Multiple area sensors can share the same zone_id. '
                    'CO2 threshold: use entity for dynamic value (e.g., input_number), '
                    'or just set the number as static fallback.',
                )
            }"
        )
        return flow.async_show_form(
            step_id="feature_config",
            data_schema=schema,
            description_placeholders={"info": info_text},
        )

    # ------------------------------------------------------------------
    # Internal fan sensors: indoor/outdoor temp/humidity + abs humidity
    # ------------------------------------------------------------------
    if group_stage == "internal_fan_sensors":
        _LOGGER.debug(
            "Routing to handle_internal_fan_sensors for device %s", selected_device_id
        )
        try:
            return await handler.handle_internal_fan_sensors(
                flow, selected_device_id, device_sources, device_abs_inputs, user_input
            )
        except Exception as e:
            _LOGGER.error("Error in handle_internal_fan_sensors: %s", e, exc_info=True)
            raise

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

    if group_stage == "rems_menu":
        options = flow.hass.data[DOMAIN]["config_entry"].options
        remote_binding_section = get_migrated_feature_section(
            options, FEATURE_REMOTE_BINDING
        )
        fan_rems = get_remote_binding_rems(remote_binding_section, selected_device_id)

        if user_input is not None:
            action = str(user_input.get("action") or "")

            if action == "add":
                flow._sensor_control_editing_rem_id = None
                flow._sensor_control_group_stage = "rems_edit"
                return await async_step_sensor_control_config(flow, None)

            if action == "edit":
                selected_rem_id: str | None = user_input.get("rem_id")
                if selected_rem_id:
                    flow._sensor_control_editing_rem_id = selected_rem_id
                    flow._sensor_control_group_stage = "rems_edit"
                    return await async_step_sensor_control_config(flow, None)

            if action == "delete":
                delete_rem_id: str | None = user_input.get("rem_id")
                if delete_rem_id:
                    delete_id_normalized = normalize_device_id(delete_rem_id)
                    new_rems = [
                        rem
                        for rem in fan_rems
                        if normalize_device_id(str(rem.get("rem_id") or ""))
                        != delete_id_normalized
                    ]
                    set_fan_section(
                        remote_binding_section,
                        selected_device_id,
                        {"REMs": new_rems},
                    )
                    _persist_remote_binding_section(
                        flow,
                        dict(options),
                        remote_binding_section,
                    )
                return await async_step_sensor_control_config(flow, None)

            if action == "back":
                flow._sensor_control_group_stage = "select_group"
                return await async_step_sensor_control_config(flow, None)

        # Build REM list for display
        rem_descriptions = []
        rem_select_options = []
        for rem in fan_rems:
            rem_id = str(rem.get("rem_id") or "unnamed")
            rem_descriptions.append(_describe_remote_binding(rem))
            rem_select_options.append(
                selector.SelectOptionDict(value=rem_id, label=f"REM: {rem_id}")
            )

        rems_info = (
            "\n".join(rem_descriptions) if rem_descriptions else "No REMs configured."
        )

        schema = vol.Schema(
            {
                vol.Required("action"): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            selector.SelectOptionDict(value="add", label="Add REM"),
                            selector.SelectOptionDict(value="edit", label="Edit REM"),
                            selector.SelectOptionDict(
                                value="delete", label="Delete REM"
                            ),
                            selector.SelectOptionDict(value="back", label="Back"),
                        ],
                        mode="list",
                    )
                ),
                vol.Optional("rem_id"): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=rem_select_options,
                        mode="dropdown",
                    )
                ),
            }
        )

        info_text = (
            "🧭 **REM Configuration**\n\n"
            f"Configuring REM bindings for FAN: `{selected_device_id}`\n\n"
            f"**Existing REMs:**\n{rems_info}"
        )

        return flow.async_show_form(
            step_id="feature_config",
            data_schema=schema,
            description_placeholders={"info": info_text},
        )

    if group_stage == "rems_edit":
        return await _async_handle_rems_edit(
            flow, handler, selected_device_id, user_input
        )

    # Fallback for unknown group stages
    _LOGGER.warning("Unknown group_stage: %s", group_stage)
    flow._sensor_control_group_stage = "select_group"
    return await async_step_sensor_control_config(flow, None)


def _get_persisted_sensor_control_sections(
    options: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return (legacy_section, canonical_section) for sensor_control config.

    The legacy section is the old top-level sensor_control dict.
    The canonical section is the new ramses_extras.features.sensor_control dict.
    """
    # Legacy (top-level) section
    legacy_section = options.get(FEATURE_SENSOR_CONTROL, {})

    # Canonical (feature) section
    canonical_section = get_migrated_feature_section(options, FEATURE_SENSOR_CONTROL)

    return legacy_section, canonical_section


def _get_area_id_options(
    options: dict[str, Any], selected_device_id: str
) -> list[selector.SelectOptionDict]:
    """Get list of area_id values from configured area sensors for the dropdown."""
    area_id_options: list[selector.SelectOptionDict] = []
    seen_area_ids: set[str] = set()

    # Add empty option
    area_id_options.append(selector.SelectOptionDict(value="", label="(no area)"))

    # Get area sensors from both legacy and canonical sections
    legacy, canonical = _get_persisted_sensor_control_sections(options)

    # Check legacy section
    area_sensors_legacy = legacy.get("area_sensors", {}).get(
        selected_device_id.replace(":", "_"), []
    )
    for area_sensor in area_sensors_legacy:
        area_id = str(area_sensor.get("area_id", "")).strip()
        if area_id and area_id not in seen_area_ids:
            seen_area_ids.add(area_id)
            area_id_options.append(
                selector.SelectOptionDict(value=area_id, label=area_id)
            )

    # Check canonical section
    canonical_devices = canonical.get("devices", {})
    device_config = canonical_devices.get(selected_device_id, {})
    area_sensors_canonical = device_config.get("area_sensors", [])
    for area_sensor in area_sensors_canonical:
        area_id = str(area_sensor.get("area_id", "")).strip()
        if area_id and area_id not in seen_area_ids:
            seen_area_ids.add(area_id)
            area_id_options.append(
                selector.SelectOptionDict(value=area_id, label=area_id)
            )

    return area_id_options


def _get_rem_device_options(hass: HomeAssistant) -> list[selector.SelectOptionDict]:
    """Get list of discovered REM device IDs for the combobox dropdown.

    Collects REM/DIS devices from the broker and already configured REMs,
    returning them as SelectOptionDict items for the dropdown.
    """
    options: list[selector.SelectOptionDict] = []
    seen_ids: set[str] = set()

    # Helper to normalize and add device ID
    def add_device_id(device_id: str, label: str | None = None) -> None:
        if not device_id:
            return
        normalized = normalize_device_id(device_id)
        if normalized in seen_ids:
            return
        seen_ids.add(normalized)
        display = label if label else normalized
        options.append(selector.SelectOptionDict(value=normalized, label=display))

    # Get discovered devices from the broker
    domain_data = hass.data.get(DOMAIN, {})
    devices = domain_data.get("devices", [])

    for device in devices:
        if isinstance(device, str):
            # For plain string devices, check if it looks like a REM ID
            # REM IDs are typically 2-digit prefixes like 18, 22, 29, 30
            device_id = str(device).replace("_", ":").strip()
            if len(device_id) >= 9 and device_id[:2] in (
                "18",
                "22",
                "29",
                "30",
            ):
                add_device_id(device_id)
            continue

        # Check device type/slug for DIS/REM
        slugs: list[str] = []

        # Get slugs from various attributes
        if hasattr(device, "slugs"):
            raw = device.slugs
            if isinstance(raw, list):
                slugs.extend(str(s) for s in raw)
            else:
                slugs.append(str(raw))

        slug_attr = device._SLUG if hasattr(device, "_SLUG") else None
        if slug_attr:
            name = slug_attr.name if hasattr(slug_attr, "name") else None
            slugs.append(str(name or slug_attr))

        if hasattr(device, "device_type"):
            slugs.append(str(device.device_type))
        if hasattr(device, "type"):
            slugs.append(str(device.type))

        # Check if any slug indicates a DIS/REM device
        is_rem = any(
            slug in ("DIS", "REM", "DIS", "HRC", "remote", "display") for slug in slugs
        )

        if is_rem:
            rem_id: str | None = device.id if hasattr(device, "id") else None
            if rem_id:
                add_device_id(str(rem_id), f"{str(rem_id)} ({', '.join(slugs)})")

    # Also get REMs from already configured bindings
    try:
        config_entry = domain_data.get("config_entry")
        if config_entry is not None:
            from ...framework.helpers.config.migration import (
                migrate_to_canonical_config,
            )
            from ...framework.helpers.config.model import (
                get_feature_section,
                get_remote_binding_rem_ids,
            )

            raw_config: dict[str, Any] = {}
            if getattr(config_entry, "data", None):
                raw_config.update(dict(config_entry.data))
            if getattr(config_entry, "options", None):
                raw_config.update(dict(config_entry.options))

            canonical_config = migrate_to_canonical_config(raw_config)
            remote_binding_section = get_feature_section(
                canonical_config, FEATURE_REMOTE_BINDING
            )

            # Get all configured REM IDs across all FANs
            fan_ids = list(remote_binding_section.get("FANs", {}).keys())
            for fan_id in fan_ids:
                rem_ids = get_remote_binding_rem_ids(remote_binding_section, fan_id)
                for rem_id in rem_ids:
                    add_device_id(rem_id)
    except Exception:
        pass  # Don't let config reading break the dropdown

    # Sort by label
    return sorted(options, key=lambda x: x["label"])


def _get_area_id_options_from_legacy(
    options: dict[str, Any], selected_device_id: str
) -> list[selector.SelectOptionDict]:
    """Get list of area_ids from existing area_sensors for the dropdown.

    Collects area_id values from area_sensors configured for this device.
    """
    area_ids: set[str] = set()

    _LOGGER.debug(
        "_get_area_id_options called for device %s, options keys: %s",
        selected_device_id,
        list(options.keys()),
    )

    # Get sensor_control section to find area_sensors
    sensor_control_section = get_migrated_feature_section(
        options, FEATURE_SENSOR_CONTROL
    )
    _LOGGER.debug(
        "sensor_control_section keys: %s",
        list(sensor_control_section.keys()),
    )

    devices = sensor_control_section.get(CONFIG_DEVICES_KEY, {})
    _LOGGER.debug(
        "devices type: %s, keys: %s",
        type(devices).__name__,
        list(devices.keys()) if isinstance(devices, dict) else "N/A",
    )

    if isinstance(devices, dict):
        norm_device_id = normalize_device_id(selected_device_id)
        _LOGGER.debug(
            "Looking for device %s (normalized: %s)",
            selected_device_id,
            norm_device_id,
        )
        device_section = devices.get(selected_device_id) or devices.get(norm_device_id)
        _LOGGER.debug(
            "device_section type: %s",
            type(device_section).__name__,
        )
        if isinstance(device_section, dict):
            area_sensors = device_section.get(SENSOR_CONTROL_AREA_SENSORS_KEY, [])
            _LOGGER.debug(
                "area_sensors type: %s, len: %s",
                type(area_sensors).__name__,
                len(area_sensors) if isinstance(area_sensors, list) else "N/A",
            )
            if isinstance(area_sensors, list):
                for sensor in area_sensors:
                    if isinstance(sensor, dict):
                        area_id = str(sensor.get("area_id") or "").strip()
                        _LOGGER.debug(
                            "Found sensor with area_id: %s",
                            area_id,
                        )
                        if area_id:
                            area_ids.add(area_id)

    _LOGGER.debug("Collected area_ids from area_sensors: %s", area_ids)

    # Also collect area_ids from REM bindings for this FAN
    remote_binding_section = get_migrated_feature_section(
        options, FEATURE_REMOTE_BINDING
    )
    fan_rems = get_remote_binding_rems(remote_binding_section, selected_device_id)
    _LOGGER.debug("Found %d REMs for device", len(fan_rems))
    for rem in fan_rems:
        if isinstance(rem, dict):
            area_id = str(rem.get("area_id") or "").strip()
            _LOGGER.debug("Found REM with area_id: %s", area_id)
            if area_id:
                area_ids.add(area_id)

    _LOGGER.debug("Final collected area_ids: %s", area_ids)

    # Build options list, sorted
    result: list[selector.SelectOptionDict] = [
        selector.SelectOptionDict(value="", label="(no area)"),
    ]
    for area_id in sorted(area_ids):
        result.append(selector.SelectOptionDict(value=area_id, label=area_id))

    _LOGGER.debug("Returning area_id_options: %s", result)
    return result


async def _async_handle_rems_menu(
    flow: Any,
    handler: Any,
    selected_device_id: str,
    user_input: dict[str, Any] | None,
) -> Any:
    """Handle the rems_menu group stage for managing REM bindings."""
    options = flow.hass.data[DOMAIN]["config_entry"].options
    remote_binding_section = get_migrated_feature_section(
        options, FEATURE_REMOTE_BINDING
    )
    fan_rems = get_remote_binding_rems(remote_binding_section, selected_device_id)

    # Handle user input from the menu
    if user_input is not None:
        action = user_input.get("action")
        if action == "add":
            flow._sensor_control_editing_rem_id = None
            flow._sensor_control_group_stage = "rems_edit"
            return await async_step_sensor_control_config(flow, None)

        if action == "back":
            flow._sensor_control_group_stage = "select_group"
            return await async_step_sensor_control_config(flow, None)

        if isinstance(action, str) and action.startswith("edit:"):
            rem_id = action.removeprefix("edit:")
            flow._sensor_control_editing_rem_id = rem_id
            flow._sensor_control_group_stage = "rems_edit"
            return await async_step_sensor_control_config(flow, None)

        if isinstance(action, str) and action.startswith("delete:"):
            rem_id = action.removeprefix("delete:")
            # Remove this REM from the list
            new_rems = [
                r
                for r in fan_rems
                if normalize_device_id(str(r.get("rem_id", "")))
                != normalize_device_id(rem_id)
            ]
            set_fan_section(
                remote_binding_section,
                selected_device_id,
                {"REMs": new_rems},
            )
            _persist_remote_binding_section(
                flow,
                dict(options),
                remote_binding_section,
            )
            # Stay on the menu page
            return await async_step_sensor_control_config(flow, None)

    # Build menu options
    menu_options: list[selector.SelectOptionDict] = [
        selector.SelectOptionDict(value="add", label="➕ Add REM"),
    ]

    for item in fan_rems:
        rem_id = str(item.get("rem_id", "Unknown"))
        enabled = bool(item.get("enabled", True))
        status = "✓" if enabled else "✗"
        menu_options.append(
            selector.SelectOptionDict(
                value=f"edit:{rem_id}",
                label=f"{status} {rem_id}",
            )
        )
        menu_options.append(
            selector.SelectOptionDict(
                value=f"delete:{rem_id}",
                label=f"  🗑️ Delete {rem_id}",
            )
        )

    menu_options.append(
        selector.SelectOptionDict(value="back", label="⬅️ Back to groups")
    )

    menu_schema = vol.Schema(
        {
            vol.Required("action"): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=menu_options,
                    mode=selector.SelectSelectorMode.LIST,
                )
            )
        }
    )

    info_lines = [
        "FAN Configuration",
        "",
        f"Configuring REM bindings for device: `{selected_device_id}`",
        "",
        (
            "These associations are managed by Extras (administrative), not device "
            "provisioning."
        ),
    ]
    if fan_rems:
        info_lines.extend(["", "Configured REMs:"])
        info_lines.extend(_describe_remote_binding(item) for item in fan_rems)
    else:
        info_lines.extend(["", "No REMs configured yet."])

    return flow.async_show_form(
        step_id="feature_config",
        data_schema=menu_schema,
        description_placeholders={"info": "\n".join(info_lines)},
    )


async def _async_handle_rems_edit(
    flow: Any,
    handler: Any,
    selected_device_id: str,
    user_input: dict[str, Any] | None,
) -> Any:
    """Handle the rems_edit group stage for editing a REM binding."""
    options = flow.hass.data[DOMAIN]["config_entry"].options
    remote_binding_section = get_migrated_feature_section(
        options, FEATURE_REMOTE_BINDING
    )
    fan_rems = get_remote_binding_rems(remote_binding_section, selected_device_id)
    editing_rem_id_raw = getattr(flow, "_sensor_control_editing_rem_id", None)
    editing_rem_id = None
    if editing_rem_id_raw:
        editing_rem_id = normalize_device_id(str(editing_rem_id_raw))

    existing_rem = None
    if editing_rem_id:
        for rem in fan_rems:
            rem_id = rem.get("rem_id")
            if (
                isinstance(rem_id, str)
                and normalize_device_id(rem_id) == editing_rem_id
            ):
                existing_rem = rem
                break

    errors: dict[str, str] = {}

    if user_input is not None:
        rem_id = normalize_device_id(str(user_input.get("rem_id") or "").strip())
        enabled = bool(user_input.get("enabled", True))
        zone_id = str(user_input.get("zone_id") or "").strip()
        area_id = str(user_input.get("area_id") or "").strip()

        if not rem_id:
            errors["rem_id"] = "REM ID is required"

        if rem_id and (editing_rem_id is None or rem_id != editing_rem_id):
            for rem in fan_rems:
                existing_id = rem.get("rem_id")
                if (
                    isinstance(existing_id, str)
                    and normalize_device_id(existing_id) == rem_id
                ):
                    errors["rem_id"] = "REM ID already exists for this FAN"
                    break

        if not errors:
            updated_rem: dict[str, Any] = {
                "rem_id": rem_id,
                "enabled": enabled,
            }
            if zone_id:
                updated_rem["zone_id"] = zone_id
            if area_id:
                updated_rem["area_id"] = area_id

            new_rems: list[dict[str, Any]] = []
            for rem in fan_rems:
                existing_id = rem.get("rem_id")
                if editing_rem_id and isinstance(existing_id, str):
                    if normalize_device_id(existing_id) == editing_rem_id:
                        continue
                new_rems.append(rem)
            new_rems.append(updated_rem)

            set_fan_section(
                remote_binding_section,
                selected_device_id,
                {"REMs": new_rems},
            )
            _persist_remote_binding_section(
                flow,
                dict(options),
                remote_binding_section,
            )

            flow._sensor_control_editing_rem_id = None
            flow._sensor_control_group_stage = "rems_menu"
            return await async_step_sensor_control_config(flow, None)

    rem_id_default = str(existing_rem.get("rem_id") if existing_rem else "").strip()
    enabled_default = bool(existing_rem.get("enabled", True)) if existing_rem else True
    zone_default = str(existing_rem.get("zone_id") if existing_rem else "").strip()
    area_default = str(existing_rem.get("area_id") if existing_rem else "").strip()

    zones_section = get_migrated_feature_section(options, FEATURE_ZONES)
    fan_zones = get_zones_for_fan(zones_section, selected_device_id)
    zone_options = [
        selector.SelectOptionDict(value="", label="(no zone)"),
        *[
            selector.SelectOptionDict(
                value=str(z.get("zone_id")),
                label=str(z.get("zone_id")),
            )
            for z in fan_zones
            if z.get("zone_id")
        ],
    ]

    zone_key: Any = vol.Optional("zone_id")
    if zone_default:
        zone_key = vol.Optional("zone_id", default=zone_default)

    # Get discovered REM options for the combobox
    rem_options = _get_rem_device_options(flow.hass)

    # Get area_id options from configured area sensors
    area_id_options = _get_area_id_options(options, selected_device_id)

    schema = vol.Schema(
        {
            vol.Required("rem_id", default=rem_id_default): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=rem_options,
                    mode=selector.SelectSelectorMode.DROPDOWN,
                    custom_value=True,
                )
            ),
            vol.Required(
                "enabled",
                default=enabled_default,
            ): selector.BooleanSelector(),
            zone_key: selector.SelectSelector(
                selector.SelectSelectorConfig(options=zone_options, mode="dropdown")
            ),
            vol.Optional("area_id", default=area_default): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=area_id_options,
                    mode=selector.SelectSelectorMode.DROPDOWN,
                    custom_value=True,
                )
            ),
        }
    )

    info_text = (
        f"{'Edit' if existing_rem else 'Add'} REM\n\n"
        f"Configure a REM association for FAN: `{selected_device_id}`\n\n"
        "Use zone_id / area_id optionally to pinpoint location.\n\n"
        "Note: When using area_id, ensure the area is actually "
        "within the selected zone_id."
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
