#!/usr/bin/env python3
"""Test script to verify entity mappings fix."""

import os
import sys

# Add the custom_components path to import the modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "custom_components"))

try:
    from custom_components.ramses_extras.const import (
        AVAILABLE_FEATURES,
        FEATURE_ID_HUMIDITY_CONTROL,
    )
    from custom_components.ramses_extras.framework.helpers.entity.core import (
        get_feature_entity_mappings,
    )

    print("Testing entity mappings fix...")
    print("=" * 50)

    # Test the entity mappings are now present
    feature = AVAILABLE_FEATURES[FEATURE_ID_HUMIDITY_CONTROL]
    print("✅ Entity mappings present:", bool(feature.get("entity_mappings", {})))
    print("✅ Required entities present:", bool(feature.get("required_entities", {})))

    print("\nEntity mappings:", feature.get("entity_mappings", {}))
    print("Required entities:", feature.get("required_entities", {}))

    # Test the mapping function
    mappings = get_feature_entity_mappings(FEATURE_ID_HUMIDITY_CONTROL, "32_153289")
    print(f"\n✅ Generated mappings for device 32_153289: {len(mappings)} items")
    print("Mappings:", mappings)

    if mappings:
        print("\n🎉 SUCCESS: Entity mappings are working correctly!")
        print(
            "The automation should now receive proper entity "
            "states instead of empty dicts."
        )
    else:
        print("\n❌ FAILED: Entity mappings are still empty!")

except Exception as e:
    print(f"❌ ERROR: {e}")
    import traceback

    traceback.print_exc()
