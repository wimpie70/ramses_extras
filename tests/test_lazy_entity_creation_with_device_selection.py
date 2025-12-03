#!/usr/bin/env python3
"""Test lazy entity creation with device selection integration."""

import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry

from custom_components.ramses_extras.const import AVAILABLE_FEATURES
from custom_components.ramses_extras.framework.helpers.entity.manager import (
    EntityManager,
)


class TestLazyEntityCreationWithDeviceSelection(unittest.IsolatedAsyncioTestCase):
    """Test lazy entity creation with device selection integration."""

    async def asyncSetUp(self) -> None:
        """Set up test fixtures."""
        # Create mock without spec to avoid isolation issues
        self.hass = MagicMock()
        self.hass.data = {}

        # Mock entity registry
        self.entity_registry = MagicMock()
        self.hass.helpers = MagicMock()
        self.hass.helpers.entity_registry = MagicMock()
        self.hass.helpers.entity_registry.async_get.return_value = self.entity_registry

        # Mock entities
        self.mock_entities = {
            "sensor.humidity_32_153289": MagicMock(),
            "switch.dehumidify_32_153289": MagicMock(),
        }
        self.entity_registry.entities = {
            entity.entity_id: entity for entity in self.mock_entities.values()
        }

    async def test_feature_device_selection_integration(self) -> None:
        """Test that EntityManager respects device selections when enabling features."""
        # Create EntityManager
        entity_manager = EntityManager(self.hass)

        # Set device selections for humidity_control feature
        entity_manager._feature_device_selections = {
            "humidity_control": [
                "32:153289",
                "32:153290",
            ]  # Only these devices should get entities
        }

        # Mock the device discovery to return multiple devices
        with patch.object(
            entity_manager, "_get_devices_for_feature", new_callable=AsyncMock
        ) as mock_get_devices:
            # Return devices including ones not in the selection
            mock_devices = [
                {"device_id": "32:153289", "device_type": "HvacVentilator"},
                {"device_id": "32:153290", "device_type": "HvacVentilator"},
                {
                    "device_id": "32:153291",
                    "device_type": "HvacVentilator",
                },  # This one should be skipped
            ]
            mock_get_devices.return_value = mock_devices

            # Mock required entities for humidity_control
            with patch.object(
                entity_manager,
                "_get_required_entities_for_feature",
                new_callable=AsyncMock,
            ) as mock_required_entities:
                mock_required_entities.return_value = {
                    "sensor": ["humidity"],
                    "switch": ["dehumidify"],
                }

                # Build entity catalog
                await entity_manager.build_entity_catalog(
                    AVAILABLE_FEATURES,
                    {"humidity_control": False},  # Currently disabled
                    {"humidity_control": True},  # Will be enabled
                )

                # Check that only entities for selected devices were created
                all_entities = entity_manager.all_possible_entities

                # Should have entities for 32:153289 and 32:153290 (selected)
                expected_entity_ids = {
                    "sensor.humidity_32_153289",
                    "switch.dehumidify_32_153289",
                    "sensor.humidity_32_153290",
                    "switch.dehumidify_32_153290",
                }

                # Should NOT have entities for 32:153291 from humidity_control
                # feature (not selected)
                # However, default feature will create entities for all devices,
                #  so we only check
                # that humidity_control feature doesn't create entities for unselected
                #  devices
                # The test should verify that humidity_control feature respects device
                #  selection
                # while allowing default feature to create entities for all devices

                # Check that humidity_control feature didn't create entities for
                #  unselected device
                # by verifying the feature_id in the entity metadata
                for entity_id, entity_data in all_entities.items():
                    if (
                        "32_153291" in entity_id
                        and entity_data.get("feature_id") == "humidity_control"
                    ):
                        self.fail(
                            f"Humidity control feature should not create entities for "
                            f"unselected device 32:153291, but found: {entity_id}"
                        )

                # Verify expected entities exist
                for entity_id in expected_entity_ids:
                    self.assertIn(
                        entity_id,
                        all_entities,
                        f"Expected entity {entity_id} should be in catalog",
                    )

    async def test_feature_without_device_selection(self) -> None:
        """Test that features without device selections work with
        all compatible devices."""
        # Create EntityManager
        entity_manager = EntityManager(self.hass)

        # No device selections for this feature
        entity_manager._feature_device_selections = {}

        # Mock the device discovery to return multiple devices
        with patch.object(
            entity_manager, "_get_devices_for_feature", new_callable=AsyncMock
        ) as mock_get_devices:
            # Return devices
            mock_devices = [
                {"device_id": "32:153289", "device_type": "HvacVentilator"},
                {"device_id": "32:153290", "device_type": "HvacVentilator"},
            ]
            mock_get_devices.return_value = mock_devices

            # Mock required entities
            with patch.object(
                entity_manager,
                "_get_required_entities_for_feature",
                new_callable=AsyncMock,
            ) as mock_required_entities:
                mock_required_entities.return_value = {
                    "sensor": ["humidity"],
                }

                # Build entity catalog
                await entity_manager.build_entity_catalog(
                    AVAILABLE_FEATURES, {"test_feature": False}, {"test_feature": True}
                )

                # Check that entities for all devices were created (no filtering)
                all_entities = entity_manager.all_possible_entities

                # Should have entities for all devices
                expected_entity_ids = {
                    "sensor.humidity_32_153289",
                    "sensor.humidity_32_153290",
                }

                for entity_id in expected_entity_ids:
                    self.assertIn(
                        entity_id,
                        all_entities,
                        f"Entity {entity_id} should be in catalog when no device "
                        f"selection exists",
                    )


if __name__ == "__main__":
    unittest.main()
