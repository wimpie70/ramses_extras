# Floorplan Helper — Workflows Cheat-Sheet

> **Current editor: ha-floorplan-studio (hfs).** The sections below the
> *Legacy* heading describe the older tinkersoder floorplan-studio
> (browser-side projects) path — still functional via `editor: studio`
> but hidden from the config flow and a removal candidate.

## The hfs pipeline

| Piece | Role |
|---|---|
| **ha-floorplan-studio** | The editor (server-side layout in `.storage/floorplan_studio.layout`, rev-checked) + native card (2D/2.5D/3D). |
| **ramses-editor-embed** | Mounts the hfs panel inline on a dashboard view. |
| **ramses-floorplan-actions** | Control surface: ＋ Add devices, ⚙ Zones, Sync areas → HA, Export ⇒ / ⇒ Update cards. |
| **ramses-hfs-overlay** | Module-level: RAMSES icons/colours/spin/captions, zone highlights, tap gestures, autosave → auto-export bridge — on the hfs card and the editor. |
| **ha-floorplan card** (`custom:floorplan-card`) | Generated output — merged SVG + rx-* rules + captions + zones. |

```
hfs editor ──autosave (2.5s debounce / page-hide)──▶ .storage (rev-checked)
      │                                                    │
      ▼                                          floorplan_studio_updated
hfs-floorplan-card renders live (+ overlay)                │
                                                           ▼
                                    floorplan_export(apply) ──▶ generated
                                    merged SVG + rules + yaml    cards
```

- Layout edits autosave; every landed write regenerates the generated cards. `Export ⇒`/`⇒ Update cards` are only needed for a first card or after options-level changes (zones, captions, icons).
- `＋ Add devices` flushes the open editor's pending save, merges new markers into the stored layout, reloads the editor onto the new revision, then regenerates cards.
- Zones (owner → rooms + devices + colour) live in **our options**, not the layout — configured in ⚙ Zones, synced both ways with the editor's selection.
- `Sync areas → HA` remains the explicit one-way room→HA-area push.

---

## Legacy — tinkersoder floorplan-studio workflows

| Tool | Role |
|---|---|
| **floorplan-studio** (HACS card) | Project-based drawing/editing. Works on a JSON *project* (rooms, markers, walls, background PNG). Exports a ha-floorplan **SVG + YAML**. |
| **Inkscape / any SVG editor** | Alternative drawing tool — edit `area.*` elements directly in the SVG. |
| **qaddodi floorplan editor** (`editor_url`) | Click existing SVG elements → assign entities → emits YAML for `floorplan_import`. |
| **ha-floorplan card** | Renders the active SVG on a dashboard; state rules + interactions + injected toolbar. |
| **ramses_extras services** | The glue: generate, import, export, upload, area sync, studio seed. |

Two file formats to keep straight:

- **Studio project JSON** — studio's internal model (Projects → Export/Import JSON). Feeds `floorplan_sync_areas` and is the target of `floorplan_seed_studio`.
- **Export pair** — ha-floorplan **SVG** (rendered) + **YAML** (rules + entities). Feed `floorplan_upload_svg` + `floorplan_import`; produced by `floorplan_export` as `svg_markup` + `card_yaml`.

## Data flow

```
 Inkscape ──(area.* in SVG)──▶ studio (Import JSON, via svg_to_studio project)
      ▲                            │ place markers, add rules
      │                            ▼
      └──── upload ◀── export: SVG + YAML / project JSON
                                   │
            ┌──────────────────────┼───────────────────────┐
            ▼                      ▼                       ▼
   floorplan_upload_svg   floorplan_import        floorplan_sync_areas
   (file → www,           (YAML → stored          (project JSON →
   toolbar injected)       rules/bindings)         HA areas + entity
            │                      │                 area_id)
            └────────── floorplan_export ◀──────────┘
                          (stored rules + topology →
                           card_yaml, svg_markup, mapping)
                                   │
                                   ▼
                          ha-floorplan card on dashboard
```

## The actions card

`ramses-floorplan-actions` — a full-width companion card meant to sit
under the studio card on the same view:

```yaml
type: custom:ramses-floorplan-actions
floors:                        # optional; needed for seed with >1 floor
  begane grond: plattegrond-bg.svg
  1e verdieping: plattegrond-1e.svg
marker_size: 20                # optional (default 20)
sync_on_pull: true             # optional — also sync areas after pull
```

**The key trick**: studio keeps its projects in this origin's IndexedDB
(`floorplan-studio` db) and autosaves ~600ms after every change — so the
card reads/writes studio storage directly. No export/download needed:

- **Project picker** lists studio's own projects (current one marked)
- **Pull ← studio** → stores it as `latest.json` + timestamped backup
  (`floorplan_store_project`), then runs `floorplan_sync_areas`
- **Seed → studio** → `seed_studio`, then writes the result *into*
  studio's project list — open it via Projects (no Import JSON needed)
- **Open studio** / **Open editor** — navigate to the configured tool URLs
- **Export bundle** — `floorplan_export`, copies `card_yaml` to clipboard.
  In custom-SVG mode it also writes a **merged SVG**
  (`generated/<name>.merged.svg`): your drawing + device markers at
  their studio positions + the toolbar — that is what the card loads,
  so rules actually bind and `rx-*` classes apply. `custom_svg_path`
  may list one SVG per floor; each gets its own `*.merged.svg` and its
  own card yaml (`ramses-floorplan-card.yaml` = first floor, plus
  `ramses-floorplan-card-<stem>.yaml` for the rest) — the card shows
  per-floor ⧉ copy buttons after export. Paste each yaml as a separate
  card to put multiple floors on one dashboard.
- **Sync areas** — `sync_areas` on the stored project
- **Resize ◉ selected** — apply the tweak icon size to the markers
  selected in studio (multi-select works — studio's own inspector can't)
- **Recolor ◧ rooms** — apply the tweak fill/opacity to selected rooms
  (shift-click) — e.g. colour every room a WTW ventilates

Both studio-side actions go through studio's own `commit()` (re-render,
autosave, Ctrl+Z-able); a DOM+IndexedDB patch is the fallback.

**Device zones** (`floorplan_set_device_zone` or the ⚙ Tweaks "◧ rooms
→ zone" flow): declare which rooms a device serves, then

- **click a marker** (in the exported floorplan card) → its zone's
  rooms get a translucent hatch + outline (`.rx-zone-<dev>` class),
  and the markers of the device's **bound devices** get an outline +
  glow (`.rx-zone-<dev>-dev`). Binding comes from the ramses schema —
  remotes/sensors under a FAN get `parent=<fan id>` — not from which
  room a device sits in (a remote bound to the WTW highlights even
  when placed in a non-zone room). Extra members can be added via the
  zone's `devices` list — ramses device ids **or plain entity ids**
  (DIY valves, zigbee area sensors…); the link is one-way so the same
  entity may serve several zones. Non-ramses members get their own
  docked marker (tap → more-info). Use "◉ markers → zone" in the
  actions card to bind markers selected in studio. HGI gateways are
  never highlighted.
- Zones may **span floors**: list areas from every floor. A device or
  entity without a marker on a floor is parked in that card's **dock**
  — the largest `outside`-class room if the drawing has one (e.g.
  terras), else a strip along the top-right canvas edge — so it stays
  visible and tappable. Tapping a zone member on the 1e card
  highlights only the zone rooms present in that SVG — and the same
  tap **syncs the highlight to every other floorplan card** on the
  dashboard: the rule broadcasts `ramses_zone_sync` via `ll-custom`,
  and the module-level listener applies the identical class toggles
  (`floorplan.*` actions alone can only reach the card that fired
  them). The class names + pattern defs are identical in each merged
  SVG, so both cards render the same highlight.
- **double-tap** → device popup (hvac-fan-card for FAN/HVAC). The
  rule fires `ll-custom`; a module-level listener in the actions-card
  JS catches it on **any** view. If the floorplan option
  `device_view_url` is set, double-tap navigates there instead —
  self-contained, no listener needed.
- **hold** → native more-info on the primary entity

**Drop zone** — fallback for a project JSON from another machine or a
backup file (e.g. migrating to prod): stores + syncs it the same way.

## Workflows

### W1 — Bootstrap (done once)

1. `floorplan_set_svg` with `custom_svg_path` per floor + `editor_url`/`planner_url`.
2. Convert SVG → studio project (`svg_to_studio.py` in `~/dev/plattegrond`, or ask me).
3. Studio → **Projects → Import JSON** → rooms appear; click the **Demo chip** → "Use this dashboard's Home Assistant" for live entities.
4. `floorplan_sync_areas` with the project JSON (or drop it on the
   actions card) → creates all HA areas.

### W2 — Place devices (HA → studio)

```yaml
action: ramses_extras.floorplan_seed_studio
data:
  floors:
    begane grond: plattegrond-bg.svg
    1e verdieping: plattegrond-1e.svg
  # project_json omitted → merges into the stored latest.json if present
```

Or the **Seed markers** button on the actions card (copies the emitted
project JSON to the clipboard). → studio **Projects → Import JSON**.
Devices with an HA `area_id` matching a room slug land at the room
centroid. Devices without an area are **parked in a strip below the
first floor's canvas** (`staging: false` to skip). Drag them into rooms.

### W3 — Assign areas by dragging (studio → HA)

1. In studio, drag markers into rooms.
2. Click **Pull ← studio** on the actions card → the project is read
   straight from studio storage, saved as `latest.json` (+ timestamped
   backup) and `floorplan_sync_areas` runs: each marker inside a room →
   that entity's `area_id` = the room slug; missing areas are created.
   (`dry_run: true` previews via Dev Tools.)

### W4 — Daily editing loop

Studio edit → Export (ha-floorplan target) →

- SVG text → `floorplan_upload_svg` (writes to `www/ramses_extras/floorplan/`, toolbar auto-injected)
- YAML → `floorplan_import` (stores rules/bindings — feeds export)
- `floorplan_export` → `card_yaml` → paste into the dashboard card

Or: Projects → Export JSON → `floorplan_sync_areas` whenever marker
positions should drive HA areas.

### W5 — Direct element binding (no studio)

- `floorplan_set_element` — bind any SVG element id (e.g. `area.woonkamer`)
  to entity/actions/icon. Merges into stored `element_bindings`.
- `floorplan_clear_element` — remove it again.
- `floorplan_assign_area` — floorplan-level area staging (no HA registry
  write — use `sync_areas` for that).

### W6 — Customise output

- `floorplan_list_icons` → available icon keys (`fan`, `hvac`, `boiler`…).
- `floorplan_generate_icon` → write a custom icon to `www/…/icons/`.
- `floorplan_suggest_css` → starter CSS for state colouring.
- `floorplan_get_boundaries` → topology summary of devices/areas.

### W7 — Migrate dev → prod

1. Studio Projects → Export JSON (the project) + keep the export SVG/YAML.
2. On prod: `floorplan_upload_svg` + `floorplan_import` replay them.
3. `floorplan_sync_areas` with the project JSON recreates areas.
4. If prod entity ids differ from dev, re-point bindings in studio and
   re-export — layout/rooms/positions survive regardless.

## Where buttons can run these

| Place | Candidate actions |
|---|---|
| **SVG toolbar** (injected bottom-right) — already live | `floorplan.editor`/`planner` → navigate to studio; `floorplan.export` → call-service `floorplan_export`; `floorplan.import`/`upload` → Dev Tools deep-links |
| **Button entities** (`button.<entry>_floorplan_*`) — on the ramses_extras device page | existing: export/refresh; easy to add: `sync_areas` (needs project JSON — better via automation/script input), `seed_studio` (same limitation) |
| **ha-floorplan element actions** — per room/marker tap & hold | `more-info`, `navigate` (e.g. to an hvac_fan_card view), `call-service` (`floorplan_seed_studio`, `climate.set_hvac_mode`…) |
| **Automation triggers** | none yet — could fire `sync_areas` on a schedule if wanted |
| **Dev Tools → Actions** | anything with a payload (project JSON services live here) |

Services that need a pasted `project_json` can't be one-tap buttons —
use a `script` with a text `input_text`/`variable`, or Dev Tools.

## Gotchas

- Markers **cannot move between floors** in studio. The staging strip is
  on the first floor only — for another floor, switch to it and click the
  entity in the list, then drag.
- `area_id` seeding assumes **area slug == room name slug** (`area.*` id).
  True for areas created by `sync_areas`; hand-renamed HA areas break it.
- Studio **walls/doors are canvas-only** — never exported to the SVG. They
  live in the project JSON only.
- Marker→room matching is **per-floor** (floors share the same canvas
  coordinates — without scoping, a smaller upstairs room can "steal" a
  marker).
- Browser cache: the card JS is served with a `?v=` that doesn't always
  bump — **hard-refresh** (Ctrl+Shift+R) after updates.
- `floorplan_upload_svg` auto-injects the toolbar (skips if present,
  respects `toolbar_enabled`).
- The toolbar shows on the **dashboard card only** — never inside studio.
- `custom_svg_path` in `floorplan_set_svg` only changes SVG mode when
  explicitly passed.
