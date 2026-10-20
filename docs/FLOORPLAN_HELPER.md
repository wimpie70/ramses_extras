# Floorplan Helper — step-by-step setup guide

The Floorplan Helper generates a ready-to-use bundle for the community
[ha-floorplan](https://github.com/ExperienceLovelace/ha-floorplan)
card: an SVG of your RAMSES devices, a shared stylesheet, and the
YAML rules that wire entities to SVG elements.

You end up with a graphical map of your RAMSES system — fans that
spin, radiators that colour on heat demand, gateways that grey out
when offline — and you can mix in any non-RAMSES entities (garden
lights, jacuzzi, irrigation) with ordinary floorplan rules.

---

## 1. Install ha-floorplan

1. Open **HACS → Frontend** and install **Floorplan Card**
   (repository `ExperienceLovelace/ha-floorplan`). The old
   `pkozul/ha-floorplan` is obsolete — use ExperienceLovelace.
2. Restart Home Assistant when HACS asks.

Floorplan Helper warns in the export response when no `floorplan.js`
Lovelace resource is found.

## 2. Enable the feature

1. **Settings → Devices & Services → Ramses Extras → Configure**.
2. Enable **Floorplan Helper** (global feature, works for all device
   types — not tied to a FAN).
3. Finish the options flow. Defaults are fine to start: *generated*
   SVG mode, no icon overrides.

Enabling the feature also creates derived
`binary_sensor.<device>_heat_demand` entities — one per
`sensor.*_heat_demand` that ramses_cc exposes — so "is this zone
calling for heat" is a simple on/off state.

## 3. Generate the bundle

Call the service (Developer Tools → Actions → `ramses_extras`):

```yaml
action: ramses_extras.floorplan_export
```

This writes:

| File | URL |
|------|-----|
| `ramses-elements.svg` | `/local/ramses_extras/floorplan/generated/ramses-elements.svg` |
| `ramses-floorplan-card.yaml` | `/local/ramses_extras/floorplan/generated/ramses-floorplan-card.yaml` |

and returns the bundle, including `card_yaml` (the config to paste)
and `changes` (what changed since the previous export — see
[Regeneration](#6-regenerating-safely)).

## 4. Add the card

1. Open `ramses-floorplan-card.yaml` in a file editor, or copy the
   `card_yaml` string from the service response.
2. Dashboard → Edit → Add card → Manual → paste the YAML.
3. Save. You now have a working floorplan: devices grouped by HA
   area (or topology group when no area is assigned), each with an
   icon, a label, and a live state readout.

## 5. Make it yours

### 5a. Quick wins — no drawing required

- **Change an icon**: `ramses_extras.floorplan_set_icon` with
  `target` = device class (`FAN`, `TRV`, `CTL`, `OTB`, `DHW`, `REM`,
  `HGI`, `BDR`, `UFC`, `CO2`, `THM`...) or an `entity_id`, and `icon`
  = one of: `fan`, `radiator`, `valve`, `water-boiler`, `thermostat`,
  `thermometer`, `remote`, `gateway`, `fire`, `window-open`,
  `battery`, `co2`, `gauge`, `pipe-valve`, `help`.
- **Assign an area**: `ramses_extras.floorplan_assign_area` with
  `source` = ramses device id (e.g. `32:153289`) or entity_id and
  `area_id` = your HA area. Devices with an area get grouped under
  the area's name; areas sort by floor.
- Re-run `floorplan_export` and reload the dashboard.

### 5b. Draw your own floorplan

The generated SVG is a schematic starting point, not your house. For
a real building layout:

1. Draw the plan in **Inkscape** (recommended — the official
   floorplan editor workflow). A flat scan or PDF of a printed layout
   works well as a tracing base. Browser tool alternative:
   `sleien.github.io/HA-floorplanner-gui` (draws and exports SVG +
   YAML; note it can't import an existing SVG — it keeps its own
   `.json` projects). Avoid draw.io — its SVG export doesn't preserve
   element ids.
2. For each interactive element, set the element `id` to the **entity
   id** it should show — that's the floorplan convention
   (`id="climate.living_room"` binds automatically).
3. Alternatively, copy elements from our symbol sheet at
   `/local/ramses_extras/features/floorplan_helper/symbol-sheet.svg`
   — each `<g>` is a ready-made device element with a real entity id.
4. Save the SVG into `config/www/ramses_extras/floorplan/` (e.g.
   `my-plan.svg`), then switch modes:

   ```yaml
   action: ramses_extras.floorplan_set_svg
   data:
     custom_svg_path: /local/ramses_extras/floorplan/my-plan.svg
   ```

   Or skip the file copy entirely — `floorplan_upload_svg` takes the
   SVG text and writes the file for you (see §5e).

5. If your custom element id differs from the entity id, bind them:

   ```yaml
   action: ramses_extras.floorplan_set_element
   data:
     element_id: valve.living_room
     entity_id: climate.13_045678
   ```

   The next export emits rules that target `valve.living_room` for
   all of that device's entities.
6. Re-run `floorplan_export` and paste the regenerated rules block.

Tips:

- Wrap animated elements (spinning fans) in a `<g>` and put
  `transform` on the group, not the animating element — floorplan's
  transforms collide with element transforms.
- Elements are styled by CSS classes (`rx-online`, `rx-heat-demand`,
  `rx-window-open`, `rx-spin`, `rx-valve-open`, `rx-offline`) defined
  in `ramses-floorplan.css` — override or extend that file's classes
  in your own stylesheet if you want different colours.

### 5c. Non-RAMSES entities

Floorplan doesn't care where entities come from. Add your own rules
for `light.garden`, `switch.jacuzzi`, `binary_sensor.irrigation`, etc.
Keep them either:

- **Outside the managed markers** in the card YAML (hand-maintained,
  never overwritten), or
- **In `extra_rules`** via `floorplan_set_element`'s `extra_rules`
  parameter — these are stored in the mapping and re-emitted inside
  the managed block on every export, so they survive regeneration.

### 5d. In-plan toolbar + external tools

The generated SVG (and the `toolbar_svg` snippet in the export
response, which you can paste once into a custom SVG) contains a small
toolbar — five glyph buttons that drive the whole editing loop from
inside the plan:

| Button | What it does |
|--------|--------------|
| ↻ export | Calls `floorplan_export` — result lands as a notification |
| ⇣ import | Opens Dev Tools with `floorplan_import` preselected — paste the YAML a binding tool produced |
| ⇡ upload | Opens Dev Tools with `floorplan_upload_svg` preselected — paste SVG text to save it into `config/www/` |
| ⛓ editor | Opens the click-to-bind tool (`editor_url` option) |
| ✎ planner | Opens the drawing tool (`planner_url` option) |

Set the tool URLs under **Configure → Floorplan Helper**. An internal
path (starting `/`, e.g. a dashboard view or a `panel_iframe` panel)
navigates inside HA; an `https://` URL opens in a new tab.

**Recommended: Floorplan Studio**
([tinkersoder/floorplan-studio](https://github.com/tinkersoder/floorplan-studio),
MIT) — a full editor that draws rooms/walls/markers *and* binds
entities, and installs **inside HA** via HACS:

1. HACS → ⋮ → Custom repositories → `tinkersoder/floorplan-studio`,
   type **Dashboard** → Download.
2. Add `type: custom:floorplan-studio-card` to a dedicated dashboard
   view.
3. Set `editor_url` and `planner_url` to that view's path
   (e.g. `/lovelace/floorplan-studio`) — the toolbar buttons will
   navigate there.

Its ha-floorplan export YAML (Copy/Download from the editor) pastes
straight into `floorplan_import`; its SVG into `floorplan_upload_svg`.

**Zero-install alternatives** (hosted pages, no HA connection):
`qaddodi.github.io/ha-floorplan-editor` (click-to-bind → YAML for
import) and `sleien.github.io/HA-floorplanner-gui` (drawing → SVG +
YAML; can't import an existing SVG). To keep them in the sidebar:

```yaml
panel_iframe:
  floorplan_editor:
    title: Floorplan editor
    url: https://qaddodi.github.io/ha-floorplan-editor/
    icon: mdi:link-variant
  floorplan_planner:
    title: Floorplanner
    url: https://sleien.github.io/HA-floorplanner-gui/
    icon: mdi:drawing
```

The hosted tools can't write to HA — that's what
`floorplan_import`/`floorplan_upload_svg` are for.

**Round-trip loop:**

1. Tap ⇣ import → paste the floorplan card YAML the editor emitted →
   bindings + rules land in the stored mapping.
2. Tap ↻ export → rules re-emit with your bindings baked in.
3. Tap ✎ planner / ⛓ editor to iterate; new drawings come back via
   ⇡ upload.

Disable the toolbar with the **Toolbar enabled** option if you don't
want the buttons on the plan.

### 5e. Gardens, outbuildings, multiple floors

- **Garden/outside**: just draw it — SVG is freeform. Put garden
  devices in an HA area named e.g. "Garden" and they get their own
  group; unassigned devices fall into an "orphan" group.
- **Multiple floors/buildings**: put each floor in an SVG group
  (e.g. `id="ground_floor"`) and toggle visibility with floorplan's
  layer rules — see the official multi-floor example. Or use one
  dashboard view per floor with `tap_action: action: navigate`.
- **Zoom**: ha-floorplan has no built-in pan/zoom. SVG is vector so
  browser zoom is lossless; layered floor views are the usual answer
  for big houses.

## 6. Regenerating safely

Re-run `floorplan_export` whenever the system changes (new devices,
renamed entities, option edits). The response includes a `changes`
report diffed against the previous export:

```yaml
changes:
  first_export: false
  devices_added: ["34:021567"]
  devices_removed: []
  devices_changed: ["32:153289"]   # entities renamed/added
warnings: [...]
```

**Merge rules:** only the block between
`# >>> ramses_extras managed rules >>>` and
`# <<< ramses_extras managed rules <<<` in the card YAML is
regenerated. Everything outside those comments is yours — keep
hand-written rules there and they are never touched. Customizations
that *should* persist through regeneration belong in the options
(icon overrides, element bindings, `extra_rules`, area overrides)
via the services above or the options flow.

## 7. Moving dev → production

The floorplan is plain files + YAML:

1. Copy `config/www/ramses_extras/` from dev to prod (static assets +
   generated files).
2. On prod, enable Floorplan Helper and run `floorplan_export` —
   regenerated YAML resolves entities by id, which are identical as
   long as you didn't rename entities differently on prod.
3. Paste the card YAML on a prod dashboard.

The stored mapping (bindings, icon overrides, areas) lives in the
integration's config entry options — export/import of the extras
config carries it over.

## 8. Service reference

| Service | Purpose |
|---------|---------|
| `ramses_extras.floorplan_export` | Regenerate files + rules; returns bundle + change report |
| `ramses_extras.floorplan_set_element` | Upsert/remove an element ↔ entity/icon binding (`element_id`, `entity_id`, `icon`, `extra_rules`, `remove`) |
| `ramses_extras.floorplan_set_icon` | Icon override per device class or entity (`target`, `icon`; omit `icon` to clear) |
| `ramses_extras.floorplan_assign_area` | Bind a device/zone to an HA area (`source`, `area_id`; omit to clear) |
| `ramses_extras.floorplan_set_svg` | Switch generated ↔ custom SVG (`custom_svg_path`; empty for generated, omit to leave) — also sets toolbar `editor_url`/`planner_url`/`toolbar_enabled` |
| `ramses_extras.floorplan_import` | Import pasted floorplan YAML into bindings + extra rules (`yaml_text`, `replace`) |
| `ramses_extras.floorplan_upload_svg` | Write an SVG into `config/www/ramses_extras/floorplan/` (`filename`, `svg_text`, `set_as_active`) |

`button.floorplan_export` triggers the same regeneration as the
service — handy as a dashboard shortcut. Every export also raises a
persistent notification with the change summary.

WebSocket commands for tooling: `ramses_extras/floorplan_helper/get_bundle`,
`get_topology`, `list_icons`.

## Troubleshooting

- **"No floorplan.js resource detected"** — install ha-floorplan via
  HACS first; the warning also appears in the export response.
- **Elements don't light up** — element ids must match the entity id
  (or the bound `element_id`). Check the id in your SVG editor.
- **Rules pasted but nothing happens** — verify the stylesheet URL
  loads: `/local/ramses_extras/features/floorplan_helper/ramses-floorplan.css`.
  Static assets are deployed on integration start; restart HA if you
  just enabled the feature.
- **My customizations disappeared** — they were inside the managed
  markers. Move them outside the markers or into `extra_rules`.
