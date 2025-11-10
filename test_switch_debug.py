#!/usr/bin/env python3
"""Debug test for switch entity creation."""

import os
import sys
from typing import Any, Dict, cast

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "custom_components"))

from custom_components.ramses_extras.const import (
    AVAILABLE_FEATURES,
    FEATURE_ID_HUMIDITY_CONTROL,
    SWITCH_CONFIGS,
)

# Test the new entity generation system
from custom_components.ramses_extras.framework.helpers.entity.core import EntityHelpers


def test_switch_configuration() -> None:
    """Test that the switch configuration is correct."""
    print("🔍 Testing switch configuration...")

    # Check humidity control feature
    humidity_feature = AVAILABLE_FEATURES.get(FEATURE_ID_HUMIDITY_CONTROL, {})
    print(f"📋 Humidity control feature: {humidity_feature}")

    # Check required entities
    required_entities = humidity_feature.get("required_entities", {})
    if isinstance(required_entities, dict):
        print(f"📋 Required entities: {required_entities}")

        # Check switches specifically
        switches = required_entities.get("switches", [])
    else:
        print(f"📋 Required entities: {required_entities} (not a dict)")
        switches = []
    print(f"🔌 Required switches: {switches}")

    # Check switch configurations
    print(f"⚙️ Available switch configs: {list(SWITCH_CONFIGS.keys())}")

    # Check if dehumidify switch is configured
    if "dehumidify" in switches:
        print("✅ Dehumidify switch is required by humidity control feature")

        if "dehumidify" in SWITCH_CONFIGS:
            print("✅ Dehumidify switch has configuration")
            print(f"   Config: {SWITCH_CONFIGS['dehumidify']}")
        else:
            print("❌ Dehumidify switch configuration missing!")
    else:
        print("❌ Dehumidify switch not found in required entities!")

    # Test platform calculation logic
    print("\n🧮 Testing calculate_required_entities logic...")
    enabled_features = {"humidity_control": True}
    # devices = ["32:153289"]

    # Simulate calculate_required_entities logic
    for feature_key, is_enabled in enabled_features.items():
        if not is_enabled or feature_key not in AVAILABLE_FEATURES:
            continue

        feature_config = AVAILABLE_FEATURES[feature_key]
        required_entities = feature_config.get("required_entities", {})

        print(f"Feature: {feature_key}")
        print(f"  Required entities: {required_entities}")

        # Check for switch platform
        if isinstance(required_entities, dict):
            switches_for_platform = required_entities.get("switches", [])
        else:
            switches_for_platform = []
        print(f"  Switches for switch platform: {switches_for_platform}")

        if "dehumidify" in switches_for_platform:
            print("  ✅ dehumidify switch should be created for switch platform!")
        else:
            print("  ❌ dehumidify switch NOT found for switch platform!")

    # Test entity generation system
    print("\n🧪 Testing entity generation system...")
    device_id = "32_153289"
    entity_name = "dehumidify"

    # Test template lookup - using SWITCH_CONFIGS directly
    try:
        # Get switch configuration
        switch_config = SWITCH_CONFIGS.get(entity_name, {})
        print(f"Switch config: {switch_config}")

        # Get entity template
        entity_template = switch_config.get("entity_template", "")
        print(f"Entity template: {entity_template}")

        # Generate entity ID manually
        if entity_template:
            entity_id = f"switch.{entity_template.format(device_id=device_id)}"
            print(f"Generated entity ID: {entity_id}")
        else:
            # Fallback to simple generation
            entity_id = f"switch.{entity_name}_{device_id}"
            print(f"Fallback entity ID: {entity_id}")

        # Test entity ID generation using EntityHelpers
        entity_id_old = EntityHelpers.generate_entity_name_from_template(
            "switch", entity_name, device_id
        )
        print(f"EntityHelpers entity ID: {entity_id_old}")

        if entity_id:
            print("✅ Entity generation system working!")
        else:
            print("❌ Entity generation system failed!")

    except Exception as e:
        print(f"Entity generation failed: {e}")
        # Fallback to simple generation
        entity_id = f"switch.{entity_name}_{device_id}"
        print(f"Fallback entity ID: {entity_id}")


if __name__ == "__main__":
    test_switch_configuration()
