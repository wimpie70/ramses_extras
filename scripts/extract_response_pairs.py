#!/usr/bin/env python3
"""Extract RQ→RP and I→W response pairs from harvested conversations.

This script extracts valid response pairs from harvested conversation YAML files
and merges them into device type YAML files for automatic answering.
"""

import argparse
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

import yaml

# Device database directory
DEVICE_DB_DIR = (
    Path(__file__).parent.parent
    / "custom_components"
    / "ramses_extras"
    / "features"
    / "device_simulator"
    / "device_db"
)
CONVERSATIONS_DIR = DEVICE_DB_DIR / "conversations"

# src prefix → device type slug (from build_device_db.py)
PREFIX_MAP: dict[str, str] = {
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


def get_device_type_from_id(device_id: str) -> str | None:
    """Get device type slug from device ID.

    :param device_id: Device ID (e.g., '37:154011' or '--:------')
    :return: Device type slug or None if unknown
    """
    if device_id == "--:------" or device_id == "ALL":
        return None
    prefix = device_id.split(":")[0] if ":" in device_id else ""
    return PREFIX_MAP.get(prefix)


def extract_response_pairs(conversations_dir: Path) -> dict[str, dict[str, set[str]]]:
    """Extract RQ→RP and I→W pairs from conversation YAML files.

    Returns {device_type: {code: {payloads}}}.

    :param conversations_dir: Path to conversations directory
    """
    # Structure: {device_type: {code: set of payloads}}
    response_data: dict[str, dict[str, set[str]]] = defaultdict(
        lambda: defaultdict(set)
    )

    for yaml_file in sorted(conversations_dir.glob("*.yaml")):
        if yaml_file.name == ".gitkeep":
            continue

        try:
            with open(yaml_file, encoding="utf-8") as f:
                data = yaml.safe_load(f)

            if not data or "frames" not in data:
                continue

            frames = data["frames"]
            print(f"Processing {yaml_file.name}: {len(frames)} frames")

            # Build a lookup by (src, code) to find matching responses
            # We need to find RQ→RP and I→W pairs where response.src == request.dst
            for i, frame in enumerate(frames):
                src = frame.get("src")
                dst = frame.get("dst")
                code = frame.get("code")
                verb = frame.get("verb")
                payload = frame.get("payload")

                if not all([src, dst, code, verb, payload]):
                    continue

                # Skip broadcast destinations for requests
                if dst in ("--:------", "ALL") and verb in ("RQ", "I"):
                    continue

                # Get device type of the responder (dst for RQ/I)
                responder_device_type = get_device_type_from_id(dst)
                if not responder_device_type:
                    continue

                # Look for matching response in subsequent frames
                # Response should have: src == original dst, same code
                # Valid patterns: RQ→RP, I→W, W→I, W→RP
                for j in range(
                    i + 1, min(i + 10, len(frames))
                ):  # Look ahead up to 10 frames
                    next_frame = frames[j]
                    next_src = next_frame.get("src")
                    next_code = next_frame.get("code")
                    next_verb = next_frame.get("verb")
                    next_payload = next_frame.get("payload")

                    # Check if this is a valid response
                    if (
                        next_src == dst  # Response comes from request destination
                        and next_code == code  # Same code
                        and (
                            (verb == "RQ" and next_verb == "RP")
                            or (verb == "I" and next_verb == "W")
                            or (verb == "W" and next_verb == "I")
                            or (verb == "W" and next_verb == "RP")
                        )
                    ):
                        # Valid response pair found
                        response_data[responder_device_type][code].add(next_payload)
                        print(
                            f"  Found {verb}→{next_verb} pair: {code} "
                            f"from {src} → {dst} (payload: {next_payload[:20]}...)"
                        )
                        break  # Found the response, stop looking

        except Exception as e:
            print(f"Error processing {yaml_file.name}: {e}")

    return dict(response_data)


def load_device_type_yaml(yaml_file: Path) -> dict[str, Any]:
    """Load a device type YAML file.

    :param yaml_file: Path to device type YAML
    :return: Parsed YAML data or empty dict
    """
    try:
        with open(yaml_file, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception as e:
        print(f"Error loading {yaml_file}: {e}")
        return {}


def save_device_type_yaml(yaml_file: Path, data: dict[str, Any]) -> None:
    """Save a device type YAML file.

    :param yaml_file: Path to device type YAML
    :param data: YAML data to save
    """
    try:
        with open(yaml_file, "w", encoding="utf-8") as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False)
        print(f"Saved {yaml_file}")
    except Exception as e:
        print(f"Error saving {yaml_file}: {e}")


def merge_response_pairs(
    device_db_dir: Path,
    response_data: dict[str, dict[str, set[str]]],
) -> int:
    """Merge extracted response pairs into device type YAML files.

    :param device_db_dir: Path to device_db directory
    :param response_data: Extracted response data
    :return: Number of device types updated
    """
    updated = 0

    for device_type, code_payloads in response_data.items():
        if not code_payloads:
            continue

        # Determine domain (heat vs hvac)
        # HVAC devices: FAN, CO2, REM
        # Heat devices: CTL, TRV, BDR, OTB, GWY, RFG
        hvac_types = {"FAN", "CO2", "REM"}
        domain = "hvac" if device_type in hvac_types else "heat"

        # Find device type YAML file
        device_file = device_db_dir / domain / f"{device_type.lower()}.yaml"

        if not device_file.exists():
            print(f"Device type file not found: {device_file}")
            # Create new device type file
            device_data = {
                "device_type": device_type,
                "domain": domain,
                "broadcast_safe": False,
                "variants": [],
                "autonomous": [],
                "responses": [],
                "conversation_refs": [],
            }
        else:
            device_data = load_device_type_yaml(device_file)

        # Merge response entries
        if "responses" not in device_data:
            device_data["responses"] = []

        # Build a map of existing responses by code
        existing_responses = {r["code"]: r for r in device_data["responses"]}

        for code, payloads in code_payloads.items():
            payloads_list = sorted(payloads)

            if code in existing_responses:
                # Merge payloads with existing
                existing = existing_responses[code]
                existing_payloads = set(existing.get("payloads", []))
                merged_payloads = sorted(existing_payloads.union(payloads))
                existing["payloads"] = merged_payloads
                print(
                    f"  Merged {len(payloads)} payloads into "
                    f"existing {code} response for {device_type}"
                )
            else:
                # Add new response entry
                new_response = {
                    "code": code,
                    "rq_verb": "RQ",
                    "rp_verb": "RP",
                    "delay_ms": 100,
                    "payloads": payloads_list,
                    "notes": "Extracted from harvested conversations",
                }
                device_data["responses"].append(new_response)
                print(
                    f"  Added new {code} response for {device_type} "
                    f"with {len(payloads_list)} payloads"
                )

        # Sort responses by code
        device_data["responses"] = sorted(
            device_data["responses"], key=lambda x: x["code"]
        )

        # Save device type file
        save_device_type_yaml(device_file, device_data)
        updated += 1

    return updated


def main():
    parser = argparse.ArgumentParser(
        description="Extract response pairs from conversations"
    )
    parser.add_argument(
        "--conversations-dir",
        type=Path,
        default=CONVERSATIONS_DIR,
        help="Path to conversations directory",
    )
    parser.add_argument(
        "--device-db-dir",
        type=Path,
        default=DEVICE_DB_DIR,
        help="Path to device_db directory",
    )

    args = parser.parse_args()

    if not args.conversations_dir.exists():
        print(f"Error: conversations directory not found: {args.conversations_dir}")
        return 1

    print("Extracting response pairs from conversations...")
    response_data = extract_response_pairs(args.conversations_dir)

    print(f"\nExtracted data for {len(response_data)} device types:")
    for device_type, code_payloads in response_data.items():
        print(f"  {device_type}: {len(code_payloads)} codes")
        for code, payloads in code_payloads.items():
            print(f"    {code}: {len(payloads)} payloads")

    print("\nMerging response pairs into device type files...")
    updated = merge_response_pairs(args.device_db_dir, response_data)

    print(f"\nUpdated {updated} device type files")
    return 0


if __name__ == "__main__":
    exit(main())
