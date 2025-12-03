#!/usr/bin/env python3
"""Debug device extraction."""

from unittest.mock import MagicMock

from custom_components.ramses_extras.framework.helpers.entity.manager import (
    EntityManager,
)

# Create a simple test
hass = MagicMock()
entity_manager = EntityManager(hass)

# Test device extraction
test_device = {"device_id": "32:153289", "device_type": "HvacVentilator"}
device_id = entity_manager._extract_device_id(test_device)
print(f"Extracted device_id: {device_id} (type: {type(device_id)})")

# Test entity ID generation
entity_name = "humidity"
singular_type = "sensor"
clean_device_id = str(device_id).replace(":", "_")
entity_id = f"{singular_type}.{entity_name}_{clean_device_id}"
print(f"Generated entity_id: {entity_id}")
