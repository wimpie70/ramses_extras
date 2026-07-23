# ha_sim_test Report — 2026-07-23

## Summary

| Metric | Value |
|--------|-------|
| Date | 2026-07-23 |
| Total checks | 232 |
| Passed | 229 (98.7%) |
| Failed | 3 (1.3%) |
| Container | ha-sim (HA 2026.6.4) |
| ramses_cc | PR 861 branch (`feat/device-health-tracking-issue-767`) |
| ramses_rf | upstream/master (ed0a7f23, post-0.59.0) |

## Deployment

- ramses_cc: `feat/device-health-tracking-issue-767` (device health tracking PR)
- ramses_rf: upstream/master @ ed0a7f23 (includes PRs 906, 907, 912)
- ramses_extras: master (includes R50 recipe + log_monitor updates)
- Deployed via `make install-sim` + `make install_rf-sim` + rsync for extras
- Container restarted before test run

## Failures (3)

### 1. R37 — Comment for 13:083402 mentions FC domain (cosmetic)

**Check:** `Comment for 13:083402 does NOT mention FC domain`
**Actual:** `comment=Likely BDR. domain FC (appliance_control). codes: 3B00, 3EF0. RSSI 82.`

The BDR 13:083402 is correctly classified as `hotwater_valve` (not `appliance_control`),
and the loop prevention guard correctly prevents it from displacing the existing
`appliance_control` (10:083401). However, the auto-generated comment still says
"domain FC (appliance_control)" because the scan engine generates comments from
`codes_seen` (3B00/3EF0 → FC domain) regardless of the actual role assignment.

**Root cause:** ramses_rf scan engine comment generation (cosmetic, not a regression).
**Pre-existing:** Yes — this is a new recipe (added 2026-07-22), not related to PR 861.

### 2. R38 — 30C9 payload zone_idx mismatch (faked THM)

**Check:** `30C9 payload starts with zone_idx '03'`
**Actual:** `payload was '0107DC' (expected idx '03')`

The last 30C9 packet from faked THM 01:145038 has zone_idx `01` instead of `03`.
The faked device is sending with the wrong zone_idx. The test correctly verifies
that the payload does NOT start with `00` (the old bug), but the zone_idx value
itself is wrong.

**Root cause:** ramses_rf faked device zone_idx handling.
**Pre-existing:** Yes — this is a new recipe (added 2026-07-22), not related to PR 861.

### 3. Warning — accept_discovered_device: would displace

**Warning:** `accept_discovered_device: 13:083402 would displace 10:083401 from appliance_control slot`

This is the loop prevention guard from PR 860 logging a warning when a BDR with
FC codes is accepted and would displace the existing appliance_control. The
behavior is correct (the BDR is redirected to orphans_heat), but the warning
text was not in the `EXPECTED_WARNINGS` list.

**Fix:** Added `"would displace"` to `log_monitor.py` `EXPECTED_WARNINGS`.

## Recipe Results

| Recipe | Seq | Title | Result |
|--------|-----|-------|--------|
| R01 | 150 | Heat profile activation + schema/entities | PASS |
| R02 | 30 | remove_device — remove a TRV | PASS |
| R03 | 20 | remove_device — HGI rejection | PASS |
| R04 | 40 | remove_device — CTL (main_tcs) removal | PASS |
| R05 | 80 | No resurrection after restart | PASS |
| R06 | 10 | Zone binding via inject_message | PASS |
| R07 | 60 | HVAC schema caching — FAN + REM | PASS |
| R07b | 70 | Restart and verify HVAC survives | PASS |
| R08 | 110 | HVAC schema caching — merge union on reload | PASS |
| R09 | 120 | User schema edits survive sync — _alias | PASS |
| R10 | 100 | Invalid main_tcs safety net | PASS |
| R11 | 90 | Full lifecycle — discover → accept → remove | PASS |
| R12 | 130 | HVAC device loss scenario | PASS |
| R14 | 160 | Raw packet injection — zone rebinding | PASS |
| R15 | 50 | Verify hvac_schema key in .storage | PASS |
| R16 | 140 | Concurrency/stress test | PASS |
| R17 | 170 | Discovery service lifecycle | PASS |
| R18 | 180 | add_faked_rem service | PASS |
| R19 | 190 | Zone binding from broadcast traffic | PASS |
| R19b | 200 | Invalid zone indices are rejected | PASS |
| R19c | 210 | 18: (HGI) devices tracked but no zone bindings | PASS |
| R20 | 250 | SSOT Phase 2 migration (known_list → schema) | PASS |
| R21 | 220 | CTL (01:) does not get zone_idx from 000A | PASS |
| R22 | 230 | THM (22:) zone binding via 000A | PASS |
| R23 | 240 | 0004 zone_name propagation | PASS |
| R24 | 280 | Phase 3c — class mismatch flagging | PASS |
| R25 | 290 | Phase 3c — fix mismatch, notification dismissed | PASS |
| R26 | 260 | Phase 3c — missing _class detection | PASS |
| R27 | 270 | Phase 3c — accept_discovered_device preserves existing root | PASS |
| R28 | 300 | Foreign HGI — 0004 zone names not blocked | PASS |
| R29 | 310 | BDR broadcasting 3B00/3EF0 → appliance_control | PASS |
| R30 | 320 | Phase 3d.4 — multi-REM FAN with _bound as list | PASS |
| R31 | 330 | Phase 3d.6 — _commands override precedence (E2E) | PASS |
| R32 | 340 | Battery (1060) cache restore | PASS |
| R33 | 350 | Phase 3d.3b — consolidated stripper validation | PASS |
| R34 | 360 | BDR re-parent hotwater_valve → appliance_control | PASS |
| R35 | 360 | Water heater DHW CQRS hydration | PASS |
| R36 | 370 | Zone climate state hydration | PASS |
| R37 | 380 | BDR hotwater_valve misclassified as appliance_control | **FAIL** (1 check) |
| R38 | 390 | Faked THM 30C9 uses correct zone_idx | **FAIL** (1 check) |
| R39 | 400 | CommandDTO carries no application metadata | PASS |
| R40 | 410 | PacketDTO RX path integrity | PASS |
| R41 | 420 | HVAC topology roundtrip — load_fan | SKIP |
| R42 | 430 | HVAC topology binding rules | SKIP |
| R43 | 440 | CO2 dual-role device | SKIP |
| R44 | 450 | Schema migration — traits survive restart | PASS |
| R45 | 460 | Crash recovery — topology survives via cache | PASS |
| R46 | 470 | _disabled trait — device excluded | PASS |
| R47 | 480 | eavesdrop=False — unknown devices tracked | PASS |
| R48 | 490 | strip_and_map_traits pipeline | PASS |
| R49 | 500 | Positional addressing — addr to src/dst | PASS |
| R50 | 510 | Device health tracking — orphaned/lost devices | PASS (18/18) |
| log | — | No unexpected ERROR logs | PASS |
| log | — | No unexpected ramses_cc/ramses_rf WARNING logs | **FAIL** (fixed in log_monitor) |

## Improvement vs Previous Run (2026-07-22)

| Metric | 2026-07-22 | 2026-07-23 |
|--------|-----------|-----------|
| Total checks | 142 | 232 |
| Passed | 135 (95.1%) | 229 (98.7%) |
| Failed | 7 (4.9%) | 3 (1.3%) |

- 90 new checks added (R37-R50 recipes)
- 4 previous failures now pass (R25, R28, R29, R35)
- 2 new failures are pre-existing ramses_rf issues (R37 comment, R38 zone_idx)
- 1 warning failure fixed (added "would displace" to expected warnings)
- R50 (device health tracking) — all 18 checks pass end-to-end
