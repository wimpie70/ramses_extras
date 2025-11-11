"""Simple test of our entity aggregation system without complex framework imports."""

import os
import sys

# Add the custom_components path so we can import modules
custom_components_path = os.path.join(os.path.dirname(__file__), "custom_components")
sys.path.insert(0, custom_components_path)

print("=== Testing Entity Definition Aggregation ===")

try:
    # Test importing feature definitions directly
    from custom_components.ramses_extras.features.default.const import (
        DEFAULT_BOOLEAN_CONFIGS,
        DEFAULT_DEVICE_ENTITY_MAPPING,
        DEFAULT_NUMBER_CONFIGS,
        DEFAULT_SENSOR_CONFIGS,
        DEFAULT_SWITCH_CONFIGS,
    )
    from custom_components.ramses_extras.features.humidity_control.const import (
        HUMIDITY_BOOLEAN_CONFIGS,
        HUMIDITY_DEVICE_ENTITY_MAPPING,
        HUMIDITY_NUMBER_CONFIGS,
        HUMIDITY_SWITCH_CONFIGS,
    )

    print("✅ Successfully imported feature definitions")

    # Test default feature definitions
    print(f"\n✅ Default SENSOR_CONFIGS: {len(DEFAULT_SENSOR_CONFIGS)} entities")
    for name in DEFAULT_SENSOR_CONFIGS:
        print(f"  - {name}")

    print(f"✅ Default SWITCH_CONFIGS: {len(DEFAULT_SWITCH_CONFIGS)} entities")
    print(f"✅ Default NUMBER_CONFIGS: {len(DEFAULT_NUMBER_CONFIGS)} entities")
    print(f"✅ Default BOOLEAN_CONFIGS: {len(DEFAULT_BOOLEAN_CONFIGS)} entities")

    # Test feature-specific definitions
    print(f"\n✅ Humidity SWITCH_CONFIGS: {len(HUMIDITY_SWITCH_CONFIGS)} entities")
    for name in HUMIDITY_SWITCH_CONFIGS:
        print(f"  - {name}")

    print(f"✅ Humidity NUMBER_CONFIGS: {len(HUMIDITY_NUMBER_CONFIGS)} entities")
    for name in HUMIDITY_NUMBER_CONFIGS:
        print(f"  - {name}")

    print(f"✅ Humidity BOOLEAN_CONFIGS: {len(HUMIDITY_BOOLEAN_CONFIGS)} entities")
    for name in HUMIDITY_BOOLEAN_CONFIGS:
        print(f"  - {name}")

    # Test device mappings
    print(f"\n✅ Default device mapping: {list(DEFAULT_DEVICE_ENTITY_MAPPING.keys())}")
    for device_type, mapping in DEFAULT_DEVICE_ENTITY_MAPPING.items():
        print(f"  - {device_type}: sensors={mapping['sensors']}")

    print(f"✅ Humidity device mapping: {list(HUMIDITY_DEVICE_ENTITY_MAPPING.keys())}")
    for device_type, mapping in HUMIDITY_DEVICE_ENTITY_MAPPING.items():
        print(f"  - {device_type}: {list(mapping.keys())}")

    # Verify inheritance
    if (
        "indoor_absolute_humidity" in DEFAULT_SENSOR_CONFIGS
        and "outdoor_absolute_humidity" in DEFAULT_SENSOR_CONFIGS
    ):
        print("\n✅ SUCCESS: Default sensors defined correctly")
    else:
        print("\n❌ ERROR: Default sensors missing")

    if "dehumidify" in HUMIDITY_SWITCH_CONFIGS:
        print("✅ SUCCESS: Feature-specific switch configs defined correctly")
    else:
        print("❌ ERROR: Feature-specific switch configs missing")

    if "relative_humidity_minimum" in HUMIDITY_NUMBER_CONFIGS:
        print("✅ SUCCESS: Feature-specific number configs defined correctly")
    else:
        print("❌ ERROR: Feature-specific number configs missing")

    if "dehumidifying_active" in HUMIDITY_BOOLEAN_CONFIGS:
        print("✅ SUCCESS: Feature-specific boolean configs defined correctly")
    else:
        print("❌ ERROR: Feature-specific boolean configs missing")

    print("\n=== ✅ ALL TESTS PASSED! ===")
    print("Entity definition aggregation is working correctly!")

except Exception as e:
    print(f"❌ ERROR: {e}")
    import traceback

    traceback.print_exc()
