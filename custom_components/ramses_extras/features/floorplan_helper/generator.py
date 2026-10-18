"""Floorplan bundle generator.

Produces everything the ha-floorplan card consumes:

- ``ramses-elements.svg`` — a working default floorplan: devices laid
  out in a grid grouped by HA area (topology group when no area), each
  element named after its primary entity so rules auto-bind. Also
  serves as the symbol sheet — copy ``<g>`` elements into a custom
  building SVG and they keep working.
- ``ramses-floorplan-card.yaml`` — a paste-ready
  ``type: custom:floorplan-card`` config with the managed rules block
  wrapped in BEGIN/END markers.
- A change report (``changes``) diffed against the previous export's
  stored snapshot.

:platform: Home Assistant
:feature: Floorplan Helper
"""

from __future__ import annotations

import logging
import re
from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from ...const import INTEGRATION_DIR
from .const import (
    DEFAULT_ICON,
    FEATURE_ID,
    FLOORPLAN_DEVICE_ICON_MAP,
    FLOORPLAN_GENERATED_BASE,
    FLOORPLAN_GENERATED_DIR_NAME,
    FLOORPLAN_ICONS,
    FLOORPLAN_STATIC_BASE,
    GENERATED_CARD_YAML,
    GENERATED_ELEMENTS_SVG,
    OPTION_AREA_OVERRIDES,
    OPTION_CUSTOM_SVG_PATH,
    OPTION_ELEMENT_BINDINGS,
    OPTION_EXTRA_RULES,
    OPTION_ICON_OVERRIDES,
    OPTION_LAST_SNAPSHOT,
    OPTION_SVG_MODE,
    RULES_BEGIN_MARKER,
    RULES_END_MARKER,
    STYLESHEET_FILENAME,
    SVG_MODE_CUSTOM,
)
from .mapping import (
    get_floorplan_options,
    model_snapshot,
    persist_floorplan_options,
    snapshot_diff,
)
from .topology import build_floorplan_model

_LOGGER = logging.getLogger(__name__)

_ICONS_DIR = (
    INTEGRATION_DIR
    / "features"
    / "floorplan_helper"
    / "www"
    / "floorplan_helper"
    / "icons"
)

_SVG_PATH_RE = re.compile(r'd="([^"]+)"')

# Grid layout constants for the generated elements SVG.
_COLS = 4
_CELL_W = 220
_CELL_H = 96
_GROUP_PAD_X = 40
_GROUP_PAD_Y = 56
_GROUP_GAP = 48
_ICON_SIZE = 24

# Role → rule templates emitted inside the managed block. ``{entity}`` and
# ``{element}`` placeholders are filled per element. Templates mirror the
# floorplan docs' class_set/text_set services.
_ROLE_RULE_TEMPLATES: dict[str, list[dict[str, Any]]] = {
    "status": [
        {
            "state_action": {
                "service": "floorplan.class_set",
                "service_data": {
                    "class": ('${entity.state === "on" ? "rx-online" : "rx-offline"}')
                },
            }
        }
    ],
    "heat_demand": [
        {
            "state_action": {
                "service": "floorplan.class_set",
                "service_data": {
                    "class": ('${Number(entity.state) > 0 ? "rx-heat-demand" : ""}')
                },
            }
        }
    ],
    "window_open": [
        {
            "state_action": {
                "service": "floorplan.class_set",
                "service_data": {
                    "class": ('${entity.state === "on" ? "rx-window-open" : ""}')
                },
            }
        }
    ],
    "fan_rate": [
        {
            "state_action": {
                "service": "floorplan.class_set",
                "service_data": {
                    "class": (
                        '${["high","boost"].includes('
                        'String(entity.state).toLowerCase()) ? "rx-spin" : ""}'
                    )
                },
            }
        }
    ],
    "temperature": [
        {
            "state_action": {
                "service": "floorplan.text_set",
                "service_data": {"text": "${entity.state}"},
            }
        }
    ],
}


def _binding_maps(
    options: dict[str, Any],
) -> tuple[dict[str, str], dict[str, dict[str, Any]]]:
    """Resolve element bindings into lookup maps.

    Bindings may be keyed by the bound entity id or by a custom element
    id carrying ``entity_id`` — either way the device's output targets
    the bound element.

    :return: ``(entity_id → element_id, entity_id → binding)``
    """
    bindings: dict[str, Any] = options.get(OPTION_ELEMENT_BINDINGS, {}) or {}
    entity_element_map: dict[str, str] = {}
    entity_binding_map: dict[str, dict[str, Any]] = {}
    for element_id, binding in bindings.items():
        if not isinstance(binding, dict):
            continue
        entity_id = binding.get("entity_id")
        if entity_id:
            entity_element_map.setdefault(entity_id, element_id)
            entity_binding_map.setdefault(entity_id, binding)
        else:
            entity_binding_map.setdefault(element_id, binding)
    return entity_element_map, entity_binding_map


def _element_id_for_device(device: dict[str, Any], options: dict[str, Any]) -> str:
    """Resolve the SVG element id a device's rules/elements target."""
    entity_element_map, _ = _binding_maps(options)
    primary = device.get("primary_entity")
    if not primary:
        return f"device.{device['device_id']}"
    return str(entity_element_map.get(primary, primary))


def _icon_for_device(device: dict[str, Any], options: dict[str, Any]) -> str:
    """Resolve the icon key for a device.

    Precedence: per-entity override → per-class override → element
    binding icon → device-class default table → DEFAULT_ICON.
    """
    overrides: dict[str, str] = options.get(OPTION_ICON_OVERRIDES, {}) or {}
    bindings: dict[str, Any] = options.get(OPTION_ELEMENT_BINDINGS, {}) or {}
    primary = device.get("primary_entity")
    device_class = device.get("device_class") or ""

    if primary and primary in overrides:
        return overrides[primary]
    if device_class in overrides:
        return overrides[device_class]
    if primary:
        # A binding may be keyed by the entity id itself or by a custom
        # element id carrying an entity_id — check both.
        for element_id, binding in bindings.items():
            if element_id != primary and (
                not isinstance(binding, dict) or binding.get("entity_id") != primary
            ):
                continue
            if isinstance(binding, dict) and binding.get("icon"):
                return str(binding["icon"])
    return FLOORPLAN_DEVICE_ICON_MAP.get(device_class, DEFAULT_ICON)


def _apply_area_overrides(model: dict[str, Any], options: dict[str, Any]) -> None:
    """Mutate device area assignment per user overrides."""
    overrides: dict[str, str] = options.get(OPTION_AREA_OVERRIDES, {}) or {}
    if not overrides:
        return
    areas = model.get("areas", {})
    for dev in model.get("devices", []):
        area = overrides.get(dev["device_id"]) or overrides.get(
            dev.get("primary_entity") or ""
        )
        if area:
            dev["area_id"] = area
            dev["area_name"] = areas.get(area, {}).get("name") or area


def _load_icon_symbol(icon_key: str) -> str | None:
    """Read a shipped icon SVG and return a ``<symbol>`` definition."""
    if icon_key not in FLOORPLAN_ICONS:
        return None
    icon_path = _ICONS_DIR / f"{icon_key}.svg"
    try:
        text = icon_path.read_text(encoding="utf-8")
    except OSError as err:
        _LOGGER.warning("Could not read floorplan icon %s: %s", icon_path, err)
        return None
    paths = _SVG_PATH_RE.findall(text)
    if not paths:
        return None
    inner = "".join(f'<path d="{d}"/>' for d in paths)
    return f'<symbol id="icon.{icon_key}" viewBox="0 0 24 24">{inner}</symbol>'


def _group_devices(
    model: dict[str, Any],
) -> list[tuple[str, str, list[dict[str, Any]]]]:
    """Group devices for layout.

    :return: ``[(group_key, group_label, [devices])]`` — areas first
        (sorted by floor then name), then topology groups, then
        unassigned.
    """
    areas = model.get("areas", {})
    floors = model.get("floors", {})
    groups: dict[str, list[dict[str, Any]]] = {}
    labels: dict[str, str] = {}
    for dev in model.get("devices", []):
        if dev.get("area_id"):
            key = f"area.{dev['area_id']}"
            label = dev.get("area_name") or areas.get(dev["area_id"], {}).get(
                "name", dev["area_id"]
            )
        else:
            key = f"group.{dev.get('group', 'orphan')}"
            label = str(dev.get("group", "orphan")).title()
        groups.setdefault(key, []).append(dev)
        labels[key] = label

    def sort_key(item: tuple[str, list[dict[str, Any]]]) -> tuple[int, float, str]:
        key = item[0]
        if key.startswith("area."):
            area_id = key.split(".", 1)[1]
            floor_id = areas.get(area_id, {}).get("floor_id")
            level = floors.get(floor_id, {}).get("level")
            return (0, float(level if level is not None else 99), key)
        return (1, 0.0, key)

    return [(k, labels[k], v) for k, v in sorted(groups.items(), key=sort_key)]


def build_elements_svg(model: dict[str, Any], options: dict[str, Any]) -> str:
    """Render the generated elements SVG.

    :param model: floorplan topology model
    :param options: merged floorplan options
    :return: SVG document text
    """
    groups = _group_devices(model)
    icon_keys = {
        _icon_for_device(dev, options) for _, _, devs in groups for dev in devs
    }
    symbols = [sym for sym in (_load_icon_symbol(k) for k in sorted(icon_keys)) if sym]

    parts: list[str] = [
        '<svg xmlns="http://www.w3.org/2000/svg" '
        'xmlns:xlink="http://www.w3.org/1999/xlink" '
        'viewBox="0 0 960 640">',
        "<defs>",
        *symbols,
        "</defs>",
        '<g id="floorplan">',
    ]

    y = _GROUP_PAD_Y
    for group_key, label, devs in groups:
        parts.append(f'<g id="{_xml_id(group_key)}">')
        parts.append(
            f'<text class="rx-group-label" x="{_GROUP_PAD_X}" '
            f'y="{y}">{_xml_text(label)}</text>'
        )
        row_y = y + 16
        for idx, dev in enumerate(devs):
            col = idx % _COLS
            row = idx // _COLS
            x = _GROUP_PAD_X + col * _CELL_W
            cy = row_y + row * _CELL_H
            element_id = _element_id_for_device(dev, options)
            icon_key = _icon_for_device(dev, options)
            parts.append(
                f'<g id="{_xml_id(element_id)}" '
                f'transform="translate({x},{cy})">'
                f'<rect class="rx-cell" width="{_CELL_W - 16}" '
                f'height="{_CELL_H - 16}" rx="8"/>'
                f'<use href="#icon.{icon_key}" '
                f'xlink:href="#icon.{icon_key}" x="12" y="14" '
                f'width="{_ICON_SIZE}" height="{_ICON_SIZE}"/>'
                f'<text class="rx-label" x="44" y="30">'
                f"{_xml_text(_short_label(dev))}</text>"
                f'<text class="rx-state" x="44" y="52"></text>'
                "</g>"
            )
        rows = (len(devs) + _COLS - 1) // _COLS
        y = row_y + rows * _CELL_H + _GROUP_GAP
        parts.append("</g>")

    parts.extend(["</g>", "</svg>"])
    return "\n".join(parts)


def _short_label(dev: dict[str, Any]) -> str:
    name = str(dev.get("display_name") or dev["device_id"])
    return name if len(name) <= 24 else name[:22] + "…"


def _xml_id(raw: str) -> str:
    """Sanitize a string for use as an SVG element id."""
    return re.sub(r"[^A-Za-z0-9_.:-]", "_", str(raw))


def _xml_text(raw: str) -> str:
    return str(raw).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _build_rules(
    model: dict[str, Any], options: dict[str, Any]
) -> list[dict[str, Any]]:
    """Build the managed floorplan rules list.

    Element bindings may be keyed by the bound entity id or by a custom
    element id carrying ``entity_id`` — either way the device's rules
    target the bound element.
    """
    _, entity_binding_map = _binding_maps(options)

    rules: list[dict[str, Any]] = []
    for dev in model.get("devices", []):
        primary = dev.get("primary_entity")
        element_id = _element_id_for_device(dev, options)

        for ent in dev.get("entities", []):
            templates = _ROLE_RULE_TEMPLATES.get(ent.get("role") or "")
            if not templates:
                continue
            for template in templates:
                rule: dict[str, Any] = {"entity": ent["entity_id"]}
                if ent["entity_id"] != element_id:
                    rule["element"] = element_id
                rule.update(deepcopy(template))
                rules.append(rule)

        binding = entity_binding_map.get(primary or "")
        if isinstance(binding, dict):
            rules.extend(_parse_extra_rules(binding.get("extra_rules")))

    # Global extra rules appended last.
    rules.extend(_parse_extra_rules(options.get(OPTION_EXTRA_RULES)))
    return rules


def _parse_extra_rules(raw: Any) -> list[dict[str, Any]]:
    """Parse extra_rules entries (dicts or YAML blobs) into rule dicts."""
    rules: list[dict[str, Any]] = []
    for extra in raw or []:
        parsed: Any = None
        if isinstance(extra, dict):
            parsed = deepcopy(extra)
        elif isinstance(extra, str):
            try:
                parsed = yaml.safe_load(extra)
            except yaml.YAMLError:
                parsed = None
        if isinstance(parsed, dict):
            rules.append(parsed)
    return rules


def _build_card_yaml(rules: list[dict[str, Any]], options: dict[str, Any]) -> str:
    """Render the paste-ready floorplan card config.

    The generated rules sit inside BEGIN/END markers so a re-export can
    replace just that block; user rules outside the markers survive.
    """
    svg_mode = options.get(OPTION_SVG_MODE, "generated")
    if svg_mode == SVG_MODE_CUSTOM and options.get(OPTION_CUSTOM_SVG_PATH):
        image_path = options[OPTION_CUSTOM_SVG_PATH]
    else:
        image_path = f"{FLOORPLAN_GENERATED_BASE}/{GENERATED_ELEMENTS_SVG}"

    card = {
        "type": "custom:floorplan-card",
        "config": {
            "image": {"location": image_path, "cache": False},
            "stylesheet": f"{FLOORPLAN_STATIC_BASE}/{STYLESHEET_FILENAME}",
            "defaults": {"hover_action": "hover-info", "tap_action": "more-info"},
            # rules must stay the last config key — the END marker is
            # appended after it.
            "rules": rules,
        },
    }
    text = yaml.dump(card, sort_keys=False, default_flow_style=False)

    lines = text.splitlines()
    out: list[str] = []
    for i, line in enumerate(lines):
        if line.startswith("  rules:"):
            out.append(f"  {RULES_BEGIN_MARKER}")
        out.append(line)
    out.append(f"  {RULES_END_MARKER}")
    return "\n".join(out) + "\n"


async def _write_generated_files(
    hass: HomeAssistant, files: dict[str, str]
) -> list[str]:
    """Write generated files under <config>/www/ramses_extras/floorplan/generated/.

    :return: list of ``/local/...`` URLs written
    """
    out_dir = (
        Path(hass.config.config_dir)
        / "www"
        / "ramses_extras"
        / FLOORPLAN_GENERATED_DIR_NAME
    )

    def _write() -> list[str]:
        out_dir.mkdir(parents=True, exist_ok=True)
        written = []
        for name, content in files.items():
            path = out_dir / name
            path.write_text(content, encoding="utf-8")
            written.append(f"{FLOORPLAN_GENERATED_BASE}/{name}")
        return written

    written: list[str] = await hass.async_add_executor_job(_write)
    return written


async def _floorplan_resource_present(hass: HomeAssistant) -> bool:
    """Check whether a floorplan.js lovelace resource is registered."""
    store: Store[dict[str, Any]] = Store(hass, 1, "lovelace_resources")
    try:
        data = await store.async_load()
    except Exception:  # noqa: BLE001
        return False
    for item in (data or {}).get("items", []):
        if "floorplan" in str(item.get("url", "")).lower():
            return True
    return False


async def async_generate_bundle(
    hass: HomeAssistant, config_entry: Any
) -> dict[str, Any]:
    """Generate the complete floorplan bundle.

    Writes generated files, persists the new model snapshot, and
    returns everything a caller needs to finish setup.

    :param hass: Home Assistant instance
    :param config_entry: Integration config entry
    :return: ``{card_yaml, rules, files_written, changes, warnings}``
    """
    model = await build_floorplan_model(hass)
    options = get_floorplan_options(config_entry)
    _apply_area_overrides(model, options)

    rules = _build_rules(model, options)
    svg_text = build_elements_svg(model, options)
    card_yaml = _build_card_yaml(rules, options)

    files_written = await _write_generated_files(
        hass,
        {
            GENERATED_ELEMENTS_SVG: svg_text,
            GENERATED_CARD_YAML: card_yaml,
        },
    )

    new_snapshot = model_snapshot(model)
    previous = options.get(OPTION_LAST_SNAPSHOT) or {}
    changes = snapshot_diff(previous, new_snapshot)
    options[OPTION_LAST_SNAPSHOT] = new_snapshot
    persist_floorplan_options(hass, config_entry, options)

    warnings: list[str] = []
    if not await _floorplan_resource_present(hass):
        warnings.append(
            "No floorplan.js lovelace resource detected — install "
            "ha-floorplan via HACS before adding the card."
        )

    return {
        "card_yaml": card_yaml,
        "rules": rules,
        "elements_svg_url": f"{FLOORPLAN_GENERATED_BASE}/{GENERATED_ELEMENTS_SVG}",
        "stylesheet_url": f"{FLOORPLAN_STATIC_BASE}/{STYLESHEET_FILENAME}",
        "files_written": files_written,
        "changes": changes,
        "warnings": warnings,
    }


__all__ = ["async_generate_bundle", "build_elements_svg"]
