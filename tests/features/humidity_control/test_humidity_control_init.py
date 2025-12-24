"""Tests for Humidity Control feature in features/humidity_control/__init__.py."""

from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from custom_components.ramses_extras.features.humidity_control import (
    create_humidity_control_feature,
)
from custom_components.ramses_extras.features.humidity_control.const import (
    HUMIDITY_CONTROL_CONST,
)


class TestCreateHumidityControlFeature:
    """Test cases for create_humidity_control_feature factory function."""

    def setup_method(self):
        """Set up test fixtures."""
        self.hass = MagicMock(spec=HomeAssistant)
        self.config_entry = MagicMock(spec=ConfigEntry)
        self.hass.async_create_task = MagicMock()
        self.hass.data = {}

    @patch(
        "custom_components.ramses_extras.features.humidity_control."
        "HumidityAutomationManager"
    )
    @patch("custom_components.ramses_extras.features.humidity_control.HumidityEntities")
    @patch("custom_components.ramses_extras.features.humidity_control.HumidityServices")
    @patch("custom_components.ramses_extras.features.humidity_control.HumidityConfig")
    @patch(
        "custom_components.ramses_extras.features.humidity_control."
        "EnhancedHumidityControl"
    )
    async def test_create_humidity_control_feature_basic(
        self, mock_enhanced, mock_config, mock_services, mock_entities, mock_automation
    ):
        """Test creating Humidity Control feature with basic setup."""
        # Mock the managers
        mock_automation_instance = MagicMock()
        mock_automation_instance.start = AsyncMock()
        mock_automation.return_value = mock_automation_instance

        mock_entities_instance = MagicMock()
        mock_entities.return_value = mock_entities_instance

        mock_services_instance = MagicMock()
        mock_services.return_value = mock_services_instance

        mock_config_instance = MagicMock()
        mock_config.return_value = mock_config_instance

        mock_enhanced_instance = MagicMock()
        mock_enhanced_instance.async_setup = AsyncMock()
        mock_enhanced.return_value = mock_enhanced_instance

        result = await create_humidity_control_feature(self.hass, self.config_entry)

        # Verify result structure
        assert isinstance(result, dict)
        assert "entities" in result
        assert "automation" in result
        assert "services" in result
        assert "config" in result
        assert "enhanced" in result
        assert "platforms" in result

        # Verify automation was started
        # async_create_task is called during state changes, not setup
        # self.hass.async_create_task.assert_called_once()
        mock_enhanced_instance.async_setup.assert_called_once()

    @patch(
        "custom_components.ramses_extras.features.humidity_control."
        "HumidityAutomationManager"
    )
    @patch("custom_components.ramses_extras.features.humidity_control.HumidityEntities")
    @patch("custom_components.ramses_extras.features.humidity_control.HumidityServices")
    @patch("custom_components.ramses_extras.features.humidity_control.HumidityConfig")
    @patch(
        "custom_components.ramses_extras.features.humidity_control."
        "EnhancedHumidityControl"
    )
    async def test_create_humidity_control_feature_skip_automation(
        self, mock_enhanced, mock_config, mock_services, mock_entities, mock_automation
    ):
        """Test creating Humidity Control feature with automation setup skipped."""
        # Mock the managers
        mock_automation_instance = MagicMock()
        mock_automation.return_value = mock_automation_instance

        mock_entities_instance = MagicMock()
        mock_entities.return_value = mock_entities_instance

        mock_services_instance = MagicMock()
        mock_services.return_value = mock_services_instance

        mock_config_instance = MagicMock()
        mock_config.return_value = mock_config_instance

        mock_enhanced_instance = MagicMock()
        mock_enhanced_instance.automation = mock_automation_instance
        mock_enhanced.return_value = mock_enhanced_instance

        result = await create_humidity_control_feature(
            self.hass, self.config_entry, skip_automation_setup=True
        )

        # Verify automation setup was skipped
        mock_enhanced_instance.async_setup.assert_not_called()
        self.hass.async_create_task.assert_not_called()

        # But automation manager was still created
        assert result["automation"] == mock_automation_instance

    @patch(
        "custom_components.ramses_extras.features.humidity_control."
        "HumidityAutomationManager"
    )
    @patch("custom_components.ramses_extras.features.humidity_control.HumidityEntities")
    @patch("custom_components.ramses_extras.features.humidity_control.HumidityServices")
    @patch("custom_components.ramses_extras.features.humidity_control.HumidityConfig")
    @patch(
        "custom_components.ramses_extras.features.humidity_control."
        "EnhancedHumidityControl"
    )
    async def test_create_humidity_control_feature_platforms(
        self, mock_enhanced, mock_config, mock_services, mock_entities, mock_automation
    ):
        """Test that Humidity Control feature includes correct platforms."""
        # Mock the managers
        mock_automation_instance = MagicMock()
        mock_automation_instance.start = AsyncMock()
        mock_automation.return_value = mock_automation_instance

        mock_entities.return_value = MagicMock()
        mock_services.return_value = MagicMock()
        mock_config.return_value = MagicMock()

        mock_enhanced_instance = MagicMock()
        mock_enhanced_instance.async_setup = AsyncMock()
        mock_enhanced.return_value = mock_enhanced_instance

        result = await create_humidity_control_feature(self.hass, self.config_entry)

        # Verify platforms
        platforms = result["platforms"]
        assert isinstance(platforms, dict)
        assert "sensor" in platforms
        assert "binary_sensor" in platforms
        assert "switch" in platforms
        assert "number" in platforms

        # Verify platform functions are callable
        for platform_name, platform_config in platforms.items():
            assert "async_setup_entry" in platform_config
            expected_create = "create_" + platform_name
            assert (
                expected_create in platform_config
                or expected_create.replace("_", "") in platform_config
            )
            assert callable(platform_config["async_setup_entry"])
