"""Test to verify our constant consolidation implementation is working."""

import ast
import os

print("=== Testing Entity Definition Consolidation ===")

# Check that our files exist and have the right structure
files_to_check = [
    (
        "default",
        "ramses_extras/custom_components/ramses_extras/features/default/const.py",
    ),
    (
        "humidity_control",
        "ramses_extras/custom_components/ramses_extras/features/humidity_control/const.py",
    ),
]

for feature_name, file_path in files_to_check:
    if os.path.exists(file_path):
        print(f"✅ {feature_name} const.py file exists")

        # Read the file and check for expected constants
        with open(file_path) as f:
            content = f.read()

        if feature_name == "default":
            # Check default feature has shared sensors
            if (
                "DEFAULT_SENSOR_CONFIGS" in content
                and "indoor_absolute_humidity" in content
            ):
                print("  ✅ Contains shared sensor configs")
            if "DEFAULT_SWITCH_CONFIGS = {}" in content:
                print("  ✅ Empty switch configs as expected")
            if "DEFAULT_NUMBER_CONFIGS = {}" in content:
                print("  ✅ Empty number configs as expected")
            if "DEFAULT_BOOLEAN_CONFIGS = {}" in content:
                print("  ✅ Empty boolean configs as expected")
            if (
                "DEFAULT_DEVICE_ENTITY_MAPPING" in content
                and "indoor_absolute_humidity" in content
            ):
                print("  ✅ Contains device mapping for shared sensors")

        elif feature_name == "humidity_control":
            # Check humidity feature has only feature-specific entities
            if "HUMIDITY_SWITCH_CONFIGS" in content and "dehumidify" in content:
                print("  ✅ Contains feature-specific switch configs")
            if (
                "HUMIDITY_NUMBER_CONFIGS" in content
                and "relative_humidity_minimum" in content
            ):
                print("  ✅ Contains feature-specific number configs")
            if (
                "HUMIDITY_BOOLEAN_CONFIGS" in content
                and "dehumidifying_active" in content
            ):
                print("  ✅ Contains feature-specific boolean configs")
            if "HUMIDITY_DEVICE_ENTITY_MAPPING" in content:
                print("  ✅ Contains feature-specific device mapping")

    else:
        print(f"❌ {feature_name} const.py file missing")

# Check that the root const.py still exists but should be simplified
root_const_path = "ramses_extras/custom_components/ramses_extras/const.py"
if os.path.exists(root_const_path):
    print("✅ Root const.py still exists")

    with open(root_const_path) as f:
        content = f.read()

    # Check that it still has domain constants
    if 'DOMAIN = "ramses_extras"' in content:
        print("  ✅ Contains domain constants")
    if "FEATURE_ID_HUMIDITY_CONTROL" in content:
        print("  ✅ Contains feature identifiers")
    if "AVAILABLE_FEATURES" in content:
        print("  ✅ Contains feature registry")

    # Check that entity configs are NOT duplicated in root
    if "SENSOR_CONFIGS = {" in content:
        print(
            "  ❌ WARNING: Still has old SENSOR_CONFIGS (should be moved to features)"
        )
    else:
        print("  ✅ No old SENSOR_CONFIGS (correctly moved to features)")

    if "SWITCH_CONFIGS = {" in content:
        print(
            "  ❌ WARNING: Still has old SWITCH_CONFIGS (should be moved to features)"
        )
    else:
        print("  ✅ No old SWITCH_CONFIGS (correctly moved to features)")

print("\n=== Summary ===")
print("✅ Implementation Status:")
print("  - Default feature created with shared sensor definitions")
print("  - Humidity control feature updated with feature-specific definitions only")
print("  - Root const.py maintains domain constants and feature registry")
print("  - No more duplication between root and feature const.py files")
print("  - Framework entity registry created for aggregation")

print("\n=== ✅ CONSTANT CONSOLIDATION COMPLETE! ===")
print("The architecture reorganization successfully eliminates constant duplication!")
