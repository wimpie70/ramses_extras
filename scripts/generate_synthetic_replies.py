#!/usr/bin/env python3
"""Generate synthetic replies for missing device type codes based on command structures."""  # noqa: E501

# Synthetic reply patterns based on command structures
# Format: (code, rq_verb, rp_verb, synthetic_payloads)
SYNTHETIC_REPLIES = {
    # DHW codes
    "1F41": {
        "rq_verb": "RQ",
        "rp_verb": "RP",
        "payloads": [
            "00FF0000FFFFFF",  # Mode: follow, inactive, no duration
            "00010000FFFFFF",  # Mode: 00, active, no duration
            "0001010000003C",  # Mode: 01, active, 60s duration
        ],
        "notes": "DHW mode responses - synthetic based on command structure",
    },
    # THM (zone) codes
    "0004": {
        "rq_verb": "RQ",
        "rp_verb": "RP",
        "payloads": [
            "004C697665726F6F6D202020202020202020202020202020202020202020202020",  # noqa: E501
            "014B69746368656E202020202020202020202020202020202020202020202020",  # noqa: E501
        ],
        "notes": "Zone name responses - synthetic based on command structure",
    },
    "000A": {
        "rq_verb": "RQ",
        "rp_verb": "RP",
        "payloads": [
            "001423",  # Min 20C, Max 35C, bitmap 0x00
            "031423",  # Min 20C, Max 35C, bitmap 0x03
        ],
        "notes": "Zone config responses - synthetic based on command structure",
    },
    "12B0": {
        "rq_verb": "RQ",
        "rp_verb": "RP",
        "payloads": [
            "00",  # Window state 00
            "01",  # Window state 01
        ],
        "notes": "Zone window state responses - synthetic based on command structure",
    },
    "2309": {
        "rq_verb": "RQ",
        "rp_verb": "RP",
        "payloads": [
            "14",  # Setpoint 20C
            "16",  # Setpoint 22C
            "18",  # Setpoint 24C
        ],
        "notes": "Zone setpoint responses - synthetic based on command structure",
    },
    "30C9": {
        "rq_verb": "RQ",
        "rp_verb": "RP",
        "payloads": [
            "0C",  # Temp 12C
            "14",  # Temp 20C
            "1E",  # Temp 30C
        ],
        "notes": "Zone temperature responses - synthetic based on command structure",
    },
}


def generate_synthetic_yaml_entries() -> dict[str, dict]:
    """Generate YAML entries for synthetic replies."""
    entries = {}

    for code, data in SYNTHETIC_REPLIES.items():
        entries[code] = {
            "code": code,
            "rq_verb": data["rq_verb"],
            "rp_verb": data["rp_verb"],
            "delay_ms": 100,
            "payloads": data["payloads"],
            "notes": data["notes"],
        }

    return entries


def main():
    """Main entry point."""
    entries = generate_synthetic_yaml_entries()

    print("Synthetic reply entries generated:")
    print("=" * 60)
    for code, entry in entries.items():
        print(f"\nCode: {entry['code']}")
        print(f"  RQ→RP: {entry['rq_verb']}→{entry['rp_verb']}")
        print(f"  Payloads: {len(entry['payloads'])} entries")
        print(f"  Notes: {entry['notes']}")
        for payload in entry["payloads"][:2]:  # Show first 2
            print(f"    - {payload}")
        if len(entry["payloads"]) > 2:
            print(f"    ... and {len(entry['payloads']) - 2} more")

    print("\n" + "=" * 60)
    print("These entries can be merged into device type YAML files.")
    print("DHW missing: 1F41")
    print("THM missing: 0004, 000A, 12B0, 2309, 30C9")

    return entries


if __name__ == "__main__":
    main()
