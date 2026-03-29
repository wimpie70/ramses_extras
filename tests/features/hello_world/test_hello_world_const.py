"""Tests for hello_world feature const.py module."""

from unittest.mock import MagicMock, patch

import pytest


class TestHelloWorldConst:
    """Tests for hello_world feature constants and load_feature function."""

    def test_domain_constant(self):
        """Test DOMAIN constant is correctly defined."""
        from custom_components.ramses_extras.features.hello_world.const import DOMAIN

        assert DOMAIN == "hello_world"

    def test_feature_id_constant(self):
        """Test FEATURE_ID constant is correctly defined."""
        from custom_components.ramses_extras.features.hello_world.const import (
            FEATURE_ID,
        )

        assert FEATURE_ID == "hello_world"

    def test_feature_name_and_description(self):
        """Test feature name and description constants."""
        from custom_components.ramses_extras.features.hello_world.const import (
            FEATURE_DESCRIPTION,
            FEATURE_NAME,
        )

        assert FEATURE_NAME == "Hello World"
        assert "Template feature" in FEATURE_DESCRIPTION
        assert "Ramses Extras architecture" in FEATURE_DESCRIPTION

    def test_hello_world_switch_configs(self):
        """Test HELLO_WORLD_SWITCH_CONFIGS structure."""
        from custom_components.ramses_extras.features.hello_world.const import (
            HELLO_WORLD_SWITCH_CONFIGS,
        )

        assert "hello_world_switch" in HELLO_WORLD_SWITCH_CONFIGS
        assert "hello_world_optional_switch" in HELLO_WORLD_SWITCH_CONFIGS

        # Check required switch
        required_switch = HELLO_WORLD_SWITCH_CONFIGS["hello_world_switch"]
        assert required_switch["name_template"] == "Hello World Switch {device_id}"
        assert required_switch["entity_template"] == "hello_world_switch_{device_id}"
        assert required_switch["icon"] == "mdi:lightbulb"
        assert "HvacVentilator" in required_switch["device_types"]
        assert "optional" not in required_switch  # Not optional

        # Check optional switch
        optional_switch = HELLO_WORLD_SWITCH_CONFIGS["hello_world_optional_switch"]
        assert (
            optional_switch["name_template"]
            == "Hello World Optional Switch {device_id}"
        )
        assert optional_switch["icon"] == "mdi:toggle-switch-variant"
        assert optional_switch["optional"] is True

    def test_hello_world_binary_sensor_configs(self):
        """Test HELLO_WORLD_BINARY_SENSOR_CONFIGS structure."""
        from custom_components.ramses_extras.features.hello_world.const import (
            HELLO_WORLD_BINARY_SENSOR_CONFIGS,
        )

        assert "hello_world_status" in HELLO_WORLD_BINARY_SENSOR_CONFIGS
        config = HELLO_WORLD_BINARY_SENSOR_CONFIGS["hello_world_status"]

        assert config["name_template"] == "Hello World Status {device_id}"
        assert config["entity_template"] == "hello_world_status_{device_id}"
        assert config["device_class"] == "connectivity"
        assert "HvacVentilator" in config["device_types"]

    def test_hello_world_sensor_configs_empty(self):
        """Test HELLO_WORLD_SENSOR_CONFIGS is empty."""
        from custom_components.ramses_extras.features.hello_world.const import (
            HELLO_WORLD_SENSOR_CONFIGS,
        )

        assert HELLO_WORLD_SENSOR_CONFIGS == {}

    def test_hello_world_device_entity_mapping(self):
        """Test HELLO_WORLD_DEVICE_ENTITY_MAPPING structure."""
        from custom_components.ramses_extras.features.hello_world.const import (
            HELLO_WORLD_DEVICE_ENTITY_MAPPING,
        )

        expected_devices = ["HvacVentilator", "HgiGateway", "HgiController"]

        for device in expected_devices:
            assert device in HELLO_WORLD_DEVICE_ENTITY_MAPPING
            mapping = HELLO_WORLD_DEVICE_ENTITY_MAPPING[device]

            assert mapping["switch"] == ["hello_world_switch"]
            assert mapping["binary_sensor"] == ["hello_world_status"]
            assert mapping["sensor"] == []  # Empty placeholder

    def test_hello_world_websocket_commands(self):
        """Test HELLO_WORLD_WEBSOCKET_COMMANDS structure."""
        from custom_components.ramses_extras.features.hello_world.const import (
            HELLO_WORLD_WEBSOCKET_COMMANDS,
        )

        expected_commands = ["toggle_switch", "get_switch_state"]

        for cmd in expected_commands:
            assert cmd in HELLO_WORLD_WEBSOCKET_COMMANDS
            assert HELLO_WORLD_WEBSOCKET_COMMANDS[cmd].startswith(
                "ramses_extras/hello_world/"
            )

    def test_default_config(self):
        """Test DEFAULT_CONFIG structure."""
        from custom_components.ramses_extras.features.hello_world.const import (
            DEFAULT_CONFIG,
        )

        assert DEFAULT_CONFIG["enabled"] is True
        assert DEFAULT_CONFIG["auto_discovery"] is True

    def test_hello_world_card_configs(self):
        """Test HELLO_WORLD_CARD_CONFIGS structure."""
        from custom_components.ramses_extras.features.hello_world.const import (
            HELLO_WORLD_CARD_CONFIGS,
        )

        assert len(HELLO_WORLD_CARD_CONFIGS) == 1
        card_config = HELLO_WORLD_CARD_CONFIGS[0]

        assert card_config["card_id"] == "hello-world"
        assert card_config["card_name"] == "Hello World Card"
        assert card_config["location"] == "hello_world"
        assert card_config["preview"] is True
        assert "documentation_url" in card_config
        assert "javascript_file" in card_config
        assert set(card_config["supported_device_types"]) == {
            "HvacVentilator",
            "HgiGateway",
            "HgiController",
        }

    def test_feature_definition_structure(self):
        """Test FEATURE_DEFINITION has all required keys."""
        from custom_components.ramses_extras.features.hello_world.const import (
            FEATURE_DEFINITION,
        )

        assert FEATURE_DEFINITION["feature_id"] == "hello_world"
        assert "sensor_configs" in FEATURE_DEFINITION
        assert "switch_configs" in FEATURE_DEFINITION
        assert "boolean_configs" in FEATURE_DEFINITION
        assert "device_entity_mapping" in FEATURE_DEFINITION
        assert "websocket_commands" in FEATURE_DEFINITION
        assert "entity_mappings" in FEATURE_DEFINITION
        assert "card_config" in FEATURE_DEFINITION

        # Check card_config is set
        assert FEATURE_DEFINITION["card_config"]["card_id"] == "hello-world"

    def test_entity_mappings(self):
        """Test entity mappings contain expected entities."""
        from custom_components.ramses_extras.features.hello_world.const import (
            FEATURE_DEFINITION,
        )

        mappings = FEATURE_DEFINITION["entity_mappings"]

        assert mappings["switch_state"] == "switch.hello_world_switch_{device_id}"
        assert (
            mappings["sensor_state"] == "binary_sensor.hello_world_status_{device_id}"
        )

    def test_load_feature_function(self):
        """Test load_feature function registers components correctly."""
        from custom_components.ramses_extras.features.hello_world.const import (
            HELLO_WORLD_BINARY_SENSOR_CONFIGS,
            HELLO_WORLD_DEVICE_ENTITY_MAPPING,
            HELLO_WORLD_SENSOR_CONFIGS,
            HELLO_WORLD_SWITCH_CONFIGS,
            HELLO_WORLD_WEBSOCKET_COMMANDS,
            load_feature,
        )

        mock_registry = MagicMock()
        mock_registry.register_switch_configs = MagicMock()
        mock_registry.register_boolean_configs = MagicMock()
        mock_registry.register_device_mappings = MagicMock()
        mock_registry.register_websocket_commands = MagicMock()
        mock_registry.register_feature = MagicMock()

        with (
            patch(
                "custom_components.ramses_extras.extras_registry.extras_registry",
                mock_registry,
            ),
            patch(
                "custom_components.ramses_extras.features.hello_world.hello_world_yaml.load_validator"
            ) as mock_load_validator,
        ):
            load_feature()

            # Check registry calls
            mock_registry.register_switch_configs.assert_called_once_with(
                HELLO_WORLD_SWITCH_CONFIGS
            )
            mock_registry.register_boolean_configs.assert_called_once_with(
                HELLO_WORLD_BINARY_SENSOR_CONFIGS
            )
            mock_registry.register_device_mappings.assert_called_once_with(
                HELLO_WORLD_DEVICE_ENTITY_MAPPING
            )
            mock_registry.register_websocket_commands.assert_called_once_with(
                "hello_world", HELLO_WORLD_WEBSOCKET_COMMANDS
            )
            mock_registry.register_feature.assert_called_once_with("hello_world")

            # Check validator loading
            mock_load_validator.assert_called_once()

    def test_all_exports(self):
        """Test __all__ contains all public exports."""
        from custom_components.ramses_extras.features.hello_world import const

        expected_exports = [
            "DOMAIN",
            "FEATURE_ID",
            "FEATURE_DEFINITION",
            "FEATURE_NAME",
            "FEATURE_DESCRIPTION",
            "HELLO_WORLD_SWITCH_CONFIGS",
            "HELLO_WORLD_BINARY_SENSOR_CONFIGS",
            "HELLO_WORLD_SENSOR_CONFIGS",
            "HELLO_WORLD_DEVICE_ENTITY_MAPPING",
            "HELLO_WORLD_WEBSOCKET_COMMANDS",
            "DEFAULT_CONFIG",
            "load_feature",
        ]

        for export in expected_exports:
            assert hasattr(const, export), f"Missing export: {export}"
