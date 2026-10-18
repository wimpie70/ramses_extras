"""Floorplan mapping — the editable config behind managed regeneration.

Stores the floorplan feature section inside the integration's config
entry options, following the established dual-write pattern used by
sensor_control (a flat per-feature key for compatibility plus the
canonical ``ramses_extras.features.<feature>`` section via
``set_feature_section``).

Section schema::

    {
        "svg_mode": "generated" | "custom",
        "custom_svg_path": "/local/ramses_extras/floorplan/my-plan.svg",
        "icon_overrides": {"<device_class|entity_id>": "<icon_key>"},
        "element_bindings": {
            "<element_id>": {
                "entity_id": "<entity_id>",
                "icon": "<icon_key>",
                "extra_rules": ["<yaml rule blob>", ...],
            }
        },
        "area_overrides": {"<device_id|entity_id>": "<area_id>"},
        "extra_rules": ["<yaml rule blob>", ...],
        "last_snapshot": {<model signature from previous export>},
    }

:platform: Home Assistant
:feature: Floorplan Helper
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from ...framework.helpers.config.migration import get_migrated_feature_section
from ...framework.helpers.config.model import set_feature_section
from .const import (
    DEFAULT_FLOORPLAN_OPTIONS,
    FEATURE_ID,
    OPTION_AREA_OVERRIDES,
    OPTION_CUSTOM_SVG_PATH,
    OPTION_ELEMENT_BINDINGS,
    OPTION_EXTRA_RULES,
    OPTION_ICON_OVERRIDES,
    OPTION_SVG_MODE,
    SVG_MODE_GENERATED,
)


def get_floorplan_options(config_entry: ConfigEntry) -> dict[str, Any]:
    """Return the merged floorplan options section (defaults + stored).

    :param config_entry: Integration config entry
    :return: Merged options dict — never None
    """
    stored = get_migrated_feature_section(dict(config_entry.options), FEATURE_ID)
    merged = deepcopy(DEFAULT_FLOORPLAN_OPTIONS)
    for key, value in stored.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = {**merged[key], **deepcopy(value)}
        else:
            merged[key] = deepcopy(value)
    return merged


def persist_floorplan_options(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    section: dict[str, Any],
) -> None:
    """Persist the floorplan section back into the config entry options.

    Dual-writes the flat per-feature key (consistent with sensor_control)
    and the canonical ``ramses_extras.features.floorplan_helper`` section.

    :param hass: Home Assistant instance
    :param config_entry: Integration config entry
    :param section: New floorplan section content
    """
    options = dict(config_entry.options)
    canonical_section = deepcopy(section)
    options[FEATURE_ID] = canonical_section
    set_feature_section(options, FEATURE_ID, canonical_section)
    hass.config_entries.async_update_entry(config_entry, options=options)


def set_icon_override(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    target: str,
    icon: str | None,
) -> dict[str, Any]:
    """Set or clear an icon override for a device class or entity.

    :param target: device class (e.g. ``FAN``) or entity_id
    :param icon: icon key, or None to clear the override
    :return: The updated options section
    """
    section = get_floorplan_options(config_entry)
    overrides = section.setdefault(OPTION_ICON_OVERRIDES, {})
    if icon is None:
        overrides.pop(target, None)
    else:
        overrides[target] = icon
    persist_floorplan_options(hass, config_entry, section)
    return section


def set_element_binding(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    element_id: str,
    binding: dict[str, Any] | None,
) -> dict[str, Any]:
    """Set or clear an element binding.

    :param element_id: SVG element id
    :param binding: ``{"entity_id": ..., "icon": ..., "extra_rules": [...]}``
        or None to remove the binding
    :return: The updated options section
    """
    section = get_floorplan_options(config_entry)
    bindings = section.setdefault(OPTION_ELEMENT_BINDINGS, {})
    if binding is None:
        bindings.pop(element_id, None)
    else:
        clean = {k: v for k, v in binding.items() if v is not None}
        bindings[element_id] = clean
    persist_floorplan_options(hass, config_entry, section)
    return section


def set_area_override(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    source: str,
    area_id: str | None,
) -> dict[str, Any]:
    """Bind a ramses device/zone to an HA area (or clear the binding).

    :param source: ramses device id or entity_id
    :param area_id: HA area id, or None to clear
    :return: The updated options section
    """
    section = get_floorplan_options(config_entry)
    overrides = section.setdefault(OPTION_AREA_OVERRIDES, {})
    if area_id is None:
        overrides.pop(source, None)
    else:
        overrides[source] = area_id
    persist_floorplan_options(hass, config_entry, section)
    return section


def set_svg_mode(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    custom_path: str | None,
) -> dict[str, Any]:
    """Switch between generated and custom SVG mode.

    :param custom_path: path to a user SVG (e.g. ``/local/.../my-plan.svg``),
        or None to return to generated mode
    :return: The updated options section
    """
    section = get_floorplan_options(config_entry)
    if custom_path:
        section[OPTION_SVG_MODE] = "custom"
        section[OPTION_CUSTOM_SVG_PATH] = custom_path
    else:
        section[OPTION_SVG_MODE] = SVG_MODE_GENERATED
        section[OPTION_CUSTOM_SVG_PATH] = ""
    persist_floorplan_options(hass, config_entry, section)
    return section


def model_snapshot(model: dict[str, Any]) -> dict[str, Any]:
    """Build a comparable signature of a topology model.

    Used for the export change report: diff the snapshot stored in
    options from the previous export against the current model.

    :param model: model from :func:`topology.build_floorplan_model`
    :return: Signature dict (serialisable, order-stable)
    """
    devices: dict[str, Any] = {}
    for dev in model.get("devices", []):
        devices[dev["device_id"]] = {
            "class": dev.get("device_class"),
            "group": dev.get("group"),
            "area": dev.get("area_id"),
            "primary": dev.get("primary_entity"),
            "entities": sorted(e["entity_id"] for e in dev.get("entities", [])),
        }
    return {"devices": devices}


def snapshot_diff(old: dict[str, Any], new: dict[str, Any]) -> dict[str, Any]:
    """Diff two model snapshots for the export change report.

    :param old: snapshot stored after the previous export (may be empty)
    :param new: snapshot of the current model
    :return: Dict with added/removed/changed device lists
    """
    old_devices = old.get("devices", {}) if isinstance(old, dict) else {}
    new_devices = new.get("devices", {}) if isinstance(new, dict) else {}

    added = sorted(k for k in new_devices if k not in old_devices)
    removed = sorted(k for k in old_devices if k not in new_devices)
    changed = sorted(
        k for k in new_devices if k in old_devices and old_devices[k] != new_devices[k]
    )
    return {
        "first_export": not old_devices,
        "devices_added": added,
        "devices_removed": removed,
        "devices_changed": changed,
    }


__all__ = [
    "get_floorplan_options",
    "model_snapshot",
    "persist_floorplan_options",
    "set_area_override",
    "set_element_binding",
    "set_icon_override",
    "set_svg_mode",
    "snapshot_diff",
]
