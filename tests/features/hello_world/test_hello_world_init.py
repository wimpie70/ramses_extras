"""Tests for Hello World feature in features/hello_world/__init__.py."""

from unittest.mock import MagicMock, patch

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from custom_components.ramses_extras.features.hello_world import (
    create_hello_world_feature,
)
from custom_components.ramses_extras.features.hello_world.const import (
    DOMAIN as HELLO_WORLD_DOMAIN,
)


class TestCreateHelloWorldFeature:
    """Test cases for create_hello_world_feature factory function."""

    def setup_method(self):
        """Set up test fixtures."""
        self.hass = MagicMock(spec=HomeAssistant)
        self.config_entry = MagicMock(spec=ConfigEntry)
        self.hass.async_create_task = MagicMock()
        self.hass.data = {}

    @patch(
        "custom_components.ramses_extras.features.hello_world."
        "create_hello_world_automation"
    )
    @patch(
        "custom_components.ramses_extras.framework.helpers.entity."
        "simple_entity_manager.SimpleEntityManager"
    )
    def test_create_hello_world_feature_basic(
        self, mock_entity_manager, mock_automation
    ):
        """Test creating Hello World feature with basic setup."""
        # Mock the managers
        mock_entity_instance = MagicMock()
        mock_entity_manager.return_value = mock_entity_instance

        mock_automation_instance = MagicMock()
        mock_automation.return_value = mock_automation_instance

        result = create_hello_world_feature(self.hass, self.config_entry)

        # Verify result structure
        assert isinstance(result, dict)
        assert "entities" in result
        assert "automation" in result
        assert "platforms" in result
        assert "feature_name" in result

        # Verify feature name
        assert result["feature_name"] == HELLO_WORLD_DOMAIN

    @patch(
        "custom_components.ramses_extras.features.hello_world."
        "create_hello_world_automation"
    )
    @patch(
        "custom_components.ramses_extras.framework.helpers.entity."
        "simple_entity_manager.SimpleEntityManager"
    )
    def test_create_hello_world_feature_skip_automation(
        self, mock_entity_manager, mock_automation
    ):
        """Test creating Hello World feature with automation setup skipped."""
        # Mock the managers
        mock_entity_instance = MagicMock()
        mock_entity_manager.return_value = mock_entity_instance

        mock_automation_instance = MagicMock()
        mock_automation.return_value = mock_automation_instance

        result = create_hello_world_feature(
            self.hass, self.config_entry, skip_automation_setup=True
        )

        # Verify automation was not started
        self.hass.async_create_task.assert_not_called()
        mock_automation_instance.start.assert_not_called()

        # But automation manager was still created and stored
        assert result["automation"] == mock_automation_instance
        assert (
            self.hass.data["ramses_extras"]["hello_world_automation"]
            == mock_automation_instance
        )

    @patch(
        "custom_components.ramses_extras.features.hello_world."
        "create_hello_world_automation"
    )
    @patch(
        "custom_components.ramses_extras.framework.helpers.entity."
        "simple_entity_manager.SimpleEntityManager"
    )
    def test_create_hello_world_feature_existing_data(
        self, mock_entity_manager, mock_automation
    ):
        """Test creating Hello World feature when HA data already exists."""
        # Pre-populate HA data
        self.hass.data = {"ramses_extras": {"existing_key": "existing_value"}}

        # Mock the managers
        mock_entity_instance = MagicMock()
        mock_entity_manager.return_value = mock_entity_instance

        mock_automation_instance = MagicMock()
        mock_automation.return_value = mock_automation_instance

        create_hello_world_feature(self.hass, self.config_entry)

        # Verify existing data is preserved
        assert self.hass.data["ramses_extras"]["existing_key"] == "existing_value"

    @patch(
        "custom_components.ramses_extras.features.hello_world."
        "create_hello_world_automation"
    )
    @patch(
        "custom_components.ramses_extras.framework.helpers.entity."
        "simple_entity_manager.SimpleEntityManager"
    )
    def test_create_hello_world_feature_platforms(
        self, mock_entity_manager, mock_automation
    ):
        """Test that Hello World feature includes correct platforms."""
        # Mock the managers
        mock_entity_manager.return_value = MagicMock()
        mock_automation.return_value = MagicMock()

        result = create_hello_world_feature(self.hass, self.config_entry)

        # Verify platforms
        platforms = result["platforms"]
        assert isinstance(platforms, dict)
        assert "switch" in platforms
        assert "binary_sensor" in platforms
        assert "sensor" in platforms
        assert "number" in platforms

        # Verify platform functions are callable
        for platform_name, platform_func in platforms.items():
            assert callable(platform_func)
