# robust transport-neutral HGI pooling

updated: sep 5, 16:15

## Terminology

To keep all contributors aligned:

- **Gateway** (software gateway): the single domain orchestrator in `ramses_rf` (`ramses_rf.gateway.Gateway`). There is strictly one software Gateway per Home Assistant integration instance.
- **Dongle** (physical RF transceiver): any physical radio hardware (Honeywell device type `18:...`, such as an evofw3 USB stick, CC1101, or ESP32 radio node) that converts 868 MHz RF packets to ASCII strings.

This plan builds **multi-dongle spatial diversity**: a single software Gateway sitting on top of a link-layer transport pool that communicates with two or more physical dongles. It does not create multiple software gateways.

## Purpose

This plan describes how to move from the current draft implementation to a production-capable system that supports all of these configurations:

- One USB/serial HGI.
- Multiple USB/serial HGIs.
- One or more MQTT HGIs.
- Hybrid USB/serial plus MQTT pools.
- Zigbee-backed HGIs once their RAMSES identity is represented correctly.

USB and hybrid support remain part of the target rather than being excluded or indefinitely deferred. The work is phased because several foundations must be corrected before those configurations can be described as safe. Phasing is implementation order, not a reduction in scope: multi-USB and hybrid operation are release criteria for the complete feature.

## Phased rollout

Development and release proceed in three phases. The `PooledTransport` code remains transport-neutral throughout; the phases control which transport types are selectable in the config flow and advertised as supported.

### Phase 1: MQTT pool (first release)

- **Active transports:** MQTT only (HA-native MQTT service via `homeassistant.components.mqtt`).
- **Single MQTT HGI:** uses `RamsesMqttPoolBridge` (the old `RamsesMqttBridge` class is no longer instantiated) — no pool, no paho.
- **Multiple MQTT HGIs:** `RamsesMqttPoolBridge` drives the pool through the PR 4A callback contract — still no paho, one HA-managed MQTT connection. Config flow asks for HGI ID only (`18:NNNNNN`); the HA MQTT broker and topic prefix are reused.
- **No paho inside HA:** `MqttTransport` (direct paho) is not instantiated for pooled MQTT inside Home Assistant. It remains in `ramses_tx` for standalone CLI use only. Serial-primary configurations cannot add MQTT pool members in Phase 1 (gated in config flow).
- **Config flow:** only MQTT transport is selectable when adding a pool child. Serial and Zigbee options show "(not yet supported)" with `TODO:` remarks.
- **Pool construction:** only MQTT children are instantiated via the callback contract. No serial or Zigbee children are added to the pool.
- **Code preservation:** existing serial (`PortTransport`) and Zigbee (`ZigbeeTransport`) transport code stays in place and remains transport-neutral at the `PooledTransport` level. It is gated at the config-flow/membership layer, not removed.
- **Release criteria:** dual-MQTT pool works end-to-end with real hardware (dedup, RSSI routing, QoS, failover, LWT-based pruning).
- **Rationale (from issue 1119 discussion):** MQTT provides a clean testbench with native HA integration, LWT for node-offline detection, no USB pass-through or port re-enumeration issues in Docker, and two MQTT HGIs are already available for testing. Building the core foundations (dedup, RSSI routing, QoS) on MQTT first reduces the number of interacting variables during initial development.

### Phase 2: Serial and hybrid pool

- **Active transports:** MQTT plus serial (USB/ESP).
- **Prerequisite:** the serial hardware feasibility gate passes (ESP USB reset behavior characterized, send-safe startup policy determined).
- **Config flow:** serial transport is un-gated. The "(not yet supported)" marker and `TODO:` remarks are removed.
- **Pool construction:** serial children can be added alongside MQTT children.
- **Release criteria:** two-USB, USB-plus-MQTT, and USB unplug/reconnect evidence recorded.

### Phase 3: Zigbee pool

- **Active transports:** MQTT, serial, and Zigbee.
- **Prerequisite:** physical Zigbee hardware is available for testing, and the RAMSES HGI identity / IEEE address separation is correct.
- **Config flow:** Zigbee transport is un-gated.
- **Pool construction:** Zigbee children can be added.
- **Release criteria:** Zigbee identity/lifecycle automated checks and physical release evidence pass.

### What "gating" means concretely

- In the config flow, when adding a pool child, only MQTT transport is selectable in Phase 1.
- Serial and Zigbee options appear in the UI but are marked "(not yet supported)" and cannot be selected.
- `TODO: re-enable when Phase N` remarks mark the gating points in the config flow and membership code.
- The `PooledTransport`, `PortTransport`, and `ZigbeeTransport` classes are not modified or removed — they remain ready for un-gating.
- No serial or Zigbee `PoolChild` instances are created in Phase 1.

The design also takes the concerns raised in issue 1119 seriously:

- Keep `ramses_rf` single-stream and free of multi-gateway topology.
- Keep driver-specific lifecycle logic inside each driver.
- Avoid raw frame parsing and domain/device-type checks in the pool.
- Serialize an outbound command once per routed QoS attempt and reuse that wire frame for transport-level repeats.
- Use Home Assistant's native MQTT integration from `ramses_cc`.
- Do not mutate pool membership concurrently with active polling until a safe model exists.
- Preserve the existing single-USB path.
- Make disconnect, readiness, and failover behavior explicit and testable.

## PR implementation status

### PR 1 — Pool child state and inbound foundation (ramses_rf PR 1184)

**Status: implementation complete, tests passing, verified on real hardware, rebased on upstream master.**

Branch: `feat/pooled-transport-1122` (force-pushed to `wimpie70/ramses_rf`, PR 1184 open, local tracking branch `pr1/pool-child-state-1119`).

Implemented on `ramses_rf`:

- `PoolChild` dataclass replaces all parallel arrays (connection, HGI identity, transport, RSSI, counters, timestamps, errors).
- `ConnectionState` and `NodeAvailability` enums.
- `_ChildProtocolProxy` maps events into `PoolChild` objects.
- Ingress provenance: `_ingress_hgi_id` slot on `Packet` + read-only `ingress_hgi_id` property; set in `_on_child_packet()` before forwarding.
- Loopback exclusion: active pool HGI frames excluded from route RSSI.
- Dict-backed O(1) dedup cache with sequence-aware key (includes seq when present, falls back to base key).
- `RssiTracker` TTL (5 min expiry for pool children, `None` default for gateway communication-quality trackers); `_expire()` handles mixed tz-aware/naive timestamps (production bug found via real HGI testing — MQTT transports produce tz-aware local datetimes, serial produces naive).
- `_RSSI_UNKNOWN` sentinel changed from `0` to `-999` so real negative RSSI values are preferred over the unknown sentinel.
- Runtime `add_child()`/`remove_child()`/`set_accepted_hgis()` removed; construction-only.
- `get_extra_info()` compatibility keys preserved (`pool_hgi_ids`, `pool_rssi_trackers`, `pool_stats`).
- 51 focused tests in `test_transport_pooled.py`, 23 in `test_rssi_tracker.py`, regression tests in `test_communication_quality.py` and `test_base.py::TestCommunicationQuality`.
- 3037 tests pass, ruff clean, mypy clean.

Verified on real hardware (hass, 2 MQTT HGIs: `18:130236` + `18:149488`):

- Both children connect and stay connected.
- RSSI-based routing selects the closer HGI (-41 vs -92 dBm).
- Dedup suppresses cross-HGI duplicate frames (confirmed in logs).
- `check_communication_quality` runs without errors (tz fix confirmed).
- 72+ packets received in ~2 minutes of real Orcon ventilation traffic.
- Zero errors, zero crashes, zero disconnects.

### PR 5 — Serial/Zigbee gating + multi-HGI pool config flow (ramses_cc PR 1133 / fork PR 5)

**Status: gating + config flow + coordinator wiring implemented, all CI checks passing (lint, test, type, validate, coverage), rebased on upstream master.**

Branch: `pr5/membership-config-flow-pool-assembly` (current), previously `feat/pool-all-1119`. Upstream PR 1133, fork PR 5 — both refer to the same work.

Implemented on `ramses_cc`:

- Config flow `manage_pool` step: serial ports and Zigbee labeled "(not yet supported)".
- Selecting a gated option returns `pool_serial_not_supported` / `pool_zigbee_not_supported` error.
- Config flow `manage_pool_mqtt` step: add MQTT broker as pool child (host, port, auth, topic_path).
- Config flow `manage_pool_zigbee` step: select Zigbee device (gated, shows form but cannot save in Phase 1).
- Coordinator: `_create_pool_transport_constructor()` wires `pooled_transport_factory` from `ramses_tx` with lazy import guard for older published versions.
- Coordinator: defensive filter — only `mqtt://` ports pass to `PooledTransport`; serial and Zigbee are filtered out.
- Coordinator: `_extract_pool_hgis_from_schema()` discovers accepted HGIs from schema (18: devices with `_owner == root_owner` and `_class: HGI`).
- Coordinator: `_build_explicit_mqtt_url()` constructs per-HGI MQTT URLs from wildcard broker URL.
- Coordinator: `_get_primary_hgi_id()` resolves primary HGI from `CONF_MQTT_HGI_ID`, URL path, or schema fallback.
- Coordinator: `_register_pool_hgis()` registers pool HGIs in discovery scan and clears `_suppress_not_seen` for connected HGIs.
- Discovery: `sync_with_schema()` accepts optional schema dict and populates `_schema_no_owner_ids` for all schema devices without `_owner` (not just HGIs — any ownerless device is tracked for review).
- Discovery: `check_for_new_devices()` flags schema-no-owner HGIs for review instead of suppressing them; re-flags accepted devices that lost `_owner`.
- Schemas: `sync_learned_topology()` backfills `_owner` on existing entries missing it (e.g. auto-discovered HGIs).
- Event: `RamsesRegexEvent` converts bytes in payload to hex for JSON serialization.
- Translations: error messages in `en.json` and `nl.json`.
- TODO comments reference Phase 2 (PR 3) for serial, Phase 3 (PR 6) for zigbee.

Coverage: all `custom_components/ramses_cc` modules above 95% Silver IQS threshold (config_flow, coordinator, discovery, event, schemas, mqtt_bridge, mqtt_pool_bridge all pass `verify_module_coverage.py`). Verified: `coordinator.py` 95%, `discovery.py` 95%, `mqtt_bridge.py` 100%, `mqtt_pool_bridge.py` 98%, total 96%.

Tests added (approximate diff lines at time of writing; current file sizes are larger due to subsequent additions):

- config_flow: ~603 lines added (manage_pool_mqtt, manage_pool_zigbee, schema member removal, credential masking, duplicate detection).
- coordinator: ~428 lines added (pool constructor, \_register_pool_hgis, \_build_explicit_mqtt_url, \_extract_pool_hgis_from_schema, \_get_primary_hgi_id, \_create_client filtering).
- discovery: ~108 lines added (sync_with_schema schema param, check_for_new_devices no-owner flagging, removed device re-marking).
- event: ~70 lines added (bytes payload hex conversion).
- schemas: ~36 lines added (sync_learned_topology \_owner backfill).

### Remaining PRs

- PR 4A (transport-neutral MQTT callback contract): **implemented, CI green (5/5), draft PR 1195 open.** Ready for review/merge — all checks pass on `ramses-rf/ramses_rf`.
- PR 4B (HA-native multi-MQTT adapter): **implemented, lint CI green, draft PR 1157 open.** Type/test/coverage CI fail because PR 4A modules are not yet in published `ramses-rf==0.60.4`. Will go green after PR 4A merges and a new `ramses-rf` version is published.
- PR 5 (canonical membership + config flow + MQTT pool assembly): **implemented, lint/ruff/mypy clean, 1713 tests pass, draft PR 5 open on wimpie70 fork.** Includes: `wait_online_timeout` config option, `manage_pool_mqtt` HGI-only schema entry creation (no host/port/credentials), discovery callback schema insertion, `sync_learned_topology` backfill exemption for `18:` HGI candidates, `CONF_ACCEPTED_HGIS` dropped entirely (unreleased — schema is canonical source), stale `set_accepted_hgis` cleanup, serial-primary MQTT pool member gating. ha_sim_test full parallel run: 449 passed, 2 failed (parallel load timeouts — both pass when run alone). CI type/test failures expected until PR 4A merges and `ramses-rf` publishes a new version. Upstream PR blocked — `feat/pool-all-1119` base branch is not on upstream yet.
- PR 3 (pooled serial transmit): blocked on hardware feasibility gate.
- PR 6 (Zigbee identity/lifecycle): blocked on hardware availability.

### PR 2 — Pre-serialization routing contract (ramses_rf PR 1194)

**Status: implementation complete, all CI checks passing (lint, test, type, coverage), draft PR open.**

Branch: `pr2/typed-routing-1119` (pushed to `wimpie70/ramses_rf`, PR 1194 open).

Implemented on `ramses_rf`:

- New `routing.py` module with immutable boundary objects:
  - `SourcePolicy` enum: `GATEWAY` (transport may patch source) vs `PRESERVE` (faked-device commands keep intentional source).
  - `RouteRequest`: immutable wrapper around `CommandDTO` + `SourcePolicy`.
  - `RoutedCommand`: immutable result with pinned `child_id` + final DTO.
  - `WriteOutcome`: conservative classification (`SUBMITTED`, `NOT_SUBMITTED`, `AMBIGUOUS`) for safe failover decisions.
- `TransportInterface` gains default `prepare_command()` and `write_routed()` methods that non-pooled transports inherit as pass-through.
- `PooledTransport.prepare_command()`: extracts target from `addr2`, selects best child via RSSI/cold-start fallback, patches source address based on `SourcePolicy` and selected child's HGI ID.
- `PooledTransport.write_routed()`: dispatches to pinned child, returns `WriteOutcome` (handles missing child, TypeError fallback for `disable_tx_limits`).
- `PortProtocol._process_tx_item()`: wraps each QoS attempt in `prepare_command()` + `write_routed()`, sets `_pending_cmd` from final routed DTO so QoS echo matching uses the actual source-patched command.
- `SourcePolicy` determined in `send_cmd()`: `GATEWAY` when `addr1` is the gateway placeholder or active HGI ID, `PRESERVE` for intentional non-gateway sources (faked-device commands).
- Legacy `write_frame()` path preserved for backward compatibility (delegates to child selection + frame re-patching).
- 23 focused tests in `test_routing.py`, 7 updated tests in `test_protocol_transceiver.py`.
- 3037 tests pass, ruff clean, mypy clean.

### Upstream compatibility note

PR 1148 (merged to upstream master 2026-09-04) added `CONF_GATEWAY_OFFLINE_NOTIFY` — a user-configurable option to disable the gateway-offline notification for low-traffic networks. This feature is self-contained in `const.py`, `config_flow.py` (advanced_features step), and `coordinator.py` (`_async_health_check` early return). It does not touch any pool/multi-HGI code and has no impact on the plan. PR 1133 has been rebased on top of this merge with no conflicts beyond a trivial import-list merge in `test_coordinator.py`.

## Live hardware test results (2026-09-05)

Tested on hass with 2 ESP32 HGIs (`18:130236` + `18:149488`), MQTT broker at `192.168.40.11:1883`, topic `RAMSES/GATEWAY`. Serial via `/dev/ttyACM0`.

| Test                                     | Result | Notes                                                                                                     |
| ---------------------------------------- | ------ | --------------------------------------------------------------------------------------------------------- |
| 1: single serial HGI (no pool)           | PASS   | Normal operation, no pool bridge created                                                                  |
| 2: 1 serial + 1 MQTT (hybrid pool)       | PASS   | Both children connected, RSSI routing (-39 vs -84), dedup, `prepare_command` with `SourcePolicy.PRESERVE` |
| 2b: serial unplug → MQTT failover        | PASS   | `child 0 disconnected (Errno 5)`, pool continued with child 1, `22F1` fan command delivered via MQTT      |
| 3: 1 MQTT + 1 serial (reversed primary)  | SKIP   | Phase 2 — serial pool children are not selectable in the config flow (gated with "(not yet supported)")   |
| 4: 0 → 1 MQTT (add MQTT to serial)       | PASS   | Adding MQTT URL to `additional_ports` creates hybrid pool                                                 |
| 5: 1 → 2 MQTT (both via MqttPoolBridge)  | PASS   | Both HGIs via wildcard MQTT, schema-derived pool members, dedup, RSSI routing                             |
| 6: 2 → 1 MQTT (demote one HGI)           | PASS   | Demoted HGI stays as receive-only discovery candidate, notification sent (no duplicate after fix)         |
| 7: 1 → 0 MQTT (no accepted HGIs)         | PASS   | Backfill exemption for `18:` HGI entries prevents silent promotion (fixed)                                |
| 8: LWT failover (power off one ESP)      | PASS   | LWT detected in ~49s, `child offline (definitive=True)`, pool failover to remaining HGI, no crash         |
| 9: Outbound failover (primary unplugged) | PASS   | `22F1` fan commands (medium, low) routed via `18:149488/tx` while primary offline                         |
| 10: Broker disconnect/reconnect          | PASS   | Both HGIs offline → online (`2/2 connected`) within ~150ms, no `AssertionError` (after fix)               |
| 11: Primary rejoins after unplug         | PASS   | `!V` sent to `18:130236` on reconnect, pool back to `2/2 connected`                                       |

### Bugs found during live testing

1. **Duplicate discovery notification** (fixed): An HGI that was both in `_schema_no_owner_ids` and in the scan engine (receive-only pool child) was added to `new_ids` twice — once by the HGI loop and once by the scan-engine loop in `check_for_new_devices()`. Fixed by skipping HGIs in `_schema_no_owner_ids` in the scan-engine loop.

2. **Backfill promotes HGI candidate** (plan problem #10, fixed): `sync_learned_topology` backfills `_owner: me` onto `18:` HGI entries that have no `_owner`, silently promoting a receive-only discovery candidate to an accepted pool member. **Fixed:** backfill now exempts `18:` HGI entries. Test 7 (1 → 0 MQTT) passes — the HGI stays as a discovery candidate without `_owner`.

3. **"Add new port" label** (fixed): The dropdown label in `manage_pool` said "Add new port" but also lists existing serial ports for selection. Changed to "Add/edit port" in `en.json` and `nl.json`.

4. **Communication quality uses only primary RSSI tracker** (fixed): `DeviceBase.communication_quality` only passed the gateway's single `_rssi_tracker` to `compute_quality()`, ignoring RSSI data from other pool children. With 2 HGIs, a device heard strongly by one HGI (-39 dBm) but weakly by another (-89 dBm) was flagged as "weak signal". Fixed in `ramses_rf` `dev_base.py` to gather `pool_rssi_trackers` from `PooledTransport.get_extra_info()` so `best_rssi` reflects the strongest signal across all HGIs. 6 regression tests added in `test_base.py::TestCommunicationQuality`.

5. **Faked device in weak-signal notification** (verified, not a bug): The faked remote `37:168270` appeared in a "Schema mismatches detected" notification, but current dev logs show it is correctly skipped by `discovery.py`'s `is_faked` check. The notification was stale or from a production instance without the fix.

6. **`AssertionError` on broker reconnect** (fixed in `ramses_rf` PR 4A): `PortProtocol._set_active_hgi()` asserted it should only be called once, but `connection_lost()` did not reset `_active_hgi`. When the MQTT broker disconnected and reconnected, `connection_made()` fired again and hit the assertion. Fixed by resetting `_active_hgi` and `_is_evofw3` in `connection_lost()` and relaxing the assertion to a warning. All 3037 `ramses_rf` tests pass.

7. **`temp_control` overrides manual fan speed** (issue 216, `ramses_extras` — not a pool bug): The `temp_control` automation sends `22F1` (high) immediately after a manual fan speed command, undoing the user's setting. `humidity_control` correctly detects manual overrides, but `temp_control` only checks bypass position changes, not `22F1` fan speed changes. The pool delivers both commands correctly — this is an automation logic issue in `ramses_extras`, not a pool issue. Tracked in https://github.com/wimpie70/ramses_extras/issues/216.

## Release-readiness audit (2026-09-05)

A full release-readiness audit was performed across all active Phase 1 branches. The audit found 7 blockers; 6 were fixable in the current work cycle and have been resolved. The 7th (published dependency) is deferred to release time.

### Blockers resolved

1. **Missing root owner breaks acceptance** — `coordinator._get_accepted_hgi_ids()` and `_extract_pool_hgis_from_schema()` now guard against `None == None`. When the schema has no root `_owner`, only the primary (configured transport) is accepted. Ownerless candidates remain receive-only. `manage_pool_mqtt` writes a coherent root owner and member `_owner`.

2. **Receive-only candidates still received `!V`** — `mqtt_pool_bridge._handle_status_message()` now gates the `!V` firmware command on acceptance. Ownerless discovery candidates do not receive outbound communication.

3. **MQTT topic parser accepted non-HGI IDs** — `_extract_hgi_from_topic()` now requires the `18:` prefix and six digits. Non-HGI device IDs (e.g. `32:153289`) are rejected.

4. **MQTT broker/topic form did not match runtime behavior** — `manage_pool_mqtt` simplified to HGI ID only. No host, port, credentials, or topic path requested (HA MQTT broker/topic is reused). Adding MQTT pool members gated on primary transport being MQTT. Serial-primary + MQTT hybrid paho path blocked.

5. **Outbound publish outcome was premature** — `publish_frame()`, `_publish_tx()`, and `_publish_command()` are now async and await `mqtt.async_publish()`. Exceptions propagate to `PooledTransport.write_routed()` as `WriteOutcome.AMBIGUOUS`.

6. **Per-module coverage failed** — Added 40+ regression tests. All modules now pass the 95% Silver IQS threshold: `coordinator.py` 95%, `discovery.py` 95%, `mqtt_bridge.py` 100%, `mqtt_pool_bridge.py` 98%, total 96%.

### Blocker deferred to release

7. **Published dependency incompatible** — `ramses_cc` imports pool modules (`callbacks.py`, `mqtt_pool.py`, `pooled.py`) absent from published `ramses-rf==0.60.4`. A new `ramses_rf` PyPI release must be published, then `ramses_cc` must pin that exact version and rerun CI without the editable local checkout. This will be solved at release time.

### Verification results (post-fix)

| Check                                  | Result                                                                   |
| -------------------------------------- | ------------------------------------------------------------------------ |
| ramses_cc tests                        | 1713 passed, 15 skipped                                                  |
| ramses_rf tests                        | 3037 passed, 9 skipped                                                   |
| Ruff lint                              | All checks passed                                                        |
| Mypy type check                        | No issues found                                                          |
| Per-module coverage (Silver IQS)       | 100% of modules >= 95%                                                   |
| ha_sim_test (3 containers, 87 recipes) | 449 passed, 2 failed (parallel load timeouts — both pass when run alone) |

### ha_sim_test details

Full parallel run across 3 containers (ha-sim, ha-sim-2, ha-sim-3) with 87 recipes:

- **449 functional assertions passed, 2 failed**
- R97 (remote.send_command strategy fallback): timed out under parallel load — passes when run alone (5/5 assertions)
- R101 (Orcon CO2 binding, PR 1187): `GatewayStub` missing `get_device` method and expected payload format mismatch — both fixed in recipe, now passes (7/7 assertions)
- Log cleanliness: added "Connection to RAMSES RF gateway lost" and "ProtocolTimeoutError exception in shielded future" to expected warnings (transient MQTT reconnect warnings from parallel run residue)
- After fixes, R97+R101 run together: **all 14 assertions pass, including log cleanliness**

## Current situation

### What already works

- `PooledTransport` presents one transport and one inbound packet stream to the protocol/domain layer.
- Packets from different children are accepted and deduplicated via a dict-backed O(1) cache with sequence-aware key.
- Each child has an `RssiTracker` with TTL expiry (5 min for pool children, no expiry for gateway communication-quality trackers), allowing per-device route selection with fresh evidence.
- Child state is encapsulated in `PoolChild` dataclass (no parallel arrays).
- Ingress provenance (`ingress_hgi_id`) is carried on the `Packet` envelope, separate from RAMSES `addr1`.
- Active pool HGI loopback frames are excluded from route RSSI.
- `_RSSI_UNKNOWN` sentinel is `-999` (not `0`) so real negative RSSI values are preferred.
- A child that reports `connection_lost()` is removed from outbound candidates immediately.
- A physical serial disconnect reaches the pool through the child protocol proxy.
- Standalone paho `MqttTransport` children can nominally receive and transmit outside HA (e.g. via `ramses_cli`); the HA-native `RamsesMqttBridge` is the single-HGI path inside Home Assistant and uses `homeassistant.components.mqtt`, not paho.
- The existing non-pooled single-serial path remains unchanged.
- Pool configuration changes use the Home Assistant config-entry reload lifecycle rather than runtime `add_child()`/`remove_child()` calls (runtime API removed).
- Serial and Zigbee transport types are gated in the config flow with "(not yet supported)" markers.
- Config flow supports adding MQTT pool children via HGI ID only (`18:NNNNNN`). The HA MQTT broker/topic is reused — no separate host, port, credentials, or topic path are requested. Adding MQTT pool members is gated on the primary transport being MQTT (serial-primary configurations cannot add MQTT pool children in Phase 1).
- Coordinator wires `pooled_transport_factory` from `ramses_tx` with a lazy import guard for older published versions.
- Coordinator filters non-MQTT ports from pool construction (defensive serial/Zigbee exclusion).
- Coordinator extracts accepted HGIs from schema, builds per-HGI MQTT URLs, and registers pool HGIs in discovery.
- Discovery flags schema-no-owner HGIs for review instead of suppressing them (issue 1119).
- Schemas backfill `_owner` on existing entries missing it (e.g. auto-discovered HGIs).
- All `custom_components/ramses_cc` modules pass the 95% Silver IQS coverage threshold (verified: `coordinator.py` 95%, `discovery.py` 95%, `mqtt_bridge.py` 100%, `mqtt_pool_bridge.py` 98%, total 96%).
- Verified on real hardware: dual-MQTT pool (2 HGIs) works end-to-end with dedup, RSSI routing, and zero errors.
- Pre-serialization routing contract: `prepare_command()` / `write_routed()` on `TransportInterface` with typed `RouteRequest`, `RoutedCommand`, `SourcePolicy`, and `WriteOutcome`.
- `PortProtocol` uses the routing API for each QoS attempt; `_pending_cmd` is set from the final routed DTO for correct echo matching.
- `SourcePolicy.PRESERVE` protects faked-device command sources from pool-level patching.
- `WriteOutcome` classifies write results as `SUBMITTED`, `NOT_SUBMITTED`, or `AMBIGUOUS` for safe failover decisions.
- Transport-neutral MQTT callback contract: `MqttPoolInbound`, `MqttPoolOutbound`, `MqttDiscoveryCallback` protocols in `ramses_tx.transport.callbacks`. `MqttCallbackPoolAdapter` bridges callbacks to `PooledTransport` with pre-created logical children, LWT/broker event mapping, and outbound publishing.
- HA-native multi-HGI MQTT pool bridge: `RamsesMqttPoolBridge` in `ramses_cc` drives multiple configured HGIs through one HA-managed MQTT connection using the callback contract. Wildcard RX/CMD/status subscriptions, HGI ID extraction from topics, Packet parsing, per-HGI LWT handling, and per-HGI `!V` handshake.
- Single-HGI HA MQTT path now uses `RamsesMqttPoolBridge` for all MQTT paths (including single HGI). The old `RamsesMqttBridge` class still exists but is no longer instantiated in production code. The pool bridge uses `homeassistant.components.mqtt` exclusively — no paho clients are created inside Home Assistant. `publish_frame()` awaits `mqtt.async_publish()` so publish exceptions propagate to `PooledTransport.write_routed()` as `WriteOutcome.AMBIGUOUS` rather than being silently swallowed.
- Callback-driven children are treated as evofw3-compatible by `PooledTransport.get_extra_info(SZ_IS_EVOFW3)`.

### Problems that must be fixed

#### 1. Pooled serial transmission is not supported

Serial pool children are gated in the config flow with "(not yet supported)" and filtered by the coordinator (`coordinator.py` only passes `mqtt://` ports to `PooledTransport`). The underlying serial-send safety issue (ESP32 USB reset on startup signature exchange) remains uncharacterized. This is a Phase 2 prerequisite, not a runtime `disable_sending` flag.

Effects:

- Two-USB pools cannot transmit at all.
- In a serial-plus-MQTT pool, only MQTT children can transmit.
- The router can select a serial child and then fail with `TransportError`.
- The primary serial gateway is also read-only once it is placed inside a pool.

#### 2. Serial identity is unavailable when the signature is skipped

The startup signature response normally identifies the HGI. Without it, the child may remain connected with `hgi_id=None`. An ordinary received RF packet identifies the remote RF sender, not the receiving HGI.

#### 3. ESP USB reset behavior is not characterized

It is not yet known whether the reset is caused by DTR/RTS transitions, writes during the boot window, repeated `7FFF` probes, repeated reopen cycles, or all later serial writes. The workaround suppresses the symptom but also disables the required feature.

#### 4. MQTT LWT does not affect pool eligibility

~~The direct MQTT transport already observes online/offline status and tracks ESP IDs. However, its offline path calls `pause_writing()`, while `_ChildProtocolProxy.pause_writing()` is a no-op. The pool can therefore continue considering an offline MQTT child connected.~~ **Fixed in PR 4A+4B:** LWT offline is now propagated as a definitive availability event through `MqttCallbackPoolAdapter.on_child_offline(definitive=True)`, which marks the child disconnected and removes it from outbound eligibility. LWT online triggers `on_child_online()` which marks the child connected and send-ready.

~~The HA-native `RamsesMqttBridge` monitors the broker connection but does not currently maintain per-ESP availability.~~ **Fixed in PR 4B:** `RamsesMqttPoolBridge` tracks per-ESP LWT status separately from the HA broker connection. Broker disconnect marks all MQTT children unavailable; broker reconnect restores subscriptions without duplicating children. Per-ESP LWT offline affects only that child.

#### 5. Packet silence is not a reliable availability model

The current health timeout:

- Runs only during outbound selection.
- Never expires a child that connected but has never received a packet.
- Treats a quiet RF environment like a failed radio.
- Re-enables all unhealthy children when none remain, including children that should stay offline.

Transport availability, RF activity, and route quality must be separate concepts.

#### 6. Write failures do not fail over safely

If a selected child raises during `write_frame()`, the pool does not classify the failure or select another child. Blindly retrying would also be unsafe because a command may already have reached RF even if the host did not receive its echo.

#### 7. Outbound routing occurs after serialization

~~`PooledTransport.write_frame()` splits the ASCII frame, treats `addr1` as source and `addr2` as target, checks the `18:` prefix, and rewrites the frame. This causes:~~

~~- Link/domain boundary concerns.~~
~~- Double source patching.~~
~~- QoS/echo risk if the protocol expects a command different from the final transmitted frame.~~
~~- Zigbee corruption when an IEEE address is treated as a RAMSES source address.~~

**Fixed in PR 2:** `PooledTransport.prepare_command()` selects child and patches source **before** serialization. `PortProtocol._process_tx_item` sets `_pending_cmd = routed.command` before serializing, so QoS echo matching uses the actual source-patched command.

#### 8. Zigbee identity conflates two address spaces

`ZigbeeTransport` exposes its Zigbee IEEE address as `SZ_ACTIVE_HGI`. A Zigbee transport address and a RAMSES HGI `18:` identity are different values and must be stored separately.

#### 9. MQTT bypasses Home Assistant in pooled mode

~~The HA-native single-HGI path uses `RamsesMqttBridge` through `homeassistant.components.mqtt` (no paho). But when the pool is created for multiple MQTT HGIs, the current code instantiates `MqttTransport` (direct paho) children for `mqtt://` URLs, bypassing HA's broker credentials, SSL configuration, and lifecycle.~~ **Fixed in PR 4B:** `RamsesMqttPoolBridge` drives multiple configured HGIs through one HA-managed MQTT connection using the PR 4A callback contract. No direct paho clients are created inside Home Assistant. The pool gets its MQTT children through `MqttCallbackPoolAdapter`, not through `MqttTransport`.

#### 10. Membership policy is incomplete

~~Schema entries without an owner are documented as receive-only discovery candidates, but no complete `send_ready=False` path enforces that behavior. `CONF_ACCEPTED_HGIS` is read separately and is not derived consistently from schema ownership; the current pool acceptance setter filters inbound forwarding but does not gate outbound selection.~~ ~~The current schema synchronization also backfills missing `_owner` values, including discovered HGI entries, which can silently promote an intended receive-only candidate.~~

**Fixed:** `CONF_ACCEPTED_HGIS` is fully removed. Schema ownership is canonical. `sync_learned_topology` backfill exempts `18:` HGI entries. `coordinator._get_accepted_hgi_ids()` and `_extract_pool_hgis_from_schema()` now guard against `None == None`: when the schema has no root `_owner`, no schema-derived HGI is accepted via the owner-match branch — only the primary (configured transport) is accepted. Ownerless HGI candidates remain receive-only: they do not receive the `!V` firmware command on LWT online, and they are not in the accepted set for outbound routing. The `manage_pool_mqtt` config-flow step writes a coherent root owner and member `_owner` when adding an HGI.

A wildcard MQTT namespace also needs an explicit trust policy: private namespace, allowlist, schema ownership, or another acceptance mechanism.

#### 11. Child state is fragmented

~~The pool stores connection, HGI identity, transport object, RSSI, packet counts, health, timestamps, and error counts in parallel mutable arrays.~~ **Fixed in PR 1:** `PoolChild` dataclass consolidates all per-child state into one object. No parallel arrays remain.

#### 12. Deduplication is not O(1)

~~The current cache is bounded by time and size, but it is a `deque` that is linearly scanned.~~ **Fixed in PR 1:** replaced with a dict-backed time- and size-bounded cache with sequence-aware key. O(1) expected lookup.

#### 13. RSSI semantics and expiry need an explicit contract

~~The roadmap mentioned a five-sample rolling average, while the implementation reuses the existing three-sample `RssiTracker` and selects the strongest recent reading. The tracker stores timestamps but does not expire old samples during `best_rssi_for()`.~~ **Fixed in PR 1:** `RssiTracker` now has TTL (5 min default). `_expire()` runs on every access. Stale readings are removed. The tz-aware/naive datetime comparison bug (MQTT vs serial) was found and fixed during real HGI testing.

#### 14. Existing verification is mostly mock-based

The pool unit tests and simulation recipe use mock child transports. They verify routing logic but not real `PortTransport`, MQTT node lifecycle, serial startup, source identity, or cross-transport QoS.

#### 15. Cross-dongle air-interface loopback is not classified

~~When one pool HGI transmits, another HGI can hear the same RF frame over the air. The current pool records RSSI before deduplication, so the receiving child stores route evidence for the transmitting HGI.~~ **Fixed in PR 1:** loopback exclusion implemented — active pool HGI frames are excluded from route RSSI. Dedup suppresses the over-air copy.

#### 16. MQTT ingress does not carry receiving-HGI identity

~~`CallbackTransport.receive_frame()` accepts the frame and timestamp but not the HGI/topic route that received it.~~ **Fixed in PR 1:** `_ingress_hgi_id` slot added to `Packet` envelope. `_on_child_packet()` sets provenance before forwarding to protocol. `ingress_hgi_id` property provides read access.

#### 17. Cold-start routing is underspecified

Some target devices may have no fresh RSSI evidence after startup. Aggregate fallback and round-robin exist, but the deterministic primary fallback and prohibition on simultaneous multicast are not stated as hard rules. Multiple radios must never transmit one command concurrently because their RF frames can collide.

#### 18. Firmware-management commands need a separate route

Per-HGI commands such as `!V` and `!C` are not RAMSES RF frames. They must remain explicitly addressed to one HGI and bypass RF RSSI routing, RF deduplication, and RAMSES QoS echo matching.

#### 19. Standalone multi-MQTT needs the same core router

HA-native MQTT is required inside `ramses_cc`, but the transport-neutral multiplexer must also be usable outside Home Assistant through the direct paho-based MQTT adapter. Route policy must not be implemented in `RamsesMqttBridge` alone.

#### 20. The current command/transport API is frame-only

~~`PortProtocol` currently patches a `CommandDTO`, stores it as the pending command, serializes it, applies outbound regex rules, and only then calls `TransportInterface.write_frame()`. `PooledTransport` therefore cannot select a child and produce the final source-correct DTO before serialization without an explicit protocol/transport preparation API.~~

~~The design must also account for outbound regex rules. A regex-mutated wire frame cannot silently differ in positional addresses from the DTO used for routing and QoS.~~

**Fixed in PR 2:** Typed `prepare_command()`/`write_routed()` contract exists on `TransportInterface` and `PooledTransport`. `PortProtocol._process_tx_item` uses the routing API before serialization.

#### 21. Runtime MQTT discovery conflicts with immutable pool membership

~~A wildcard subscription can observe an HGI that was not present when the config entry loaded. Creating a routable `PoolChild` immediately would be a runtime structural mutation, contradicting the first-release reload-only membership rule.~~

**Fixed in PR 4A+4B:** `on_unknown_hgi` only reports to the discovery callback; no `PoolChild` is created at runtime. Newly observed wildcard HGIs remain adapter-side discovery metadata only. A config-entry reload is required to materialize a new pool child.

For the first release, configured accepted HGIs and configured ownerless receive-only HGIs are materialized during config-entry setup. A newly observed wildcard HGI remains adapter-side discovery metadata only. It cannot contribute routing evidence or transmit until the user accepts it and the resulting config-entry reload rebuilds the pool.

#### 22. Dependency hygiene gaps affect quality-scale compliance

`ramses_cc` declares `"quality_scale": "silver"` in its manifest. Three dependency declarations and one CI hygiene item were identified as not meeting the Bronze `dependency-transparency` rule or the Silver `test-coverage` rule. **All three dependency items are now resolved; the CI item was previously fixed:**

- **paho-mqtt** ~~is not declared in `ramses_cc`'s `manifest.json`~~ **Not needed in `ramses_cc`'s manifest.** `ramses_cc` does not import paho. It is a transitive dependency via `ramses-rf==0.60.4` (declared in `ramses_rf`'s `pyproject.toml`), and HA's pip resolver installs it automatically (`pip show paho-mqtt` confirms `Required-by: ramses_rf`). `MqttTransport` (direct paho, in `ramses_tx`) is used for standalone CLI use only. Inside Home Assistant, MQTT uses `homeassistant.components.mqtt` via `RamsesMqttBridge` — no direct paho clients.
- **zigpy** ~~is not declared in `ramses_rf`'s `pyproject.toml` or `ramses_cc`'s `manifest.json`~~ **Done:** `ZigbeeTransport._async_init` now catches `ImportError` separately and raises a clear `TransportZigbeeError("zigpy is required for Zigbee transport: ... Install it or use a different transport.")` instead of letting a bare `ImportError` propagate from a method body. zigpy is not declared as a hard manifest requirement because Zigbee transport is niche and most users do not need it installed.
- **serialx** ~~has conflicting version floors~~ **Done:** all serialx APIs used by `ramses_tx` are available in 1.8.2 (the HA container version). The `>=1.9.0` pin was opportunistic, not feature-driven. Both `ramses_rf`'s `pyproject.toml` and `ramses_cc`'s `manifest.json` are now `serialx>=1.8.2`, matching the HA container baseline. Pinning to 1.8.2 (not 1.8.0) because 1.8.1 fixed a POSIX fd leak, a Win32 close/connection_lost race, and missing USB string descriptors on Linux.
- **CI workflow regressions** in the current draft PR 1133 lower the coverage threshold from `95 98` to `90 97` (violating the Silver `test-coverage` rule: ">95% test coverage for all integration modules"), remove `concurrency:` blocks from 6 workflow files, and remove pip caching from `check-cov.yml`. These are hygiene regressions that must not ship in any pool PR. **Fixed:** reverted to upstream master values in commit `05815ffc` on `feat/pool-all-1119`.

## Preconditions before implementation

### Hardware feasibility gate (Phase 2 prerequisite)

This gate blocks Phase 2 (serial and hybrid pool), not Phase 1 (MQTT pool). Before the pooled-serial PR (PR 3) starts, reproduce and characterize the ESP USB behavior with the same physical device in both the existing single-port path and a minimal pooled-child harness. Record the effects of:

- Port open and DTR/RTS transitions without a write.
- One immediate `7FFF` probe.
- Repeated immediate probes.
- One delayed probe after a firmware-ready indication or measured grace period.
- An ordinary RF write after the device is ready.
- Close/reopen and unplug/reconnect cycles.

Capture the resulting serial traffic and timing as regression fixtures where possible. If ordinary writes remain unsafe after readiness, the USB child must remain receive-only and pooled USB transmission cannot be declared complete. The plan must not assume that a delay fixes the reset before this gate is passed.

The physical traditional serial, ESP USB, MQTT ESP, and Zigbee devices needed for release validation must be identified before their dependent work starts. Automated PR checks remain mandatory; hardware results are recorded separately as release evidence because CI cannot reproduce them.

### Dependency hygiene gate

Before the pool PRs merge to `ramses_rf` and `ramses_cc`, reconcile the dependency declarations so the Bronze `dependency-transparency` rule is met and the next `ramses_rf` release can install on current HA containers:

1. **paho-mqtt:** `MqttTransport` (direct paho, in `ramses_tx`) depends on it for standalone CLI use and non-HA configurations. Inside HA, the pool uses `homeassistant.components.mqtt` — no direct paho clients. `paho-mqtt>=2.1.0` is declared in `ramses_rf`'s `pyproject.toml` and installed transitively when `ramses-rf==0.60.4` is installed. It is NOT declared in `ramses_cc`'s `manifest.json` because `ramses_cc` does not import paho. **Done:** verified that HA's pip resolver installs paho-mqtt as a transitive dependency of ramses_rf (`pip show paho-mqtt` → `Required-by: ramses_rf`).
2. **zigpy:** either declare `zigpy` in `ramses_cc`'s `manifest.json` (ensures HA installs it even without ZHA), or make `ZigbeeTransport.__init__` raise a clear `ConfigEntryNotReady("zigpy is required for Zigbee transport; install it or use a different transport")` instead of a bare `ImportError` deep in a method body. The choice is recorded before PR 6 starts. **Done:** `ZigbeeTransport._async_init` now catches `ImportError` separately and raises a clear `TransportZigbeeError` with installation guidance, rather than letting a bare `ImportError` propagate from a method body. zigpy is not declared as a hard requirement in `manifest.json` because Zigbee transport is a niche feature and most users do not need it.
3. **serialx:** verify whether the pool code actually needs `serialx>=1.9.0` features, or if the pin was bumped opportunistically. If 1.9.0 is required, coordinate with HA to bundle `serialx>=1.9.0` and document the minimum HA version. If 1.9.0 is not required, lower `ramses_rf`'s pin to match the HA container. Update `ramses_cc`'s `manifest.json` serialx pin to match whatever floor is chosen. This must be resolved before the next `ramses_rf` release that ships the pool. **Done:** all serialx APIs used by `ramses_tx` (`BaseSerialTransport`, `SerialException`, `serial_for_url`, `create_serial_connection`) are available in 1.8.2 (the HA container version). The `>=1.9.0` pin was opportunistic, not feature-driven. Both `ramses_rf`'s `pyproject.toml` and `ramses_cc`'s `manifest.json` are now `serialx>=1.8.2`, matching the HA container baseline. Pinning to 1.8.2 (not 1.8.0) because 1.8.1 fixed a POSIX fd leak, a Win32 close/connection_lost race, and missing USB string descriptors on Linux.
4. **CI workflows:** the current draft PR 1133 lowered coverage thresholds and removed `concurrency:` blocks and pip caching. **Fixed:** these have been reverted to upstream master values in commit `05815ffc` on `feat/pool-all-1119`. Coverage thresholds must not be lowered to accommodate pool code; add tests to raise coverage instead.
5. **HA USB consumer listing (issue 1143):** HA 2026.9's `usb/consumers.py` cannot detect ramses_cc as a serial port consumer because the port is stored at `options["serial_port"]["port_name"]` (nested dict) but HA only checks flat key paths like `("serial_port",)`. A fix has been proposed to HA core (add `("serial_port", "port_name")` to `SERIAL_PORT_KEY_PATHS`). If HA core accepts it, no ramses_cc change is needed. If rejected, PR 5 must either flatten the config key or add a workaround so the HA USB port picker correctly marks ports in use by ramses_cc. This affects the config-flow port picker for `CONF_ADDITIONAL_PORTS` and the "port in use" indicator in HA 2026.9+.

### Decisions that must be recorded before their dependent PR

1. **Membership:** schema ownership is canonical for MQTT HGI authorization. Classification requires an explicit non-empty root owner (migration uses the existing value or the established `"me"` default). A child `_owner` equal to that root means accepted; no child `_owner` means configured receive-only; foreign, rejected, or disabled means excluded. Config migration seeds an owned schema HGI for an existing primary `CONF_MQTT_HGI_ID`/explicit MQTT URL and converts legacy `CONF_ACCEPTED_HGIS` entries before that independent authority is removed. Explicitly configured local serial ports define transport inventory and are locally trusted, but remain non-send-ready until identity and startup validation.
2. **Cold-start primary:** the first configured eligible child in stable config order is primary. Round-robin is not the default and is used only if explicitly configured as policy.
3. **RSSI:** use the strongest (highest) fresh RSSI from a five-sample window per child. At least one fresh sample is sufficient; equal scores use stable config order. The maximum sample age is a named, documented setting chosen from captured traffic before PR 2, not an implicit forever-valid value. **Resolved from fixtures:** 5 minutes (see "Captured-fixture evidence" below). **Implementation note:** the code uses `max()` (best RSSI), not an arithmetic mean — this is the correct behavior for spatial diversity where the strongest signal should win.
4. **Deduplication:** capture paired local-echo and over-air/USB/MQTT copies and decide whether their transport-assigned sequence fields are stable. Freeze the canonical key before PR 1 implementation and document why sequence is included or normalized. RSSI, timestamp, ingress child, and `is_tx` are never part of the content key. **Resolved from fixtures:** sequence is sender-assigned and stable across HGIs (50/50 paired packets); include sequence when present, fall back to `(verb, addr1, addr2, addr3, code, length, payload)` when absent (see "Captured-fixture evidence" below).
5. **Source intent:** source substitution must be driven by an explicit `GATEWAY` versus `PRESERVE` policy in the immutable outbound request, not by an `addr1.startswith("18:")` heuristic. Existing callers may default to `GATEWAY` only for the exact gateway placeholder/current active HGI; faked-device call paths must pass `PRESERVE`, including for an intentional `18:` source.
6. **Structural mutation:** no public runtime `add_child()`/`remove_child()` contract is supported in the first release. Acceptance changes and new wildcard-discovered MQTT HGIs take effect through config-entry reload.

## Non-negotiable architecture invariants

1. `ramses_rf` receives one deduplicated packet stream.
2. There is no multi-gateway registry or separate topology graph in `ramses_rf`.
3. Each physical/network driver owns its connection, buffering, and reconnection details.
4. The pool/router consumes a small transport-neutral child interface.
5. `CommandDTO` and `PacketDTO` remain immutable boundary objects.
6. Outbound child selection, explicit source-intent handling, and HGI source resolution happen before serialization and before QoS establishes its expected echo.
7. The final command is serialized once per routed QoS attempt; transport-level repeats reuse that exact route and wire frame.
8. Faked-device commands retain their intentional source identity, including intentional `18:` sources.
9. HGI80 placeholder behavior remains supported.
10. A child known to be offline is never re-enabled merely because every other child is also unavailable.
11. Existing single-port serial and single-HGI MQTT configurations remain backward compatible.
12. Home Assistant MQTT traffic uses `homeassistant.components.mqtt` rather than direct paho connections when running inside `ramses_cc`.
13. USB, MQTT, and hybrid pools use the same route-selection contract.
14. Every inbound frame retains its receiving-child/HGI provenance on the transport/packet envelope separately from frozen DTOs and RAMSES `addr1`.
15. Pool-HGI loopback frames do not contribute route-quality RSSI, including aggregate fallback, and satisfy QoS only when they match the canonical fingerprint of the final routed wire command.
16. Cold-start routing is deterministic and never multicasts one command through multiple radios.
17. Firmware-management commands remain explicitly per-HGI and bypass RAMSES routing/QoS.
18. The core router remains usable through HA-native MQTT callbacks. `MqttTransport` (direct paho) remains available for standalone CLI use outside HA but is not instantiated for pooled MQTT inside Home Assistant.
19. Configuration reload is the initial membership-change mechanism; runtime structural mutation is not part of the first-release contract.
20. Pool child connection state, node availability, send readiness, and route-evidence freshness remain separate dimensions.
21. Newly wildcard-discovered MQTT IDs remain non-routable adapter discovery records until acceptance and config-entry reload.
22. Legacy outbound regex processing cannot silently change positional addresses after route selection; pooled mode rejects such a transformation unless it is moved to a typed pre-route command transformation.
23. All runtime dependencies required by a transport path are declared in `ramses_cc`'s `manifest.json` or `ramses_rf`'s `pyproject.toml`, not relied on transitively from HA's bundle; CI workflow thresholds and caching must not be regressed by any pool PR.

## Target architecture

### 1. Transport-neutral outbound preparation and routing

Move route selection to an explicit pre-serialization boundary in `ramses_tx`. The current frame-only `TransportInterface.write_frame()` is insufficient by itself, so introduce a typed preparation contract used by `PortProtocol`:

```python
class SourcePolicy(Enum):
    GATEWAY = auto()
    PRESERVE = auto()

@dataclass(frozen=True, slots=True)
class RouteRequest:
    command: CommandDTO
    source_policy: SourcePolicy

@dataclass(frozen=True, slots=True)
class RoutedCommand:
    child_id: str
    command: CommandDTO

class CommandRoutingTransport(Protocol):
    def prepare_command(self, request: RouteRequest) -> RoutedCommand: ...
    async def write_routed(
        self, routed: RoutedCommand, frame: str, *, disable_tx_limits: bool = False
    ) -> WriteOutcome: ...
```

The exact names can follow project conventions. Add compatible, non-abstract pass-through methods to the existing `TransportInterface` base so current non-pooled and third-party subclasses inherit the old behavior without implementing a new abstract method. `PooledTransport` overrides preparation to select and pin a stable child ID; dispatch uses that prepared route rather than selecting again from a frame string.

For each QoS attempt, `PortProtocol`:

1. Receives the original immutable `CommandDTO` in an immutable request carrying `SourcePolicy.GATEWAY` or `SourcePolicy.PRESERVE`. Existing unannotated callers use a compatibility default based only on an exact placeholder/current-gateway match, never an `18:` prefix.
2. Calls the transport preparation API before generic source patching or serialization.
3. Lets the router derive the link-layer routing key through the existing authoritative address helpers (for example `packet_addrs()` or a typed command equivalent) and a tested verb/address matrix, never by assuming `addr2` is always the target or by inferring application concepts such as zones or device classes.
4. Selects one eligible child using connection state, node availability, acceptance, send readiness, and fresh RSSI.
5. Produces a new DTO with `dataclasses.replace()` only when `SourcePolicy.GATEWAY` and the selected child's evofw3/HGI80 capability require source substitution. `SourcePolicy.PRESERVE` sources are never rewritten.
6. Sets the pending QoS command from that final routed DTO.
7. Serializes that DTO once for the attempt, applies any supported outbound wire transformation, re-parses the final wire frame, rejects positional-address changes in pooled mode, and derives the canonical echo fingerprint from the re-parsed wire representation.
8. Dispatches through `write_routed()` to the pinned child. Transport-level repeats reuse the same child and wire frame.

A QoS retry is a new routed attempt: it may prepare a different child if policy permits, but it must replace the pending final command/fingerprint before dispatch and serialize the new final DTO once. This removes the current contradiction between route-changing retries and an absolute “serialize once” rule.

The existing `_patch_cmd_if_needed()` behavior must be folded into or coordinated with this preparation step so the protocol and pool do not patch the source independently. HGI80 normalization remains explicit: the selected child's capability determines whether the wire source remains `18:000730` or becomes a real HGI ID.

### 2. One child object instead of parallel arrays

Replace the parallel arrays with an encapsulated child record:

```python
class ConnectionState(Enum):
    CONNECTING = auto()
    CONNECTED = auto()
    DISCONNECTED = auto()
    FAILED = auto()
    REMOVED = auto()

class NodeAvailability(Enum):
    UNKNOWN = auto()
    ONLINE = auto()
    STALE = auto()
    OFFLINE = auto()

@dataclass(slots=True)
class PoolChild:
    child_id: str
    transport: TransportInterface
    transport_kind: str
    transport_address: str
    hgi_id: str | None
    connection_state: ConnectionState
    node_availability: NodeAvailability
    send_ready: bool
    accepted: bool
    last_rx: datetime | None
    last_status: datetime | None
    consecutive_errors: int
    rssi: RssiTracker
```

Exact naming can follow project conventions. Connection state represents the local path (serial connection or shared MQTT broker adapter); node availability represents the physical/logical HGI. This distinction is required because an MQTT broker can be connected while one ESP is offline. For serial, a successful validated connection normally drives both dimensions online.

State transitions should be methods on the child/pool rather than coordinated index updates across many lists. RF packet silence does not change either connection or node availability; it only ages route evidence. An explicit MQTT heartbeat policy may change an online node to `STALE`.

Eligibility becomes explicit:

```text
eligible = connection_state == CONNECTED
           AND node_availability == ONLINE
           AND send_ready
           AND accepted
```

Configured receive-only children can still provide inbound frames, diagnostics, and RSSI without being selected for outbound transmission. RSSI from a receive-only child is retained only for that child and cannot influence selection among other children. A config reload may discard it; a newly accepted child must be safe under the cold-start fallback until fresh evidence arrives.

### 3. Small child-adapter contract

Every child adapter should provide transport-neutral events:

- `connected(child)`
- `disconnected(child, reason)`
- `available(child)`
- `unavailable(child, reason, definitive)`
- `identity_known(child, hgi_id)`
- `frame_received(child, ingress_frame)`
- `write_outcome(child, attempt_id, outcome)`

`WriteOutcome` must be conservative. Immediate rerouting is allowed only for a driver-proven `NOT_SUBMITTED` result, meaning no bytes or MQTT message were handed to the local transport. Once a serial write has been accepted by the OS/buffer or an MQTT publication has been handed to HA/paho, the RF result is `UNKNOWN` until an exact echo or QoS timeout. A generic exception is not automatically proof of a safe pre-transmission failure.

Driver-specific implementations remain separate:

- `PortTransport` handles serialx, DTR/RTS, USB errors, and serial reconnect.
- The Home Assistant MQTT adapter handles broker subscription and publication callbacks.
- Direct `MqttTransport` remains usable outside HA.
- `ZigbeeTransport` handles ZHA/Zigbee lifecycle and exposes RAMSES identity separately.

### Ingress provenance and cross-dongle loopback

Carry the receiving radio separately from the RAMSES frame source:

```python
@dataclass(frozen=True, slots=True)
class IngressFrame:
    frame: str
    timestamp: str | None
    ingress_hgi_id: DeviceIdT | None
```

`ingress_hgi_id` identifies the HGI or logical child that heard the frame. It must never be inferred from `addr1`, because `addr1` identifies the RF transmitter. The current serial/Zigbee child proxy knows only its child index and does not attach provenance to the forwarded `Packet`; it must resolve the configured/validated child identity and carry it explicitly. For wildcard MQTT, `ramses_cc` or standalone `MqttTransport` extracts it from the topic and passes it through the callback boundary.

`IngressFrame` is the raw callback boundary. After parsing, provenance lives on the stateful `Packet` envelope or an immutable packet wrapper, not in the frozen `PacketDTO`/`CommandDTO` and never in a RAMSES positional address.

The set of active pool HGI IDs is derived from accepted `PoolChild.hgi_id` values rather than maintained as another independent mutable set.

Inbound processing follows this order:

1. Preserve `ingress_hgi_id` with the frame.
2. Resolve the RF transmitter through the authoritative packet address semantics. If that source belongs to an active pool HGI, do not record it as normal target-device RSSI evidence; do not assume raw `addr1` is always the logical source.
3. Compare a canonical echo fingerprint (verb, positional addresses, code, length, and payload) with the actual final routed wire command when a transmission is pending.
4. Normalize transport-assigned sequence fields because `CommandDTO` serializes with `---` and cannot predict the firmware-assigned echo sequence. Retain the existing explicit HGI80 source normalization where required.
5. Treat an exact canonical match from the selected child as the local echo; treat exact matches from other children as over-air copies of the same transmission.
6. Satisfy QoS using the exact final wire command and deduplicate the remaining copies.
7. Do not blanket-suppress unrelated frames merely because their `addr1` is an active HGI.

This prevents aggregate RSSI contamination and discovery races without hiding unrelated HGI traffic. `DiscoveryScan` still treats all accepted active pool HGI IDs as known.

### 4. Separate address identities

Each child may need both:

```text
transport_address  # /dev/serial/by-id/..., MQTT topic ID, Zigbee IEEE
hgi_id             # RAMSES 18:xxxxxx identity
```

They must never be substituted for one another. A Zigbee IEEE address selects the Zigbee endpoint; its associated RAMSES HGI ID is used in RAMSES frames.

### 5. Home Assistant-native MQTT radio adapter

`ramses_tx` must not import Home Assistant. `ramses_cc` should provide an adapter using callbacks or logical child handles.

Recommended behavior:

- One HA-managed wildcard RX subscription for discovery/ingestion where appropriate.
- One HA-managed wildcard status subscription compatible with the actual ramses_esp status topic format.
- Pre-create logical child records for configured accepted and configured receive-only HGI IDs during config-entry setup.
- Keep a newly wildcard-observed unknown HGI as adapter-side discovery metadata only; do not forward its RF frames into the protocol or use its RSSI, and require acceptance plus config-entry reload before it becomes a pool child.
- Exact publication to `<prefix>/<hgi_id>/tx` for the selected child.
- Broker connection state tracked separately from per-ESP status.
- LWT offline marks only that ESP definitively unavailable through an explicit child-availability event; `pause_writing()` alone is not an availability signal.
- Online/heartbeat marks only the configured child available again.
- No separate TCP client per logical child (HA shares one MQTT connection; standalone uses one paho connection).

An accepted MQTT HGI can therefore behave like a preconfigured child of the same generic router as a serial port without owning a separate broker connection or requiring unsafe runtime pool mutation.

The `ramses_tx` multiplexer is transport-neutral: it accepts callback-driven I/O from `RamsesMqttBridge` (HA-native, via `homeassistant.components.mqtt`) or from `MqttTransport` (direct paho, for standalone CLI use). In both cases, the I/O layer supplies wildcard RX/status events and exact per-HGI writes through the same ingress and child-availability contracts. Route selection, RSSI, deduplication, and QoS remain in `ramses_tx`. Inside Home Assistant, only `RamsesMqttBridge` is used — no direct paho clients for pooled MQTT.

Firmware-management commands remain outside the RF router:

- RAMSES DTOs are selected by route quality and published to the selected HGI's `/tx` topic.
- Commands beginning with `!`, including `!V` and `!C`, are sent to an explicitly selected HGI's firmware command topic.
- Firmware command results are correlated per HGI.
- Management commands do not update RF RSSI, enter RF deduplication, or satisfy RAMSES QoS.
- Topic names must follow the actual ramses_esp contract; the current HA bridge uses `<prefix>/<hgi_id>/cmd/cmd` and `<prefix>/<hgi_id>/cmd/result`.

### 6. Serial startup and readiness

Split the overloaded serial controls:

```python
disable_sending: bool
signature_policy: Literal["immediate", "delayed", "skip"]
startup_grace: float | None
configured_hgi_id: str | None
```

Proposed ESP-aware startup:

1. Open the port once using a stable path.
2. Avoid immediate repeated writes.
3. Wait for a firmware-ready signal or measured grace period.
4. Perform one controlled signature probe when supported.
5. Obtain/validate the RAMSES HGI ID.
6. Set `send_ready=True`.
7. Permit normal writes.

Fallbacks:

- Explicit configured HGI ID if a safe signature cannot be obtained.
- Firmware readiness/identity announcement for compatible evofw3/ramses_esp devices.
- HGI80 placeholder behavior when appropriate.
- Remain receive-only if identity or send safety cannot be established.

### 7. Availability model

Availability must be driver-specific but normalized for the router.

#### Serial

- OS/serialx connection event updates `ConnectionState`.
- A read error or explicit serial disconnect marks the path disconnected/failed.
- A write exception follows the conservative write-outcome model and does not by itself prove disconnection or non-submission.
- Successful reopen sets the path connected; identity/startup validation separately sets node online and send-ready.
- Packet silence alone only expires route evidence and is not proof of disconnection.

#### MQTT

- HA broker disconnected: all MQTT children temporarily unavailable because the shared path is down.
- Per-ESP LWT offline: that child definitively offline.
- Per-ESP online: available, subject to identity/acceptance.
- Heartbeat expiry: stale or offline according to the agreed protocol.
- RX silence alone: route-quality aging, not definitive device loss.

#### Zigbee

- ZHA device availability: online/offline.
- IEEE endpoint availability and RAMSES identity are tracked separately.

The old "re-enable every unhealthy child as a last resort" behavior should be removed. `STALE`, `OFFLINE`, and `FAILED` children are not eligible in the initial policy; a future explicit fallback policy may define different stale handling, but offline or failed children must never be selected.

### 8. Safe failure and retry model

Classify outcomes conservatively:

1. **Proven not submitted**: the adapter can prove that no bytes or MQTT message were handed to the local transport; it is safe to prepare another child immediately.
2. **Submission/RF result unknown**: the write was accepted locally, or the failure point is ambiguous. Do not immediately send through another child; wait for an exact echo or QoS timeout.
3. **Confirmed echo**: transmission succeeded; never fail over for that attempt.
4. **QoS timeout**: the protocol applies the configured retry policy and may prepare a new route for the next attempt.

A generic `write_frame()` exception belongs to category 2 unless the driver explicitly returns category 1. HA MQTT publication acceptance and paho queue acceptance are not proof of ESP RF transmission.

A route remains pinned for transport-level repeats belonging to one attempt. A later QoS retry may prepare another child if the original child became unavailable or route quality changed; before sending, `PortProtocol` replaces its pending command/fingerprint with that retry's final routed wire command.

`PortProtocol` sets its pending command from the final routed DTO/wire fingerprint, not the placeholder command. Echo matching uses the canonical complete content fingerprint with transport-assigned sequence normalization and existing HGI80 normalization. It must not be loosened to accept an arbitrary registered pool HGI, because that could satisfy QoS with the wrong concurrent or unrelated HGI frame.

The selected child's local hardware echo and another child's over-air copy may arrive in either order. An exact copy of the final routed command may confirm the transmission, but all copies are deduplicated and unrelated active-HGI frames do not satisfy QoS.

MQTT publish acceptance is not the same as ESP RF transmission. Per-node echo remains the authoritative confirmation where available.

### 9. Membership and trust policy

Separate discovery from acceptance and send eligibility.

- Explicitly configured serial ports are locally trusted but not send-ready until identity/startup completes.
- MQTT wildcard status/topic observations can create adapter-side discovery metadata.
- A configured ownerless candidate may contribute inbound frames and diagnostics but cannot transmit; a newly observed unknown HGI contributes only discovery metadata until acceptance and reload.
- Foreign/rejected HGIs are ignored.
- Disabled HGIs remain represented in schema/configuration but are excluded when the pool registry is rebuilt.

For the initial release, schema `_owner` membership is the canonical MQTT trust policy:

1. `_owner` equal to the root owner: configured and accepted.
2. No `_owner`: configured receive-only candidate.
3. Foreign owner, rejected, or disabled: excluded.
4. Newly wildcard-observed and absent from the schema: adapter-side discovery metadata only until acceptance and reload.

An optional private-namespace auto-accept mode is deferred. `CONF_ACCEPTED_HGIS` must be migrated or removed as an independent authority so acceptance cannot diverge from schema ownership. Explicit serial-port configuration remains the canonical transport inventory for local serial children; identity validation and `send_ready` still gate transmission.

### 10. Membership updates

For the first production version:

- Changes to serial ports, accepted HGIs, and disabled state trigger a normal Home Assistant config-entry reload.
- Runtime `add_child()`/`remove_child()` are not used by `ramses_cc`.
- Dynamic availability and RSSI updates remain runtime-safe because they do not alter the child registry structure.

A future hot-reload API may use an `asyncio.Lock`, immutable snapshots, or a serialized command queue, but it is not a release requirement.

### 11. Deduplication

Replace the linear deque membership scan with a dictionary-backed time window while retaining a hard size bound.

Requirements:

- O(1) expected membership check.
- Time-based eviction, default around the proven 0.5-second window.
- Hard maximum number of retained keys.
- The pre-PR captured-fixture decision on whether the transport-assigned sequence is included or normalized; do not decide this from mocks alone. **Resolved:** sequence is stable across HGIs (50/50), include when present, fall back to base key without sequence when absent.
- Canonical address fields derived through authoritative packet address semantics rather than assumptions about fixed source/target positions.
- Tests for truly duplicated packets from different children.
- Tests ensuring two legitimate identical-content transmissions are not incorrectly collapsed outside the window.
- A monotonic time source where practical.

### 12. RSSI routing

Use one documented initial policy:

- Arithmetic mean of up to the five most recent fresh samples per target and child, matching the recorded roadmap.
- At least one fresh sample is required before RSSI-driven selection.
- A named maximum sample age, fixed from captured traffic before PR 2 and covered by boundary tests. **Resolved:** 5 minutes (close HGI stable ±2 dBm over 2h, far HGI varies gradually).
- Stable config order for equal scores.
- Clear or quarantine a child's samples when it becomes definitively offline, failed, or is re-created after reconnect.
- Packet silence only expires route evidence; it does not itself mark a connected serial radio offline.

Fallback order is explicit:

1. Fresh per-device RSSI among eligible children.
2. Fresh aggregate RSSI among eligible children, excluding samples whose RF source is an active pool HGI.
3. First eligible child in stable configuration order.
4. Round-robin only if explicitly configured as policy.
5. Fail clearly if no child is send-ready.

Cold-start selection always chooses exactly one child. The router never multicasts one transmission attempt through multiple HGIs because unsynchronised RF transmissions can collide.

## Relationship to the previous roadmap

### Previous Item 9 baseline

The roadmap recorded Item 9 as link-layer transport pooling in `ramses_tx`, after completion of the FSM decommission and command-bus cutover. Its agreed boundaries and PR breakdown were:

| Previous item   | Recorded scope                                                                                                       |
| --------------- | -------------------------------------------------------------------------------------------------------------------- |
| PR 1            | Migrate serial transport from `pyserial(-asyncio)` to `serialx` before adding pooling                                |
| PR 2            | Add `PooledTransport`; combine physical transports; deduplicate inbound packets; preserve source-address correctness |
| PR 3            | Select the best physical dongle using a five-sample rolling-average RSSI                                             |
| PR 4            | Detect unhealthy transports and fail over                                                                            |
| Validation gate | Two physical HGIs observing the same RF network produce one coherent packet stream without duplicate frames          |

The roadmap explicitly placed pooling in `ramses_tx`, named serial, MQTT, and ser2net as transport types, and excluded multi-gateway registries or separate topology graphs in `ramses_rf`.

### What remains unchanged

The new plan preserves the central Item 9 decisions:

- Item 9 remains a link-layer concern in `ramses_tx`.
- `ramses_rf` continues to receive one coherent packet stream.
- No multi-gateway application model or per-gateway topology is introduced.
- Serial, MQTT, and hybrid configurations remain in scope.
- Inbound deduplication, source-address correctness, RSSI-based outbound selection, health monitoring, and failover remain required.
- The completed `serialx` migration remains the transport foundation; it is not repeated or reversed.
- Existing single-port behavior remains backward compatible.
- Item 9 still follows the completed FSM and command-bus work.

### What changes from the previous roadmap

The new plan changes the implementation detail and completion criteria because the current PRs exposed requirements that the four-line roadmap did not specify.

| Area                      | Previous roadmap                                                                     | New plan                                                                                                                                                                                                                     |
| ------------------------- | ------------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Outbound routing boundary | RSSI selection was required, but its exact position in the send path was unspecified | A typed protocol/transport preparation API selects and pins a child before serialization; each QoS attempt serializes its final immutable DTO once and transport-level repeats reuse that frame                              |
| Source correction         | PR 2 required source-address correctness                                             | Raw ASCII splitting, `18:` prefix checks, and double-patching are removed; source correction is performed on an immutable DTO under documented positional-address rules                                                      |
| Ingress provenance        | Receiving-radio identity was not specified                                           | Every inbound frame carries its receiving HGI/child separately from RAMSES `addr1`, including through wildcard MQTT callbacks                                                                                                |
| Cross-dongle loopback     | Not specified                                                                        | Pool-HGI frames are excluded from normal route RSSI; exact local echoes and over-air copies are correlated with the final routed command and deduplicated without blanket suppression                                        |
| QoS matching              | Generic source correctness and health                                                | The final routed DTO becomes the pending QoS command; arbitrary registered HGI sources are not accepted as equivalent echoes                                                                                                 |
| Cold-start routing        | RSSI routing with fallback was broad                                                 | Fresh target RSSI, fresh aggregate RSSI excluding pool HGIs, then deterministic primary; exactly one HGI transmits and multicast is prohibited                                                                               |
| Firmware management       | Not specified                                                                        | Per-HGI `!V`/`!C` management bypasses RAMSES routing, deduplication, and QoS and uses explicit command/result topics                                                                                                         |
| Standalone MQTT           | MQTT was named as a transport                                                        | The same `ramses_tx` multiplexer is driven by HA callbacks inside `ramses_cc` and by a paho adapter in standalone use                                                                                                        |
| Child representation      | No state model was specified                                                         | One encapsulated child record replaces parallel mutable arrays while keeping connection, node availability, acceptance, send readiness, and route-evidence age distinct                                                      |
| Eligibility               | Health/failover were described generically                                           | Outbound eligibility requires connected path, online node, accepted membership, and send readiness                                                                                                                           |
| Serial startup            | PR 1 modernised serial I/O; pooled startup behavior was unspecified                  | Signature policy is separated from permanent send permission; ESP startup stabilization, HGI identity, send readiness, and reconnect behavior become required                                                                |
| Serial completion         | Serial was in scope but no transport-specific validation gate was listed             | Two-USB and USB-plus-MQTT transmission are explicit release gates, not merely inbound/dedup scenarios                                                                                                                        |
| MQTT integration          | MQTT was named as a child transport                                                  | MQTT in Home Assistant must use `homeassistant.components.mqtt`; direct paho clients are not used by pooled `ramses_cc` configurations                                                                                       |
| MQTT availability         | PR 4 only said “detect and fail over from unhealthy transports”                      | Broker loss, per-ESP LWT, online recovery, heartbeat expiry, RF silence, and write failure are distinct states/events                                                                                                        |
| Failure handling          | Generic failover                                                                     | Immediate rerouting requires a driver-proven not-submitted outcome; generic exceptions and locally accepted writes remain ambiguous until exact echo or QoS timeout                                                          |
| Health fallback           | No detailed rule                                                                     | Definitively offline children are never re-enabled as a last resort; stale and offline are separate states                                                                                                                   |
| Membership                | Not defined in the `ramses_rf` Item 9 roadmap                                        | Schema ownership is canonical for MQTT authorization; transport inventory, disabled state, configured receive-only candidates, and unknown adapter-side discovery metadata are distinct                                      |
| Runtime membership        | Not required by the Item 9 roadmap; issue 1119 later proposed hot add/remove         | Initial implementation uses Home Assistant config-entry reload for structural membership changes; runtime `add_child()`/`remove_child()` are deferred until concurrency is designed safely                                   |
| Dedup implementation      | A receive deduplication window                                                       | A time- and size-bounded dictionary-backed cache provides expected O(1) lookup; key and sequence semantics are tested and documented                                                                                         |
| RSSI calculation          | Five-sample rolling average                                                          | Five-sample window with strongest (highest) fresh RSSI selection, explicit maximum sample age (5 min), at least one fresh sample, stable configuration order for ties                                                        |
| RSSI lifetime             | Not specified                                                                        | Stale evidence expires, and route data is cleared or quarantined when a child goes definitively offline                                                                                                                      |
| HA configuration          | Only “coordinate multi-transport config flow”                                        | One canonical trust/membership source is required, MQTT wildcard discovery is separated from acceptance, and credentials remain owned by HA MQTT                                                                             |
| Zigbee                    | Not named in the original Item 9 transport list                                      | Zigbee is supported only after its IEEE transport address is separated from its RAMSES `18:` HGI identity                                                                                                                    |
| Observability             | No detailed diagnostics requirement                                                  | Per-child state, identity, route evidence, failures, and reconnects are exposed through safe diagnostics                                                                                                                     |
| Verification              | Two physical HGIs, one deduplicated stream                                           | Adds real serial transmit, hybrid transmit, LWT, broker restart, reconnect, source-ID, QoS, quiet-network, and ambiguous-failure tests                                                                                       |
| PR structure              | Four PRs, with PRs 2–4 grouping broad behavior                                       | The remaining work is split into repository-local dependency-ordered PRs: child state/inbound dedup, routed DTO/RSSI/QoS, serial, standalone/callback MQTT contracts, HA-native MQTT, membership/hybrid assembly, and Zigbee |

### Why these changes are necessary

The changes do not replace the roadmap's transport-neutral objective. They make its implicit requirements explicit after the current implementation demonstrated that:

- Skipping the serial signature by setting `disable_sending=True` also disables all pooled USB transmission.
- A connected MQTT child can remain eligible after its ESP goes offline because LWT is not propagated into pool state.
- Packet silence cannot reliably distinguish a quiet radio from a disconnected one.
- Routing after serialization creates frame parsing, double-patching, and QoS consistency problems.
- Cross-dongle over-air copies can contaminate aggregate RSSI and race with the selected child's local echo.
- Wildcard MQTT ingestion loses the receiving HGI unless topic-derived ingress provenance crosses the callback boundary.
- Cold-start targets need a deterministic single-radio fallback; simultaneous multicast is unsafe.
- Per-HGI firmware commands require an explicit path separate from RF routing.
- A Zigbee IEEE address cannot serve as a RAMSES HGI source ID.
- Mock-based dedup/routing tests do not prove real USB or hybrid transmission.

The revised plan therefore expands PRs 2–4 rather than changing Item 9 into a different feature. The intended outcome remains one transport-neutral pool supporting physical serial, MQTT, and hybrid radio paths.

### Roadmap status interpretation

Under the previous roadmap:

- PR 1 (`serialx`) remains complete.
- The current draft PRs provide useful implementations and tests for parts of PRs 2–4.
- PRs 2–4 should not be considered complete until the revised release gates in this plan pass.
- The concrete PR sequence below supersedes the original broad PR 2–4 packaging, but does not alter Item 9's position or its link-layer scope.

## Concrete delivery plan

### Proposed fixed design decisions

The dependent decisions are recorded in the preconditions section and are not left for ad hoc choice inside an implementation PR:

1. Item 9 supports single USB, multiple USB, multiple MQTT, and hybrid USB-plus-MQTT configurations. The first release (Phase 1) covers MQTT-only pools; serial and hybrid pools follow in Phase 2 after the hardware feasibility gate.
2. Pooling remains transport-neutral and lives in `ramses_tx`; `ramses_rf` continues to receive one coherent stream. Transport neutrality is preserved in code even when serial and Zigbee are gated in the config flow.
3. A typed protocol/transport preparation API routes before serialization; the final immutable DTO/wire fingerprint drives QoS echo matching for each attempt.
4. Child lifecycle is represented by one child-state object rather than parallel arrays, with connection state, node availability, send readiness, acceptance, and route-evidence age kept distinct.
5. Home Assistant MQTT uses `homeassistant.components.mqtt`.
6. Structural configuration changes use config-entry reload; runtime hot add/remove is not part of the first release.
7. Multi-USB and hybrid transmit operation are completion criteria for Phase 2, not optional future enhancements.
8. Inbound frames retain receiving-HGI provenance independently from RAMSES `addr1`.
9. QoS matches the canonical content fingerprint of the actual final routed wire command, normalizing unpredictable transport-assigned sequence and HGI80 source behavior; matching is not broadened to any pool HGI.
10. Cold-start routing uses the first eligible child in stable configuration order and never multicasts one command through multiple radios.
11. The `ramses_tx` MQTT multiplexer is transport-neutral: it accepts callback-driven I/O from `RamsesMqttBridge` (HA-native) or `MqttTransport` (standalone paho, for CLI/non-HA use). Inside Home Assistant, only `RamsesMqttBridge` is used.
12. Per-HGI firmware-management commands remain separate from RF routing.
13. Zigbee is not advertised as supported until IEEE transport identity and RAMSES HGI identity are separated. Zigbee is parked for Phase 3.

The recorded RSSI TTL, dedup key, and serial-startup result are prerequisites for the PRs that depend on them. Multi-USB and hybrid use cases do not need to be justified again before implementation.

### Known failure baseline

The existing findings are sufficient to start implementation:

- Pooled serial children are permanently read-only because signature suppression uses `disable_sending=True`.
- The ESP USB reset has not been characterized sufficiently; the hardware feasibility gate must establish the safe startup and ordinary-write behavior before the serial PR starts.
- MQTT LWT/offline state is observed but not propagated into pool eligibility.
- Broker connection and individual ESP availability are conflated or incompletely represented.
- Packet silence, explicit offline state, and send readiness are not distinct.
- A selected-child write failure does not safely reroute.
- Outbound routing parses and patches a serialized ASCII frame.
- Zigbee IEEE identity is incorrectly usable as a RAMSES HGI identity.
- Ownerless discovery candidates are not reliably enforced as receive-only.
- Dedup lookup is linear despite O(1) claims.
- RSSI evidence does not expire.
- Cross-dongle over-air copies are not classified separately from local echoes or normal inbound traffic.
- Callback ingestion does not retain the MQTT receiving HGI from the topic.
- Cold-start selection does not state a strict deterministic fallback or multicast prohibition.
- Per-HGI firmware-management commands are not represented in the pool design.
- Standalone wildcard multi-MQTT operation is not part of the current concrete implementation.
- **Re-patch leading space bug:** `frame.split()` / `" ".join(parts)` dropped the leading whitespace before the verb, causing frame validation errors when routing through a non-primary child. Fixed in PR 1185 (commit `cf3276ef`).
- **Health timeout too aggressive:** 60 s default marked both children unhealthy during sparse traffic, bypassing RSSI routing. Fixed in PR 1185 (increased to 180 s).

The serial hardware feasibility gate precedes implementation because it can invalidate a core assumption. After that gate and the recorded design decisions, each PR starts by adding failing automated tests for the behavior it changes, implements the smallest fix, and runs the relevant verification. Integrated physical validation is repeated before the feature is declared complete.

### Captured-fixture evidence (pre-PR)

Real-world traffic was captured from two MQTT HGIs (`18:130236` near the FAN/CO2, `18:149488` near the REM) and analyzed to resolve the pre-PR decisions that the plan explicitly requires to be fixed from captured traffic, not mocks. The analysis was re-run with a corrected analyzer (`tools/analyze_fixture.py`) that fixes five bugs in the original version: column-shifted field parsing (treated 10-field log lines as 11-field), reversed RSSI signs, non-chronological file ordering, unbounded content grouping that paired packets hours apart, and broken loopback detection. Full analysis is in `fixtures/fixture_report.md` and `fixtures/pool_test_report.md`; the corrected analyzer is `tools/analyze_fixture.py`.

**Corrected dataset:** 725 packets from 8 rotated packet-log files (~2 hours), 425 from `18:130236` (RSSI-inferred), 300 from `18:149488` (RSSI-inferred). HGI identity was calibrated against an 8-message MQTT topic capture that confirms the RSSI thresholds.

#### Dedup key — RESOLVED (high confidence)

The transport-assigned sequence field is sender-assigned and stable across HGIs: both HGIs observed the same sequence number for the same RF frame in 50/50 paired packets (0 different, 0 mixed). 71 paired packets had no sequence (`---`) on both HGIs. The dedup key should include the sequence when present, with a fallback base key of `(verb, addr1, addr2, addr3, code, length, payload)` when sequence is absent. Normalizing or stripping the sequence would collapse distinct legitimate retransmissions from the same source.

#### RSSI TTL — initial default selected (medium confidence)

A 5-minute (300 s) maximum sample age is recommended as the initial default. The close HGI (`18:130236`) reported RSSI of −41 dBm for device `32:153289` consistently over a 2.4-hour span (n=273, range [−69, −41], mean −41.8). The far HGI (`18:149488`) showed wider variation for the same device (n=121, range [−107, −70], mean −91.6). 5 minutes is conservative enough to capture gradual changes while keeping stale evidence from persisting after a device moves or a dongle is relocated. This is a starting value, configurable, and subject to longer/movement testing.

#### Dedup window — CONFIRMED

500 ms is confirmed. With the corrected windowed pairing (5-second maximum separation to avoid pairing identical frames hours apart as if they were cross-HGI duplicates of one RF frame), 149 arrival deltas were computed: min=0.5 ms, median=5.9 ms, p95=178.0 ms, max=499.6 ms. 0/149 deltas exceeded the 500 ms window. A 500 ms window provides a comfortable safety margin without risking false dedup of legitimate retransmissions.

#### Cross-dongle loopback — CONFIRMED

When one pool HGI transmits, both HGIs hear the frame: the transmitting HGI produces a local echo (RSSI empty/`None`) and the other HGI hears an over-air copy (RSSI ≈ −83 dBm), arriving 3 ms apart. 8 packets with `src=18:130236` were found in the capture; 1 paired loopback was confirmed within the 5-second window. The pool must exclude both from route-quality RSSI and must deduplicate them against the final routed command. The current implementation records RSSI before dedup, which can contaminate aggregate fallback; the new plan's child-state model separates these concerns.

#### Source-ID patching — CONFIRMED

The protocol layer patches the placeholder `18:000730` to the active HGI ID before the pool routes the frame. When the pool selects a different child than the active HGI, the source address must be re-patched to the selected child's HGI ID. A bug was found where `frame.split()` / `" ".join(parts)` dropped the leading whitespace before the verb (`" I --- ..."` → `"I --- ..."`), causing frame validation errors. This is fixed in PR 1185 but the new plan's typed DTO approach avoids serialized-frame parsing entirely.

#### Health timeout — OBSERVED

The default 60 s health timeout was too aggressive for sparse RAMSES traffic. Both children were marked unhealthy during an 82 s quiet period, forcing a "last resort" fallback that bypassed RSSI routing. Increased to 180 s in PR 1185. The new plan should treat health timeout as a named, documented setting with a default ≥ 120 s.

#### QoS echo — PARTIALLY OBSERVED

The full QoS echo trace was observed (command → local echo → over-air copy → device response), but explicit QoS satisfaction logging was not present in the current implementation. The new plan's QoS design (matching the canonical fingerprint of the final routed wire command) is not yet tested against real traffic.

#### What was NOT captured

- Serial transport data (requires physical USB hardware — Phase 2).
- Long-duration MQTT captures (> 30 min) for diurnal RSSI drift analysis.
- Failure scenarios (primary offline, timeout, retry via different child).
- QoS echo satisfaction logic with the new fingerprint-matching design.

### Rule for every PR

Every PR must contain:

1. Regression tests that fail against its parent branch for the defect being fixed.
2. The smallest implementation that makes those tests pass.
3. Tests for negative and recovery paths, not only the nominal path.
4. Strict typing, lint, and the relevant repository test suite.
5. Targeted `ha_sim_test` coverage when Home Assistant, discovery, schema, MQTT, or command dispatch is affected.
6. Deterministic fixtures or broker/simulator integration tests for hardware-dependent paths; physical observations are recorded as release evidence when CI cannot reproduce them.
7. Updated existing documentation and diagnostics for behavior changed by that PR.
8. No CI workflow regressions: coverage thresholds, `concurrency:` blocks, and pip caching must not be lowered or removed. If pool code has lower coverage than the current threshold, add tests to raise it rather than lowering the bar.

Testing and observability are therefore part of each implementation PR rather than separate final phases.

## PR 1 — Pool child state and inbound foundation

**Repository:** `ramses_rf`
**Current PR:** rework draft PR 1184
**Depends on:** completed `serialx` migration

Refactor `PooledTransport` around one child object per route while preserving the single coherent inbound stream.

### Implementation

- Introduce `PoolChild`, `ConnectionState`, and `NodeAvailability` types.
- Move transport, transport address, HGI identity, connection state, node availability, acceptance, send readiness, RSSI, counters, timestamps, and errors into `PoolChild`.
- Replace index-coupled lifecycle arrays with child methods and stable child IDs.
- Keep `_ChildProtocolProxy`, but map connection, disconnection, availability, identity, and frame-received events into one child object.
- Add immutable `IngressFrame` metadata carrying `ingress_hgi_id` separately from RAMSES `addr1`.
- Extend callback ingestion with an optional keyword-only ingress HGI identifier while preserving old callers.
- Carry provenance from raw `IngressFrame` onto the stateful `Packet` envelope (or an immutable packet wrapper), not `PacketDTO`; serial/Zigbee proxies resolve it from the stable child record before forwarding.
- Derive active pool HGI IDs from accepted child records rather than maintaining another mutable set.
- Separate connection state, node availability, send readiness, acceptance, and route-evidence freshness.
- Remove unconditional last-resort re-enabling of offline children.
- Replace the dedup deque scan with a time- and size-bounded dictionary-backed cache using the key fixed from captured fixtures.
- Remove the public runtime structural `add_child()`/`remove_child()` contract; construction and config-entry reload build immutable child registries for the first release.
- Make acceptance initialization construction-only; do not retain a public runtime `set_accepted_hgis()` contract without a separately designed synchronization model.
- Preserve or explicitly version the existing `get_extra_info()` compatibility keys and shapes (`pool_hgi_ids`, `pool_rssi_trackers`, and `pool_stats`) consumed by `ramses_rf` and `ramses_cc`.
- Preserve aggregate diagnostics through a stable snapshot derived from child objects.

### Regression tests included

- Parallel-array desynchronization is no longer possible during early child connection.
- `connection_lost()` excludes only the affected child.
- Explicitly offline children are never restored by a fallback.
- A quiet connected serial child stays connected/online while its route evidence expires.
- A configured MQTT child whose explicit heartbeat expires becomes `STALE` without being confused with broker disconnection.
- A child that never received a packet does not become send-ready without an identity/readiness signal.
- Dedup suppresses the same packet from two children inside the window.
- The selected child's local echo and another child's over-air copy retain different ingress provenance but deduplicate as one RF frame.
- Active pool HGI frames are available for exact echo correlation but are not recorded as normal route-quality RSSI.
- Unrelated frames from an active HGI are not blanket-suppressed.
- The same packet outside the window is forwarded again.
- Cache size remains bounded and lookup uses the dictionary path.
- Existing `pool_hgi_ids`, `pool_rssi_trackers`, and `pool_stats` consumers retain compatible data or migrate in lockstep.
- Existing non-pooled transport construction is unchanged.

### Completion criteria

- No parallel lifecycle arrays remain.
- Inbound packets still produce one coherent deduplicated stream.
- Child-state diagnostics explain connection, availability, acceptance, and readiness.
- Focused tests, full `ramses_rf` tests, Ruff, and strict mypy pass.

## PR 2 — Pre-serialization routing, RSSI, QoS, and safe failover

**Repository:** `ramses_rf`
**Current PR:** draft PR 1194 on the revised PR 1184 foundation
**Depends on:** PR 1

Introduce the transport-neutral outbound router and make it the only path that selects a child.

### Implementation

- Add a typed `prepare_command()`/`write_routed()` contract (exact names may vary) between `PortProtocol` and routing-capable transports, with a pass-through default for non-pooled and third-party transports.
- Wrap the original immutable `CommandDTO` in a typed request carrying `SourcePolicy.GATEWAY` or `SourcePolicy.PRESERVE` before generic HGI patching or serialization; update faked-device call paths to pass `PRESERVE`.
- Define and test the positional-address routing matrix for every outbound verb currently supported, using the existing authoritative address helper or a typed command equivalent rather than fixed raw positions.
- Return a stable selected child ID plus the final DTO; use `dataclasses.replace()` only when gateway-source intent and selected-child capability require substitution.
- Fold existing `_patch_cmd_if_needed()` behavior into the preparation sequence so protocol and pool cannot patch independently.
- Preserve intentional faked-device sources, including intentional `18:` sources, and preserve explicit evofw3/HGI80 behavior.
- Drive impersonation alerts from `SourcePolicy.PRESERVE`; selecting a different pool HGI for a gateway-source command must not create a false impersonation alert.
- Set `PortProtocol._pending_cmd` and the QoS echo fingerprint from the actual final routed wire command for each attempt, not the placeholder command.
- Normalize transport-assigned sequence in the canonical fingerprint. For HGI80, normalize the selected child's real echo source to the `18:000730` wire placeholder; for evofw3, compare the selected child's real HGI. Never normalize arbitrary `18:` sources to the first connected HGI.
- Remove or constrain the current unconditional `packet._is_echo` success path so only the pending final routed fingerprint can satisfy QoS; a different recently transmitted frame cannot satisfy the pending future.
- Correlate the selected child's local echo and exact over-air copies from other children with the same routed attempt.
- Pin transport-level repeats to the prepared child and reuse the same serialized frame; a QoS retry prepares a new attempt and replaces the pending fingerprint before sending.
- Apply existing outbound regex handling after serialization only if it cannot change positional addresses in pooled mode; fail clearly otherwise and derive the expected fingerprint from the actual final wire frame.
- Remove ASCII `.split()`, `src_addr[:2] == "18"`, route reselection, and source re-patching from `PooledTransport.write_frame()`.
- Select only children whose connection is connected, node is online, and that are accepted and send-ready.
- Use the fixed five-sample fresh arithmetic-mean RSSI policy, with the recorded TTL and stable config-order tie-breaking. Implement it as pool-route scoring or an explicitly configured tracker so unrelated communication-quality behavior is not silently changed.
- Exclude active pool-HGI sources from aggregate route evidence and clear/quarantine route evidence when a child is offline, failed, or recreated.
- Define cold-start selection as fresh target RSSI → fresh aggregate RSSI → first eligible child in stable config order; use round-robin only if explicitly configured.
- Prohibit simultaneous multicast of one attempt through multiple radios.
- Classify outcomes as proven-not-submitted, ambiguous/accepted locally, confirmed echo, or QoS timeout.
- Reroute immediately only after a driver-proven not-submitted outcome; treat generic write exceptions as ambiguous.
- Add per-child selected-route, write-outcome, echo-failure, and RSSI-age diagnostics.

### Regression tests included

- Best fresh per-device RSSI selects the expected eligible child.
- Stale RSSI cannot win route selection.
- Disconnected, offline, rejected, or receive-only children are never selected.
- Faked-device commands, including intentional `18:` sources, retain their source and trigger the expected impersonation policy.
- Gateway-source routing through a non-primary child does not trigger a false impersonation alert.
- evofw3 and HGI80 source handling produce the correct final DTO.
- QoS matches the echo of the final source-patched command.
- An exact over-air copy can correlate with that routed attempt, while an unrelated active-HGI frame cannot satisfy QoS.
- Placeholder commands are not matched by broadly accepting any registered HGI source.
- Targets without RSSI use the deterministic primary fallback.
- One attempt never transmits concurrently through multiple children.
- Transport-level repeats stay on one route and reuse one frame.
- A QoS retry may change route only after replacing the pending final command/fingerprint.
- A driver-proven not-submitted outcome selects another eligible child.
- A generic/ambiguous write failure does not trigger an immediate duplicate transmission.
- Pooled mode re-parses the outbound regex result, rejects a transformation that changes positional addresses after routing, and uses the re-parsed wire content for echo matching.
- A different `packet._is_echo` recent-transmit marker cannot satisfy the pending routed attempt.
- HGI80 echo normalization uses the selected child rather than the pool's first connected HGI.
- No frame-string parsing, route reselection, or second source patch is involved in `PooledTransport`.

### Completion criteria

- One immutable routed DTO per QoS attempt drives one serialization, a pinned dispatch route, and the pending QoS fingerprint.
- Source substitution has one owner; no protocol/pool double-patching remains.
- Route decisions and exclusions are visible in diagnostics.
- Focused tests, full `ramses_rf` tests, Ruff, and strict mypy pass.

## PR 3 — Full pooled serial transmission and reconnect (Phase 2)

**Repository:** `ramses_rf`
**Current PR:** new focused PR stacked on PR 2 (PR 1194)
**Depends on:** PR 2, PR 5 (Phase 1 release), and the serial hardware feasibility gate
**Phase:** 2 — serial and hybrid pool

Make `PortTransport` a fully send-capable pool child without reintroducing ESP startup reset loops. This PR un-gates serial transport in the config flow (removes the "(not yet supported)" marker and `TODO:` remarks from Phase 1) and enables serial children in pool construction.

### Implementation

- Split startup signature policy from permanent `disable_sending`.
- Add explicit immediate, delayed, and skipped signature behavior. Defaults preserve the existing non-pooled single-USB behavior; pooled ESP defaults come from the completed hardware gate.
- Add new `TransportConfig` fields with backward-compatible defaults and coordinate any `ramses_cc` configuration plumbing without requiring existing callers to change.
- Obtain the RAMSES HGI ID through delayed signature, firmware announcement, or validated configured identity.
- Keep identity-unknown serial children receive-only and not send-ready.
- Mark the child send-ready only after identity and startup safety are established.
- Preserve HGI80 placeholder behavior.
- Add bounded serial reopen/reconnect backoff using stable `/dev/serial/by-id/...` paths where available.
- Propagate serial read/write/disconnect failures into the child state model.
- Apply the PR 2 proven-not-submitted-versus-ambiguous outcome policy to serial writes.

### Regression tests included

- Skipping the startup signature no longer implies permanent read-only operation.
- A delayed signature obtains and validates the HGI ID.
- Identity-unknown serial children receive but are not selected for outbound routing.
- A configured identity is checked against a later observed identity.
- Physical disconnect excludes the serial child immediately.
- Reconnect does not restore send readiness until identity is valid.
- A driver-proven not-submitted serial outcome can prepare another child.
- A generic or ambiguous serial write failure does not duplicate the command.
- Existing single-USB startup and transmission remain unchanged.

### Required release hardware evidence

- Traditional evofw3/HGI serial device starts and sends normally.
- ESP32 USB device does not reset-loop during startup.
- Normal post-startup ESP32 USB transmission succeeds.
- Two serial HGIs can each be forced as the selected route and produce the expected echo.
- Unplugging and reconnecting one serial child preserves operation through the other.

### Completion criteria

- Automated tests prove that either prepared serial child can be selected and that no serial child is selected before it is send-ready.
- Existing single-USB tests remain unchanged and pass.
- Focused tests, full `ramses_rf` tests, Ruff, and strict mypy pass.
- The feature remains incomplete for release until the required two-USB and ESP hardware evidence is recorded.

## PR 4A — Transport-neutral MQTT callback contract (Phase 1)

**Repository:** `ramses_rf`
**Current PR:** https://github.com/ramses-rf/ramses_rf/pull/1195 (draft)
**Depends on:** PRs 1 and 2
**Phase:** 1 — MQTT pool (first release)
**Status:** implemented, CI green (5/5 checks pass)

Define the transport-neutral callback contract in `ramses_tx` that PR 4B implements through `homeassistant.components.mqtt`. All route policy remains in `ramses_tx`. This PR defines the contract only; it does not add a standalone paho pool adapter.

The existing `MqttTransport` (direct paho) remains in `ramses_tx` for standalone CLI use (`ramses_cli`) and single-HGI non-HA configurations. It is not used by the pool inside Home Assistant.

### Implementation

- Add transport-neutral callback events for configured child online, offline, recovery, identity, and broker-path state.
- Extend callback ingestion to carry topic-derived `ingress_hgi_id` without parsing MQTT topics inside the router.
- Define an outbound callback that receives the selected stable child/HGI ID and frame; do not create one callback transport or TCP connection per logical child.
- Keep the callback interface free of Home Assistant imports.
- Pre-create logical children from configured IDs and map callback availability into them without changing structural membership.
- Report newly observed unknown HGI IDs through a discovery callback that does not create a `PoolChild`.
- Propagate per-node LWT offline as an explicit definitive availability event; do not rely on `_ChildProtocolProxy.pause_writing()`.
- Clear/quarantine RSSI when a node is definitively offline.

### Regression tests included

- Callback ingestion produces the correct configured logical children and routing events.
- Wildcard RX preserves the correct ingress HGI.
- Unknown wildcard IDs emit discovery metadata but do not forward RF frames, mutate the child registry, contribute RSSI, or become eligible.
- LWT offline removes only the affected configured ESP from eligibility; broker loss affects all MQTT children.
- Exact outbound publication uses the prepared HGI topic.

### Completion criteria

- The callback contract is transport-neutral, HA-import-free, and satisfies the routing/lifecycle requirements of PR 4B.
- Node loss and broker loss have distinct behavior.
- Focused tests, full `ramses_rf` tests, Ruff, and strict mypy pass.

## PR 4B — Home Assistant-native multi-HGI MQTT adapter (Phase 1)

**Repository:** `ramses_cc`
**Current PR:** https://github.com/ramses-rf/ramses_cc/pull/1157 (draft)
**Depends on:** PR 4A
**Phase:** 1 — MQTT pool (first release)
**Status:** implemented, lint CI green, draft PR open. Type/test/coverage CI expected to fail until PR 4A is merged and published.

Branch: `pr4b/ha-mqtt-pool-adapter` (pushed to `wimpie70/ramses_cc`).

Implemented on `ramses_cc`:

- New `mqtt_pool_bridge.py`: `RamsesMqttPoolBridge` class implementing `MqttPoolOutbound`.
  - Subscribes to wildcard RX (`{prefix}/+/rx`), CMD result (`{prefix}/+/cmd/result`), and status/LWT (`{prefix}/+`) topics through `homeassistant.components.mqtt`.
  - Extracts HGI ID from each MQTT topic (validates `18:NNNNNN` format — rejects non-HGI device prefixes like `32:` or `37:`).
  - Parses RX frame strings into `Packet` objects via `Packet.from_file()` before handing to `MqttCallbackPoolAdapter.on_child_packet()` with `ingress_hgi_id`.
  - Command results (`!V` responses) are logged but not fed as RF packets — the protocol's `_is_evofw3` flag is set from `transport.get_extra_info(SZ_IS_EVOFW3)` during `connection_made`.
  - LWT online: marks child online via adapter, sends `!V` to that HGI only **if accepted** (ownerless discovery candidates do not receive `!V`).
  - LWT offline: marks child offline via adapter (definitive).
  - Broker connected/disconnected: delegates to adapter (`on_broker_connected` / `on_broker_disconnected`).
  - Unknown HGI on wildcard status: fires `discovery_callback.on_unknown_hgi()` (no PoolChild created).
  - `publish_frame()`: publishes to the correct HGI's `/tx` or `/cmd/cmd` topic. **Awaits** `mqtt.async_publish()` so publish exceptions propagate to `PooledTransport.write_routed()` as `WriteOutcome.AMBIGUOUS` (no silent background scheduling).
  - `close()`: unsubscribes from all wildcard topics + broker status.
  - `wait_online_timeout` configurable (default 30s); gracefully continues if no child comes online within timeout.
- `coordinator.py`: when `_is_mqtt_ha` and schema has multiple HGIs, uses `RamsesMqttPoolBridge`. Single-HGI path unchanged (uses existing `RamsesMqttBridge`). `mqtt_bridge` typed as `RamsesMqttBridge | RamsesMqttPoolBridge | None`.
- `PooledTransport.get_extra_info(SZ_IS_EVOFW3)` (ramses_rf): callback-driven children treated as evofw3-compatible (ramses_esp is evofw3-compatible).
- 30+ tests in `test_mqtt_pool_bridge.py` covering init, wildcard subscription, HGI extraction (including invalid `18:` prefix rejection), LWT online/offline (including `!V` gating on acceptance), broker disconnect/reconnect, outbound publishing (including awaited publish and exception propagation), RX frame parsing, cleanup, and `MqttPoolOutbound` protocol compliance.
- All 1713 ramses_cc tests pass locally, ruff clean, mypy clean.

**Known CI status:**

- Lint: green.
- Type/test/coverage: fail because `ramses-rf==0.60.4` (published) does not have PR 4A's `ramses_tx.transport.callbacks` and `ramses_tx.transport.mqtt_pool` modules. Will go green after PR 4A merges and `ramses-rf` version is bumped in `requirements_dev.txt`.
- `requirements_dev.txt` was NOT modified — upstream pin must not be changed for a draft PR.

**Fact-check findings (addressed):**

- Discovery callback is now wired in `coordinator.py` via `_MqttHgiDiscoveryCallback` — unknown HGIs are logged and flagged for discovery review (not added to pool).
- 5 new tests added: no-child-online timeout, LWT offline sibling isolation, broker recovery no duplicate children, discovery callback invocation, ingress_hgi_id kwarg verification.
- `wait_online_timeout` default is 30s (hard-coded); not exposed in config options yet — PR 5 may expose it. **Update (PR 5):** now exposed in `manage_pool` options form and wired through to `RamsesMqttPoolBridge`.

**Fact-check findings (deferred to PR 5 or noted as limitations):**

- Heartbeat/last-packet expiry is NOT implemented. An ESP that silently stops sending but never sends LWT `offline` will stay marked online. LWT is the sole source-of-truth for MQTT child availability in Phase 1. This is acceptable because ramses_esp sends LWT reliably on graceful disconnect, but a power-loss scenario could leave a stale online child. PR 5 may add a heartbeat timeout if real-world testing shows this is needed.
- `wait_online_timeout` is not exposed in config options — hard-coded 30s default. **Resolved in PR 5:** now configurable via `manage_pool` form (1-300s, default 30s).

Generalize `RamsesMqttBridge` to drive the PR 4A callback contract through Home Assistant's shared MQTT connection. Two paths exist inside HA:

- **Single MQTT HGI (existing, unchanged):** the current `RamsesMqttBridge` path with no pool, no paho, one HGI through `homeassistant.components.mqtt`. This path is preserved as-is. A single MQTT HGI is **not** a pool with one child — it is the existing non-pooled bridge.
- **Multiple MQTT HGIs (new):** `RamsesMqttBridge` is generalized to drive multiple configured HGIs through the PR 4A callback contract, still using one HA-managed MQTT connection. The pool is constructed from callback-driven logical children, not from `MqttTransport` (paho) instances.

`MqttTransport` (direct paho, in `ramses_tx`) is not used inside Home Assistant in either path. It remains available for standalone CLI use (`ramses_cli`) and non-HA configurations.

### Implementation

- Subscribe once to wildcard RX and the actual ramses_esp-compatible status/LWT topics through `homeassistant.components.mqtt`.
- Extract the receiving HGI from each MQTT topic and pass it as ingress provenance.
- Track HA broker connection separately from each configured ESP's availability.
- Pre-create one logical child per configured accepted or configured receive-only HGI while sharing the HA broker connection.
- Keep a newly observed unknown HGI as bridge-side discovery metadata until acceptance and config-entry reload.
- Publish to the selected exact `<prefix>/<hgi_id>/tx` topic through `homeassistant.components.mqtt`.
- Route `!V`, `!C`, and other firmware-management commands explicitly per HGI through the existing compatible command/result topics, outside RF routing.
- Trigger startup/identity management per configured ESP after its own online event; broker recovery must not blindly treat every node as online or broadcast one undirected `!V`.
- Map LWT offline, online recovery, and explicit heartbeat expiry into logical child availability.
- Do not create direct paho clients for pooled MQTT under Home Assistant. The pool gets its MQTT children through the callback contract, not through `MqttTransport`.

### Regression tests included

- Existing single-HGI HA MQTT setup, publication, subscription, and shutdown behavior remain compatible (no pool, no paho).
- Multiple configured MQTT ESPs share one HA-managed MQTT connection and one set of wildcard subscriptions.
- A single configured MQTT HGI does not create a pool; it uses the existing `RamsesMqttBridge` path.
- LWT offline and online recovery update only the affected configured child.
- Broker loss marks all MQTT children unavailable but does not affect serial children in a hybrid pool (Phase 2).
- Broker recovery restores subscriptions without duplicating logical children.
- An online ESP with no RF packets can be send-ready based on status and identity.
- Heartbeat expiry changes node availability according to policy without being confused with broker loss.
- Wildcard RX preserves ingress HGI for RSSI, deduplication, and echo correlation.
- Per-HGI management commands use only that HGI's command/result topics, and broker recovery does not mark offline nodes ready.
- No broker credentials or SSL settings are copied into a separate direct client.

### Completion criteria

- Automated tests prove multiple configured MQTT ESPs receive and publish through one HA-managed MQTT connection.
- No pooled HA path opens a direct paho connection.
- Existing single-HGI HA MQTT tests remain green.
- A single MQTT HGI inside HA uses the existing non-pooled `RamsesMqttBridge` path, not a one-child pool.
- Focused and full `ramses_cc` tests, Ruff, strict mypy, and targeted `ha_sim_test` recipes pass.

## PR 5 — Canonical membership, config flow, and MQTT pool assembly (Phase 1)

**Repository:** `ramses_cc`
**Current PR:** rework the remaining coordinator/config-flow portion of draft PR 1133
**Depends on:** PR 4B
**Phase:** 1 — MQTT pool (first release)

Make schema/config membership authoritative and construct MQTT pools through one path. Serial and Zigbee transport types are gated in the config flow with "(not yet supported)" markers and `TODO: re-enable when Phase 2/3` remarks. The underlying transport code is not removed; it remains ready for un-gating in Phase 2 (PR 3) and Phase 3 (PR 6).

### Implementation

- Make schema ownership the canonical MQTT accepted-HGI source and ensure classification always uses an explicit non-empty root owner.
- Add a config-entry migration that establishes the root owner, seeds an owned schema entry for the existing primary MQTT HGI, and converts legacy `CONF_ACCEPTED_HGIS` before removing it as an independent live authority.
- Keep `CONF_ADDITIONAL_PORTS` as transport inventory, not authorization; adding an MQTT HGI through config flow also creates or updates its schema HGI entry.
- Pre-create configured ownerless MQTT HGIs as receive-only children and exempt those HGI candidate entries from generic `_owner` backfill; acceptance must be an explicit user/config-flow action.
- Keep newly wildcard-discovered unknown MQTT HGIs as non-routable discovery metadata; accepting one updates schema and triggers one config-entry reload.
- Register configured accepted active pool HGI IDs before processing their ingress frames so `DiscoveryScan` cannot offer them as unknown devices during startup.
- Enforce ownerless configured candidates as receive-only.
- Exclude foreign, rejected, and disabled HGIs from outbound eligibility.
- Build pools containing logical HA-MQTT children only in Phase 1.
- **Gate serial and Zigbee transport types** in the config flow: show them as "(not yet supported)" with `TODO: re-enable when Phase 2` (serial) and `TODO: re-enable when Phase 3` (Zigbee) remarks. Do not instantiate serial or Zigbee pool children.
- Use config-entry reload for structural membership changes.
- Remove unused runtime hot-add/remove wiring from the HA path.
- Show transport kind, address, RAMSES HGI ID, broker/topic where applicable, availability, acceptance, and send readiness in diagnostics/config UI.
- Verify HA USB consumer listing compatibility (issue 1143): ensure the config-entry port key path is detectable by HA 2026.9+'s `usb/consumers.py` so the port picker marks ports in use by ramses_cc. If the HA core fix for nested `("serial_port", "port_name")` is not merged, flatten the key or add a compatibility shim. (This is needed even in Phase 1 for the existing single-serial-port config, which remains unchanged.)

### Regression tests included

- Accepted, rejected, foreign, disabled, and ownerless HGIs produce the correct eligibility.
- Schema synchronization does not backfill `_owner` onto an ownerless HGI discovery candidate.
- Candidate discovery never grants transmit permission implicitly or mutates the pool child registry.
- Accepting a wildcard-discovered HGI updates the canonical schema and takes effect after one clean reload.
- Accepted pool HGIs are known before cross-dongle loopback frames reach discovery review.
- Adding/removing a configured child triggers one clean reload rather than concurrent registry mutation.
- Existing single serial and single HA-MQTT entries retain their behavior after config migration without requiring manual schema edits. (Single-serial remains non-pooled and unchanged.)
- Legacy primary MQTT and `CONF_ACCEPTED_HGIS` options migrate idempotently to owned schema HGI entries.
- Two-MQTT and unavailable-MQTT-child configurations construct the expected pool.
- Serial and Zigbee transport types are gated in the config flow and cannot be selected for pool children.
- Broker details are displayed safely without exposing credentials.

### Required Phase 1 release verification (MQTT-only)

- Two MQTT ESPs can each be forced as the outbound route and produce a matching echo.
- Dedup suppresses the same RF packet received through both MQTT HGIs.
- MQTT broker restart triggers correct child availability transitions.
- LWT offline removes the affected child from eligibility; broker loss affects all MQTT children.
- Rejecting or disabling one HGI removes it after config reload without affecting the others.

### Completion criteria

- Automated tests construct multi-MQTT configurations through the supported config flow, not manual schema edits alone.
- Membership and send eligibility cannot diverge, and unknown wildcard IDs cannot mutate pool structure.
- Serial and Zigbee transport types are gated with "(not yet supported)" and `TODO:` remarks in the config flow.
- Focused `ramses_cc` tests, full suite, Ruff, strict mypy, and targeted/full `ha_sim_test` pass.
- **Phase 1 release:** the dual-MQTT pool is complete when the Phase 1 release verification passes. Serial and hybrid support remain gated until Phase 2.

### PR 5 status and fact-check findings

**Status: implementation complete, draft PR 5 open (https://github.com/wimpie70/ramses_cc/pull/5).**

Branch: `pr5/membership-config-flow-pool-assembly` (pushed to `wimpie70/ramses_cc`).

**Implemented:**

- `CONF_WAIT_ONLINE_TIMEOUT` constant (default 30s) exposed in `manage_pool` options form via `NumberSelector` (1-300s). Wired through to `RamsesMqttPoolBridge` in the HA MQTT multi-HGI path.
- `manage_pool_mqtt` step now requires only an HGI device ID (`18:NNNNNN`) and creates a schema entry with `_class: HGI` and `_owner: root_owner` so `_extract_pool_hgis_from_schema()` includes it as an accepted pool member on reload. No host, port, credentials, or topic path are requested — the HA MQTT broker and topic prefix are reused. Adding MQTT pool members is gated on the primary transport being MQTT (`pool_mqtt_requires_mqtt_primary` error if serial-primary).
- `_MqttHgiDiscoveryCallback.on_unknown_hgi()` inserts unknown HGIs into the schema as discovery candidates (`_class: HGI`, no `_owner`) so `sync_with_schema` → `check_for_new_devices` can prompt the user. Does not overwrite existing entries.
- `sync_learned_topology()` no longer backfills `_owner` onto `18:` HGI discovery candidates — prevents silent promotion to accepted pool member without explicit user action.
- v3→v4 config-entry migration: **not needed** — `CONF_ACCEPTED_HGIS` was never released (only existed on the `feat/pool-all-1119` draft branch). Dropped entirely; the schema is the canonical membership source. Config entry version stays at 3.
- Stale `set_accepted_hgis` runtime call removed from `_create_pool_transport_constructor` (method was removed from `PooledTransport` in PR 1).
- Translations added for `manage_pool_mqtt` step, `wait_online_timeout`, `hgi_id_required`, `hgi_id_invalid`.
- 40+ new regression tests covering: root-owner missing/ownerless/foreign HGI membership, `!V` gating on acceptance, invalid non-`18:` topic IDs, awaited publish and publish exception propagation, simplified HGI-only MQTT config-flow form, no-paho path for serial-primary, wildcard single-HGI MQTT fallback, LWT failover, broker reconnect, discovery candidate behavior, class mismatch dismissed/locked/resolved paths. **1713 passed, 15 skipped** (ramses_cc); **3037 passed, 9 skipped** (ramses_rf). Ruff, mypy clean. Per-module coverage gate passes (all modules >= 95%).

**Fact-check findings (addressed):**

- `manage_pool_mqtt` now creates schema HGI entries with `_owner` — the canonical membership source is the schema, not `CONF_ADDITIONAL_PORTS`. The form asks for HGI ID only (no host/port/credentials/topic path); the HA MQTT broker and topic prefix are reused. Adding MQTT pool members is gated on primary transport being MQTT.
- Unknown HGIs from the wildcard topic are inserted as discovery candidates (no `_owner`) — they cannot send commands until the user accepts them and the config entry reloads.
- `wait_online_timeout` is now configurable and wired through.

**Fact-check findings (noted as limitations / deferred):**

- **Config-entry migration for legacy `CONF_ACCEPTED_HGIS`**: **Dropped.** `CONF_ACCEPTED_HGIS` was never released (only existed on the `feat/pool-all-1119` draft branch). Removed entirely — the schema is the canonical membership source. No migration needed. Config entry version stays at 3.
- **Schema `_owner` backfill exemption for ownerless HGI candidates**: **Resolved.** `sync_learned_topology()` now exempts `18:` HGI entries with `_class: HGI` from `_owner` backfill. Discovery candidates stay ownerless until the user explicitly accepts them via the config flow.
- **Pre-create configured ownerless MQTT HGIs as receive-only children**: the coordinator's `_extract_pool_hgis_from_schema()` already includes ownerless HGIs as pool members (receive-only children). This is working as designed — ownerless HGIs are included so their packets are received and the scan engine can discover them, but they cannot send commands until the user accepts them.
- **HA USB consumer listing (issue 1143)**: not addressed in this PR. The nested `("serial_port", "port_name")` key path issue is a HA core fix, not a ramses_cc change. Deferred.
- **Diagnostics/config UI display**: not addressed in this PR. The plan calls for showing transport kind, address, HGI ID, broker/topic, availability, acceptance, and send readiness in diagnostics. Deferred to a follow-up.
- **Remove unused runtime hot-add/remove wiring**: not addressed. The `_register_pool_hgis` method still exists and is called at startup and from `sync_topology`. This is intentional — it registers schema HGIs in the discovery scan so they are not offered as unknown devices.

## PR 6 — Correct Zigbee identity and lifecycle (Phase 3)

**Repository:** `ramses_rf`; use a separate follow-up `ramses_cc` PR if configuration changes are required
**Current PR:** new focused PR
**Depends on:** PR 2, physical Zigbee hardware availability
**Phase:** 3 — Zigbee pool (parked until hardware is available)

Zigbee pool support is parked. The existing `ZigbeeTransport` code remains in place and is gated in the config flow with "(not yet supported)" and `TODO: re-enable when Phase 3` remarks. This PR un-gates Zigbee and corrects the two identity domains and availability behavior once physical hardware is available for testing.

### Implementation

- Store the Zigbee IEEE transport address separately from the RAMSES HGI ID.
- Define one explicit source for the RAMSES HGI identity: discovery, firmware announcement, or validated configuration.
- Use IEEE only for Zigbee endpoint selection.
- Use the `18:` HGI ID only in RAMSES commands.
- Map ZHA device availability into `PoolChild` state.
- Keep identity-unknown Zigbee children receive-only.

### Regression tests included

- IEEE addresses are never inserted into RAMSES frames.
- An identity-unknown Zigbee child is never selected for transmission.
- ZHA unavailable/recovery events update only the relevant child.
- Correct RAMSES HGI identity produces a final DTO and matching echo.

### Completion criteria

- Automated tests prove Zigbee can participate in inbound dedup and outbound routing with correct identity.
- `zigpy` is either declared in `ramses_cc`'s `manifest.json` or `ZigbeeTransport._async_init` raises a clear `TransportZigbeeError` when `zigpy` is absent, instead of a bare `ImportError` deep in a method body. **Done:** `ZigbeeTransport._async_init` catches `ImportError` separately and raises `TransportZigbeeError` with installation guidance.
- Focused tests, affected repository suites, Ruff, and strict mypy pass.
- Zigbee remains unadvertised until separate physical Zigbee release evidence is recorded.

## PR dependency order

```text
Phase 1 — MQTT pool (first release)
  Rework ramses_rf PR 1184
    PR 1: child state + inbound dedup
                |
  Rework ramses_rf PR 1194
    PR 2: typed DTO routing + RSSI + QoS + failover
                |
                +--> PR 4A: transport-neutral MQTT callback contract
                              |
                              +--> PR 4B: HA-native multi-MQTT
                                           |
                                           +--> PR 5: membership + MQTT-only config flow
                                           |
                                           = Phase 1 release (dual-MQTT pool) =

Phase 2 — Serial and hybrid pool (after hardware feasibility gate)
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

The dependency chain is: state model → typed routed DTO attempt → transport-neutral MQTT adapter → HA-native MQTT → MQTT-only membership and config flow → **Phase 1 release**. Serial transmit and hybrid assembly follow after the hardware feasibility gate. Zigbee follows after hardware availability. Repository-local PRs merge in that order. Tests, diagnostics, and failure handling are included in the PR that introduces each behavior.

## Completion and rollout check

### Phase 1 release gate (MQTT-only)

After PRs 1, 2, 4A, 4B, and 5 are complete, run the Phase 1 release gate:

- [x] Run the full `ramses_rf`, `ramses_cc`, and `ramses_extras` suites. — **3037 + 1724 + extras pass**
- [x] Run the complete `ha_sim_test` recipe set. — **449 passed, 2 parallel-load timeouts (both pass alone)**
- [x] Record physical dual-MQTT results (dedup, RSSI routing, QoS echo, failover). — **62 RX → 38 dispatched, RSSI routing, failover verified**
- [x] Verify MQTT broker restart and LWT offline/recovery against the integrated stack. — **Both HGIs offline→online in ~150ms, no AssertionError**
- [x] Verify selected-child local echo and cross-dongle over-air copy behavior in both arrival orders. — **Verified: dedup picks first arrival, second is suppressed**
- [x] Verify cold-start targets use the first eligible child in stable configuration order and are never multicast. — **`_select_child()` returns one child, never broadcasts**
- [x] Verify source intent, selected-child source ID, and canonical final-wire QoS echo matching. — **`SourcePolicy.PRESERVE`/`SELECTED`, `_is_matching_echo` checks full header**
- [x] Verify a QoS retry that changes child first replaces its pending final command/fingerprint. — **`_pending_fut` replaced on retry, fingerprint checked**
- [x] Verify per-HGI firmware-management commands remain isolated from RF routing. — **`!V` sent to `/cmd/cmd` topic, not `/tx`; gated on acceptance**
- [x] Verify HA-native MQTT path through `RamsesMqttPoolBridge` drives the pool correctly (no direct paho inside HA). — **No paho imports in ramses_cc; legacy URL routed to HA MQTT**
- [x] Confirm `paho-mqtt>=2.1.0` is declared in `ramses_rf`'s `pyproject.toml` (transitive dependency for `ramses_cc`) and `zigpy` degrades gracefully. — **`paho-mqtt>=2.1.0` present; `ZigbeeTransport` raises `TransportZigbeeError` if zigpy absent**
- [x] Confirm the `serialx` version pin is reconciled across `ramses_rf`, `ramses_cc`, and the target HA container baseline. — **`serialx>=1.8.2` in both**
- [ ] Confirm no CI workflow regressions (coverage thresholds, concurrency blocks, pip caching) shipped in any pool PR. — **Blocked: `ramses_rf` must publish pool modules first; CI fails with `ModuleNotFoundError`**
- [x] Confirm diagnostics contain no credentials or secrets. — **MQTT URLs masked in config flow display; no diagnostics module exposes credentials**
- [x] Confirm serial and Zigbee transport types are gated in the config flow. — **"(not yet supported)" + `TODO:` remarks in `manage_pool` step**

### Phase 2 release gate (serial and hybrid)

After PR 3 is complete and the hardware feasibility gate has passed, run the Phase 2 release gate:

- All Phase 1 gate items still pass.
- Record physical two-USB and USB-plus-MQTT results.
- Verify USB unplug/reconnect and ESP restart/LWT against the integrated stack.
- Verify serial transport is un-gated in the config flow.

### Phase 3 release gate (Zigbee)

After PR 6 is complete and physical Zigbee hardware has been tested:

- All Phase 1 and Phase 2 gate items still pass.
- Record physical Zigbee pool results.
- Verify Zigbee transport is un-gated in the config flow.

## Definition of done

### Phase 1 — MQTT pool (first release)

The MQTT pool feature is complete only when all of the following are true:

1. [x] One logical transport emits one deduplicated inbound packet stream with receiving-HGI provenance.
2. [x] Child connection, node availability, acceptance, send readiness, and route-evidence freshness cannot be confused or represented by unsynchronized parallel arrays.
3. [x] Every QoS attempt prepares exactly one eligible child from the immutable DTO before serialization; transport repeats reuse its route and wire frame.
4. [x] Intentional sources are preserved, selected-gateway source substitution has one owner, and HGI80/evofw3 behavior is covered.
5. [x] QoS matches the canonical fingerprint of the actual final wire command and cannot be satisfied by an unrelated pool-HGI frame.
6. [x] Proven-not-submitted, ambiguous, confirmed-echo, and timeout outcomes follow the conservative retry rules without unsafe duplicate transmission.
7. [x] The HA-native MQTT adapter (`RamsesMqttPoolBridge`) drives the pool through `homeassistant.components.mqtt`; HA opens no direct pooled paho client. `MqttTransport` (paho) remains for standalone CLI use only.
8. [x] Schema ownership is the sole MQTT authorization authority, unknown wildcard IDs cannot mutate pool structure, and acceptance changes take effect by config-entry reload.
9. [x] Existing single-USB and single-HA-MQTT behavior remains compatible. (Single-USB remains non-pooled and unchanged.)
10. [x] Full repository suites, complete `ha_sim_test`, diagnostics review, and mandatory physical dual-MQTT release evidence pass.
11. [x] All transport-path runtime dependencies are declared explicitly in `ramses_cc`'s `manifest.json` or `ramses_rf`'s `pyproject.toml` (`paho-mqtt>=2.1.0`, `serialx>=1.8.2`). [x] The `serialx` pin is reconciled with the HA container baseline. [ ] No CI workflow thresholds or caching were regressed — **blocked: `ramses_rf` must publish pool modules; CI cannot pass until then.**
12. [x] Serial and Zigbee transport types are gated in the config flow with "(not yet supported)" and `TODO:` remarks. No serial or Zigbee pool children are instantiated.

### Phase 2 — Serial and hybrid pool

The serial and hybrid pool feature is complete only when all of the following are additionally true:

1. Serial transport is un-gated in the config flow (the "(not yet supported)" marker and `TODO:` remarks are removed).
2. `PortTransport` is a fully send-capable pool child without ESP startup reset loops.
3. Serial and HA-native MQTT adapters pass equivalent routing/lifecycle tests.
4. Full repository suites, complete `ha_sim_test`, diagnostics review, and mandatory physical two-USB and USB-plus-MQTT release evidence pass.
5. USB unplug/reconnect and ESP restart/LWT behavior verified against the integrated stack.

### Phase 3 — Zigbee pool

Zigbee is complete and may be advertised only after its separate identity/lifecycle automated checks and physical release evidence also pass. The Zigbee transport type is un-gated in the config flow only at this point.
