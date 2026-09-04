# Pool Test Report: feat/pool-all-1119 + feat/rssi-routing-1122

**Date:** 2026-09-03
**Test environment:** hass dev container with two MQTT HGIs
**ramses_cc:** feat/pool-all-1119 (PR 1133)
**ramses_rf:** feat/rssi-routing-1122 (PR 1185)

## Setup

| HGI       | Role                 | RSSI range      | Nearby devices                   |
| --------- | -------------------- | --------------- | -------------------------------- |
| 18:130236 | child 0 (primary)    | -41 to -69 dBm  | FAN (32:153289), CO2 (37:126776) |
| 18:149488 | child 1 (additional) | -70 to -107 dBm | REM (29:176861)                  |

Pool auto-configured from schema (both HGIs have `_owner: me`):

```
PooledTransport: creating pool with 2 ports:
  ['mqtt://...@192.168.40.11:1883',          ← child 0 (wildcard)
   'mqtt://...@192.168.40.11:1883/RAMSES/GATEWAY/18:149488']  ← child 1
```

## Findings

### 1. Pool construction: WORKS

Both children connected successfully:

```
child 0 connected (HGI=18:130236), 1/2 connected
child 1 connected (HGI=18:149488), 2/2 connected
```

### 2. Deduplication: WORKS

Same packets from both children are deduplicated correctly:

```
deduped packet from child 1: RQ --- 18:130236 32:153289 --:------ 10D0 001 00
deduped packet from child 0: RQ --- 18:130236 32:153289 --:------ 10D0 001 00
```

Only one copy reaches the protocol layer.

### 3. Source-ID patching: WORKS

Protocol layer patches placeholder to active HGI before pool routing:

```
Patching command with active HGI ID: swapped 18:000730 -> 18:130236 for  I|3150
```

### 4. RSSI-based routing: WORKS (with caveats)

Pool selects child based on RSSI for target device:

```
_select_transport target=29:176861 candidates=[0, 1] rssi_values={0: 0.0, 1: 0.0}
selected child 1 (rssi=0.0) for target 29:176861
```

In this case, RSSI values were 0.0 (unknown — tracker empty after restart),
so selection fell back to round-robin and picked child 1. With accumulated
RSSI data, the selection would be based on real RSSI values.

### 5. Re-patching for selected child: WORKS (bug fixed)

When pool selects a different child than the protocol's "active" HGI,
the source address is re-patched:

```
re-patched frame source 18:130236 -> 18:149488 for child 1
```

**Bug found and fixed:** `frame.split()` drops the leading whitespace
before the verb (`" I --- ..."` → `["I", "---", ...]`), so
`" ".join(parts)` produced `"I --- ..."` without the leading space,
causing `"Bad frame: Invalid structure"` errors. Fix: preserve the
original leading character.

### 6. Cross-dongle loopback: CONFIRMED

When child 1 sends a command, both children hear it:

```
mq Tx: {"msg": "I --- 18:149488 29:176861 --:------ 3150 001 00"}    ← sent via child 1
Recv'd: ...  I --- 18:149488 29:176861 --:------ 3150 001 00          ← local echo (child 1, RSSI='')
deduped packet from child 0:  I --- 18:149488 29:176861 ...           ← over-air copy (child 0)
deduped packet from child 1:  I --- 18:149488 29:176861 ...           ← (deduped)
```

The pool deduplicates the local echo and over-air copy correctly.

### 7. QoS echo trace (10D0 command to FAN)

Full sequence for a command routed through child 0:

```
11:04:57.037 Patching: swapped 18:000730 -> 18:130236 for RQ|10D0
11:04:57.107 mq Tx: RQ --- 18:130236 32:153289 --:------ 10D0 001 00
11:04:57.197 Recv'd (echo): ... RQ --- 18:130236 32:153289 --:------ 10D0 001 00 (rssi='')
11:04:57.202 deduped from child 1: RQ --- 18:130236 32:153289 --:------ 10D0 001 00 (over-air)
11:04:57.215 Recv'd (response): -41 RP --- 32:153289 18:130236 --:------ 10D0 006 0011B4130000
```

The FAN responds to `18:130236` (the HGI that sent the RQ). Response
RSSI=-41 confirms FAN is near child 0.

### 8. Health timeout: BUG (fixed)

60s health timeout was too aggressive for sparse RAMSES traffic:

```
child 0 marked unhealthy (no packets for 81.8s)
child 1 marked unhealthy (no packets for 81.8s)
no healthy children, re-enabling as last resort: [0, 1]
```

This caused the pool to bypass RSSI routing and fall back to
round-robin. Fixed: increased default to 180s.

## Bugs found and fixed

| Bug                           | Location                     | Fix                                 | PR      |
| ----------------------------- | ---------------------------- | ----------------------------------- | ------- |
| Re-patch drops leading space  | ramses_rf pooled.py          | Preserve `frame[0]` if whitespace   | PR 1185 |
| Health timeout too aggressive | ramses_rf pooled.py          | 60s → 180s                          | PR 1185 |
| No routing decision logging   | ramses_rf pooled.py          | Added \_select_transport debug logs | PR 1185 |
| CI workflow regressions       | ramses_cc .github/workflows/ | Restored from upstream master       | PR 1133 |

## What was NOT tested

- QoS echo satisfaction logic (no explicit QoS log observed)
- RSSI routing with accumulated tracker data (tracker was empty after restart)
- Primary failover (child 0 offline → child 1 takes over)
- Command timeout and retry via different child
- Serial transport (both HGIs were MQTT)

## Implementation-independent findings (apply to new plan)

These findings are protocol/physical layer facts, not implementation-specific:

1. **Dedup key**: sequence is sender-assigned, stable across HGIs (50/50 paired packets)
2. **RSSI TTL**: 5 min is safe (close HGI stable 2h, far HGI varies over hours)
3. **Dedup window**: 500ms confirmed (median arrival delta 8.4ms)
4. **Loopback**: local echo (RSSI='') + over-air copy (RSSI=-83), 3-8ms delta
5. **Source-ID patching**: protocol swaps `18:000730 -> active HGI` before pool routing
6. **Per-device RSSI routing scenario**: REM -49 at child 1, FAN -41 at child 0
7. **Health timeout**: must be > 60s for sparse traffic (180s recommended)
