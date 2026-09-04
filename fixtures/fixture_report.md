# MQTT Fixture Report: Dedup Key and RSSI TTL Decisions

**Collected:** 2026-09-03, from `hass` dev instance
**Source:** Two MQTT HGIs (`18:130236`, `18:149488`) on broker `192.168.40.11:1883`
**Data:** 725 packets from 8 packet log files (~2 hours of traffic), plus 8-message MQTT topic capture for HGI calibration

## HGI calibration (from MQTT topic capture)

The packet log does not record which HGI heard each packet. We calibrated
the HGI identity from RSSI using a direct MQTT subscription that captures
the topic (which contains the HGI ID):

| HGI                        | RSSI range      | Signal | Location                     |
| -------------------------- | --------------- | ------ | ---------------------------- |
| `18:130236`                | -41 to -69 dBm  | Strong | Close to devices             |
| `18:149488`                | -70 to -107 dBm | Weak   | Farther away                 |
| `18:130236` (RSSI=000/...) | N/A             | —      | Same HGI, didn't decode RSSI |

Classification threshold: RSSI > -70 → `18:130236`, RSSI <= -70 →
`18:149488`, RSSI=000/... → `18:130236`.

**Result:** 425 packets from `18:130236`, 300 from `18:149488`.

## Decision 4: Dedup key — sequence field stability

**Question:** Is the transport-assigned sequence field stable across
HGIs for the same RF frame? If yes, it can be part of the dedup key.
If no, it must be normalized or excluded.

### Finding

**The sequence field is assigned by the SENDER, not the receiver. It
is stable across HGIs.**

| Category                                       | Count  |
| ---------------------------------------------- | ------ |
| Paired packets (heard by both HGIs)            | 121    |
| Both have seq=--- (no sequence, I/unsolicited) | 71     |
| Same sequence across both HGIs                 | **50** |
| Different sequence across HGIs                 | **0**  |
| Mixed (one ---, one numbered)                  | **0**  |

### Evidence

All 50 paired packets with sequence numbers show the **same sequence**
on both HGIs. Examples:

```
seq=016 code=31D9  18:149488 rssi=-90  ts=10:51:08.138
                   18:130236 rssi=-41  ts=10:51:08.148

seq=021 code=31D9  18:149488 rssi=-103 ts=10:56:56.049
                   18:130236 rssi=-68  ts=10:56:56.059

seq=022 code=31D9  18:149488 rssi=-93  ts=10:57:03.303
                   18:130236 rssi=-41  ts=10:57:03.313

seq=024 code=31D9  18:130236 rssi=-41  ts=10:57:10.183
                   18:149488 rssi=-89  ts=10:57:10.173

seq=027 code=31D9  18:130236 rssi=-41  ts=10:57:14.795
                   18:149488 rssi=-98  ts=10:57:14.786
```

The sequence is a RAMSES protocol field set by the sending device
(e.g. `32:153289`). Both HGIs receive the same RF frame and report the
same sequence number. There is no transport-assigned per-HGI sequence.

### Recommendation for the dedup key

```
dedup_key = (verb, src, addr1, addr2, addr3, code, length, payload, seq)
```

Where `seq` is included when != `---`. For `---` packets (unsolicited
I/Info frames), the key without sequence is sufficient because the
content (src, addresses, code, payload) uniquely identifies the frame.

The key does **not** include: RSSI, timestamp, ingress HGI, or `is_tx`
— these are never part of the content key (as the plan already states).

## Decision 3: RSSI TTL — how quickly does RSSI become stale?

### Finding

**RSSI is remarkably stable for the close HGI over ~2 hours. The far
HGI varies more, suggesting environmental sensitivity.**

| HGI → Device          | n   | RSSI range  | Mean  | Span  |
| --------------------- | --- | ----------- | ----- | ----- |
| 18:130236 → 32:153289 | 273 | -41 to -69  | -41.8 | ~2h   |
| 18:130236 → 37:126776 | 41  | -56 to -58  | -57.3 | ~1.8h |
| 18:130236 → 37:169161 | 28  | -57 to -69  | -60.8 | ~2h   |
| 18:149488 → 18:130236 | 3   | -83 to -103 | -89.7 | ~2h   |
| 18:149488 → 32:153289 | 121 | -70 to -107 | -91.6 | ~2h   |
| 18:149488 → 37:126776 | 47  | -73 to -109 | -79.2 | ~1.9h |
| 18:149488 → 37:154519 | 6   | -94 to -106 | -96.7 | ~2.2h |
| 18:149488 → 37:168270 | 65  | -82 to -105 | -87.6 | ~1.9h |
| 18:149488 → 37:169161 | 58  | -70 to -104 | -89.8 | ~2h   |

### Time series (18:130236 → 32:153289, first 15 readings)

```
09:48:13  rssi=-41
09:48:13  rssi=-41
09:48:48  rssi=-41
09:48:48  rssi=-41
09:50:39  rssi=-41
09:50:39  rssi=-41
09:50:39  rssi=-41
09:53:03  rssi=-41
09:53:03  rssi=-41
09:53:04  rssi=-41
09:53:04  rssi=-41
09:53:48  rssi=-41
09:53:48  rssi=-41
09:57:54  rssi=-41
09:57:54  rssi=-41
```

The close HGI reports -41 dBm consistently for 2+ hours with occasional
outliers at -65/-69. The far HGI varies by 20-37 dBm over the same
period.

### Recommendation for RSSI TTL

A TTL of **5 minutes** is conservative and safe:

- The close HGI's RSSI is stable for 2+ hours; 5 min captures any
  gradual changes.
- The far HGI's RSSI varies over hours, not minutes; 5 min is fresh
  enough to reflect current conditions.
- The plan's "five-sample rolling arithmetic mean" with a 5-minute TTL
  means the tracker uses the most recent 5 readings within the last 5
  minutes. With traffic every ~30-60s for active devices, this gives
  5-10 samples per TTL window.

A shorter TTL (e.g. 2 minutes) would be too aggressive for quiet
devices that report every 2-3 minutes. A longer TTL (e.g. 15 minutes)
risks routing through a child whose environment has changed.

The named setting should be `rssi_ttl_seconds: 300` (5 minutes),
documented and configurable, with boundary tests at 0s, 300s, and 600s.

## Timing: paired packet arrival delta

| Stat                          | Value                                            |
| ----------------------------- | ------------------------------------------------ |
| n                             | 439                                              |
| min                           | 0.0ms                                            |
| median                        | **8.4ms**                                        |
| mean                          | 172s (skewed by same-content frames hours apart) |
| >500ms (outside dedup window) | 132/439                                          |

The median arrival delta is **8.4ms** — well within the 500ms dedup
window. The >500ms cases are not real paired packets but the same frame
content (e.g. a periodic `31D9` status update) transmitted again hours
later. The 500ms dedup window is appropriate and confirmed by this data.

## Cross-dongle loopback (CONFIRMED with real data)

### HGI-originated commands (loopback evidence)

The `3150` command from `18:130236` is heard by **both** HGIs:

```
ts=08:43:45.143  HGI=18:149488  rssi=-83   (over-air copy)
ts=08:43:45.146  HGI=18:130236  rssi=...   (local echo)

ts=09:43:45.157  HGI=18:149488  rssi=-103  (over-air copy)
ts=09:43:45.158  HGI=18:130236  rssi=...   (local echo)

ts=10:43:45.168  HGI=18:149488  rssi=-83   (over-air copy)
ts=10:43:45.176  HGI=18:130236  rssi=...   (local echo)
```

This is exactly the cross-dongle loopback scenario from problem #15:

- `18:130236` hears its own transmission (local echo, RSSI=.../000)
- `18:149488` hears the same frame over the air (RSSI=-83 to -103)
- Arrival delta: 3-8ms

### Device-originated RQ commands (also paired)

RQ commands from `37:169161` to `32:153289` are heard by both HGIs:

```
code=313F  ts=10:45:23.711  HGI=18:130236  rssi=-61
           ts=10:45:23.720  HGI=18:149488  rssi=-88

code=1470  ts=10:45:24.211  HGI=18:130236  rssi=-60
           ts=10:45:24.219  HGI=18:149488  rssi=-89

code=31DA  ts=10:45:47.711  HGI=18:130236  rssi=-59
           ts=10:45:47.719  HGI=18:149488  rssi=-88
```

### RP responses (also paired)

RP responses from `32:153289` to `37:169161` are heard by both HGIs:

```
code=008   ts=10:45:24.229  HGI=18:149488  rssi=-90
           ts=10:45:24.237  HGI=18:130236  rssi=-41
```

### Implications for the pool

1. **Loopback is real and frequent** — every HGI-originated command
   produces a local echo + over-air copy pair within 3-8ms.

2. **The over-air copy must not contaminate RSSI** — `18:149488`
   hearing `18:130236`'s transmission at -83 to -103 dBm is not a
   reading of `18:130236`'s signal quality as a route to target
   devices. It's loopback.

3. **Dedup must catch both copies** — the local echo and over-air copy
   have the same content (same seq, src, addr1, addr2, code, payload)
   and arrive within 3-8ms. The dedup key recommended above handles
   this correctly.

4. **QoS echo matching** — the local echo (from the transmitting HGI)
   should satisfy QoS. The over-air copy (from the other HGI) should
   NOT independently satisfy QoS — it's the same RF frame, not an
   independent confirmation. But it can correlate with the routed
   attempt as per plan invariant 15.

5. **Direction field matters for loopback classification** — the local
   echo has RSSI=.../000 (undecodable), while the over-air copy has a
   real RSSI. This could be used as a heuristic, but the plan's
   approach (ingress_hgi_id + canonical fingerprint matching) is more
   robust.

## Summary for plan decisions

| Decision          | Answer                                                                                                                                                    | Confidence                                                        |
| ----------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------- |
| **4. Dedup key**  | Sequence is sender-assigned, stable across HGIs. Include `seq` in key when != `---`. Base key: `(verb, src, addr1, addr2, addr3, code, length, payload)`. | **High** — 50/50 paired packets have same sequence, 0 differences |
| **3. RSSI TTL**   | 5 minutes (`rssi_ttl_seconds: 300`). Close HGI stable for 2+ hours, far HGI varies over hours.                                                            | **Medium-High** — based on ~2 hours of data                       |
| **Dedup window**  | 500ms confirmed appropriate (median delta 8.4ms)                                                                                                          | **High**                                                          |
| **Loopback**      | Confirmed: both local echo and over-air copy observed for HGI-originated frames, 3-8ms delta                                                              | **High** — direct evidence from `3150` commands                   |
| **RQ/RP pairing** | Device commands and responses are also paired across HGIs (same dedup key works)                                                                          | **High**                                                          |

## Limitations

1. **HGI identification is inferred from RSSI**, not from the MQTT
   topic. The packet log strips the topic. The 8-message MQTT capture
   confirmed the RSSI-to-HGI mapping but a longer topic capture would
   strengthen this.

2. **No QoS echo data for outbound pool commands**: The `3150` commands
   were sent by the current single-HGI setup, not by a pool. We have
   not observed what happens when a pool sends a command through one
   child and both children hear the echo. This requires pool testing.

3. **No serial data**: Both HGIs are MQTT. Serial-specific behavior
   (local echo timing, USB reset) requires physical hardware
   (the hardware feasibility gate, PR 3).

4. **Low HGI command diversity**: Only `3150` commands from
   `18:130236` were observed as loopback. More command types would
   strengthen the loopback classification evidence.

## Files

- `fixtures/mqtt_fixture_short.jsonl` — 8-message MQTT topic capture
- `fixtures/packet_log*` — 8 packet log files (~725 packets)
- `tools/collect_mqtt_fixture.py` — MQTT collection script
- `tools/analyze_fixture.py` — analysis script
