#!/usr/bin/env python3
"""Offline build script for Device Simulator Device Database.

Mines ramses_rf source files and the regression packet log to generate
structured YAML device type files in device_db/heat/ and device_db/hvac/.

Sources:
  - ramses_rf/src/ramses_tx/ramses.py: _DEV_KLASSES_HEAT/HVAC for code/verb schema
  - ramses_rf/src/ramses_tx/fingerprints.py: __DEVICE_INFO_RAW for hardware variants
  - ramses_rf/tests/fixtures/regression_packets_sorted.txt: example payloads + intervals

Output:
  - custom_components/ramses_extras/features/device_simulator/device_db/
    ├── heat/*.yaml
    ├── hvac/*.yaml
    └── conversations/*.yaml

Usage:
  source ~/venvs/extras/bin/activate
  python scripts/build_device_db.py
"""

from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Add ramses_rf to path for importing schema
RAMSES_RF_PATH = Path("/home/willem/dev/ramses_rf/src")
sys.path.insert(0, str(RAMSES_RF_PATH))

OUTPUT_DIR = (
    Path(__file__).parent.parent
    / "custom_components"
    / "ramses_extras"
    / "features"
    / "device_simulator"
    / "device_db"
)
REGRESSION_FILE = Path(
    "/home/willem/dev/ramses_rf/tests/fixtures/regression_packets_sorted.txt"
)


def load_ramses_schema() -> tuple[dict, dict]:
    """Parse _DEV_KLASSES_HEAT and _DEV_KLASSES_HVAC from ramses.py source."""
    ramses_path = RAMSES_RF_PATH / "ramses_tx" / "ramses.py"
    if not ramses_path.exists():
        print(f"ramses.py not found at {ramses_path}")
        return {}, {}

    source = ramses_path.read_text(encoding="utf-8")

    def extract_dict_content(text: str, start_marker: str) -> str:
        """Extract content between outer braces for a dict assignment."""
        # Find the actual assignment line (e.g. "_DEV_KLASSES_HVAC: dict[...] = {")
        pattern = rf"{re.escape(start_marker)}.*=\s*\{{"
        match = re.search(pattern, text)
        if not match:
            return ""
        brace_idx = match.end() - 1  # Position of opening brace

        # Track brace depth to find the matching close brace
        depth = 1
        idx = brace_idx + 1
        while idx < len(text) and depth > 0:
            if text[idx] == "{":
                depth += 1
            elif text[idx] == "}":
                depth -= 1
            idx += 1
        return text[brace_idx + 1 : idx - 1]

    def parse_dev_klasses(content: str) -> dict[str, dict[str, set[str]]]:
        """Extract {slug: {verb: {codes}}} from a _DEV_KLASSES_* content."""
        result: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))

        # Pattern for DevType.SLUG: { ... } blocks
        # Use brace depth counting to handle nested structures
        idx = 0
        while True:
            match = re.search(r"DevType\.(\w+):\s*\{", content[idx:])
            if not match:
                break

            slug = match.group(1)
            block_start = idx + match.end() - 1  # Position of opening brace

            # Find matching closing brace
            depth = 1
            pos = block_start + 1
            while pos < len(content) and depth > 0:
                if content[pos] == "{":
                    depth += 1
                elif content[pos] == "}":
                    depth -= 1
                pos += 1

            code_block = content[block_start + 1 : pos - 1]
            idx = pos

            # Parse Code._XXXX: {I_: {}, RP: {}, ...} entries
            # Verbs are bare like I_:, RP:, RQ:, W_: (not Verb.I format)
            for cv_match in re.finditer(
                r"Code\.(_[0-9A-F]{4}):\s*\{([^}]*)\}", code_block
            ):
                code = cv_match.group(1).lstrip("_")  # _0006 -> 0006
                verbs_str = cv_match.group(2)
                # Extract bare verb names (I_, RP, RQ, W_)
                for verb_match in re.finditer(r"\b(I_|RQ|RP|W_)\b", verbs_str):
                    verb = verb_match.group(1).rstrip("_")  # I_ -> I, RP -> RP
                    result[slug][verb].add(code)

        return dict(result)

    heat_content = extract_dict_content(source, "_DEV_KLASSES_HEAT")
    hvac_content = extract_dict_content(source, "_DEV_KLASSES_HVAC")

    heat = parse_dev_klasses(heat_content)
    hvac = parse_dev_klasses(hvac_content)

    return heat, hvac


def load_fingerprints() -> dict[str, dict[str, Any]]:
    """Parse hardware fingerprints from fingerprints.py source."""
    fp_path = RAMSES_RF_PATH / "ramses_tx" / "fingerprints.py"
    if not fp_path.exists():
        print(f"fingerprints.py not found at {fp_path}")
        return {}

    source = fp_path.read_text(encoding="utf-8")

    # Find __DEVICE_INFO_RAW dict
    match = re.search(r"__DEVICE_INFO_RAW\s*=\s*\{([^}]+)\}", source, re.DOTALL)
    if not match:
        return {}

    content = match.group(1)
    result: dict[str, dict[str, Any]] = {}

    # Parse entries like: "0001001B221201FEFF": {"slug": "CVE", "brand": "Itho", ...}
    entry_pattern = r'"([0-9A-F]{16})":\s*\{([^}]+)\}'
    for entry_match in re.finditer(entry_pattern, content):
        fp_id = entry_match.group(1)
        fields_str = entry_match.group(2)

        fields: dict[str, Any] = {}
        for field_match in re.finditer(r'"(\w+)":\s*"([^"]*)"', fields_str):
            key, value = field_match.groups()
            fields[key] = value

        if fields:
            result[fp_id] = fields

    return result


@dataclass
class PacketEntry:
    """Parsed regression packet entry."""

    timestamp: str
    verb: str
    src: str
    dst: str
    code: str
    length: int
    payload: str
    parsed: dict[str, Any] = field(default_factory=dict)


# Regex for regression file lines
# Format: 2020-01-01T00:00:00.000000 --- RQ --- 18:000730 01:145038 --:------ 0006 004
# 00...
PACKET_RE = re.compile(
    r"^(\S+)\s+---\s+(\S+)\s+---\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\d{3})\s+(\S+)"
)


def parse_regression_file(max_lines: int | None = None) -> list[PacketEntry]:
    """Parse the regression packet file.

    :param max_lines: Optional limit for testing.
    :return: List of parsed packet entries.
    """
    entries: list[PacketEntry] = []

    if not REGRESSION_FILE.exists():
        print(f"Regression file not found: {REGRESSION_FILE}")
        return entries

    with open(REGRESSION_FILE, encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            if max_lines and i > max_lines:
                break

            line = line.strip()
            if not line or line.startswith("#"):
                continue

            # Split on comment for JSON data
            parts = line.split("  # ", 1)
            packet_part = parts[0]
            json_part = parts[1] if len(parts) > 1 else "{}"

            match = PACKET_RE.match(packet_part)
            if not match:
                continue

            ts, verb, src, dst1, dst2, code, length, payload = match.groups()

            # Parse JSON if present
            try:
                parsed = json.loads(json_part) if json_part else {}
            except json.JSONDecodeError:
                parsed = {}

            entries.append(
                PacketEntry(
                    timestamp=ts,
                    verb=verb,
                    src=src,
                    dst=dst1 if dst1 != "--:------" else dst2,
                    code=code.upper(),
                    length=int(length),
                    payload=payload,
                    parsed=parsed,
                )
            )

    print(f"Parsed {len(entries)} packets from regression file")
    return entries


def extract_payloads_by_device_type(
    entries: list[PacketEntry],
) -> dict[str, dict[str, list[str]]]:
    """Extract example payloads per (device_type, code) from regression data.

    Uses src prefix heuristics: 37:xx = FAN/HVAC, 32:xx = CO2, etc.

    :param entries: Parsed packet entries.
    :return: {device_type: {code: [payloads]}}.
    """
    # src prefix → device type slug (rough mapping from ramses_rf conventions)
    prefix_map: dict[str, str] = {
        "37": "FAN",  # HVAC fans
        "32": "CO2",  # CO2 sensors
        "34": "REM",  # Remotes
        "30": "RFG",  # Relay/bridge
        "18": "GWY",  # Gateway
        "01": "CTL",  # Controller
        "04": "TRV",  # TRV
        "03": "OTB",  # Opentherm bridge
        "13": "BDR",  # Boiler relay
    }

    result: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))

    for entry in entries:
        prefix = entry.src.split(":")[0] if ":" in entry.src else ""
        slug = prefix_map.get(prefix, "UNKNOWN")

        # Only keep unique payloads per code (max 5 examples)
        payloads = result[slug][entry.code]
        if entry.payload not in payloads and len(payloads) < 5:
            payloads.append(entry.payload)

    return dict(result)


def compute_intervals(entries: list[PacketEntry]) -> dict[tuple[str, str], float]:
    """Compute typical intervals between I messages per (src, code).

    :param entries: Parsed packet entries.
    :return: {(src_prefix, code): interval_seconds}.
    """
    from datetime import datetime

    # Group I messages by (src, code)
    i_messages: dict[tuple[str, str], list[datetime]] = defaultdict(list)

    for entry in entries:
        if entry.verb != "I":
            continue
        try:
            ts = datetime.fromisoformat(entry.timestamp.replace("Z", "+00:00"))
            i_messages[(entry.src, entry.code)].append(ts)
        except ValueError:
            continue

    # Compute median interval per group (capped at 1 hour)
    max_interval = 3600.0  # 1 hour - RAMSES heartbeats don't exceed this
    intervals: dict[tuple[str, str], float] = {}
    for key, timestamps in i_messages.items():
        if len(timestamps) < 2:
            continue
        timestamps.sort()
        deltas = [
            (timestamps[i + 1] - timestamps[i]).total_seconds()
            for i in range(len(timestamps) - 1)
        ]
        # Filter out huge gaps (likely sparse captures, not real intervals)
        deltas = [d for d in deltas if d < max_interval * 2]  # Keep only < 2 hours
        if not deltas:
            continue
        # Use median to ignore remaining outliers
        deltas.sort()
        median = deltas[len(deltas) // 2]
        # Cap at reasonable max
        capped = min(median, max_interval) if median > 0 else 60.0
        if capped > 0:
            intervals[key] = round(capped, 1)

    return intervals


def scaffold_device_type_yaml(
    slug: str,
    domain: str,
    codes: dict[str, set[str]],  # verb: set of codes
    fingerprints: dict[str, dict[str, Any]],
    payload_examples: dict[str, list[str]],
    intervals: dict[tuple[str, str], float],
) -> str:
    """Generate YAML content for a device type.

    :param slug: Device type slug (e.g. 'FAN').
    :param domain: 'heat' or 'hvac'.
    :param codes: Map of verb → set of codes from ramses.py schema.
    :param fingerprints: Hardware fingerprint data.
    :param payload_examples: Code → list of example payloads.
    :param intervals: (src, code) → interval seconds.
    :return: YAML string.
    """
    import yaml

    # Build variants from fingerprints
    variants: list[dict[str, Any]] = []
    for fp_id, fp_info in fingerprints.items():
        if fp_info.get("slug") != slug:
            continue

        variant: dict[str, Any] = {
            "id": fp_id,
            "fingerprint": fp_id,  # fingerprint ID is the key
            "desc": fp_info.get("desc", ""),
            "brand": fp_info.get("brand", ""),
            "date": fp_info.get("date", ""),
            "broadcast_safe": False,  # default conservative
        }

        # Add scheme_22f1 if fan and brand known
        if slug == "FAN" and fp_info.get("brand"):
            brand = fp_info.get("brand", "").lower()
            if "itho" in brand:
                variant["scheme_22f1"] = "itho"
            elif "orcon" in brand:
                variant["scheme_22f1"] = "orcon"
            elif "nuaire" in brand:
                variant["scheme_22f1"] = "nuaire"
            elif "vasco" in brand:
                variant["scheme_22f1"] = "vasco"

        variants.append(variant)

    # Build autonomous from I codes + payload examples
    autonomous: list[dict[str, Any]] = []
    for code in codes.get("I", set()):
        payloads = payload_examples.get(code, [])
        # Estimate interval from intervals dict (median across all srcs for this code)
        code_intervals = [v for (src, c), v in intervals.items() if c == code]
        interval = (
            round(sum(code_intervals) / len(code_intervals), 1)
            if code_intervals
            else 60.0
        )

        entry: dict[str, Any] = {
            "code": code,
            "verb": "I",
            "trigger": "periodic",
            "interval_seconds": interval,
            "payloads": payloads[:3] if payloads else [],
        }
        if payloads:
            entry["notes"] = "Example payloads from regression file"
        autonomous.append(entry)

    # Build responses from RQ codes
    responses: list[dict[str, Any]] = []
    for code in codes.get("RQ", set()):
        entry = {
            "code": code,
            "rq_verb": "RQ",
            "rp_verb": "RP",
            "delay_ms": 100,
            "payloads": payload_examples.get(code, [])[:1],  # Just first example
        }
        if not entry["payloads"]:
            entry["payloads"] = []  # Will be filled manually or from 10E0 fingerprint
        responses.append(entry)

    # Build structure
    data: dict[str, Any] = {
        "device_type": slug,
        "domain": domain,
        "broadcast_safe": False,  # Conservative default
    }

    if variants:
        data["variants"] = variants

    if autonomous:
        data["autonomous"] = autonomous

    if responses:
        data["responses"] = responses

    # YAML output with comments preserved via our structure
    return yaml.dump(data, sort_keys=False, allow_unicode=True)


def build_all() -> None:
    """Main entry: load sources, generate all YAML files."""
    print("=" * 60)
    print("Building Device Simulator Database")
    print("=" * 60)

    # Ensure output dirs exist
    for subdir in ("heat", "hvac", "conversations"):
        (OUTPUT_DIR / subdir).mkdir(parents=True, exist_ok=True)

    # Load sources
    print("\n[1/4] Loading ramses.py schema...")
    heat_classes, hvac_classes = load_ramses_schema()
    print(f"  Heat device types: {list(heat_classes.keys())}")
    print(f"  HVAC device types: {list(hvac_classes.keys())}")

    print("\n[2/4] Loading fingerprints...")
    fingerprints = load_fingerprints()
    print(f"  Hardware variants: {len(fingerprints)}")

    print("\n[3/4] Parsing regression file...")
    entries = parse_regression_file()

    print("\n[4/4] Extracting payloads and intervals...")
    payload_map = extract_payloads_by_device_type(entries)
    intervals = compute_intervals(entries)

    # Scaffold YAML files
    print("\n[5/4] Generating YAML files...")

    # HVAC domain
    for slug, codes in hvac_classes.items():
        domain = "hvac"
        payloads = payload_map.get(slug, {})
        yaml_content = scaffold_device_type_yaml(
            slug, domain, codes, fingerprints, payloads, intervals
        )
        out_path = OUTPUT_DIR / domain / f"{slug}.yaml"
        with open(out_path, "w", encoding="utf-8") as f:
            f.write("# Auto-generated from ramses_rf sources\n")
            f.write(f"# Device type: {slug} (domain: {domain})\n")
            f.write("# Manual review recommended before committing\n")
            f.write("---\n")
            f.write(yaml_content)
        print(f"  Written: {out_path}")

    # Heat domain
    for slug, codes in heat_classes.items():
        domain = "heat"
        payloads = payload_map.get(slug, {})
        yaml_content = scaffold_device_type_yaml(
            slug, domain, codes, fingerprints, payloads, intervals
        )
        out_path = OUTPUT_DIR / domain / f"{slug}.yaml"
        with open(out_path, "w", encoding="utf-8") as f:
            f.write("# Auto-generated from ramses_rf sources\n")
            f.write(f"# Device type: {slug} (domain: {domain})\n")
            f.write("# Manual review recommended before committing\n")
            f.write("---\n")
            f.write(yaml_content)
        print(f"  Written: {out_path}")

    print("\n" + "=" * 60)
    print("Build complete. Review generated files before committing.")
    print("=" * 60)


if __name__ == "__main__":
    build_all()
