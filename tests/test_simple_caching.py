"""Simple test to understand the caching issue."""

import asyncio
from unittest.mock import MagicMock

from custom_components.ramses_extras.framework.helpers.entity.simple_entity_manager import (  # noqa: E501
    SimpleEntityManager,
)


async def test_simple_caching():
    """Simple test to understand caching."""

    # Create mock Home Assistant
    mock_hass = MagicMock()

    print("=== Simple caching test ===")

    # Test 1: Calculate entities for device 1
    print("\n--- Test 1: Device 1 ---")
    matrix_state1 = {"32:153289": {"default": True}}
    entity_manager1 = SimpleEntityManager(mock_hass)
    entity_manager1.restore_device_feature_matrix_state(matrix_state1)
    entities1 = await entity_manager1._calculate_required_entities()
    print(f"Entities for device 1: {len(entities1)} - {entities1}")

    # Test 2: Calculate entities for device 2
    print("\n--- Test 2: Device 2 ---")
    matrix_state2 = {"45:67890": {"default": True}}
    entity_manager2 = SimpleEntityManager(mock_hass)
    entity_manager2.restore_device_feature_matrix_state(matrix_state2)
    entities2 = await entity_manager2._calculate_required_entities()
    print(f"Entities for device 2: {len(entities2)} - {entities2}")

    # Test 3: Calculate entities for device 1 again
    print("\n--- Test 3: Device 1 again ---")
    matrix_state3 = {"32:153289": {"default": True}}
    entity_manager3 = SimpleEntityManager(mock_hass)
    entity_manager3.restore_device_feature_matrix_state(matrix_state3)
    entities3 = await entity_manager3._calculate_required_entities()
    print(f"Entities for device 1 (again): {len(entities3)} - {entities3}")

    # Analysis
    print("\n=== Analysis ===")
    if entities1 == entities3:
        print("✅ Same device gives same results")
    else:
        print("❌ Same device gives different results")
        print(f"First: {entities1}")
        print(f"Second: {entities3}")

    if len(entities1) == 2 and len(entities2) == 2 and len(entities3) == 2:
        print("✅ All calculations give expected results")
    else:
        print("❌ Some calculations give unexpected results")


if __name__ == "__main__":
    asyncio.run(test_simple_caching())
