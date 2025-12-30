"""Tests for extras_registry.py."""

from unittest.mock import MagicMock, patch

import pytest

from custom_components.ramses_extras.extras_registry import RamsesEntityRegistry


@pytest.fixture
def registry():
    """Return a fresh RamsesEntityRegistry instance."""
    return RamsesEntityRegistry()


def test_registry_init(registry):
    """Test registry initialization."""
    assert registry.get_all_sensor_configs() == {}
    assert registry.get_all_switch_configs() == {}
    assert registry.get_all_number_configs() == {}
    assert registry.get_all_boolean_configs() == {}
    assert registry.get_all_device_mappings() == {}
    assert registry.get_loaded_features() == []


def test_register_sensor_configs(registry):
    """Test registering sensor configurations."""
    configs = {"sensor1": {"name": "Sensor 1"}}
    registry.register_sensor_configs(configs)
    assert registry.get_all_sensor_configs() == configs


def test_register_switch_configs(registry):
    """Test registering switch configurations."""
    configs = {"switch1": {"name": "Switch 1"}}
    registry.register_switch_configs(configs)
    assert registry.get_all_switch_configs() == configs


def test_register_number_configs(registry):
    """Test registering number configurations."""
    configs = {"number1": {"name": "Number 1"}}
    registry.register_number_configs(configs)
    assert registry.get_all_number_configs() == configs


def test_register_boolean_configs(registry):
    """Test registering boolean configurations."""
    configs = {"boolean1": {"name": "Boolean 1"}}
    registry.register_boolean_configs(configs)
    assert registry.get_all_boolean_configs() == configs


def test_register_device_mappings(registry):
    """Test registering device mappings and merging."""
    mappings1 = {"32": {"sensor": ["sensor.temp1"]}}
    registry.register_device_mappings(mappings1)
    assert registry.get_all_device_mappings() == mappings1

    mappings2 = {
        "32": {"sensor": ["sensor.temp2"], "switch": ["switch.fan1"]},
        "18": {"sensor": ["sensor.hum1"]},
    }
    registry.register_device_mappings(mappings2)

    expected = {
        "32": {"sensor": ["sensor.temp1", "sensor.temp2"], "switch": ["switch.fan1"]},
        "18": {"sensor": ["sensor.hum1"]},
    }
    assert registry.get_all_device_mappings() == expected


def test_register_card_config(registry):
    """Test registering card configuration."""
    config = {"type": "custom:ramses-card"}
    registry.register_card_config("feature1", config)
    assert registry.get_card_config("feature1") == config
    assert registry.get_all_card_configs() == {"feature1": config}


def test_register_feature(registry):
    """Test marking a feature as registered."""
    registry.register_feature("feature1")
    assert "feature1" in registry.get_loaded_features()


def test_register_websocket_commands(registry):
    """Test registering WebSocket commands."""
    commands = {"get_data": "ramses_extras/get_data"}
    registry.register_websocket_commands("feature1", commands)
    assert registry.get_websocket_commands_for_feature("feature1") == commands
    assert registry.get_all_websocket_commands() == {"feature1": commands}
    assert registry.get_features_with_websocket_commands() == ["feature1"]


def test_clear(registry):
    """Test clearing the registry."""
    registry.register_feature("feature1")
    registry.register_sensor_configs({"s1": {}})
    registry.clear()
    assert registry.get_loaded_features() == []
    assert registry.get_all_sensor_configs() == {}


def test_load_feature_definitions_missing_module(registry):
    """Test loading feature definitions when module is missing."""
    with patch("importlib.import_module", side_effect=ImportError):
        registry.load_feature_definitions("nonexistent", "path")
        assert "nonexistent" not in registry.get_loaded_features()


def test_load_feature_definitions_with_feature_definition_dict(registry):
    """Test loading feature definitions using FEATURE_DEFINITION dict."""
    mock_module = MagicMock()
    websocket_commands = {"cmd1": "type1"}
    mock_module.FEATURE_DEFINITION = {
        "sensor_configs": {"s1": {"name": "S1"}},
        "switch_configs": {"sw1": {"name": "SW1"}},
        "number_configs": {"n1": {"name": "N1"}},
        "boolean_configs": {"b1": {"name": "B1"}},
        "device_entity_mapping": {"32": {"sensor": ["s1"]}},
        "card_config": {"type": "card1"},
        "websocket_commands": websocket_commands,
    }

    with patch("importlib.import_module", return_value=mock_module):
        registry.load_feature_definitions("test_feature", "path")

    assert "test_feature" in registry.get_loaded_features()
    assert "s1" in registry.get_all_sensor_configs()
    assert "sw1" in registry.get_all_switch_configs()
    assert "n1" in registry.get_all_number_configs()
    assert "b1" in registry.get_all_boolean_configs()
    assert registry.get_all_device_mappings()["32"]["sensor"] == ["s1"]
    assert registry.get_card_config("test_feature") == {"type": "card1"}
    assert (
        registry.get_websocket_commands_for_feature("test_feature")
        == websocket_commands
    )


def test_load_feature_definitions_legacy_attributes(registry):
    """Test loading feature definitions using legacy individual attributes."""
    mock_module = MagicMock()
    mock_module.FEATURE_DEFINITION = None
    mock_module.TEST_FEATURE_SENSOR_CONFIGS = {"s1": {"name": "S1"}}
    mock_module.TEST_FEATURE_SWITCH_CONFIGS = {"sw1": {"name": "SW1"}}
    mock_module.TEST_FEATURE_NUMBER_CONFIGS = {"n1": {"name": "N1"}}
    mock_module.TEST_FEATURE_BOOLEAN_CONFIGS = {"b1": {"name": "B1"}}
    mock_module.TEST_FEATURE_DEVICE_ENTITY_MAPPING = {"32": {"sensor": ["s1"]}}
    mock_module.TEST_FEATURE_CARD_CONFIG = {"type": "card1"}
    mock_module.TEST_FEATURE_WEBSOCKET_COMMANDS = {"cmd1": "type1"}

    with patch("importlib.import_module", return_value=mock_module):
        registry.load_feature_definitions("test_feature", "path")

    assert "test_feature" in registry.get_loaded_features()
    assert "s1" in registry.get_all_sensor_configs()
    assert "sw1" in registry.get_all_switch_configs()
    assert "n1" in registry.get_all_number_configs()
    assert "b1" in registry.get_all_boolean_configs()
    assert registry.get_all_device_mappings()["32"]["sensor"] == ["s1"]
    assert registry.get_card_config("test_feature") == {"type": "card1"}
    assert registry.get_websocket_commands_for_feature("test_feature") == {
        "cmd1": "type1"
    }


def test_load_feature_definitions_exception(registry):
    """Test loading feature definitions handles generic exceptions."""
    with patch("importlib.import_module", side_effect=Exception("Generic error")):
        registry.load_feature_definitions("test_feature", "path")
        assert "test_feature" not in registry.get_loaded_features()


def test_clear_all(registry):
    """Test clear_all method."""
    registry.register_feature("f1")
    registry.register_sensor_configs({"s1": {}})
    registry.clear_all()
    assert registry.get_loaded_features() == []
    assert registry.get_all_sensor_configs() == {}
