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
    FLOORPLAN_STATIC_BASE,
    GENERATED_CARD_YAML,
    GENERATED_ELEMENTS_SVG,
    OPTION_BACKGROUND,
    OPTION_CUSTOM_SVG_PATH,
    OPTION_LAST_SNAPSHOT,
    OPTION_SVG_MODE,
    RULES_BEGIN_MARKER,
    RULES_END_MARKER,
    STYLESHEET_FILENAME,
    SVG_MODE_CUSTOM,
)
from .importer import (
    best_floor_for_svg,
    load_latest_project,
    studio_marker_positions,
)
from .mapping import (
    get_floorplan_options,
    model_snapshot,
    persist_floorplan_options,
    snapshot_diff,
)
from .markers import (
    apply_area_overrides,
    apply_room_styles,
    build_elements_svg,
    build_overlay_fragment,
    build_toolbar_svg,
    strip_toolbar,
)
from .rules import build_rules
from .svg_utils import merge_svg_overlay
from .topology import build_floorplan_model


def custom_svg_refs(options: dict[str, Any]) -> list[str]:
    """Normalize ``custom_svg_path`` — a single path or a list (one per
    floor — each gets its own ``<stem>.merged.svg`` on export)."""
    raw = options.get(OPTION_CUSTOM_SVG_PATH)
    if isinstance(raw, str):
        raw = [raw]
    return [str(r) for r in (raw or []) if r]


async def _build_merged_svg(
    hass: HomeAssistant,
    model: dict[str, Any],
    options: dict[str, Any],
    ref: str,
) -> tuple[str | None, list[str], str | None]:
    """Splice device markers + toolbar into the user's custom SVG.

    Marker positions come from the stored studio project (latest.json),
    read from the floor whose room names match the SVG's ``area.*`` ids.

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

    positions: dict[str, dict[str, Any]] = {}
    rooms: list[dict[str, Any]] | None = None
    warnings: list[str] = []
    project_json = await hass.async_add_executor_job(load_latest_project, hass)
    project: dict[str, Any] | None = None
    if project_json:
        try:
            project = json.loads(project_json)
        except json.JSONDecodeError:
            project = None
    if project:
        floor = best_floor_for_svg(project, svg_text)
        if floor:
            rooms = floor.get("rooms") or []
        positions = studio_marker_positions(
            project, str(floor.get("name")) if floor else None
        )
    else:
        warnings.append("No stored studio project — markers placed at area centroids")

    # drop any stale toolbar (old button set, no tooltips) — a fresh
    # one is re-injected inside build_overlay_fragment below
    svg_text = strip_toolbar(svg_text)
    fragment, frag_warnings = build_overlay_fragment(
        model, options, positions, svg_text
    )
    warnings.extend(frag_warnings)
    # Studio room fill/opacity win over the SVG's embedded .room classes —
    # patch the elements' inline style directly (survives every consumer,
    # unlike a <style> block with escaped-id selectors).
    svg_text = apply_room_styles(svg_text, rooms)
    return f"{src.stem}.merged.svg", warnings, merge_svg_overlay(svg_text, fragment)


def build_card_yaml(
    rules: list[dict[str, Any]],
    options: dict[str, Any],
    image_path: str | None = None,
) -> str:
    """Render the paste-ready floorplan card config.

    The generated rules sit inside BEGIN/END markers so a re-export can
    replace just that block; user rules outside the markers survive.
    """
    svg_mode = options.get(OPTION_SVG_MODE, "generated")
    if image_path is None:
        if svg_mode == SVG_MODE_CUSTOM and custom_svg_refs(options):
            image_path = custom_svg_refs(options)[0]
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
    apply_area_overrides(model, options)

    rules = build_rules(model, options)
    svg_text = build_elements_svg(model, options)

    files: dict[str, str] = {}
    warnings: list[str] = []
    merged_names: list[str] = []
    if options.get(OPTION_SVG_MODE) == SVG_MODE_CUSTOM:
        # custom_svg_path may list one SVG per floor — each is merged
        # against the matching project floor and gets its own card yaml
        for ref in custom_svg_refs(options):
            merged_name, merged_warnings, merged_text = await _build_merged_svg(
                hass, model, options, ref
            )
            warnings.extend(merged_warnings)
            if merged_text is not None and merged_name:
                files[merged_name] = merged_text
                merged_names.append(merged_name)

    # One card yaml per merged floor; the un-suffixed file keeps the
    # first floor for backwards compatibility.
    card_yamls: dict[str, str] = {}
    for i, merged_name in enumerate(merged_names):
        stem = Path(merged_name).stem.removesuffix(".merged")
        yml = build_card_yaml(
            rules, options, f"{FLOORPLAN_GENERATED_BASE}/{merged_name}"
        )
        card_yamls[stem] = yml
        files[GENERATED_CARD_YAML if i == 0 else f"{CARD_YAML_STEM}-{stem}.yaml"] = yml
    if not card_yamls:
        card_yamls["default"] = build_card_yaml(rules, options)

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
        "card_yaml": card_yaml,
        "card_yamls": card_yamls,
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
    "build_card_yaml",
    "custom_svg_refs",
]
