"""Tests for ramses_debugger feature const.py module."""

from unittest.mock import MagicMock, patch

import pytest


class TestRamsesDebuggerConst:
    """Tests for ramses_debugger feature constants and load_feature function."""

    def test_domain_constant(self):
        """Test DOMAIN constant is correctly defined."""
        from custom_components.ramses_extras.features.ramses_debugger.const import (
            DOMAIN,
        )

        assert DOMAIN == "ramses_debugger"

    def test_feature_id_constant(self):
        """Test FEATURE_ID constant is correctly defined."""
        from custom_components.ramses_extras.features.ramses_debugger.const import (
            FEATURE_ID,
        )

        assert FEATURE_ID == "ramses_debugger"

    def test_entity_configs_empty(self):
        """Test all entity config dicts are empty."""
        from custom_components.ramses_extras.features.ramses_debugger.const import (
            RAMSES_DEBUGGER_BOOLEAN_CONFIGS,
            RAMSES_DEBUGGER_NUMBER_CONFIGS,
            RAMSES_DEBUGGER_SENSOR_CONFIGS,
            RAMSES_DEBUGGER_SWITCH_CONFIGS,
        )

        # Ramses Debugger doesn't create entities, it's a debugging feature
        assert RAMSES_DEBUGGER_SENSOR_CONFIGS == {}
        assert RAMSES_DEBUGGER_SWITCH_CONFIGS == {}
        assert RAMSES_DEBUGGER_NUMBER_CONFIGS == {}
        assert RAMSES_DEBUGGER_BOOLEAN_CONFIGS == {}

    def test_ramses_debugger_websocket_commands(self):
        """Test RAMSES_DEBUGGER_WEBSOCKET_COMMANDS structure."""
        from custom_components.ramses_extras.features.ramses_debugger.const import (
            RAMSES_DEBUGGER_WEBSOCKET_COMMANDS,
        )

        expected_commands = [
            "traffic_get_stats",
            "traffic_reset_stats",
            "traffic_subscribe_stats",
            "log_list_files",
            "log_get_tail",
            "log_search",
            "packet_log_list_files",
            "packet_log_get_messages",
            "messages_get_messages",
            "cache_get_stats",
            "cache_clear",
            "config_export",
            "config_diagnostics",
            "config_import",
        ]

        assert len(RAMSES_DEBUGGER_WEBSOCKET_COMMANDS) == len(expected_commands)
        for cmd in expected_commands:
            assert cmd in RAMSES_DEBUGGER_WEBSOCKET_COMMANDS
            assert RAMSES_DEBUGGER_WEBSOCKET_COMMANDS[cmd].startswith(
                "ramses_extras/ramses_debugger/"
            )

    def test_ramses_debugger_device_entity_mapping(self):
        """Test RAMSES_DEBUGGER_DEVICE_ENTITY_MAPPING structure."""
        from custom_components.ramses_extras.features.ramses_debugger.const import (
            RAMSES_DEBUGGER_DEVICE_ENTITY_MAPPING,
        )

        assert "HvacVentilator" in RAMSES_DEBUGGER_DEVICE_ENTITY_MAPPING
        mapping = RAMSES_DEBUGGER_DEVICE_ENTITY_MAPPING["HvacVentilator"]

        # All entity lists should be empty since debugger doesn't create entities
        assert mapping["sensor"] == []
        assert mapping["switch"] == []
        assert mapping["number"] == []
        assert mapping["binary_sensor"] == []

    def test_ramses_debugger_card_configs(self):
        """Test RAMSES_DEBUGGER_CARD_CONFIGS structure."""
        from custom_components.ramses_extras.features.ramses_debugger.const import (
            RAMSES_DEBUGGER_CARD_CONFIGS,
        )

        assert len(RAMSES_DEBUGGER_CARD_CONFIGS) == 3

        # Check first card - traffic analyser
        traffic_card = RAMSES_DEBUGGER_CARD_CONFIGS[0]
        assert traffic_card["card_id"] == "ramses-traffic-analyser"
        assert traffic_card["card_name"] == "Ramses Traffic Analyser"
        assert "Spreadsheet-like comms matrix" in traffic_card["description"]
        assert traffic_card["location"] == "ramses_debugger"
        assert traffic_card["preview"] is True
        assert traffic_card["supported_device_types"] == ["HvacVentilator"]
        assert traffic_card["javascript_file"] == "ramses-traffic-analyser.js"

        # Check second card - log explorer
        log_card = RAMSES_DEBUGGER_CARD_CONFIGS[1]
        assert log_card["card_id"] == "ramses-log-explorer"
        assert log_card["card_name"] == "Ramses Log Explorer"
        assert "Filter and extract context" in log_card["description"]

        # Check third card - packet log explorer
        packet_card = RAMSES_DEBUGGER_CARD_CONFIGS[2]
        assert packet_card["card_id"] == "ramses-packet-log-explorer"
        assert packet_card["card_name"] == "Ramses Packet Log Explorer"
        assert "Explore the ramses packet" in packet_card["description"]

    def test_feature_definition_structure(self):
        """Test FEATURE_DEFINITION has all required keys."""
        from custom_components.ramses_extras.features.ramses_debugger.const import (
            FEATURE_DEFINITION,
        )

        assert FEATURE_DEFINITION["feature_id"] == "ramses_debugger"
        assert "sensor_configs" in FEATURE_DEFINITION
        assert "switch_configs" in FEATURE_DEFINITION
        assert "number_configs" in FEATURE_DEFINITION
        assert "boolean_configs" in FEATURE_DEFINITION
        assert "device_entity_mapping" in FEATURE_DEFINITION
        assert "websocket_commands" in FEATURE_DEFINITION
        assert "card_config" in FEATURE_DEFINITION
        assert "required_entities" in FEATURE_DEFINITION

        # Check card_config is set to first card
        assert FEATURE_DEFINITION["card_config"]["card_id"] == "ramses-traffic-analyser"

        # Check required_entities is empty
        assert FEATURE_DEFINITION["required_entities"] == {}

    def test_load_feature_function(self):
        """Test load_feature function registers components correctly."""
        from custom_components.ramses_extras.features.ramses_debugger.const import (
            FEATURE_ID,
            RAMSES_DEBUGGER_BOOLEAN_CONFIGS,
            RAMSES_DEBUGGER_DEVICE_ENTITY_MAPPING,
            RAMSES_DEBUGGER_NUMBER_CONFIGS,
            RAMSES_DEBUGGER_SENSOR_CONFIGS,
            RAMSES_DEBUGGER_SWITCH_CONFIGS,
            RAMSES_DEBUGGER_WEBSOCKET_COMMANDS,
            load_feature,
        )

        mock_registry = MagicMock()
        mock_registry.register_device_mappings = MagicMock()
        mock_registry.register_websocket_commands = MagicMock()
        mock_registry.register_card_config = MagicMock()
        mock_registry.register_feature = MagicMock()

        with (
            patch(
                "custom_components.ramses_extras.extras_registry.extras_registry",
                mock_registry,
            ),
            patch(
                "custom_components.ramses_extras.features.ramses_debugger.ramses_debugger_yaml.load_validator"
            ) as mock_load_validator,
        ):
            load_feature()

            # Check registry calls
            mock_registry.register_device_mappings.assert_called_once_with(
                RAMSES_DEBUGGER_DEVICE_ENTITY_MAPPING
            )
            mock_registry.register_websocket_commands.assert_called_once_with(
                FEATURE_ID, RAMSES_DEBUGGER_WEBSOCKET_COMMANDS
            )
            mock_registry.register_feature.assert_called_once_with(FEATURE_ID)

            # Check card config registration (3 cards)
            assert mock_registry.register_card_config.call_count == 3
            mock_registry.register_card_config.assert_any_call(
                FEATURE_ID, {"card_id": "ramses-traffic-analyser"}
            )
            mock_registry.register_card_config.assert_any_call(
                FEATURE_ID, {"card_id": "ramses-log-explorer"}
            )
            mock_registry.register_card_config.assert_any_call(
                FEATURE_ID, {"card_id": "ramses-packet-log-explorer"}
            )

            # Check validator loading
            mock_load_validator.assert_called_once()

    def test_all_exports(self):
        """Test __all__ contains all public exports."""
        from custom_components.ramses_extras.features.ramses_debugger import const

        expected_exports = [
            "FEATURE_ID",
            "FEATURE_DEFINITION",
            "RAMSES_DEBUGGER_DEVICE_ENTITY_MAPPING",
            "RAMSES_DEBUGGER_WEBSOCKET_COMMANDS",
            "RAMSES_DEBUGGER_CARD_CONFIGS",
            "load_feature",
        ]

        for export in expected_exports:
            assert hasattr(const, export), f"Missing export: {export}"
