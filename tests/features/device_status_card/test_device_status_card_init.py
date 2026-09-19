"""Tests for device_status_card feature initialization."""

from unittest.mock import MagicMock

import pytest
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from custom_components.ramses_extras.features.device_status_card import (
    DeviceStatusCardManager,
    create_device_status_card_feature,
)
from custom_components.ramses_extras.features.device_status_card.const import (
    DOMAIN as DEVICE_STATUS_CARD_DOMAIN,
)


class TestCreateDeviceStatusCardFeature:
    """Test the create_device_status_card_feature function."""

    @pytest.fixture
    def hass(self):
        """Mock HomeAssistant instance."""
        mock_hass = MagicMock(spec=HomeAssistant)
        mock_hass.data = {}
        mock_hass.bus = MagicMock()
        mock_hass.bus.async_listen = MagicMock()
        return mock_hass

    @pytest.fixture
    def config_entry(self):
        """Mock ConfigEntry instance."""
        entry = MagicMock(spec=ConfigEntry)
        entry.options = {}
        entry.async_on_unload = MagicMock()
        return entry

    def test_create_feature_basic_initialization(self, hass, config_entry):
        """Test basic feature creation with default settings."""
        result = create_device_status_card_feature(hass, config_entry)

        assert result["feature_name"] == DEVICE_STATUS_CARD_DOMAIN
        assert isinstance(result["card_manager"], DeviceStatusCardManager)
        assert result["card_manager"].feature_name == DEVICE_STATUS_CARD_DOMAIN

    def test_card_configurations_returned(self, hass, config_entry):
        """The card manager exposes the feature's card configs."""
        manager = DeviceStatusCardManager(hass, config_entry)
        configs = manager._get_card_configurations()

        assert len(configs) == 1
        assert configs[0]["card_id"] == "device-status-card"
        assert configs[0]["javascript_file"] == "device-status-card.js"
