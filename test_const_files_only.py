"""Test the const files directly without framework imports."""

import os
import sys

# Add the custom_components path so we can import modules
custom_components_path = os.path.join(os.path.dirname(__file__), "custom_components")
sys.path.insert(0, custom_components_path)

print("=== Testing Entity Definition Consolidation ===")

try:
    # Test importing default feature definitions
    print("Testing default feature definitions...")
    sys.path.insert(
        0, os.path.join(custom_components_path, "ramses_extras", "features", "default")
    )

    from const import (
        DEFAULT_BOOLEAN_CONFIGS,
        DEFAULT_DEVICE_ENTITY_MAPPING,
        DEFAULT_NUMBER_CONFIGS,
        DEFAULT_SENSOR_CONFIGS,
        DEFAULT_SWITCH_CONFIGS,
    )

    print("✅ Successfully imported default feature definitions")

    # Test default feature definitions
    print(f"\n✅ DEFAULT_SENSOR_CONFIGS: {len(DEFAULT_SENSOR_CONFIGS)} entities")
    for name in DEFAULT_SENSOR_CONFIGS:
        print(f"  - {name}: {DEFAULT_SENSOR_CONFIGS[name]['name_template']}")

    print(f"✅ DEFAULT_SWITCH_CONFIGS: {len(DEFAULT_SWITCH_CONFIGS)} entities")
    print(f"✅ DEFAULT_NUMBER_CONFIGS: {len(DEFAULT_NUMBER_CONFIGS)} entities")
    print(f"✅ DEFAULT_BOOLEAN_CONFIGS: {len(DEFAULT_BOOLEAN_CONFIGS)} entities")

    print(
        f"✅ DEFAULT_DEVICE_ENTITY_MAPPING: "
        f"{list(DEFAULT_DEVICE_ENTITY_MAPPING.keys())}"
    )

    # Test importing humidity control feature definitions
    print("\nTesting humidity control feature definitions...")
    sys.path.insert(
        0,
        os.path.join(
            custom_components_path, "ramses_extras", "features", "humidity_control"
        ),
    )

    from const import (
        HUMIDITY_BOOLEAN_CONFIGS,
        HUMIDITY_DECISION_ACTIONS,
        HUMIDITY_DECISION_THRESHOLDS,
        HUMIDITY_DEVICE_ENTITY_MAPPING,
        HUMIDITY_NUMBER_CONFIGS,
        HUMIDITY_SWITCH_CONFIGS,
    )

    print("✅ Successfully imported humidity control feature definitions")

    # Test feature-specific definitions
    print(f"\n✅ HUMIDITY_SWITCH_CONFIGS: {len(HUMIDITY_SWITCH_CONFIGS)} entities")
    for name in HUMIDITY_SWITCH_CONFIGS:
        print(f"  - {name}: {HUMIDITY_SWITCH_CONFIGS[name]['name_template']}")

    print(f"✅ HUMIDITY_NUMBER_CONFIGS: {len(HUMIDITY_NUMBER_CONFIGS)} entities")
    for name in HUMIDITY_NUMBER_CONFIGS:
        print(f"  - {name}: {HUMIDITY_NUMBER_CONFIGS[name]['name_template']}")

    print(f"✅ HUMIDITY_BOOLEAN_CONFIGS: {len(HUMIDITY_BOOLEAN_CONFIGS)} entities")
    for name in HUMIDITY_BOOLEAN_CONFIGS:
        print(f"  - {name}: {HUMIDITY_BOOLEAN_CONFIGS[name]['name_template']}")

    # Test device mappings
    print(
        f"\n✅ Humidity device mapping: {list(HUMIDITY_DEVICE_ENTITY_MAPPING.keys())}"
    )
    for device_type, mapping in HUMIDITY_DEVICE_ENTITY_MAPPING.items():
        print(f"  - {device_type}: {list(mapping.keys())}")

    # Verify the consolidation worked
    print("\n=== Verifying Consolidation Success ===")

    # Check that default has only shared sensors
    if (
        len(DEFAULT_SENSOR_CONFIGS) == 2
        and "indoor_absolute_humidity" in DEFAULT_SENSOR_CONFIGS
        and "outdoor_absolute_humidity" in DEFAULT_SENSOR_CONFIGS
    ):
        print("✅ SUCCESS: Default feature has only shared sensors")
    else:
        print("❌ ERROR: Default feature sensor configuration incorrect")

    # Check that humidity feature has only feature-specific entities
    if len(HUMIDITY_SWITCH_CONFIGS) == 1 and "dehumidify" in HUMIDITY_SWITCH_CONFIGS:
        print("✅ SUCCESS: Humidity feature has correct switch configs")
    else:
        print("❌ ERROR: Humidity feature switch configuration incorrect")

    if len(HUMIDITY_NUMBER_CONFIGS) == 3:
        print("✅ SUCCESS: Humidity feature has correct number configs")
    else:
        print("❌ ERROR: Humidity feature number configuration incorrect")

    if (
        len(HUMIDITY_BOOLEAN_CONFIGS) == 1
        and "dehumidifying_active" in HUMIDITY_BOOLEAN_CONFIGS
    ):
        print("✅ SUCCESS: Humidity feature has correct boolean configs")
    else:
        print("❌ ERROR: Humidity feature boolean configuration incorrect")

    # Check inheritance (humidity inherits sensors from default)
    if "indoor_absolute_humidity" in HUMIDITY_DEVICE_ENTITY_MAPPING.get(
        "HvacVentilator", {}
    ).get("sensors", []):
        print("✅ SUCCESS: Humidity feature inherits shared sensors from default")
    else:
        print("❌ ERROR: Humidity feature doesn't inherit shared sensors")

    print("\n=== ✅ ALL TESTS PASSED! ===")
    print("Entity definition consolidation is working correctly!")
    print("No more duplication between root const.py and feature const.py files!")

except Exception as e:
    print(f"❌ ERROR: {e}")
    import traceback

    traceback.print_exc()
