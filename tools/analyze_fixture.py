#!/usr/bin/env python3
"""Analyze packet logs for dedup key and RSSI TTL decisions.

Log line format (10 whitespace-separated fields):
    ts rssi verb seq addr1 addr2 addr3 code len payload

Where addr1 is the source, addr2 is the destination, addr3 is the
third address slot (often --:------).

The packet log does not record which HGI heard each packet.  We infer
it from RSSI using calibration from the MQTT topic capture:
  - RSSI -41 to -69  → 18:130236 (close to devices, strong signal)
  - RSSI -70 to -120 → 18:149488 (farther, weaker signal)
  - RSSI "..." or 000 → 18:130236 (didn't decode RSSI for this packet)

If an MQTT fixture (mqtt_paired_raw.jsonl or mqtt_fixture_short.jsonl)
is available, it is preferred because it carries the HGI ID in the
topic — no RSSI inference is needed.
"""

import json
import re
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures"

# Packet log line format (10 fields):
#   2026-09-03T09:48:13.864675 -83  I --- 37:168270 32:153289 --:------ 22F1 003 000107
# Fields: ts rssi verb seq addr1 addr2 addr3 code len payload
LINE_RE = re.compile(
    r"^(\S+)\s+"  # 1: timestamp
    r"(\S+)\s+"  # 2: RSSI (-83, ..., 000, ...)
    r"(\S+)\s+"  # 3: verb/direction (I, RQ, RP, W)
    r"(\S+)\s+"  # 4: seq (---, 220, etc)
    r"(\S+)\s+"  # 5: addr1 (source)
    r"(\S+)\s+"  # 6: addr2 (destination)
    r"(\S+)\s+"  # 7: addr3
    r"([0-9A-F]{4})\s+"  # 8: code
    r"([0-9A-F]{3})\s+"  # 9: length
    r"(.*)$"  # 10: payload
)

# Pool HGI set for loopback detection
POOL_HGIS = {"18:130236", "18:149488"}

# Maximum window for pairing the same frame content across HGIs (seconds).
# Packets with identical content arriving more than this apart are treated
# as independent transmissions, not cross-HGI duplicates of one RF frame.
PAIR_WINDOW_S = 5.0


def classify_hgi(rssi_str: str) -> str:
    """Infer which HGI heard this packet from RSSI.

    From MQTT fixture calibration:
      18:130236 reports: -41, -57, -41, 000  (strong, close)
      18:149488 reports: -78, -98             (weak, farther)
    Threshold: RSSI > -70 (i.e. -41 to -69) → 18:130236
               RSSI <= -70 (i.e. -70 to -120) → 18:149488
    """
    if rssi_str in ("...", "000"):
        return "18:130236"  # 18:130236 sometimes reports 000/...
    try:
        rssi = int(rssi_str)  # already negative, e.g. -83
        if rssi > -70:
            return "18:130236"
        return "18:149488"
    except ValueError:
        return "unknown"


def parse_rssi(rssi_str: str, *, negate: bool = False) -> int | None:
    """Parse RSSI string to a negative integer (dBm).

    Packet log values are already negative (e.g. -83, -41).
    MQTT msg values are positive and need negation (e.g. 078 → -78).
    Set ``negate=True`` for MQTT msg format.

    Returns None for sentinels (... or 000) or unparsable values.
    """
    if rssi_str in ("...", "000"):
        return None
    try:
        val = int(rssi_str)
        return -val if negate and val > 0 else val
    except ValueError:
        return None


def parse_log(filepath: Path) -> list[dict]:
    """Parse a packet log file into a list of packet dicts."""
    packets: list[dict] = []
    with open(filepath) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            m = LINE_RE.match(line)
            if not m:
                continue
            ts_str, rssi_str, verb, seq, addr1, addr2, addr3, code, length, payload = (
                m.groups()
            )
            rssi = parse_rssi(rssi_str)
            hgi_id = classify_hgi(rssi_str)
            # Content key: everything except RSSI and timestamp.
            # verb is RX-side metadata, not part of RF frame content, but
            # we keep it in the key because I/RQ/RP/W distinguishes frame
            # roles that share the same addresses and code.
            content = f"{verb} {seq} {addr1} {addr2} {addr3} {code} {length} {payload}"
            packets.append(
                {
                    "ts_str": ts_str,
                    "ts": _parse_ts(ts_str),
                    "rssi_str": rssi_str,
                    "rssi": rssi,
                    "verb": verb,
                    "seq": seq,
                    "src": addr1,
                    "addr1": addr1,
                    "addr2": addr2,
                    "addr3": addr3,
                    "code": code,
                    "length": length,
                    "payload": payload,
                    "hgi_id": hgi_id,
                    "content": content,
                    "file": filepath.name,
                }
            )
    return packets


def _parse_ts(ts_str: str) -> datetime | None:
    """Parse an ISO-format timestamp, returning None on failure."""
    try:
        return datetime.fromisoformat(ts_str)
    except ValueError, TypeError:
        return None


def parse_mqtt_fixture(filepath: Path) -> list[dict]:
    """Parse an MQTT JSONL fixture (preferred — has topic-derived HGI ID)."""
    packets: list[dict] = []
    with open(filepath) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            hgi_id = entry.get("hgi_id")
            msg_text = entry.get("payload", {}).get("msg", "")
            if not hgi_id or not msg_text:
                continue
            parts = msg_text.split()
            if len(parts) < 9:
                continue
            # msg format: RSSI verb seq addr1 addr2 addr3 code len payload
            rssi_str = parts[0]
            verb = parts[1]
            seq = parts[2]
            addr1 = parts[3]
            addr2 = parts[4]
            addr3 = parts[5]
            code = parts[6]
            length = parts[7]
            payload = " ".join(parts[8:])
            ts_str = entry.get("payload", {}).get("ts", entry.get("ts_capture", ""))
            rssi = parse_rssi(rssi_str, negate=True)  # MQTT msg uses positive RSSI
            content = f"{verb} {seq} {addr1} {addr2} {addr3} {code} {length} {payload}"
            packets.append(
                {
                    "ts_str": ts_str,
                    "ts": _parse_ts(ts_str),
                    "rssi_str": rssi_str,
                    "rssi": rssi,
                    "verb": verb,
                    "seq": seq,
                    "src": addr1,
                    "addr1": addr1,
                    "addr2": addr2,
                    "addr3": addr3,
                    "code": code,
                    "length": length,
                    "payload": payload,
                    "hgi_id": hgi_id,  # from topic — no RSSI inference
                    "content": content,
                    "file": filepath.name,
                }
            )
    return packets


def load_all_packets() -> tuple[list[dict], str]:
    """Load packets for analysis.

    The MQTT fixture (mqtt_fixture_short.jsonl) is a small calibration
    capture (~8 packets) used to validate RSSI-to-HGI thresholds.  The
    packet logs (packet_log.log*) contain the bulk of the data (~700+
    packets over ~2 hours) but do not record which HGI heard each frame
    — HGI identity is inferred from RSSI using the calibration.

    Returns (packets, source_label) where source_label is "packet_log".
    """
    # Always use packet logs for the main analysis — they have the data volume
    # needed for dedup/timing/RSSI-TTL statistics.
    all_packets: list[dict] = []
    # Sort so that .log.N (older) comes before .log (newest):
    # reverse-lexicographic order gives .log.7, .log.6, ..., .log.1, .log
    for f in sorted(
        FIXTURE_DIR.glob("packet_log*"), key=lambda p: p.name, reverse=True
    ):
        all_packets.extend(parse_log(f))

    # Sort by timestamp to ensure chronological order across rotated files
    all_packets.sort(key=lambda p: p["ts"] or datetime.min)
    return all_packets, "packet_log"


def pair_within_window(
    packets: list[dict], window_s: float = PAIR_WINDOW_S
) -> dict[str, list[dict]]:
    """Group packets by content, keep those arriving within window_s.

    This avoids pairing identical frames that are hours apart
    (independent retransmissions) as cross-HGI duplicates of one RF
    frame.
    """
    by_content: dict[str, list[dict]] = defaultdict(list)
    for p in packets:
        by_content[p["content"]].append(p)

    paired: dict[str, list[dict]] = {}
    for content, msgs in by_content.items():
        if len(msgs) < 2:
            continue
        # Sort by timestamp
        msgs_sorted = sorted(msgs, key=lambda x: x["ts"] or datetime.min)
        # Sliding window: group messages within window_s of each other
        groups: list[list[dict]] = []
        current: list[dict] = [msgs_sorted[0]]
        for m in msgs_sorted[1:]:
            prev_ts = current[-1]["ts"]
            cur_ts = m["ts"]
            if prev_ts and cur_ts and (cur_ts - prev_ts).total_seconds() <= window_s:
                current.append(m)
            else:
                groups.append(current)
                current = [m]
        groups.append(current)
        # Keep groups with 2+ distinct HGIs
        for g in groups:
            if len({x["hgi_id"] for x in g}) >= 2:
                paired[content] = g
                break
    return paired


def main() -> None:
    all_packets, source = load_all_packets()
    print(f"Source: {source}")
    print(f"Total packets: {len(all_packets)}")

    # HGI distribution
    hgi_counts: dict[str, int] = defaultdict(int)
    for p in all_packets:
        hgi_counts[p["hgi_id"]] += 1
    label = "topic-derived" if source == "mqtt" else "RSSI-inferred"
    print(f"\nHGI distribution ({label}):")
    for hgi, count in sorted(hgi_counts.items()):
        print(f"  {hgi}: {count}")

    # Group by content
    by_content: dict[str, list[dict]] = defaultdict(list)
    for p in all_packets:
        by_content[p["content"]].append(p)

    # Paired using windowed approach
    paired = pair_within_window(all_packets)
    single = {k: v for k, v in by_content.items() if k not in paired}

    print(f"\nUnique frame contents: {len(by_content)}")
    print(f"Paired (2+ HGIs within {PAIR_WINDOW_S}s): {len(paired)}")
    print(f"Single-HGI only: {len(single)}")

    # === DEDUP KEY ANALYSIS ===
    print(f"\n{'=' * 60}")
    print("DEDUP KEY ANALYSIS: Sequence field stability")
    print(f"{'=' * 60}")

    seq_same = 0
    seq_diff = 0
    seq_no_seq = 0
    seq_mixed = 0

    for content, msgs in paired.items():
        seqs = [m["seq"] for m in msgs]
        unique_seqs = set(seqs)
        if all(s == "---" for s in seqs):
            seq_no_seq += 1
        elif "---" in unique_seqs and len(unique_seqs) > 1:
            seq_mixed += 1
        elif len(unique_seqs) == 1:
            seq_same += 1
        else:
            seq_diff += 1

    print(f"Paired packets: {len(paired)}")
    print(f"  Both have seq=--- (no sequence): {seq_no_seq}")
    print(f"  Same sequence across HGIs: {seq_same}")
    print(f"  Different sequence across HGIs: {seq_diff}")
    print(f"  Mixed (one ---, one numbered): {seq_mixed}")

    if seq_diff > 0:
        print("\n  *** DIFFERENT sequences found! ***")
        for content, msgs in paired.items():
            seqs = [m["seq"] for m in msgs]
            if len(set(seqs)) > 1 and "---" not in set(seqs):
                print(f"  content: {content[:80]}")
                for m in msgs:
                    print(f"    HGI={m['hgi_id']} seq={m['seq']} rssi={m['rssi']}")

    if seq_same > 0:
        print("\n  Examples with SAME sequence:")
        shown = 0
        for content, msgs in paired.items():
            seqs = [m["seq"] for m in msgs]
            if len(set(seqs)) == 1 and seqs[0] != "---":
                print(
                    f"  seq={seqs[0]} code={msgs[0]['code']} "
                    f"src={msgs[0]['src']} addr2={msgs[0]['addr2']}"
                )
                for m in sorted(msgs, key=lambda x: x["ts"] or datetime.min):
                    ts_short = m["ts_str"][11:23] if m["ts_str"] else "?"
                    print(f"    HGI={m['hgi_id']} rssi={m['rssi']} ts={ts_short}")
                shown += 1
                if shown >= 10:
                    break

    # === TIMING ANALYSIS (windowed nearest-neighbor) ===
    print(f"\n{'=' * 60}")
    print(
        f"TIMING ANALYSIS: Paired packet arrival delta (within {PAIR_WINDOW_S}s window)"
    )
    print(f"{'=' * 60}")

    deltas: list[float] = []
    for content, msgs in paired.items():
        if len(msgs) < 2:
            continue
        ts_list = sorted([m["ts"] for m in msgs if m["ts"]])
        for i in range(1, len(ts_list)):
            delta_ms = (ts_list[i] - ts_list[i - 1]).total_seconds() * 1000
            deltas.append(delta_ms)

    if deltas:
        deltas.sort()
        n = len(deltas)
        print(f"Arrival deltas: n={n}")
        print(f"  min={deltas[0]:.1f}ms")
        print(f"  max={deltas[-1]:.1f}ms")
        print(f"  mean={sum(deltas) / n:.1f}ms")
        print(f"  median={deltas[n // 2]:.1f}ms")
        print(f"  p95={deltas[int(n * 0.95)]:.1f}ms")
        print(
            f"  >500ms (outside dedup window): {sum(1 for d in deltas if d > 500)}/{n}"
        )
    else:
        print("No timing data available.")

    # === RSSI TTL ANALYSIS ===
    print(f"\n{'=' * 60}")
    print("RSSI TTL ANALYSIS: RSSI variation over time per HGI per device")
    print(f"{'=' * 60}")

    rssi_readings: dict[tuple[str, str], list[tuple[datetime, int]]] = defaultdict(list)
    for p in all_packets:
        if p["rssi"] is not None and p["src"] != "--:------":
            if p["ts"]:
                rssi_readings[(p["hgi_id"], p["src"])].append((p["ts"], p["rssi"]))

    print("\nRSSI readings by (HGI, device):")
    for (hgi, device), readings in sorted(rssi_readings.items()):
        if len(readings) < 3:
            continue
        # Sort by timestamp (already sorted globally, but be safe)
        readings.sort(key=lambda x: x[0])
        rssi_values = [r[1] for r in readings]
        t_first = readings[0][0]
        t_last = readings[-1][0]
        span_s = (t_last - t_first).total_seconds()

        print(
            f"  {hgi} → {device}: n={len(readings)} "
            f"rssi=[{min(rssi_values)}..{max(rssi_values)}] "
            f"mean={sum(rssi_values) / len(rssi_values):.1f} "
            f"span={span_s:.0f}s"
        )

        if len(readings) >= 5 and span_s > 60:
            print("    time series (first 15):")
            for ts, rssi in readings[:15]:
                print(f"      {ts.strftime('%H:%M:%S.%f')[:-3]} rssi={rssi}")

    # === CROSS-DONGLE LOOPBACK ANALYSIS ===
    print(f"\n{'=' * 60}")
    print("CROSS-DONGLE LOOPBACK: packets where src (addr1) is an active pool HGI")
    print(f"{'=' * 60}")

    loopback = [p for p in all_packets if p["src"] in POOL_HGIS]
    print(f"Packets with src in pool HGIs: {len(loopback)}")
    if loopback:
        print(
            "  (These are either local echoes or over-air copies of HGI transmissions)"
        )
        loopback_by_content: dict[str, list[dict]] = defaultdict(list)
        for p in loopback:
            loopback_by_content[p["content"]].append(p)
        paired_loopback = pair_within_window(loopback)
        print(
            f"  Paired loopback (2+ HGIs within {PAIR_WINDOW_S}s): "
            f"{len(paired_loopback)}"
        )
        for p in loopback[:15]:
            ts_short = p["ts_str"][11:23] if p["ts_str"] else "?"
            print(
                f"  {ts_short} hgi={p['hgi_id']} verb={p['verb']} "
                f"src={p['src']} code={p['code']} rssi={p['rssi']} seq={p['seq']}"
            )
        if paired_loopback:
            print("\n  Paired loopback examples:")
            for content, msgs in list(paired_loopback.items())[:5]:
                print(f"    content: {content[:70]}")
                for m in sorted(msgs, key=lambda x: x["ts"] or datetime.min):
                    ts_short = m["ts_str"][11:23] if m["ts_str"] else "?"
                    print(
                        f"      HGI={m['hgi_id']} verb={m['verb']}"
                        f" rssi={m['rssi']} ts={ts_short}"
                    )

    # === OUTBOUND COMMAND ANALYSIS ===
    print(f"\n{'=' * 60}")
    print("OUTBOUND COMMANDS: RQ/W packets (sent by HGI)")
    print(f"{'=' * 60}")

    outbound = [p for p in all_packets if p["verb"] in ("RQ", "W")]
    print(f"Outbound packets (RQ/W): {len(outbound)}")
    outbound_by_hgi: dict[str, list[dict]] = defaultdict(list)
    for p in outbound:
        outbound_by_hgi[p["src"]].append(p)
    for hgi, msgs in sorted(outbound_by_hgi.items()):
        print(f"  {hgi}: {len(msgs)} outbound packets")
        paired_out = pair_within_window(msgs)
        print(f"    paired (heard by 2+ HGIs as loopback): {len(paired_out)}")

    # === RESPONSE ANALYSIS ===
    print(f"\n{'=' * 60}")
    print("RESPONSES: RP packets (device responses to HGI commands)")
    print(f"{'=' * 60}")

    responses = [p for p in all_packets if p["verb"] == "RP"]
    print(f"Response packets (RP): {len(responses)}")
    resp_by_content: dict[str, list[dict]] = defaultdict(list)
    for p in responses:
        resp_by_content[p["content"]].append(p)
    paired_resp = pair_within_window(responses)
    print(f"  Paired responses (heard by 2+ HGIs): {len(paired_resp)}")
    if paired_resp:
        print("  Examples:")
        for content, msgs in paired_resp.items():
            m0 = msgs[0]
            print(f"    code={m0['code']} src={m0['src']} addr2={m0['addr2']}")
            for m in sorted(msgs, key=lambda x: x["ts"] or datetime.min):
                ts_short = m["ts_str"][11:23] if m["ts_str"] else "?"
                print(f"      HGI={m['hgi_id']} rssi={m['rssi']} ts={ts_short}")
            break

    # === SUMMARY FOR PLAN DECISIONS ===
    print(f"\n{'=' * 60}")
    print("SUMMARY FOR PLAN DECISIONS")
    print(f"{'=' * 60}")

    print(f"""
Decision 4 (Dedup key):
  - Sequence field is assigned by the SENDER, not the receiver
  - Same sequence across both HGIs: {seq_same}
  - Different sequence across HGIs: {seq_diff}
  - No sequence (---) on both: {seq_no_seq}
  - Mixed (one ---, one numbered): {seq_mixed}
  → Sequence CAN be part of the dedup key (it's stable across HGIs)
  → But --- packets need a key that works without sequence
  → Recommendation: include sequence when present, use (verb, src,
    addr2, addr3, code, payload) as the base key, add seq when != ---

Decision 3 (RSSI TTL):
  - See RSSI readings above for variation over time
  - Need to determine when readings become "stale"
  - The 0.5s dedup window is separate from RSSI TTL
  → Initial default: 300 seconds; configurable and subject to
    longer/movement testing
""")

    print("(Analysis complete — see above for details)")


if __name__ == "__main__":
    main()
