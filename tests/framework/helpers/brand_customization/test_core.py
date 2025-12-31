"""Tests for Brand Customization Core framework."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.core import HomeAssistant

from custom_components.ramses_extras.framework.helpers.brand_customization.core import (
    BrandCustomizerManager,
    ExtrasBrandCustomizer,
)


class TestExtrasBrandCustomizer:
    """Test cases for ExtrasBrandCustomizer."""

    @pytest.fixture
    def hass(self):
        """Mock Home Assistant instance."""
        return MagicMock(spec=HomeAssistant)

    @pytest.fixture
    def customizer(self, hass):
        """Create brand customizer instance."""
        return ExtrasBrandCustomizer(hass, "orcon")

    @pytest.mark.asyncio
    async def test_customize_device(self, customizer):
        """Test customizing a device."""
        device = MagicMock()
        device.id = "32:123456"
        device.model = "HRV300"

        event_data = {
            "device_id": "32:123456",
            "entity_ids": ["sensor.existing"],
        }

        # Mock internal methods to avoid deep dependency testing
        customizer._add_brand_entities = AsyncMock()
        customizer._configure_brand_behaviors = AsyncMock()
        customizer._set_brand_defaults = AsyncMock()

        result = await customizer.customize_device(device, event_data)

        assert "model_config" in result
        assert result["model_config"]["model_key"] == "HRV300"
        customizer._add_brand_entities.assert_called_once()
        customizer._configure_brand_behaviors.assert_called_once()
        customizer._set_brand_defaults.assert_called_once()

    @pytest.mark.asyncio
    async def test_customize_device_unknown_model(self, customizer):
        """Test customizing a device with unknown model."""
        device = MagicMock()
        device.model = None
        event_data = {"entity_ids": []}

        result = await customizer.customize_device(device, event_data)
        assert result == event_data

    @pytest.mark.asyncio
    async def test_add_brand_entities(self, customizer):
        """Test adding brand entities."""
        device = MagicMock()
        device.id = "32:123456"
        model_info = {
            "model_key": "HRV300",
            "high_end_models": ["HRV300"],
            "special_entities": ["filter_timer"],
        }
        event_data = {"entity_ids": []}

        await customizer._add_brand_entities(device, event_data, model_info)

        entities = event_data["entity_ids"]
        # Should have standard, special, and high-end entities
        assert "orcon_filter_usage_32:123456" in entities
        assert "number.orcon_filter_timer_32:123456" in entities
        assert "sensor.orcon_air_quality_index_32:123456" in entities

    @pytest.mark.asyncio
    async def test_configure_brand_behaviors(self, customizer):
        """Test configuring brand behaviors."""
        device = MagicMock()
        model_info = {"max_fan_speed": 3, "supported_modes": ["auto", "boost"]}
        event_data = {}

        await customizer._configure_brand_behaviors(device, event_data, model_info)

        config = event_data["orcon_config"]
        assert config["fan_speed_levels"] == [1, 2, 3]
        assert "auto" in config["mode_configs"]

    @pytest.mark.asyncio
    async def test_set_brand_defaults(self, customizer):
        """Test setting brand defaults."""
        model_info = {"humidity_range": (30, 70)}
        event_data = {"device_id": "32:123456"}

        await customizer._set_brand_defaults(event_data, model_info)

        assert "orcon_defaults" in event_data
        assert "default_enabled_entities" in event_data
        assert event_data["orcon_defaults"]["target_humidity"] == 50

    def test_get_brand_behavior_config(self, customizer):
        """Test getting behavior config."""
        config = customizer._get_brand_behavior_config({})
        assert config["auto_mode_hysteresis"] == 5

    def test_get_mode_configs(self, customizer):
        """Test getting mode configs."""
        model_info = {"supported_modes": ["auto"]}
        configs = customizer._get_mode_configs(model_info, 3)
        assert "auto" in configs
        assert configs["auto"]["default_fan_speed"] == 2

    def test_get_brand_defaults(self, customizer):
        """Test getting brand defaults."""
        model_info = {"humidity_range": (40, 60)}
        defaults = customizer._get_brand_defaults(model_info)
        assert defaults["target_humidity"] == 50

    def test_get_entity_enablement(self, customizer):
        """Test getting entity enablement."""
        enablement = customizer._get_entity_enablement("123", {})
        assert enablement["orcon_operation_mode"] is True


class TestBrandCustomizerManager:
    """Test cases for BrandCustomizerManager."""

    @pytest.fixture
    def hass(self):
        """Mock Home Assistant instance."""
        return MagicMock(spec=HomeAssistant)

    @pytest.fixture
    def manager(self, hass):
        """Create manager instance."""
        return BrandCustomizerManager(hass)

    def test_register_customizer(self, manager, hass):
        """Test registering customizer."""
        customizer = ExtrasBrandCustomizer(hass, "orcon")
        manager.register_customizer(customizer)

        assert manager.get_customizer("orcon") == customizer
        assert "orcon" in manager.get_registered_brands()

    @pytest.mark.asyncio
    async def test_customize_device_dispatch(self, manager, hass):
        """Test dispatching customization to registered brand."""
        customizer = ExtrasBrandCustomizer(hass, "orcon")
        customizer.customize_device = AsyncMock(return_value={"customized": True})
        manager.register_customizer(customizer)

        device = MagicMock()
        device.model = "Orcon HRV300"
        event_data = {"id": "1"}

        result = await manager.customize_device(device, event_data)
        assert result == {"customized": True}
        customizer.customize_device.assert_called_once()

    @pytest.mark.asyncio
    async def test_customize_device_no_brand(self, manager):
        """Test dispatching when no brand detected."""
        device = MagicMock()
        device.model = "Unknown"
        event_data = {"id": "1"}

        result = await manager.customize_device(device, event_data)
        assert result == event_data

    @pytest.mark.asyncio
    async def test_customize_device_no_customizer(self, manager):
        """Test dispatching when no customizer registered for brand."""
        device = MagicMock()
        device.model = "Orcon HRV"
        event_data = {"id": "1"}

        result = await manager.customize_device(device, event_data)
        assert result == event_data
