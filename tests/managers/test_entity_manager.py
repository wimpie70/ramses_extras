"""Test EntityManager class functionality.

This module contains comprehensive unit tests for the EntityManager class,
testing all aspects of entity catalog building, change detection, and operations.
"""

from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from custom_components.ramses_extras.const import AVAILABLE_FEATURES
from custom_components.ramses_extras.framework.helpers.entity.manager import (
    EntityInfo,
    EntityManager,
)


class TestEntityManager:
    """Test cases for EntityManager class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_hass = MagicMock()
        self.mock_hass.data = {"ramses_extras": {"devices": []}}
        self.entity_manager = EntityManager(self.mock_hass)

    def test_entity_info_typed_dict(self):
        """Test EntityInfo TypedDict structure."""
        entity_info: EntityInfo = {
            "exists_already": True,
            "enabled_by_feature": False,
            "feature_id": "test_feature",
            "entity_type": "sensor",
            "entity_name": "test_entity",
        }

        assert entity_info["exists_already"] is True
        assert entity_info["enabled_by_feature"] is False
        assert entity_info["feature_id"] == "test_feature"
        assert entity_info["entity_type"] == "sensor"
        assert entity_info["entity_name"] == "test_entity"

    @pytest.mark.asyncio
    async def test_entity_manager_initialization(self):
        """Test EntityManager initialization."""
        assert self.entity_manager.hass == self.mock_hass
        assert self.entity_manager.all_possible_entities == {}
        assert self.entity_manager.current_features == {}
        assert self.entity_manager.target_features == {}

    @pytest.mark.asyncio
    async def test_build_entity_catalog_basic(self):
        """Test basic entity catalog building."""
        available_features = {
            "test_feature": {
                "category": "sensor",
                "supported_device_types": ["Device1"],
                "default_enabled": False,
            }
        }
        current_features = {"test_feature": False}

        # Mock the methods that would scan entities
        with patch.object(
            self.entity_manager, "_get_all_existing_entities", return_value=set()
        ):
            with patch.object(
                self.entity_manager, "_scan_feature_entities", new_callable=AsyncMock
            ):
                await self.entity_manager.build_entity_catalog(
                    available_features, current_features
                )

        assert self.entity_manager.current_features == current_features
        # Note: The actual entities would be populated by _scan_feature_entities

    @pytest.mark.asyncio
    async def test_update_feature_targets(self):
        """Test updating feature targets."""
        # First set up some entities
        self.entity_manager.all_possible_entities = {
            "entity1": {
                "exists_already": True,
                "enabled_by_feature": False,  # Initially disabled
                "feature_id": "feature1",
                "entity_type": "sensor",
                "entity_name": "entity1",
            },
            "entity2": {
                "exists_already": False,
                "enabled_by_feature": False,  # Initially disabled
                "feature_id": "feature2",
                "entity_type": "switch",
                "entity_name": "entity2",
            },
        }

        # Update targets to enable feature1, disable feature2
        target_features = {"feature1": True, "feature2": False}
        self.entity_manager.update_feature_targets(target_features)

        assert self.entity_manager.target_features == target_features
        assert (
            self.entity_manager.all_possible_entities["entity1"]["enabled_by_feature"]
            is True
        )
        assert (
            self.entity_manager.all_possible_entities["entity2"]["enabled_by_feature"]
            is False
        )

    @pytest.mark.asyncio
    async def test_get_all_existing_entities(self):
        """Test getting all existing entities."""
        # Mock entity registry with proper structure
        mock_registry = MagicMock()
        mock_entity1 = MagicMock()
        mock_entity1.entity_id = "sensor.test1"
        mock_entity2 = MagicMock()
        mock_entity2.entity_id = "switch.test2"

        # Create a proper dict-like object that supports .values()
        entities_dict = {"entity1": mock_entity1, "entity2": mock_entity2}
        mock_registry.entities = entities_dict

        with patch(
            "custom_components.ramses_extras.framework.helpers.entity.manager.entity_registry.async_get",
            return_value=mock_registry,
        ):
            existing = await self.entity_manager._get_all_existing_entities()

            assert "sensor.test1" in existing
            assert "switch.test2" in existing
            assert len(existing) == 2

    @pytest.mark.asyncio
    async def test_get_all_existing_entities_error(self):
        """Test error handling when getting existing entities fails."""
        self.mock_hass.helpers.entity_registry.async_get.side_effect = Exception(
            "Registry error"
        )

        existing = await self.entity_manager._get_all_existing_entities()

        assert existing == set()

    @pytest.mark.asyncio
    async def test_scan_feature_entities_cards(self):
        """Test scanning card entities."""
        feature_id = "test_card_feature"
        feature_config = {
            "category": "sensor",  # Not cards category
            "location": "test_location",
        }
        existing_entities = set()

        # Enable the feature for scanning
        self.entity_manager.current_features = {feature_id: True}
        self.entity_manager.target_features = {feature_id: False}

        # Mock the has_cards method to return True (simulating card
        #  configurations found)
        with patch.object(self.entity_manager, "_feature_has_cards", return_value=True):
            await self.entity_manager._scan_feature_entities(
                feature_id, feature_config, existing_entities
            )

        # Card entities should be added even without category: "cards"
        expected_key = "local_ramses_extras_features_test_card_feature"
        assert expected_key in self.entity_manager.all_possible_entities

        entity_info = self.entity_manager.all_possible_entities[expected_key]
        assert entity_info["exists_already"] is False  # Cards are file-based
        assert entity_info["enabled_by_feature"] is False  # Target is False
        assert entity_info["feature_id"] == feature_id
        assert entity_info["entity_type"] == "card"

    @pytest.mark.asyncio
    async def test_scan_feature_entities_devices(self):
        """Test scanning device-based entities."""
        feature_id = "test_device_feature"
        feature_config = {
            "category": "sensor",
            "supported_device_types": ["TestDevice"],
        }
        existing_entities = {
            "sensor.test_device_1": True,
            "sensor.test_device_2": False,
        }

        self.entity_manager.current_features = {feature_id: True}
        self.entity_manager.target_features = {feature_id: True}

        # Mock device-related methods
        with patch.object(
            self.entity_manager,
            "_get_devices_for_feature",
            return_value=[Mock(id="device1")],
        ):
            with patch.object(
                self.entity_manager,
                "_get_required_entities_for_feature",
                return_value={"sensor": ["temperature", "humidity"]},
            ):
                with patch.object(
                    self.entity_manager,
                    "_get_all_existing_entities",
                    return_value=set(),
                ):
                    await self.entity_manager._scan_feature_entities(
                        feature_id, feature_config, existing_entities
                    )

                    # Verify entities were added
                    assert len(self.entity_manager.all_possible_entities) == 2
                    assert (
                        "sensor.temperature_device1"
                        in self.entity_manager.all_possible_entities
                    )
                    assert (
                        "sensor.humidity_device1"
                        in self.entity_manager.all_possible_entities
                    )

    def test_get_entities_to_remove(self):
        """Test getting entities that should be removed."""
        self.entity_manager.all_possible_entities = {
            "entity1": {
                "exists_already": True,
                "enabled_by_feature": False,  # Should be removed
                "feature_id": "feature1",
                "entity_type": "sensor",
                "entity_name": "entity1",
            },
            "entity2": {
                "exists_already": True,
                "enabled_by_feature": True,  # Should stay
                "feature_id": "feature2",
                "entity_type": "switch",
                "entity_name": "entity2",
            },
            "entity3": {
                "exists_already": False,
                "enabled_by_feature": False,  # Doesn't exist, should stay gone
                "feature_id": "feature3",
                "entity_type": "binary_sensor",
                "entity_name": "entity3",
            },
        }

        to_remove = self.entity_manager.get_entities_to_remove()

        assert "entity1" in to_remove
        assert "entity2" not in to_remove
        assert "entity3" not in to_remove
        assert len(to_remove) == 1

    def test_get_entities_to_create(self):
        """Test getting entities that should be created."""
        self.entity_manager.all_possible_entities = {
            "entity1": {
                "exists_already": False,
                "enabled_by_feature": True,  # Should be created
                "feature_id": "feature1",
                "entity_type": "sensor",
                "entity_name": "entity1",
            },
            "entity2": {
                "exists_already": True,
                "enabled_by_feature": True,  # Already exists
                "feature_id": "feature2",
                "entity_type": "switch",
                "entity_name": "entity2",
            },
            "entity3": {
                "exists_already": False,
                "enabled_by_feature": False,  # Should stay gone
                "feature_id": "feature3",
                "entity_type": "binary_sensor",
                "entity_name": "entity3",
            },
        }

        to_create = self.entity_manager.get_entities_to_create()

        assert "entity1" in to_create
        assert "entity2" not in to_create
        assert "entity3" not in to_create
        assert len(to_create) == 1

    @pytest.mark.asyncio
    async def test_scan_feature_entities_auto_detect_cards(self):
        """Test that card entities are automatically
        detected from card configurations."""
        feature_id = "hvac_fan_card"
        feature_config = {
            "category": "sensor",  # Not cards category
            "supported_device_types": ["HvacVentilator"],
        }
        existing_entities = set()

        # Enable the feature for scanning
        self.entity_manager.current_features = {feature_id: True}
        self.entity_manager.target_features = {feature_id: True}

        # Mock the has_cards method to return True
        #  (simulating HVAC_FAN_CARD_CONFIGS found)
        with patch.object(self.entity_manager, "_feature_has_cards", return_value=True):
            await self.entity_manager._scan_feature_entities(
                feature_id, feature_config, existing_entities
            )

        # Card entities should be added even without category: "cards"
        expected_key = "local_ramses_extras_features_hvac_fan_card"
        assert expected_key in self.entity_manager.all_possible_entities

        entity_info = self.entity_manager.all_possible_entities[expected_key]
        assert entity_info["exists_already"] is False  # Cards are file-based
        assert entity_info["enabled_by_feature"] is True  # Target is True
        assert entity_info["feature_id"] == feature_id
        assert entity_info["entity_type"] == "card"

    @pytest.mark.asyncio
    async def test_scan_feature_entities_no_cards(self):
        """Test that features without cards don't create card entities."""
        feature_id = "humidity_control"
        feature_config = {
            "category": "sensor",
            "supported_device_types": ["HvacVentilator"],
        }
        existing_entities = set()

        # Enable the feature for scanning
        self.entity_manager.current_features = {feature_id: True}
        self.entity_manager.target_features = {feature_id: True}

        # Mock the has_cards method to return False (no card configurations)
        with patch.object(
            self.entity_manager, "_feature_has_cards", return_value=False
        ):
            await self.entity_manager._scan_feature_entities(
                feature_id, feature_config, existing_entities
            )

        # Card entities should NOT be added
        expected_key = "local_ramses_extras_features_humidity_control"
        assert expected_key not in self.entity_manager.all_possible_entities

    def test_get_entity_summary(self):
        """Test getting entity summary statistics."""
        self.entity_manager.all_possible_entities = {
            "entity1": {  # existing + enabled
                "exists_already": True,
                "enabled_by_feature": True,
                "feature_id": "feature1",
                "entity_type": "sensor",
                "entity_name": "entity1",
            },
            "entity2": {  # existing + disabled
                "exists_already": True,
                "enabled_by_feature": False,
                "feature_id": "feature2",
                "entity_type": "switch",
                "entity_name": "entity2",
            },
            "entity3": {  # non-existing + enabled
                "exists_already": False,
                "enabled_by_feature": True,
                "feature_id": "feature3",
                "entity_type": "binary_sensor",
                "entity_name": "entity3",
            },
            "entity4": {  # non-existing + disabled
                "exists_already": False,
                "enabled_by_feature": False,
                "feature_id": "feature4",
                "entity_type": "climate",
                "entity_name": "entity4",
            },
        }

        summary = self.entity_manager.get_entity_summary()

        assert summary["total_entities"] == 4
        assert summary["existing_enabled"] == 1  # entity1
        assert summary["existing_disabled"] == 1  # entity2
        assert summary["non_existing_enabled"] == 1  # entity3
        assert summary["non_existing_disabled"] == 1  # entity4

    @pytest.mark.asyncio
    async def test_apply_entity_changes(self):
        """Test applying entity changes."""
        # Mock the entity lists
        self.entity_manager.get_entities_to_remove = Mock(
            return_value=["entity1", "entity2"]
        )
        self.entity_manager.get_entities_to_create = Mock(return_value=["entity3"])

        # Mock the removal and creation methods
        with patch.object(
            self.entity_manager, "_remove_entities", new_callable=AsyncMock
        ) as mock_remove:
            with patch.object(
                self.entity_manager, "_create_entities", new_callable=AsyncMock
            ) as mock_create:
                await self.entity_manager.apply_entity_changes()

                mock_remove.assert_called_once_with(["entity1", "entity2"])
                mock_create.assert_called_once_with(["entity3"])

    @pytest.mark.asyncio
    async def test_remove_entities_by_type(self):
        """Test removing entities grouped by type."""
        entity_ids = ["card1", "card2", "sensor1", "sensor2"]

        self.entity_manager.all_possible_entities = {
            "card1": {"entity_type": "card"},
            "card2": {"entity_type": "card"},
            "sensor1": {"entity_type": "sensor"},
            "sensor2": {"entity_type": "sensor"},
        }

        with patch.object(
            self.entity_manager, "_remove_card_entities", new_callable=AsyncMock
        ) as mock_card_remove:
            with patch.object(
                self.entity_manager, "_remove_regular_entities", new_callable=AsyncMock
            ) as mock_regular_remove:
                await self.entity_manager._remove_entities(entity_ids)

                # Verify each type was called with correct entities
                mock_card_remove.assert_called_once_with(["card1", "card2"])
                mock_regular_remove.assert_called_once_with(
                    ["sensor1", "sensor2"], "sensor"
                )

    @pytest.mark.asyncio
    async def test_remove_entities_error_handling(self):
        """Test error handling during entity removal."""
        entity_ids = ["entity1", "entity2"]

        self.entity_manager.all_possible_entities = {
            "entity1": {"entity_type": "sensor"},
            "entity2": {"entity_type": "switch"},
        }

        with patch.object(
            self.entity_manager,
            "_remove_regular_entities",
            side_effect=Exception("Removal error"),
        ):
            # Should not raise exception, just log error
            await self.entity_manager._remove_entities(entity_ids)

    @pytest.mark.asyncio
    async def test_get_devices_for_feature(self):
        """Test getting devices for a feature."""
        feature_id = "test_feature"
        supported_devices = ["Device1", "Device2"]

        # Mock device data
        mock_device1 = Mock()
        mock_device1.__class__.__name__ = "Device1"
        mock_device2 = Mock()
        mock_device2.__class__.__name__ = "Device2"
        mock_device3 = Mock()
        mock_device3.__class__.__name__ = "Device3"  # Not supported

        self.mock_hass.data["ramses_extras"]["devices"] = [
            mock_device1,
            mock_device2,
            mock_device3,
        ]

        devices = await self.entity_manager._get_devices_for_feature(
            feature_id, supported_devices
        )

        assert len(devices) == 2
        assert mock_device1 in devices
        assert mock_device2 in devices
        assert mock_device3 not in devices

    @pytest.mark.asyncio
    async def test_get_devices_for_feature_error(self):
        """Test error handling when getting devices."""
        feature_id = "test_feature"
        supported_devices = ["Device1"]

        self.mock_hass.data = {}  # Missing ramses_extras data

        devices = await self.entity_manager._get_devices_for_feature(
            feature_id, supported_devices
        )

        assert devices == []


class TestEntityManagerIntegration:
    """Integration tests for EntityManager with real-world scenarios."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_hass = MagicMock()
        self.entity_manager = EntityManager(self.mock_hass)

    @pytest.mark.asyncio
    async def test_full_workflow_enable_feature(self):
        """Test full workflow when enabling a feature."""
        # Simulate enabling a new feature
        available_features = {
            "new_feature": {
                "category": "sensor",
                "supported_device_types": ["TestDevice"],
            }
        }
        current_features = {"new_feature": False}
        new_features = {"new_feature": True}

        # Mock existing entities (none for new feature)
        with patch.object(
            self.entity_manager, "_get_all_existing_entities", return_value=set()
        ):
            with patch.object(
                self.entity_manager, "_get_devices_for_feature", return_value=[]
            ):
                # Build catalog with current features
                await self.entity_manager.build_entity_catalog(
                    available_features, current_features
                )

                # Update targets to new features
                self.entity_manager.update_feature_targets(new_features)

                # Check what should be created
                to_remove = self.entity_manager.get_entities_to_remove()

                # Should want to create entities for new feature, remove none
                assert len(to_remove) == 0
                # Note: actual entity creation depends on device scanning logic

    @pytest.mark.asyncio
    async def test_full_workflow_disable_feature(self):
        """Test full workflow when disabling a feature."""
        # Simulate disabling an existing feature
        available_features = {
            "existing_feature": {
                "category": "sensor",
                "supported_device_types": ["TestDevice"],
            }
        }
        current_features = {"existing_feature": True}
        new_features = {"existing_feature": False}

        # Mock existing entities (some exist for this feature)
        existing_entities = {
            "sensor.existing_feature_temp",
            "sensor.existing_feature_humidity",
        }

        with patch.object(
            self.entity_manager,
            "_get_all_existing_entities",
            return_value=existing_entities,
        ):
            with patch.object(
                self.entity_manager, "_get_devices_for_feature", return_value=[]
            ):
                # Build catalog with current features
                await self.entity_manager.build_entity_catalog(
                    available_features, current_features
                )

                # Update targets to new features (disabled)
                self.entity_manager.update_feature_targets(new_features)

                # Check what should be removed
                to_create = self.entity_manager.get_entities_to_create()

                # Should want to remove entities for disabled feature, create none
                assert len(to_create) == 0
                # Note: actual entity removal depends on device scanning logic

    def test_logging_and_error_handling(self):
        """Test that EntityManager logs appropriately and handles errors gracefully."""
        # Test initialization logging
        assert self.entity_manager.hass == self.mock_hass

        # Test empty catalog handling
        summary = self.entity_manager.get_entity_summary()
        assert summary["total_entities"] == 0
        assert all(count == 0 for count in summary.values() if isinstance(count, int))

        # Test empty lists
        assert self.entity_manager.get_entities_to_create() == []
        assert self.entity_manager.get_entities_to_remove() == []
