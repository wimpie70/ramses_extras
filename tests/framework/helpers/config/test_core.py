"""Tests for ExtrasConfigManager in framework/helpers/config/core.py."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from custom_components.ramses_extras.framework.helpers.config.core import (
    ExtrasConfigManager,
    create_config_manager,
)


class TestExtrasConfigManager:
    """Test cases for ExtrasConfigManager."""

    def setup_method(self):
        """Set up test fixtures."""
        self.hass = MagicMock(spec=HomeAssistant)
        self.config_entry = MagicMock(spec=ConfigEntry)
        self.config_entry.options = {}
        self.config_entry.data = {}
        self.feature_id = "test_feature"
        self.default_config = {
            "enabled": False,
            "automation_enabled": False,
            "min_value": 0,
            "max_value": 100,
        }

    def test_init(self):
        """Test initialization of ExtrasConfigManager."""
        manager = ExtrasConfigManager(
            self.hass, self.config_entry, self.feature_id, self.default_config
        )

        assert manager.hass == self.hass
        assert manager.config_entry == self.config_entry
        assert manager.feature_id == self.feature_id
        assert manager._default_config == self.default_config
        assert manager._config == {}

    @pytest.mark.asyncio
    async def test_async_load_with_defaults_only(self):
        """Test loading configuration with only defaults."""
        manager = ExtrasConfigManager(
            self.hass, self.config_entry, self.feature_id, self.default_config
        )

        await manager.async_load()

        assert manager._config == self.default_config

    @pytest.mark.asyncio
    async def test_async_load_with_config_entry_options(self):
        """Test loading configuration with config entry options."""
        self.config_entry.options = {"enabled": True, "custom_setting": "value"}
        manager = ExtrasConfigManager(
            self.hass, self.config_entry, self.feature_id, self.default_config
        )

        await manager.async_load()

        expected_config = self.default_config.copy()
        expected_config.update(self.config_entry.options)
        assert manager._config == expected_config

    @pytest.mark.asyncio
    async def test_async_load_with_config_entry_data(self):
        """Test loading configuration with config entry data."""
        self.config_entry.data = {"enabled": True, "data_setting": "value"}
        manager = ExtrasConfigManager(
            self.hass, self.config_entry, self.feature_id, self.default_config
        )

        await manager.async_load()

        expected_config = self.default_config.copy()
        expected_config.update(self.config_entry.data)
        assert manager._config == expected_config

    @pytest.mark.asyncio
    async def test_async_load_options_override_data(self):
        """Test that options override data in config loading."""
        self.config_entry.data = {"enabled": False, "setting": "data"}
        self.config_entry.options = {"enabled": True, "setting": "options"}
        manager = ExtrasConfigManager(
            self.hass, self.config_entry, self.feature_id, self.default_config
        )

        await manager.async_load()

        # Options should override data
        assert manager._config["enabled"] is True
        assert manager._config["setting"] == "options"

    @pytest.mark.asyncio
    async def test_async_save_valid_config(self):
        """Test saving valid configuration."""
        manager = ExtrasConfigManager(
            self.hass, self.config_entry, self.feature_id, self.default_config
        )
        await manager.async_load()
        manager._config["enabled"] = True

        result = await manager.async_save()

        assert result is True

    @pytest.mark.asyncio
    async def test_async_save_invalid_config(self):
        """Test saving invalid configuration."""
        manager = ExtrasConfigManager(
            self.hass, self.config_entry, self.feature_id, self.default_config
        )
        await manager.async_load()
        manager._config["enabled"] = "not_boolean"  # Invalid

        result = await manager.async_save()

        assert result is False

    def test_validate_config_valid(self):
        """Test validation of valid configuration."""
        manager = ExtrasConfigManager(
            self.hass, self.config_entry, self.feature_id, self.default_config
        )
        manager._config = {
            "enabled": True,
            "min_value": 10,
            "max_value": 20,
        }

        result = manager.validate_config()

        assert result is True

    def test_validate_config_invalid_enabled_type(self):
        """Test validation of invalid enabled type."""
        manager = ExtrasConfigManager(
            self.hass, self.config_entry, self.feature_id, self.default_config
        )
        manager._config = {"enabled": "not_boolean"}

        result = manager.validate_config()

        assert result is False

    def test_validate_config_invalid_min_max_values(self):
        """Test validation of invalid min/max values."""
        manager = ExtrasConfigManager(
            self.hass, self.config_entry, self.feature_id, self.default_config
        )
        manager._config = {
            "min_value": 30,
            "max_value": 20,  # min > max
        }

        result = manager.validate_config()

        assert result is False

    def test_validate_config_invalid_min_max_types(self):
        """Test validation of invalid min/max types."""
        manager = ExtrasConfigManager(
            self.hass, self.config_entry, self.feature_id, self.default_config
        )
        manager._config = {
            "min_value": "not_number",
            "max_value": 20,
        }

        result = manager.validate_config()

        assert result is False

    def test_get_method(self):
        """Test get method."""
        manager = ExtrasConfigManager(
            self.hass, self.config_entry, self.feature_id, self.default_config
        )
        manager._config = {"test_key": "test_value"}

        assert manager.get("test_key") == "test_value"
        assert manager.get("missing_key", "default") == "default"
        assert manager.get("missing_key") is None

    def test_set_method(self):
        """Test set method."""
        manager = ExtrasConfigManager(
            self.hass, self.config_entry, self.feature_id, self.default_config
        )
        manager._config = {}

        manager.set("test_key", "test_value")

        assert manager._config["test_key"] == "test_value"

    def test_get_all_method(self):
        """Test get_all method."""
        manager = ExtrasConfigManager(
            self.hass, self.config_entry, self.feature_id, self.default_config
        )
        test_config = {"key1": "value1", "key2": "value2"}
        manager._config = test_config

        result = manager.get_all()

        assert result == test_config
        assert result is not manager._config  # Should return a copy

    def test_get_config_schema_dict(self):
        manager = ExtrasConfigManager(
            self.hass, self.config_entry, self.feature_id, self.default_config
        )
        schema = manager.get_config_schema_dict()
        assert schema["type"] == "object"
        assert "enabled" in schema["properties"]

    def test_update_method(self):
        """Test update method."""
        manager = ExtrasConfigManager(
            self.hass, self.config_entry, self.feature_id, self.default_config
        )
        manager._config = {"existing": "old_value"}

        updates = {"existing": "new_value", "new_key": "new_value"}
        manager.update(updates)

        assert manager._config["existing"] == "new_value"
        assert manager._config["new_key"] == "new_value"

    def test_is_enabled_method(self):
        """Test is_enabled method."""
        manager = ExtrasConfigManager(
            self.hass, self.config_entry, self.feature_id, self.default_config
        )

        manager._config = {"enabled": True}
        assert manager.is_enabled() is True

        manager._config = {"enabled": False}
        assert manager.is_enabled() is False

        manager._config = {}  # No enabled key
        assert manager.is_enabled() is False

    def test_is_automation_enabled_method(self):
        """Test is_automation_enabled method."""
        manager = ExtrasConfigManager(
            self.hass, self.config_entry, self.feature_id, self.default_config
        )

        manager._config = {"enabled": True, "automation_enabled": True}
        assert manager.is_automation_enabled() is True

        manager._config = {"enabled": False, "automation_enabled": True}
        assert manager.is_automation_enabled() is False

        manager._config = {"enabled": True, "automation_enabled": False}
        assert manager.is_automation_enabled() is False

    def test_reset_to_defaults_method(self):
        """Test reset_to_defaults method."""
        manager = ExtrasConfigManager(
            self.hass, self.config_entry, self.feature_id, self.default_config
        )
        manager._config = {"modified": "value"}

        manager.reset_to_defaults()

        assert manager._config == self.default_config

    def test_get_config_schema_method(self):
        """Test get_config_schema method."""
        manager = ExtrasConfigManager(
            self.hass, self.config_entry, self.feature_id, self.default_config
        )

        schema = manager.get_config_schema()

        expected_schema = {
            "type": "object",
            "properties": {
                "enabled": {
                    "type": "boolean",
                    "title": f"Enable {self.feature_id.title().replace('_', ' ')}",
                    "description": f"Enable or disable the {self.feature_id} feature",
                },
            },
        }

        assert schema == expected_schema

    def test_get_numeric_validation_valid(self):
        """Test numeric validation with valid values."""
        manager = ExtrasConfigManager(
            self.hass, self.config_entry, self.feature_id, self.default_config
        )
        manager._config = {"test_value": 50}

        result = manager.get_numeric_validation("test_value", 0, 100)

        assert result is True

    def test_get_numeric_validation_invalid_type(self):
        """Test numeric validation with invalid type."""
        manager = ExtrasConfigManager(
            self.hass, self.config_entry, self.feature_id, self.default_config
        )
        manager._config = {"test_value": "not_number"}

        result = manager.get_numeric_validation("test_value", 0, 100)

        assert result is False

    def test_get_numeric_validation_out_of_range(self):
        """Test numeric validation with out of range value."""
        manager = ExtrasConfigManager(
            self.hass, self.config_entry, self.feature_id, self.default_config
        )
        manager._config = {"test_value": 150}

        result = manager.get_numeric_validation("test_value", 0, 100)

        assert result is False

    def test_get_boolean_validation_valid(self):
        """Test boolean validation with valid value."""
        manager = ExtrasConfigManager(
            self.hass, self.config_entry, self.feature_id, self.default_config
        )
        manager._config = {"test_value": True}

        result = manager.get_boolean_validation("test_value")

        assert result is True

    def test_get_boolean_validation_invalid_type(self):
        """Test boolean validation with invalid type."""
        manager = ExtrasConfigManager(
            self.hass, self.config_entry, self.feature_id, self.default_config
        )
        manager._config = {"test_value": "not_boolean"}

        result = manager.get_boolean_validation("test_value")

        assert result is False

    def test_get_string_validation_valid(self):
        """Test string validation with valid value."""
        manager = ExtrasConfigManager(
            self.hass, self.config_entry, self.feature_id, self.default_config
        )
        manager._config = {"test_value": "valid_choice"}

        result = manager.get_string_validation("test_value", ["valid_choice", "other"])

        assert result is True

    def test_get_string_validation_invalid_type(self):
        """Test string validation with invalid type."""
        manager = ExtrasConfigManager(
            self.hass, self.config_entry, self.feature_id, self.default_config
        )
        manager._config = {"test_value": 123}

        result = manager.get_string_validation("test_value")

        assert result is False

    def test_get_string_validation_invalid_choice(self):
        """Test string validation with invalid choice."""
        manager = ExtrasConfigManager(
            self.hass, self.config_entry, self.feature_id, self.default_config
        )
        manager._config = {"test_value": "invalid_choice"}

        result = manager.get_string_validation("test_value", ["valid_choice", "other"])

        assert result is False


class TestCreateConfigManager:
    """Test cases for create_config_manager function."""

    def setup_method(self):
        """Set up test fixtures."""
        self.hass = MagicMock(spec=HomeAssistant)
        self.config_entry = MagicMock(spec=ConfigEntry)
        self.config_entry.options = {}
        self.config_entry.data = {}
        self.feature_id = "test_feature"
        self.default_config = {"enabled": False}

    def test_create_config_manager(self):
        """Test create_config_manager function."""
        manager = create_config_manager(
            self.hass, self.config_entry, self.feature_id, self.default_config
        )

        assert isinstance(manager, ExtrasConfigManager)
        assert manager.hass == self.hass
        assert manager.config_entry == self.config_entry
        assert manager.feature_id == self.feature_id
        assert manager._default_config == self.default_config
