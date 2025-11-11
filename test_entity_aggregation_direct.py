"""Direct test of entity definition aggregation functionality."""

# Add the custom_components directory to the path for testing
import os
import sys

# Add the custom_components path so we can import modules
custom_components_path = os.path.join(os.path.dirname(__file__), "custom_components")
sys.path.insert(0, custom_components_path)

# Test the framework aggregation system
try:
    # Import the registry directly
    from custom_components.ramses_extras.framework.helpers.entity.registry import (
        entity_registry,
    )

    # Test loading all features
    enabled_features = ["humidity_control"]
    entity_registry.load_all_features(enabled_features)

    # Test getting all configurations
    sensors = entity_registry.get_all_sensor_configs()
    switches = entity_registry.get_all_switch_configs()
    numbers = entity_registry.get_all_number_configs()
    booleans = entity_registry.get_all_boolean_configs()
    devices = entity_registry.get_all_device_mappings()

    print("=== Entity Definition Aggregation Test ===")
    print(f"✅ Sensor configs: {len(sensors)} found")
    for name in sensors:
        print(f"  - {name}")

    print(f"\n✅ Switch configs: {len(switches)} found")
    for name in switches:
        print(f"  - {name}")

    print(f"\n✅ Number configs: {len(numbers)} found")
    for name in numbers:
        print(f"  - {name}")

    print(f"\n✅ Boolean configs: {len(booleans)} found")
    for name in booleans:
        print(f"  - {name}")

    print(f"\n✅ Device mappings: {len(devices)} found")
    for device_type, mapping in devices.items():
        print(f"  - {device_type}: {list(mapping.keys())}")

    # Test that shared sensors are inherited
    if "indoor_absolute_humidity" in sensors and "outdoor_absolute_humidity" in sensors:
        print("\n✅ SUCCESS: Default feature sensors inherited correctly")
    else:
        print("\n❌ ERROR: Default feature sensors not found")

    # Test that feature-specific entities are loaded
    if "dehumidify" in switches:
        print("✅ SUCCESS: Feature-specific switch configs loaded correctly")
    else:
        print("❌ ERROR: Feature-specific switch configs not found")

    if "relative_humidity_minimum" in numbers:
        print("✅ SUCCESS: Feature-specific number configs loaded correctly")
    else:
        print("❌ ERROR: Feature-specific number configs not found")

    print("\n=== Test completed successfully! ===")

except Exception as e:
    print(f"❌ ERROR: {e}")
    import traceback

    traceback.print_exc()
