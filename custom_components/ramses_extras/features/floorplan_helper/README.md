# Floorplan Helper

Generates a managed bundle for the community
[ha-floorplan](https://github.com/ExperienceLovelace/ha-floorplan)
card: icons, a shared stylesheet, an elements SVG, and rules YAML
derived from the discovered RAMSES topology.

The card renders the floorplan; this feature only *produces inputs for
it*. Nothing is rendered by ramses_extras at runtime.

## User documentation

See `docs/FLOORPLAN_HELPER.md` for the step-by-step setup guide
(installation, Inkscape editing, migration, regeneration semantics).

## Architecture

```
ramses_cc entities/devices          options (config entry)
        │                                   │
        ▼                                   ▼
  topology.py  ──build_floorplan_model──►  bundle.py
  (device/entity/area model)             merged SVGs + card yamls
                                              │
                                        <config>/www/ramses_extras/
                                          floorplan/generated/
                                              │
                                          /local/ramses_extras/...
                                              │
                                    paste card YAML into dashboard
```

- `topology.py` — joins ramses_cc device ids, the HA entity/device
  registries, and the area/floor registries into a per-device model
  (entities, role classification, area, primary element candidate).
  Device grouping (heat / hvac / hgi / orphan) comes from the shared
  `framework/helpers/ramses_topology.py`, also used by
  `device_status_card`. Id-prefix class inference reuses ramses_rf's
  `DEVICE_ID_REGEX` via `domains.device_class_from_id` (`18:*` → HGI…).
- `mapping.py` — reads/writes the `floorplan_helper` options section
  (dual-write: flat key + canonical `ramses_extras.features.*`
  section). Owns `icon_overrides`, `element_bindings`,
  `area_overrides`, `extra_rules`, `svg_mode`, and the
  `last_snapshot` used for export change reports.
- `domains/` — per-device-class behaviour registry (`get_domain`):
  `hvac.py` covers FAN + bound devices + infra, `heat.py` registers the
  heat classes so behaviour lands there instead of growing shared
  code. Answers "does this marker spin / join zones / open which
  popup".
- `svg_utils.py` — low-level SVG helpers: id/text escaping, slugs,
  `marker_svg`/`svg_button` builders, `set_element_style`,
  `strip_element`, `merge_svg_overlay`, icon-symbol loading. Reuse
  these for any additive change to a drawing.
- `expressions.py` — all `${…}` rule expressions. Documents the
  ha-floorplan eval5 contract (no `return`/`function` substring, no
  `.includes`, `class_set` re-emits the full class set).
- `zones.py` — zone semantics: `rx-zone-*` class naming, bound-device
  resolution via the ramses parent link + one-way zone `devices`,
  hatch defs, toggle/sync/clear payloads.
- `markers.py` — element-id + icon resolution, dock placement,
  overlay fragment (markers + zone defs + toolbar), the generated
  `ramses-elements.svg`, toolbar snippet, studio room-style patching.
- `rules.py` — assembles the managed `rules:` list; small factories
  (`class_set_rule`, `text_set_rule`, `fire_dom_event`, `link_action`)
  for new rule shapes.
- `bundle.py` — orchestrates the export: per-floor merged SVGs, the
  paste-ready card YAML with `# >>> ramses_extras managed rules >>>`
  markers, file writes, snapshot diff.
- `generator.py` — compatibility shim re-exporting the public API.
- `services.py` — `floorplan_export`, `floorplan_set_element`,
  `floorplan_set_icon`, `floorplan_assign_area`, `floorplan_set_svg`,
  `floorplan_import`, `floorplan_upload_svg`. All mapping edits go
  through services so regeneration is managed. Export also raises a
  `persistent_notification` summary (tap-action calls can't show a
  service response).
- `importer.py` — pure parser turning pasted floorplan YAML (card
  config, `views:` dashboard, or bare rules list) into
  `element_bindings` + verbatim `extra_rules`.
- `websocket_commands.py` — `get_bundle`, `get_topology`,
  `list_icons` under `ramses_extras/floorplan_helper/*`.
- `platforms/button.py` — `button.floorplan_export`, one-press
  regeneration (first `button` platform in the integration — see
  `button.py` at top level plus `Platform.BUTTON` in
  `framework/setup/features.py`). The button deliberately has no
  `device_info`: the orphan-device cleanup in
  `framework/setup/devices.py` runs before platform entities attach
  and would delete a synthetic feature device every boot.
- `platforms/binary_sensor.py` — derived
  `binary_sensor.*_heat_demand` entities, one per
  `sensor.*_heat_demand` discovered in the entity registry
  (registry-driven, not device-list-driven). They make "zone calling
  for heat" a plain `class_set` rule instead of a template.
- `config_flow.py` — options step (`async_step_floorplan_helper_config`)
  dispatched from the main options flow via `async_step_feature_config`.

## The editor as source of truth

### hfs (current)

The hfs layout owns **geometry**: walls, rooms, doors, floors, trace
images and device markers (`type`/`entity`/position/`name`). It is
stored server-side in `.storage/floorplan_studio.layout` behind a
rev-checked `LayoutStore`; edits autosave from the open editor.

The RAMSES layer is deliberately **not** part of the layout — hfs
capabilities say `marker_icons=False`, `marker_actions=False`,
`stamp_extras=False` (its validator may strip unknown fields). Zone
membership/colour, caption selections, icon overrides and extra rules
live in our options and are applied by the overlay (hfs card/editor)
and the generated rules — derived output, never merged back.

Every landed store write fires `floorplan_studio_updated`; the
overlay debounces that into `floorplan_export(apply)` so generated
cards regenerate without a button press.

### studio (legacy)

The floorplan-studio **project is the SSOT for everything it can
express**. Our export is a pure function of (project + topology +
conventions) — we never keep a second copy of per-marker semantics
that could conflict.

| Studio field | Used for |
|---|---|
| `marker.actions.tap/hold/double` | gesture actions (see bridges below) |
| `marker.entities` + `elementId` | rule binding / element id |
| `marker.style.icon/color/size/label/showState` | icon, disc color, marker size, name caption, state text on/off |
| `style.glyph/ring/opacity` *(our keys)* | badge inner styling — unknown fields round-trip untouched |
| `marker.ramsesZone` *(our key)* | zone config (`areas`/`devices`/`color`) — read via `effective_zones`; `device_zones` option is fallback only |
| `marker.ramsesCaption` *(our key)* | caption spec — `["eid|suffix", …]` wins over `caption_overrides`; `[]` hides it |
| `project.ramsesDeviceViewUrl` *(our key)* | double-tap navigate target — wins over `device_view_url` option |
| `room` stateRules/fill/opacity | room styling |

**Option migration.** Stored `icon_overrides` / `caption_overrides` /
`marker_style_overrides` / `device_zones` / `device_view_url` still
work as fallback for elements without a marker, and
`migrate_overrides_to_project` (bundle.py) stamps them into the
project on export — *absent fields only*, so studio-owned values are
never clobbered. `floorplan_set_icon` / `floorplan_set_device_zone`
write both stores directly. The config menu no longer exposes the
override text fields; per-marker settings are edited in studio.

Action kinds studio can't express (`fire-dom-event`, action lists)
are bridged through real HA services, which *are* expressible as
`call-service`:

- `ramses_extras.floorplan_zone_toggle` — `{toggles:[{class,elements}],
  clear}` → fires `ramses_extras_floorplan_zone_toggle`; the actions
  module toggles the classes on **every** floorplan card.
- `ramses_extras.floorplan_device_view` — `{device_id,entity,card}` →
  fires `ramses_extras_floorplan_device_view`; the module clears all
  zone highlights and opens the device popup.

The seeded marker writes the full `serviceData` YAML, so studio's own
export emits working actions verbatim; our export regenerates them
from live config (service name = shorthand → never stale).

Studio has no fields for: multi-entity caption expressions, `rx-*`
status classes, the toolbar, and the merged-artwork SVG itself —
those remain generated/managed and additive-only, so they cannot
conflict with studio-owned fields.

## Managed regeneration

- Generated rules live between `RULES_BEGIN_MARKER`/`RULES_END_MARKER`
  in the emitted card YAML. User-authored rules must live outside the
  markers so a re-paste only replaces the managed block.
- Custom rules that *should* round-trip through regeneration are
  stored as YAML blobs in `extra_rules` (global) or per-binding
  `element_bindings[<element_id>].extra_rules`.
- Each export stores `model_snapshot()` in options and diffs against
  the previous one → `changes: {devices_added, devices_removed,
  devices_changed, first_export}`.
- `element_bindings` may be keyed by entity_id or by a custom element
  id carrying `entity_id`; both resolve to the same element through
  `_binding_maps()` — used consistently by `build_elements_svg()` and
  `_build_rules()` so generated SVG ids always match rule targets.

## In-SVG toolbar

`build_toolbar_svg()` emits a `<g id="floorplan.toolbar">` with three
glyph buttons; `_toolbar_rules()` emits their `tap_action` rules
inside the managed block:

| Element | Action |
|---------|--------|
| `floorplan.export` | fires `ramses_fp_action="export"` → module-level dialog runs `floorplan_export` |
| `floorplan.upload` | fires `ramses_fp_action="upload"` → file-picker → `floorplan_upload_svg` |
| `floorplan.editor` | navigates to `editor_url` — the floorplan-studio view (default `/floorplan-studio`) |

`floorplan.import` and `floorplan.planner` are retired glyph ids — no
rules are emitted for them anymore (studio is the editor and project
JSON is the import format). `floorplan_import` remains as a service
for legacy `element_bindings`/`extra_rules` workflows, and the
module-level `import`/`upload`/`export` dialogs still respond if an
older pasted toolbar triggers them.

Internal tool URLs (`/...`) emit `navigate`; external URLs emit `url`
(new tab). The generated SVG includes the toolbar at the bottom-right;
custom SVGs get the snippet from the `toolbar_svg` bundle key — paste
it once, rules keep working.

## Deployed paths

| What | Source | Served at |
|------|--------|-----------|
| Icons, CSS, symbol sheet | `www/floorplan_helper/` | `/local/ramses_extras/features/floorplan_helper/` |
| Generated SVG + card YAML | `floorplan_export` | `/local/ramses_extras/floorplan/generated/` |

Static assets deploy through the normal card pipeline —
`framework/setup/cards.py` copies any non-empty feature `www/` dir,
not only dirs containing `.js` (extended for this feature).

## Tests

`tests/features/floorplan_helper/test_floorplan_helper.py` covers
options merge/persistence, icon override precedence, snapshot diffs,
elements-SVG generation, rule building, markers, and extra_rules
parsing.
