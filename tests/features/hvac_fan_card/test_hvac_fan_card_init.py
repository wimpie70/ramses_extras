"""Tests for HVAC Fan Card feature in features/hvac_fan_card/__init__.py."""

from unittest.mock import MagicMock

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

        # The skip_automation_setup parameter is included for consistency
        # but doesn't affect this feature since it doesn't have automation
