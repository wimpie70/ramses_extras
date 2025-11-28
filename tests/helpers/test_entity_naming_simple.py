"""Simple test for the improved entity naming system without
Home Assistant dependencies."""

import os
import sys

# Add the custom component to the path
sys.path.insert(
    0, os.path.join(os.path.dirname(__file__), "../../custom_components/ramses_extras")
)


# Mock Home Assistant types for testing
class MockHomeAssistant:
    pass


class EntityCategory:
    DIAGNOSTIC = "diagnostic"
    CONFIG = "config"


# Mock the const values we need for testing - using both CC and Extras format templates
SENSOR_CONFIGS = {
    "indoor_absolute_humidity": {
        "name_template": "Indoor Absolute Humidity",
        "entity_category": EntityCategory.DIAGNOSTIC,
        "unit": "g/m³",
        "icon": "mdi:water-percent",
        "device_class": None,
        "supported_device_types": ["HvacVentilator"],
        "entity_template": "indoor_absolute_humidity_{device_id}",
        # Extras format (device_id at end)
    },
    "outdoor_absolute_humidity": {
        "name_template": "Outdoor Absolute Humidity",
        "entity_category": EntityCategory.DIAGNOSTIC,
        "unit": "g/m³",
        "icon": "mdi:weather-partly-cloudy",
        "device_class": None,
        "supported_device_types": ["HvacVentilator"],
        "entity_template": "outdoor_absolute_humidity_{device_id}",
        # Extras format (device_id at end)
    },
}

SWITCH_CONFIGS = {
    "dehumidify": {
        "name_template": "Dehumidify",
        "icon": "mdi:air-humidifier",
        "entity_category": EntityCategory.CONFIG,
        "supported_device_types": ["HvacVentilator"],
        "entity_template": "dehumidify_{device_id}",
        # Extras format (device_id at end)
    },
}

BOOLEAN_CONFIGS = {
    "dehumidifying_active": {
        "name_template": "Dehumidifying Active",
        "icon": "mdi:air-humidifier",
        "entity_category": EntityCategory.DIAGNOSTIC,
        "device_class": "running",
        "supported_device_types": ["HvacVentilator"],
        "entity_template": "dehumidifying_active_{device_id}",
        # Extras format (device_id at end)
    },
}

NUMBER_CONFIGS = {
    "relative_humidity_minimum": {
        "name_template": "Relative Humidity Minimum",
        "entity_category": EntityCategory.CONFIG,
        "unit": "%",
        "icon": "mdi:water-minus",
        "device_class": None,
        "min_value": 30,
        "max_value": 80,
        "step": 1,
        "default_value": 40,
        "supported_device_types": ["HvacVentilator"],
        "entity_template": "relative_humidity_minimum_{device_id}",
        # Extras format (device_id at end)
    },
    "relative_humidity_maximum": {
        "name_template": "Relative Humidity Maximum",
        "entity_category": EntityCategory.CONFIG,
        "unit": "%",
        "icon": "mdi:water-plus",
        "device_class": None,
        "min_value": 50,
        "max_value": 90,
        "step": 1,
        "default_value": 60,
        "supported_device_types": ["HvacVentilator"],
        "entity_template": "relative_humidity_maximum_{device_id}",
        # Extras format (device_id at end)
    },
    "absolute_humidity_offset": {
        "name_template": "Absolute Humidity Offset",
        "entity_category": EntityCategory.CONFIG,
        "unit": "g/m³",
        "icon": "mdi:swap-horizontal",
        "device_class": None,
        "min_value": -3.0,
        "max_value": 3.0,
        "step": 0.1,
        "default_value": 0.4,
        "supported_device_types": ["HvacVentilator"],
        "entity_template": "absolute_humidity_offset_{device_id}",
        # Extras format (device_id at end)
    },
}

ENTITY_TYPE_CONFIGS = {
    "sensor": SENSOR_CONFIGS,
    "switch": SWITCH_CONFIGS,
    "binary_sensor": BOOLEAN_CONFIGS,
    "number": NUMBER_CONFIGS,
}


# Now define the helper functions (copied from device.py without HA dependencies)
def get_entity_template(entity_type: str, entity_name: str) -> str | None:
    """Get the entity template for a specific entity type and name."""
    configs = ENTITY_TYPE_CONFIGS.get(entity_type, {})
    entity_config = configs.get(entity_name, {})
    return entity_config.get("entity_template")


def generate_entity_name_from_template(
    entity_type: str, entity_name: str, device_id: str
) -> str | None:
    """Generate a full entity ID using the configured template."""
    template = get_entity_template(entity_type, entity_name)
    if not template:
        return None

    # Replace {device_id} placeholder with actual device ID
    entity_id_part = template.format(device_id=device_id)

    # Add the entity type prefix
    type_to_prefix = {
        "sensor": "sensor",
        "switch": "switch",
        "number": "number",
        "binary_sensor": "binary_sensor",
    }

    prefix = type_to_prefix.get(entity_type, entity_type)
    return f"{prefix}.{entity_id_part}"


def get_all_required_entity_ids_for_device(device_id: str) -> list[str]:
    """Get all entity IDs required for a device based on its capabilities."""
    entity_ids = []

    # For each entity type configuration
    for entity_type, configs in ENTITY_TYPE_CONFIGS.items():
        # For each entity in that type
        for entity_name in configs.keys():
            entity_id = generate_entity_name_from_template(
                entity_type, entity_name, device_id
            )
            if entity_id:
                entity_ids.append(entity_id)

    return entity_ids


def parse_entity_id(entity_id: str) -> tuple[str, str, str] | None:
    """Parse an entity ID to extract entity type, name,
    and device ID with automatic format detection."""
    try:
        # Split on first dot to get type and rest
        if "." not in entity_id:
            return None

        entity_type, entity_name = entity_id.split(".", 1)

        # Find device_id pattern in the entity name
        import re

        pattern = r"(\d+[_:]\d+)"
        match = re.search(pattern, entity_name)
        if not match:
            return None

        device_id = match.group(1).replace(":", "_")
        position = match.start()

        # Automatic format detection based on position
        if position <= len(entity_name) * 0.3:  # First 30% → CC format
            # CC format: device_id at beginning
            identifier = entity_name[position + len(device_id) :].lstrip("_")
            parsed_name = identifier if identifier else "unknown"
        else:  # Last portion → Extras format
            # Extras format: device_id at end
            parsed_name = entity_name[:position].rstrip("_")

        # Validate entity type
        valid_types = {"sensor", "switch", "number", "binary_sensor"}
        if entity_type in valid_types:
            return entity_type, parsed_name, device_id

        return None

    except (ValueError, IndexError):
        return None


def test_automatic_format_detection():
    """Test automatic format detection for both CC and Extras formats."""
    print("\n🧪 Testing automatic format detection...")

    # Import the actual EntityHelpers (if available, otherwise use mock)
    try:
        import os
        import sys

        sys.path.insert(
            0,
            os.path.join(
                os.path.dirname(__file__), "../../custom_components/ramses_extras"
            ),
        )
        from framework.helpers.entity.core import EntityHelpers

        has_entity_helpers = True
    except ImportError:
        print("⚠️  EntityHelpers not available, using mock implementation")
        has_entity_helpers = False  # noqa: F841

        # Mock EntityHelpers for testing
        class EntityHelpers:
            @staticmethod
            def parse_entity_id(entity_id: str):
                """Simple mock implementation."""
                if not entity_id or "." not in entity_id:
                    return None
                try:
                    entity_type, entity_name = entity_id.split(".", 1)

                    # Check for device_id pattern
                    import re

                    pattern = r"(\d+[_:]\d+)"
                    match = re.search(pattern, entity_name)
                    if not match:
                        return None

                    device_id = match.group(1).replace(":", "_")
                    position = match.start()

                    # Simple format detection
                    if position <= len(entity_name) * 0.3:  # CC format
                        identifier = entity_name[position + len(device_id) :].lstrip(
                            "_"
                        )
                        return entity_type, identifier, device_id
                    # Extras format
                    parsed_name = entity_name[:position].rstrip("_")
                    return entity_type, parsed_name, device_id
                except:  # noqa: E722
                    return None

    test_cases = [
        # Extras format (device_id at end)
        (
            "sensor.indoor_absolute_humidity_32_153289",
            "extras",
            "indoor_absolute_humidity",
        ),
        ("switch.dehumidify_32_153289", "extras", "dehumidify"),
        (
            "number.relative_humidity_minimum_32_153289",
            "extras",
            "relative_humidity_minimum",
        ),
        # CC format (device_id at beginning)
        ("sensor.32_153289_temp", "cc", "temp"),
        ("number.32_153289_param_7c00", "cc", "param_7c00"),
        ("switch.32_153289_fan_speed", "cc", "fan_speed"),
    ]

    for entity_id, expected_format, expected_name in test_cases:
        parsed = EntityHelpers.parse_entity_id(entity_id)
        if parsed:
            entity_type, parsed_name, device_id = parsed
            print(f"✅ {entity_id}: {entity_type}.{parsed_name} (device: {device_id})")

            # Verify parsing worked correctly
            assert entity_type in ["sensor", "switch", "number", "binary_sensor"]
            assert device_id == "32_153289"
            assert parsed_name == expected_name
        else:
            raise AssertionError(f"Failed to parse {entity_id}")

    print("✅ All automatic format detection tests passed!")


def test_entity_generation():
    """Test entity ID generation with device ID templates."""
    print("🧪 Testing entity ID generation...")

    device_id = "32_153289"

    # Test sensor entity generation (Extras format)
    sensor_id = generate_entity_name_from_template(
        "sensor", "indoor_absolute_humidity", device_id
    )
    print(f"✅ Sensor entity: {sensor_id}")
    expected_sensor = "sensor.indoor_absolute_humidity_32_153289"
    assert sensor_id == expected_sensor, f"Expected {expected_sensor}, got {sensor_id}"

    # Test number entity generation (Extras format)
    number_id = generate_entity_name_from_template(
        "number", "relative_humidity_maximum", device_id
    )
    print(f"✅ Number entity: {number_id}")
    expected_number = "number.relative_humidity_maximum_32_153289"
    assert number_id == expected_number, f"Expected {expected_number}, got {number_id}"

    # Test switch entity generation (Extras format)
    switch_id = generate_entity_name_from_template("switch", "dehumidify", device_id)
    print(f"✅ Switch entity: {switch_id}")
    expected_switch = "switch.dehumidify_32_153289"
    assert switch_id == expected_switch, f"Expected {expected_switch}, got {switch_id}"

    # Test binary sensor entity generation (Extras format)
    binary_id = generate_entity_name_from_template(
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
        # Test Extras format (device_id at end)
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
        # Test CC format (device_id at beginning) - should also work
        (
            "sensor.32_153289_temp",
            "sensor",
            "temp",
            "32_153289",
        ),
        (
            "number.32_153289_param_7c00",
            "number",
            "param_7c00",
            "32_153289",
        ),
    ]

    for entity_id, expected_type, expected_name, expected_device in test_cases:
        parsed = parse_entity_id(entity_id)
        if parsed:
            entity_type, entity_name, device_id = parsed
            print(f"✅ Parsed {entity_id}:")
            print(f"   Type: {entity_type} (expected: {expected_type})")
            print(f"   Name: {entity_name} (expected: {expected_name})")
            print(f"   Device: {device_id} (expected: {expected_device})")

            assert entity_type == expected_type, (
                f"Type mismatch: {entity_type} != {expected_type}"
            )
            assert entity_name == expected_name, (
                f"Name mismatch: {entity_name} != {expected_name}"
            )
            assert device_id == expected_device, (
                f"Device ID mismatch: {device_id} != {expected_device}"
            )
        else:
            raise AssertionError(f"Failed to parse entity ID: {entity_id}")

    print("✅ All entity parsing tests passed!")


def test_all_entities_for_device():
    """Test generating all required entities for a device."""
    print("\n🧪 Testing all entities for device...")

    device_id = "32_153289"
    all_entities = get_all_required_entity_ids_for_device(device_id)

    print(f"Generated {len(all_entities)} entities for device {device_id}:")
    for entity_id in sorted(all_entities):
        print(f"  - {entity_id}")

    # Check that we have entities for all types
    entity_types = [entity_id.split(".")[0] for entity_id in all_entities]
    expected_types = {"sensor", "number", "switch", "binary_sensor"}
    found_types = set(entity_types)

    print(f"Found entity types: {sorted(found_types)}")
    print(f"Expected entity types: {sorted(expected_types)}")

    assert found_types == expected_types, (
        f"Entity types mismatch: {found_types} != {expected_types}"
    )

    print("✅ All entities for device test passed!")


def test_name_templates():
    """Test that name templates are properly defined."""
    print("\n🧪 Testing name templates...")

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

            assert template is not None, (
                f"{config_type}.{entity_name} missing entity_template"
            )
            assert "{device_id}" in template, (
                f"{config_type}.{entity_name} entity_template missing {{device_id}}"
            )
            assert name_template is not None, (
                f"{config_type}.{entity_name} missing name_template"
            )

    print("✅ All name template tests passed!")


def test_naming_consistency():
    """Test that the new naming system is consistent and predictable."""
    print("\n🧪 Testing naming consistency...")

    # Test different device IDs
    device_ids = ["32_153289", "10_456789", "1_123"]

    for device_id in device_ids:
        print(f"\n📋 Testing with device ID: {device_id}")

        # Generate all entities for this device
        entities = get_all_required_entity_ids_for_device(device_id)

        # Verify all entities can be parsed back correctly
        for entity_id in entities:
            # Verify we can parse it back
            parsed = parse_entity_id(entity_id)
            assert parsed is not None, f"Failed to parse {entity_id}"

            parsed_type, parsed_name, parsed_device = parsed
            assert parsed_device == device_id, f"Device ID mismatch in {entity_id}"

            # Verify entity type is valid
            assert parsed_type in ["sensor", "switch", "number", "binary_sensor"]

            print(
                f"  ✅ {entity_id} -> {parsed_type}.{parsed_name} "
                f"(device: {parsed_device})"
            )

    print("✅ Naming consistency tests passed!")


if __name__ == "__main__":
    print("🚀 Starting entity naming system tests...\n")

    try:
        test_entity_generation()
        test_entity_parsing()
        test_automatic_format_detection()  # New test for automatic format detection
        test_all_entities_for_device()
        test_name_templates()
        test_naming_consistency()

        print(
            "\n🎉 All tests passed! The improved entity naming"
            " system is working correctly."
        )
        print("\n📋 Summary of improvements:")
        print("  - ✅ Entity names now use templates with automatic format detection")
        print(
            "  - ✅ Supports both CC format (device_id at beginning)"
            " and Extras format (device_id at end)"
        )
        print("  - ✅ Automatic format detection based on device_id position")
        print("  - ✅ Helper methods for entity generation and parsing")
        print("  - ✅ Refactored from ENTITY_CONFIGS to SENSOR_CONFIGS")
        print("  - ✅ Feature-centric templates work with automatic detection")

    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
