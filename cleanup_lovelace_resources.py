#!/usr/bin/env python3
"""
Cleanup script for lovelace_resources file.

This script removes old/duplicate hvac-fan-card entries from the lovelace_resources
file, keeping only the correct path:
/local/ramses_extras/features/hvac_fan_card/hvac-fan-card.js

Usage:
    sudo python3 cleanup_lovelace_resources.py
"""

import json
import sys
from pathlib import Path

# Path to lovelace_resources file
LOVELACE_RESOURCES_PATH = Path(
    "/home/willem/docker_files/hass/config/.storage/lovelace_resources"
)


def cleanup_lovelace_resources() -> None:
    """Clean up old hvac-fan-card entries from lovelace_resources."""

    if not LOVELACE_RESOURCES_PATH.exists():
        print(f"❌ Error: File not found: {LOVELACE_RESOURCES_PATH}")
        sys.exit(1)

    # Read the lovelace_resources file
    print(f"📖 Reading {LOVELACE_RESOURCES_PATH}")
    with open(LOVELACE_RESOURCES_PATH) as f:
        data = json.load(f)

    # Filter out old hvac-fan-card entries, keeping only the correct one
    correct_url = "/local/ramses_extras/features/hvac_fan_card/hvac-fan-card.js"
    filtered_items = []
    found_correct = False
    removed_count = 0

    for item in data.get("items", []):
        url = item.get("url", "")
        # Keep non-hvac entries
        if "hvac" not in url.lower():
            filtered_items.append(item)
        # Keep only the correct hvac-fan-card entry
        elif url == correct_url and not found_correct:
            filtered_items.append(item)
            found_correct = True
            print(f"✅ Keeping correct entry: {url}")
        else:
            print(f"🗑️  Removing old entry: {url}")
            removed_count += 1

    # Update the data
    data["items"] = filtered_items

    # Write back to file
    print(f"\n💾 Writing cleaned data back to {LOVELACE_RESOURCES_PATH}")
    with open(LOVELACE_RESOURCES_PATH, "w") as f:
        json.dump(data, f, indent=4)

    print("\n✅ Cleaned up lovelace_resources file")
    print(f"📊 Total entries: {len(filtered_items)}")
    print(f"🗑️  Removed entries: {removed_count}")

    if not found_correct:
        print("\n⚠️  Warning: Correct entry not found in file!")
        print(f"   Expected: {correct_url}")
        print("   You may need to restart Home Assistant to register the card.")


if __name__ == "__main__":
    try:
        cleanup_lovelace_resources()
    except PermissionError:
        print("\n❌ Permission denied. Please run with sudo:")
        print("   sudo python3 cleanup_lovelace_resources.py")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
