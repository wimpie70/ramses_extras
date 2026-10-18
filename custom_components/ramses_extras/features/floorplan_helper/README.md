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
  topology.py  ──build_floorplan_model──►  generator.py
  (device/entity/area model)             elements SVG + rules YAML
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
  `device_status_card`.
- `mapping.py` — reads/writes the `floorplan_helper` options section
  (dual-write: flat key + canonical `ramses_extras.features.*`
  section). Owns `icon_overrides`, `element_bindings`,
  `area_overrides`, `extra_rules`, `svg_mode`, and the
  `last_snapshot` used for export change reports.
- `generator.py` — renders the elements SVG (area-grouped grid,
  MDI-derived `<symbol>` defs inlined from shipped icons), the managed
  rules list (role → rule templates), and the paste-ready card YAML
  with `# >>> ramses_extras managed rules >>>` markers.
- `services.py` — `floorplan_export`, `floorplan_set_element`,
  `floorplan_set_icon`, `floorplan_assign_area`, `floorplan_set_svg`.
  All mapping edits go through services so regeneration is managed.
- `websocket_commands.py` — `get_bundle`, `get_topology`,
  `list_icons` under `ramses_extras/floorplan_helper/*`.
- `platforms/binary_sensor.py` — derived
  `binary_sensor.*_heat_demand` entities, one per
  `sensor.*_heat_demand` discovered in the entity registry
  (registry-driven, not device-list-driven). They make "zone calling
  for heat" a plain `class_set` rule instead of a template.
- `config_flow.py` — options step (`async_step_floorplan_helper_config`)
  dispatched from the main options flow via `async_step_feature_config`.

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
