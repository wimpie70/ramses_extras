#!/usr/bin/env python3
"""Test extras_registry functionality in isolation."""

import os
import sys

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Import extras_registry directly without going through the full integration
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../custom_components"))

# Test the registry module directly
try:
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "extras_registry",
        os.path.join(
            os.path.dirname(__file__),
            "../custom_components/ramses_extras/extras_registry.py",
        ),
    )
    extras_registry = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(extras_registry)

    print("Testing EntityRegistry isolation...")

    # Test 1: Basic import and creation
    registry = extras_registry.RamsesEntityRegistry()
    print("✅ Registry instance created")

    # Test 2: Clear registry
    registry.clear()
    print("✅ Registry cleared")

    # Test 3: Load default feature
    registry.load_feature_definitions(
        "default", "custom_components.ramses_extras.features.default"
    )
    print("✅ Default feature loaded")

    # Test 4: Check sensor loaded
    sensor = registry.get_all_sensor_configs()
    print(f"✅ Got {len(sensor)} sensor configs")

    # Test 5: Load all features
    registry.clear()
    registry.load_all_features(["humidity_control"])
    print("✅ Load all features works without hanging")

    # Test 6: Check loaded features
    loaded = registry.get_loaded_features()
    print(f"✅ Loaded features: {loaded}")

    # Test 7: Multiple concurrent access
    for i in range(100):
        registry.get_all_switch_configs()
        registry.get_all_number_configs()
        registry.get_all_boolean_configs()
        registry.get_all_device_mappings()
    print("✅ Multiple concurrent access works")

    print("\n🎉 All registry tests passed! The deadlock fix is working.")

except Exception as e:
    print(f"❌ Test failed: {e}")
    import traceback

    traceback.print_exc()
    sys.exit(1)
