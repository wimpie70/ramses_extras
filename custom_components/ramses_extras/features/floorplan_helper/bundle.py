"""Bundle orchestration — merged SVGs, card yamls, file writes.

Composes the specialised renderers into the export artefact:

- per-floor ``<stem>.merged.svg`` (user drawing + markers + toolbar)
- one paste-ready ``custom:floorplan-card`` yaml per floor, with the
  managed rules block wrapped in BEGIN/END markers
- the generated ``ramses-elements.svg`` fallback plan
- the snapshot diff driving the export's change report

:platform: Home Assistant
:feature: Floorplan Helper
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import yaml
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import (
    CARD_YAML_STEM,
    FLOORPLAN_GENERATED_BASE,
    FLOORPLAN_GENERATED_DIR_NAME,
    FLOORPLAN_ICON_MDI,
    FLOORPLAN_STATIC_BASE,
    GENERATED_CARD_YAML,
    GENERATED_ELEMENTS_SVG,
    OPTION_BACKGROUND,
    OPTION_CUSTOM_SVG_PATH,
    OPTION_DEVICE_VIEW_URL,
    OPTION_DEVICE_ZONES,
    OPTION_ICON_OVERRIDES,
    OPTION_LAST_SNAPSHOT,
    OPTION_SVG_MODE,
    RULES_BEGIN_MARKER,
    RULES_END_MARKER,
    STYLESHEET_FILENAME,
    SVG_MODE_CUSTOM,
)
from .importer import (
    best_floor_for_svg,
    dedupe_rooms,
    project_drawing_svg,
    studio_marker_positions,
    studio_marker_zone,
    studio_room_fills,
)
from .mapping import (
    get_floorplan_options,
    model_snapshot,
    persist_floorplan_options,
    snapshot_diff,
)
from .markers import (
    apply_area_overrides,
    apply_room_labels,
    apply_room_styles,
    build_elements_svg,
    build_overlay_fragment,
    build_toolbar_svg,
    marker_style_for_key,
    strip_toolbar,
)
from .rules import build_rules, caption_override_for_device
from .svg_utils import merge_svg_overlay, slugify
from .topology import build_floorplan_model


def custom_svg_refs(options: dict[str, Any]) -> list[str]:
    """Normalize ``custom_svg_path`` — a single path or a list (one per
    floor — each gets its own ``<stem>.merged.svg`` on export)."""
    raw = options.get(OPTION_CUSTOM_SVG_PATH)
    if isinstance(raw, str):
        raw = [raw]
    return [str(r) for r in (raw or []) if r]


# option override → studio project field it migrates into
_STYLE_PART_KEYS = {
    "disc": "color",  # studio's colour picker owns the badge disc
    "glyph": "glyph",
    "ring": "ring",
    "opacity": "opacity",
}


def migrate_overrides_to_project(
    project: dict[str, Any],
    model: dict[str, Any],
    options: dict[str, Any],
) -> bool:
    """Copy stored option-level overrides into studio project fields.

    Studio round-trips unknown marker fields untouched, so stamping our
    values into markers makes the project self-describing — the single
    source of truth the config-menu text fields used to duplicate.
    Only *absent* fields are written: once stamped, the project owns
    the value and further menu/service writes no longer reach it.

    ``disc`` migrates into ``style.color`` (studio's colour picker then
    owns it); ``ramsesCaption``/``ramsesZone`` and ``style.glyph`` /
    ``style.ring`` / ``style.opacity`` are our own round-tripped keys.

    :return: True when the project was mutated (caller should persist)
    """
    ent_to_dev: dict[str, dict[str, Any]] = {}
    for dev in model.get("devices") or []:
        for eid in [dev.get("primary_entity")] + [
            e.get("entity_id") for e in dev.get("entities") or []
        ]:
            if eid:
                ent_to_dev.setdefault(str(eid), dev)

    icon_overrides: dict[str, Any] = options.get(OPTION_ICON_OVERRIDES) or {}
    zones: dict[str, Any] = options.get(OPTION_DEVICE_ZONES) or {}
    changed = False
    for floor in project.get("floors") or []:
        for marker in floor.get("markers") or []:
            dev = next(
                (
                    ent_to_dev[e]
                    for e in marker.get("entities") or []
                    if str(e) in ent_to_dev
                ),
                None,
            )
            if dev is None:
                continue
            style = marker.setdefault("style", {})

            icon_key = next(
                (
                    icon_overrides[str(key)]
                    for key in (dev.get("primary_entity"), dev.get("device_class"))
                    if key is not None and str(key) in icon_overrides
                ),
                None,
            )
            if icon_key and not style.get("icon"):
                mdi = FLOORPLAN_ICON_MDI.get(str(icon_key))
                if mdi:
                    style["icon"] = mdi
                    changed = True

            parts = marker_style_for_key(dev, options)
            for part, skey in _STYLE_PART_KEYS.items():
                if part in parts and style.get(skey) is None:
                    style[skey] = parts[part]
                    changed = True

            if "ramsesCaption" not in marker:
                raw = caption_override_for_device(dev, options)
                if raw is not None:
                    marker["ramsesCaption"] = [
                        str(item) for item in (raw if isinstance(raw, list) else [raw])
                    ]
                    changed = True

            device_id = str(dev.get("device_id") or "")
            if "ramsesZone" not in marker and device_id in zones:
                studio_marker_zone(marker, zones[device_id])
                changed = True

    if "ramsesDeviceViewUrl" not in project and options.get(OPTION_DEVICE_VIEW_URL):
        project["ramsesDeviceViewUrl"] = str(options[OPTION_DEVICE_VIEW_URL])
        changed = True
    return changed


async def _build_merged_svg(
    hass: HomeAssistant,
    model: dict[str, Any],
    options: dict[str, Any],
    ref: str,
    project: dict[str, Any] | None = None,
) -> tuple[str | None, list[str], str | None]:
    """Splice device markers + toolbar into the user's custom SVG.

    Marker positions come from the editor's stored plan, read from the
    floor whose room names match the SVG's ``area.*`` ids.

    :return: ``(merged filename, warnings, merged SVG text or None)``
    """
    if ref.startswith("/local/"):
        src = Path(hass.config.config_dir) / "www" / ref[len("/local/") :]
    else:
        src = (
            Path(hass.config.config_dir)
            / "www"
            / "ramses_extras"
            / "floorplan"
            / Path(ref).name
        )

    def _read() -> str | None:
        try:
            return src.read_text(encoding="utf-8")
        except OSError:
            return None

    svg_text = await hass.async_add_executor_job(_read)
    if svg_text is None:
        return (
            None,
            [f"Custom SVG not readable: {ref} — image left unchanged"],
            None,
        )

    # Inkscape drawings are authored on a transparent page — without a
    # backdrop the HA theme shows through and translucent room fills
    # render dark. The rect goes first so any drawing elements stay on
    # top (namedview/defs render nothing, so position is irrelevant).
    background = str(options.get(OPTION_BACKGROUND) or "")
    if background:
        svg_text = re.sub(
            r"<svg\b[^>]*>",
            rf'\g<0><rect id="rx.background" width="100%" height="100%" '
            f'fill="{background}"/>',
            svg_text,
            count=1,
        )

    warnings: list[str] = []
    floor: dict[str, Any] | None = None
    if project:
        floor = best_floor_for_svg(project, svg_text)
    else:
        warnings.append("No stored plan — markers placed at area centroids")

    tail_warnings, merged = _merge_overlay_tail(
        model, options, svg_text, project, floor
    )
    warnings.extend(tail_warnings)
    return f"{src.stem}.merged.svg", warnings, merged


def _merge_overlay_tail(
    model: dict[str, Any],
    options: dict[str, Any],
    svg_text: str,
    project: dict[str, Any] | None,
    floor: dict[str, Any] | None,
) -> tuple[list[str], str]:
    """Shared merge tail — positions, overlay fragment, room styles.

    ``floor`` supplies the studio room set; without one (no stored
    project) markers fall back to ``area.*`` centroids in the drawing.
    """
    rooms = dedupe_rooms(floor.get("rooms")) if floor else None
    positions = (
        studio_marker_positions(project, str(floor.get("name")) if floor else None)
        if project
        else {}
    )
    # drop any stale toolbar (old button set, no tooltips) — a fresh
    # one is re-injected inside build_overlay_fragment below
    svg_text = strip_toolbar(svg_text)
    fragment, warnings = build_overlay_fragment(
        model, options, positions, svg_text, studio_room_fills(rooms)
    )
    # Studio room fill/opacity win over the SVG's embedded .room classes —
    # patch the elements' inline style directly (survives every consumer,
    # unlike a <style> block with escaped-id selectors).
    svg_text = apply_room_styles(svg_text, rooms)
    # room names come from the project too — the drawing's baked
    # <text> keeps its position but carries the studio name
    svg_text = apply_room_labels(svg_text, rooms)
    return warnings, merge_svg_overlay(svg_text, fragment)


def _build_project_merged_svg(
    model: dict[str, Any],
    options: dict[str, Any],
    project: dict[str, Any] | None,
    floor: dict[str, Any],
) -> tuple[str | None, list[str], str | None]:
    """Merge the marker overlay into a drawing rendered from the
    project itself — studio is the SSOT, so no authored SVG file is
    needed (mirrors floorplan-studio's own export: background image +
    room polygons + labels).

    :return: ``(merged filename, warnings, merged SVG text or None)``
    """
    name = str(floor.get("name") or "floor")
    svg_text = project_drawing_svg(floor)
    if svg_text is None:
        return None, [f"Studio floor '{name}' has no canvas — skipped"], None
    background = str(options.get(OPTION_BACKGROUND) or "")
    if background:
        # fills any alpha pixels the PNG background leaves behind
        svg_text = re.sub(
            r"<svg\b[^>]*>",
            rf'\g<0><rect id="rx.background" width="100%" height="100%" '
            f'fill="{background}"/>',
            svg_text,
            count=1,
        )
    warnings, merged = _merge_overlay_tail(model, options, svg_text, project, floor)
    return f"{slugify(name)}.merged.svg", warnings, merged


def build_card_config(
    rules: list[dict[str, Any]],
    options: dict[str, Any],
    image_path: str | None = None,
) -> dict[str, Any]:
    """Return the floorplan card config as a dict (pre-serialisation)."""
    svg_mode = options.get(OPTION_SVG_MODE, "generated")
    if image_path is None:
        if svg_mode == SVG_MODE_CUSTOM and custom_svg_refs(options):
            image_path = custom_svg_refs(options)[0]
        else:
            image_path = f"{FLOORPLAN_GENERATED_BASE}/{GENERATED_ELEMENTS_SVG}"

    return {
        "type": "custom:floorplan-card",
        # full-width in sections dashboards (clamped by HA at the
        # section's max column count)
        "layout_options": {"grid_columns": 200},
        "config": {
            "image": {"location": image_path, "cache": False},
            "stylesheet": f"{FLOORPLAN_STATIC_BASE}/{STYLESHEET_FILENAME}",
            "defaults": {"hover_action": "hover-info", "tap_action": "more-info"},
            # rules must stay the last config key — the END marker is
            # appended after it.
            "rules": rules,
        },
    }


def build_card_yaml(
    rules: list[dict[str, Any]],
    options: dict[str, Any],
    image_path: str | None = None,
) -> str:
    """Render the paste-ready floorplan card config.

    The generated rules sit inside BEGIN/END markers so a re-export can
    replace just that block; user rules outside the markers survive.
    """
    card = build_card_config(rules, options, image_path)

    # no aliases — shared dicts (zone toggles reused as service_data and
    # in ramses_zone_sync) must render as repeated blocks, not anchors
    class _NoAliasDumper(yaml.Dumper):
        def ignore_aliases(self, data: Any) -> bool:
            return True

    text = yaml.dump(
        card,
        sort_keys=False,
        default_flow_style=False,
        Dumper=_NoAliasDumper,
    )

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
    hass: HomeAssistant, config_entry: Any, editor: str | None = None
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
    apply_area_overrides(model, options)

    from .editors import resolve_editor  # noqa: PLC0415 — import cycle

    adapter = await resolve_editor(hass, options, editor)

    # the editor's plan is the per-marker SSOT: actions/showState/label
    # edits persist there and are honoured by the rule builder
    marker_meta: dict[str, dict[str, Any]] | None = None
    rules_options = options
    project: dict[str, Any] | None = await adapter.async_load(hass)
    if project:
        # option-level overrides migrate into the plan once —
        # afterwards the marker fields own them (SSOT). Only written
        # back for editors that round-trip our extra marker keys.
        if adapter.capabilities.stamp_extras and migrate_overrides_to_project(
            project, model, options
        ):
            await adapter.async_store(hass, project)
        marker_meta = studio_marker_positions(project)
        url = project.get("ramsesDeviceViewUrl")
        if url:
            # project-level field wins; the stored option is the
            # fallback for plans without one — keep storage
            # clean by applying it to a throwaway copy
            rules_options = {**options, OPTION_DEVICE_VIEW_URL: str(url)}

    rules = build_rules(model, rules_options, marker_meta)
    svg_text = build_elements_svg(model, options)

    files: dict[str, str] = {}
    warnings: list[str] = []
    merged_names: list[str] = []
    project_floors = [
        f for f in (project or {}).get("floors") or [] if project_drawing_svg(f)
    ]
    if project_floors:
        # Studio is the SSOT — each project floor renders to its own
        # <floor>.merged.svg; authored drawing files aren't consulted.
        for floor in project_floors:
            merged_name, merged_warnings, merged_text = _build_project_merged_svg(
                model, options, project, floor
            )
            warnings.extend(merged_warnings)
            if merged_text is not None and merged_name:
                files[merged_name] = merged_text
                merged_names.append(merged_name)
    elif options.get(OPTION_SVG_MODE) == SVG_MODE_CUSTOM:
        # legacy fallback for setups with no stored project: merge the
        # overlay onto the authored drawing files in custom_svg_path
        for ref in custom_svg_refs(options):
            merged_name, merged_warnings, merged_text = await _build_merged_svg(
                hass, model, options, ref, project
            )
            warnings.extend(merged_warnings)
            if merged_text is not None and merged_name:
                files[merged_name] = merged_text
                merged_names.append(merged_name)

    # One card yaml per merged floor; the un-suffixed file keeps the
    # first floor for backwards compatibility. ``cards`` carries the
    # same configs as dicts so callers (the actions card) can patch a
    # dashboard directly, without re-parsing yaml.
    card_yamls: dict[str, str] = {}
    cards: dict[str, dict[str, Any]] = {}
    for i, merged_name in enumerate(merged_names):
        stem = Path(merged_name).stem.removesuffix(".merged")
        image_path = f"{FLOORPLAN_GENERATED_BASE}/{merged_name}"
        yml = build_card_yaml(rules, options, image_path)
        card_yamls[stem] = yml
        cards[stem] = build_card_config(rules, options, image_path)
        files[GENERATED_CARD_YAML if i == 0 else f"{CARD_YAML_STEM}-{stem}.yaml"] = yml
    if not card_yamls:
        card_yamls["default"] = build_card_yaml(rules, options)
        cards["default"] = build_card_config(rules, options)

    card_yaml = next(iter(card_yamls.values()))
    files[GENERATED_ELEMENTS_SVG] = svg_text
    files.setdefault(GENERATED_CARD_YAML, card_yaml)

    files_written = await _write_generated_files(hass, files)

    new_snapshot = model_snapshot(model)
    previous = options.get(OPTION_LAST_SNAPSHOT) or {}
    changes = snapshot_diff(previous, new_snapshot)
    options[OPTION_LAST_SNAPSHOT] = new_snapshot
    persist_floorplan_options(hass, config_entry, options)

    if not await _floorplan_resource_present(hass):
        warnings.append(
            "No floorplan.js lovelace resource detected — install "
            "ha-floorplan via HACS before adding the card."
        )

    return {
        "editor": adapter.key,
        "card_yaml": card_yaml,
        "card_yamls": card_yamls,
        "cards": cards,
        "rules": rules,
        "elements_svg_url": f"{FLOORPLAN_GENERATED_BASE}/{GENERATED_ELEMENTS_SVG}",
        "stylesheet_url": f"{FLOORPLAN_STATIC_BASE}/{STYLESHEET_FILENAME}",
        "toolbar_svg": build_toolbar_svg(options),
        "files_written": files_written,
        "changes": changes,
        "warnings": warnings,
    }


__all__ = [
    "async_generate_bundle",
    "build_card_config",
    "build_card_yaml",
    "custom_svg_refs",
]
