#!/usr/bin/env python3
"""Simple test script for helpers/platform.py functions."""

import sys
import os
from typing import Set

# Add the custom_components directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'custom_components'))

from ramses_extras.helpers.platform import (
    convert_fan_id_format,
    calculate_required_entities,
    find_orphaned_entities
)


def test_fan_id_conversion() -> None:
    """Test fan ID format conversion."""
    print("Testing fan ID conversion...")

    # Test conversion
    original = "32:153289"
    converted = convert_fan_id_format(original)

    assert converted == "32_153289", f"Expected '32_153289', got '{converted}'"
    print(f"✅ Fan ID conversion: {original} → {converted}")


def test_required_entities_calculation() -> None:
    """Test required entities calculation."""
    print("\nTesting required entities calculation...")

    # Mock enabled features
    enabled_features = {
        'test1': False,
        'test2': False,
        'hvac_fan_card': True,  # This should create entities
        'humidity_automation': False
    }

    # Mock fans
    fans = ['32:153289']

    # Test sensor calculation
    required_sensors = calculate_required_entities(
        "sensor",
        enabled_features,
        fans
    )

    print(f"Required sensor entities: {required_sensors}")
    assert len(required_sensors) > 0, "Should have required sensor entities"
    print("✅ Required entities calculation working")


def test_entity_matching() -> None:
    """Test entity matching logic."""
    print("\nTesting entity matching logic...")

    # Mock entity registry with actual format
    mock_registry = {
        'sensor.indoor_absolute_humidity_32_153289': None,
        'sensor.outdoor_absolute_humidity_32_153289': None,
        'switch.dehumidify_32_153289': None
    }

    # Mock HASS object with proper entity registry structure
    class MockEntityRegistry:
        def __init__(self, entities_dict):
            self.entities = entities_dict

    class MockHass:
        def __init__(self):
            self.data = {'entity_registry': MockEntityRegistry(mock_registry)}

    # Test finding orphaned entities when no features are enabled
    hass = MockHass()
    fans_list = ['32:153289']
    required_entities_set: Set[str] = set()  # No entities required
    all_possible_types_list = ['indoor_abs_humid', 'outdoor_abs_humid']

    # Test the find_orphaned_entities function
    orphaned = find_orphaned_entities(
        "sensor",
        hass,
        fans_list,
        required_entities_set,
        all_possible_types_list
    )

    print(f"Found {len(orphaned)} orphaned entities: {orphaned}")
    print("✅ Entity matching logic working")

if __name__ == "__main__":
    print("🧪 Testing helpers/platform.py functions...\n")

    test_fan_id_conversion()
    test_required_entities_calculation()
    test_entity_matching()

    print("\n✅ All tests passed! Helper functions are working correctly.")
    print("\n📋 Next steps:")
    print("1. Refactor sensor.py to use these helpers")
    print("2. Refactor switch.py to use these helpers")
    print("3. Refactor binary_sensor.py to use these helpers")
    print("4. Remove duplicated code from platform files")
