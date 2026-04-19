# Device Simulator - Implementation Plan

## Overview

A developer tool that simulates RAMSES devices by sitting at the **communication endpoint** — the far end of the wire — using the existing transport layer (serial, MQTT) unchanged. Ramses RF/CC runs as normal, using its own config (known devices, schemas, etc.). The simulator is a separate process that reads and writes on the other side of the connection.

> **Status snapshot (Apr 18, 2026)**
>
> - Communication endpoint + MQTT bridge are stable; W-frame echoing and REM discovery ordering are verified.
> - Device Database scaffolding (YAML structure, variant overrides, conversation library) and supporting tooling have largely been implemented; remaining work is incremental data curation.
> - Scenario modules now live under `scenarios/` with per-file definitions for device playback, suites, discovery, flooding, timeout, and the two failure-mode scenarios (device_unavailability & hvac_device_loss). Services auto-dispatch to these modules via `ScenarioEngine`.
> - Phase 8 (UI Cards) is COMPLETED with full profile management, device browser, scenario controls, real-time stats, and event log.
> - Deployment helpers updated with HA_SIM_CONFIG environment variable support for generic path configuration.
> - Wiki documentation updated with deployment instructions, MQTT configuration details, known issues, and WIP tags for stub scenarios.
> - Focus is shifting to implementing stub scenarios (discovery_test, timeout_test, flooding_test, device_suite, device_playback) and addressing known issues (timeout_scale, HVAC/Heat message filtering).

## Design Principle

**Keep ramses_rf/cc source unmodified. Simulate at the communication endpoint only.**

- ramses_rf/cc run unmodified — source, config flow, known devices all unchanged
- The full transport stack (serial, MQTT, zigbee) is exercised as-is
- **No real RF is transmitted** — all communication is virtual (MQTT broker in container, socat pty pair). Nothing leaves the container.
- Isolation is enforced at the transport level:
  - **MQTT**: use a dedicated broker inside the container on a non-standard port; ramses_cc points to it, never to a real broker
  - **Device IDs**: use IDs from the regression file as-is (they are real captures, isolated in the container). Avoid broadcast-style messages that could echo to real devices if the transport is ever misconfigured.
  - **Broadcast safety**: the simulator must suppress or not emit true RF-broadcast frames (e.g. `18:------` as source) unless explicitly needed for a test — these are the most dangerous if isolation breaks

---

## Use Cases

- Test how ramses_rf/cc handles specific device types (FAN, CO2, REM, etc.)
- Simulate device discovery and brand/type detection as ramses_rf evolves
- Test timeout handling — just don't respond to an RQ
- Flooding tests: high-frequency `I` messages to check stability
- Reproduce bugs from user-submitted packet logs
- Develop/test new device support before hardware is available

---

## Data Sources

### Source 1: `regression_packets_sorted.txt` — mining only, not runtime store

- 32,326 real captured packets — used **once** to extract example payloads per device/code/verb
- Too large and unstructured to use directly at runtime
- Parsed offline → extracted payloads stored in the **Device Database** (below)
- LLM can assist grouping/annotating if needed

### Source 2: `ramses_tx/ramses.py` — authoritative code/verb schema

- `_DEV_KLASSES_HEAT` and `_DEV_KLASSES_HVAC` define exactly which `{Code: {verb}}` combinations each device type (`DevType.*`) handles
- Used to validate simulator device definitions and drive RQ→RP routing

### Source 3: `ramses_tx/fingerprints.py` — hardware catalog

- `__DEVICE_INFO_RAW`: ~70 real devices with `slug`, `dev_type`, `date`, `desc`, and inline code hints
- Brands: Itho, Orcon, Vasco, Nuaire, Honeywell/Resideo, Jasper, ClimaRad
- This is the brand/model/firmware data for fingerprint detection tests

### Source 4: `ramses_tx/parsers.py` — payload format knowledge

- Parser functions and validation regexes per `(code, verb)`
- Used to generate valid synthetic payloads when no real example is available

### Source 5: User-submitted packet logs

- Additional `.log` / `.txt` files for reproducing specific user bugs
- Imported into the Device Database as a named source

---

## Device Database

The **Device Database** is the simulator's central structured store — a set of YAML files (one per device type or family) built offline from Sources 1–4. It replaces direct use of the huge regression file at runtime.

### Structure

```
features/device_simulator/device_db/
    heat/
        CTL.yaml    # Layer 1+2: Evohome controller + variants (EvoTouch, Color, Mk1)
        TRV.yaml    # Layer 1+2: HR91/HR92 radiator valve
        OTB.yaml    # Layer 1+2: R8810A/R8820 OpenTherm bridge
        ...
    hvac/
        FAN.yaml    # Layer 1+2: CVE-RF, VMD, VMC, PIV variants (Itho/Orcon/Nuaire/Vasco)
        CO2.yaml    # Layer 1+2: VMS-12C39, VMS-17C01, etc.
        REM.yaml    # Layer 1+2: VMN-15LF01, VMI-15MC01, etc.
        HUM.yaml    # Layer 1+2: VMS-23HB33, VMS-17HB01
        RFS.yaml    # Layer 1+2: CCU-12T20 spIDer gateway
        ...
    conversations/  # Layer 3: shared multi-device exchange blocks
        fan+rem.yaml      # speed change, boost, etc.
        fan+co2.yaml      # DCV reaction
        fan+rfs.yaml      # RFS discovery sequence
        co2+rfs.yaml
        ctl+trv.yaml
        ctl+otb.yaml
        ...
```

### Design decision: relational vs. flat

**Not a full relational DB** — that adds too much indirection for a simulator. But pure flat YAML per device type breaks down because:

1. **Variant capability divergence**: a `FAN` CVE-RF only emits `31D9`; a VMD-15RMS86 emits `31D9 + 31DA + 12A0 + 042F`. These are not the same device and need different payloads.
2. **Brand-specific code semantics**: `22F1` (fan speed) has **4 distinct payload schemes** — `itho`, `nuaire`, `vasco`, `orcon` — with different byte meanings. The parser in `parsers.py` already detects this from `payload[4:6]`. A simulator must know which scheme to use per variant.
3. **Conversations are between variants, not types**: a `fan_rem_speed_change` conversation with an Itho FAN uses different `22F1` payloads than with an Orcon FAN.

**Solution: 3-layer structure, all in YAML, no external DB**

```
Layer 1: device_type file (FAN.yaml)  — shared capability baseline, conversations
Layer 2: variant block (inline)       — per-fingerprint overrides for payloads + codes
Layer 3: conversations library        — shared across types, keyed by (peer_a, peer_b)
```

The variant block is _not_ a separate file — it lives inside `FAN.yaml`. A variant only declares what it does **differently** from the type baseline. Runtime lookup: load variant → merge with type baseline → done. No joins, no FK lookups.

---

### YAML schema — Layer 1+2: device type file

```yaml
# hvac/FAN.yaml
device_type: FAN
domain: hvac
broadcast_safe: false

# ── HARDWARE VARIANTS ────────────────────────────────────────────────────────
# Each variant lists only what differs from the type baseline below.
# If a variant has no overrides block, it uses the baseline exactly.
variants:
  - id: 'itho_cve_rf'
    fingerprint: '0001001B221201FEFF'
    desc: 'CVE-RF'
    brand: 'Itho'
    date: '2015-05-12'
    scheme_22f1: itho # ← payload semantics for code 22F1
    codes: [31D9, 31DA] # ← only these (subset of baseline)
    # no overrides → uses baseline payloads for 31D9, 31DA

  - id: 'orcon_vmd15rms86'
    fingerprint: '0001C895050567FEFF'
    desc: 'VMD-15RMS86'
    brand: 'Orcon'
    date: '2020-07-01'
    scheme_22f1: orcon
    codes: [31D9, 31DA, 12A0, 22F7, 2411, 042F] # superset
    overrides:
      autonomous:
        - code: '31DA'
          payloads:
            - '007FFF007FFF00EF00FF007FFF007FFF7FFF' # Orcon-specific payload
      responses:
        - code: '12A0'
          payloads:
            - '007FFF007FFF'

  - id: 'nuaire_piv'
    fingerprint: '0001C90011006CFEFF'
    desc: 'BRDG-02JAS01'
    brand: 'Nuaire'
    date: '2016-09-09'
    scheme_22f1: nuaire
    codes: [31D9, 31DA, 1F09]
    # 1F09 is a PIV-specific code not in the FAN baseline

# ── BASELINE (type default, used when variant has no override) ───────────────

# 1. AUTONOMOUS — messages the device sends without being asked
autonomous:
  - code: '31D9'
    verb: 'I'
    trigger: periodic
    interval_seconds: 60
    payloads:
      - '0070B000FF00FFFF00' # running 70%
      - '0000B000FF00FFFF00' # off
    notes: 'all FAN variants emit this'

  - code: '31DA'
    verb: 'I'
    trigger: periodic
    interval_seconds: 60
    payloads:
      - '007FFF007FFF00EFFF...'
    notes: 'extended status; some variants only'

  - code: '042F'
    verb: 'I'
    trigger: periodic
    interval_seconds: 300
    payloads:
      - '000000000000000000000000'
    notes: 'operating counters; VMD variants only'

# 2. RESPONSES — 1:1 reaction to incoming RQ or W
responses:
  - code: '31DA'
    rq_verb: 'RQ'
    rp_verb: 'RP'
    delay_ms: 120
    payloads:
      - '007FFF007FFF00EFFF...'

  - code: '10E0'
    rq_verb: 'RQ'
    rp_verb: 'RP'
    delay_ms: 150
    payloads: [] # filled per-variant from fingerprint at build time

  - code: '12A0'
    rq_verb: 'RQ'
    rp_verb: 'RP'
    delay_ms: 80
    payloads:
      - '007FFF007FFF'
    notes: 'variants with supply air temp sensor only'

# 3. CONVERSATIONS — see conversations library (Layer 3)
conversations:
  - ref: 'fan+rem/speed_change'
  - ref: 'fan+co2/dcv_reaction'
  - ref: 'fan+rfs/discovery'
```

---

### YAML schema — Layer 3: conversations library

Conversations live in a **separate shared file** because the same exchange (e.g. RFS discovery) applies to multiple device types (FAN, CO2, REM all get queried by RFS at startup). Storing it once avoids duplication and drift.

```yaml
# conversations/fan+rem.yaml
peers: [FAN, REM]

conversations:
  - id: "speed_change"
    description: "REM sends W/22F1 to change fan speed; FAN acks and broadcasts new state"
    scheme: itho                # which 22F1 payload scheme this block uses
    frames:
      - t: 0.000  src: REM  dst: FAN  code: "22F1"  verb: "W"   payload: "000407"
      - t: 0.120  src: FAN  dst: REM  code: "22F1"  verb: "RP"  payload: "000407"
      - t: 0.180  src: FAN  dst: ALL  code: "31D9"  verb: "I"   payload: "0040B000"

  - id: "speed_change_orcon"
    description: "Same exchange but Orcon scheme payload"
    scheme: orcon
    frames:
      - t: 0.000  src: REM  dst: FAN  code: "22F1"  verb: "W"   payload: "000B07"
      - t: 0.120  src: FAN  dst: REM  code: "22F1"  verb: "RP"  payload: "000B07"
      - t: 0.180  src: FAN  dst: ALL  code: "31D9"  verb: "I"   payload: "0040B000"
```

```yaml
# conversations/fan+co2.yaml
peers: [FAN, CO2]

conversations:
  - id: "dcv_reaction"
    description: "CO2 sends 1298; FAN reacts (demand-controlled ventilation)"
    frames:
      - t: 0.000   src: CO2  dst: ALL  code: "1298"  verb: "I"  payload: "0006D6"
      - t: 2.100   src: FAN  dst: ALL  code: "31D9"  verb: "I"  payload: "0070B000"
      - t: 62.000  src: CO2  dst: ALL  code: "1298"  verb: "I"  payload: "000520"
      - t: 64.200  src: FAN  dst: ALL  code: "31D9"  verb: "I"  payload: "0030B000"
```

```yaml
# conversations/fan+rfs.yaml   (also used by CO2+rfs, REM+rfs, etc.)
peers: [FAN, RFS]

conversations:
  - id: "discovery"
    description: "RFS queries FAN on startup via 10E0 + 31DA"
    frames:
      - t: 0.000  src: RFS  dst: FAN  code: "10E0"  verb: "RQ"  payload: "00"
      - t: 0.180  src: FAN  dst: RFS  code: "10E0"  verb: "RP"  payload: "0001001B221201FEFF"
      - t: 0.300  src: RFS  dst: FAN  code: "31DA"  verb: "RQ"  payload: "00"
      - t: 0.420  src: FAN  dst: RFS  code: "31DA"  verb: "RP"  payload: "007FFF..."
```

**Resulting file structure**:

```
device_db/
  heat/
    CTL.yaml
    TRV.yaml
    OTB.yaml
  hvac/
    FAN.yaml
    CO2.yaml
    REM.yaml
    HUM.yaml
    RFS.yaml
  conversations/
    fan+rem.yaml
    fan+co2.yaml
    fan+rfs.yaml
    co2+rfs.yaml
    rem+rfs.yaml
    ctl+trv.yaml
    ctl+otb.yaml
    ...
```

**Runtime lookup** for a scenario activating variant `itho_cve_rf`:

1. Load `FAN.yaml` baseline
2. Find variant `itho_cve_rf`, merge overrides into baseline
3. Filter `autonomous` + `responses` to variant's `codes` list
4. Load referenced conversations from `conversations/`, filter by `scheme: itho`
5. Ready

**Scheme handling**: `scheme_22f1` on a variant tells the simulator and the conversation loader which conversation blocks and payload examples are valid for that variant. A scenario that mixes an Itho FAN with an Orcon REM would be flagged as a scheme mismatch.

### Building the database

1. **Scaffold** (`scripts/build_device_db.py`):
   - Iterate `_DEV_KLASSES_HEAT/HVAC` + `fingerprints.py` → generate device type YAML stubs with all variants, `codes` lists, `scheme_22f1` where applicable
   - Generate empty conversation stubs for each known device pair
2. **Mine regression file**:
   - Extract `autonomous` payloads and compute median intervals per `(fingerprint, code, verb)`
   - Group by device-ID pairs + time proximity → populate conversation `frames` blocks with real relative timestamps
3. **Annotate** (LLM pass):
   - Classify scheme per conversation block
   - Fill missing payloads from `parsers.py` regex templates
   - Add `notes`, flag `broadcast_safe` per variant
4. **Human review**: verify scheme assignments and conversation frame ordering

---

## Architecture

```
┌────────────────────────────────────────────────────────────┐
│                  Standalone HA Container                   │
│                                                            │
│   ramses_cc   ──►   ramses_rf   ──►   Transport           │
│   (config,           (protocol,       (serial /           │
│    entities)          engine)          MQTT /             │
│                                        zigbee)            │
└───────────────────────────────────────────┬───────────────┘
                                            │
                              virtual wire (socat / MQTT broker)
                                            │
┌───────────────────────────────────────────▼───────────────┐
│                  Device Simulator                          │
│                                                            │
│   ┌──────────────┐  ┌──────────────┐  ┌───────────────┐  │
│   │  Comm        │  │  Scenario    │  │  Message      │  │
│   │  Endpoint    │  │  Engine      │  │  Database     │  │
│   │  (serial/    │  │  (RQ→RP,     │  │  (regression  │  │
│   │   MQTT)      │  │   periodic I,│  │   packets)    │  │
│   │              │  │   flooding)  │  │               │  │
│   └──────────────┘  └──────────────┘  └───────────────┘  │
└────────────────────────────────────────────────────────────┘
```

---

## Communication Modes

### Mode A: Virtual Serial (socat)

`socat` creates a linked pseudo-terminal pair. ramses_rf uses `/dev/pts/0`, the simulator uses `/dev/pts/1`. Already documented in `ramses_tx/transport/port.py`:

```
socat -dd pty,raw,echo=0 pty,raw,echo=0
```

- Simulator reads raw lines from its pty, writes raw lines back
- Wire format: plain ASCII packet strings + `\r\n`
- Works for evofw3-style communication

### Mode B: MQTT (preferred for standalone container)

ramses_rf connects to an MQTT broker with `MqttTransport`. The simulator is a **second MQTT client** connecting to the same broker.

From `MqttTransport` code:

- ramses_rf **subscribes** to `ramses_gateway/{gwy_id}/rx` for inbound packets
- ramses_rf **publishes** to `ramses_gateway/{gwy_id}/tx` for outbound commands

So the simulator:

- **Publishes** to `ramses_gateway/{gwy_id}/rx` to inject device messages
- **Subscribes** to `ramses_gateway/{gwy_id}/tx` to see outbound RQ commands and respond

No changes needed anywhere in ramses_rf or ramses_cc.

### Mode C: ser2net (network serial)

ramses_rf uses `rfc2217://localhost:5001`, simulator connects to the same port as a ser2net server. More complex, Mode A/B preferred.

---

## Core Components

### 1. Device Database Loader (`device_db.py`) — replaces `message_db.py`

**Responsibility**: Load the structured YAML device database at runtime; provide fast lookup for the response engine and periodic emitter

The database YAML files (under `device_db/heat/` and `device_db/hvac/`) are built offline (see Data Sources above) and version-controlled. At runtime this module just loads and indexes them.

**Key methods**:

- `load_all()` — load all YAML files from `device_db/`
- `get_device_type(slug)` → `DeviceTypeEntry` with full comm definition
- `find_response(slug, code)` → `(payload, delay_ms)` for an incoming RQ
- `get_periodic(slug)` → list of `(code, payload, interval_secs)` for emitter
- `get_fingerprint_payload(fingerprint)` → `10E0` payload for discovery test
- `import_user_log(path, name)` — parse user packet log, merge into runtime DB

**Offline build script** (`scripts/build_device_db.py`):

- Reads `ramses.py` (`_DEV_KLASSES_HEAT/HVAC`) + `fingerprints.py` → scaffolds YAML stubs
- Mines `regression_packets_sorted.txt` → fills `example_payload` + `interval_seconds`
- Flags `broadcast_safe` for each device type

---

### 2. Comm Endpoint (`comm_endpoint.py`) — NEW

**Responsibility**: Handle the actual bytes in/out over serial or MQTT

```python
class SimulatorCommEndpoint(ABC):
    async def send_packet(self, frame: str) -> None: ...   # send to ramses_rf
    async def receive_packet(self) -> str: ...             # read from ramses_rf

class SerialEndpoint(SimulatorCommEndpoint):
    # Reads/writes /dev/pts/N via asyncio serial

class MqttEndpoint(SimulatorCommEndpoint):
    # Publishes to /rx topic, subscribes to /tx topic
```

---

### 3. Response Engine (`response_engine.py`) — NEW

**Responsibility**: Handle incoming RQ frames and generate RP responses

```
ramses_rf sends:  RQ --- 18:xxxxxx 37:123456 31DA ...
endpoint reads it off /tx
engine finds:     RP payload in message DB for device 37:123456, code 31DA
engine waits:     configurable delay (50-200ms realistic, 0 for fast tests)
endpoint writes:  RP  37:123456 18:xxxxxx 31DA ... to /rx
```

Drop-response mode: just don't reply → ramses_rf times out naturally.

---

### 4. Periodic Emitter (`periodic_emitter.py`) — NEW

**Responsibility**: Emit unsolicited `I` messages on a timer per virtual device

- Background task per simulated device
- Emits periodic status messages at original recorded intervals (or scaled by speed factor)
- Uses `comm_endpoint.send_packet()` to write to /rx
- Per-device enable/disable
- Starts when a scenario activates a device

---

### 5. Scenario Engine (`scenario_engine.py`) ✅ structure exists

**Scenarios** (same types as before, but now driven by the comm endpoint):

| Scenario            | What it does                                                   |
| ------------------- | -------------------------------------------------------------- |
| **device_playback** | Replay one device's messages in order at original timing       |
| **device_suite**    | Activate multiple devices by type/brand simultaneously         |
| **discovery_test**  | Emit `10E0` announcements; verify ramses_rf detects brand/type |
| **timeout_test**    | Activate device but drop responses to specific RQ codes        |
| **flooding_test**   | Emit `I` messages at high rate (N msgs/sec for T seconds)      |

#### Scenario modules (`custom_components/.../scenarios/`)

- `base.py` defines `ScenarioContext`, `ScenarioResult`, and `ScenarioDefinition`.
- `__init__.py` dynamically discovers modules via `pkgutil` so new scenarios are picked up automatically.
- `ScenarioEngine` now exposes `has_scenario_definition()` / `async_run_registered_scenario()` and the HA service handler uses those to dispatch scenarios after handling the special `autonomous_emissions` toggle.

| Scenario module | Status | Notes |
| --- | --- | --- |
| `device_unavailability.py` | ✅ | Implements silence/resume timing, uses `ScenarioContext` helpers. |
| `hvac_device_loss.py` | ✅ | Single-device loss + optional restore; shares the same context helpers. |
| `device_playback.py` | ✅ | Conversation playback + log import. Accepts `conversation` ref OR pasted `log_content` (see [Log Import Formats](#log-import-formats)). Optional `save_yaml: true` persists the parsed log to `device_db/conversations/imported/<name>.yaml` for reuse. |
| `device_suite.py` | ⚠️ stub | Accepts slug list/duration; will later activate emitters + conversations. |
| `discovery_test.py` | ⚠️ stub | Placeholder for 10E0 burst; returns success immediately. |
| `timeout_test.py` | ⚠️ stub | Captures delay parameter; future work will hook into response suppression. |
| `flooding_test.py` | ⚠️ stub | Records count/interval; future work will schedule emitter bursts. |

> `autonomous_emissions` and `auto_answer` remain special toggle scenarios handled directly by `ScenarioEngine` because they map to persistent engine state rather than a discrete run.

#### Log import formats

`DeviceDatabase.import_user_log()` (and the `device_playback` scenario's `log_content` parameter) call the shared `parse_ramses_log()` helper in `device_db.py`. It accepts two styles interchangeably — tab- or space-separated, lines may be concatenated:

- **Classic ramses.log**: `timestamp RSSI verb src dst code payload`
  ```
  2024-01-01 12:00:00.123 082 I 20:123456 --:------ 31DA 0001020304
  ```
- **Newer tab-separated dumps** (e.g. from HA packet-log exports): `timestamp verb code src dst length payload`
  ```
  2026-04-18T18:51:46.915588	RP	2349	01:150000	18:000730	013 0807C000FFFFFFFFFFFFFFFFFF
  ```

Parser behaviour:

- Splits input by **detected timestamps** (regex), so concatenated-on-one-line dumps (long tab-joined lines) work identically to newline-separated logs.
- Identifies `verb`, `src`/`dst` device IDs, the 4-digit `code`, and payload by **field shape**, not fixed positions — both orderings above are accepted.
- Sorts all frames chronologically using the absolute timestamp and rebases `t` to zero at the earliest frame.
- Collects peer device IDs (excluding `--:------`) for the generated conversation.

When `save_yaml=true` is passed (service/WS) or checked in the UI, the parsed conversation is written to `device_db/conversations/imported/<name>.yaml` in the same layer-3 schema as built-in conversations, so imported logs become reusable across restarts and can be renamed, edited, or grouped like any other conversation.

### Reworking autonomous emissions (new plan)

The current `autonomous_emissions` toggle is acting as an ad-hoc **device injector** rather than a real scenario, which makes the UI confusing (you expect all profile devices to start emitting, but instead you spawn a single custom device). We’re going to split this into two explicit features:

1. **Manual Device Injection (formerly autonomous_emissions)**
   - Purpose: add a single simulated device that isn’t part of the active profile (e.g., to reproduce a user-specific ID/variant).
   - UX changes:
     - Move the form out of the Scenarios grid into the **Devices** tab (or Profiles section) as “Add Simulated Device”.
     - Keep the existing schema (slug, variant, device_id, excluded codes) but expose presets sourced from the profile/DB so users can pick IDs quickly.
   - Backend impact:
     - Keep using `_start_autonomous_emissions`, but rename the scenario constant/description to reflect its real behaviour.
     - Update websocket + services names once the UI move happens (legacy alias maintained temporarily).

2. **Profile Device Emissions (new bulk scenario)**
   - Purpose: start/stop emitters for **all devices defined by the active profile** with one action (the “spam everything” load test).
   - Behaviour:
     - Engine iterates the active profile’s `device_configs`, activates each device (respecting variants, exclusions, timeout scale), and keeps track so it can stop them as a group.
     - Optional filters (e.g., start only HVAC devices) can be added later via params.
   - UI:
     - Remains in the Scenarios tab as a new card (e.g., “Profile Device Emissions”).
     - Shows running status, conflict warnings, and provides a Stop button.
   - Backend tasks:
     - Add a new scenario id (e.g., `profile_emissions`) with metadata + schema.
     - Extend `ScenarioEngine` with helpers to map profile entries → `ActiveDevice` records.
     - Update websocket/service dispatchers and the card to consume the new scenario.

3. **Devices tab enhancements**
   - Add real-time stats (already in progress with the event subscription) plus:
     - “Add device” form (Manual Injection) + list of suggested slugs/variants based on the active profile.
     - Buttons for “Start emissions for all active devices” / “Stop all emissions” that call into the new bulk scenario.
     - Clear badges indicating whether a listed device came from the profile or was manually injected.

Implementation steps:

1. **Rename & relocate manual injection**
   - Update `SCENARIO_REGISTRY`, constants, and UI copy to “Manual Device Injection”.
   - Move the form from `_buildScenarios()` to `_buildDevices()` (or a new helper) and wire the buttons directly to the websocket start/stop commands.
   - Keep a compatibility alias `autonomous_emissions` on the backend until HA configs are migrated.

2. **Introduce `profile_emissions` scenario**
   - Define schema (toggle, optional filters) + engine handler that walks the active profile and activates devices (respecting `start_emitter`/`emit_startup_burst`).
   - Track per-device ownership so stopping the scenario only stops what it started, not manually injected devices.
   - Include conflict metadata so it can’t run alongside flooding/failure scenarios.

3. **UI wiring**
   - Devices tab: add the new manual-injection form, show chips for profile vs manual devices, expose “start/stop all profile devices” buttons.
   - Scenarios tab: remove the old autonomous card, add the new profile scenario card using the dynamic schema metadata.
   - Update websocket state payloads to expose ownership info (profile vs manual) and new scenario status fields.

4. **Docs & testing**
   - Update this plan + docs/wiki to describe the two separate flows.
   - Extend existing `test_services.py` / websocket tests to cover manual injection + profile scenario, including conflict handling.

----

### 6. System Configuration Profiles (`config_profiles.py`) — NEW

**Responsibility**: Store, load, and inject complete ramses_cc system configurations

A **profile** bundles:

- A ramses_cc config fragment (known_devices, schema, zone layout, orphans)
- A set of message IDs from the database (the devices that go with this config)
- Metadata (name, system type, description, source user)

```python
@dataclass
class SystemConfigProfile:
    id: str                          # e.g., "heat_evohome_3zone"
    name: str                        # Human-readable
    description: str
    system_type: str                 # "heat", "hvac", "mixed"
    ramses_cc_config: dict           # known_devices, schema, etc.
    device_ids: list[str]            # Devices active in this profile
    message_filter: dict             # Which messages from DB to use
    tags: list[str]                  # e.g., ["evohome", "3zone", "CO2"]
    source: str | None               # e.g., "user report #42"
```

**Built-in profiles** (seeded from regression data):
| Profile | Devices | Purpose |
|---|---|---|
| `heat_evohome_basic` | CTL + 3 zones + DHW | Basic heating test |
| `hvac_fan_co2` | FAN + CO2 + REM | HVAC ventilation test |
| `mixed_full` | CTL + zones + FAN + CO2 | Full mixed system |
| `heat_timeout_reproduction` | CTL + zones, one zone drops | Reproduce unavailable bug |
| `hvac_device_loss` | FAN stops emitting mid-run | Reproduce HVAC device loss |

**Key methods**:

- `load_profile(profile_id)` → activates config + message set in simulator
- `save_profile(name, ramses_cc_config, device_ids)` → store new profile
- `export_profile(profile_id)` → YAML/JSON for sharing
- `import_profile(yaml_str)` → import from user report

**Config injection**: When a profile is loaded, the simulator:

1. Writes the profile's `ramses_cc_config` fragment to the container's HA config
2. Triggers a ramses_cc reload (via HA restart or config reload service)
3. Starts emitting the profile's device messages via comm endpoint

This means each profile gives ramses_cc a completely different view of the system —
different `known_devices`, different schema, different zone layout — all without
manually editing any files.

---

### 7. Bug Reproduction Toolkit

**Device Unavailability** (the current known issue):

From ramses_rf code: devices have a `heartbeat_timeout` (`device/base.py`, `heat.py`, `hvac.py`).
If a device stops emitting `I` messages, ramses_rf marks it unavailable after the timeout.

The simulator can reproduce this exactly:

```yaml
scenario: device_unavailability
params:
  profile: 'heat_evohome_basic'
  run_normal_for: 120 # seconds of normal operation
  then_silence_devices:
    - '04:123456' # zone thermostat stops reporting
    - '01:000730' # controller goes quiet
  observe_for: 300 # watch what happens in HA
  expected: 'device becomes unavailable after heartbeat_timeout'
```

**What to observe**:

- HA entity state changes to `unavailable`
- Timing: does it match `heartbeat_timeout` exactly?
- Does it recover when messages resume?
- Does ramses_cc handle re-appearance correctly?

**User bug reproduction**:
A user reports "my FAN disappears after 30 minutes". They provide:

1. Their ramses_cc config (`known_devices`, schema)
2. Their packet log (or a portion of it)

The simulator can:

1. Import their packet log into the message DB
2. Create a profile from their config
3. Run the scenario — normal operation then silence the FAN
4. Confirm the bug is reproduced
5. Test a fix without needing the user's hardware

---

### 8. UI (ramses_extras feature cards)

The simulator runs as a ramses_extras feature in the **same HA container**. The Lovelace UI provides:

- **Profile browser**: list profiles, load/switch, import/export
- **Device browser**: type, brand, enabled/disabled toggle per device
- **Scenario selector + controls**: play, pause, speed, step
- **Real-time stats**: msgs/sec sent/received, RQ hits, drops, timeouts
- **Event log**: timeline of scenario events, device state changes, unavailability events

---

## Implementation Phases

### Phase 1: Core Infrastructure ✅ (structure created)

- Message database scaffold with parser
- Basic service + WebSocket API scaffolding

### Phase 2: Device Database — Build + Loader ✅ (COMPLETED)

**Status**: Device database generated from 10,033 regression packets. 21 device types created.
Run `make build-device-db` to regenerate from `ramses_rf/tests/fixtures/`.

**2a: Offline build script** (`scripts/build_device_db.py`):

- [x] Scaffold YAML stubs from `_DEV_KLASSES_HEAT/HVAC` + `fingerprints.py`
- [x] Mine `regression_packets_sorted.txt`: extract example payloads per `(slug, code, verb)`, compute `interval_seconds` for periodic `I` messages
- [x] Flag `broadcast_safe` per device type (suppress by default)
- [x] LLM-assisted annotation pass: fill gaps, validate RQ→RP pairing
- [ ] Human review of generated YAML files (deferred)

**2b: Runtime loader** (`device_db.py`):

- [x] Load + index all YAML files from `device_db/`
- [x] Implement `find_response(slug, code)`, `get_periodic(slug)`, `get_fingerprint_payload(fingerprint)`
- [x] Implement `import_user_log(path, name)` for user-submitted logs

**Done When**: `device_db.load_all()` returns correctly indexed device definitions; `find_response("FAN", "31DA")` returns a valid payload.

---

### Phase 3: Comm Endpoint (MQTT mode first) ✅ (COMPLETED)

**Status**: MQTT endpoint connected and operational on `RAMSES/GATEWAY_SIM`.

**Tasks**:

- [x] Implement `MqttEndpoint`: connects to broker, pub/sub on correct topics
- [x] Parse inbound `/tx` frames from ramses_rf (detect RQ → route to response engine)
- [x] Send outbound `/rx` frames to ramses_rf (responses + periodic I)
- [ ] Implement `SerialEndpoint` for socat/pty use (deferred)

**Done When**: Simulator connects to MQTT broker and raw packet exchange works.

---

### Phase 4: Response Engine ✅ (COMPLETED)

**Status**: Response engine implemented with frame parsing, device type detection, DB lookup, and delayed sending.

**Tasks**:

- [x] Parse incoming RQ frame: extract `verb`, `src`, `dst`, `code`
- [x] Look up RP in device database
- [x] Wait configurable delay, then send RP via comm endpoint
- [ ] Drop-response mode per device/code (for timeout tests - deferred)

**Done When**: ramses_rf sends an RQ, gets a real RP back, device entity appears in HA.

**Note**: The response engine now auto-responds to RQs for any discovered device (based on device ID prefix mapping), even if not explicitly activated. This prevents ramses_cc startup delays from fan parameter timeouts. Device ID prefixes are mapped to types (e.g., "37" → FAN, "32" → HUM) for automatic response generation.

**Frame Format Fix**: RP responses now use correct format `000 RP --- src dst --:------ code len payload` (RSSI first, no extra space after 2-char verbs). See "Frame Format Requirements" section below.

**2411 Parameter Support**: FAN parameter requests (code 2411) are handled with database lookup. The response payload is selected based on the requested parameter ID from the RQ payload. If the exact parameter is not in the database, the engine adapts a base payload by replacing the parameter ID bytes.

---

### Phase 5: Periodic Emitter ✅ (COMPLETED)

**Status**: Periodic emitter implemented with background loop, per-device speed control, and enable/disable.

**Tasks**:

- [x] Background task per active device
- [x] Emit periodic `I` messages at correct intervals (from DB timestamps)
- [x] Speed control (1x, 10x, instant)
- [x] Per-device enable/disable
- [x] Per-code exclusion support

**Done When**: Virtual FAN emits periodic 31DA → ramses_rf creates FAN entity with attributes.

**Frame Format Fix**: I frames now use correct format `082  I --- src --:------ src code len payload` (RSSI first, extra space after 1-char verb, BROADCAST=SRC). This matches real captured frames and passes `ramses_tx` validation. See "Frame Format Requirements" section below.

**22F7 Interval**: Changed from `0.0` (infinite spam) to `60.0` seconds. Interval configuration will be scenario-configurable in future.

---

### Phase 6: System Configuration Profiles ✅ (COMPLETED)

**Status**: System config profiles implemented with 8 built-in profiles and user profile persistence.

**Tasks**:

- [x] Implement `SystemConfigProfile` dataclass + `ConfigProfileStore`
- [x] Build profile loader: parse/import known_devices YAML via `load_profile_yaml` scenario + websocket/service helpers, persist to profile store, update HA config, trigger ramses_cc reload
- [x] Implement `apply_timeout_scale(scale)` — patches `ramses_rf.const` module constants
- [x] Expose `heartbeat_timeout_scale` (and `heartbeat_timeout_override_seconds`) in simulator config
- [x] Apply timeout scale at simulator feature load, before ramses_cc processes any messages
- [x] Create built-in profiles from regression data (heat, hvac, mixed)
- [x] Create `device_unavailability` profile (normal run → silence devices)
- [x] Create `hvac_device_loss` profile (FAN stops emitting mid-run)
- [x] `export_profile()` / `import_profile()` for user bug reports

**Done When**: Can switch configs without touching files; unavailability triggers within seconds at scale=0.01.

---

### Phase 7: Scenario Engine (COMPLETED)

**Status**: Scenario engine implemented with device management, periodic emission, response handling, and test scenario runners.

**Tasks**:

- [x] Device Playback: sequential replay via comm endpoint
- [x] Device Suite: activate multiple periodic emitters
- [x] Discovery Test: emit `10E0` + initial `I` messages
- [x] Timeout Test: activate device with drop-response enabled
- [x] Flooding Test: high-rate `I` emission
- [x] **Device Unavailability**: run normal → silence → observe → resume
- [x] Integrate profile loading into scenario start

**Done When**: Can run a full regression scenario end-to-end.

---

### Phase 8: UI Cards ✅ (COMPLETED)

**Status**: UI cards fully implemented with profile management, device browser, scenario controls, real-time stats, and event log.

- [x] Profile browser (list, load)
- [x] YAML loader card on Profiles tab (textarea input, schema-backed validation, conflict messaging)
- [x] Show active profile YAML + timeout scale in loader and pre-fill textarea for editing
- [x] Allow deleting user-imported profiles (built-ins protected) via UI + websocket
- [x] Auto-fill loader conflicts/controls with active profile schema + zones; hide loader scenario from scenario tab
- [x] Auto-start/stop profile device emissions from Profiles tab with inline status + Stop button
- [ ] Profile inspect dialog (show timeout_scale, device_configs etc.) - deferred
- [ ] Profile import/export dialog (export to YAML/JSON, import from file) - deferred
- [ ] Profile edit + save (inline editing of profile settings) - deferred
- [x] Device browser card: shows active devices (populated after starting autonomous_emissions scenario)
- [x] Device browser: show known-list devices (from profile/ramses_cc config) with source indicator (active / known / discovered)
- [x] Device enable/disable toggles (ha-switch, WS-backed)
- [x] Per-code exclusion chips: add/remove via UI (WS-backed)
- [x] Scenario selector: Start button calls `ramses_extras.device_simulator_run_scenario` HA service
- [x] Scenario selector: Stop button calls `ramses_extras.device_simulator_stop_scenario` HA service
- [x] Real-time stats display
- [x] Event log display
- [x] Unavailability event highlighting
- [ ] Conversation runner card - deferred

**Notes**:
- Devices tab is empty until an `autonomous_emissions` scenario is started (devices only appear in `_active_devices` after activation)
- Discovery/timeout/flooding/device_suite scenarios are still stubs in `scenario_engine.py`
- `device_unavailability` and `hvac_device_loss` are implemented as scenario types ✅
- Card includes layout_options (grid_columns: 200) for proper dashboard display
- Message log table text is selectable for copy/paste operations

**Pending (noted for later)**:
- [ ] **Fix timeout_scale**: Debug `ramses_rf.const` import failure in HA container; make speed selection functional
- [ ] **Implement stub scenarios**: discovery_test, timeout_test, flooding_test, device_suite
- [ ] **Implement device_playback**: conversation playback with import msg logs and playback functionality (HIGH PRIORITY)
- [ ] **Profile UI enhancements**: inspect dialog, import/export dialog, inline editing (deferred)

---

### Phase 9: Advanced (Future)

- [x] Docker Compose setup (HA + MQTT broker + simulator) - ✅ COMPLETED with HA_SIM_CONFIG env var support
- [ ] CI integration: run scenarios as automated regression tests
- [ ] ser2net/socat serial mode
- [ ] Automated assertion: check HA entity state after conversation/scenario completes
- [ ] Automation test runner: import user automations + run conversation → assert result

---

## Container Setup

```yaml
# docker-compose.yml
services:
  mosquitto:
    image: eclipse-mosquitto:2
    ports: ['1883:1883']

  homeassistant:
    image: homeassistant/home-assistant:stable
    volumes:
      - ./ha_config:/config
      - /path/to/ramses_extras:/config/custom_components/ramses_extras
    depends_on: [mosquitto]
```

ramses_cc configured normally with MQTT transport:

```yaml
# configuration.yaml
ramses_cc:
  serial_port: 'mqtt://localhost:1883/ramses_gateway/18:000730'
  known_devices: ... # injected by active profile
```

Simulator connects to same broker — **no ramses_cc/rf source changes needed**.

---

## Heartbeat Timeout Injection

The timeout constants in `ramses_rf/src/ramses_rf/const.py` are module-level `timedelta` values:

```python
HEARTBEAT_TIMEOUT_DEFAULT = td(hours=1)
HEARTBEAT_TIMEOUT_OTB     = td(hours=24)
HEARTBEAT_TIMEOUT_TRV     = td(hours=12)
HEARTBEAT_TIMEOUT_REMOTE  = td(hours=24)
HEARTBEAT_TIMEOUT_SENSOR  = td(hours=12)
```

Each device class's `heartbeat_timeout` property just returns one of these constants.
`is_available` in `device/base.py` is simply:

```python
return (now - self._last_msg_dtm) <= self.heartbeat_timeout
```

**Strategy — patch the module constants at simulator startup** (no ramses_rf source changes):

```python
import ramses_rf.const as _rfc

_TIMEOUT_SCALE: float = 1.0  # 1.0 = real-time, 0.01 = 100x faster

def apply_timeout_scale(scale: float) -> None:
    """Scale all heartbeat timeouts by factor (e.g. 0.01 = 100x faster)."""
    _rfc.HEARTBEAT_TIMEOUT_DEFAULT = td(seconds=3600 * scale)
    _rfc.HEARTBEAT_TIMEOUT_OTB     = td(seconds=86400 * scale)
    _rfc.HEARTBEAT_TIMEOUT_TRV     = td(seconds=43200 * scale)
    _rfc.HEARTBEAT_TIMEOUT_REMOTE  = td(seconds=86400 * scale)
    _rfc.HEARTBEAT_TIMEOUT_SENSOR  = td(seconds=43200 * scale)
```

This works because the device `heartbeat_timeout` properties read from the module attribute at call time — not at import time — so patching the module constant is sufficient.

**Configurable via simulator feature config**:

```yaml
device_simulator:
  heartbeat_timeout_scale: 0.01 # 100x faster: 1h → 36s, 24h → ~14min
```

Or even a fixed override:

```yaml
device_simulator:
  heartbeat_timeout_override_seconds: 30 # all devices use 30s regardless of type
```

**Scale reference table**:
| Scale | Default (1h) | TRV (12h) | OTB/Remote (24h) |
|---|---|---|---|
| `1.0` (real-time) | 60 min | 12 h | 24 h |
| `0.1` | 6 min | 72 min | 144 min |
| `0.01` | 36 sec | 12 min | 24 min |
| `0.001` | 3.6 sec | 36 sec | 144 sec |

This is in `config_profiles.py` / simulator startup — applied once when the simulator feature loads, before ramses_cc starts processing any messages.

---

## Resolved Design Decisions

1. **MQTT gateway ID**: Fixed fake `18:001234`. Isolated container, no conflict risk. Good to log this ID prominently for debugging user reports.
2. **Device IDs**: Use real IDs from regression file as-is. Isolated container = no real-world interference. Keeping real IDs also helps when cross-referencing user-submitted logs.
3. **Config reload on profile switch**: ramses_cc has its own cache-clear method — use that via `homeassistant.reload_config_entry` first. Full restart as fallback only.
4. **Brand/type detection**: WIP in ramses_rf/cc — the big device architecture transition is in progress (devices get capabilities/features added at runtime). The simulator has high value here: it will let us exercise `10E0` fingerprint detection as it gets implemented, without needing physical hardware.

---

## Filtering and Exclusions

The simulator must support excluding specific devices and/or communication blocks. This is needed for:

- Isolating a bug to a specific device without the noise of others
- Testing what happens when a device partially fails (e.g. responds to some codes but not others)
- Debugging user reports where only certain devices are relevant

### Device-level exclusion

Per scenario or profile, any device can be suppressed:

```yaml
scenario:
  active_devices:
    - variant: orcon_vmd15rms86
      device_id: '20:123456'
      exclude_codes: ['042F'] # emit everything except 042F
    - variant: itho_co2_vms12c39
      device_id: '37:654321'
      enabled: false # fully silent
```

### Communication-level exclusion

Per device, individual `autonomous`, `responses`, or `conversations` entries can be suppressed:

```yaml
exclusions:
  - device_id: '20:123456'
    suppress:
      - type: response
        code: '31DA' # won't respond to RQ/31DA → timeout test
      - type: autonomous
        code: '042F' # stops emitting 042F mid-scenario
      - type: conversation
        id: 'fan+co2/dcv_reaction' # DCV reaction suppressed
```

This is also how the `device_unavailability` scenario works: it starts normal, then at `t=N` adds an exclusion for all `autonomous` entries of the target device — simulating it going silent.

---

## User Configuration Import

To reproduce a user's exact environment, we need their full ramses_cc config — not just `known_devices` but also schema, orphans, advanced settings.

### What to import

ramses_cc stores its config in two places:

- `configuration.yaml` / `config_entries` — `serial_port`, `schema`, `known_devices`, `orphan_ids`, `enforce_known_list`, etc.
- Config entry options (set via config flow) — stored in HA's `.storage/core.config_entries`

### Import approach

```python
def import_from_cc_config(config_path: str) -> SystemConfigProfile:
    """Parse a ramses_cc configuration.yaml or config entry JSON.
    Extracts: known_devices, schema, orphan_ids, enforce_known_list,
    message_events, and any advanced options.
    Returns a SystemConfigProfile ready to activate."""
```

The simulator provides a service call:

```yaml
service: device_simulator.import_user_config
data:
  source: '/config/configuration.yaml' # or a pasted YAML string
  name: 'User report #42 - FAN disappears'
  attach_log: '/tmp/user_packets.txt' # optional packet log to go with it
```

This creates a named profile combining their exact config + their packet log — immediately reproducible.

### What gets extracted

- `known_devices` dict → seeded into profile's `ramses_cc_config`
- `schema` (system layout) → profile's zone/device topology
- `orphan_ids`, `enforce_known_list` → simulator respects these when deciding which device IDs to emit
- Advanced options (poll_interval, disable_discovery, etc.) → stored in profile metadata for reference

---

## HA Automation Testing

Because the simulator runs **inside the same HA container**, user automations, scripts, and dashboard configs can be installed alongside it and tested against simulated device traffic.

### How it works

- User installs their `automations.yaml` / `scripts.yaml` in the container config
- Simulator runs a scenario (e.g. FAN speed changes, CO2 spikes, zone temp drops)
- HA processes the simulated device events exactly as it would real ones
- Automations fire, scripts execute, entity states update — fully observable


### What this enables

- Test `if CO2 > 1000 ppm then set FAN to boost` automation without hardware
- Test `notify when zone goes unavailable` alert automation
- Reproduce a user's automation bug: "my FAN speed automation stopped working after update"
- Future: assertion hooks — check HA state after conversation completes

**Note**: this does NOT require any changes to HA's automation engine — it just injects the right simulated device traffic and lets HA do its thing.

---

## Success Criteria

### Core

- [ ] ramses_rf + MQTT transport connects to MQTT broker in container
- [ ] Simulator connects to same broker as second MQTT client
- [ ] Virtual FAN emits 31DA → FAN entity appears in HA with correct attributes
- [ ] ramses_rf sends RQ 31DA → simulator responds with real RP payload

### Bug Reproduction

- [ ] Device stops emitting → HA entity goes `unavailable` at correct (scaled) timeout
- [ ] Device resumes emitting → HA entity recovers correctly
- [ ] `heartbeat_timeout_scale: 0.01` makes a 1h timeout fire in ~36 seconds
- [ ] Can import a user packet log + config and reproduce their exact failure
- [ ] `device_unavailability` scenario runs end-to-end with observable HA state changes

### Configurations

- [ ] Load `heat_evohome_basic` profile → heating entities appear in HA
- [ ] Load `hvac_fan_co2` profile → HVAC entities appear, heating entities gone
- [ ] Load `mixed_full` profile → both heating and HVAC entities present
- [ ] Switch profiles without manual file editing

### Stress

- [ ] Flooding test: 100 msgs/sec, 60s, no HA instability
- [ ] Discovery test: simulator emits `10E0` → ramses_rf detects device type

---

## Resources

### Build-time (offline DB construction)

- `ramses_rf/src/ramses_tx/ramses.py` — `_DEV_KLASSES_HEAT/HVAC`: authoritative `{slug: {Code: {verb}}}` schema
- `ramses_rf/src/ramses_tx/fingerprints.py` — `__DEVICE_INFO_RAW`: ~70 hardware variants with brand/model/firmware
- `ramses_rf/src/ramses_tx/parsers.py` — payload format/validation regexes per `(code, verb)`
- `ramses_rf/tests/fixtures/regression_packets_sorted.txt` — 32,326 real packets; mined once for payloads + intervals

### Runtime

- `ramses_rf/src/ramses_tx/transport/mqtt.py` — MQTT topic format: `ramses_gateway/{id}/rx` (inbound), `/tx` (outbound)
- `ramses_rf/src/ramses_tx/transport/port.py` — socat instructions for virtual serial pty pair
- `ramses_rf/src/ramses_rf/device/base.py` — `heartbeat_timeout` + `is_available` logic
- `ramses_rf/src/ramses_rf/device/heat.py` — `HEARTBEAT_TIMEOUT_OTB/TRV`
- `ramses_rf/src/ramses_rf/device/hvac.py` — `HEARTBEAT_TIMEOUT_REMOTE/SENSOR`
- `ramses_rf/src/ramses_rf/const.py` — module-level timeout constants (patch target)

---

## Notes

- **MQTT is the preferred mode** — cleaner than virtual serial, easier to debug (MQTT Explorer shows all traffic)
- The simulator is completely external to ramses_rf/cc — no patching, no monkey-patching
- **Profile system** is what turns this from a toy into a serious test tool — being able to reproduce exact user configs is the key capability
- **Config import** from a user's `configuration.yaml` + packet log → instant reproduction of their exact environment
- **Heartbeat timeout** is the root of device unavailability reports — the simulator can reproduce it deterministically by stopping `I` messages at a precise time
- **Exclusions** at device and code level are what make targeted bug reproduction possible — silence exactly the right thing
- **Automation testing**: running inside the same HA container means user automations react to simulated events with zero extra setup
- The standalone container approach means we can reset/rebuild freely — treat it as disposable infrastructure
- The ramses_rf/cc device architecture transition (WIP) is exactly why this simulator has lasting value — new device capabilities can be tested here as they're added

---

## Device DB Audit Tooling

### Tool: `tools/audit_device_db.py`

Offline script that audits, enriches and applies DB payloads through the full pipeline.
**Activate venv first**: `source ~/venvs/extras/bin/activate`

### Modes

| Command | What it does |
|---|---|
| `python tools/audit_device_db.py` | Parse all DB payloads, write `tools/audit_all.yaml` |
| `python tools/audit_device_db.py --device FAN` | Audit single device, write `tools/audit_fan.yaml` |
| `python tools/audit_device_db.py --extract-from-logs` | Mine known log files, update DB YAMLs in-place |
| `python tools/audit_device_db.py --extract-from-logs /path/a /path/b` | Same, with explicit log paths |
| `python tools/audit_device_db.py --llm-audit tools/audit_all.yaml` | Heuristic pass, write `tools/audit_all_reviewed.yaml` (attention-only) |
| `python tools/audit_device_db.py --apply-audit tools/audit_all_reviewed.yaml` | Apply reviewed decisions back to DB YAMLs |

### Full Pipeline (run in order)

```bash
# 1. Mine any new log files and upgrade DB payloads automatically
python tools/audit_device_db.py --extract-from-logs

# 2. Audit everything — generates audit_all.yaml with Y/N/Remark per payload
python tools/audit_device_db.py --output tools/audit_all.yaml

# 3. Heuristic LLM pass — auto-decides obvious cases, writes attention-only file
python tools/audit_device_db.py --llm-audit tools/audit_all.yaml

# 4. Human review — open tools/audit_all_reviewed.yaml
#    Change audit: fields where the heuristic was wrong
#    Y = keep, N = remove, Remark = keep with note

# 5. Apply reviewed decisions back to DB YAMLs
python tools/audit_device_db.py --apply-audit tools/audit_all_reviewed.yaml
```

### When New Log Files Arrive

1. Add the log file path to `_DEFAULT_LOG_FILES` in `audit_device_db.py`, **or** pass it explicitly:
   ```bash
   python tools/audit_device_db.py --extract-from-logs /path/to/new.log
   ```
2. Run the full pipeline from step 1 above.
3. The extractor will only **replace** existing DB payloads if the new captures score better (fewer sentinels, no implausible values). Existing good payloads are never downgraded.

### Frame Classification Logic

The extractor uses **address pattern + RQ context window**, not just verb, to classify each frame:

| Pattern | Code type | Recent RQ? | → Section |
|---|---|---|---|
| `I src --:------ src` | any | — | `autonomous` (self-addressed) |
| `I src 63:262142 --:------` | any | — | `autonomous` (broadcast) |
| `I src dst --:------` | I-only (no RQ in schema) | — | `autonomous` (unsolicited push) |
| `I src dst --:------` | has RQ | no (within 5s) | `autonomous` (unsolicited) |
| `I src dst --:------` | has RQ | yes (within 5s) | `responses` (solicited) |
| `RP src dst --:------` | any | — | `responses` |

**I-only codes** (never have a RQ cycle) are loaded from `ramses_tx.CODES_SCHEMA` at runtime. Examples: `31DA`, `31D9`, `1060`, `22F3`, `3150`.

### Sentinel Allowlist

Some codes have sentinel bytes that are **valid** (device has no sensor for that field).
Configured in `_CODE_SENTINEL_ALLOWLIST` in the script:

| Code | Allowed sentinels | Why |
|---|---|---|
| `22F7` | `EF` | Bypass position sensor absent on many units |
| `31DA` | `7FFF`, `EF`, `EFEF` | Temp / AQ / CO2 sensors optional |
| `10E0` | `FFFF` | Padding bytes in device info |

### Payload Quality Scoring

Each payload gets a score (used to select best capture from logs):
- Start: 100
- `-20` per unexpected sentinel byte pattern
- `-30` per implausible field value (e.g. temp=-60, fan_speed=0 when all fields zero)
- `-5` per `None` field (could not be decoded)

Existing DB payloads are only replaced if the new score is strictly higher.

### Audit Decisions

| `audit:` value | Meaning | `--apply-audit` action |
|---|---|---|
| `Y` | Good — keep as-is | Keep payload unchanged |
| `N` | Bad — remove from DB | Payload removed |
| `Remark` | Keep but note the issue | Keep with inline `# REMARK:` comment |
| `?` | Unreviewed | Kept with a warning printed |

### Outstanding DB Issues (as of 2026-04-13)

After running the full pipeline, the following categories need human attention in `tools/audit_all_reviewed.yaml`:

**`N` — parser rejects (payload format wrong for verb/code):**
- `CTL/0404`, `CTL/0001`, `CTL/0010`, `CTL/22D9`, `CTL/3EF0` — payloads don't match RP parser regex; need correct RP-format payloads or removal
- `DHW/2309`, `DHW/2349` — multi-zone format sent as single-zone RP
- `TRV/2309`, `TRV/12B0`, `TRV/3150`, `TRV/22D9`, `TRV/3EF0` — same issue
- `REM/12C8` — wrong verb (12C8 is I-only, not RP)
- `FAN/22F1`, `FAN/22F3` — payloads too short for parser

**`N` — mostly sentinel (placeholder payloads, no real data):**
- `RFG/31DA` — all three payloads heavily sentinel; no real RFG captures available
- `FAN/22F7` — `EF` in a 1-byte field = nothing but sentinel

**`Remark` — sentinel bytes present but decode OK (verify before shipping):**
- `10E0` on most device types — `FFFF` padding in device info is normal, but double-check real firmware dates
- `BDR/1100`, `CTL/1F41`, `CTL/2349` — `7FFF` temp setpoint sentinel means "no override active"; may be valid

**Next steps:**
1. Open `tools/audit_all_reviewed.yaml`, review each `N` and `Remark` entry
2. For parser-reject `N` entries: find correct RP payload format from `ramses_tx/parsers.py` or remove
3. For `RFG/31DA`: if no real captures exist, remove the sentinel payloads (DB entry stays with empty `payloads:`)
4. Run `--apply-audit` to apply decisions
5. Re-run audit to confirm clean state

---

## Implementation Status

**Last Updated:** 2026-04-13

### Completed ✅

| Component | Status | Details |
|-----------|--------|---------|
| Feature structure | ✅ | `features/device_simulator/` with proper layout |
| `const.py` | ✅ | MQTT topics, scenario types, verb constants |
| `comm_endpoint.py` | ✅ | `MqttEndpoint` with HA MQTT integration |
| `device_db.py` | ✅ | YAML loader, `DeviceDatabase` with query methods |
| `scenario_engine.py` | ✅ | `ScenarioEngine` with emitters, responses, conversation playback |
| `services.py` | ✅ | HA services (inject, activate, silence, run_scenario, stop_scenario, import_config) |
| `websocket.py` | ✅ | 8 WebSocket commands for real-time control |
| `platforms/sensor.py` | ✅ | 3 sensors (status, messages_sent, active_devices) |
| Device DB build script | ✅ | `scripts/build_device_db.py` mines ramses_rf sources |
| Generated YAML files | ✅ | 21 device types in `device_db/heat/` and `device_db/hvac/` |
| Conversation YAML | ✅ | `fan_rem.yaml` with RQ/RP exchanges |
| MQTT dependency | ✅ | Added to `manifest.json` |
| Message logging | ✅ | All sent packets logged for WebSocket retrieval |

### In Progress 🔄

| Component | Status | Notes |
|-----------|--------|-------|
| Scenario runners | 🔄 | Per-file modules for `device_playback`, `device_suite`, `discovery_test`, `timeout_test`, `flooding_test`, `device_unavailability`, `hvac_device_loss`; still need full implementations for playback/suite/discovery/flooding/timeouts + UI wiring |
| End-to-end testing | ⏳ | Requires HA with MQTT broker setup |

### Pending ⏳

| Component | Status | Notes |
|-----------|--------|-------|
| Profile system | ⏳ | Import user ramses_cc config + packet log |
| More conversations | ⏳ | CO2 sensor, REM temperature patterns |
| UI panel | ⏳ | Custom card for device browser & scenario control |
| Heartbeat scaling | ⏳ | Monkeypatch integration for timeout tests |

### Architecture Decisions

- **MQTT integration**: Uses HA's built-in MQTT via `homeassistant.components.mqtt` (no separate broker client)
- **Device Database**: Layered YAML with baseline + variants + conversations, built offline from regression file
- **Isolation**: Fixed gateway ID `18:001234` prevents collision with real hardware
- **No ramses_rf modifications**: Simulator is completely external

---

## Frame Format Requirements (Discovered During Debugging)

The RAMSES protocol frame format must exactly match what `ramses_tx` expects. Any deviation causes `PacketInvalid` errors.

### Verified Frame Format

```
RSSI VERB --- SRC DST BROADCAST CODE LEN PAYLOAD
```

**Field Details:**
- **RSSI**: 3 digits (e.g., `082` for I frames, `000` for RP responses)
- **VERB**: 2-3 chars with leading space for 1-char verbs
  - ` I` (Info) - space + I
  - ` W` (Write) - space + W
  - `RQ` (Request) - no leading space
  - `RP` (Response) - no leading space
- **SRC/DST**: Device IDs in format `XX:XXXXXX`
- **BROADCAST**: For I frames, equals SRC; for RP/RQ, typically `--:------`
- **CODE**: 4 hex digits (e.g., `22F7`, `2411`)
- **LEN**: 3 digits, payload length in bytes
- **PAYLOAD**: Hex string, 2 chars per byte

### Critical Format Rules

| Verb | RSSI Position | Extra Space | Example |
|------|---------------|-------------|---------|
| I | First | Yes: `082  I` | `082  I --- 32:153289 --:------ 32:153289 22F7 001 00` |
| W | First | Yes: `000  W` | `000  W --- 32:153289 37:168270 --:------ 22F1 003 000407` |
| RP | First | No: `000 RP` | `000 RP --- 32:153289 37:168270 --:------ 2411 023 000031...` |
| RQ | First | No: `000 RQ` | `000 RQ --- 37:168270 32:153289 --:------ 2411 003 000031` |

### Common Mistakes

1. **Verb before RSSI**: `I 082` → Wrong. Must be `082  I`
2. **Missing BROADCAST field**: Causes `PacketInvalid` - I frames need SRC as BROADCAST
3. **Wrong spacing after verb**: `082 I ---` → Wrong. Must be `082  I ---` (2 spaces)
4. **Wrong spacing for 2-char verbs**: `000  RP` → Wrong. Must be `000 RP` (1 space)

### Implementation Reference

```python
# I frame (periodic announcement)
frame = f"082  I --- {device_id} --:------ {device_id} {code} {len:03d} {payload}"

# RP frame (response to RQ)
frame = f"000 RP --- {src} {dst} --:------ {code} {len:03d} {payload}"
```

### Frame Validation

All frames must pass `ramses_tx.const.COMMAND_REGEX`:
```python
COMMAND_REGEX = re.compile(
    r"^([0-9A-F]{2}([0-9A-F]{2}){1,2}){0,1} "  # RSSI (optional for outbound)
    r"([ RQW]{1,3}) "                           # Verb
    r"--- "                                     # Separator
    r"([0-9:]{9}) "                            # SRC
    r"([0-9:]{9}|--:------) "                  # DST
    r"([0-9:]{9}|--:------) "                  # BROADCAST
    r"([0-9A-F]{4}) "                          # CODE
    r"(\d{3})"                                 # LEN
    r"( [0-9A-F]{2,})*$"                       # PAYLOAD
)
```

---

_Status: Phase 1-7 Complete — Core infrastructure, device database, comm endpoint, response engine, periodic emitter, config profiles, and scenario engine ready for testing_
_Priority: UI Cards (Phase 8) and advanced features (Phase 9)_
_Estimated Effort: 2-3 weeks for full MVP completion_
