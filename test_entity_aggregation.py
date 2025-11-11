"""Test script to verify entity definition aggregation works correctly."""

# Test the framework aggregation system
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
print(f"Sensor configs: {len(sensors)} found")
for name in sensors:
    print(f"  - {name}")

print(f"\nSwitch configs: {len(switches)} found")
for name in switches:
    print(f"  - {name}")

print(f"\nNumber configs: {len(numbers)} found")
for name in numbers:
    print(f"  - {name}")

print(f"\nBoolean configs: {len(booleans)} found")
for name in booleans:
    print(f"  - {name}")

print(f"\nDevice mappings: {len(devices)} found")
for device_type, mapping in devices.items():
    print(f"  - {device_type}: {list(mapping.keys())}")

print("\n=== Test completed successfully! ===")
