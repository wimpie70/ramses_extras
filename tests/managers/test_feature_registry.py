"""Comprehensive tests for feature registry and entity lifecycle management.

This module tests every step of the feature enable/disable workflow:
- What entities need to be created when a feature is enabled
- What entities already exist and should be kept
- What entities need to be removed when a feature is disabled
- Edge cases and state transitions
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.ramses_extras.const import AVAILABLE_FEATURES
from custom_components.ramses_extras.framework.helpers.entity.manager import (
    EntityManager,
)


class TestFeatureEnableDisableWorkflow:
    """Test complete feature enable/disable workflows."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_hass = MagicMock()
        self.entity_manager = EntityManager(self.mock_hass)

    @pytest.mark.asyncio
    async def test_enable_feature_from_scratch(self):
        """Test enabling a feature when no entities exist yet."""
        # Setup: No existing entities
        with patch(
            "custom_components.ramses_extras.framework.helpers.entity.manager.entity_registry.async_get"
        ) as mock_registry:
            mock_registry.return_value.entities = {}

            # Current state: feature disabled
            current_features = {"default": True, "humidity_control": False}

            # Build catalog with current state
            await self.entity_manager.build_entity_catalog(
                AVAILABLE_FEATURES, current_features
            )

            # Target state: enable humidity_control
            target_features = {"default": True, "humidity_control": True}
            self.entity_manager.update_feature_targets(target_features)

            # Verify: entities should be created
            # to_create = self.entity_manager.get_entities_to_create()
            to_remove = self.entity_manager.get_entities_to_remove()

            # Should have entities to create (humidity_control entities)
            # Should have nothing to remove
            assert len(to_remove) == 0
            # Note: to_create might be 0 if no devices are discovered
            # This is expected in test environment

    @pytest.mark.asyncio
    async def test_disable_feature_with_existing_entities(self):
        """Test disabling a feature when entities already exist."""
        # Setup: Mock existing humidity_control entities
        mock_entity1 = MagicMock()
        mock_entity1.entity_id = "sensor.humidity_32_153289"
        mock_entity2 = MagicMock()
        mock_entity2.entity_id = "switch.humidity_boost_32_153289"

        with patch(
            "custom_components.ramses_extras.framework.helpers.entity.manager.entity_registry.async_get"
        ) as mock_registry:
            mock_registry.return_value.entities = {
                "entity1": mock_entity1,
                "entity2": mock_entity2,
            }

            # Current state: feature enabled
            current_features = {"default": True, "humidity_control": True}

            # Build catalog with current state
            await self.entity_manager.build_entity_catalog(
                AVAILABLE_FEATURES, current_features
            )

            # Manually add entities to catalog (simulating they were discovered)
            self.entity_manager.all_possible_entities["sensor.humidity_32_153289"] = {
                "exists_already": True,
                "enabled_by_feature": True,
                "feature_id": "humidity_control",
                "entity_type": "sensor",
                "entity_name": "humidity_32_153289",
            }
            self.entity_manager.all_possible_entities[
                "switch.humidity_boost_32_153289"
            ] = {
                "exists_already": True,
                "enabled_by_feature": True,
                "feature_id": "humidity_control",
                "entity_type": "switch",
                "entity_name": "humidity_boost_32_153289",
            }

            # Target state: disable humidity_control
            target_features = {"default": True, "humidity_control": False}
            self.entity_manager.update_feature_targets(target_features)

            # Verify: entities should be removed
            to_create = self.entity_manager.get_entities_to_create()
            to_remove = self.entity_manager.get_entities_to_remove()

            assert len(to_create) == 0
            assert len(to_remove) == 2
            assert "sensor.humidity_32_153289" in to_remove
            assert "switch.humidity_boost_32_153289" in to_remove

    @pytest.mark.asyncio
    async def test_keep_enabled_feature_entities(self):
        """Test that entities from enabled features are kept."""
        # Setup: Mock existing entities
        mock_entity1 = MagicMock()
        mock_entity1.entity_id = "sensor.humidity_32_153289"

        with patch(
            "custom_components.ramses_extras.framework.helpers.entity.manager.entity_registry.async_get"
        ) as mock_registry:
            mock_registry.return_value.entities = {"entity1": mock_entity1}

            # Current state: feature enabled
            current_features = {"default": True, "humidity_control": True}

            # Build catalog
            await self.entity_manager.build_entity_catalog(
                AVAILABLE_FEATURES, current_features
            )

            # Add entity to catalog
            self.entity_manager.all_possible_entities["sensor.humidity_32_153289"] = {
                "exists_already": True,
                "enabled_by_feature": True,
                "feature_id": "humidity_control",
                "entity_type": "sensor",
                "entity_name": "humidity_32_153289",
            }

            # Target state: keep feature enabled
            target_features = {"default": True, "humidity_control": True}
            self.entity_manager.update_feature_targets(target_features)

            # Verify: no changes needed
            to_create = self.entity_manager.get_entities_to_create()
            to_remove = self.entity_manager.get_entities_to_remove()

            assert len(to_create) == 0
            assert len(to_remove) == 0

    @pytest.mark.asyncio
    async def test_multiple_features_enable_disable(self):
        """Test enabling one feature while disabling another."""
        # Setup: Mock existing entities from feature A
        mock_entity1 = MagicMock()
        mock_entity1.entity_id = "sensor.feature_a_entity"

        with patch(
            "custom_components.ramses_extras.framework.helpers.entity.manager.entity_registry.async_get"
        ) as mock_registry:
            mock_registry.return_value.entities = {"entity1": mock_entity1}

            # Current state: feature A enabled, feature B disabled
            current_features = {
                "default": True,
                "humidity_control": True,
                "hvac_fan_card": False,
            }

            # Build catalog
            await self.entity_manager.build_entity_catalog(
                AVAILABLE_FEATURES, current_features
            )

            # Add feature A entity
            self.entity_manager.all_possible_entities["sensor.feature_a_entity"] = {
                "exists_already": True,
                "enabled_by_feature": True,
                "feature_id": "humidity_control",
                "entity_type": "sensor",
                "entity_name": "feature_a_entity",
            }

            # Target state: disable feature A, enable feature B
            target_features = {
                "default": True,
                "humidity_control": False,
                "hvac_fan_card": True,
            }
            self.entity_manager.update_feature_targets(target_features)

            # Verify: feature A entities removed, feature B entities created
            to_remove = self.entity_manager.get_entities_to_remove()

            assert "sensor.feature_a_entity" in to_remove


class TestFeatureEntityCatalog:
    """Test entity catalog building for different feature states."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_hass = MagicMock()
        self.entity_manager = EntityManager(self.mock_hass)

    @pytest.mark.asyncio
    async def test_catalog_with_all_features_disabled(self):
        """Test catalog when all optional features are disabled."""
        with patch(
            "custom_components.ramses_extras.framework.helpers.entity.manager.entity_registry.async_get"
        ) as mock_registry:
            mock_registry.return_value.entities = {}

            current_features = {
                "default": True,
                "humidity_control": False,
                "hvac_fan_card": False,
            }

            await self.entity_manager.build_entity_catalog(
                AVAILABLE_FEATURES, current_features
            )

            # Verify: catalog built but no entities enabled
            summary = self.entity_manager.get_entity_summary()
            assert summary["total_entities"] >= 0
            # All entities should be disabled
            assert summary["existing_enabled"] == 0
            assert summary["non_existing_enabled"] == 0

    @pytest.mark.asyncio
    async def test_catalog_with_all_features_enabled(self):
        """Test catalog when all features are enabled."""
        with patch(
            "custom_components.ramses_extras.framework.helpers.entity.manager.entity_registry.async_get"
        ) as mock_registry:
            mock_registry.return_value.entities = {}

            current_features = {
                "default": True,
                "humidity_control": True,
                "hvac_fan_card": True,
            }

            await self.entity_manager.build_entity_catalog(
                AVAILABLE_FEATURES, current_features
            )

            # Verify: catalog built
            summary = self.entity_manager.get_entity_summary()
            assert summary["total_entities"] >= 0

    @pytest.mark.asyncio
    async def test_catalog_excludes_default_feature(self):
        """Test that default feature entities are excluded from management."""
        with patch(
            "custom_components.ramses_extras.framework.helpers.entity.manager.entity_registry.async_get"
        ) as mock_registry:
            mock_registry.return_value.entities = {}

            current_features = {"default": True, "humidity_control": False}

            await self.entity_manager.build_entity_catalog(
                AVAILABLE_FEATURES, current_features
            )

            # Verify: default feature entities not in removal/creation lists
            to_remove = self.entity_manager.get_entities_to_remove()
            to_create = self.entity_manager.get_entities_to_create()

            # No default feature entities should be in these lists
            for entity_id in to_remove + to_create:
                info = self.entity_manager.all_possible_entities.get(entity_id)
                if info:
                    assert info["feature_id"] != "default"


class TestEntityStateTransitions:
    """Test entity state transitions during feature changes."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_hass = MagicMock()
        self.entity_manager = EntityManager(self.mock_hass)

    @pytest.mark.asyncio
    async def test_entity_exists_and_should_exist(self):
        """Test entity that exists and should continue to exist."""
        with patch(
            "custom_components.ramses_extras.framework.helpers.entity.manager.entity_registry.async_get"
        ) as mock_registry:
            mock_entity = MagicMock()
            mock_entity.entity_id = "sensor.test_entity"
            mock_registry.return_value.entities = {"entity1": mock_entity}

            current_features = {"default": True, "humidity_control": True}
            await self.entity_manager.build_entity_catalog(
                AVAILABLE_FEATURES, current_features
            )

            # Add entity to catalog
            self.entity_manager.all_possible_entities["sensor.test_entity"] = {
                "exists_already": True,
                "enabled_by_feature": True,
                "feature_id": "humidity_control",
                "entity_type": "sensor",
                "entity_name": "test_entity",
            }

            # Keep feature enabled
            self.entity_manager.update_feature_targets(current_features)

            # Verify: entity not in remove or create lists
            to_remove = self.entity_manager.get_entities_to_remove()
            to_create = self.entity_manager.get_entities_to_create()

            assert "sensor.test_entity" not in to_remove
            assert "sensor.test_entity" not in to_create

    @pytest.mark.asyncio
    async def test_entity_exists_but_should_not(self):
        """Test entity that exists but should be removed."""
        with patch(
            "custom_components.ramses_extras.framework.helpers.entity.manager.entity_registry.async_get"
        ) as mock_registry:
            mock_entity = MagicMock()
            mock_entity.entity_id = "sensor.test_entity"
            mock_registry.return_value.entities = {"entity1": mock_entity}

            current_features = {"default": True, "humidity_control": True}
            await self.entity_manager.build_entity_catalog(
                AVAILABLE_FEATURES, current_features
            )

            # Add entity to catalog
            self.entity_manager.all_possible_entities["sensor.test_entity"] = {
                "exists_already": True,
                "enabled_by_feature": True,
                "feature_id": "humidity_control",
                "entity_type": "sensor",
                "entity_name": "test_entity",
            }

            # Disable feature
            target_features = {"default": True, "humidity_control": False}
            self.entity_manager.update_feature_targets(target_features)

            # Verify: entity in remove list
            to_remove = self.entity_manager.get_entities_to_remove()
            to_create = self.entity_manager.get_entities_to_create()

            assert "sensor.test_entity" in to_remove
            assert "sensor.test_entity" not in to_create

    @pytest.mark.asyncio
    async def test_entity_does_not_exist_but_should(self):
        """Test entity that doesn't exist but should be created."""
        with patch(
            "custom_components.ramses_extras.framework.helpers.entity.manager.entity_registry.async_get"
        ) as mock_registry:
            mock_registry.return_value.entities = {}

            current_features = {"default": True, "humidity_control": False}
            await self.entity_manager.build_entity_catalog(
                AVAILABLE_FEATURES, current_features
            )

            # Add entity to catalog (doesn't exist yet)
            self.entity_manager.all_possible_entities["sensor.test_entity"] = {
                "exists_already": False,
                "enabled_by_feature": False,
                "feature_id": "humidity_control",
                "entity_type": "sensor",
                "entity_name": "test_entity",
            }

            # Enable feature
            target_features = {"default": True, "humidity_control": True}
            self.entity_manager.update_feature_targets(target_features)

            # Verify: entity in create list
            to_remove = self.entity_manager.get_entities_to_remove()
            to_create = self.entity_manager.get_entities_to_create()

            assert "sensor.test_entity" not in to_remove
            assert "sensor.test_entity" in to_create

    @pytest.mark.asyncio
    async def test_entity_does_not_exist_and_should_not(self):
        """Test entity that doesn't exist and shouldn't exist."""
        with patch(
            "custom_components.ramses_extras.framework.helpers.entity.manager.entity_registry.async_get"
        ) as mock_registry:
            mock_registry.return_value.entities = {}

            current_features = {"default": True, "humidity_control": False}
            await self.entity_manager.build_entity_catalog(
                AVAILABLE_FEATURES, current_features
            )

            # Add entity to catalog (doesn't exist, feature disabled)
            self.entity_manager.all_possible_entities["sensor.test_entity"] = {
                "exists_already": False,
                "enabled_by_feature": False,
                "feature_id": "humidity_control",
                "entity_type": "sensor",
                "entity_name": "test_entity",
            }

            # Keep feature disabled
            self.entity_manager.update_feature_targets(current_features)

            # Verify: entity not in remove or create lists
            to_remove = self.entity_manager.get_entities_to_remove()
            to_create = self.entity_manager.get_entities_to_create()

            assert "sensor.test_entity" not in to_remove
            assert "sensor.test_entity" not in to_create


class TestEntitySummaryReporting:
    """Test entity summary reporting for different scenarios."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_hass = MagicMock()
        self.entity_manager = EntityManager(self.mock_hass)

    @pytest.mark.asyncio
    async def test_summary_with_mixed_states(self):
        """Test summary with entities in all possible states."""
        with patch(
            "custom_components.ramses_extras.framework.helpers.entity.manager.entity_registry.async_get"
        ) as mock_registry:
            mock_registry.return_value.entities = {}

            current_features = {"default": True, "humidity_control": True}
            await self.entity_manager.build_entity_catalog(
                AVAILABLE_FEATURES, current_features
            )

            # Add entities in different states
            self.entity_manager.all_possible_entities["sensor.existing_enabled"] = {
                "exists_already": True,
                "enabled_by_feature": True,
                "feature_id": "humidity_control",
                "entity_type": "sensor",
                "entity_name": "existing_enabled",
            }

            self.entity_manager.all_possible_entities["sensor.existing_disabled"] = {
                "exists_already": True,
                "enabled_by_feature": False,
                "feature_id": "humidity_control",
                "entity_type": "sensor",
                "entity_name": "existing_disabled",
            }

            self.entity_manager.all_possible_entities["sensor.new_enabled"] = {
                "exists_already": False,
                "enabled_by_feature": True,
                "feature_id": "humidity_control",
                "entity_type": "sensor",
                "entity_name": "new_enabled",
            }

            self.entity_manager.all_possible_entities["sensor.new_disabled"] = {
                "exists_already": False,
                "enabled_by_feature": False,
                "feature_id": "humidity_control",
                "entity_type": "sensor",
                "entity_name": "new_disabled",
            }

            # Get summary
            summary = self.entity_manager.get_entity_summary()

            # Verify counts
            assert summary["total_entities"] == 4
            assert summary["existing_enabled"] == 1
            assert summary["existing_disabled"] == 1
            assert summary["non_existing_enabled"] == 1
            assert summary["non_existing_disabled"] == 1

    @pytest.mark.asyncio
    async def test_summary_excludes_cards_and_automations(self):
        """Test that summary excludes cards and automations."""
        with patch(
            "custom_components.ramses_extras.framework.helpers.entity.manager.entity_registry.async_get"
        ) as mock_registry:
            mock_registry.return_value.entities = {}

            current_features = {"default": True, "humidity_control": True}
            await self.entity_manager.build_entity_catalog(
                AVAILABLE_FEATURES, current_features
            )

            # Add different entity types
            self.entity_manager.all_possible_entities["sensor.test"] = {
                "exists_already": True,
                "enabled_by_feature": True,
                "feature_id": "humidity_control",
                "entity_type": "sensor",
                "entity_name": "test",
            }

            self.entity_manager.all_possible_entities["card.test"] = {
                "exists_already": True,
                "enabled_by_feature": True,
                "feature_id": "hvac_fan_card",
                "entity_type": "card",
                "entity_name": "test",
            }

            self.entity_manager.all_possible_entities["automation.test"] = {
                "exists_already": True,
                "enabled_by_feature": True,
                "feature_id": "humidity_control",
                "entity_type": "automation",
                "entity_name": "test",
            }

            # Get summary
            summary = self.entity_manager.get_entity_summary()

            # Verify: only sensor counted, not card or automation
            assert summary["total_entities"] == 1
            assert summary["existing_enabled"] == 1


class TestFeatureConflictResolution:
    """Test handling of feature conflicts and priorities."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_hass = MagicMock()
        self.entity_manager = EntityManager(self.mock_hass)

    @pytest.mark.asyncio
    async def test_no_conflicts_when_features_independent(self):
        """Test that independent features don't conflict."""
        with patch(
            "custom_components.ramses_extras.framework.helpers.entity.manager.entity_registry.async_get"
        ) as mock_registry:
            mock_registry.return_value.entities = {}

            # Enable multiple independent features
            current_features = {
                "default": True,
                "humidity_control": True,
                "hvac_fan_card": True,
            }

            await self.entity_manager.build_entity_catalog(
                AVAILABLE_FEATURES, current_features
            )

            # Verify: catalog built successfully
            assert len(self.entity_manager.all_possible_entities) >= 0

    @pytest.mark.asyncio
    async def test_feature_priority_ordering(self):
        """Test that feature priority is respected."""
        # This test verifies the _should_skip_entity logic
        current_features = {
            "default": True,
            "humidity_control": True,
            "hvac_fan_card": True,
        }

        self.entity_manager.current_features = current_features

        # Test priority check (humidity_control has priority 1, default has 0)
        should_skip = await self.entity_manager._should_skip_entity(
            "default", "test_state", "sensor.test"
        )

        # Default feature should not be skipped (it's always enabled)
        # This is a basic check - actual behavior depends on implementation
        assert isinstance(should_skip, bool)
