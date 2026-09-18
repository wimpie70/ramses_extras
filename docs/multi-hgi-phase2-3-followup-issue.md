# Follow-up issue: multi-HGI pool — Phase 2 (serial/hybrid) and Phase 3 (Zigbee)

**Source plan:** [`multi-hgi-plan.md`](../multi-hgi-plan.md) (repo root)
**version:** Sep 15 2026 19:30
**Scope:** Continue the phased rollout of transport-neutral HGI pooling after
Phase 1 (MQTT-only pool) ships. Phase 2 adds serial and hybrid USB+MQTT pools;
Phase 3 adds Zigbee pools once physical hardware is available.

## Current status (2026-09-15)

### Phase 2 — COMPLETE

Phase 2 (serial and hybrid pool) is **complete and verified on real hardware**:

- **ramses_rf PR 1208** (`feat/phase2-signature-policy`): **MERGED** (2026-09-12). Head `6fb694e7`. Includes all pool work: `PoolChild` state model, typed routing contract, MQTT callback contract, serial/hybrid pool support, callback-driven `mark_online()`, stale child fallback.
- **ramses_cc PR 1183** (`fix/issue-1171-pool-config-bugs`): **OPEN**, not draft, awaiting review. Head `333988ff`. Includes pool health entities, config flow improvements, test alignment. CI: lint/type/hassfest/HACS pass; test/coverage blocked only by `ramses-rf==0.60.5` pin (needs 0.60.6 publish).
- **ramses_extras** (commit `2059b77`): dynamic default sensor creation for newly discovered devices + pool health entity integration in `TransportMonitor`.

### Phase 3 — IN PROGRESS (hardware verified)

Physical Zigbee hardware is now available (Elecram ESP32-C6 running
IMMRMKW's `ramses_esp` firmware, paired via ZHA) and the Zigbee pool is
**verified end-to-end on hardware (2026-09-15)**:

- Zigbee child connects via ZHA, receives RAMSES packets, and
  participates in RSSI-based TX routing.
- Full TX path proven: pool → Zigbee cluster → C6 → RF → over-air echo
  heard by a second HGI → pool deduplicates the child's own RX copy.
- The ramses_esp HGI identity is derived from the IEEE address
  (`18:254172` for the C6) — no synthetic IDs needed.
- Regression tests and `ha_sim_test` recipe R126 added; full suites run.

Remaining before release: ZHA availability→`PoolChild` mapping, docs,
draft PRs.

## Background

The multi-HGI plan delivers **multi-dongle spatial diversity**: a single
software `Gateway` in `ramses_rf` sitting on top of a link-layer transport pool
(`PooledTransport` in `ramses_tx`) that communicates with two or more physical
dongles (USB/serial, MQTT, or Zigbee). It does **not** create multiple software
gateways.

The rollout is phased because several foundations must be corrected before
USB/serial and Zigbee configurations can be described as safe. **Phasing is
implementation order, not a reduction in scope** — multi-USB, hybrid, and
Zigbee operation are release criteria for the complete feature.

### Phase 1 status (done — ready for release)

Phase 1 (MQTT-only pool) is implemented, verified on real hardware, and all
issue 1171 config bugs are fixed:

- PR 1 (ramses_rf PR 1184): `PoolChild` state model, ingress provenance, O(1)
  dedup, `RssiTracker` TTL — implementation complete, tests passing, verified
  on real hardware.
- PR 2 (ramses_rf PR 1194): typed `prepare_command()`/`write_routed()` routing
  contract, `SourcePolicy`, `WriteOutcome` — implementation complete, CI green.
- PR 4A (ramses_rf PR 1195, merged): transport-neutral MQTT callback contract.
  Published in `ramses-rf==0.60.5`.
- PR 4B (ramses_cc PR 1157, merged): HA-native `RamsesMqttPoolBridge` driving
  multiple HGIs through one `homeassistant.components.mqtt` connection.
- PR 5 (ramses_cc PR 1133 / fork PR 5): canonical schema-ownership membership,
  config flow, MQTT pool assembly, serial/Zigbee gating — implementation
  complete, draft PR open.
- PR 1178 (ramses_cc, this branch): issue 1171 config bug fixes — pool
  removal, re-add, display, healing, sentinel filtering, CI coverage.
- **Issue 1171 follow-up (2026-09-11, branch `fix/issue-1171-pool-config-bugs`):**
  three additional fixes for the pool management UI:
  - **Simplified USB→MQTT switch step** (commit
    `615726d3`): when a non-primary HGI switches from USB to MQTT via
    the pool management UI, the config flow now redirects to
    `manage_pool_mqtt_url` and only asks for HGI ID and an optional
    topic prefix (HA MQTT broker is always used; no
    host/port/credentials are collected). Previously it only changed
    `_preferred_type` and removed the serial port without collecting
    any MQTT info.
  - **MQTT bridge creation for non-primary `_preferred_type: mqtt`**
    (commit `68a455cc`): the coordinator's MQTT activation gate now
    includes schema HGIs with `_preferred_type: "mqtt"`, so the MQTT
    pool bridge is created even when the primary is serial.
  - **HGI comment warning migration** (commit `61b45209`): HGI
    `_comment` fields now include the warning suffix
    ` (don't edit here — adapt with the Pool Management config)`.
    A migration in `coordinator.async_setup` appends the warning to
    existing comments on startup. The warning text avoids the words
    `usb`, `mqtt`, and `zigbee` so comment-based transport detection
    is not broken.
  - **Regression test R123** added to `ha_sim_test` covering all three
    fixes (21 checks, all pass).

Live hardware test results (2026-09-05, hass, 2 ESP32 MQTT HGIs): 11/11 test
scenarios pass (dual-MQTT, hybrid serial+MQTT receive, LWT failover, broker
restart, unplug/reconnect, outbound failover). 6 bugs found during live testing
were fixed. Release-readiness audit: 7 blockers found, 6 fixed in-cycle, 1
(published dependency) resolved with `ramses-rf==0.60.5`.

Issue 1171 live hardware test results (2026-09-07, hass, 2 ESP32 MQTT HGIs +
1 USB ESP): 6/6 test scenarios pass:
- USB-only primary (serial connection, no pool bridge)
- USB primary + MQTT add blocked (error shown, re-add options hidden)
- 1 MQTT (HA MQTT primary, HGI discovered and accepted)
- 2 MQTT + dedup (both HGIs online, duplicate packets deduped)
- Remove both MQTT HGIs with confirmation (pool cleared, no re-enrichment)
- No "healing" of empty serial_port on restart

See the "PR implementation status" and "Live hardware test results" sections of
[`multi-hgi-plan.md`](../multi-hgi-plan.md) for full details.

### What is gated in Phase 1

In the config flow, when adding a pool child, only MQTT transport is selectable.
Serial and Zigbee options appear in the UI but are marked "(not yet supported)"
and cannot be selected. `TODO: re-enable when Phase 2` (serial) and
`TODO: re-enable when Phase 3` (Zigbee) remarks mark the gating points. The
underlying `PortTransport` and `ZigbeeTransport` classes are **not modified or
removed** — they remain ready for un-gating. The coordinator defensively
filters non-`mqtt://` ports from pool construction.

Re-add of removed HGIs is also gated: the "Re-add HGI" dropdown options are
only shown when the primary transport is MQTT or empty (not serial).

---

## Phase 2 — Serial and hybrid pool

**Status: COMPLETE (2026-09-12).** Verified on real hardware (hass, 2 ESP32 MQTT HGIs + 1 USB ESP).

**Goal:** make `PortTransport` a fully send-capable pool child alongside MQTT
children, without reintroducing ESP32 USB startup reset loops. Un-gate serial
transport in the config flow.

**Prerequisite:** the **serial hardware feasibility gate** ~~must pass before
PR 3 starts~~ **PASSED 2026-09-06** (see below).

**Delivery PR:** PR 3 — Full pooled serial transmission and reconnect
(`ramses_rf`, merged into PR 1208). **MERGED 2026-09-12.**

### Hardware feasibility gate (Phase 2 prerequisite) — PASSED 2026-09-06

**Status: PASSED** (2026-09-08, 2x ESP32 USB JTAG serial debug units)

**Hardware tested:** 2x ESP32 USB JTAG serial debug units:
- `/dev/ttyACM0` (CC:BA:97:09:FC:BC), firmware 0.6.6c
- `/dev/ttyACM1` (CC:BA:97:0A:47:F0)

**Test tools:**
- `tools/esp_usb_feasibility_test.py` — async, requires `serialx` (from ramses_rf venv)
- `tools/esp_usb_feasibility_standalone.py` — standalone, requires only `pyserial`

This gate blocks Phase 2, not Phase 1. ~~Before PR 3 starts, reproduce and
characterize the ESP USB behavior with the same physical device in both the
existing single-port path and a minimal pooled-child harness.~~ **Done.**

**Result: PASS.** Pooled serial transmission is feasible with a delayed
startup policy. Full report: `docs/serial_hw_gate_report.md`.

**Root cause:** pyserial sets DTR=True/RTS=True on port open. The ESP32-S3
uses DTR/RTS for auto-reset. The transition pulses EN and resets the chip.
This is a one-time reset per port open, **not a reset loop**. The ESP32 boots
in ~1.9s (cold) or ~0.4s (warm WiFi) and then operates normally with ~10ms
echo latency.

**Our test results (dual-port, 13/13 steps passed, 0 resets detected):**

| Test | Port 1 | Port 2 | Notes |
|------|--------|--------|-------|
| Port open (no write) | PASS | PASS | No reset, no spurious data |
| Immediate 7FFF probe | PASS | PASS | Echo received (86-103 bytes) |
| Repeated probes (5x) | PASS | PASS | 5 echoes each (430 bytes), no reset loop |
| Delayed probe (2s grace) | PASS | PASS | Echo received (86-140 bytes) |
| Ordinary RF write | PASS | PASS | Response received (52 bytes) |
| Close/reopen | PASS | PASS | Reopened successfully, no reset |
| Dual simultaneous write | PASS | — | Both ports echoed simultaneously |

**Key finding:** The ESP32 USB JTAG serial debug units (firmware 0.6.6c) do NOT
exhibit the reset loop problem. Immediate writes, repeated writes, close/reopen,
and dual-port simultaneous writes all work without triggering an ESP reset.

**Current code handling of reset-prone ESPs:** The existing `PortTransport` has
a binary `disable_sending` flag. When `True`, it skips the signature probe
entirely (`connect_sans_signature`) and blocks all writes — the child becomes
permanently receive-only with no HGI ID. When `False`, it sends immediate
signature probes (40x, 0.05s gap) which would trigger reset loops on affected
hardware. The Phase 2 plan (PR 3) splits this into `signature_policy:
"immediate"|"delayed"|"skip"` + `startup_grace: float | None` to allow a
delayed probe after the ESP stabilizes.

**Recommended Phase 2 defaults:**
- `signature_policy = "id_command"` with `startup_grace = 3.0s` for pooled serial
  children (grace period is once per port open, not per message). `ID_COMMAND`
  sends `!I` to query the HGI ID after the grace period; this is the implemented
  policy (the original recommendation was `delayed`).
- `signature_policy = "immediate"` for non-pooled single-USB (backward
  compatible).
- Do NOT change DTR/RTS after open — any transition resets the ESP32.
- `disable_sending` remains a permanent send permission flag, not a startup
  workaround.

**Hybrid USB+MQTT test:** Both transports can receive RF frames independently.
A ramses_esp 0.4.9 firmware crash was found when MQTT TX is sent to an ESP32
that is also on USB serial — this is a firmware bug, not a pool issue. The
pool design prevents this scenario (an HGI is either a USB child or an MQTT
child, never both). The crash should be reported to the ramses_esp project.

**Remaining hardware evidence (for Phase 2 release, not feasibility gate):**
- ~~Two-USB pool test~~ **Done — PASS.** Both ports opened simultaneously, both received RF independently, both transmitted cleanly, cross-dongle over-air copy confirmed.
- ~~USB unplug/reconnect test~~ **Done — PASS.** Device unplugged, detected via `os.path.exists()`, reconnected after ~28s, ESP booted, echo received. No reset loop on reconnect.
- Cross-dongle over-air copy with active RF traffic — partially confirmed.
- Traditional evofw3/HGI serial device (not available). A standalone test
  script (`tools/esp_usb_feasibility_standalone.py`) has been written for
  Egbert to run on his traditional evofw3 device. It requires only `pyserial`.

Test tools: `tools/serial_hw_gate.py`, `tools/hybrid_usb_mqtt_test.py`, `tools/two_usb_test.py`, `tools/esp_usb_feasibility_test.py`, `tools/esp_usb_feasibility_standalone.py`.

### PR 3 — Full pooled serial transmission and reconnect

**Repository:** `ramses_rf`
**Depends on:** PR 2 (PR 1194), PR 5 (Phase 1 release), and the serial hardware
feasibility gate (**PASSED 2026-09-06**).
**Phase:** 2 — serial and hybrid pool.

Make `PortTransport` a fully send-capable pool child without reintroducing ESP
startup reset loops. This PR un-gates serial transport in the config flow
(removes the "(not yet supported)" marker and `TODO:` remarks from Phase 1) and
enables serial children in pool construction.

#### Implementation

- Split startup signature policy from permanent `disable_sending`.
- Add explicit immediate, delayed, and skipped signature behavior. Defaults
  preserve the existing non-pooled single-USB behavior; pooled ESP defaults
  come from the completed hardware gate.
- Add new `TransportConfig` fields with backward-compatible defaults and
  coordinate any `ramses_cc` configuration plumbing without requiring existing
  callers to change.
- Obtain the RAMSES HGI ID through `ID_COMMAND` (`!I` query), firmware
  announcement, or validated configured identity.
- Keep identity-unknown serial children receive-only and not send-ready.
- Mark the child send-ready only after identity and startup safety are
  established.
- Preserve HGI80 placeholder behavior.
- Add bounded serial reopen/reconnect backoff using stable
  `/dev/serial/by-id/...` paths where available.
- Propagate serial read/write/disconnect failures into the child state model.
- Apply the PR 2 proven-not-submitted-versus-ambiguous outcome policy to serial
  writes.
- **Hybrid pool construction (ramses_cc):** the coordinator must build a single
  `PooledTransport` that combines serial children (via serialx transport) and
  MQTT children (via the HA-native `RamsesMqttPoolBridge`, callback-driven).
  This is the core of Phase 2 — mixed serial+MQTT pools are the whole goal.
  - Serial primary + MQTT additional: serial children via
    `pooled_transport_factory`, MQTT children via `RamsesMqttPoolBridge`.
  - MQTT primary + serial additional: MQTT children via
    `RamsesMqttPoolBridge`, serial children via `pooled_transport_factory`.
  - Both directions produce one `PooledTransport` with mixed transport-driven
    and callback-driven children.
- **No paho in ramses_cc (invariant):** MQTT pool children inside HA always
  go through the HA-native `RamsesMqttPoolBridge`
  (`homeassistant.components.mqtt`), never through paho transports.  The
  `pooled_transport_factory` is used only for serial (serialx) children.
  Paho is permitted only in the standalone `ramses_rf` CLI when run without
  `ramses_cc` and without HA.
- **ramses_cc side:** remove the serial gating in the `manage_pool` config-flow
  step (drop the `pool_serial_not_supported` error and the "(not yet
  supported)" label). Remove the defensive `mqtt://`-only filter in
  `_create_pool_transport_constructor` so serial ports reach
  `PooledTransport`. Remove the `TODO: re-enable when Phase 2` remarks.

#### Regression tests required

- Skipping the startup signature no longer implies permanent read-only
  operation.
- A delayed signature obtains and validates the HGI ID.
- Identity-unknown serial children receive but are not selected for outbound
  routing.
- A configured identity is checked against a later observed identity.
- Physical disconnect excludes the serial child immediately.
- Reconnect does not restore send readiness until identity is valid.
- A driver-proven not-submitted serial outcome can prepare another child.
- A generic or ambiguous serial write failure does not duplicate the command.
- Existing single-USB startup and transmission remain unchanged.
- Serial and Zigbee transport types are un-gated/remaining-gated correctly in
  the config flow (serial selectable, Zigbee still "(not yet supported)").
- Hybrid pool: serial primary + MQTT additional constructs a single
  `PooledTransport` with serial (transport-driven) and MQTT
  (callback-driven, HA-native) children.
- Hybrid pool: MQTT primary + serial additional constructs the same mixed
  pool in the reverse direction.
- No paho transport is instantiated inside `ramses_cc` for any pool
  configuration (serial-only, MQTT-only, or hybrid).

#### Required release hardware evidence

- Traditional evofw3/HGI serial device starts and sends normally.
- ESP32 USB device does not reset-loop during startup.
- Normal post-startup ESP32 USB transmission succeeds.
- Two serial HGIs can each be forced as the selected route and produce the
  expected echo.
- Unplugging and reconnecting one serial child preserves operation through the
  other.

#### Completion criteria

- Automated tests prove that either prepared serial child can be selected and
  that no serial child is selected before it is send-ready.
- Existing single-USB tests remain unchanged and pass.
- Focused tests, full `ramses_rf` tests, Ruff, and strict mypy pass.
- The feature remains incomplete for release until the required two-USB and ESP
  hardware evidence is recorded.

### Phase 2 release gate

After PR 3 is complete and the hardware feasibility gate has passed, run the
Phase 2 release gate:

- [x] All Phase 1 gate items still pass.
- [x] Record physical two-USB and USB-plus-MQTT results. — **2026-09-09, scenarios C+E PASS**
- [x] Verify USB unplug/reconnect and ESP restart/LWT against the integrated
      stack. — **2026-09-09, scenario D PASS**
- [x] Verify serial transport is un-gated in the config flow. — **Serial selectable as "USB (serial)", only Zigbee remains gated**
- [x] Full `ramses_rf`, `ramses_cc`, and `ramses_extras` suites pass.
- [x] Complete `ha_sim_test` recipe set passes (0 failures).
- [x] Diagnostics review: no credentials exposed; per-child state, identity,
      route evidence, failures, and reconnects visible.

### Phase 2 definition of done

The serial and hybrid pool feature is complete only when all of the following
are additionally true:

1. [x] Serial transport is un-gated in the config flow (the "(not yet supported)"
   marker and `TODO:` remarks are removed).
2. [x] `PortTransport` is a fully send-capable pool child without ESP startup reset
   loops. — **`SignaturePolicy` (IMMEDIATE/DELAYED/SKIP/ID_COMMAND),
   `startup_grace`, `configured_hgi_id` implemented in `ramses_tx`;
   `pooled_transport_factory` supports per-child config overrides**
3. [x] Serial and HA-native MQTT adapters pass equivalent routing/lifecycle tests.
4. [x] Full repository suites, complete `ha_sim_test`, diagnostics review, and
   mandatory physical two-USB and USB-plus-MQTT release evidence pass.
5. [x] USB unplug/reconnect and ESP restart/LWT behavior verified against the
   integrated stack.

---

## Phase 3 — Zigbee pool

**Goal:** un-gate Zigbee transport in the config flow and correct the two
identity domains (Zigbee IEEE transport address vs. RAMSES `18:` HGI ID) and
availability behavior once physical hardware is available for testing.

**Prerequisite:** physical Zigbee hardware is available for testing, and the
RAMSES HGI identity / IEEE address separation is correct.

**Delivery PR:** PR 6 — Correct Zigbee identity and lifecycle (`ramses_rf`,
new focused PR; separate `ramses_cc` PR if configuration changes are required).

Zigbee pool support is **implemented and hardware-verified (2026-09-15)**.
Tested device: Elecram ESP32-C6 running IMMRMKW's `ramses_esp` firmware
(v0.3), paired to ZHA on the development HA instance.

**ramses_esp identity model (firmware `device.c`):** the gateway ID is
derived from the last three bytes of the ESP base MAC,
`(mac[3]<<16 | mac[4]<<8 | mac[5]) & 0x3FFFF`, class `18:`. The Zigbee
IEEE address is that base MAC expanded to EUI-64 via a `ff:fe` insertion,
so the derivation is reversible. Verified against real devices:

| Device | Base MAC | IEEE (EUI-64) | Derived HGI | Actual HGI |
|--------|----------|---------------|-------------|------------|
| Elecram C6 | `10:bd:a3:a7:e0:dc` | `10:bd:a3:ff:fe:a7:e0:dc` | `18:254172` | `18:254172` |
| USB ESP32 | `cc:ba:97:09:fc:bc` | `cc:ba:97:ff:fe:09:fc:bc` | `18:130236` | `18:130236` |
| USB ESP32 | `cc:ba:97:0a:47:f0` | `cc:ba:97:ff:fe:0a:47:f0` | `18:149488` | `18:149488` |

No synthetic HGI ID scheme is needed for `ramses_esp` hardware. Other
Zigbee RAMSES bridge firmware may use a different identity scheme — for
those, `configured_hgi_id` remains the explicit override and the
`18:000730` sentinel keeps the child receive-only.

### PR 6 — Correct Zigbee identity and lifecycle

**Repository:** `ramses_rf`; use a separate follow-up `ramses_cc` PR if
configuration changes are required.
**Depends on:** PR 2 (PR 1194), physical Zigbee hardware availability.
**Phase:** 3 — Zigbee pool.

#### Implementation

- [x] Store the Zigbee IEEE transport address separately from the RAMSES
  HGI ID. — `_resolve_hgi_id()` in `ZigbeeTransport`; the IEEE is only
  used for ZHA endpoint selection.
- [x] Define one explicit source for the RAMSES HGI identity. —
  precedence: `configured_hgi_id` > firmware-compatible derivation from
  the IEEE (`_hgi_id_from_ieee`, ramses_esp convention) > `18:000730`
  sentinel.
- [x] Use IEEE only for Zigbee endpoint selection.
- [x] Use the `18:` HGI ID only in RAMSES commands.
- [x] Map ZHA device availability into `PoolChild` state. — two
  mechanisms: (a) a coordinator watcher reloads the entry once the ZHA
  gateway appears when a child failed at setup (capped attempts; see
  degraded-boot fixes below); (b) a per-device availability monitor in
  the Zigbee transport (ramses_rf PR 1224) subscribes to the device's
  `zha_event` offline signal, polls `available`/`on_network`/`last_seen`
  freshness with a Basic-cluster ping fallback, drops the child from
  routing via `connection_lost`, and reconnects via `connection_made`
  on signs of life.
- [x] Keep identity-unknown Zigbee children receive-only. — sentinel
  children are excluded from `accepted_hgis` and never TX-selected.
- [x] **ramses_cc side:** Zigbee un-gated in `manage_pool` (gating
  error, "(not yet supported)" labels, `TODO: Phase 3` remarks removed;
  `pool_zigbee_not_supported` / `pool_serial_not_supported` translation
  keys removed). Pool-add flow registers the derived HGI in the schema
  with `_owner: me` and `_preferred_type: zigbee` (send-capable without
  manual acceptance; excluded from the MQTT bridge so no phantom child).
- [x] Hybrid pool construction for MQTT-primary + Zigbee additional
  ports (`primary_is_mqtt` path; Zigbee children get
  `SignaturePolicy.SKIP`, no `!I` probing, no DTR handling).
- [x] `_ChildProtocolProxy.wait_for_connection_made` now fails fast on
  `connection_lost` — a Zigbee child that cannot reach ZHA no longer
  stalls pool construction for the 60s Zigbee timeout.

#### Physical evidence (2026-09-15, dev instance)

Pool: `mqtt_ha` primary + `mqtt://.../18:130236` +
`mqtt://.../18:149488` + `zigbee://10:bd:a3:ff:fe:a7:e0:dc/...`:

```text
HybridPool: creating pool with 1 serial children + 2 MQTT callback
children: serial=['zigbee://10:bd:a3:.../...'], mqtt=['18:130236',
'18:149488']
Zigbee transport ready: ieee=10:bd:a3:ff:fe:a7:e0:dc cluster=0xfc00
attr=0x0000 (hgi_id=18:254172)
PooledTransport: child 0 connected (HGI=18:254172), 3/3 connected
_select_child candidates=[0, 1, 2] rssi={0: -83.0, 1: -37.0, 2: -999.0}
```

Forced TX through the Zigbee child (other HGI disabled):

```text
PooledTransport: selected child 0 (hgi=18:254172) for target 32:153289
Zigbee TX 1/1: RQ --- 29:176861 32:153289 --:------ 2411 003 000075
Recv'd: -32 RQ --- 29:176861 32:153289 ...   # over-air echo on MQTT HGI
PooledTransport: deduped packet from child 0: RQ --- ...
```

Per-child health entity created
(`binary_sensor.hgi_18_254172_online`), stale IEEE/`18:000730` registry
entries removed.

#### Degraded-boot fixes (2026-09-16, SLZB offline at startup)

A boot with the Zigbee coordinator down exposed three stacked issues,
all fixed and covered:

- `pooled_transport_factory` waited for a connected child *before* the
  MQTT bridge could attach — a pool whose transport children all failed
  could never satisfy it. Now skipped when callback children are
  reserved (ramses_rf PR 1223).
- `entry.runtime_data` was assigned before `async_setup()` and never
  cleared on failure — HA's retry hit the "already set up" guard,
  leaving a zombie integration. Now assigned only after setup succeeds.
- `async_attach_to_pool` never bound the gateway protocol when no
  transport child connected — `client.start()` would still time out.
  It now binds like `create_pool` does.
- New: `_schedule_zigbee_rejoin` watches for the ZHA gateway and
  reloads the entry once it appears (max 3 attempts) so a failed
  Zigbee child rejoins without a manual restart.
- New (ramses_rf PR 1224): per-device availability monitor covers the
  *runtime* case — the C6 dropping off the Zigbee network while the
  pool is running. `connection_lost` drops the child from routing;
  fresh `last_seen`/ping triggers reconnect. Also fixes
  `mark_connected()` to restore `child.transport` on reconnect.

Verified live: SLZB powered off → pool up with both MQTT HGIs online
via LWT and live traffic flowing, Zigbee child entity correctly
unavailable.

#### Startup-wrap-up block (2026-09-18, SLZB offline at startup)

A degraded boot left `hass.config.state` stuck below `RUNNING` for
minutes, which latched every `ramses_extras` frontend card into its
"Home Assistant is initializing" state even though the backend and
websocket layer were fully up. HA logged
`Something is blocking Home Assistant from wrapping up the start up
phase` with three tracked tasks pending.

Root cause: fire-and-forget tasks created with
`hass.async_create_task` are awaited by `async_block_till_done`
during startup wrap-up. With the Zigbee coordinator offline these
never finished:

- `RamsesCoordinator._schedule_zigbee_rejoin._watch` — polled for the
  ZHA gateway indefinitely.
- `RamsesServiceHandler._async_run_fan_param_sequence` — ~30-param
  sweep, up to 30 s/param on a degraded transport (spawned from
  `services.py` and `coordinator.get_all_fan_params`).
- `RamsesFanHandler.async_setup_fan_device.on_fan_first_message` —
  waited for the device's first packet, then ran the same sweep.
- `coordinator._probe_task` — probe-and-discover, ~20 s+/device.

All are now `async_create_background_task` (still cancelled on entry
unload / HA stop), so they cannot delay startup wrap-up. The rejoin
watcher additionally unregisters its own unload-cancellation before
calling `async_reload` (self-cancellation guard) and is deduplicated
against a pending watcher. Verified live: SLZB powered off → HA
reaches `state: RUNNING` in ~70 s, `get_cards_enabled` returns true,
no bootstrap-block warnings.

Companion fixes in ramses_rf (`fix(protocol): quiet expected pool
lifecycle noise`):

- `ZigbeeTransport._async_init` logs expected `TransportZigbeeError`
  (missing ZHA gateway/device) as a warning without a traceback —
  unexpected failures still log with `_LOGGER.exception`.
- `connection_lost` retrieves exceptions set on
  `_wait_connection_lost` and abandoned send futures, eliminating
  `Future exception was never retrieved: TransportZigbeeError`.
- `PortProtocol.connection_made` no-ops when already connected —
  a second pool child coming online (or a reconnect racing a queued
  `connection_lost`) no longer re-runs active-HGI detection and no
  longer logs `Active gateway already set ... overwriting`.

Design note: mid-operation coordinator/device failure does **not**
block HA — the Zigbee transport's own availability loop (not an
HA-tracked task) marks the child offline and retries; only the
startup-phase `wait_for_gateway` poll (30 s, bounded) is on the
connection path.

#### Regression tests required

- [x] IEEE addresses are never inserted into RAMSES frames. —
  `TestResolveHgiId.test_resolved_id_is_never_the_ieee` +
  `TestHgiIdFromIeee` vectors (`tests_tx/test_transport_zigbee.py`).
- [x] An identity-unknown Zigbee child is never selected for
  transmission. —
  `test_sentinel_hgi_zigbee_child_is_receive_only`
  (`tests_tx/test_transport_pooled.py`).
- [x] ZHA unavailable/recovery events update only the relevant child. —
  covered by failure isolation: `test_child_connection_lost_fails_wait_promptly`
  + recipe R126 (`zigbee://` child fails fast without ZHA; MQTT callback
  children unaffected). Late ZHA availability recovers the child via
  `_schedule_zigbee_rejoin` (entry reload, capped); runtime per-device
  online/offline tracking is covered by the transport availability
  monitor + recipe R127 (ramses_rf PR 1224).
- [x] Correct RAMSES HGI identity produces a final DTO and matching
  echo. — physical evidence above (routed TX → over-air echo → dedup).
- [x] ramses_cc: `mqtt_ha` primary + `zigbee://` additional uses the
  hybrid pool (`primary_is_mqtt`, `serial_additional=[zigbee_url]`);
  plain MQTT pool unchanged; `_extract_pool_hgis_from_schema` excludes
  Zigbee members (`tests_new/test_coordinator.py`).
- [x] `ha_sim_test` recipe R126 — in-container structural checks
  (identity vectors, precedence, IEEE-never-as-HGI, fail-fast child,
  pool failure isolation).

#### Completion criteria

- [x] Automated tests prove Zigbee can participate in inbound dedup and
  outbound routing with correct identity.
- [x] `zigpy` is either declared in `ramses_cc`'s `manifest.json` or
  `ZigbeeTransport._async_init` raises a clear `TransportZigbeeError` when
  `zigpy` is absent. **Done both:** the `ImportError` →
  `TransportZigbeeError` mapping already existed; `zigpy>=2.0.0` is now
  also declared as a `ramses-rf` optional dependency (`[zigbee]` extra)
  and `zha` is in `ramses_cc`'s `manifest.json` `after_dependencies`.
- [x] Focused tests, affected repository suites, Ruff, and strict mypy
  pass.
- [x] Physical Zigbee release evidence recorded (above).

### Phase 3 release gate

After PR 6 is complete and physical Zigbee hardware has been tested:

- [x] All Phase 1 and Phase 2 gate items still pass.
- [x] Record physical Zigbee pool results. — **2026-09-15, above**
- [x] Verify Zigbee transport is un-gated in the config flow. —
      **"Zigbee" / "Zigbee (detected)" selectable; pool-add flow works**

### Phase 3 definition of done

Zigbee is complete and may be advertised only after its separate
identity/lifecycle automated checks and physical release evidence also pass.
The Zigbee transport type is un-gated in the config flow only at this point.

**Status (2026-09-17):** automated checks and physical evidence pass; the
config flow is un-gated. ZHA availability→`PoolChild` mapping is
implemented in two layers: entry-reload rejoin for setup-time failures
(`_schedule_zigbee_rejoin`, ramses_cc PR 1206) and a runtime per-device
availability monitor (ramses_rf PR 1224, recipe R127).

Also fixed (ramses_cc PR 1206): the per-HGI `*_online` and
`pool_status` entities were gated on `is_pool_enabled`, which only
recognised option-driven pools (`additional_ports`, `mqtt_hgi_id`,
`mqtt_use_ha`) or ≥2 *accepted* schema HGIs.  Schema-driven pools —
ownerless HGIs are receive-only pool children — never got health
entities.  `is_pool_enabled` now mirrors actual pool construction
(schema pool HGIs + MQTT in play), and `_extract_pool_hgis_from_schema`
no longer early-returns when the root `_owner` key is absent (profile
loads that rebuild the schema can transiently drop it); ownerless HGIs
stay receive-only candidates, foreign-owned HGIs remain excluded.

---

## PR dependency order

```text
Phase 1 — MQTT pool (first release) — ALMOST DONE
  PR 1: child state + inbound dedup
  PR 2: typed DTO routing + RSSI + QoS + failover
  PR 4A: transport-neutral MQTT callback contract   (merged)
  PR 4B: HA-native multi-MQTT                        (merged)
  PR 5: membership + MQTT-only config flow
  = Phase 1 release (dual-MQTT pool) =

Phase 2 — Serial and hybrid pool (hardware feasibility gate PASSED 2026-09-06)
  PR 2 + PR 4B + PR 5
              |
              +--> PR 3: pooled serial transmit (un-gate serial in config flow)
              |
              = Phase 2 release (USB + hybrid pool) = DONE

Phase 3 — Zigbee pool (hardware verified 2026-09-15)
  PR 2
              |
              +--> PR 6: Zigbee identity/lifecycle (un-gate Zigbee in config flow)
              |
              = Phase 3 release (Zigbee pool) = IN PROGRESS
```

---

## Architecture invariants that carry forward

These invariants from Phase 1 remain binding for Phase 2 and Phase 3. The full
list is in the "Non-negotiable architecture invariants" section of
[`multi-hgi-plan.md`](../multi-hgi-plan.md); the ones most relevant to serial
and Zigbee:

1. `ramses_rf` receives one deduplicated packet stream.
2. There is no multi-gateway registry or separate topology graph in
   `ramses_rf`.
3. Each physical/network driver owns its connection, buffering, and
   reconnection details.
4. The pool/router consumes a small transport-neutral child interface.
5. `CommandDTO` and `PacketDTO` remain immutable boundary objects.
6. Outbound child selection, explicit source-intent handling, and HGI source
   resolution happen before serialization and before QoS establishes its
   expected echo.
7. The final command is serialized once per routed QoS attempt; transport-level
   repeats reuse that exact route and wire frame.
8. Faked-device commands retain their intentional source identity, including
   intentional `18:` sources.
9. HGI80 placeholder behavior remains supported.
10. A child known to be offline is never re-enabled merely because every other
    child is also unavailable.
11. Existing single-port serial and single-HGI MQTT configurations remain
    backward compatible.
12. USB, MQTT, and hybrid pools use the same route-selection contract.
13. Every inbound frame retains its receiving-child/HGI provenance on the
    transport/packet envelope separately from frozen DTOs and RAMSES `addr1`.
14. Pool-HGI loopback frames do not contribute route-quality RSSI, including
    aggregate fallback, and satisfy QoS only when they match the canonical
    fingerprint of the final routed wire command.
15. Cold-start routing is deterministic and never multicasts one command
    through multiple radios.
16. Firmware-management commands remain explicitly per-HGI and bypass RAMSES
    routing/QoS.
17. Configuration reload is the initial membership-change mechanism; runtime
    structural mutation is not part of the first-release contract.
18. Pool child connection state, node availability, send readiness, and
    route-evidence freshness remain separate dimensions.
19. Legacy outbound regex processing cannot silently change positional
    addresses after route selection; pooled mode rejects such a transformation
    unless it is moved to a typed pre-route command transformation.
20. All runtime dependencies required by a transport path are declared in
    `ramses_cc`'s `manifest.json` or `ramses_rf`'s `pyproject.toml`, not relied
    on transitively from HA's bundle; CI workflow thresholds and caching must
    not be regressed by any pool PR.

### Separate address identities (Phase 3 specific)

Each child may need both:

```text
transport_address  # /dev/serial/by-id/..., MQTT topic ID, Zigbee IEEE
hgi_id             # RAMSES 18:xxxxxx identity
```

They must never be substituted for one another. A Zigbee IEEE address selects
the Zigbee endpoint; its associated RAMSES HGI ID is used in RAMSES frames.
This separation is also good practice for serial (the `/dev/...` path is not
the HGI ID) and MQTT (the topic ID is the HGI ID, but the broker host is not).

### Serial startup and readiness (Phase 2 specific)

Split the overloaded serial controls:

```python
disable_sending: bool
signature_policy: Literal["immediate", "delayed", "skip"]
startup_grace: float | None
configured_hgi_id: str | None
enable_reconnect: bool
```

Proposed ESP-aware startup (validated by hardware feasibility gate, 2026-09-06):

1. Open the port once using a stable path. **Do NOT change DTR/RTS after
   open** — any transition resets the ESP32.
2. Avoid immediate repeated writes.
3. Wait `startup_grace` seconds (default 3.0s, minimum 2.0s) for the ESP32
   to finish booting. The grace period is needed **once per port open**
   (startup or reconnect), not per message.
4. Perform one controlled signature probe when supported.
5. Obtain/validate the RAMSES HGI ID.
6. **Detect ramses_esp firmware version** from boot banner (`# ramses_esp
   <version>`) or `!V` response. Log a warning if below v0.6.1 (known MQTT
   disconnect crash bug, fixed in v0.6.1+). Do not block operation — the pool
   can work around crashes with grace period re-application.
7. Set `send_ready=True`.
8. Permit normal writes (~10ms echo latency after boot).

Fallbacks:

- Explicit configured HGI ID if a safe signature cannot be obtained.
- Firmware readiness/identity announcement for compatible evofw3/ramses_esp
  devices.
- HGI80 placeholder behavior when appropriate.
- Remain receive-only if identity or send safety cannot be established.

### Availability model (serial and Zigbee)

#### Serial

- OS/serialx connection event updates `ConnectionState`.
- A read error or explicit serial disconnect marks the path
  disconnected/failed.
- A write exception follows the conservative write-outcome model and does not
  by itself prove disconnection or non-submission.
- Successful reopen sets the path connected; identity/startup validation
  separately sets node online and send-ready.
- Packet silence alone only expires route evidence and is not proof of
  disconnection.

#### Zigbee

- ZHA device availability: online/offline.
- IEEE endpoint availability and RAMSES identity are tracked separately.

The old "re-enable every unhealthy child as a last resort" behavior should be
removed. `STALE`, `OFFLINE`, and `FAILED` children are not eligible in the
initial policy; a future explicit fallback policy may define different stale
handling, but offline or failed children must never be selected.

---

## Rule for every PR

Every PR must contain:

1. Regression tests that fail against its parent branch for the defect being
   fixed.
2. The smallest implementation that makes those tests pass.
3. Tests for negative and recovery paths, not only the nominal path.
4. Strict typing, lint, and the relevant repository test suite.
5. Targeted `ha_sim_test` coverage when Home Assistant, discovery, schema,
   MQTT, or command dispatch is affected.
6. Deterministic fixtures or broker/simulator integration tests for
   hardware-dependent paths; physical observations are recorded as release
   evidence when CI cannot reproduce them.
7. Updated existing documentation and diagnostics for behavior changed by that
   PR.
8. No CI workflow regressions: coverage thresholds, `concurrency:` blocks, and
   pip caching must not be lowered or removed. If pool code has lower coverage
   than the current threshold, add tests to raise it rather than lowering the
   bar.

Testing and observability are part of each implementation PR rather than
separate final phases.

---

## Open items deferred from Phase 1 (candidates for Phase 2/3 follow-up)

These were noted as limitations or deferred during Phase 1 and may be addressed
during Phase 2/3 work if they become relevant. Items already resolved are
marked **[DONE]** and retained for historical context.

- **Heartbeat/last-packet expiry for MQTT children** is not implemented. An
  ESP that silently stops sending but never sends LWT `offline` will stay
  marked online. LWT is the sole source-of-truth for MQTT child availability
  in Phase 1. A heartbeat timeout may be added if real-world testing shows
  this is needed.
- **[DONE] Per-HGI status sensors** (issue 1171 comment by
  silverrailscolo). Per-HGI online/offline binary sensors and an
  aggregate pool status sensor now track MQTT LWT and serial connection
  state separately. The legacy `binary_sensor.hgi_18_*_gateway_status`
  entities remain as a secondary surface.
- **[DONE] HGI `_comment` warning** — **Fixed (2026-09-11, commit `61b45209`).**
  HGI `_comment` fields now include the warning suffix
  ` (don't edit here — adapt with the Pool Management config)`. A
  migration in `coordinator.async_setup` appends the warning to existing
  comments on startup. `build_hgi_comment()` and
  `ensure_hgi_comment_warning()` helpers in `const.py` ensure the warning
  is always present and idempotent. The warning text avoids `usb`, `mqtt`,
  and `zigbee` so comment-based transport detection is not broken.
- **Diagnostics/config UI display** of transport kind, address, HGI ID,
  broker/topic, availability, acceptance, and send readiness — partially
  addressed: per-child state, identity, route evidence, failures, and
  reconnects are visible in diagnostics; the config-flow UI for transport
  kind selection is implemented via `_preferred_type`. Full diagnostics
  review confirmed no credentials are exposed.
- **HA USB consumer listing (issue 1143)**: HA 2026.9's `usb/consumers.py`
  cannot detect ramses_cc as a serial port consumer because the port is stored
  at `options["serial_port"]["port_name"]` (nested dict) but HA only checks
  flat key paths. A fix has been proposed to HA core. If HA core accepts it, no
  ramses_cc change is needed. If rejected, the config key must be flattened or
  a compatibility shim added. This affects the config-flow port picker for
  `CONF_ADDITIONAL_PORTS` and the "port in use" indicator in HA 2026.9+.
- **Optional private-namespace auto-accept mode** for wildcard MQTT HGIs is
  deferred.
- **[DONE] ramses_esp firmware crash (MQTT disconnect + USB serial)**: ramses_esp
  0.4.9 and 0.5.2 crash with `RTC_SW_CPU_RST` when the MQTT connection
  disconnects (e.g. when the USB serial port is opened and the DTR/RTS
  reset drops the MQTT connection). Both ESP32s crash when either port is
  opened, even sequentially. A separate `LoadProhibited` crash occurs when
  MQTT TX is sent to an ESP32 that is also on USB serial. The ESP32
  auto-reboots and recovers in ~1.9s. This is a firmware bug, not a pool
  issue. **FIXED in v0.6.6c** — both ESP32s updated via OTA, no crashes
  observed after update. The fix was likely introduced in v0.6.1 (ramses_esp
  issue 30: "Fix misconfigured MQTT reboot loop"). No need to file a firmware
  issue — the update resolves it. The serial transport should detect the
  ramses_esp firmware version on startup and log a warning if below v0.6.1,
  advising the user to update via OTA. The config flow should enforce mutual
  exclusivity: an HGI ID configured as USB serial should not be addable as
  an MQTT pool member, and vice versa.

---

## References

- Full plan: [`multi-hgi-plan.md`](../multi-hgi-plan.md) (repo root)
- Phase 1 PRs:
  - ramses_rf PR 1184 (PR 1: child state + inbound dedup)
  - ramses_rf PR 1194 (PR 2: typed routing + RSSI + QoS + failover)
  - ramses_rf PR 1195 (PR 4A: MQTT callback contract, merged)
  - ramses_cc PR 1157 (PR 4B: HA-native MQTT pool bridge, merged)
  - ramses_cc PR 1133 (PR 5: membership + config flow + MQTT pool assembly)
- Fixture evidence: `fixtures/fixture_report.md`, `fixtures/pool_test_report.md`
- Analyzer: `tools/analyze_fixture.py`
- Hardware feasibility gate report: `docs/serial_hw_gate_report.md`
- Hardware test tools: `tools/serial_hw_gate.py`, `tools/hybrid_usb_mqtt_test.py`
- Hardware test logs: `logs/serial_hw_gate_20260906_*.log`
- Regression test: `tools/ha_sim_test/recipes/r123_non_primary_usb_to_mqtt.py`
  (R123 — non-primary HGI USB→MQTT switch, comment warning migration)
- Regression test: `tools/ha_sim_test/recipes/r126_phase3_zigbee_pool.py`
  (R126 — Zigbee identity derivation, IEEE/HGI separation, fail-fast child,
  pool failure isolation)
- Related issues:
  - https://github.com/ramses-rf/ramses_rf/issues/1119 (original multi-HGI
    discussion)
  - https://github.com/ramses-rf/ramses_rf/issues/1122 (pool child state)
  - https://github.com/ramses-rf/ramses_cc/issues/1143 (HA USB consumer
    listing)
