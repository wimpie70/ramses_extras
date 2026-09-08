# Follow-up issue: multi-HGI pool — Phase 2 (serial/hybrid) and Phase 3 (Zigbee)

**Source plan:** [`multi-hgi-plan.md`](../multi-hgi-plan.md) (repo root)
**Created:** Sep 6 2026
**Scope:** Continue the phased rollout of transport-neutral HGI pooling after
Phase 1 (MQTT-only pool) ships. Phase 2 adds serial and hybrid USB+MQTT pools;
Phase 3 adds Zigbee pools once physical hardware is available.

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

**Goal:** make `PortTransport` a fully send-capable pool child alongside MQTT
children, without reintroducing ESP32 USB startup reset loops. Un-gate serial
transport in the config flow.

**Prerequisite:** the **serial hardware feasibility gate** ~~must pass before
PR 3 starts~~ **PASSED 2026-09-06** (see below).

**Delivery PR:** PR 3 — Full pooled serial transmission and reconnect
(`ramses_rf`, new focused PR stacked on PR 2 / PR 1194).

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
- `signature_policy = "delayed"` with `startup_grace = 3.0s` for pooled serial
  children (grace period is once per port open, not per message).
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
- Obtain the RAMSES HGI ID through delayed signature, firmware announcement, or
  validated configured identity.
- Keep identity-unknown serial children receive-only and not send-ready.
- Mark the child send-ready only after identity and startup safety are
  established.
- Preserve HGI80 placeholder behavior.
- Add bounded serial reopen/reconnect backoff using stable
  `/dev/serial/by-id/...` paths where available.
- Propagate serial read/write/disconnect failures into the child state model.
- Apply the PR 2 proven-not-submitted-versus-ambiguous outcome policy to serial
  writes.
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

- [ ] All Phase 1 gate items still pass.
- [ ] Record physical two-USB and USB-plus-MQTT results.
- [ ] Verify USB unplug/reconnect and ESP restart/LWT against the integrated
      stack.
- [ ] Verify serial transport is un-gated in the config flow.
- [ ] Full `ramses_rf`, `ramses_cc`, and `ramses_extras` suites pass.
- [ ] Complete `ha_sim_test` recipe set passes (0 failures).
- [ ] Diagnostics review: no credentials exposed; per-child state, identity,
      route evidence, failures, and reconnects visible.

### Phase 2 definition of done

The serial and hybrid pool feature is complete only when all of the following
are additionally true:

1. Serial transport is un-gated in the config flow (the "(not yet supported)"
   marker and `TODO:` remarks are removed).
2. `PortTransport` is a fully send-capable pool child without ESP startup reset
   loops.
3. Serial and HA-native MQTT adapters pass equivalent routing/lifecycle tests.
4. Full repository suites, complete `ha_sim_test`, diagnostics review, and
   mandatory physical two-USB and USB-plus-MQTT release evidence pass.
5. USB unplug/reconnect and ESP restart/LWT behavior verified against the
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

Zigbee pool support is **parked** until hardware is available. The existing
`ZigbeeTransport` code remains in place and is gated in the config flow with
"(not yet supported)" and `TODO: re-enable when Phase 3` remarks.

### PR 6 — Correct Zigbee identity and lifecycle

**Repository:** `ramses_rf`; use a separate follow-up `ramses_cc` PR if
configuration changes are required.
**Depends on:** PR 2 (PR 1194), physical Zigbee hardware availability.
**Phase:** 3 — Zigbee pool (parked until hardware is available).

#### Implementation

- Store the Zigbee IEEE transport address separately from the RAMSES HGI ID.
- Define one explicit source for the RAMSES HGI identity: discovery, firmware
  announcement, or validated configuration.
- Use IEEE only for Zigbee endpoint selection.
- Use the `18:` HGI ID only in RAMSES commands.
- Map ZHA device availability into `PoolChild` state.
- Keep identity-unknown Zigbee children receive-only.
- **ramses_cc side:** remove the Zigbee gating in the `manage_pool` config-flow
  step (drop the `pool_zigbee_not_supported` error and the "(not yet
  supported)" label). Remove the `TODO: re-enable when Phase 3` remarks.

#### Regression tests required

- IEEE addresses are never inserted into RAMSES frames.
- An identity-unknown Zigbee child is never selected for transmission.
- ZHA unavailable/recovery events update only the relevant child.
- Correct RAMSES HGI identity produces a final DTO and matching echo.

#### Completion criteria

- Automated tests prove Zigbee can participate in inbound dedup and outbound
  routing with correct identity.
- `zigpy` is either declared in `ramses_cc`'s `manifest.json` or
  `ZigbeeTransport._async_init` raises a clear `TransportZigbeeError` when
  `zigpy` is absent, instead of a bare `ImportError` deep in a method body.
  **Already done:** `ZigbeeTransport._async_init` catches `ImportError`
  separately and raises `TransportZigbeeError` with installation guidance.
- Focused tests, affected repository suites, Ruff, and strict mypy pass.
- Zigbee remains unadvertised until separate physical Zigbee release evidence
  is recorded.

### Phase 3 release gate

After PR 6 is complete and physical Zigbee hardware has been tested:

- [ ] All Phase 1 and Phase 2 gate items still pass.
- [ ] Record physical Zigbee pool results.
- [ ] Verify Zigbee transport is un-gated in the config flow.

### Phase 3 definition of done

Zigbee is complete and may be advertised only after its separate
identity/lifecycle automated checks and physical release evidence also pass.
The Zigbee transport type is un-gated in the config flow only at this point.

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
              = Phase 2 release (USB + hybrid pool) =

Phase 3 — Zigbee pool (after hardware availability)
  PR 2
              |
              +--> PR 6: Zigbee identity/lifecycle (un-gate Zigbee in config flow)
              |
              = Phase 3 release (Zigbee pool) =
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
during Phase 2/3 work if they become relevant:

- **Heartbeat/last-packet expiry for MQTT children** is not implemented. An
  ESP that silently stops sending but never sends LWT `offline` will stay
  marked online. LWT is the sole source-of-truth for MQTT child availability
  in Phase 1. A heartbeat timeout may be added if real-world testing shows
  this is needed.
- **Gateway status binary sensor does not reflect per-HGI offline state**
  (issue 1171 comment by silverailscolo). The `RamsesGatewayBinarySensor`
  tracks the ramses_rf gateway's `is_active`, which in a pool setup reflects
  the overall pool bridge state, not individual HGI connectivity. If the
  primary HGI is unplugged but cached packets are loaded or other HGIs are
  still online, the sensor stays "OK". Per-HGI online/offline sensors and
  proper last-packet expiry are Phase 2 items.
- **Diagnostics/config UI display** of transport kind, address, HGI ID,
  broker/topic, availability, acceptance, and send readiness — not addressed
  in PR 5.
- **HA USB consumer listing (issue 1143)**: HA 2026.9's `usb/consumers.py`
  cannot detect ramses_cc as a serial port consumer because the port is stored
  at `options["serial_port"]["port_name"]` (nested dict) but HA only checks
  flat key paths. A fix has been proposed to HA core. If HA core accepts it, no
  ramses_cc change is needed. If rejected, the config key must be flattened or
  a compatibility shim added. This affects the config-flow port picker for
  `CONF_ADDITIONAL_PORTS` and the "port in use" indicator in HA 2026.9+.
- **Optional private-namespace auto-accept mode** for wildcard MQTT HGIs is
  deferred.
- **ramses_esp firmware crash (MQTT disconnect + USB serial)**: ramses_esp
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
- Related issues:
  - https://github.com/ramses-rf/ramses_rf/issues/1119 (original multi-HGI
    discussion)
  - https://github.com/ramses-rf/ramses_rf/issues/1122 (pool child state)
  - https://github.com/ramses-rf/ramses_cc/issues/1143 (HA USB consumer
    listing)
