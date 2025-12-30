"""Tests for HVAC Fan Card feature in features/hvac_fan_card/__init__.py."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from custom_components.ramses_extras.features.hvac_fan_card import (
    HvacFanCardManager,
    create_hvac_fan_card_feature,
)
from custom_components.ramses_extras.features.hvac_fan_card.const import (
    DOMAIN as HVAC_FAN_CARD_DOMAIN,
)
from custom_components.ramses_extras.features.hvac_fan_card.const import (
    HVAC_FAN_CARD_CONFIGS,
)


class TestHvacFanCardManager:
    """Test cases for HvacFanCardManager."""

    def setup_method(self):
        """Set up test fixtures."""
        self.hass = MagicMock(spec=HomeAssistant)
        self.config_entry = MagicMock(spec=ConfigEntry)
        self.manager = HvacFanCardManager(self.hass, self.config_entry)

    def test_init(self):
        """Test initialization of HvacFanCardManager."""
        assert self.manager.hass == self.hass
        assert self.manager.config_entry == self.config_entry
        assert self.manager.feature_name == HVAC_FAN_CARD_DOMAIN

    def test_get_card_configurations(self):
        """Test getting card configurations."""
        result = self.manager._get_card_configurations()
        assert result == HVAC_FAN_CARD_CONFIGS
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_async_register_cards_success(self):
        """Test successful card registration."""
        with patch.object(self.manager, "_register_single_card") as mock_register:
            mock_register.return_value = {"name": "Test Card", "type": "test-card"}

            result = await self.manager.async_register_cards()

            assert len(result) == len(HVAC_FAN_CARD_CONFIGS)
            assert "hvac-fan-card" in result
            mock_register.assert_called()

    @pytest.mark.asyncio
    async def test_async_register_cards_failure(self):
        """Test card registration failure."""
        with patch.object(self.manager, "_register_single_card", return_value=None):
            result = await self.manager.async_register_cards()
            assert result == {}

    @pytest.mark.asyncio
    async def test_async_register_cards_exception(self):
        """Test card registration with exception."""
        with patch.object(
            self.manager, "_get_card_configurations", side_effect=Exception("Error")
        ):
            result = await self.manager.async_register_cards()
            assert result == {}

    @pytest.mark.asyncio
    async def test_register_single_card_success(self):
        """Test registering a single card successfully."""
        card_config = HVAC_FAN_CARD_CONFIGS[0]

        with patch(
            "custom_components.ramses_extras.framework.helpers.paths.DEPLOYMENT_PATHS.get_source_feature_path"
        ) as mock_path:
            mock_dir = MagicMock(spec=Path)
            mock_dir.exists.return_value = True
            mock_file = MagicMock(spec=Path)
            mock_file.exists.return_value = True
            # Mock relative_to to return a path-like string
            mock_file.relative_to.return_value = (
                "features/hvac_fan_card/hvac-fan-card.js"
            )
            mock_dir.relative_to.return_value = "features/hvac_fan_card"

            mock_path.return_value = mock_dir
            # Mock / operator
            mock_dir.__truediv__.return_value = mock_file

            result = await self.manager._register_single_card(card_config)

            assert result is not None
            assert result["type"] == card_config["card_id"]
            assert result["name"] == card_config["card_name"]

    @pytest.mark.asyncio
    async def test_register_single_card_missing_dir(self):
        """Test registering a single card with missing directory."""
        card_config = HVAC_FAN_CARD_CONFIGS[0]
        with patch(
            "custom_components.ramses_extras.framework.helpers.paths.DEPLOYMENT_PATHS.get_source_feature_path"
        ) as mock_path:
            mock_dir = MagicMock(spec=Path)
            mock_dir.exists.return_value = False
            mock_path.return_value = mock_dir

            result = await self.manager._register_single_card(card_config)
            assert result is None

    @pytest.mark.asyncio
    async def test_register_single_card_missing_file(self):
        """Test registering a single card with missing JS file."""
        card_config = HVAC_FAN_CARD_CONFIGS[0]
        with patch(
            "custom_components.ramses_extras.framework.helpers.paths.DEPLOYMENT_PATHS.get_source_feature_path"
        ) as mock_path:
            mock_dir = MagicMock(spec=Path)
            mock_dir.exists.return_value = True
            mock_file = MagicMock(spec=Path)
            mock_file.exists.return_value = False
            mock_path.return_value = mock_dir
            mock_dir.__truediv__.return_value = mock_file

            result = await self.manager._register_single_card(card_config)
            assert result is None

    @pytest.mark.asyncio
    async def test_async_cleanup(self):
        """Test cleanup of registered cards."""
        self.manager._registered_cards = {"card1": {}}
        await self.manager.async_cleanup()
        assert self.manager._registered_cards == {}

    def test_get_registered_cards(self):
        """Test getting registered cards copy."""
        self.manager._registered_cards = {"card1": {"name": "Test"}}
        cards = self.manager.get_registered_cards()
        assert cards == self.manager._registered_cards
        assert cards is not self.manager._registered_cards


class TestCreateHvacFanCardFeature:
    """Test cases for create_hvac_fan_card_feature factory function."""

    def setup_method(self):
        """Set up test fixtures."""
        self.hass = MagicMock(spec=HomeAssistant)
        self.config_entry = MagicMock(spec=ConfigEntry)

    def test_create_hvac_fan_card_feature(self):
        """Test creating HVAC fan card feature."""
        result = create_hvac_fan_card_feature(self.hass, self.config_entry)

        assert isinstance(result, dict)
        assert "card_manager" in result
        assert "feature_name" in result

        # Check card manager
        card_manager = result["card_manager"]
        assert isinstance(card_manager, HvacFanCardManager)
        assert card_manager.hass == self.hass
        assert card_manager.config_entry == self.config_entry

        # Check feature name
        assert result["feature_name"] == HVAC_FAN_CARD_DOMAIN

    def test_create_hvac_fan_card_feature_with_skip_automation(self):
        """Test creating HVAC fan card feature with skip automation flag."""
        result = create_hvac_fan_card_feature(
            self.hass, self.config_entry, skip_automation_setup=True
        )

        assert isinstance(result, dict)
        assert "card_manager" in result
        assert "feature_name" in result
