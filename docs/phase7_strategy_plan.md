# Phase 7 + Strategy Pattern Plan

**Created:** Aug 19 2026
**Status:** Draft — pending agreement with PWhite-Eng and silverailscolo
**Related:** https://github.com/ramses-rf/ramses_rf/issues/639#issuecomment-5341806836
**Depends on:** All Phase 2.x work (DONE), Phase 6 dataclass payloads (DONE)

> **Scope note:** This plan covers two independent workstreams
> that can run in parallel (Wave 1 from the issue 639 roadmap):
> - **Phase 7** — inbound pipeline cleanup (dead code removal)
> - **Strategy pattern** — extract vendor-specific quirks into
>   strategy classes (stops quirks.py growth, prerequisite for
>   Phase 10 command bus and multi-HGI)

---

## Table of Contents

- [Phase 7: Inbound Pipeline Cleanup](#phase-7-inbound-pipeline-cleanup)
- [Strategy Pattern](#strategy-pattern)
- [Parallelism and Dependencies](#parallelism-and-dependencies)
- [Risk Assessment](#risk-assessment)

---

<a id="phase-7-inbound-pipeline-cleanup"></a>
## Phase 7: Inbound Pipeline Cleanup

**Goal:** Remove dead code, legacy shims, and paused async
infrastructure left over from the Phase 2.x strangler fig
migration.  The inbound pipeline works correctly today — this
phase is pure cleanup with zero behavior change.

**Risk:** LOW.  All code being removed is either dead (never
called), paused (explicitly not started), or adapter layers
that duplicate working functionality.

### Current State

The Phase 2.x strangler fig migration left behind:

1. **Paused async pipeline** — `CentralDispatcher`
   (`pipeline/dispatcher.py`) with async queues for SSOT,
   discovery, binding, and faked devices.  Built but never
   activated — `lifecycle.py:123` says "We do not call .start()
   because the Phase 2.75 async cutover is paused".  The
   synchronous path in `gateway.py:521-525` is used instead.

2. **Legacy parser adapters** — `_LegacyAddress` and
   `_LegacyMessage` classes in `parsers/decoder.py:57-140`,
   mimicking the old ramses_tx interface.  All 108 dataclass
   parsers are registered and active; the legacy path always
   falls through to `parse_unknown_payload`.

3. **29+ `to_legacy_dict()` methods** in `payloads/hvac.py` —
   anti-corruption layer converting dataclass payloads back to
   dicts for ramses_cc.  ramses_cc still receives dict payloads
   via the `payload_to_dict()` boundary adapter (retained in
   Phase 6), so these methods are still called.  **Cannot remove
   until ramses_cc is migrated to dataclass payloads** — out of
   scope for Phase 7.

4. **Legacy `_handle_msg` hook** in `ramses_tx/engine.py:418` —
   `handler = getattr(self, "_handle_msg", None)`.  All device
   `_handle_msg` overrides were deleted in Phase 2.95; the hook
   remains but always falls through to the callback path.

5. **Strangler fig translation** in `gateway.py:504-517` —
   bridges TopologyBuilder to the old routing format.  Works
   but adds an unnecessary translation step.

6. **`shim_status` method** in `hvac_ventilators.py:882-905` —
   maps CQRS keys back to legacy downstream keys.  Still used by
   ramses_cc's `sync_learned_topology`.  **Cannot remove until
   ramses_cc uses CQRS state directly** — out of scope.

7. **Legacy trace logger** — `_TRACE =
   logging.getLogger("ramses_rf.legacy_trace")` in
   `dev_registry.py:41` and `zones.py:86`.  No longer referenced
   for actual tracing.

8. **Phase 3 device registry logic** — `dev_registry.py:957`
   has `if False:` guarding "PHASE 3" logic.  Status unclear —
   needs PWhite-Eng input before enabling.

### What's In Scope (safe to remove)

| Item | File(s) | Lines | Risk |
|------|---------|-------|------|
| Remove `_handle_msg` hook | `ramses_tx/engine.py` | ~418 | None — no overrides exist |
| Remove `_LegacyAddress`/`_LegacyMessage` | `parsers/decoder.py` | 57-140 | None — dead code |
| Remove legacy trace logger | `dev_registry.py`, `zones.py` | 41, 86 | None — unused |
| Remove paused `CentralDispatcher` | `pipeline/dispatcher.py` | 18-94 | None — never started |
| Remove paused `DecoderEngine` | `pipeline/decoder.py` | all | None — never activated |
| Remove paused `ReassemblyBuffer` | `pipeline/reassembly.py` | all | None — never activated |
| Remove "legacy parity" comments | multiple | scattered | None — cosmetic |
| Remove `lifecycle.py` pause comment | `lifecycle.py` | 123 | None — cosmetic |

### What's OUT of Scope (has dependents)

| Item | Why deferred | Dependency |
|------|-------------|------------|
| `to_legacy_dict()` methods (29+) | Still called by `payload_to_dict()` | ramses_cc dataclass migration |
| `shim_status` method | Still called by ramses_cc `sync_learned_topology` | ramses_cc CQRS state migration |
| Strangler fig translation | Still routes topology events | Needs TopologyBuilder to consume native Message format |
| Phase 3 `if False:` guard | Unclear if logic is ready | PWhite-Eng input needed |
| Async queue cutover | High risk — changes hot path | Separate phase (was Phase 2.99) |

### Implementation Plan

**Single PR, ~200-300 lines deleted, ~0 lines added.**

1. Remove dead code items from the "In Scope" table
2. Run full test suite (`pytest tests/` in ramses_rf)
3. Run ha_sim_test to verify no regressions
4. No ramses_cc changes needed — all removed code is internal

### Verification

- `pytest tests/tests_rf/` — all tests pass
- `pytest tests/tests_tx/` — all tests pass
- `ha_sim_test` — full suite passes (no behavior change expected)

---

<a id="strategy-pattern"></a>
## Strategy Pattern

**Goal:** Extract vendor-specific HVAC quirks from `quirks.py`
into strategy classes (`OrconStrategy`, `IthoStrategy`,
`NuaireStrategy`, `VascoStrategy`).  Each strategy owns its
vendor's behavior: fan mode maps, payload quirks, binding
codes, and classification heuristics.

**Risk:** LOW.  Pure refactor — same logic, different structure.
No behavior change.  All prerequisites already exist.

### Why Now

1. **quirks.py is growing** — 5 if-blocks today, every new
   vendor/model adds another.  Extraction is easiest now while
   there are only 5 blocks handling 3 codes.

2. **Bug 995** (Orcon Dutch fan mode names rejected) — exactly
   the kind of vendor-specific behavior the Strategy pattern
   fixes.  Currently `build_set_fan_mode` validates against
   `_22F1_SCHEMES[scheme]` which only has English names.

3. **DIS vs REM distinction** — multiple TODO comments reference
   the strategy pattern as the solution for distinguishing
   Orcon RF15 Display (DIS) from REM by 2411 frequency or
   DIS-only codes (1470/042F).

4. **Prerequisite for Phase 10** (command bus cutover) — each
   strategy owns its command handling, making the unified
   command bus cleaner.

5. **Prerequisite for multi-HGI** — different gateways may
   observe different codes from the same device; the strategy
   can accumulate evidence from multiple transports.

### Current State

**`quirks.py`** (179 lines, 5 if-blocks):
- `12A0` — Orcon/Ventura structural quirk (hvac_index mapping)
- `31DA` — humidity 0.0 → None normalization (all vendors)
- `31D9` — drop raw hex fan_mode values (all vendors)
- `31DA` — Itho-specific: prevent zero exhaust_fan_speed overwrite
- `31DA` — prevent fan_info overwrites with null markers (all vendors)

**`_scheme` attribute** — stored on `Device` (dev_base.py:112),
set from schema traits.  Used ad-hoc in:
- `hvac_ventilators.py:625` — `set_fan_mode()` defaults to "orcon"
- `hvac_remotes.py:73` — `initiate_binding_process()` checks for "nuaire"
- `hvac_remotes.py:107` — `set_fan_rate()` defaults to "orcon"
- `payloads/hvac.py:1628` — 22F1 payload includes `_scheme`
- `payloads/hvac.py:2028` — 31D9 payload hardcodes `"orcon"`

**`_22F1_SCHEMES`** — 4 vendor mode maps in
`protocol/ramses.py:904-909` and `models/hvac_schemas.py:57-62`:
- `itho`: off, trickle, low, medium, high
- `nuaire`: normal, boost, heater_off, heater_auto
- `orcon`: away, low, medium, high, auto, auto_alt, boost, off
- `vasco`: off, away, low, medium, high, auto

**`build_set_fan_mode`** — `commands/builders/hvac.py:171-248`,
takes `scheme` parameter, validates against `_22F1_SCHEMES`,
maps fan_mode to hex via scheme-specific mode map.

**`apply_hvac_quirks`** — called from 2 sites:
- `state_projector.py:432` — before hydrating HVAC state
- `pipeline/ingestion.py:670` — before processing HVAC packets

**`_classify`** — `discovery_scan.py:1314-1395`, classifies
devices by prefix + verb/code pairs.  Cannot distinguish DIS
from REM (both 37: prefix, same VC pairs).

### Architecture

```
HvacStrategy (abstract base)
├── OrconStrategy
├── IthoStrategy
├── NuaireStrategy
└── VascoStrategy
```

Each strategy implements:

```python
class HvacStrategy(Protocol):
    """Vendor-specific HVAC behavior."""

    scheme: str  # "orcon", "itho", "nuaire", "vasco"

    # --- Fan mode mapping ---
    def fan_mode_to_hex(self, fan_mode: str) -> str:
        """Map semantic fan mode name to hex code."""
        ...

    def hex_to_fan_mode(self, hex_code: str) -> str:
        """Map hex code to semantic fan mode name."""
        ...

    @property
    def mode_max(self) -> str:
        """Max mode byte for this scheme (e.g. '07' for orcon)."""
        ...

    @property
    def fan_modes(self) -> dict[str, str]:
        """All valid fan modes for this scheme."""
        ...

    # --- Payload quirks ---
    def apply_quirk(
        self, code: Code, payload: dict[str, Any], msg: Message
    ) -> dict[str, Any]:
        """Apply vendor-specific payload transformations."""
        ...

    # --- Binding ---
    def binding_codes(self) -> tuple[Code, ...]:
        """Codes to send during binding process."""
        ...

    # --- Classification ---
    @classmethod
    def matches(
        cls, device_id: str, codes_seen: list[str]
    ) -> bool:
        """Check if accumulated evidence matches this strategy."""
        ...
```

### Implementation Plan (3 Steps)

#### Step 1: Extract quirks.py into strategy classes

**PR 1 — pure refactor, no behavior change.**

Create `src/ramses_rf/strategies/` directory:

```
strategies/
├── __init__.py          # exports + best_hvac_strategy()
├── base.py              # HvacStrategy protocol
├── orcon.py             # OrconStrategy
├── itho.py              # IthoStrategy
├── nuaire.py            # NuaireStrategy
└── vasco.py             # VascoStrategy
```

**What moves where:**

| Current location | Moves to | What |
|-----------------|----------|------|
| `quirks.py:72-103` (12A0 Orcon) | `OrconStrategy.apply_quirk()` | hvac_index mapping |
| `quirks.py:111-115` (31DA humidity) | `HvacStrategy.apply_quirk()` (base) | All-vendor normalization |
| `quirks.py:133-140` (31D9 fan_mode) | `HvacStrategy.apply_quirk()` (base) | All-vendor normalization |
| `quirks.py:148-154` (31DA Itho) | `IthoStrategy.apply_quirk()` | Itho-specific guard |
| `quirks.py:162-176` (31DA fan_info) | `HvacStrategy.apply_quirk()` (base) | All-vendor guard |
| `protocol/ramses.py:867-902` (mode maps) | Each strategy's `fan_modes` | Vendor mode dicts |
| `models/hvac_schemas.py:18-23` (mode_max) | Each strategy's `mode_max` | Max mode bytes |
| `hvac_remotes.py:73` (nuaire binding) | `NuaireStrategy.binding_codes()` | Binding code selection |

**What stays:**
- `quirks.py` remains as a thin shim — `apply_hvac_quirks()`
  delegates to `strategy.apply_quirk()`.  This keeps the 2
  call sites (`state_projector.py:432`, `ingestion.py:670`)
  unchanged until Step 3.
- `_22F1_SCHEMES` dict stays in `protocol/ramses.py` for
  backward compat (imported by strategies).
- `build_set_fan_mode` stays unchanged — still takes `scheme`
  parameter, still looks up `_22F1_SCHEMES`.  Delegation to
  strategy happens in Step 3.

**Tests:**
- Move existing quirk tests to `tests/tests_rf/test_strategies/`
- Add tests for each strategy's `fan_mode_to_hex` / `hex_to_fan_mode`
- Add tests for `binding_codes()` per strategy
- Verify `apply_hvac_quirks()` still produces identical output

#### Step 2: Add `best_hvac_strategy()` parallel to `best_dev_role()`

**PR 2 — additive, new function, doesn't change existing path.**

```python
# strategies/__init__.py

def best_hvac_strategy(
    device_id: str,
    scheme: str | None = None,
    codes_seen: list[str] | None = None,
) -> HvacStrategy:
    """Select the best HVAC strategy for a device.

    Priority:
    1. Explicit scheme from schema (_scheme trait)
    2. Evidence-based: codes_seen matches a strategy's signature
    3. Default: OrconStrategy (most common)
    """
    if scheme:
        return _STRATEGY_BY_SCHEME[scheme]()
    if codes_seen:
        for strategy_cls in _STRATEGY_CLASSES:
            if strategy_cls.matches(device_id, codes_seen):
                return strategy_cls()
    return OrconStrategy()
```

**Evidence-based matching** (future, not in this PR):
- `OrconStrategy.matches()` — checks for 1470, 042F (Orcon-only codes)
- `IthoStrategy.matches()` — checks for Itho-specific 31DA patterns
- `NuaireStrategy.matches()` — checks for nuaire binding codes
- `VascoStrategy.matches()` — checks for vasco-specific codes

**Step 2 scope:** just the function + scheme-based selection.
Evidence-based matching is a TODO comment — implement when we
have real-world traffic samples to validate against.

**Tests:**
- `test_best_hvac_strategy_explicit_scheme()` — scheme="itho" → IthoStrategy
- `test_best_hvac_strategy_default()` — no scheme, no codes → OrconStrategy
- `test_best_hvac_strategy_invalid_scheme()` — scheme="bogus" → OrconStrategy (fallback)

#### Step 3: Add `device.set_strategy()` and wire it in

**PR 3 — wires the strategy into the device lifecycle.**

Changes:
1. `Device.set_strategy(strategy: HvacStrategy)` — sets `self._strategy`
2. `Device._get_strategy()` — returns `self._strategy` or
   `best_hvac_strategy(self.id, self._scheme)`
3. `hvac_ventilators.py:set_fan_mode()` — delegates to
   `self._get_strategy().fan_mode_to_hex(mode)` instead of
   `self._scheme or "orcon"` + `_22F1_SCHEMES` lookup
4. `hvac_remotes.py:initiate_binding_process()` — delegates to
   `self._get_strategy().binding_codes()` instead of
   `if self._scheme == "nuaire"` check
5. `build_set_fan_mode()` — accepts optional `strategy` param,
   delegates to `strategy.fan_mode_to_hex()` if provided,
   falls back to `_22F1_SCHEMES` lookup if not (backward compat)
6. `quirks.py:apply_hvac_quirks()` — delegates to
   `device._get_strategy().apply_quirk()` if device has a
   strategy, falls back to current logic if not

**What gets deleted:**
- `quirks.py` — fully replaced by strategy delegation
- `_22F1_SCHEMES` lookup in `build_set_fan_mode` — strategy owns it

**What stays:**
- `_22F1_SCHEMES` dict in `protocol/ramses.py` — imported by
  strategy classes, still used for schema validation
- `_scheme` attribute on Device — still set from schema, used
  by `best_hvac_strategy()` for selection

**Tests:**
- `test_set_fan_mode_delegates_to_strategy()` — verify strategy is used
- `test_set_strategy_overrides_scheme()` — explicit strategy wins
- `test_apply_quirks_delegates_to_strategy()` — verify quirks delegation
- Full ha_sim_test suite — no behavior change expected

### Bug 995 Fix (Orcon Dutch fan mode names)

**Can be done as part of Step 1 or as a separate small PR.**

Current: `build_set_fan_mode` validates `fan_mode` against
`_22F1_SCHEMES["orcon"]` which has English names only
(away, low, medium, high, auto, auto_alt, boost, off).

Fix: `OrconStrategy.fan_modes` includes Dutch aliases:
```python
{
    # English (canonical)
    "away": "00", "low": "01", "medium": "02", "high": "03",
    "auto": "04", "auto_alt": "05", "boost": "06", "off": "07",
    # Dutch (aliases, for bug 995)
    "afwezig": "00", "laag": "01", "medium": "02", "hoog": "03",
    "auto": "04", "boost": "06", "uit": "07",
}
```

The strategy's `fan_mode_to_hex()` checks both canonical and
alias names.  The canonical name is always the return value of
`hex_to_fan_mode()`.

### DIS vs REM Distinction (future, after Step 3)

Once strategies are wired in, `OrconStrategy.matches()` can
distinguish DIS from REM:

- **DIS (Orcon RF15 Display)** sends `RQ 2411` routinely
  (user interacts with the display)
- **REM** sends `RQ 2411` only when prompted by a VMI
- **DIS-only codes**: 1470, 042F (not sent by REM)

The strategy accumulates evidence (2411 frequency, presence of
DIS-only codes) and can override the device class.  This
replaces the TODO comments in `discovery_scan.py:1333-1340`,
`protocol/ramses.py:750-753`, and `hvac.py` HvacTopologyHandler.

**Out of scope for the initial 3-step plan** — needs real-world
traffic samples to validate the heuristics.  But the strategy
infrastructure makes this a clean addition, not a new tangle
of if-blocks.

---

<a id="parallelism-and-dependencies"></a>
## Parallelism and Dependencies

```
Wave 1 (now):
  Phase 7 (cleanup) ──────────────┐
  Strategy Step 1 (extract) ──────┤── all independent, parallel
  Strategy Step 2 (best_hvac) ────┤
  Bug 995 fix (Dutch names) ──────┘

Wave 2 (after Step 1):
  Strategy Step 3 (wire in) ────── depends on Step 1

After Wave 1+2:
  Phase 10 (command bus) ───────── depends on Strategy Step 3
  Multi-HGI ────────────────────── depends on Strategy + Phase 9 + 10.5
```

**Phase 7** and **Strategy Steps 1-2** touch completely
different code:
- Phase 7: `parsers/decoder.py`, `pipeline/dispatcher.py`,
  `ramses_tx/engine.py`, comments in `gateway.py`
- Strategy: new `strategies/` directory, `quirks.py`,
  `protocol/ramses.py` mode maps, `hvac_ventilators.py`,
  `hvac_remotes.py`

No merge conflicts expected.

### Internal Step Dependencies (Strategy)

| Step | Depends on | Can parallel with |
|------|-----------|-------------------|
| Step 1 (extract) | — | Phase 7, Bug 995 |
| Step 2 (best_hvac) | Step 1 (needs classes to exist) | Phase 7, Step 3 |
| Step 3 (wire in) | Step 1 (needs classes to exist) | Step 2 |

Step 1 is the prerequisite. Steps 2 and 3 are independent of
each other and can be done in parallel after Step 1.

---

<a id="risk-assessment"></a>
## Risk Assessment

| Work | Risk | Why |
|------|------|-----|
| Phase 7 | **Very low** | Only deletes dead/paused code. No behavior change. Full test suite verifies. |
| Strategy Step 1 | **Low** | Pure refactor — same logic, different structure. `apply_hvac_quirks()` output is identical. |
| Strategy Step 2 | **Very low** | Additive — new function, not called yet. |
| Strategy Step 3 | **Low-medium** | Changes `set_fan_mode()` and binding code paths. But delegation produces same output. ha_sim_test verifies. |
| Bug 995 fix | **Very low** | Adds aliases to a dict. No existing behavior changes. |

### Verification Strategy

1. **Unit tests** — move and expand quirk tests to strategy tests
2. **ha_sim_test** — full suite, no behavior change expected
3. **hass deployment** — verify on real hardware after each PR
4. **Comparison testing** — before/after `apply_hvac_quirks()` output
   must be identical for all existing test packets

### What Could Go Wrong

1. **Strategy selection picks wrong vendor** — if `_scheme` is
   not set in schema, `best_hvac_strategy()` defaults to
   OrconStrategy.  Mitigation: log a warning when falling back
   to default, and the user can set `_scheme` in the schema.

2. **Missing quirk** — if a quirk in `quirks.py` is
   vendor-specific but not clearly attributed (e.g. the 31DA
   humidity normalization could be Orcon-specific, not
   all-vendor).  Mitigation: keep the base class `apply_quirk()`
   conservative — only move clearly vendor-specific logic to
   strategy classes.  All-vendor normalizations stay in base.

3. **Phase 7 removes something still needed** — the paused
   async pipeline might be needed later.  Mitigation: keep
   `CentralDispatcher` if PWhite-Eng plans to activate it;
   only remove if confirmed dead.  The `to_legacy_dict()`
   methods and `shim_status` are explicitly out of scope.
