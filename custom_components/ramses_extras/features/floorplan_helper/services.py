"""Floorplan Helper services.

Managed-regeneration surface for the ha-floorplan bundle:

- ``floorplan_export`` — regenerate files + rules, return the bundle
  (response-only service).
- ``floorplan_set_element`` — upsert/remove an element binding in the
  stored mapping.
- ``floorplan_set_icon`` — icon override per device class or entity.
- ``floorplan_assign_area`` — bind a device/zone to an HA area.
- ``floorplan_set_svg`` — switch between generated and custom SVG.
- ``floorplan_import`` — parse pasted floorplan YAML (e.g. from the
  external floorplan-editor) into stored bindings and extra rules.
- ``floorplan_upload_svg`` — write an SVG file into
  ``config/www/ramses_extras/floorplan/`` and optionally activate it —
  the file bridge external browser tools cannot perform themselves.
- ``floorplan_sync_areas`` — import a floorplan-studio project JSON:
  creates HA areas for room names and assigns marker entities to the
  room they sit in (real ``entity_registry`` area ids).

:platform: Home Assistant
:feature: Floorplan Helper
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

import voluptuous as vol
from homeassistant.components import persistent_notification
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.helpers import config_validation as cv

from ...const import DOMAIN
from .const import (
    FEATURE_ID,
    FLOORPLAN_ICONS,
    FLOORPLAN_UPLOAD_DIR_NAME,
    OPTION_CUSTOM_SVG_PATH,
    OPTION_EDITOR_URL,
    OPTION_ELEMENT_BINDINGS,
    OPTION_EXTRA_RULES,
    OPTION_PLANNER_URL,
    OPTION_SVG_MODE,
    OPTION_TOOLBAR_ENABLED,
    SVG_MODE_CUSTOM,
    SVG_MODE_GENERATED,
)
from .generator import async_generate_bundle, build_toolbar_svg
from .importer import parse_floorplan_yaml, parse_studio_project, room_for_point
from .mapping import (
    get_floorplan_options,
    persist_floorplan_options,
    set_area_override,
    set_element_binding,
    set_icon_override,
    set_svg_mode,
)

_LOGGER = logging.getLogger(__name__)

SVC_EXPORT = "floorplan_export"
SVC_SET_ELEMENT = "floorplan_set_element"
SVC_SET_ICON = "floorplan_set_icon"
SVC_ASSIGN_AREA = "floorplan_assign_area"
SVC_SET_SVG = "floorplan_set_svg"
SVC_IMPORT = "floorplan_import"
SVC_UPLOAD_SVG = "floorplan_upload_svg"
SVC_SYNC_AREAS = "floorplan_sync_areas"

NOTIFICATION_ID = "ramses_extras_floorplan_export"

_TOOLBAR_W = 5 * 34  # five 26px buttons spaced 34px


def _inject_toolbar(svg_text: str) -> str:
    """Append the toolbar ``<g>`` before ``</svg>``, placed bottom-right.

    Position derives from the viewBox when present; falls back to a fixed
    offset matching the generated SVG's 800-wide canvas.
    """
    x, y = 770.0, 605.0
    m = re.search(r'viewBox="[^"]*?\s([\d.]+)\s([\d.]+)"', svg_text)
    if m:
        vb_w, vb_h = float(m.group(1)), float(m.group(2))
        x = max(0, vb_w - _TOOLBAR_W - 8)
        y = max(0, vb_h - 32)
    snippet = f'<g transform="translate({x:g},{y:g})">{build_toolbar_svg()}</g>'
    if "</svg>" in svg_text:
        return svg_text.replace("</svg>", snippet + "\n</svg>", 1)
    return svg_text + "\n" + snippet


def _config_entry(hass: HomeAssistant) -> ConfigEntry:
    """Return the integration's config entry."""
    entry = hass.data.get(DOMAIN, {}).get("config_entry")
    if not isinstance(entry, ConfigEntry):
        raise RuntimeError("ramses_extras config entry not found")
    return entry


def notify_export(hass: HomeAssistant, bundle: dict[str, Any]) -> None:
    """Raise a persistent_notification summarising an export.

    Needed because tap_action service calls (the in-SVG export button)
    can't display a service response.
    """
    changes = bundle.get("changes") or {}
    lines = [
        f"{len(bundle.get('rules', []))} rules, "
        f"{len(bundle.get('files_written', []))} files written.",
    ]
    if changes.get("first_export"):
        lines.append("First export — snapshot stored.")
    else:
        for key in ("devices_added", "devices_removed", "devices_changed"):
            if changes.get(key):
                lines.append(f"{key.replace('_', ' ')}: {', '.join(changes[key])}")
    for warning in bundle.get("warnings", []):
        lines.append(f"⚠ {warning}")
    persistent_notification.async_create(
        hass,
        "\n".join(lines),
        title="Floorplan bundle regenerated",
        notification_id=NOTIFICATION_ID,
    )


async def async_setup_services(hass: HomeAssistant) -> None:
    """Register floorplan helper services."""

    async def _async_export(call: ServiceCall) -> dict[str, Any]:
        """Regenerate the floorplan bundle and return it."""
        bundle = await async_generate_bundle(hass, _config_entry(hass))
        notify_export(hass, bundle)
        _LOGGER.info(
            "Floorplan export complete: %d rules, %d files",
            len(bundle.get("rules", [])),
            len(bundle.get("files_written", [])),
        )
        return bundle

    async def _async_set_element(call: ServiceCall) -> dict[str, Any]:
        """Upsert an element binding (or remove it)."""
        element_id: str = call.data["element_id"]
        remove = call.data.get("remove", False)
        binding = None
        if not remove:
            binding = {
                "entity_id": call.data.get("entity_id"),
                "icon": call.data.get("icon"),
            }
            extra_rules = call.data.get("extra_rules")
            if extra_rules:
                binding["extra_rules"] = extra_rules
        section = set_element_binding(hass, _config_entry(hass), element_id, binding)
        return {
            "element_id": element_id,
            "binding": section.get("element_bindings", {}).get(element_id),
            "removed": remove,
        }

    async def _async_set_icon(call: ServiceCall) -> dict[str, Any]:
        """Set or clear an icon override."""
        target: str = call.data["target"]
        icon: str | None = call.data.get("icon") or None
        if icon is not None and icon not in FLOORPLAN_ICONS:
            raise vol.Invalid(
                f"Unknown icon '{icon}'. Available: {', '.join(FLOORPLAN_ICONS)}"
            )
        section = set_icon_override(hass, _config_entry(hass), target, icon)
        return {
            "target": target,
            "icon": icon,
            "icon_overrides": section.get("icon_overrides", {}),
        }

    async def _async_assign_area(call: ServiceCall) -> dict[str, Any]:
        """Bind a ramses device/zone to an HA area."""
        source: str = call.data["source"]
        area_id: str | None = call.data.get("area_id") or None
        section = set_area_override(hass, _config_entry(hass), source, area_id)
        return {
            "source": source,
            "area_id": area_id,
            "area_overrides": section.get("area_overrides", {}),
        }

    async def _async_set_svg(call: ServiceCall) -> dict[str, Any]:
        """Switch SVG mode and/or set the toolbar's tool URLs."""
        entry = _config_entry(hass)
        section = get_floorplan_options(entry)
        if "custom_svg_path" in call.data:
            custom_path = call.data.get("custom_svg_path") or None
            if custom_path:
                section[OPTION_SVG_MODE] = SVG_MODE_CUSTOM
                section[OPTION_CUSTOM_SVG_PATH] = custom_path
            else:
                section[OPTION_SVG_MODE] = SVG_MODE_GENERATED
                section[OPTION_CUSTOM_SVG_PATH] = ""
        if "editor_url" in call.data:
            section[OPTION_EDITOR_URL] = call.data["editor_url"] or ""
        if "planner_url" in call.data:
            section[OPTION_PLANNER_URL] = call.data["planner_url"] or ""
        if "toolbar_enabled" in call.data:
            section[OPTION_TOOLBAR_ENABLED] = bool(call.data["toolbar_enabled"])
        persist_floorplan_options(hass, entry, section)
        return {
            "svg_mode": section.get(OPTION_SVG_MODE),
            "custom_svg_path": section.get(OPTION_CUSTOM_SVG_PATH),
            "editor_url": section.get(OPTION_EDITOR_URL),
            "planner_url": section.get(OPTION_PLANNER_URL),
            "toolbar_enabled": section.get(OPTION_TOOLBAR_ENABLED),
        }

    async def _async_import(call: ServiceCall) -> dict[str, Any]:
        """Import pasted floorplan YAML into the stored mapping."""
        parsed = parse_floorplan_yaml(call.data["yaml_text"])
        if "error" in parsed:
            raise vol.Invalid(str(parsed["error"]))

        entry = _config_entry(hass)
        section = get_floorplan_options(entry)

        bindings = section.setdefault(OPTION_ELEMENT_BINDINGS, {})
        for element_id, binding in parsed["bindings"].items():
            existing = bindings.get(element_id)
            merged = dict(existing) if isinstance(existing, dict) else {}
            merged.update(binding)
            bindings[element_id] = merged

        extra = section.setdefault(OPTION_EXTRA_RULES, [])
        if call.data.get("replace"):
            section[OPTION_EXTRA_RULES] = list(parsed["extra_rules"])
        else:
            seen = {repr(rule) for rule in extra}
            extra.extend(
                rule for rule in parsed["extra_rules"] if repr(rule) not in seen
            )

        persist_floorplan_options(hass, entry, section)
        _LOGGER.info(
            "Floorplan import: %d element bindings, %d rules kept",
            len(parsed["bindings"]),
            len(parsed["extra_rules"]),
        )
        return {
            "bindings_imported": len(parsed["bindings"]),
            "rules_kept": len(parsed["extra_rules"]),
            "warnings": parsed["warnings"],
        }

    async def _async_upload_svg(call: ServiceCall) -> dict[str, Any]:
        """Write an SVG into config/www/ramses_extras/floorplan/."""
        filename = Path(str(call.data["filename"])).name
        if not filename.lower().endswith(".svg"):
            filename += ".svg"
        svg_text = str(call.data["svg_text"])
        if "<svg" not in svg_text:
            raise vol.Invalid("svg_text does not look like an SVG document")

        # External tools (e.g. floorplan-studio) rebuild the SVG from their
        # own model, so our toolbar elements are lost — re-inject them
        # bottom-right so the export/import/upload round-trip survives.
        section = get_floorplan_options(_config_entry(hass))
        if section.get(OPTION_TOOLBAR_ENABLED, True) and (
            "floorplan.toolbar" not in svg_text
        ):
            svg_text = _inject_toolbar(svg_text)

        out_dir = (
            Path(hass.config.config_dir)
            / "www"
            / "ramses_extras"
            / FLOORPLAN_UPLOAD_DIR_NAME
        )

        def _write() -> str:
            out_dir.mkdir(parents=True, exist_ok=True)
            (out_dir / filename).write_text(svg_text, encoding="utf-8")
            return filename

        written = await hass.async_add_executor_job(_write)
        web_path = f"/local/ramses_extras/{FLOORPLAN_UPLOAD_DIR_NAME}/{written}"
        _LOGGER.info("Floorplan SVG uploaded: %s", web_path)

        activated = False
        if call.data.get("set_as_active"):
            set_svg_mode(hass, _config_entry(hass), web_path)
            activated = True

        return {
            "web_path": web_path,
            "activated": activated,
        }

    async def _async_sync_areas(call: ServiceCall) -> dict[str, Any]:
        """Sync HA areas from a floorplan-studio project export.

        Creates HA areas for room names (optional) and assigns each
        marker's entities to the smallest room containing it — marker
        placement in the studio drives real entity-registry area ids.
        """
        from homeassistant.helpers import area_registry as ar
        from homeassistant.helpers import entity_registry as er
        from homeassistant.util import slugify

        parsed = parse_studio_project(call.data["project_json"])
        if "error" in parsed:
            raise vol.Invalid(str(parsed["error"]))

        create_areas = call.data.get("create_areas", True)
        dry_run = call.data.get("dry_run", False)
        area_reg = ar.async_get(hass)
        ent_reg = er.async_get(hass)

        # Match rooms to HA areas by slugified name (or existing area id).
        def _slug(name: str) -> str:
            return str(slugify(str(name))).replace("-", "_")

        areas = list(area_reg.async_list_areas())
        by_slug = {_slug(a.name): a for a in areas}
        by_slug.update({a.id: a for a in areas})

        created: list[str] = []
        room_area: dict[str, Any] = {}
        for room in parsed["rooms"]:
            slug = _slug(room["name"])
            area = by_slug.get(slug)
            if area is None and create_areas and not dry_run:
                area = area_reg.async_create(str(room["name"]))
            if area is not None:
                by_slug[slug] = area
                room_area[room["id"]] = area
            elif create_areas:
                # dry-run: pretend it exists for the report
                room_area[room["id"]] = None
            else:
                parsed["warnings"].append(
                    f"{room['floor']}: no HA area for room '{room['name']}'"
                )
        if create_areas:
            created = (
                [a.name for a in area_reg.async_list_areas() if a not in areas]
                if not dry_run
                else [
                    r["name"] for r in parsed["rooms"] if room_area.get(r["id"]) is None
                ]
            )

        assignments: dict[str, str] = {}
        skipped: list[str] = []
        outside: list[str] = []
        for marker in parsed["markers"]:
            room = room_for_point(parsed["rooms"], marker["x"], marker["y"])
            area = room_area.get(room["id"]) if room else None
            for entity_id in marker["entities"]:
                if room is None:
                    outside.append(entity_id)
                    continue
                if ent_reg.async_get(entity_id) is None:
                    skipped.append(entity_id)
                    continue
                target = area.id if area else _slug(room["name"])
                assignments[entity_id] = target
                if area is not None and not dry_run:
                    ent_reg.async_update_entity(entity_id, area_id=area.id)

        _LOGGER.info(
            "Floorplan sync_areas: %d areas created, %d entities assigned",
            len(created),
            len(assignments),
        )
        return {
            "areas_created": created,
            "assignments": assignments,
            "entities_without_area_room": outside,
            "entities_not_in_registry": skipped,
            "dry_run": dry_run,
            "warnings": parsed["warnings"],
        }

    if not hass.services.has_service(DOMAIN, SVC_EXPORT):
        hass.services.async_register(
            DOMAIN,
            SVC_EXPORT,
            _async_export,
            schema=vol.Schema({}, extra=vol.PREVENT_EXTRA),
            supports_response=SupportsResponse.ONLY,
        )

    if not hass.services.has_service(DOMAIN, SVC_SET_ELEMENT):
        hass.services.async_register(
            DOMAIN,
            SVC_SET_ELEMENT,
            _async_set_element,
            schema=vol.Schema(
                {
                    vol.Required("element_id"): cv.string,
                    vol.Optional("entity_id"): cv.entity_id,
                    vol.Optional("icon"): cv.string,
                    vol.Optional("extra_rules"): [cv.string],
                    vol.Optional("remove", default=False): cv.boolean,
                },
                extra=vol.PREVENT_EXTRA,
            ),
            supports_response=SupportsResponse.OPTIONAL,
        )

    if not hass.services.has_service(DOMAIN, SVC_SET_ICON):
        hass.services.async_register(
            DOMAIN,
            SVC_SET_ICON,
            _async_set_icon,
            schema=vol.Schema(
                {
                    vol.Required("target"): cv.string,
                    vol.Optional("icon"): cv.string,
                },
                extra=vol.PREVENT_EXTRA,
            ),
            supports_response=SupportsResponse.OPTIONAL,
        )

    if not hass.services.has_service(DOMAIN, SVC_ASSIGN_AREA):
        hass.services.async_register(
            DOMAIN,
            SVC_ASSIGN_AREA,
            _async_assign_area,
            schema=vol.Schema(
                {
                    vol.Required("source"): cv.string,
                    vol.Optional("area_id"): cv.string,
                },
                extra=vol.PREVENT_EXTRA,
            ),
            supports_response=SupportsResponse.OPTIONAL,
        )

    if not hass.services.has_service(DOMAIN, SVC_SET_SVG):
        hass.services.async_register(
            DOMAIN,
            SVC_SET_SVG,
            _async_set_svg,
            schema=vol.Schema(
                {
                    vol.Optional("custom_svg_path"): cv.string,
                    vol.Optional("editor_url"): cv.string,
                    vol.Optional("planner_url"): cv.string,
                    vol.Optional("toolbar_enabled"): cv.boolean,
                },
                extra=vol.PREVENT_EXTRA,
            ),
            supports_response=SupportsResponse.OPTIONAL,
        )

    if not hass.services.has_service(DOMAIN, SVC_IMPORT):
        hass.services.async_register(
            DOMAIN,
            SVC_IMPORT,
            _async_import,
            schema=vol.Schema(
                {
                    vol.Required("yaml_text"): cv.string,
                    vol.Optional("replace", default=False): cv.boolean,
                },
                extra=vol.PREVENT_EXTRA,
            ),
            supports_response=SupportsResponse.OPTIONAL,
        )

    if not hass.services.has_service(DOMAIN, SVC_UPLOAD_SVG):
        hass.services.async_register(
            DOMAIN,
            SVC_UPLOAD_SVG,
            _async_upload_svg,
            schema=vol.Schema(
                {
                    vol.Required("filename"): cv.string,
                    vol.Required("svg_text"): cv.string,
                    vol.Optional("set_as_active", default=True): cv.boolean,
                },
                extra=vol.PREVENT_EXTRA,
            ),
            supports_response=SupportsResponse.OPTIONAL,
        )

    if not hass.services.has_service(DOMAIN, SVC_SYNC_AREAS):
        hass.services.async_register(
            DOMAIN,
            SVC_SYNC_AREAS,
            _async_sync_areas,
            schema=vol.Schema(
                {
                    vol.Required("project_json"): cv.string,
                    vol.Optional("create_areas", default=True): cv.boolean,
                    vol.Optional("dry_run", default=False): cv.boolean,
                },
                extra=vol.PREVENT_EXTRA,
            ),
            supports_response=SupportsResponse.OPTIONAL,
        )

    _LOGGER.info("Registered floorplan_helper services")


async def async_unload_services(hass: HomeAssistant) -> None:
    """Unregister floorplan helper services."""
    for service in (
        SVC_EXPORT,
        SVC_SET_ELEMENT,
        SVC_SET_ICON,
        SVC_ASSIGN_AREA,
        SVC_SET_SVG,
        SVC_IMPORT,
        SVC_UPLOAD_SVG,
        SVC_SYNC_AREAS,
    ):
        if hass.services.has_service(DOMAIN, service):
            hass.services.async_remove(DOMAIN, service)


__all__ = ["async_setup_services", "async_unload_services", "notify_export"]
