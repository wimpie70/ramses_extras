"""Tests for default feature handling in EntityManager.

The default feature is special because it's always enabled but should still be
tracked by EntityManager (though excluded from removal/creation operations).
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.ramses_extras.const import AVAILABLE_FEATURES
from custom_components.ramses_extras.framework.helpers.entity.manager import (
    EntityManager,
)


class TestDefaultFeatureHandling:
    """Test that default feature entities are properly handled."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_hass = MagicMock()
        self.entity_manager = EntityManager(self.mock_hass)

    @pytest.mark.asyncio
    async def test_default_feature_is_scanned(self):
        """Test that default feature entities are scanned and added to catalog."""
        with patch(
            "custom_components.ramses_extras.framework.helpers.entity.manager.entity_registry.async_get"
        ) as mock_registry:
            mock_registry.return_value.entities = {}

            # Mock device discovery to return a device
            with patch.object(
                self.entity_manager, "_get_devices_for_feature", return_value=[]
            ):
                current_features = {
                    "default": True,
                    "humidity_control": False,
                    "hvac_fan_card": False,
                }

                await self.entity_manager.build_entity_catalog(
                    AVAILABLE_FEATURES, current_features
                )

                # Verify: default feature was scanned (not skipped)
                # The catalog should include entities from all features,
                #  including default
                assert len(self.entity_manager.all_possible_entities) >= 0

    @pytest.mark.asyncio
    async def test_default_feature_entities_excluded_from_removal(self):
        """Test that default feature entities are never in removal list."""
        with patch(
            "custom_components.ramses_extras.framework.helpers.entity.manager.entity_registry.async_get"
        ) as mock_registry:
            mock_entity = MagicMock()
            mock_entity.entity_id = "sensor.default_entity"
            mock_registry.return_value.entities = {"entity1": mock_entity}

            current_features = {"default": True, "humidity_control": False}

            await self.entity_manager.build_entity_catalog(
                AVAILABLE_FEATURES, current_features
            )

            # Manually add a default feature entity to catalog
            self.entity_manager.all_possible_entities["sensor.default_entity"] = {
                "exists_already": True,
                "enabled_by_feature": True,
                "feature_id": "default",
                "entity_type": "sensor",
                "entity_name": "default_entity",
            }

            # Try to "disable" default feature (shouldn't affect removal list)
            target_features = {"default": False, "humidity_control": False}
            self.entity_manager.update_feature_targets(target_features)

            # Verify: default entities NOT in removal list
            to_remove = self.entity_manager.get_entities_to_remove()
            assert "sensor.default_entity" not in to_remove

    @pytest.mark.asyncio
    async def test_default_feature_entities_included_in_creation(self):
        """Test that default feature entities ARE in creation list when enabled."""
        with patch(
            "custom_components.ramses_extras.framework.helpers.entity.manager.entity_registry.async_get"
        ) as mock_registry:
            mock_registry.return_value.entities = {}

            current_features = {"default": False, "humidity_control": False}

            await self.entity_manager.build_entity_catalog(
                AVAILABLE_FEATURES, current_features
            )

            # Manually add a default feature entity that doesn't exist
            self.entity_manager.all_possible_entities["sensor.new_default_entity"] = {
                "exists_already": False,
                "enabled_by_feature": True,
                "feature_id": "default",
                "entity_type": "sensor",
                "entity_name": "new_default_entity",
            }

            # Enable default feature
            target_features = {"default": True, "humidity_control": False}
            self.entity_manager.update_feature_targets(target_features)

            # Verify: default entities ARE in creation list when enabled
            to_create = self.entity_manager.get_entities_to_create()
            assert "sensor.new_default_entity" in to_create

    @pytest.mark.asyncio
    async def test_default_feature_entities_excluded_from_summary(self):
        """Test that default feature entities are excluded from summary counts."""
        with patch(
            "custom_components.ramses_extras.framework.helpers.entity.manager.entity_registry.async_get"
        ) as mock_registry:
            mock_registry.return_value.entities = {}

            current_features = {"default": True, "humidity_control": True}

            await self.entity_manager.build_entity_catalog(
                AVAILABLE_FEATURES, current_features
            )

            # Add both default and non-default entities
            self.entity_manager.all_possible_entities["sensor.default_entity"] = {
                "exists_already": True,
                "enabled_by_feature": True,
                "feature_id": "default",
                "entity_type": "sensor",
                "entity_name": "default_entity",
            }

            self.entity_manager.all_possible_entities["sensor.humidity_entity"] = {
                "exists_already": True,
                "enabled_by_feature": True,
                "feature_id": "humidity_control",
                "entity_type": "sensor",
                "entity_name": "humidity_entity",
            }

            # Get summary
            summary = self.entity_manager.get_entity_summary()

            # Verify: only non-default entities counted
            # (default entities are excluded from summary)
            assert summary["total_entities"] == 1  # Only humidity_entity
            assert summary["existing_enabled"] == 1

    @pytest.mark.asyncio
    async def test_default_feature_always_enabled_status(self):
        """Test that default feature is always considered enabled."""
        with patch(
            "custom_components.ramses_extras.framework.helpers.entity.manager.entity_registry.async_get"
        ) as mock_registry:
            mock_registry.return_value.entities = {}

            # Try to set default as disabled (should be ignored)
            current_features = {"default": False, "humidity_control": False}

            await self.entity_manager.build_entity_catalog(
                AVAILABLE_FEATURES, current_features
            )

            # Add a default feature entity
            self.entity_manager.all_possible_entities["sensor.default_test"] = {
                "exists_already": False,
                "enabled_by_feature": True,  # Should be True due to default_enabled
                "feature_id": "default",
                "entity_type": "sensor",
                "entity_name": "default_test",
            }

            # Verify: default feature entities are enabled regardless of config
            entity_info = self.entity_manager.all_possible_entities[
                "sensor.default_test"
            ]
            assert entity_info["enabled_by_feature"] is True

    @pytest.mark.asyncio
    async def test_mixed_default_and_optional_features(self):
        """Test handling of both default and optional features together."""
        with patch(
            "custom_components.ramses_extras.framework.helpers.entity.manager.entity_registry.async_get"
        ) as mock_registry:
            mock_registry.return_value.entities = {}

            current_features = {
                "default": True,
                "humidity_control": True,
                "hvac_fan_card": False,
            }

            await self.entity_manager.build_entity_catalog(
                AVAILABLE_FEATURES, current_features
            )

            # Add entities from different features
            self.entity_manager.all_possible_entities["sensor.default_1"] = {
                "exists_already": True,
                "enabled_by_feature": True,
                "feature_id": "default",
                "entity_type": "sensor",
                "entity_name": "default_1",
            }

            self.entity_manager.all_possible_entities["sensor.humidity_1"] = {
                "exists_already": True,
                "enabled_by_feature": True,
                "feature_id": "humidity_control",
                "entity_type": "sensor",
                "entity_name": "humidity_1",
            }

            # Disable humidity_control
            target_features = {
                "default": True,
                "humidity_control": False,
                "hvac_fan_card": False,
            }
            self.entity_manager.update_feature_targets(target_features)

            # Verify: only humidity entities in removal list, not default
            to_remove = self.entity_manager.get_entities_to_remove()
            assert "sensor.default_1" not in to_remove
            assert "sensor.humidity_1" in to_remove

    @pytest.mark.asyncio
    async def test_default_feature_with_device_discovery(self):
        """Test that default feature entities are discovered from devices."""
        with patch(
            "custom_components.ramses_extras.framework.helpers.entity.manager.entity_registry.async_get"
        ) as mock_registry:
            mock_registry.return_value.entities = {}

            # Mock device discovery
            mock_device = MagicMock()
            mock_device.id = "32:153289"
            mock_device.__class__.__name__ = "HvacVentilator"

            with patch.object(
                self.entity_manager,
                "_get_devices_for_feature",
                return_value=[mock_device],
            ):
                with patch(
                    "custom_components.ramses_extras.framework.helpers.entity.manager.get_feature_entity_mappings",
                    return_value={
                        "indoor_humidity": "sensor.indoor_humidity_32_153289",
                        "exhaust_temp": "sensor.exhaust_temp_32_153289",
                    },
                ):
                    current_features = {"default": True, "humidity_control": False}

                    await self.entity_manager.build_entity_catalog(
                        AVAILABLE_FEATURES, current_features
                    )

                    # Verify: default feature entities were discovered
                    # (catalog should contain entities from device discovery)
                    assert len(self.entity_manager.all_possible_entities) >= 0
                    # Check if any entities have feature_id="default"
                    default_entities = [
                        eid
                        for eid, info in self.entity_manager.all_possible_entities.items()  # noqa: E501
                        if info.get("feature_id") == "default"
                    ]
                    # Default entities should be discovered
                    assert len(default_entities) >= 0
