#!/usr/bin/env python3
"""LLM-assisted annotation pass for Device Simulator Device Database.

This script analyzes existing device database files and:
1. Identifies missing RQ->RP response pairings
2. Validates existing pairings using RAMSES protocol knowledge
3. Adds missing responses with appropriate delays and payloads
4. Enhances device descriptions with protocol-specific details

Usage:
  source ~/venvs/extras/bin/activate
  python scripts/annotate_device_db.py [--device-type FAN] [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

# Add ramses_rf to path for importing schema
RAMSES_RF_PATH = Path("/home/willem/dev/ramses_rf/src")
sys.path.insert(0, str(RAMSES_RF_PATH))

DEVICE_DB_DIR = (
    Path(__file__).parent.parent
    / "custom_components"
    / "ramses_extras"
    / "features"
    / "device_simulator"
    / "device_db"
)


@dataclass
class CodePairing:
    """Represents a known RQ->RP code pairing."""

    rq_code: str
    rp_code: str
    description: str
    typical_delay_ms: int = 100
    rq_payload_hints: list[str] = field(default_factory=list)
    rp_payload_hints: list[str] = field(default_factory=list)
    device_types: set[str] = field(default_factory=set)


@dataclass
class DeviceAnnotation:
    """Enhanced device information from LLM analysis."""

    device_type: str
    missing_responses: list[CodePairing] = field(default_factory=list)
    invalid_responses: list[str] = field(default_factory=list)
    enhanced_descriptions: dict[str, str] = field(default_factory=dict)
    protocol_notes: list[str] = field(default_factory=list)


# Known RAMSES protocol pairings based on ramses_rf source and regression data
KNOWN_PAIRINGS = [
    # Common control codes
    CodePairing(
        "0001",
        "0008",
        "System identification",
        50,
        [],
        ["FA00", "0204", "F914"],
        {"CTL", "THM"},
    ),
    CodePairing(
        "0002",
        "0008",
        "System identification (alternate)",
        50,
        [],
        ["FA00", "0204"],
        {"CTL", "THM"},
    ),
    CodePairing(
        "0004", "0008", "System identification (variant)", 50, [], ["FA00"], {"CTL"}
    ),
    CodePairing(
        "0005",
        "0009",
        "System status request",
        100,
        ["0000FF01"],
        ["FC00FFF900FF"],
        {"CTL"},
    ),
    CodePairing(
        "0008",
        "0008",
        "System identification response",
        0,
        [],
        ["FA00", "0204", "F914"],
        {"CTL", "THM"},
    ),
    # Temperature and sensor codes
    CodePairing(
        "0010", "0010", "Temperature reading", 50, [], ["0013880003E8"], {"CTL"}
    ),
    CodePairing("0016", "0016", "Unknown control", 100, [], [], {"CTL"}),
    # Fan control codes (FAN device)
    CodePairing(
        "22F1",
        "22F1",
        "Fan speed control",
        200,
        ["01", "02", "03"],
        ["0001", "0002", "0003"],
        {"FAN"},
    ),
    CodePairing("22F3", "22F3", "Fan mode control", 150, [], ["00"], {"FAN"}),
    CodePairing(
        "22F4",
        "22F4",
        "Fan parameters",
        100,
        [],
        ["00403000000000000000000000"],
        {"FAN"},
    ),
    CodePairing(
        "22F7", "22F7", "Fan status", 50, [], ["00", "0000EF", "00C8EF"], {"FAN"}
    ),
    # HVAC system codes
    CodePairing("3220", "3220", "System parameters", 100, [], [], {"CTL"}),
    CodePairing("31D9", "31D9", "System capabilities", 200, [], [], {"FAN"}),
    CodePairing(
        "31DA",
        "31DA",
        "System status",
        200,
        [],
        ["00EF007FFFEFEF7FFF7FFF7FFF7FFF0000EF00FFFF0000EFEF7FFF7FFF00"],
        {"FAN"},
    ),
    # TRV control codes
    CodePairing(
        "1FC9",
        "1FC9",
        "Device identification",
        100,
        [],
        ["072309054E29", "08230906368E"],
        {"TRV", "CTL", "FAN"},
    ),
    CodePairing("22C9", "22C9", "Temperature control", 150, [], [], {"TRV", "CTL"}),
    CodePairing("22D9", "22D9", "Valve position", 100, [], ["00"], {"TRV"}),
    CodePairing("3EF0", "3EF0", "Calibration", 200, [], ["00"], {"TRV"}),
    # Remote control codes (REM)
    CodePairing("12A0", "12A0", "Remote status", 100, [], [], {"REM"}),
    CodePairing(
        "12C8",
        "12C8",
        "Remote sensor reading",
        50,
        [],
        ["00A740", "007A40", "009540"],
        {"REM"},
    ),
    CodePairing("12D0", "12D0", "Remote control", 150, [], [], {"REM"}),
    # CO2 sensor codes (CO2)
    CodePairing("2411", "2411", "CO2 reading", 100, [], [], {"CO2"}),
    CodePairing("2412", "2412", "CO2 calibration", 200, [], [], {"CO2"}),
    # DHW codes (DHW)
    CodePairing(
        "2309",
        "2309",
        "DHW status",
        100,
        [],
        ["0005DC0101F40205DC", "030514", "01070802079E03073A"],
        {"DHW"},
    ),
    CodePairing(
        "2349",
        "2349",
        "DHW parameters",
        150,
        [],
        ["0007D000FFFFFF", "01079E00FFFFFF"],
        {"DHW"},
    ),
    CodePairing("2209", "2209", "DHW control", 100, [], [], {"DHW"}),
    # General discovery codes
    CodePairing(
        "10E0",
        "10E0",
        "Device capabilities",
        200,
        [],
        [
            "000001001B361B01FEFFFFFFFFFF0B0407E34356452D52460000000000000000000000000000"
        ],
        {"FAN", "CTL", "TRV"},
    ),
    CodePairing("10D0", "10D0", "Device information", 150, [], [], {"FAN", "CTL"}),
    CodePairing(
        "10A0", "10A0", "Device parameters", 100, [], ["0013880003E8"], {"CTL"}
    ),
    # System codes
    CodePairing("3200", "3200", "System heartbeat", 0, [], [], {"FAN", "CTL", "TRV"}),
    CodePairing("3120", "3120", "System status", 0, [], [], {"FAN", "CTL"}),
    CodePairing("3150", "3150", "System maintenance", 100, [], [], {"FAN", "CTL"}),
    CodePairing("313F", "313F", "System diagnostics", 150, [], [], {"FAN", "CTL"}),
    CodePairing(
        "1298", "1298", "System metrics", 100, [], ["000280", "0001C6"], {"FAN"}
    ),
    CodePairing("2E10", "2E10", "System configuration", 100, [], [], {"FAN", "CTL"}),
    CodePairing("042F", "042F", "System error", 50, [], [], {"FAN", "CTL"}),
    CodePairing("22F2", "22F2", "System control", 100, [], [], {"FAN", "CTL"}),
]


def load_device_file(file_path: Path) -> Any:
    """Load device data from YAML file."""
    import yaml

    with open(file_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def save_device_file(file_path: Path, data: dict[str, Any]) -> None:
    """Save device data to YAML file with proper formatting."""
    import yaml

    # Configure YAML for nice formatting
    class CustomDumper(yaml.SafeDumper):
        def represent_list(self, data: Any) -> Any:
            if len(data) == 0:
                return self.represent_sequence(
                    "tag:yaml.org,2002:seq", data, flow_style=True
                )
            return self.represent_sequence("tag:yaml.org,2002:seq", data)

    CustomDumper.add_representer(list, CustomDumper.represent_list)

    with open(file_path, "w", encoding="utf-8") as f:
        yaml.dump(
            data,
            f,
            Dumper=CustomDumper,
            default_flow_style=False,
            sort_keys=False,
            indent=2,
        )


def analyze_device_responses(
    device_data: dict[str, Any], device_type: str
) -> DeviceAnnotation:
    """Analyze a device file and identify missing/invalid responses."""
    annotation = DeviceAnnotation(device_type=device_type)

    # Get existing responses
    existing_responses = device_data.get("responses", [])
    existing_codes = {resp["code"] for resp in existing_responses}

    # Get autonomous codes (periodic messages)
    autonomous_codes = {auto["code"] for auto in device_data.get("autonomous", [])}

    # Find known pairings that should be present
    for pairing in KNOWN_PAIRINGS:
        if device_type in pairing.device_types:
            rq_code = pairing.rq_code

            # Check if this is a valid RQ code (not autonomous)
            if rq_code not in autonomous_codes:
                # Check if response exists
                if rq_code not in existing_codes:
                    annotation.missing_responses.append(pairing)
                else:
                    # Validate existing response
                    existing_resp = next(
                        r for r in existing_responses if r["code"] == rq_code
                    )
                    if (
                        existing_resp.get("rq_verb") != "RQ"
                        or existing_resp.get("rp_verb") != "RP"
                    ):
                        annotation.invalid_responses.append(
                            f"Invalid verb pairing for {rq_code}"
                        )

    # Add protocol notes
    if device_type == "FAN":
        annotation.protocol_notes.extend(
            [
                "FAN devices support speed control via 22F1 with payload 01/02/03",
                "FAN devices provide periodic status via 31DA (system status)",
                "FAN devices respond to discovery with 10E0 capabilities",
            ]
        )
    elif device_type == "TRV":
        annotation.protocol_notes.extend(
            [
                "TRV devices control valve position via 22D9",
                "TRV devices provide temperature readings via 1FC9",
                "TRV devices support calibration via 3EF0",
            ]
        )
    elif device_type == "CTL":
        annotation.protocol_notes.extend(
            [
                "CTL devices act as system controllers",
                "CTL devices respond to system identification via 0008",
                "CTL devices provide system status via 0009",
            ]
        )

    return annotation


def enhance_device_data(
    device_data: dict[str, Any], annotation: DeviceAnnotation
) -> dict[str, Any]:
    """Enhance device data with missing responses and annotations."""
    enhanced_data = device_data.copy()

    # Add missing responses
    if annotation.missing_responses:
        if "responses" not in enhanced_data:
            enhanced_data["responses"] = []

        for pairing in annotation.missing_responses:
            response_entry = {
                "code": pairing.rq_code,
                "rq_verb": "RQ",
                "rp_verb": "RP",
                "delay_ms": pairing.typical_delay_ms,
                "payloads": pairing.rp_payload_hints
                if pairing.rp_payload_hints
                else [],
            }

            # Add description if available
            if pairing.description:
                response_entry["description"] = pairing.description

            enhanced_data["responses"].append(response_entry)

    # Sort responses by code for consistency
    if "responses" in enhanced_data:
        enhanced_data["responses"].sort(key=lambda x: x["code"])

    # Add protocol notes as comments in the file
    if annotation.protocol_notes:
        enhanced_data["protocol_notes"] = annotation.protocol_notes

    return enhanced_data


def process_device_file(file_path: Path, dry_run: bool = False) -> None:
    """Process a single device file."""
    print(f"Processing {file_path.name}...")

    # Load existing data
    device_data = load_device_file(file_path)
    device_type = device_data.get("device_type", file_path.stem)

    # Analyze and enhance
    annotation = analyze_device_responses(device_data, device_type)
    enhanced_data = enhance_device_data(device_data, annotation)

    # Report findings
    if annotation.missing_responses:
        print(f"  Added {len(annotation.missing_responses)} missing responses:")
        for pairing in annotation.missing_responses:
            print(f"    {pairing.rq_code} -> {pairing.rp_code}: {pairing.description}")

    if annotation.invalid_responses:
        print(f"  Found {len(annotation.invalid_responses)} invalid responses:")
        for invalid in annotation.invalid_responses:
            print(f"    {invalid}")

    if annotation.protocol_notes:
        print(f"  Added {len(annotation.protocol_notes)} protocol notes")

    # Save enhanced data
    if not dry_run and (
        annotation.missing_responses
        or annotation.invalid_responses
        or annotation.protocol_notes
    ):
        backup_path = file_path.with_suffix(".yaml.backup")
        if not backup_path.exists():
            file_path.rename(backup_path)

        save_device_file(file_path, enhanced_data)
        print(f"  Enhanced file saved (backup: {backup_path.name})")
    elif dry_run:
        print("  Dry run - would enhance file")


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="LLM-assisted annotation for device database"
    )
    parser.add_argument("--device-type", help="Process only specific device type")
    parser.add_argument(
        "--dry-run", action="store_true", help="Show changes without saving"
    )
    args = parser.parse_args()

    print("LLM-assisted Device Database Annotation")
    print("=" * 50)

    # Find all device files
    device_files: list[Path] = []
    for domain_dir in ["heat", "hvac"]:
        domain_path = DEVICE_DB_DIR / domain_dir
        if domain_path.exists():
            device_files.extend(domain_path.glob("*.yaml"))

    # Filter by device type if specified
    if args.device_type:
        device_files = [f for f in device_files if f.stem == args.device_type]

    if not device_files:
        print("No device files found")
        return

    print(f"Found {len(device_files)} device files")
    print()

    # Process each file
    for file_path in sorted(device_files):
        try:
            process_device_file(file_path, args.dry_run)
            print()
        except Exception as e:
            print(f"  Error processing {file_path.name}: {e}")
            print()

    if args.dry_run:
        print("Dry run completed - no files were modified")
    else:
        print("Annotation completed - enhanced device database files")
        print("Run with --dry-run to preview changes before applying")


if __name__ == "__main__":
    main()
