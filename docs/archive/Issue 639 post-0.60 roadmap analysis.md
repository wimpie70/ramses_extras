# Issue 639: balanced post-0.60 roadmap analysis

## Purpose

This document reviews the latest roadmap proposal in:

- https://github.com/ramses-rf/ramses_rf/issues/639
- https://github.com/ramses-rf/ramses_rf/issues/639#issuecomment-5358848883

The goal is not to produce a perfect architecture. The goal is to agree on a
post-0.60 roadmap that balances two legitimate priorities:

1. Stronger contracts, cleaner boundaries, and less technical debt.
2. A stable and understandable codebase that solves user problems without
   creating months of risky refactoring and review work.

Stable 0.60.0 remains the release gate. The roadmap below applies after that
release has been tagged and verified.

## Executive conclusion

The latest proposal contains a sound architectural direction but too many
asserted prerequisites.

The sound direction is:

- Multiple physical HGIs should appear as one RAMSES network to the domain
  layer.
- Incoming frames should be combined and deduplicated below the domain model.
- Outbound traffic should use exactly one healthy HGI: the HGI with the
  strongest recent average RSSI for the target device.
- `ramses_rf` should not build separate device registries and topology graphs
  for each dongle.

The parts that should be narrowed are:

- Type-safety PRs 1–6 should not become a mandatory Wave 0.
- A serial library migration and payload-construction rewrite are not
  mechanical typing work.
- SQLite removal, HVAC Strategy, command-bus completion, and full transport
  FSM decommission are not proven prerequisites for multi-HGI.
- Transport pooling cannot require literally zero changes outside
  `ramses_tx`; configuration and the concept of local HGI identity are
  currently singular.

The recommended compromise is:

- Keep the useful user-facing and maintainability work: Phase 7 cleanup, UFH,
  OpenTherm, and a deliberately small Strategy extraction.
- Treat typing improvements as an independent quality track, not a gate.
- Implement multi-HGI as a minimal vertical slice with acceptance tests,
  rather than first completing every surrounding architecture phase.
- Keep SQLite, FSM, and command-bus work incremental and evidence-driven.

## Decision principles

Every roadmap item should satisfy these rules.

### 1. Stable behavior is the primary constraint

No post-0.60 refactor is merged merely because it produces a theoretically
cleaner architecture. It must preserve behavior and have focused regression
coverage.

### 2. User-facing defects and missing capabilities come first

UFH correctness, OpenTherm state, vendor-specific HVAC behavior, and
multi-HGI reception/transmission provide direct user value. They take
priority over broad mechanical rewrites.

### 3. A dependency must be demonstrated

An item is a prerequisite only when a focused test or prototype proves that
another item cannot proceed without it. Architectural preference alone is
not enough.

### 4. Prefer narrow vertical changes

A small change that implements and verifies one complete behavior is easier
to review than a sequence of broad foundational PRs whose value only appears
much later.

### 5. Stop after sufficient improvement

The target is maintainable and reliable code, not zero `Any`, zero
`getattr`, zero casts, or a perfect interpretation of OSI layering.

### 6. Re-audit before executing an old plan

The codebase has changed quickly. Plans based on counts of ignores, casts,
or untracked tasks become stale. Each phase starts with a fresh audit of
current `master`.

## Assessment of the proposed Wave 0

The latest proposal makes Phase 6.5 PRs 1–6 a foundational type-safety wave.
The intention is good, but the group is not uniformly low-risk or mechanical.

Current facts:

- CI already runs mypy and currently passes under the repository's configured
  strictness.
- There are still approximately 126 source `# type: ignore` suppressions.
- Important task paths already maintain strong references, including protocol
  handler tasks, FSM send tasks, Engine tasks, and EntityState delete tasks.
- `Message.dtm` is already explicit, so part of the earlier message-contract
  proposal is complete.
- The audit must therefore be refreshed before planning six PRs from the old
  counts.

### Wave 0 item-by-item assessment

| Proposed item | Value | Risk | Recommendation |
|---|---:|---:|---|
| Nullable annotations and defaults | Useful | Low | Do opportunistically in one small PR after a fresh audit. |
| Generics, tuple annotations, and `DeviceIdT` wrappers | Useful | Low | Combine with the nullable quick wins if the diff remains small. |
| Replace pyserial with `serialx` | Potentially useful | Medium/high | Keep as a separate dependency/runtime proposal. Do not classify as typing cleanup. |
| Replace polymorphic payload `__new__` methods | Some typing benefit | Medium/high | Defer unless a concrete payload bug or API need justifies it. The payload layer was recently changed and remains regression-sensitive. |
| Standardise Message tracing properties | Mixed; partly complete | Medium | Re-audit. Add only properties with a current consumer. Do not add speculative trace metadata. |
| Structured concurrency and task references | Useful where leaks exist | Medium | Fix demonstrated task-lifecycle defects individually. Do not rewrite all task creation as one phase. |

### Recommended type-safety policy

Do not create a mandatory Wave 0.

Maintain an independent quality track:

1. Re-run the audit on current `master`.
2. Merge one small quick-wins PR if it is genuinely mechanical.
3. Keep serial transport migration separate.
4. Keep payload factory changes separate.
5. Stop when CI typing catches the defects relevant to upcoming work.

This preserves Phil's compiler-safety objective without delaying all
user-facing work behind six PRs.

## Roadmap item assessments

### Phase 7: inbound pipeline cleanup

Reference:
https://github.com/ramses-rf/ramses_rf/issues/1092

This remains sensible if its scope stays limited to code proven dead or
paused.

Recommended scope:

- Remove the obsolete `_handle_msg` hook only if no override exists.
- Remove adapters and async pipeline components only when static search and
  tests prove they are unused.
- Retain `to_legacy_dict()`, `shim_status`, and topology translation while
  `ramses_cc` still depends on them.
- Do not activate the paused asynchronous pipeline as part of cleanup.

This should be one deletion-focused PR with the full unit and HA simulation
suites. It is low risk when treated as cleanup, not as a hidden pipeline
cutover.

### Phase 7.5: UFH modernisation

This work has direct value because it addresses real UFH/PWM manifold
behavior and can be validated against Phil's installation.

It should remain on the roadmap with these constraints:

- Start with a reproducible failing test for the stroke/demand behavior.
- Separate bug fixes from model cleanup where possible.
- Avoid redesigning unrelated zone or actuator models.
- Preserve existing UFH behavior through data-driven packet fixtures.

UFH is independent of Strategy, SQLite, command-bus, and multi-HGI work. It
can proceed after 0.60 without waiting for them.

### Phase 8: OpenTherm state extraction

Extracting OpenTherm-specific state from generic `DemandState` is reasonable
when it clarifies actual OpenTherm behavior or exposes missing values.

Recommended scope:

- Move only state fields that are demonstrably OpenTherm-specific.
- Preserve all current property results and entity behavior.
- Add packet-level parity tests before moving fields.
- Avoid making this a general state-model rewrite.

OpenTherm work is independent of Strategy and multi-HGI. It should not depend
on SQLite removal unless a specific getter requires it.

### Strategy pattern

Reference:
https://github.com/ramses-rf/ramses_rf/issues/1093

A small Strategy extraction makes sense. Vendor-specific HVAC behavior should
not continue accumulating in one global `quirks.py` function.

However, the first implementation should be smaller than the full long-term
proposal.

Recommended first scope:

1. Extract the existing Orcon/Itho behavior without changing results.
2. Select a strategy from existing `_scheme` or explicit device traits.
3. Keep a generic strategy as the default.
4. Add parity tests proving the extracted strategies reproduce the current
   quirk outputs.

Defer until demonstrated necessary:

- Dynamic strategy swapping from accumulated packet evidence.
- Transport-aware strategy selection.
- Moving all fan-mode command construction into strategies.
- New Protocol/visitor hierarchies.

The Strategy pattern improves maintainability and vendor behavior. It is not
a prerequisite for multi-HGI, SQLite removal, or transport pooling.

### Phase 9: SQLite state deprecation

Removing disk-backed state reads from property getters is valuable, but it is
a broad and regression-sensitive change.

Recommended approach:

- Measure and list the remaining property getters that actually read from the
  MessageStore.
- Convert one state family at a time to an existing in-memory read model.
- Keep packet logging/history storage separate from current-state retrieval.
- Verify warm restart, cache restoration, and stale packet behavior after
  each conversion.
- Do not perform a single big-bang MessageStore removal.

SQLite work is not a prerequisite for multi-HGI if duplicate frames are
removed before entering the domain stream.

### Phase 10 and 10.5: command bus and transport FSM

The current architecture still has both L7 `ConversationManager` tracking and
L3 protocol/FSM reply handling. Consolidation may eventually remove duplicate
logic.

That does not make full FSM decommission an automatic prerequisite for other
features.

Recommended policy:

- Keep the current send path stable until parity tests cover echo, reply,
  timeout, retry, impersonation, HGI80, evofw3, and MQTT behavior.
- Finish individual command paths through `CommandDispatcher` when touching
  those paths for a concrete feature.
- Change or remove FSM responsibilities only when a focused test demonstrates
  duplication or blocks multi-HGI.
- Do not make an approximately 880-line FSM rewrite a roadmap gate.

## Multi-HGI architecture assessment

References:

- https://github.com/ramses-rf/ramses_rf/issues/289
- https://github.com/ramses-rf/ramses_rf/issues/639#issuecomment-5358848883

### What is agreed

The upper domain should see one RAMSES network, not one independent network
per HGI.

The intended shape is:

```text
USB HGI ----\
             +-- transport pool -- one deduplicated packet stream --> ramses_rf
MQTT HGI ---/
```

The transport side should primarily own:

- Child transport lifecycle.
- Per-HGI receive observations.
- Cross-HGI packet deduplication.
- Transport health.
- Selection of the healthy outbound HGI with the best recent average RSSI
  for the target device.
- Deterministic fallback when no RSSI observations exist.
- HGI-specific source-address behavior.

`ConversationManager`, `TopologyBuilder`, device state, and Home Assistant
entities should remain transport-agnostic wherever possible.

### Where the latest proposal is too absolute

The current implementation is singular in several places:

- `EngineConfig` has one `port_name` and one `hgi_id`.
- `Engine` owns one Protocol and one Transport.
- Protocol source-address patching uses one active HGI ID.
- `Gateway.hgi` exposes one active HGI.
- `DeviceFilter` receives one active-HGI provider.
- `DiscoveryScan` contains a TODO to check all local HGI IDs.
- `ramses_cc` config flow currently configures one endpoint.

Therefore, transport pooling can keep domain processing single-stream, but it
cannot require literally zero changes outside `ramses_tx`.

The unavoidable non-transport changes should remain small:

- Accept multiple transport endpoints in configuration.
- Expose the set of configured local HGI IDs.
- Preserve one primary/default `Gateway.hgi` for compatibility.
- Treat every configured local HGI as local rather than foreign.
- Make discovery ignore all configured local HGIs.
- Extend the `ramses_cc` config flow to configure the endpoint list.

### Source-address and echo correctness

Outbound selection cannot be based only on which child transport writes a
prebuilt frame.

Different HGI types require different source treatment:

- evofw3 may require its real HGI ID.
- HGI80 may require the `18:000730` placeholder.
- Two evofw3/MQTT gateways have different real HGI IDs.

The selected child transport and source-address patch must therefore be
chosen consistently before echo tracking begins.

The transport layer should continue to own echo verification. It cannot be
completely stateless if echo verification remains part of the issue-639
boundary.

### Deduplication correctness

The same RF transmission may arrive through multiple HGIs with different
RSSI values and slightly different timestamps.

A pool should use all copies to update its routing observations but emit only
one packet upstream. A likely deduplication key is:

```text
verb + addr1 + addr2 + addr3 + code + raw payload
```

within a short receive window. RSSI and timestamp should not be part of that
identity key.

Tests must prove that deduplication does not suppress legitimate repeated
transmissions.

### RSSI routing correctness

The first routing policy can remain deliberately simple. For each target
and each HGI, keep a bounded history of the last five valid inbound RSSI
samples and use their arithmetic mean:

```text
rssi_samples[(target_device_id, hgi_id)] = deque(maxlen=5)
best_hgi = max(healthy_hgis, key=average_rssi_for_target)
```

The policy should follow these rules:

- Record the RSSI reported by every HGI before duplicate packets are
  collapsed into one upstream packet.
- Key observations by the source device of the inbound RF packet; that
  source becomes the target when sending a command back to it.
- Use however many samples are available; do not wait for all five.
- Ignore TX echoes, missing RSSI values, and invalid RSSI values.
- Prefer the healthy HGI with the strongest average. "Closest" here means
  the best observed radio path, not physical distance.
- When no HGI has observations for a target, use a configured/default HGI.
- Resolve equal averages deterministically, preferably in favor of the
  configured/default HGI.
- Keep these observations in memory. They do not need to be persisted.

Transport health belongs in the selection filter, but defining health
checks, warning users, and reporting a degraded HGI can be a separate task.
The first routing implementation only needs a way to exclude an HGI already
known to be unhealthy.

### No separate throwaway spike is required

A separate experimental project would add overhead. Instead, the first
multi-HGI PR should be a minimal vertical slice guarded by acceptance tests.

Start with tests using two virtual or callback transports:

1. Both transports connect.
2. A frame heard by both is emitted upstream once.
3. The last five RSSI observations are retained independently for each
   target/HGI pair.
4. One outbound command uses exactly one healthy transport: the transport
   with the strongest average RSSI for that target.
5. The command source address matches the selected HGI type and ID.
6. Echo/reply handling still completes.
7. With no RSSI history, the configured/default HGI is selected.
8. An unhealthy best-RSSI HGI is excluded and the next valid HGI is used.
9. Mixed MQTT and direct-port transports follow the same contract.

A reasonable first implementation shape is:

```text
Engine
  +-- one Protocol
       +-- one PooledTransport
            +-- PortTransport
            +-- MqttTransport
```

If this shape cannot satisfy the existing `TransportInterface`, the failing
acceptance test identifies the smallest required extraction. That is better
than preemptively completing Phase 9, Phase 10, or Phase 10.5.

## Proposed post-0.60 roadmap

The order below is a priority order, not a claim that every earlier row is a
technical dependency of every later row. Items marked parallel may proceed
at the same time when review capacity allows.

| Order | Roadmap item | Primary value | Scope guard | Dependencies | Risk |
|---:|---|---|---|---|---|
| 0 | Stable 0.60.0 release | Establish a trusted baseline | No roadmap refactors before the release is verified | Current release fixes | Low |
| 1 | Post-release bug fixes | Protect users and the baseline | Reproducible defects only; no architecture bundled into fixes | Stable 0.60.0 | Low/medium |
| 2 | Phase 7 inbound cleanup | Reduce dead-code noise | Delete only code proven unused; no async pipeline cutover | Stable baseline | Low |
| 3 | Phase 7.5 UFH correctness | Fix real UFH/PWM behavior | Tests first; avoid unrelated model redesign | Stable baseline | Medium |
| 4 | Phase 8 OpenTherm extraction | Improve OpenTherm state ownership and missing values | Move only OpenTherm-specific state with parity tests | Stable baseline | Medium |
| 5 | Minimal HVAC Strategy extraction | Contain current vendor quirks | Existing behavior only; `_scheme` selection; defer dynamic swapping | Stable baseline and current payload models | Low/medium |
| 6 | Multi-HGI vertical slice | Deliver the main missing capability | Unified stream, deduplication, five-sample average RSSI routing across healthy HGIs, source correctness, deterministic fallback | Stable transport contract; not SQLite/Strategy/FSM decommission | Medium/high |
| 7 | Incremental SQLite state cutover | Remove disk reads from current-state getters | One state family per PR; preserve logging/history | In-memory state parity for each family | Medium/high |
| 8 | Command path consolidation | Reduce direct-send and duplicate conversation paths | Convert touched command families; parity tests | Concrete consumer or blocker | Medium/high |
| 9 | FSM responsibility reduction | Remove proven duplicate reply logic | Echo tracking remains in transport; no big-bang rewrite | Full echo/reply/timeout parity | High |
| Q | Typing quick wins, anytime | Improve local compiler coverage | Re-audit first; small nullable/generic PRs only | None; never a roadmap gate | Low |
| D | serialx, payload factory rewrite, Protocol/visitor overhaul | Potential future cleanup | Separate proposals with demonstrated benefit | None currently | Medium/high; deferred |

## Suggested waves and ownership

### Release gate

- Finish and verify stable 0.60.0.
- Merge no broad roadmap refactors before that baseline.

### Wave 1: independent, reviewable work

These items can proceed independently after 0.60 when reviewer capacity
allows:

- Phase 7 deletion-only cleanup.
- UFH bug/model work, led by Phil with real hardware validation.
- OpenTherm extraction, led by Phil with packet fixtures.
- Minimal Strategy extraction, led by Willem.
- A refreshed typing quick-wins audit, but not as a gate.

### Wave 2: primary capability and state improvements

- Multi-HGI minimal vertical slice with acceptance tests.
- Incremental SQLite getter conversion may proceed separately.

Neither item blocks the other.

### Wave 3: conditional consolidation

- Consolidate command paths where Strategy or multi-HGI demonstrates a need.
- Reduce FSM responsibilities only after parity tests and only to the extent
  required.

This wave is conditional. It is not automatically required merely because it
appeared in an earlier architecture blueprint.

## Agreement points for maintainers

A roadmap is agreeable when all maintainers can accept the following:

1. 0.60.0 stability comes first.
2. User-facing fixes and capabilities outrank architecture purity.
3. Phil may pursue type quality, UFH, and OpenTherm improvements in focused,
   test-backed PRs.
4. Willem may pursue the minimal Strategy extraction and multi-HGI work
   without waiting for unrelated phases.
5. No item is declared a prerequisite without a demonstrated dependency.
6. Broad dependency, payload, state, or FSM rewrites remain separate review
   decisions.
7. Every phase can stop once the code is sufficiently reliable and
   maintainable.

## Recommended decision on the latest proposal

Accept the architectural intent, but amend the execution plan:

- Accept unified link-layer transport pooling as the preferred multi-HGI
  direction.
- Reject "zero changes outside ramses_tx" as an absolute requirement.
- Reject Phase 6.5 PRs 1–6 as a mandatory Wave 0.
- Reject SQLite, Strategy, command-bus completion, and full FSM decommission
  as unproven multi-HGI prerequisites.
- Keep Phase 7, UFH, OpenTherm, and a minimal Strategy extraction.
- Begin multi-HGI with acceptance tests and a minimal vertical slice rather
  than a separate throwaway spike or a long prerequisite chain.
- Keep deeper cleanup optional and evidence-driven.

This gives Phil room to improve contracts and architecture while protecting
the maintainers and users from unnecessary, review-heavy, high-risk work.
