# Floorplan Helper — Workflows Cheat-Sheet

## The pieces

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

## Workflows

### W1 — Bootstrap (done once)

1. `floorplan_set_svg` with `custom_svg_path` per floor + `editor_url`/`planner_url`.
2. Convert SVG → studio project (`svg_to_studio.py` in `~/dev/plattegrond`, or ask me).
3. Studio → **Projects → Import JSON** → rooms appear; click the **Demo chip** → "Use this dashboard's Home Assistant" for live entities.
4. `floorplan_sync_areas` with the project JSON → creates all HA areas.

### W2 — Place devices (HA → studio)

```yaml
action: ramses_extras.floorplan_seed_studio
data:
  floors:
    begane grond: plattegrond-bg.svg
    1e verdieping: plattegrond-1e.svg
  project_json: >-     # paste your current project export (optional but
    {...}              # keeps background + walls + your edits)
```

→ copy `project_json` from the response → studio **Projects → Import JSON**.
Devices with an HA `area_id` matching a room slug land at the room centroid.
Devices without an area are **parked in a strip below the first floor's
canvas** (`staging: false` to skip). Drag them into rooms.

### W3 — Assign areas by dragging (studio → HA)

1. In studio, drag markers into rooms.
2. Projects → **Export JSON**.
3. Call `floorplan_sync_areas` with `project_json: <paste>` (add
   `dry_run: true` to preview). Each marker inside a room → that entity's
   `area_id` = the room slug; missing areas are created.

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
- `floorplan_upload_svg` auto-injects the toolbar (skips if present,
  respects `toolbar_enabled`).
- The toolbar shows on the **dashboard card only** — never inside studio.
- `custom_svg_path` in `floorplan_set_svg` only changes SVG mode when
  explicitly passed.
