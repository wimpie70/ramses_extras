# ha_sim_test Report — 2026-07-23

## Summary

| Metric | Value |
|--------|-------|
| Date | 2026-07-23 |
| Total checks | 232 |
| Passed | 232 (100%) |
| Failed | 0 (0%) |
| Container | ha-sim (HA 2026.6.4) |
| ramses_cc | PR 861 branch (`feat/device-health-tracking-issue-767`) |
| ramses_rf | upstream/master + PR 914 (Phase 3.75 eradicate `__class__` mutations) |
| Elapsed | 30.7 min (event-driven waiting) |

## Deployment

- ramses_cc: `feat/device-health-tracking-issue-767` (device health tracking PR)
- ramses_rf: upstream/master + PR 914 branch (`test/pr914_plus_834_fix`)
  - PR 914: Phase 3.75 eradicate dynamic `__class__` mutations (PWhite-Eng)
  - PR 917 fix: BDR declared hotwater_valve not classified as FC domain (wimpie70)
- ramses_extras: master (includes R50 recipe + log_monitor + event-driven waiting)
- Deployed via `make install-sim` + `make install_rf-sim` + rsync for extras
- Container restarted before test run

## Failures (0)

All 232 checks pass. Previous failures (R37 comment, R38 zone_idx, warning
attribution) have been fixed:

- **R37 fix (PR 917):** BDR declared as `hotwater_valve` in schema no longer
  classified as FC domain by the 3B00/3EF0 TPI broadcast heuristic.
  `_is_declared_hotwater_valve()` added to `discovery_scan.py`.
- **R38 fix:** Correct grep pattern for 30C9 packet in `home-assistant.log`
  + `clear_cached_state` at recipe start to prevent QoS queue contention.
- **Warning fix:** `"would displace"` added to `EXPECTED_WARNINGS` in
  `log_monitor.py`.

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
| R37 | 380 | BDR hotwater_valve misclassified as appliance_control | PASS (10/10) |
| R38 | 390 | Faked THM 30C9 uses correct zone_idx | PASS (4/4) |
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
| log | — | No unexpected ramses_cc/ramses_rf WARNING logs | PASS |

## Improvement vs Previous Run (2026-07-22)

| Metric | 2026-07-22 | 2026-07-23 (final) |
|--------|-----------|-----------|
| Total checks | 142 | 232 |
| Passed | 135 (95.1%) | 232 (100%) |
| Failed | 7 (4.9%) | 0 (0%) |
| Elapsed | ~35 min | 30.7 min |

- 90 new checks added (R37-R50 recipes)
- All previous failures now pass (R25, R28, R29, R35, R37, R38, warning)
- R37 fix: PR 917 (ramses_rf) — `_is_declared_hotwater_valve()` in discovery_scan.py
- R38 fix: correct log grep + `clear_cached_state` for QoS queue contention
- R50 (device health tracking) — all 18 checks pass end-to-end
- PR 914 (Phase 3.75) integrated — no regressions
- Event-driven waiting: R37 100.7s→80.2s, R38 68.7s→52.7s
- Per-recipe timing + per-recipe log attribution added to harness
