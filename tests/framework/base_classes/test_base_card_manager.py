# tests/framework/base_classes/test_base_card_manager.py
"""Test base card manager."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.ramses_extras.framework.base_classes.base_card_manager import (
    BaseCardManager,
)


class TestBaseCardManager:
    """Test BaseCardManager class."""

    def test_init(self, hass):
        """Test initialization of BaseCardManager."""
        config_entry = MagicMock()
        feature_name = "humidity_control"

        manager = BaseCardManager(hass, config_entry, feature_name)

        assert manager.hass == hass
        assert manager.config_entry == config_entry
        assert manager.feature_name == feature_name
        assert manager._registered_cards == {}

    def test_get_card_configurations_default(self, hass):
        """Test default _get_card_configurations implementation."""
        config_entry = MagicMock()
        manager = BaseCardManager(hass, config_entry, "test_feature")

        result = manager._get_card_configurations()

        # Default implementation returns empty list
        assert result == []

    @pytest.mark.asyncio
    async def test_async_register_cards_success(self, hass):
        """Test successful card registration."""
        config_entry = MagicMock()
        manager = BaseCardManager(hass, config_entry, "test_feature")

        # Mock card configurations
        card_configs = [
            {
                "card_id": "test_card",
                "card_name": "Test Card",
                "description": "A test card",
            }
        ]

        # Mock card registration info
        card_info = {
            "type": "test_card",
            "name": "Test Card",
            "description": "A test card",
            "js_path": "features/test_feature/test_card.js",
            "card_dir_path": "features/test_feature",
            "location": "test_card",
            "feature": "test_feature",
        }

        with (
            patch.object(
                manager, "_get_card_configurations", return_value=card_configs
            ),
            patch.object(manager, "_register_single_card", return_value=card_info),
        ):
            result = await manager.async_register_cards()

            assert "test_card" in result
            assert result["test_card"] == card_info
            assert manager._registered_cards == result

    @pytest.mark.asyncio
    async def test_async_register_cards_no_configs(self, hass):
        """Test card registration with no configurations."""
        config_entry = MagicMock()
        manager = BaseCardManager(hass, config_entry, "test_feature")

        with patch.object(manager, "_get_card_configurations", return_value=[]):
            result = await manager.async_register_cards()

            assert result == {}
            assert manager._registered_cards == {}

    @pytest.mark.asyncio
    async def test_async_register_cards_registration_failure(self, hass):
        """Test card registration when single card registration fails."""
        config_entry = MagicMock()
        manager = BaseCardManager(hass, config_entry, "test_feature")

        card_configs = [
            {
                "card_id": "failing_card",
                "card_name": "Failing Card",
            }
        ]

        with (
            patch.object(
                manager, "_get_card_configurations", return_value=card_configs
            ),
            patch.object(manager, "_register_single_card", return_value=None),
        ):
            result = await manager.async_register_cards()

            # Failed registration should result in empty dict
            assert result == {}
            assert manager._registered_cards == {}

    @pytest.mark.asyncio
    async def test_async_register_cards_exception_handling(self, hass):
        """Test exception handling in card registration."""
        config_entry = MagicMock()
        manager = BaseCardManager(hass, config_entry, "test_feature")

        with patch.object(
            manager, "_get_card_configurations", side_effect=Exception("Config error")
        ):
            result = await manager.async_register_cards()

            assert result == {}
            assert manager._registered_cards == {}

    @pytest.mark.asyncio
    async def test_register_single_card_success(self, hass):
        """Test successful single card registration."""
        config_entry = MagicMock()
        manager = BaseCardManager(hass, config_entry, "test_feature")

        card_config = {
            "card_id": "test_card",
            "card_name": "Test Card",
            "description": "A test card",
            "location": "custom_location",
            "preview": False,
            "documentation_url": "https://example.com",
        }

        # Mock file existence checks
        with (
            patch(
                "custom_components.ramses_extras.framework.base_classes.base_card_manager.DEPLOYMENT_PATHS"
            ) as mock_paths,
            patch(
                "custom_components.ramses_extras.framework.base_classes.base_card_manager.INTEGRATION_DIR"
            ),
        ):
            mock_source_path = MagicMock(spec=Path)
            mock_js_path = MagicMock(spec=Path)
            mock_paths.get_source_feature_path.return_value = mock_source_path
            mock_source_path.__truediv__.return_value = mock_js_path
            mock_source_path.exists.return_value = True
            mock_js_path.exists.return_value = True

            # Mock relative path calculations
            mock_js_path.relative_to.return_value = Path(
                "features/test_feature/test_card.js"
            )
            mock_source_path.relative_to.return_value = Path("features/test_feature")

            result = await manager._register_single_card(card_config)

            assert result is not None
            assert result["type"] == "test_card"
            assert result["name"] == "Test Card"
            assert result["description"] == "A test card"
            assert result["preview"] is False
            assert result["documentation_url"] == "https://example.com"
            assert result["location"] == "custom_location"
            assert result["feature"] == "test_feature"

    @pytest.mark.asyncio
    async def test_register_single_card_missing_directory(self, hass):
        """Test single card registration when directory doesn't exist."""
        config_entry = MagicMock()
        manager = BaseCardManager(hass, config_entry, "test_feature")

        card_config = {
            "card_id": "test_card",
            "card_name": "Test Card",
        }

        with patch(
            "custom_components.ramses_extras.framework.base_classes.base_card_manager.DEPLOYMENT_PATHS"
        ) as mock_paths:
            mock_source_path = MagicMock(spec=Path)
            mock_paths.get_source_feature_path.return_value = mock_source_path
            mock_source_path.exists.return_value = False  # Directory doesn't exist

            result = await manager._register_single_card(card_config)

            assert result is None

    @pytest.mark.asyncio
    async def test_register_single_card_missing_js_file(self, hass):
        """Test single card registration when JS file doesn't exist."""
        config_entry = MagicMock()
        manager = BaseCardManager(hass, config_entry, "test_feature")

        card_config = {
            "card_id": "test_card",
            "card_name": "Test Card",
        }

        with (
            patch(
                "custom_components.ramses_extras.framework.base_classes.base_card_manager.DEPLOYMENT_PATHS"
            ) as mock_paths,
            patch(
                "custom_components.ramses_extras.framework.base_classes.base_card_manager.INTEGRATION_DIR"
            ),
        ):
            mock_source_path = MagicMock(spec=Path)
            mock_js_path = MagicMock(spec=Path)
            mock_paths.get_source_feature_path.return_value = mock_source_path
            mock_source_path.__truediv__.return_value = mock_js_path
            mock_source_path.exists.return_value = True  # Directory exists
            mock_js_path.exists.return_value = False  # JS file doesn't exist

            result = await manager._register_single_card(card_config)

            assert result is None

    @pytest.mark.asyncio
    async def test_register_single_card_exception_handling(self, hass):
        """Test exception handling in single card registration."""
        config_entry = MagicMock()
        manager = BaseCardManager(hass, config_entry, "test_feature")

        # Invalid config missing required fields
        card_config = {}

        result = await manager._register_single_card(card_config)

        assert result is None

    @pytest.mark.asyncio
    async def test_async_cleanup(self, hass):
        """Test async cleanup functionality."""
        config_entry = MagicMock()
        manager = BaseCardManager(hass, config_entry, "test_feature")

        # Add some registered cards
        manager._registered_cards = {
            "card1": {"name": "Card 1"},
            "card2": {"name": "Card 2"},
        }

        await manager.async_cleanup()

        assert manager._registered_cards == {}

    def test_get_registered_cards(self, hass):
        """Test getting registered cards."""
        config_entry = MagicMock()
        manager = BaseCardManager(hass, config_entry, "test_feature")

        # Set up registered cards
        original_cards = {
            "card1": {"name": "Card 1", "type": "card1"},
            "card2": {"name": "Card 2", "type": "card2"},
        }
        manager._registered_cards = original_cards

        result = manager.get_registered_cards()

        # Should return a copy, not the original
        assert result == original_cards
        assert result is not manager._registered_cards  # Should be a different object

        # Modifying the returned dict shouldn't affect the original
        result["card3"] = {"name": "Card 3"}
        assert "card3" not in manager._registered_cards
