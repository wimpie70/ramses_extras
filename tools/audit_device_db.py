#!/usr/bin/env python3
"""Audit, enrich and apply device DB YAML payloads using ramses_tx.

Modes:
  audit (default)
      Parse every payload in the DB, detect sentinel/implausible values,
      write a YAML audit file with Y/N/Remark per payload.

  --extract-from-logs LOG [LOG ...]
      Mine RAMSES packet log files for real captured payloads.
      For each DB code that is missing or has bad payloads, find the best
      real captures, parse them, and update the DB YAML in-place.

  --llm-audit AUDIT_YAML
      Re-read an audit YAML, apply heuristic LLM-style reasoning to set
      audit=Y/N/Remark with a remark for every entry, then rewrite it.
      Outputs an audit file with only entries needing human attention.

  --apply-audit AUDIT_YAML
      Read a (human-reviewed) audit YAML and apply decisions back to the
      DB YAML: remove N payloads, keep Y, annotate Remark with comment.

Usage:
    source ~/venvs/extras/bin/activate
    # Full pipeline (run in order):
    python tools/audit_device_db.py --extract-from-logs \
        ~/docker_files/hass/config/ramses_log [more...]
    python tools/audit_device_db.py [--device FAN] [--output tools/audit_all.yaml]
    python tools/audit_device_db.py --llm-audit tools/audit_all.yaml
    # Review tools/audit_all.yaml, change audit: fields as needed, then:
    python tools/audit_device_db.py --apply-audit tools/audit_all.yaml
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime as dt
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Path setup: ensure device_db is importable.
# ramses_tx is used from the active venv (do NOT add ramses_rf/src — it pulls
# in aiofiles and other deps that may not be present).
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_REPO_ROOT / "custom_components" / "ramses_extras"))

# ---------------------------------------------------------------------------
# Sentinel detection
# ---------------------------------------------------------------------------
_SENTINEL_PATTERNS = {
    "7fff": "unavailable (temperature/numeric)",
    "7ffe": "unavailable (temperature)",
    "efef": "unavailable (humidity/percentage)",
    "ffff": "unavailable (generic)",
    "ff": "unavailable (single-byte generic)",
    "ef": "unavailable (single-byte humidity)",
}

# Per-code sentinel bytes that are legitimately valid (device has no sensor for that
# field).
# Key: code, Value: set of lowercase hex patterns that are expected/valid.
_CODE_SENTINEL_ALLOWLIST: dict[str, set[str]] = {
    "22F7": {"ef"},  # bypass_position=EF when no position sensor fitted
    "31DA": {"7fff", "ef", "efef"},  # temp/AQ/CO2 sensors may be absent on some units
    "10E0": {"ffff"},  # padding bytes in device info payload
    "2210": {"ffff"},  # padding bytes in zone info payload
}


def _has_sentinel(payload: str, code: str = "") -> list[str]:
    """Return list of unexpected sentinel descriptions found in payload."""
    p = payload.lower()
    allowed = _CODE_SENTINEL_ALLOWLIST.get(code.upper(), set())
    hits = []
    for pat, desc in _SENTINEL_PATTERNS.items():
        if pat in p and pat not in allowed:
            hits.append(f"{pat.upper()} ({desc})")
    return hits


# Per-field plausibility ranges: (min_inclusive, max_inclusive)
# Fields outside these ranges are flagged as implausible.
_FIELD_RANGES: dict[str, tuple[float, float]] = {
    "exhaust_temp": (-10.0, 50.0),
    "supply_temp": (-10.0, 50.0),
    "indoor_temp": (5.0, 40.0),
    "outdoor_temp": (-30.0, 50.0),
    "indoor_humidity": (0.01, 1.0),
    "outdoor_humidity": (0.01, 1.0),
    "co2_level": (300.0, 5000.0),
    "air_quality": (0.01, 1.0),
    "exhaust_fan_speed": (0.0, 1.0),
    "supply_fan_speed": (0.0, 1.0),
    "supply_flow": (0.0, 9999.0),
    "exhaust_flow": (0.0, 9999.0),
    "bypass_position": (0.0, 1.0),  # 0 is valid but flag if ALL speeds also 0
}

# Fields where 0.0 is a real valid value (not implausible by itself)
_ZERO_OK = {
    "bypass_position",
    "pre_heat",
    "post_heat",
    "remaining_mins",
    "exhaust_fan_speed",
    "supply_fan_speed",
    "supply_flow",
    "exhaust_flow",
}


def _check_value_plausibility(parsed: dict) -> list[str]:
    """Return list of implausible field descriptions based on decoded values."""
    issues = []
    # Empty string value means ramses_tx parsed the field but couldn't decode it
    # (e.g. unknown data_type in 2411)
    if parsed.get("value") == "":
        issues.append(
            "value='' (unknown data_type — payload format not recognised by ramses_tx)"
        )
    for field, (lo, hi) in _FIELD_RANGES.items():
        val = parsed.get(field)
        if val is None:
            continue
        if not isinstance(val, (int, float)):
            continue
        if val < lo or val > hi:
            issues.append(f"{field}={val} (expected {lo}..{hi})")
    return issues


def _sentinel_ratio(payload: str, parsed: dict) -> tuple[str, list[str]]:
    """Return (quality_string, implausible_value_descriptions)."""
    if not parsed:
        return "no_fields", []
    none_count = sum(1 for v in parsed.values() if v is None)
    total = len(parsed)
    implausible = _check_value_plausibility(parsed)
    if none_count == total:
        return "all_sentinel", implausible
    if none_count > total // 2:
        return "mostly_sentinel", implausible
    if implausible:
        return "implausible", implausible
    return "ok", []


# ---------------------------------------------------------------------------
# Address-pattern helpers
# ---------------------------------------------------------------------------
# RAMSES addressing:
#   autonomous broadcast  : src --:------ src  (self-addressed I)
#   unsolicited directed  : src dst --:------  (directed I, no preceding RQ)
#   solicited response    : src dst --:------  (directed I or RP, after RQ)
# The verb alone is not reliable — some devices answer with I instead of RP,
# and some push unsolicited updates directed at a specific peer.

_NULLADDR = "--:------"
_GW_PREFIX = "18:"
_BROADCAST_ADDR = "63:262142"  # ALL_DEV_ADDR — broadcast to all devices

# Codes that have no RQ defined in ramses_tx — their I frames are ALWAYS
# autonomous/unsolicited, even when directed at a specific peer device.
_I_ONLY_CODES: frozenset[str] = frozenset()


def _load_i_only_codes() -> frozenset[str]:
    """Load codes that have no RQ verb from ramses_tx schema."""
    try:
        from ramses_tx.const import VerbT  # noqa: PLC0415
        from ramses_tx.ramses import CODES_SCHEMA  # noqa: PLC0415

        return frozenset(
            str(code)
            for code, schema in CODES_SCHEMA.items()
            if VerbT.RQ not in schema and VerbT.I_ in schema
        )
    except Exception:
        # Fallback known set if import fails
        return frozenset(
            {
                "0009",
                "1060",
                "10E2",
                "12C8",
                "1FD4",
                "2249",
                "22C9",
                "22D0",
                "22F3",
                "2E10",
                "3150",
                "31E0",
                "31DA",
                "31D9",
                "3B00",
            }
        )


def _addr_section(
    verb: str, src: str, dst: str, via: str, code: str = "", rq_seen: bool = False
) -> str:
    """Classify a frame as 'autonomous' or 'responses' by address pattern.

    Args:
        verb: RAMSES verb (I, RP, RQ, W)
        src: source address
        dst: destination address
        via: via/third address slot
        code: RAMSES code (4 hex chars) — used to check I-only codes
        rq_seen: True if a RQ for this code was seen from dst recently
    """
    global _I_ONLY_CODES  # noqa: PLW0603
    if not _I_ONLY_CODES:
        _I_ONLY_CODES = _load_i_only_codes()

    # RP/W are unambiguously responses
    if verb in ("RP", "W"):
        return "responses"

    # Self-addressed autonomous broadcast: src == via, or both dst+via are null
    if src == via or (dst == _NULLADDR and via == _NULLADDR):
        return "autonomous"

    # Broadcast to all devices (63:262142) — always autonomous
    if dst == _BROADCAST_ADDR or via == _BROADCAST_ADDR:
        return "autonomous"

    # I-only codes have no request/response cycle — always autonomous even if directed
    if code.upper() in _I_ONLY_CODES:
        return "autonomous"

    # Directed I to a real non-gateway, non-broadcast peer
    real_dst = (
        dst != _NULLADDR and not dst.startswith(_GW_PREFIX) and dst != _BROADCAST_ADDR
    )
    real_via = (
        via != _NULLADDR and not via.startswith(_GW_PREFIX) and via != _BROADCAST_ADDR
    )

    if real_dst or real_via:
        # Solicited if we saw a matching RQ recently, else unsolicited → autonomous
        return "responses" if rq_seen else "autonomous"

    # Directed to gateway only — treat as response
    return "responses"


# ---------------------------------------------------------------------------
# Frame builder
# ---------------------------------------------------------------------------
def _build_frame(section: str, src_id: str, code: str, payload: str) -> str:
    """Build a minimal parseable RAMSES frame for the given section."""
    if section == "autonomous":
        # Self-addressed I broadcast
        addrs = f"{src_id} {_NULLADDR} {src_id}"
        verb = "I"
    else:
        # RP response from device to a gateway
        addrs = f"{src_id} 18:000001 {_NULLADDR}"
        verb = "RP"
    length = len(payload) // 2
    return f"000 {verb:>2} --- {addrs} {code} {length:03d} {payload}"


# ---------------------------------------------------------------------------
# Parser wrapper
# ---------------------------------------------------------------------------
def _parse_frame(frame: str) -> tuple[dict | None, str | None]:
    """Return (parsed_payload_dict, error_string)."""
    import logging  # noqa: PLC0415

    # Silence ramses_tx's own loggers during parsing — we handle errors ourselves
    _quiet = [
        logging.getLogger(n)
        for n in (
            "ramses_tx",
            "ramses_tx.parsers",
            "ramses_tx.message",
            "ramses_tx.packet",
        )
    ]
    _orig = [(lg, lg.level, lg.propagate) for lg in _quiet]
    for lg in _quiet:
        lg.setLevel(logging.CRITICAL)
        lg.propagate = False

    try:
        from ramses_tx.message import Message  # noqa: PLC0415
        from ramses_tx.packet import Packet  # noqa: PLC0415

        pkt = Packet(dt.now(), frame)
        msg = Message(pkt)
        result = msg.payload
        if isinstance(result, list):
            result = result[0] if result else {}
        return result, None
    except Exception as exc:
        return None, f"{type(exc).__name__}: {exc}"
    finally:
        for lg, lvl, prop in _orig:
            lg.setLevel(lvl)
            lg.propagate = prop


# ---------------------------------------------------------------------------
# Main audit logic
# ---------------------------------------------------------------------------
def audit_device(slug: str, db_dir: Path) -> list[dict]:
    """Return audit entries for all payloads of a device type."""
    import yaml  # noqa: PLC0415

    # Find the YAML file
    yaml_file: Path | None = None
    for subdir in ("hvac", "heat"):
        candidate = db_dir / subdir / f"{slug.upper()}.yaml"
        if candidate.exists():
            yaml_file = candidate
            break

    if yaml_file is None:
        print(f"  [!] No YAML found for {slug}", file=sys.stderr)
        return []

    with open(yaml_file, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    # Resolve the device ID to use for frame building
    try:
        from features.device_simulator.system_config import SIM_DEVICE_ID

        src_id = SIM_DEVICE_ID.get(slug.upper(), "32:150000")
    except ImportError:
        src_id = "32:150000"

    entries: list[dict[str, Any]] = []

    def _audit_entries(section: str, items: list[dict]) -> None:
        display_verb = "I" if section == "autonomous" else "RP"
        for item in items or []:
            code = str(item.get("code", ""))
            notes = item.get("notes", "") or item.get("description", "") or ""
            payloads = item.get("payloads") or []

            if not payloads:
                entries.append(
                    {
                        "device": slug.upper(),
                        "section": section,
                        "code": code,
                        "verb": display_verb,
                        "payload_index": None,
                        "payload": None,
                        "parsed": None,
                        "sentinels": [],
                        "quality": "no_payload",
                        "notes": notes,
                        "audit": "N/A",
                        "remark": "no payload in DB",
                    }
                )
                continue

            for idx, payload in enumerate(payloads):
                # Strip inline YAML comments before parsing
                raw_payload = str(payload).split("#")[0].strip()
                frame = _build_frame(section, src_id, code, raw_payload)
                parsed, err = _parse_frame(frame)
                sentinels = _has_sentinel(raw_payload, code)
                quality, implausible = _sentinel_ratio(raw_payload, parsed or {})

                # Default audit suggestion
                if err:
                    audit = "?"
                    remark = f"parse error: {err}"
                elif quality == "all_sentinel":
                    audit = "N"
                    remark = "all fields are sentinel — replace or remove"
                elif quality == "mostly_sentinel":
                    audit = "N"
                    remark = "mostly sentinel values — replace or remove"
                elif quality == "implausible":
                    audit = "N"
                    remark = "implausible values: " + "; ".join(implausible)
                elif sentinels:
                    audit = "Remark"
                    remark = "some sentinel bytes — check if fields make sense"
                else:
                    audit = "Y"
                    remark = ""

                entries.append(
                    {
                        "device": slug.upper(),
                        "section": section,
                        "code": code,
                        "verb": display_verb,
                        "payload_index": idx,
                        "payload": raw_payload,
                        "parsed": _flatten_parsed(parsed),
                        "sentinels": sentinels,
                        "implausible": implausible,
                        "quality": quality,
                        "notes": notes,
                        "audit": audit,
                        "remark": remark,
                    }
                )

    _audit_entries("autonomous", data.get("autonomous", []))
    _audit_entries("responses", data.get("responses", []))

    return entries


def _flatten_parsed(parsed: dict | None) -> dict | None:
    """Convert parsed payload to simple str-keyed dict for YAML output."""
    if parsed is None:
        return None
    out = {}
    for k, v in parsed.items():
        if isinstance(v, (int, float, str, bool, type(None))):
            out[k] = v
        elif isinstance(v, list):
            out[k] = str(v)
        else:
            out[k] = str(v)
    return out


def write_audit_yaml(entries: list[dict], output: Path) -> None:
    """Write audit entries to a grouped, human-friendly YAML file.

    Structure:
      - device / section / code block
        - payloads list (skips no_payload entries)
          - payload, quality, sentinels, parsed, audit, remark
    """
    import yaml  # noqa: PLC0415

    # Group by (device, section, code)
    grouped: dict[tuple, list[dict]] = {}
    for e in entries:
        key = (e["device"], e["section"], e["code"])
        grouped.setdefault(key, []).append(e)

    doc: list[dict] = []
    for (device, section, code), items in grouped.items():
        # Skip codes that have no payloads at all — nothing to audit
        has_payload = any(e["payload"] is not None for e in items)
        if not has_payload:
            continue

        payload_entries = []
        for item in items:
            if item["payload"] is None:
                continue
            pe: dict = {
                "payload": item["payload"],
                "quality": item["quality"],
            }
            if item["sentinels"]:
                pe["sentinels"] = item["sentinels"]
            if item.get("implausible"):
                pe["implausible"] = item["implausible"]
            if item["parsed"]:
                pe["parsed"] = item["parsed"]
            if item.get("remark"):
                pe["remark"] = item["remark"]
            # audit is the key field to fill in — always last for easy editing
            pe["audit"] = item["audit"]
            payload_entries.append(pe)

        first = items[0]
        block: dict = {
            "device": device,
            "section": section,
            "code": code,
            "verb": first["verb"],
        }
        if first.get("notes"):
            block["notes"] = first["notes"]
        block["payloads"] = payload_entries

        doc.append(block)

    with open(output, "w", encoding="utf-8") as f:
        yaml.dump(doc, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

    print(f"Audit written to {output}")


def print_summary(entries: list[dict]) -> None:
    """Print a compact summary table to stdout."""
    print(
        f"\n{'Device':<8} {'Code':<6} {'Sec':<12} {'#':<3} {'Quality':<16} "
        f"{'Sentinels':<30} Audit"
    )
    print("-" * 90)
    for e in entries:
        idx = str(e["payload_index"]) if e["payload_index"] is not None else "-"
        sents = ", ".join(e["sentinels"])[:28] if e["sentinels"] else ""
        print(
            f"{e['device']:<8} {e['code']:<6} {e['section']:<12} {idx:<3} "
            f"{e['quality']:<16} {sents:<30} {e['audit']}"
        )


# ---------------------------------------------------------------------------
# Device-type fingerprint: addr_prefix → slug
# ---------------------------------------------------------------------------
_ADDR_PREFIX_TO_SLUG: dict[str, str] = {
    "01": "CTL",
    "02": "UFC",
    "03": "HCW",
    "04": "TRV",
    "07": "DHW",
    "08": "JIM",
    "10": "OTB",
    "12": "DTS",
    "13": "BDR",
    "17": "OUT",
    "21": "RFS",
    "22": "THM",
    "23": "PRG",
    "29": "FAN",  # also HUM, REM — resolved by code
    "30": "RFG",  # also RFS, CTL — resolved by code
    "31": "JST",
    "32": "FAN",  # also HUM, REM — resolved by code
    "34": "RND",
    "37": "REM",  # also FAN, CO2 — resolved by code
}

# For addr prefixes that map to multiple slugs, use secondary hints (code presence).
# These are resolved later during extraction.
_AMBIGUOUS_PREFIXES = {"29", "30", "32", "37"}


def _slug_from_frame(
    verb: str, src: str, dst: str, code: str, db_codes: dict[str, list[str]]
) -> str | None:
    """Guess the device slug from the source address prefix."""
    prefix = src.split(":")[0]
    slug = _ADDR_PREFIX_TO_SLUG.get(prefix)
    if slug and prefix not in _AMBIGUOUS_PREFIXES:
        return slug
    # Ambiguous: resolve by checking which slug in the DB actually has this code
    if prefix == "37":
        # FAN (dev_type 37 firmware), REM, or CO2
        for candidate in ("FAN", "REM", "CO2"):
            if code in db_codes.get(candidate, []):
                return candidate
        return "REM"  # default
    if prefix in ("29", "32"):
        # FAN, HUM, or REM
        for candidate in ("FAN", "HUM", "REM"):
            if code in db_codes.get(candidate, []):
                return candidate
        return None  # can't determine — skip
    if prefix == "30":
        # RFG, RFS, or CTL (Vasco gateway)
        for candidate in ("RFG", "RFS", "CTL"):
            if code in db_codes.get(candidate, []):
                return candidate
        return None
    return slug


# ---------------------------------------------------------------------------
# Log extraction
# ---------------------------------------------------------------------------
_FRAME_RE = re.compile(
    r"(\d{3})\s+(I|RP|RQ|W)\s+---\s+(\S+)\s+(\S+)\s+(\S+)\s+([0-9A-F]{4})\s+(\d{3})\s+([0-9A-F]+)"
)


def extract_from_logs(
    log_files: list[Path], db_dir: Path
) -> dict[str, dict[str, dict[str, list[str]]]]:
    """Mine log files for real payloads, grouped by slug→code→[payloads].

    Returns: {slug: {code: [payload_hex, ...]}}
    """
    # Build index of which codes exist per slug in the DB
    import yaml  # noqa: PLC0415

    db_codes: dict[str, list[str]] = {}
    for subdir in ("hvac", "heat"):
        for yf in (db_dir / subdir).glob("*.yaml"):
            device_slug = yf.stem.upper()
            data = yaml.safe_load(yf.read_text(encoding="utf-8")) or {}
            codes = [str(e.get("code", "")) for e in (data.get("autonomous") or [])] + [
                str(e.get("code", "")) for e in (data.get("responses") or [])
            ]
            db_codes[device_slug] = codes

    # Collect payloads per slug+code+section, deduplicated
    # Key: (slug, code, section) → set of payload hex strings
    found: dict[str, dict[str, dict[str, set[str]]]] = {}
    total_frames = 0

    # RQ context window: track recent RQs so directed-I can be classified correctly.
    # rq_window[(dst_addr, code)] = last_seen_timestamp (float seconds)
    _rq_window_secs = 5.0
    _ts_re = re.compile(r"(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2})")
    rq_window: dict[tuple[str, str], float] = {}

    def _ts_from_line(line: str) -> float | None:
        m2 = _ts_re.search(line)
        if not m2:
            return None
        from datetime import datetime  # noqa: PLC0415

        try:
            return datetime.fromisoformat(m2.group(1).replace(" ", "T")).timestamp()
        except ValueError:
            return None

    for log_file in log_files:
        if not log_file.exists():
            print(f"  [skip] {log_file} not found")
            continue
        print(f"  Scanning {log_file} ...")
        rq_window.clear()
        with open(log_file, encoding="utf-8", errors="replace") as f:
            for line in f:
                m = _FRAME_RE.search(line)
                if not m:
                    continue
                _rssi, verb, src, dst, via, code, _length, payload = m.groups()
                verb = verb.strip()
                ts = _ts_from_line(line)

                # Track RQs: key is (requester_addr, code)
                if verb == "RQ":
                    key = (src, code)
                    rq_window[key] = ts or 0.0
                    continue

                # Drop W — we only want I/RP data frames
                if verb not in ("I", "RP"):
                    continue
                # Only care about frames from a real device (not HGI/gateway)
                if src.startswith(_GW_PREFIX) or src == _NULLADDR:
                    continue
                slug: str | None = _slug_from_frame(verb, src, dst, code, db_codes)
                if slug is None:
                    continue
                if code not in db_codes.get(slug, []):
                    continue

                # Check if there was a recent RQ from dst for this code
                rq_key = (dst, code)
                rq_ts = rq_window.get(rq_key)
                rq_seen = (
                    rq_ts is not None
                    and ts is not None
                    and 0 <= (ts - rq_ts) <= _rq_window_secs
                )

                section = _addr_section(verb, src, dst, via, code=code, rq_seen=rq_seen)
                found.setdefault(slug, {}).setdefault(code, {}).setdefault(
                    section, set()
                ).add(payload)
                total_frames += 1

    print(f"  Found {total_frames} usable frames across {len(found)} device types")
    # Convert sets to sorted lists: {slug: {code: {section: [payloads]}}}
    return {
        s: {
            c: {sec: sorted(ps) for sec, ps in secs.items()}
            for c, secs in codes.items()
        }
        for s, codes in found.items()
    }


def _score_payload(
    payload: str, code: str, slug: str, section: str = "autonomous"
) -> tuple[int, dict | None]:
    """Score a payload: higher = better candidate for DB. Returns (score, parsed)."""
    try:
        from features.device_simulator.system_config import (
            SIM_DEVICE_ID,  # noqa: PLC0415
        )

        src_id = SIM_DEVICE_ID.get(slug, "32:150000")
    except ImportError:
        src_id = "32:150000"
    frame = _build_frame(section, src_id, code, payload)
    parsed, err = _parse_frame(frame)
    if err or parsed is None:
        return -1, None
    sentinels = _has_sentinel(payload, code)
    _, implausible = _sentinel_ratio(payload, parsed)
    score = 100
    score -= len(sentinels) * 20
    score -= len(implausible) * 30
    none_vals = sum(1 for v in parsed.values() if v is None)
    score -= none_vals * 5
    return score, parsed


def update_db_from_logs(log_files: list[Path], db_dir: Path) -> None:
    """Extract real payloads from logs and update DB YAMLs in-place."""
    import yaml  # noqa: PLC0415

    extracted = extract_from_logs(log_files, db_dir)
    if not extracted:
        print("No usable frames found in logs.")
        return

    updated_count = 0
    for subdir in ("hvac", "heat"):
        for yaml_file in sorted((db_dir / subdir).glob("*.yaml")):
            slug = yaml_file.stem.upper()
            slug_data = extracted.get(slug)
            if not slug_data:
                continue

            data = yaml.safe_load(yaml_file.read_text(encoding="utf-8")) or {}
            changed = False

            for section_key in ("autonomous", "responses"):
                for entry in data.get(section_key) or []:
                    code = str(entry.get("code", ""))
                    # Look up candidates for this specific section, fall back to any
                    # section
                    code_data: dict[str, Any] | list[str] = slug_data.get(code, {})
                    if not isinstance(code_data, dict):
                        continue

                    candidates = list(
                        code_data.get(section_key, set())
                        or code_data.get("autonomous", set())
                        or code_data.get("responses", set())
                    )
                    if not candidates:
                        continue

                    # Score all candidates, pick best ones (up to 3)
                    scored = []
                    for payload in candidates:
                        score, parsed = _score_payload(payload, code, slug, section_key)
                        if score >= 0:
                            scored.append((score, payload, parsed))
                    scored.sort(key=lambda x: -x[0])

                    if not scored:
                        continue

                    # Only update if current payloads are missing or all bad
                    current = [
                        str(p).split("#")[0].strip()
                        for p in (entry.get("payloads") or [])
                    ]
                    current_scores = [
                        _score_payload(p, code, slug, section_key)[0]
                        for p in current
                        if p
                    ]
                    best_current = max(current_scores, default=-1)
                    best_new = scored[0][0]

                    if best_new <= best_current and current:
                        continue  # existing payloads are already at least as good

                    # Take up to 3 distinct best payloads
                    new_payloads = [p for _, p, _ in scored[:3]]
                    entry["payloads"] = new_payloads
                    entry["notes"] = (
                        f"Real captured payloads from log (score={scored[0][0]})"
                    )
                    changed = True
                    updated_count += 1
                    print(
                        f"  Updated {slug}/{code}: {len(new_payloads)} payload(s) "
                        f"(score {best_current}→{best_new})"
                    )

            if changed:
                with open(yaml_file, "w", encoding="utf-8") as f:
                    yaml.dump(
                        data,
                        f,
                        default_flow_style=False,
                        allow_unicode=True,
                        sort_keys=False,
                    )
                print(f"  Saved {yaml_file.name}")

    print(f"\nTotal: {updated_count} code entries updated in DB.")


# ---------------------------------------------------------------------------
# LLM-style audit (heuristic reasoning pass)
# ---------------------------------------------------------------------------

# Known-good field ranges for plausibility checking in audit remarks
_FIELD_DESCRIPTIONS: dict[str, str] = {
    "exhaust_fan_speed": "fan speed fraction 0.0–1.0",
    "supply_fan_speed": "fan speed fraction 0.0–1.0",
    "supply_flow": "airflow m³/h, expected >0 when fan running",
    "exhaust_flow": "airflow m³/h, expected >0 when fan running",
    "exhaust_temp": "temperature °C, plausible -10..50",
    "supply_temp": "temperature °C, plausible -10..50",
    "indoor_temp": "temperature °C, plausible 5..40",
    "outdoor_temp": "temperature °C, plausible -30..50",
    "indoor_humidity": "relative humidity 0.0–1.0",
    "outdoor_humidity": "relative humidity 0.0–1.0",
    "co2_level": "CO₂ ppm, plausible 300–5000",
    "air_quality": "AQ fraction 0.0–1.0",
    "bypass_position": "bypass valve 0.0–1.0 (0=closed)",
    "setpoint": "temperature °C setpoint, plausible 5..35",
    "temperature": "measured temperature °C, plausible -10..60",
}


def _llm_judge(entry: dict) -> tuple[str, str]:
    """Apply heuristic reasoning to an audit entry. Returns (audit, remark)."""
    quality = entry.get("quality", "")
    parsed = entry.get("parsed") or {}
    sentinels = entry.get("sentinels") or []
    implausible = entry.get("implausible") or []
    current_audit = entry.get("audit", "?")

    # Already decided — keep if human already filled in (only re-judge ? entries)
    if current_audit in ("Y", "N") and not implausible:
        return current_audit, entry.get("remark") or ""

    if quality == "no_fields":
        err = entry.get("remark", "")
        if "PacketPayloadInvalid" in err or "PacketInvalid" in err:
            return (
                "N",
                f"Parser rejects payload — wrong format or verb for this code. {err}",
            )
        return "?", f"No fields decoded — investigate. {err}"

    if quality in ("all_sentinel", "mostly_sentinel"):
        return (
            "N",
            "All/most fields are unavailable sentinels — payload is a placeholder, "
            "needs real capture.",
        )

    if quality == "implausible":
        details = "; ".join(implausible)
        return (
            "N",
            f"Values outside plausible ranges: {details}. Replace with real "
            f"captured payload.",
        )

    if quality == "ok" and not sentinels:
        # Check for suspiciously zeroed numeric fields
        zero_fields = [
            k
            for k, v in parsed.items()
            if isinstance(v, (int, float))
            and v == 0.0
            and k in _FIELD_DESCRIPTIONS
            and k not in _ZERO_OK
        ]
        if len(zero_fields) >= 3:
            return (
                "Remark",
                f"Many meaningful fields are zero ({', '.join(zero_fields)}) — may be "
                f"placeholder payload.",
            )
        return "Y", ""

    if quality == "ok" and sentinels:
        # Sentinels present but passed allowlist — fields still decode fine
        sentinel_str = ", ".join(sentinels)
        return (
            "Remark",
            f"Sentinel bytes present ({sentinel_str}) but remaining fields decode OK — "
            f"verify device has those sensors.",
        )

    return current_audit, entry.get("remark") or ""


def llm_audit(audit_yaml: Path, attention_only: bool = True) -> None:
    """Apply heuristic reasoning to every entry in an audit YAML, rewrite it.

    If attention_only=True, output only entries that need human review (N, Remark, ?).
    """
    import yaml  # noqa: PLC0415

    data = yaml.safe_load(audit_yaml.read_text(encoding="utf-8")) or []
    attention_entries = []
    y_count = n_count = remark_count = q_count = 0

    for block in data:
        new_payloads = []
        for pe in block.get("payloads") or []:
            audit, remark = _llm_judge({**block, **pe})
            pe["audit"] = audit
            pe["remark"] = remark or None
            if audit == "Y":
                y_count += 1
            elif audit == "N":
                n_count += 1
            elif audit == "Remark":
                remark_count += 1
            else:
                q_count += 1
            new_payloads.append(pe)
        block["payloads"] = new_payloads

        # Include in attention output if any payload needs review
        needs_attention = any(
            pe.get("audit") in ("N", "Remark", "?") for pe in new_payloads
        )
        if not attention_only or needs_attention:
            attention_entries.append(block)

    out_path = audit_yaml.with_stem(audit_yaml.stem + "_reviewed")
    with open(out_path, "w", encoding="utf-8") as f:
        yaml.dump(
            attention_entries if attention_only else data,
            f,
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False,
        )

    total = y_count + n_count + remark_count + q_count
    print(f"\nLLM audit complete: {total} payloads")
    print(f"  Y={y_count}  N={n_count}  Remark={remark_count}  ?={q_count}")
    print(f"  Attention needed: {len(attention_entries)} code blocks")
    print(f"  Written to {out_path}")


# ---------------------------------------------------------------------------
# Apply audit back to DB
# ---------------------------------------------------------------------------


def apply_audit(audit_yaml: Path, db_dir: Path) -> None:
    """Apply human-reviewed audit YAML decisions back to the device DB YAMLs.

    - audit: Y  → keep payload as-is
    - audit: N  → remove payload from DB
    - audit: Remark → keep but add inline comment in notes
    - audit: ?  → leave unchanged, emit warning
    """
    import yaml  # noqa: PLC0415

    data = yaml.safe_load(audit_yaml.read_text(encoding="utf-8")) or []

    # Build decision map: (device, section, code) → {payload_hex: (audit, remark)}
    decisions: dict[tuple, dict[str, tuple[str, str]]] = {}
    for block in data:
        key = (block["device"], block["section"], block["code"])
        decisions[key] = {}
        for pe in block.get("payloads") or []:
            decisions[key][pe["payload"]] = (
                pe.get("audit", "?"),
                pe.get("remark") or "",
            )

    removed = kept = remarked = skipped = 0

    for subdir in ("hvac", "heat"):
        for yaml_file in sorted((db_dir / subdir).glob("*.yaml")):
            slug = yaml_file.stem.upper()
            db_data = yaml.safe_load(yaml_file.read_text(encoding="utf-8")) or {}
            changed = False

            for section_key, verb in (("autonomous", "I"), ("responses", "RP")):
                for entry in db_data.get(section_key) or []:
                    code = str(entry.get("code", ""))
                    key = (slug, section_key, code)
                    if key not in decisions:
                        continue
                    code_decisions = decisions[key]

                    old_payloads = [
                        str(p).split("#")[0].strip()
                        for p in (entry.get("payloads") or [])
                    ]
                    new_payloads = []

                    for raw in entry.get("payloads") or []:
                        p = str(raw).split("#")[0].strip()
                        audit, remark = code_decisions.get(p, ("?", ""))
                        if audit == "Y":
                            new_payloads.append(raw)
                            kept += 1
                        elif audit == "N":
                            removed += 1
                            changed = True
                        elif audit == "Remark":
                            # Keep payload as clean hex; append remark to notes
                            new_payloads.append(p)
                            if remark:
                                existing_notes = entry.get("notes") or ""
                                tag = f"REMARK: {remark}"
                                if tag not in existing_notes:
                                    entry["notes"] = (
                                        f"{existing_notes}. {tag}".lstrip(". ")
                                        if existing_notes
                                        else tag
                                    )
                            remarked += 1
                            changed = True
                        else:  # ?
                            new_payloads.append(raw)
                            skipped += 1
                            print(
                                f"  [?] {slug}/{code} payload {p[:20]}... — "
                                f"unreviewed, kept"
                            )

                    if len(new_payloads) != len(old_payloads):
                        entry["payloads"] = new_payloads
                        changed = True

            if changed:
                with open(yaml_file, "w", encoding="utf-8") as f:
                    yaml.dump(
                        db_data,
                        f,
                        default_flow_style=False,
                        allow_unicode=True,
                        sort_keys=False,
                    )
                print(f"  Applied to {yaml_file.name}")

    print(
        f"\nApply complete: kept={kept}  removed={removed}  remarked={remarked} "
        f"skipped={skipped}"
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
_DEFAULT_LOG_FILES = [
    Path.home() / "docker_files" / "hass" / "config" / "ramses_log",
    Path.home() / "dev" / "ramses_extras" / "ha_nas.log",
    Path.home()
    / ".config"
    / "Windsurf.backup_20260312_193148"
    / "User"
    / "History"
    / "6cf4877a"
    / "WrcY.log",
    Path.home()
    / ".config"
    / "Windsurf.backup_20260312_193148"
    / "User"
    / "History"
    / "6cf4877a"
    / "4a2k.log",
    Path.home()
    / ".config"
    / "Windsurf.backup_20260312_193148"
    / "User"
    / "History"
    / "-3cdff0e7"
    / "ax0O.log",
]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Audit, enrich and apply device DB YAML payloads",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--device",
        "-d",
        help="Device type(s) to audit, comma-separated (default: all)",
        default=None,
    )
    parser.add_argument(
        "--output",
        "-o",
        help="Output YAML file (default: tools/audit_all.yaml or audit_<device>.yaml)",
        default=None,
    )
    parser.add_argument(
        "--extract-from-logs",
        nargs="*",
        metavar="LOG",
        help="Mine log files for real payloads and update DB YAMLs. "
        "Pass log file paths, or omit to use known default log locations.",
    )
    parser.add_argument(
        "--llm-audit",
        metavar="AUDIT_YAML",
        help="Apply heuristic audit to AUDIT_YAML, write *_reviewed.yaml with only "
        "attention-needed entries.",
    )
    parser.add_argument(
        "--apply-audit",
        metavar="AUDIT_YAML",
        help="Apply reviewed AUDIT_YAML decisions (Y/N/Remark) back to DB YAMLs.",
    )
    args = parser.parse_args()

    db_dir = (
        _REPO_ROOT
        / "custom_components"
        / "ramses_extras"
        / "features"
        / "device_simulator"
        / "device_db"
    )

    # --- Mode: extract from logs ---
    if args.extract_from_logs is not None:
        log_files = (
            [Path(f) for f in args.extract_from_logs]
            if args.extract_from_logs
            else _DEFAULT_LOG_FILES
        )
        print(f"Extracting from {len(log_files)} log file(s)...")
        update_db_from_logs(log_files, db_dir)
        return

    # --- Mode: llm-audit ---
    if args.llm_audit:
        llm_audit(Path(args.llm_audit))
        return

    # --- Mode: apply-audit ---
    if args.apply_audit:
        apply_audit(Path(args.apply_audit), db_dir)
        return

    # --- Default mode: audit ---
    if args.device:
        devices = [d.strip().upper() for d in args.device.split(",")]
    else:
        devices = sorted(
            p.stem
            for subdir in ("hvac", "heat")
            for p in (db_dir / subdir).glob("*.yaml")
        )

    all_entries: list[dict] = []
    for slug in devices:
        print(f"Auditing {slug}...")
        entries = audit_device(slug, db_dir)
        all_entries.extend(entries)
        print(f"  {len(entries)} entries")

    print_summary(all_entries)

    if args.output:
        out_path = Path(args.output)
    elif args.device and "," not in args.device:
        out_path = _REPO_ROOT / "tools" / f"audit_{args.device.lower()}.yaml"
    else:
        out_path = _REPO_ROOT / "tools" / "audit_all.yaml"

    write_audit_yaml(all_entries, out_path)


if __name__ == "__main__":
    main()
