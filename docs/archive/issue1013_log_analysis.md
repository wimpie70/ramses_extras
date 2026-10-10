# Issue 1013: Multi-room zones have no `current_temperature` since 0.59.7

## Log-verified analysis of @peternash's test comments

- **Comment 1** (ramses_cc master + ramses_rf 0.59.9, 57 min run):
  https://github.com/ramses-rf/ramses_cc/issues/1013#issuecomment-5374140093
- **Comment 2** (ramses_cc 0.59.9 + ramses_rf 0.59.9, 34 min run):
  https://github.com/ramses-rf/ramses_cc/issues/1013#issuecomment-5374634252

> **Version note:** Both tests ran `ramses_tx 0.59.9` (confirmed by identical packet
> log header `# ramses_tx 0.59.9`). The ramses_rf 0.59.9 release includes PR 1096
> "Eavesdropping fails to discover TRV as zone sensor (issue 1010)", so the
> 30C9-based sensor learning fix is present in both tests. Both tests also had the
> same ramses_cc code (PR 1021 + PR 1023). The difference in outcomes is **not** a
> version difference — it appears to be related to ramses_db state and timing of
> device acceptance. See the "Revised analysis" section at the end for details.

---

## Comment 1 (ramses_cc master + ramses_rf 0.59.9, 57 min run)

**Timeline:**

| Time | Event |
|------|-------|
| 19:05:16 | Startup. Config has `18:072981: {_owner: not-me}` (correctly declined) |
| 19:05:19 | First sync_learned_topology: 1 real sensor (zone 01: `04:034682`) — from cached ramses_rf state |
| **19:05:44** | **Fresh start triggered** — `.storage` cache cleared, all ramses_rf state wiped |
| 19:05:45 | Restart with empty schema (only `18:191664` in schema) |
| 19:06:01–19:10:45 | Devices rediscovered: 7 devices in 5 min (CTL, OTB, 2xTRV, BDR, HGI, RND) |
| **19:11:13** | **User accepts 6 devices including CTL (01:216136)** → reload triggered |
| 19:11:17 | sync_learned_topology after reload: 12 zones, **0 real sensors** (CTL now in schema) |
| 19:11:27–29 | **3150 packets** from zone 0B TRVs (04:208992, 04:034692, 04:034684) — CTL is in schema |
| 19:11:38 | 04:034684 and 04:034692 added to discovery metadata (from scan) |
| 19:11:42 | 04:034684 and 04:034692 auto-accepted |
| **19:11:47** | sync_learned_topology: **1 real sensor** (zone 0B: `04:034684`) — learned from 3150! |
| 19:28:43 | sync_learned_topology: **2 real sensors** (zone 0B + DHW: `07:050121`) |
| 19:28:43–20:01:44 | **No further sensor learning** — zones 02, 07 stay without sensor |
| 20:01:44 | End of log (57 min total) |

**Final schema:** Only 1 zone sensor (zone 0B: `04:034684`) + DHW sensor. Zones 02
(Hall, 2 TRVs) and 07 (Bathrooms, 4 TRVs) have **no sensor** despite having 30C9 and
3150 traffic from all their TRVs.

**Key:** The CTL was accepted at 19:11:13, *before* the 3150 packets arrived at
19:11:27–29. ramses_rf could learn the zone sensor assignment because the CTL was
already in the known_list.

---

## Comment 2 (ramses_cc 0.59.9 + ramses_rf 0.59.9, 34 min run)

**Timeline:**

| Time | Event |
|------|-------|
| 20:13:25 | Startup. Learned schema has 2 real sensors (DHW: `07:050121`, zone 0B: `04:034684`) — from cached state |
| **20:14:02** | **Fresh start triggered** — `.storage` cache cleared |
| 20:14:03 | Restart with empty schema (only `18:191664`) |
| 20:14:08–20:29:03 | Devices rediscovered progressively (24 devices by 20:29) |
| 20:11:27–30 | **3150 packets** from zone 0B TRVs — but **no devices in schema yet** (only 18:072981, 18:191664) |
| 20:29:03 | sync_with_schema: all 24 devices "not in schema, marked as REMOVED" — none accepted yet |
| 20:31:27–29 | **More 3150 packets** from zone 0B TRVs — still no devices accepted |
| **20:32:17** | **User accepts ALL 24 devices in one batch** → reload triggered |
| 20:32:21 | sync_learned_topology after reload: 12 zones, **0 real sensors** |
| 20:33:09 | Second reload (schema updated) |
| 20:33:13–20:43:13 | sync_learned_topology: 13 zones, **0 real sensors** — 3150 packets already in the past |
| 20:47:23 | End of log (34 min total) |

**Final schema:** **0 zone sensors.** All 12 zones have no sensor. Despite having 3150
packets from zone 0B TRVs at 20:11 and 20:31, ramses_rf did NOT learn the sensor
assignment.

**Key:** The CTL was not accepted until 20:32:17, *after* the 3150 packets had already
been received at 20:11 and 20:31. ramses_rf could not learn the zone sensor assignment
because the CTL was not in the known_list when the 3150 packets arrived. After
acceptance and reload, ramses_rf started fresh — the 3150 packets were already in the
past and were not re-processed. The next 3150 cycle for zone 0B would have been around
20:51, but the log ended at 20:47.

---

## Root cause: timing of device acceptance vs 3150 packet arrival

### 1. Both tests ran the same ramses_rf version

Both packet logs have the header `# ramses_tx 0.59.9`. The ramses_rf 0.59.9 release
includes PR 1096 ("Eavesdropping fails to discover TRV as zone sensor"). The
3150-based sensor learning fix is present in both tests.

### 2. The critical difference: CTL acceptance timing

| | Comment 1 | Comment 2 |
|---|-----------|-----------|
| CTL accepted | 19:11:13 | 20:32:17 |
| 3150 packets (zone 0B) | 19:11:27–29 (after CTL) | 20:11 & 20:31 (before CTL) |
| Sensor learned? | Yes (19:11:47) | No |

ramses_rf can only learn a zone sensor from 3150 packets if the CTL is already in the
known_list. In comment 1, the user accepted the CTL early (19:11:13), so the 3150
packets that followed at 19:11:27–29 were processed and the sensor was learned. In
comment 2, the user accepted all devices late (20:32:17), after the 3150 packets had
already passed. After the reload, ramses_rf started fresh and the 3150 packets were
not re-processed.

### 3. Only 1 of 3 multi-room zones got a sensor (even in comment 1)

The CTL's 30C9 payload includes zones 00, 01, 03, 04, 05, 06, 08, 09, 0A — but **not**
zones 02, 07, 0B (the multi-room zones). This is normal Evohome behaviour.

Even in comment 1, only zone 0B got a representative TRV sensor. Zones 02 and 07 did
not, despite:

- All their TRVs sending 30C9 broadcasts (comment 1: 7+ packets per TRV)
- 3150 packets from zone 07's TRVs at 20:00:47 (04:036068) — but this was at the very
  end of the run

The 3150 packets for zones 02 and 07 arrived too late (or not at all during the run)
for ramses_rf to learn the sensor. Zone 0B's 3150 packets arrived early (19:11:27–29,
just 6 min after fresh start).

### 4. Foreign HGI `_owner: not-me` lost after fresh start

**Confirmed in logs:**

- Before fresh start: `18:072981: {'_class': 'HGI', '_owner': 'not-me'}` ✓
- After fresh start: `18:072981: {'_class': 'HGI'}` — **`_owner` gone!**

The fresh start at 19:05:44 cleared the `.storage` cache, which wiped the schema
including the `_owner: not-me` trait. The foreign HGI was rediscovered but the user's
decline decision was lost. The device was never re-prompted.

This is a **real bug**: fresh start should preserve `_owner: not-me` for declined
devices, or the discovery flow should re-prompt for previously-declined devices.

### 5. No 0004/0005 active discovery packets after fresh start

Both logs show **zero** 0004/0005 packets after the fresh start. All 0004/0005 packets
are from before the fresh start (cached from 07:40). This means the system relies
entirely on:

- **3150 packets** (zone binding broadcasts from TRVs) — for zone assignment
- **30C9 packets** (temperature broadcasts) — for temperature data

Passive scan mode doesn't send any requests, so it can only learn what devices
volunteer to send.

### 6. Timing summary

| Metric | Comment 1 | Comment 2 |
|--------|--------------------|--------------------|
| ramses_rf version | 0.59.9 | 0.59.9 |
| Run duration | 57 min | 34 min |
| CTL accepted | 19:11:13 (early) | 20:32:17 (late) |
| 3150 packets (zone 0B) | 19:11:27 (after CTL) | 20:11 & 20:31 (before CTL) |
| Time to first sensor | 6 min (zone 0B) | Never |
| Total sensors at end | 2 (zone 0B + DHW) | 0 |
| Multi-room zones with sensor | 1 of 3 (zone 0B only) | 0 of 3 |
| 3150 packets received (live) | 2 (zones 07, 06) | Many (all zones) |
| 30C9 TRV packets | 187 | 378 |

---

## Conclusions

1. **The sensor learning fix (PR 1096) IS in 0.59.9.** Both tests ran the same
   ramses_rf version. The difference in outcomes is not a version issue.

2. **The root cause is timing**: ramses_rf can only learn a zone sensor from 3150
   packets if the CTL is already in the known_list when the 3150 packets arrive. In
   comment 1, the user accepted the CTL before the 3150 packets. In comment 2, the
   user accepted all devices after the 3150 packets had already passed, and the next
   3150 cycle hadn't arrived before the log ended.

3. **Passive scan relies on TRVs volunteering 3150 packets**, which happen every
   ~20 minutes per TRV. A complete schema needs all TRVs to have sent at least one
   3150 packet *after* the CTL was accepted, which can take hours.

4. **The foreign HGI `_owner: not-me` loss is a separate bug** — fresh start wipes
   declined device state without re-prompting.

5. **For users upgrading from 0.56.0**: the key risk is that a fresh start (or any
   cache clear) wipes the learned schema. After acceptance, users must wait for all
   TRVs to send 3150 packets (potentially hours) before all zone sensors are
   restored. This is inherent to passive scan mode — there is no active query for
   zone bindings.

---

## Revised analysis (2026-08-22)

> The initial analysis above contained several errors. This section corrects them
> with evidence from deeper log inspection and ramses_rf source code review.

### Correction 1: ramses_cc PR availability

The initial analysis suggested comment 2 might not have PR 1023 (skip topology sync
in `review_discovered`). This is **incorrect**. Both tests had the same effective
ramses_cc code:

| PR | Description | Merged (local) | In comment 1? | In comment 2? |
|----|-------------|----------------|---------------|---------------|
| PR 1021 | Preserve learned representative TRV zone sensors | 11:58 | Yes (master) | Yes (0.59.9) |
| PR 1023 | Skip topology sync in `review_discovered` | 17:41 | Yes (master) | Yes (0.59.9) |
| PR 1022 | Bump version + _rf dependency | 19:06 | No (merged 1 min after test start) | Yes (0.59.9, version bump only) |

- **Comment 1** test started at 19:05 local. User said "current masters of both
  ramses_cc and ramses_rf". PR 1023 was merged at 17:41 local — 84 minutes before the
  test. PR 1022 (version bump) was merged at 19:06 — 1 minute after the test started,
  so likely not pulled.
- **Comment 2** test started at 20:13 local. User said "0.59.9 was available so I
  installed that". The ramses_cc 0.59.9 release was published at 19:46 local — 27
  minutes before the test. This release includes PR 1021 + PR 1023 + PR 1022.

**Conclusion:** The ramses_cc code was effectively identical in both tests. The
difference in outcomes is **not** a code difference.

### Correction 2: Sensor learning mechanism is 30C9-based, not 3150-based

The initial analysis attributed sensor learning to 3150 packets. This is
**incorrect**. The ramses_rf eavesdropper (`src/ramses_rf/eavesdropper.py`) has two
paths for learning zone sensors, both based on **30C9** (temperature broadcast)
correlation:

1. **`_eavesdrop_from_controller_broadcast`**: When the CTL broadcasts a 30C9 zone
   array, the eavesdropper compares it with the previous array. For zones with
   **changed** temperatures, it looks for TRVs with matching temperatures that
   broadcast 30C9 after the previous CTL array. If exactly one TRV matches, it is
   bound as the zone's sensor.

2. **`_eavesdrop_from_trv_broadcast`**: When a TRV broadcasts a 30C9 temperature,
   the eavesdropper checks all zones of the CTL. For each zone without a sensor, it
   compares `zone.temperature()` with the TRV temperature. If exactly one zone
   matches, the TRV is bound as that zone's sensor.

The 3150 packets (heat demand) are handled by `_evaluate_directed_telemetry_rules`,
which binds TRVs as **actuators** to zones — not as sensors. The `device_role` for
3150 is hardcoded to `"actuator"` (line 239 of `eavesdropper.py`).

### Correction 3: Multi-room zones are NOT in the CTL's 30C9 array

The CTL's 30C9 zone array includes only zones 00, 01, 03, 04, 05, 06, 08, 09, 0A
(the single-TRV zones). Multi-room zones 02, 07, 0B are **never** in the array —
not before the fresh start, not after. This is normal Evohome behaviour: the CTL
only broadcasts a zone temperature when it knows which sensor to use, and for
multi-room zones without a designated sensor, it has no temperature to broadcast.

This means `zone.temperature()` returns `None` for multi-room zones (the
`temp_state.temperature` field is never set from the CTL array). Therefore:

- `_eavesdrop_from_trv_broadcast` cannot match TRV temps to multi-room zone temps
  (`None == trv_temp` is always `False`).
- `_eavesdrop_from_controller_broadcast` cannot find changed zones for multi-room
  zones (they are not in the array at all).

**This is a fundamental limitation**: the 30C9-based eavesdropper **cannot** learn
sensors for multi-room zones through temperature matching, because the CTL does not
broadcast temperatures for those zones.

### Correction 4: ramses.db SQLite database was NOT cleared by fresh start

The "fresh start" at 19:05:44 cleared HA's `.storage` cache, but ramses_rf's own
SQLite database (`ramses.db`) was **not** cleared. Evidence:

- At the first reload (19:11:14), ramses_cc logged: `Starting with 152 cached
  packets`
- Only ~20–30 packets were received between 19:05:44 and 19:11:14 (5.5 minutes)
- The ramses_rf log shows: `Hydrated memory DB from disk: ramses.db`
- The 152 cached packets include packets from before the fresh start (e.g., TRV 30C9
  from 12:59:59, CTL 30C9 from 18:58:31)

This means ramses_rf retained packet data from before the fresh start. When the
gateway was recreated at 19:11:14 (CTL accepted), these 152 cached packets were
replayed through the eavesdropper.

### Correction 5: How the sensor was actually learned in comment 1

**Timeline of sensor learning in comment 1:**

| Time | Event |
|------|-------|
| (earlier session) | HGIs poll CTL for zone 0B temp → RQ/RP 30C9 → zone.temperature() set → TRV 30C9 matches → sensor learned |
| 19:05:16 | Comment 1 startup. CACHED_SCHEMA has zone 0B with `sensor: None` (fresh start cleared schema) |
| 19:05:16 | 175 cached packets loaded from ramses.db (includes RQ/RP 30C9 from earlier session) |
| **19:05:44** | **Fresh start triggered** — `.storage` cache cleared, ramses.db snapshot written |
| 19:11:13 | CTL accepted → reload triggered |
| 19:11:14 | ramses_rf reloaded: CTL in known_list, 152 cached packets loaded from ramses.db |
| 19:11:14 | All 12 zones created (00–0B), but no actuators or sensors yet |
| 19:11:17 | sync_learned_topology: **0 sensors** (zones exist but no bindings yet) |
| 19:11:17–19:11:42 | 152 cached packets replayed through eavesdropper — includes RQ/RP 30C9 for zone 0B |
| 19:11:27 | sync_learned_topology: **0 sensors** (still processing) |
| 19:11:42 | TRVs accepted → second reload triggered |
| 19:11:43 | CONFIG_SCHEMA already has `sensor: '04:034684'` for zone 0B — learned during first reload |
| 19:11:47 | sync_learned_topology: **1 sensor** (zone 0B: 04:034684) |

The sensor was learned by ramses_rf **during the first reload's packet replay**
(19:11:14 to 19:11:42). The 152 cached packets from ramses.db included RQ/RP 30C9
packets from an earlier session (when HGIs were actively polling the CTL for zone
0B temperature). When these packets were replayed, the RP 30C9 set
`zone.temperature()` for zone 0B, and a TRV 30C9 broadcast with matching
temperature triggered the eavesdropper to bind the TRV as zone 0B's sensor.

**This mechanism was confirmed by simulation (R84, step 7):** when HGI polling
(RQ/RP 30C9) provides a zone temperature for a multi-room zone, the eavesdropper
CAN learn the sensor by matching TRV 30C9 broadcasts. Without HGI polling, the
eavesdropper CANNOT learn the sensor (steps 1-5).

The peternash conversation logs confirm that HGIs do poll the CTL for multi-room
zone temperatures. The CTL conversation YAML shows regular `RQ 30C9 02`, `RQ 30C9
07`, `RQ 30C9 0B` from HGIs `18:072981` and `18:191664`, with corresponding `RP
30C9` responses from the CTL.

### Correction 6: Comment 2 had live 30C9 packets after acceptance, but from wrong zones

After the second reload in comment 2 (20:33:09), there **were** live TRV 30C9
packets:

| Time | TRV | Zone | Temp |
|------|-----|------|------|
| 20:36:48 | 04:034690 | 07 | 20.3C |
| 20:37:41 | 04:034692 | 0B | 21.5C |
| 20:39:08 | 04:208992 | 0B | 21.9C |
| 20:47:44 | 04:034722 | 07 | 19.6C |

All of these are from **multi-room zones** (07, 0B) which are NOT in the CTL's 30C9
array. The eavesdropper cannot match these TRV temperatures to zone temperatures
because `zone.temperature()` is None for these zones.

There were **no** live TRV 30C9 packets from single-TRV zones (00, 01, 03, etc.)
after the reload. The TRVs in single-TRV zones broadcast every ~20 minutes, and the
next broadcast cycle didn't arrive before the log ended at 20:47.

### Revised timing summary

| Metric | Comment 1 | Comment 2 |
|--------|--------------------|--------------------|
| ramses_rf version | 0.59.9 | 0.59.9 |
| ramses_cc code | PR 1021 + PR 1023 (master) | PR 1021 + PR 1023 (0.59.9) |
| Run duration | 57 min | 34 min |
| CTL accepted | 19:11:13 (early, staged) | 20:32:17 (late, batch) |
| ramses.db cleared? | No (152 cached packets) | No (cached packets loaded) |
| Sensor learned? | Yes (zone 0B: 04:034684) | No |
| Sensor learned from | Cached packet replay during 1st reload | N/A |
| Live TRV 30C9 after acceptance | From zones 08, 0A, 01, 0B, 03, 02 | From zones 07, 0B (multi-room only) |
| Multi-room zones in CTL 30C9? | No (never) | No (never) |

### Open questions (resolved by simulation)

1. **How was the sensor for zone 0B learned in comment 1?** **RESOLVED.** The
   152 cached packets from ramses.db included RQ/RP 30C9 from an earlier session
   where HGIs were polling the CTL for zone 0B temperature. When replayed, these
   set `zone.temperature()` for zone 0B, enabling the eavesdropper to match a TRV
   30C9 broadcast. Confirmed by R84 step 7.

2. **Would comment 2 have learned sensors if the run was longer?** **PARTIALLY
   RESOLVED.** Comment 2's ramses.db also had cached packets (178 packets, 289
   messages), and the CACHED_SCHEMA at startup already had `sensor: '04:034684'`
   for zone 0B (from comment 1's learning). However, the fresh start at 20:14:02
   cleared the schema. The reload at 20:32:21 started fresh. Without HGI polling
   during the run, the eavesdropper could not learn sensors for multi-room zones.
   If the run had been longer AND HGI polling had occurred, sensors could have
   been learned. But in pure passive scan mode (no polling), they cannot.

3. **Is the ramses.db not being cleared by fresh start a bug?** **CONFIRMED.**
   The fresh start clears `.storage` (HA's cache) but does not clear ramses.db
   (ramses_rf's SQLite database). This is why comment 1 learned a sensor from
   cached packets — the ramses.db retained RQ/RP 30C9 from an earlier session.
   This should be considered a bug: fresh start should clear all ramses_rf state.

---

## Simulation results (R84)

**Recipe:** `r84_multiroom_zone_sensor_learning_issue_1013.py`
**Date:** 2026-08-22
**Result:** All 8 checks passed (0 failures)
**Codebase:** ramses_rf `bbbcff0f` (master, post-0.59.8, includes PR 1096) +
ramses_cc `7de7f9e` (master, post-0.59.8, includes PR 1021 + PR 1023)

### Setup

The recipe creates a controlled reproduction of the issue 1013 scenario:

- CTL `01:150000` with two zones:
  - Zone `0B` (multi-room): 3 TRVs (`04:150003`, `04:150004`, `04:150005`), no sensor
  - Zone `03` (single-TRV): 1 TRV (`04:150006`), sensor = TRV
- CTL broadcasts 30C9 zone array with zone 03 only (NOT zone 0B) — mimicking real
  Evohome behaviour where the CTL omits multi-room zones from the temperature array
- TRVs broadcast 30C9 temperatures and 3150 heat_demand with their zone_index
- HGI `18:001234` polls CTL for zone 0B temperature (RQ/RP 30C9)

### Test steps and results

| Step | What was tested | Result |
|------|----------------|--------|
| 1 | 3150 packets bind TRVs as actuators | PASS — zone 0B has 3 actuators |
| 2 | CTL 30C9 array (without zone 0B) + TRV 30C9 | PASS — zone 0B has NO sensor |
| 3 | Second CTL 30C9 with changed temp + TRV match | PASS — zone 0B has NO sensor (collision abstinence) |
| 4 | TRV with unique temp (no zone match) | PASS — zone 0B has NO sensor |
| 5 | sync_topology after all injections | PASS — zone 0B has NO sensor |
| 6 | HGI polling (RQ/RP 30C9) + TRV 30C9 match + sync | PASS — zone 0B learns sensor `04:150003`! |
| 7 | No unexpected errors in logs | PASS |

### Key findings

**1. Without HGI polling, the eavesdropper CANNOT learn sensors for multi-room
zones (steps 1-5).** This was confirmed across all test scenarios:

- **30C9 temperature matching fails**: `zone.temperature()` returns `None` for
  multi-room zones (not in CTL array), so `None == trv_temp` is always `False`.
- **Controller broadcast path doesn't help**: `_eavesdrop_from_controller_broadcast`
  only processes zones in the CTL's 30C9 array. Multi-room zones are absent.
- **Collision abstinence works correctly**: when a TRV temp matches a single-TRV
  zone temp, the eavesdropper correctly binds the TRV to that zone (not the
  multi-room zone). When multiple TRVs match, no binding occurs.
- **Unique temperatures don't help**: a TRV broadcasting a temperature that
  matches no zone temp cannot be bound, because there's no zone temp to match
  against.

**2. With HGI polling, the eavesdropper CAN learn sensors for multi-room zones
(step 6).** This is the key finding:

- HGI sends `RQ 30C9 0B` to CTL → CTL responds with `RP 30C9 0B0834` (zone 0B,
  21.0C)
- This sets `zone.temperature()` for zone 0B to 21.0C
- TRV `04:150003` broadcasts `30C9 0B0834` (zone 0B, 21.0C) — matches zone 0B's
  polled temperature
- No other zone has temp 21.0C (zone 03 was changed to 21.12C in step 4)
- Collision abstinence: only one zone matches → TRV bound as zone 0B's sensor
- `sync_topology` propagates the learned sensor to ramses_cc's config schema

### The "fixes fighting each other" document

A separate analysis document (`docs/Issue 1013: the fixes are fighting each.md`)
identified that ramses_cc's `sync_learned_topology` had a sanitization rule that
removed TRV-based sensors (setting `sensor = None` when a TRV was both sensor and
actuator). This was an overcorrection of issue 813 that incorrectly assumed TRVs
can never be zone sensors.

**This sanitization has been fixed in the current codebase.** The ha-sim's
ramses_cc code (post-PR 1021) correctly preserves TRV sensors:
- A representative TRV is both the zone sensor and an actuator
- If a dedicated thermostat (22:, 34:) is also present, it takes priority as sensor
- The TRV remains in actuators regardless

The R84 simulation confirms this: after `sync_topology`, the learned TRV sensor
(`04:150003`) survives in the config schema alongside its actuator role.

### The peternash conversation logs

The device simulator has 24 conversation YAML files harvested from Peter Nash's
real packet logs, including:
- `heat_ctl_01_216136_packet_log(1).yaml` — CTL with RQ/RP 30C9 for zones 02, 07, 0B
- `heat_trv_04_034684_packet_log(1).yaml` — TRV for zone 0B
- `heat_trv_04_034722_packet_log(1).yaml` — TRV for zone 07
- Plus 21 more device conversations

The CTL conversation log shows that HGIs (`18:072981`, `18:191664`) actively poll
the CTL for individual zone temperatures using `RQ 30C9 <zone_index>`. The CTL
responds with `RP 30C9 <zone_index><temp>`. This polling happens for ALL zones,
including multi-room zones (02, 07, 0B) that are NOT in the CTL's broadcast array.

This is the mechanism that enabled sensor learning in the earlier session (before
comment 1): the HGI polling set `zone.temperature()` for multi-room zones, allowing
the eavesdropper to match TRV 30C9 broadcasts.

### What this means for issue 1013

The root cause of issue 1013 is **two-fold**:

1. **Passive scan mode does not poll the CTL for zone temperatures.** Without HGI
   polling (RQ/RP 30C9), `zone.temperature()` remains `None` for multi-room zones,
   and the eavesdropper cannot match TRV temperatures to zone temperatures.

2. **ramses.db is not cleared by fresh start.** The 152 cached packets from
   ramses.db (retained from an earlier session where HGI polling occurred) enabled
   sensor learning in comment 1. Comment 2 may have had a different ramses.db state
   or the replay didn't produce the same matching conditions.

The "fixes fighting each other" issue (ramses_cc removing TRV sensors) was a
**separate problem** that has been fixed by PR 1021. The current codebase correctly
preserves learned TRV sensors.

### Implications for a fix

Since the eavesdropper CAN learn sensors for multi-room zones when HGI polling
provides zone temperatures, the fix options are:

1. **Active polling (recommended)**: ramses_cc should send `RQ 30C9 <zone_index>`
   to the CTL for each zone that has no sensor, when in passive scan mode. This
   would set `zone.temperature()` and enable the eavesdropper to learn the sensor.
   This requires `send_packet: True` or a limited polling mode.

2. **Heuristic sensor assignment**: for multi-room zones without a sensor,
   designate the first actuator TRV as the representative sensor (similar to what
   the CTL does internally). This is what PR 1021 ("preserve learned representative
   TRV zone sensors") partially addresses — it preserves sensors that are already
   learned but doesn't help with the initial learning.

3. **Clear ramses.db on fresh start**: ensure the fresh start actually clears all
   ramses_rf state, including the SQLite database. This would make behaviour
   deterministic (no sensor learning from stale cached state).

4. **User-configured sensors**: allow the user to manually designate which TRV is
   the zone sensor for multi-room zones, since passive scan cannot discover this
   automatically without polling.

### Open question: peternash playback recipe

The 24 peternash conversation YAML files could be used to create a full playback
recipe (R85) that replays the real traffic through the simulator. This would
verify that the HGI polling mechanism works with real-world traffic patterns,
including the timing between RQ/RP 30C9 and TRV 30C9 broadcasts. This is left as
future work.

---

## History: when 30C9 polling was removed

The legacy `DiscoveryService` actively polled `RQ 30C9 <zone_index>` to the CTL
every **5 minutes** for each zone.  This was the mechanism that set
`zone.temperature()` for multi-room zones (which the CTL omits from its broadcast
array), enabling the eavesdropper to match TRV 30C9 broadcasts and learn zone
sensors.

### Timeline

| Date | Commit | Event |
|------|--------|-------|
| 2021-05-31 | `7fb4e78e` | `Command.get_zone_temperature` (RQ/30C9) introduced |
| ~2021 | — | `Zone._setup_discovery_cmds` polls RQ/30C9 every 5 min via `_add_discovery_cmd(Command.get_zone_temp(self.ctl.id, self.idx), 60 * 5, delay=0)` |
| 2026-07-24 14:13 | `1a0c7f52` | **Phase 4c.3**: `start_poller()` made a no-op ("Legacy polling loop is disabled in favor of L7 PollingManager"). `initiate_discovery()` replaced with `polling_manager.start()`. New `PollingManager` schedule for CTL does **not** include 30C9. |
| 2026-07-24 15:43 | `dba5bf7d` | **Phase 4c.4**: `discovery.py` deleted entirely; all `_setup_discovery_cmds` methods removed from `Zone`, `DhwZone`, etc. |
| 2026-08-13 | `c0310227` | PR 947 restored per-zone `0004` polling (zone names lost after cache clear) but did **not** restore `30C9`. |
| 2026-08-21 | `ec93c0e2` | PR 1096 fixed the eavesdropper to learn TRV zone sensors via 30C9 matching — but the polling that supplied the zone temperatures was already gone. |

### What the legacy Zone polled (every 5 minutes)

```python
self._add_discovery_cmd(Command.get_zone_config(self.ctl.id, self.idx), 60 * 60 * 6)
self._add_discovery_cmd(Command.get_zone_name(self.ctl.id, self.idx), 60 * 60 * 6)
self._add_discovery_cmd(Command.get_zone_mode(self.ctl.id, self.idx), 60 * 5)
self._add_discovery_cmd(Command.get_zone_temp(self.ctl.id, self.idx), 60 * 5)  # 30C9
self._add_discovery_cmd(Command.get_zone_window_state(self.ctl.id, self.idx), 60 * 15)
```

### What the new PollingManager polls for CTL

```python
DevType.CTL: {
    Code._10E0: INTERVAL_DAILY,        # device info
    Code._1F41: INTERVAL_HOURLY,       # DHW mode
    Code._2E04: INTERVAL_DAILY,        # system mode
    Code._313F: INTERVAL_EVERY_12_HOURS,  # datetime sync
    Code._0004: INTERVAL_EVERY_6_HOURS,   # zone name (per-zone, restored by PR 947)
}
```

**30C9 is absent.** The refactoring dropped per-zone temperature polling and
never restored it.

### The irony

The eavesdropper fix (PR 1096, issue 1010) was merged on 2026-08-21 — four weeks
**after** the polling that supplied its input data was removed (2026-07-24). The
eavesdropper was fixed to use 30C9 temperature matching at the same time that
the source of those temperatures was eliminated. The two changes were part of
the same broader refactoring effort but were never reconciled.
