#!/usr/bin/env python3
"""Harvest RAMSES RF logs from ramses_rf test directory for the simulator.

This script converts RAMSES RF log files into conversation YAML files
that can be imported into the device simulator database.
"""

import argparse
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

# Mapping of simulator slugs to their RAMSES device ID prefixes (first byte)
DEVICE_TYPE_PREFIX: dict[str, str] = {
    "HGI": "18",
    # HVAC
    "FAN": "32",
    "CO2": "37",
    "HUM": "29",
    "REM": "37",
    "DIS": "37",
    "RFS": "30",
    # Heat
    "CTL": "01",
    "TRV": "04",
    "DHW": "07",
    "BDR": "13",
    "OTB": "10",
    "PRG": "23",
    "UFC": "02",
    "OUT": "17",
    "DTS": "12",
    "HCW": "03",
    "RND": "34",
    "RFG": "30",
    "THM": "22",
    "JIM": "08",
    "JST": "31",
}

PREFIX_TO_DEVICE_TYPES: dict[str, set[str]] = defaultdict(set)
for slug, prefix in DEVICE_TYPE_PREFIX.items():
    PREFIX_TO_DEVICE_TYPES[prefix].add(slug)


@dataclass
class ConversationFrame:
    """A single frame within a conversation block.

    :param t: Relative timestamp in seconds from start of block.
    :param src: Source device slug (e.g. 'FAN', 'REM').
    :param dst: Destination slug or 'ALL' for broadcast.
    :param code: RAMSES code.
    :param verb: Message verb (I/RQ/RP/W).
    :param payload: Hex payload string.
    """

    t: float
    src: str
    dst: str
    code: str
    verb: str
    payload: str


# Matches both ISO "2026-04-18T18:51:46.915588" and classic "2024-01-01 12:00:00.123"
_TS_PATTERN = re.compile(r"\b(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?)\b")
_VERBS = ("RQ", "RP", "I", "W")
_DEVICE_ID = re.compile(r"(?:\d{2}:\d{6}|--:------|\d{3}:\d{6})")


def _parse_timestamp(raw: str) -> datetime | None:
    """Parse an ISO or classic ramses timestamp."""
    for fmt in (
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
    ):
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    return None


def parse_ramses_log(
    content: str,
) -> tuple[list[ConversationFrame], set[str]]:
    """Parse a ramses log blob into chronologically sorted frames.

    Accepts three styles (fields may be tab- or space-separated):

    * **Classic ramses.log**: ``timestamp RSSI verb src dst code payload``
      e.g. ``2024-01-01 12:00:00.123 082 I 20:123456 --:------ 31DA 0001020304``
    * **Newer tab-separated dumps**: ``timestamp verb code src dst length payload``
      e.g. ``2026-04-18T18:51:46.915588\tRP\t2349\t01:150000\t18:000730\t013 0807C0...``
    * **Device-name format**: ``timestamp verb code_hex device_slug target``
      ``length payload``
      e.g. ``2025-01-01T00:00:00.000000\tI\t31E0\tCO2\tALL\t007\t6400CD03E803E8``

    The parser splits input by detected timestamps, tokenises each record, and
    identifies verb/code/src/dst positions dynamically to tolerate various orderings.

    Returns ``(frames, peers_set)`` where frames are sorted chronologically and
    peer device_ids (excluding broadcast ``--:------``) are collected.

    :param content: Raw log content as a single string.
    """
    # Split the content into chunks that each start with a timestamp
    matches = list(_TS_PATTERN.finditer(content))
    if not matches:
        return [], set()

    records: list[tuple[datetime, list[str]]] = []
    for idx, m in enumerate(matches):
        ts_raw = m.group(1)
        ts = _parse_timestamp(ts_raw)
        if ts is None:
            continue
        start = m.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(content)
        rest = content[start:end]
        tokens = [tok for tok in re.split(r"[\t ]+", rest.strip()) if tok]
        if not tokens:
            continue
        records.append((ts, tokens))

    # Parse each record into a ConversationFrame candidate
    frames: list[ConversationFrame] = []
    raw_frames: list[tuple[datetime, ConversationFrame]] = []
    peers_set: set[str] = set()

    for ts, tokens in records:
        # Find verb
        verb_idx = next((i for i, t in enumerate(tokens) if t in _VERBS), None)
        if verb_idx is None:
            continue
        verb = tokens[verb_idx]

        # Try to find two device-id tokens (src, dst) — in that order
        dev_idxs = [i for i, t in enumerate(tokens) if _DEVICE_ID.fullmatch(t)]

        # If we don't have 2 device IDs, try alternate format:
        # timestamp verb code_hex device_name broadcast_flag length payload
        if len(dev_idxs) < 2:
            # Look for a 4-hex code right after verb
            code_candidates = [
                (i, t)
                for i, t in enumerate(tokens)
                if i > verb_idx
                and len(t) == 4
                and all(c in "0123456789ABCDEFabcdef" for c in t)
            ]
            if not code_candidates:
                continue
            code_idx, code = code_candidates[0]
            # In this format, src/dst are slugs immediately following the code
            src_idx = code_idx + 1
            dst_idx = code_idx + 2
            src = tokens[src_idx].upper() if src_idx < len(tokens) else "UNKNOWN"
            dst = tokens[dst_idx].upper() if dst_idx < len(tokens) else "ALL"
            # Payload is the last hex token (skip length prefix if present)
            hex_tokens = [
                (i, t)
                for i, t in enumerate(tokens)
                if i > code_idx and all(c in "0123456789ABCDEFabcdef" for c in t)
            ]
            if not hex_tokens:
                continue
            # Skip 3-digit length prefix if present
            if len(hex_tokens) > 1 and len(hex_tokens[0][1]) == 3:
                payload = hex_tokens[-1][1].upper()
            elif len(hex_tokens) == 1 and len(hex_tokens[0][1]) == 3:
                continue
            else:
                payload = hex_tokens[-1][1].upper()
        else:
            # Standard format with device IDs
            if len(dev_idxs) < 2:
                continue
            src = tokens[dev_idxs[0]]
            dst = tokens[dev_idxs[1]]

            # Find the 4-hex-digit code (appears once, separate from payload)
            code_candidates = [
                (i, t)
                for i, t in enumerate(tokens)
                if len(t) == 4
                and all(c in "0123456789ABCDEFabcdef" for c in t)
                and i != verb_idx
                and i not in dev_idxs
            ]
            if not code_candidates:
                continue
            code_idx, code = code_candidates[0]

            # Payload = last long hex token after code (skip length prefix if present).
            hex_tokens = [
                (i, t)
                for i, t in enumerate(tokens)
                if i > max(verb_idx, code_idx, *dev_idxs)
                and all(c in "0123456789ABCDEFabcdef" for c in t)
            ]
            if not hex_tokens:
                continue
            # If the first hex token is 3 digits, it's likely a length prefix
            if len(hex_tokens) > 1 and len(hex_tokens[0][1]) == 3:
                payload = hex_tokens[-1][1].upper()
            elif len(hex_tokens) == 1 and len(hex_tokens[0][1]) == 3:
                continue
            else:
                payload = hex_tokens[-1][1].upper()

        frame_src = src
        frame_dst = dst
        raw_frames.append(
            (
                ts,
                ConversationFrame(
                    t=0.0,  # filled in after sorting
                    src=frame_src,
                    dst=frame_dst,
                    code=code.upper(),
                    verb=verb,
                    payload=payload,
                ),
            )
        )

        peers_set.add(frame_src)
        if frame_dst != "--:------" and frame_dst != "ALL":
            peers_set.add(frame_dst)

    if not raw_frames:
        return [], peers_set

    # Sort chronologically, compute relative t from first frame
    raw_frames.sort(key=lambda pair: pair[0])
    t0 = raw_frames[0][0]
    for ts, fr in raw_frames:
        fr.t = (ts - t0).total_seconds()
        frames.append(fr)

    return frames, peers_set


# ---------------------------------------------------------------------------
# Helper utilities for device filtering and conversation building
# ---------------------------------------------------------------------------


def _collect_peers(frames: list[ConversationFrame]) -> list[str]:
    peers: set[str] = set()
    for frame in frames:
        for addr in (frame.src, frame.dst):
            if addr in ("--:------", "ALL"):
                continue
            peers.add(addr)
    return sorted(peers)


def _frames_to_dicts(frames: list[ConversationFrame]) -> list[dict[str, Any]]:
    if not frames:
        return []
    base_t = frames[0].t
    return [
        {
            "t": f.t - base_t,
            "src": f.src,
            "dst": f.dst,
            "code": f.code,
            "verb": f.verb,
            "payload": f.payload,
        }
        for f in frames
    ]


def _device_slugs_for_id(device_id: str, allowed: set[str]) -> set[str]:
    if not device_id or ":" not in device_id:
        return set()
    prefix = device_id.split(":", 1)[0]
    matches = PREFIX_TO_DEVICE_TYPES.get(prefix, set())
    if not matches:
        return set()
    if not allowed:
        return matches
    return {slug for slug in matches if slug in allowed}


def _group_frames_by_device(
    frames: list[ConversationFrame], allowed_slugs: set[str]
) -> dict[tuple[str, str], list[ConversationFrame]]:
    groups: dict[tuple[str, str], list[ConversationFrame]] = {}
    if not allowed_slugs:
        return groups

    for frame in frames:
        frame_keys: set[tuple[str, str]] = set()
        for device_id in (frame.src, frame.dst):
            for slug in _device_slugs_for_id(device_id, allowed_slugs):
                key = (slug, device_id)
                if key in frame_keys:
                    continue
                groups.setdefault(key, []).append(frame)
                frame_keys.add(key)
    return groups


def _sanitize_conv_id(*parts: str) -> str:
    raw = "_".join(parts)
    return raw.replace(":", "_").replace(" ", "_").replace("-", "_")


# RAMSES RF test directory
RAMSES_RF_DIR = Path("/home/willem/dev/ramses_rf/tests/tests")

# Output directory for harvested conversations
OUTPUT_DIR = Path(__file__).parent.parent / "device_db" / "conversations"

# Log file patterns to harvest
HVAC_PATTERNS = [
    "bindings/hvac/*.log",
    "fingerprints/hvac/*.log",
    "eavesdrop_dev_class/hvac/*.log",
]

HEAT_PATTERNS = [
    "bindings/heat/*.log",
    "fingerprints/heat/*.log",
    "eavesdrop_schema/*/*.log",
]


def harvest_logs(
    ramses_rf_dir: Path,
    output_dir: Path,
    category: str,
    patterns: list[str],
    device_filters: set[str] | None = None,
) -> int:
    """Harvest logs from ramses_rf test directory.

    :param ramses_rf_dir: Path to ramses_rf tests directory
    :param output_dir: Path to output directory for conversation YAMLs
    :param category: Category name (HVAC or HEAT)
    :param patterns: Glob patterns for log files to harvest
    :return: Number of logs harvested
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    harvested = 0

    for pattern in patterns:
        for log_file in ramses_rf_dir.glob(pattern):
            if not log_file.is_file():
                continue

            try:
                content = log_file.read_text(encoding="utf-8")
                frames, peers = parse_ramses_log(content)

                if not frames:
                    print(f"Skipping {log_file}: no valid frames")
                    continue

                device_groups = _group_frames_by_device(frames, device_filters or set())

                if device_groups:
                    for (slug, device_id), subset in device_groups.items():
                        frames_dict = _frames_to_dicts(subset)
                        peers_list = _collect_peers(subset)
                        conv_id = _sanitize_conv_id(
                            category.lower(), slug.lower(), device_id, log_file.stem
                        )
                        conversation = {
                            "peers": peers_list,
                            "conversations": [
                                {
                                    "id": conv_id,
                                    "description": (
                                        f"Harvested from {log_file.name}: "
                                        f"device {device_id} ({slug})"
                                    ),
                                    "frames": frames_dict,
                                }
                            ],
                        }

                        output_file = output_dir / f"{conv_id}.yaml"
                        with open(output_file, "w", encoding="utf-8") as f:
                            yaml.dump(
                                conversation,
                                f,
                                default_flow_style=False,
                                sort_keys=False,
                            )

                        rel_path = output_file.relative_to(output_dir)
                        print(
                            f"Harvested: {log_file.name} ({device_id}/{slug}) -> {rel_path}"  # noqa: E501
                        )
                        harvested += 1
                    continue

                # Convert ConversationFrame objects to dicts for YAML serialization
                frames_dict = _frames_to_dicts(frames)

                # Create conversation YAML with category prefix
                stem = log_file.stem.replace(" ", "_").replace("-", "_")
                conv_id = f"{category.lower()}_{stem}"
                peers_list = sorted(peers)

                conversation = {
                    "peers": peers_list,
                    "conversations": [
                        {
                            "id": conv_id,
                            "description": (
                                f"Harvested from ramses_rf: "
                                f"{log_file.relative_to(ramses_rf_dir)}"
                            ),
                            "frames": frames_dict,
                        }
                    ],
                }

                # Write YAML file
                output_file = output_dir / f"{conv_id}.yaml"
                with open(output_file, "w", encoding="utf-8") as f:
                    yaml.dump(
                        conversation, f, default_flow_style=False, sort_keys=False
                    )

                rel_path = output_file.relative_to(output_dir)
                print(f"Harvested: {log_file.name} -> {rel_path}")
                harvested += 1

            except Exception as e:
                print(f"Error processing {log_file}: {e}")

    return harvested


def main() -> int:
    parser = argparse.ArgumentParser(description="Harvest RAMSES RF logs for simulator")
    parser.add_argument(
        "--ramses-rf-dir",
        type=Path,
        default=RAMSES_RF_DIR,
        help="Path to ramses_rf tests directory",
    )
    parser.add_argument(
        "--log-file",
        type=Path,
        help="Path to a single RAMSES log file (overrides --category patterns)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=OUTPUT_DIR,
        help="Path to output directory for conversation YAMLs",
    )
    parser.add_argument(
        "--category",
        choices=["HVAC", "HEAT", "ALL"],
        default="ALL",
        help="Category of logs to harvest",
    )
    parser.add_argument(
        "--device-types",
        nargs="*",
        help="Filter conversations to specific device types (e.g. RND THM OTB DHW)",
    )

    args = parser.parse_args()

    if not args.ramses_rf_dir.exists():
        print(f"Error: ramses_rf directory not found: {args.ramses_rf_dir}")
        return 1

    device_filters: set[str] = set()
    if args.device_types:
        for token in args.device_types:
            for raw in token.split(","):
                slug = raw.strip().upper()
                if not slug:
                    continue
                if slug not in DEVICE_TYPE_PREFIX:
                    print(f"Warning: unknown device type '{raw}', skipping")
                    continue
                device_filters.add(slug)

    device_filters = device_filters or set()

    if args.log_file:
        if not args.log_file.exists():
            print(f"Error: log file not found: {args.log_file}")
            return 1

        category = args.category if args.category != "ALL" else "custom"
        log_dir = args.log_file.parent
        print(f"\nHarvesting {args.log_file} (category={category})...")
        harvested = harvest_logs(
            log_dir,
            args.output_dir,
            category,
            [args.log_file.name],
            device_filters or None,
        )
        print(f"\nTotal harvested: {harvested} logs")
        return 0

    total_harvested = 0

    if args.category in ("HVAC", "ALL"):
        print("\nHarvesting HVAC logs...")
        harvested = harvest_logs(
            args.ramses_rf_dir,
            args.output_dir,
            "HVAC",
            HVAC_PATTERNS,
            device_filters or None,
        )
        print(f"Harvested {harvested} HVAC logs")
        total_harvested += harvested

    if args.category in ("HEAT", "ALL"):
        print("\nHarvesting HEAT logs...")
        harvested = harvest_logs(
            args.ramses_rf_dir,
            args.output_dir,
            "HEAT",
            HEAT_PATTERNS,
            device_filters or None,
        )
        print(f"Harvested {harvested} HEAT logs")
        total_harvested += harvested

    print(f"\nTotal harvested: {total_harvested} logs")
    return 0


if __name__ == "__main__":
    exit(main())
