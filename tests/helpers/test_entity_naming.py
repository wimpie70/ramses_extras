"""Test the improved entity naming system."""

import os
import sys

# Add the custom component to the path
sys.path.insert(
    0, os.path.join(os.path.dirname(__file__), "../../custom_components/ramses_extras")
)

# Import the entity helper functions from the custom component
from ramses_extras.helpers.entity import EntityHelpers


def test_entity_generation():
    """Test entity ID generation with device ID templates."""
    print("🧪 Testing entity ID generation...")

    device_id = "32_153289"

    # Test sensor entity generation
    sensor_id = EntityHelpers.generate_entity_name_from_template(
        "sensor", "indoor_absolute_humidity", device_id
    )
    print(f"✅ Sensor entity: {sensor_id}")
    expected_sensor = "sensor.indoor_absolute_humidity_32_153289"
    assert sensor_id == expected_sensor, f"Expected {expected_sensor}, got {sensor_id}"

    # Test number entity generation
    number_id = EntityHelpers.generate_entity_name_from_template(
        "number", "relative_humidity_maximum", device_id
    )
    print(f"✅ Number entity: {number_id}")
    expected_number = "number.relative_humidity_maximum_32_153289"
    assert number_id == expected_number, f"Expected {expected_number}, got {number_id}"

    # Test switch entity generation
    switch_id = EntityHelpers.generate_entity_name_from_template(
        "switch", "dehumidify", device_id
    )
    print(f"✅ Switch entity: {switch_id}")
    expected_switch = "switch.dehumidify_32_153289"
    assert switch_id == expected_switch, f"Expected {expected_switch}, got {switch_id}"

    # Test binary sensor entity generation
    binary_id = EntityHelpers.generate_entity_name_from_template(
        "binary_sensor", "dehumidifying_active", device_id
    )
    print(f"✅ Binary sensor entity: {binary_id}")
    expected_binary = "binary_sensor.dehumidifying_active_32_153289"
    assert binary_id == expected_binary, f"Expected {expected_binary}, got {binary_id}"

    print("✅ All entity generation tests passed!")


def test_entity_parsing():
    """Test entity ID parsing to extract components."""
    print("\n🧪 Testing entity ID parsing...")

    test_cases = [
        (
            "sensor.indoor_absolute_humidity_32_153289",
            "sensor",
            "indoor_absolute_humidity",
            "32_153289",
        ),
        (
            "number.relative_humidity_maximum_32_153289",
            "number",
            "relative_humidity_maximum",
            "32_153289",
        ),
        ("switch.dehumidify_32_153289", "switch", "dehumidify", "32_153289"),
        (
            "binary_sensor.dehumidifying_active_32_153289",
            "binary_sensor",
            "dehumidifying_active",
            "32_153289",
        ),
    ]

    for entity_id, expected_type, expected_name, expected_device in test_cases:
        parsed = EntityHelpers.parse_entity_id(entity_id)
        if parsed:
            entity_type, entity_name, device_id = parsed
            print(f"✅ Parsed {entity_id}:")
            print(f"   Type: {entity_type} (expected: {expected_type})")
            print(f"   Name: {entity_name} (expected: {expected_name})")
            print(f"   Device: {device_id} (expected: {expected_device})")

            assert (
                entity_type == expected_type
            ), f"Type mismatch: {entity_type} != {expected_type}"
            assert (
                entity_name == expected_name
            ), f"Name mismatch: {entity_name} != {expected_name}"
            assert (
                device_id == expected_device
            ), f"Device ID mismatch: {device_id} != {expected_device}"
        else:
            raise AssertionError(f"Failed to parse entity ID: {entity_id}")

    print("✅ All entity parsing tests passed!")


def test_all_entities_for_device():
    """Test generating all required entities for a device."""
    print("\n🧪 Testing all entities for device...")

    device_id = "32_153289"
    all_entities = EntityHelpers.get_all_required_entity_ids_for_device(device_id)

    print(f"Generated {len(all_entities)} entities for device {device_id}:")
    for entity_id in sorted(all_entities):
        print(f"  - {entity_id}")

    # Check that we have entities for all types
    entity_types = [entity_id.split(".")[0] for entity_id in all_entities]
    expected_types = {"sensor", "number", "switch", "binary_sensor"}
    found_types = set(entity_types)

    print(f"Found entity types: {sorted(found_types)}")
    print(f"Expected entity types: {sorted(expected_types)}")

    assert (
        found_types == expected_types
    ), f"Entity types mismatch: {found_types} != {expected_types}"

    print("✅ All entities for device test passed!")


def test_name_templates():
    """Test that name templates are properly defined."""
    print("\n🧪 Testing name templates...")

    from custom_components.ramses_extras.const import (
        BOOLEAN_CONFIGS,
        NUMBER_CONFIGS,
        SENSOR_CONFIGS,
        SWITCH_CONFIGS,
    )

    # Test that all configs have entity_template
    all_configs = [
        ("sensor", SENSOR_CONFIGS),
        ("switch", SWITCH_CONFIGS),
        ("binary_sensor", BOOLEAN_CONFIGS),
        ("number", NUMBER_CONFIGS),
    ]

    for config_type, configs in all_configs:
        print(f"\n📋 Checking {config_type} configs:")
        for entity_name, config in configs.items():
            template = config.get("entity_template")
            name_template = config.get("name_template")

            print(f"  - {entity_name}:")
            print(f"    name_template: {name_template}")
            print(f"    entity_template: {template}")

            assert (
                template is not None
            ), f"{config_type}.{entity_name} missing entity_template"
            assert (
                "{device_id}" in template
            ), f"{config_type}.{entity_name} entity_template missing {{device_id}}"
            assert (
                name_template is not None
            ), f"{config_type}.{entity_name} missing name_template"

    print("✅ All name template tests passed!")


if __name__ == "__main__":
    print("🚀 Starting entity naming system tests...\n")

    try:
        test_entity_generation()
        test_entity_parsing()
        test_all_entities_for_device()
        test_name_templates()

        print(
            "\n🎉 All tests passed! The improved entity "
            "naming system is working correctly."
        )

    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
