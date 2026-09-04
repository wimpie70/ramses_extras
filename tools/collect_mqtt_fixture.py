#!/usr/bin/env python3
"""Collect MQTT traffic fixtures from two HGIs for dedup key and RSSI TTL analysis.

Captures raw MQTT messages with their topics (which contain the HGI ID)
for a configurable duration, then writes:
  - fixtures/mqtt_paired_raw.jsonl   (one JSON object per message)
  - fixtures/mqtt_paired_summary.txt  (analysis of paired packets)
"""

import asyncio
import json
import os
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import paho.mqtt.client as mqtt

BROKER = os.environ.get("RAMSES_MQTT_BROKER", "192.168.40.11")
PORT = int(os.environ.get("RAMSES_MQTT_PORT", "1883"))
USER = os.environ.get("RAMSES_MQTT_USER", "")
PASS = os.environ.get("RAMSES_MQTT_PASS", "")
TOPIC_RX = "RAMSES/GATEWAY/+/rx"
TOPIC_STATUS = "RAMSES/GATEWAY/+/status"
DURATION = int(sys.argv[1]) if len(sys.argv) > 1 else 120
OUTDIR = Path(__file__).parent.parent / "fixtures"  # write to fixtures/, not tools/

messages: list[dict] = []


def on_connect(client, userdata, flags, reason_code, properties=None):
    print(f"Connected: {reason_code}", flush=True)
    client.subscribe([(TOPIC_RX, 0), (TOPIC_STATUS, 0)])


def on_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload)
    except json.JSONDecodeError, UnicodeDecodeError:
        payload = {"raw": msg.payload.decode(errors="replace")}

    entry = {
        "topic": msg.topic,
        "hgi_id": msg.topic.split("/")[-2] if "/rx" in msg.topic else None,
        "ts_capture": datetime.utcnow().isoformat(),
        "payload": payload,
    }
    messages.append(entry)
    if len(messages) % 50 == 0:
        print(f"  ...collected {len(messages)} messages", flush=True)


def main():
    if not USER or not PASS:
        print(
            "ERROR: Set RAMSES_MQTT_USER and RAMSES_MQTT_PASS environment "
            "variables before running.",
            flush=True,
        )
        sys.exit(1)

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.username_pw_set(USER, PASS)
    client.on_connect = on_connect
    client.on_message = on_message

    print(f"Connecting to {BROKER}:{PORT}...", flush=True)
    client.connect(BROKER, PORT, 60)
    client.loop_start()

    print(f"Collecting for {DURATION}s...", flush=True)
    time.sleep(DURATION)

    client.loop_stop()
    client.disconnect()
    print(f"Collected {len(messages)} messages total", flush=True)

    # Write raw JSONL
    rawpath = OUTDIR / "mqtt_paired_raw.jsonl"
    with open(rawpath, "w") as f:
        for m in messages:
            f.write(json.dumps(m) + "\n")
    print(f"Wrote {rawpath}", flush=True)

    # Analyze
    analyze(messages)


def analyze(messages):
    """Find paired packets (same content heard by both HGIs) and report."""
    rx_msgs = [m for m in messages if m["hgi_id"] and "/rx" in m["topic"]]
    print(f"\nRX messages: {len(rx_msgs)}", flush=True)

    # Group by frame content (the "msg" field in the payload)
    by_content: dict[str, list[dict]] = defaultdict(list)
    for m in rx_msgs:
        msg_text = m["payload"].get("msg", "")
        if not msg_text:
            continue
        by_content[msg_text].append(m)

    # Find pairs (heard by 2+ HGIs)
    paired = {k: v for k, v in by_content.items() if len({x["hgi_id"] for x in v}) >= 2}
    single = {k: v for k, v in by_content.items() if len({x["hgi_id"] for x in v}) == 1}

    print(f"Unique frame contents: {len(by_content)}", flush=True)
    print(f"Paired (2+ HGIs): {len(paired)}", flush=True)
    print(f"Single-HGI only: {len(single)}", flush=True)

    # Extract RSSI from the msg field (first 3 chars)
    def parse_rssi(msg_text):
        rssi_str = msg_text[:3].strip()
        if rssi_str == "..." or rssi_str == "000" or not rssi_str:
            return None
        try:
            return -int(rssi_str)
        except ValueError:
            return None

    def parse_frame(msg_text):
        """Parse the RAMSES frame from the msg field."""
        parts = msg_text.split()
        if len(parts) < 8:
            return None
        # Format: RSSI I seq src addr1 addr2 addr3 code len payload
        # Skip RSSI, then: I, seq, src, addr1, addr2, addr3, code, len, payload
        # Actually: "041  I 233 32:153289 --:------ 32:153289 31D9 017 ..."
        # parts[0] = RSSI, parts[1] = direction, parts[2] = seq (or ---),
        # parts[3] = src, parts[4] = addr1, parts[5] = addr2, parts[6] = addr3,
        # parts[7] = code, parts[8] = length, parts[9:] = payload
        return {
            "rssi_raw": parts[0],
            "direction": parts[1],
            "seq": parts[2],
            "src": parts[3],
            "addr1": parts[4],
            "addr2": parts[5],
            "addr3": parts[6],
            "code": parts[7],
            "length": parts[8],
            "payload": " ".join(parts[9:]) if len(parts) > 9 else "",
        }

    # Report paired packets with RSSI and timing
    summary_lines = []
    summary_lines.append("MQTT Paired Packet Fixture Analysis")
    summary_lines.append("=" * 60)
    summary_lines.append(f"Collection: {datetime.utcnow().isoformat()}Z")
    summary_lines.append(f"Duration: {DURATION}s")
    summary_lines.append(f"Total RX messages: {len(rx_msgs)}")
    summary_lines.append(f"Unique frame contents: {len(by_content)}")
    summary_lines.append(f"Paired (2+ HGIs): {len(paired)}")
    summary_lines.append(f"Single-HGI only: {len(single)}")
    summary_lines.append("")

    # HGI inventory
    hgi_counts = defaultdict(int)
    for m in rx_msgs:
        hgi_counts[m["hgi_id"]] += 1
    summary_lines.append("HGI message counts:")
    for hgi_id, count in sorted(hgi_counts.items()):
        summary_lines.append(f"  {hgi_id}: {count} messages")
    summary_lines.append("")

    # Paired packet examples
    summary_lines.append("Paired packet examples (first 20):")
    summary_lines.append("-" * 60)
    for i, (content, msgs) in enumerate(list(paired.items())[:20]):
        summary_lines.append(f"\nPair {i + 1}:")
        summary_lines.append(f"  frame: {content[:80]}...")
        frame = parse_frame(content)
        if frame:
            summary_lines.append(
                f"  parsed: code={frame['code']} seq={frame['seq']} "
                f"addr1={frame['addr1']} addr2={frame['addr2']} "
                f"src={frame['src']}"
            )
        for m in sorted(msgs, key=lambda x: x["ts_capture"]):
            rssi = parse_rssi(content)
            ts = m["payload"].get("ts", m["ts_capture"])
            summary_lines.append(f"  HGI={m['hgi_id']} RSSI={rssi} ts={ts}")

    # RSSI analysis
    summary_lines.append("\n" + "=" * 60)
    summary_lines.append("RSSI Analysis:")
    summary_lines.append("-" * 60)

    rssi_by_hgi: dict[str, list[int]] = defaultdict(list)
    for content, msgs in paired.items():
        for m in msgs:
            rssi = parse_rssi(content)
            if rssi is not None:
                rssi_by_hgi[m["hgi_id"]].append(rssi)

    for hgi_id, rssi_list in sorted(rssi_by_hgi.items()):
        if rssi_list:
            summary_lines.append(
                f"  {hgi_id}: n={len(rssi_list)} "
                f"min={min(rssi_list)} max={max(rssi_list)} "
                f"mean={sum(rssi_list) / len(rssi_list):.1f}"
            )

    # Sequence field analysis (critical for dedup key decision)
    summary_lines.append("\n" + "=" * 60)
    summary_lines.append("Sequence field analysis (dedup key decision):")
    summary_lines.append("-" * 60)

    seq_pairs: list[dict] = []
    for content, msgs in paired.items():
        frame = parse_frame(content)
        if not frame:
            continue
        hgi_seqs = {}
        for m in msgs:
            hgi_seqs[m["hgi_id"]] = frame["seq"]
        if len(hgi_seqs) >= 2:
            seq_pairs.append(
                {
                    "frame": content[:60],
                    "code": frame["code"],
                    "seqs": hgi_seqs,
                    "same_seq": len(set(hgi_seqs.values())) == 1,
                }
            )

    same_count = sum(1 for p in seq_pairs if p["same_seq"])
    diff_count = sum(1 for p in seq_pairs if not p["same_seq"])
    summary_lines.append(f"Paired packets with sequence field: {len(seq_pairs)}")
    summary_lines.append(f"  Same sequence across HGIs: {same_count}")
    summary_lines.append(f"  Different sequence across HGIs: {diff_count}")
    summary_lines.append("")

    if diff_count > 0:
        summary_lines.append("Examples with DIFFERENT sequences:")
        for p in [x for x in seq_pairs if not x["same_seq"]][:10]:
            summary_lines.append(
                f"  code={p['code']} seqs={p['seqs']} frame={p['frame']}"
            )
    if same_count > 0:
        summary_lines.append("\nExamples with SAME sequences:")
        for p in [x for x in seq_pairs if x["same_seq"]][:10]:
            summary_lines.append(
                f"  code={p['code']} seqs={p['seqs']} frame={p['frame']}"
            )

    # Timing analysis (how close in time do paired packets arrive?)
    summary_lines.append("\n" + "=" * 60)
    summary_lines.append("Timing analysis (paired packet arrival delta):")
    summary_lines.append("-" * 60)

    deltas = []
    for content, msgs in paired.items():
        if len(msgs) < 2:
            continue
        ts_list = sorted([m["ts_capture"] for m in msgs])
        for i in range(1, len(ts_list)):
            try:
                t0 = datetime.fromisoformat(ts_list[i - 1])
                t1 = datetime.fromisoformat(ts_list[i])
                delta_ms = (t1 - t0).total_seconds() * 1000
                deltas.append(delta_ms)
            except ValueError, TypeError:
                pass

    if deltas:
        summary_lines.append(f"Arrival deltas: n={len(deltas)}")
        summary_lines.append(
            f"  min={min(deltas):.1f}ms max={max(deltas):.1f}ms "
            f"mean={sum(deltas) / len(deltas):.1f}ms"
        )
        summary_lines.append(f"  median={sorted(deltas)[len(deltas) // 2]:.1f}ms")
        summary_lines.append(
            f"  >500ms: {sum(1 for d in deltas if d > 500)}/{len(deltas)}"
        )
    else:
        summary_lines.append("No timing data available (need ts from MQTT payload)")

    # Status messages
    status_msgs = [m for m in messages if "/status" in m["topic"]]
    summary_lines.append(f"\nStatus messages: {len(status_msgs)}")
    for m in status_msgs[:5]:
        summary_lines.append(f"  {m['topic']}: {m['payload']}")

    summary = "\n".join(summary_lines)
    print(summary, flush=True)

    summarypath = OUTDIR / "mqtt_paired_summary.txt"
    with open(summarypath, "w") as f:
        f.write(summary)
    print(f"\nWrote {summarypath}", flush=True)


if __name__ == "__main__":
    main()
