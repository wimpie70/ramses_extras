"""Tests for Hello World feature configuration."""

from unittest.mock import MagicMock

import pytest
import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from custom_components.ramses_extras.features.hello_world.config import (
    FEATURE_CONFIG_SCHEMA,
    OPTIONS_SCHEMA,
    HelloWorldConfig,
    create_hello_world_config,
)
from custom_components.ramses_extras.features.hello_world.const import DEFAULT_CONFIG


@pytest.fixture
def hass():
    """Mock Home Assistant."""
    return MagicMock(spec=HomeAssistant)


@pytest.fixture
def config_entry():
    """Mock Config Entry."""
    entry = MagicMock(spec=ConfigEntry)
    entry.data = {}
    entry.options = {}
    return entry


def test_hello_world_config_init(hass, config_entry):
    """Test HelloWorldConfig initialization."""
    config = HelloWorldConfig(hass, config_entry)
    assert config.feature_id == "hello_world"
    assert config._default_config == DEFAULT_CONFIG


def test_validate_config_valid(hass, config_entry):
    """Test validate_config with valid configuration."""
    config = HelloWorldConfig(hass, config_entry)
    config._config = DEFAULT_CONFIG.copy()
    assert config.validate_config() is True


def test_validate_config_invalid(hass, config_entry):
    """Test validate_config with invalid configuration."""
    config = HelloWorldConfig(hass, config_entry)
    config._config = {"enabled": "not_a_boolean"}
    # voluptuous will fail to validate "not_a_boolean" as boolean
    assert config.validate_config() is False


def test_get_config_schema(hass, config_entry):
    """Test get_config_schema returns expected structure."""
    config = HelloWorldConfig(hass, config_entry)
    schema = config.get_config_schema()
    assert "properties" in schema
    assert "auto_discovery" in schema["properties"]


def test_is_auto_discovery_enabled(hass, config_entry):
    """Test is_auto_discovery_enabled helper."""
    config = HelloWorldConfig(hass, config_entry)

    config._config = {"auto_discovery": True}
    assert config.is_auto_discovery_enabled() is True

    config._config = {"auto_discovery": False}
    assert config.is_auto_discovery_enabled() is False


def test_create_hello_world_config(hass, config_entry):
    """Test factory function."""
    config = create_hello_world_config(hass, config_entry)
    assert isinstance(config, HelloWorldConfig)


def test_schemas_defined():
    """Test that schemas are defined."""
    assert FEATURE_CONFIG_SCHEMA is not None
    assert OPTIONS_SCHEMA is not None
