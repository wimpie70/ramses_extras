"""Tests for hvac_fan_card feature const.py module."""

from unittest.mock import MagicMock, patch

import pytest


class TestHvacFanCardConst:
    """Tests for hvac_fan_card feature constants and load_feature function."""

    def test_domain_constant(self):
        """Test DOMAIN constant is correctly defined."""
        from custom_components.ramses_extras.features.hvac_fan_card.const import DOMAIN

        assert DOMAIN == "hvac_fan_card"

    def test_feature_id_constant(self):
        """Test FEATURE_ID constant is correctly defined."""
        from custom_components.ramses_extras.features.hvac_fan_card.const import (
            FEATURE_ID,
        )

        assert FEATURE_ID == "hvac_fan_card"

    def test_entity_configs_empty(self):
        """Test all entity config dicts are empty."""
        from custom_components.ramses_extras.features.hvac_fan_card.const import (
            HVAC_FAN_CARD_BOOLEAN_CONFIGS,
            HVAC_FAN_CARD_NUMBER_CONFIGS,
            HVAC_FAN_CARD_SENSOR_CONFIGS,
            HVAC_FAN_CARD_SWITCH_CONFIGS,
        )

        # HVAC Fan Card doesn't create entities, it uses existing ones
        assert HVAC_FAN_CARD_SENSOR_CONFIGS == {}
        assert HVAC_FAN_CARD_SWITCH_CONFIGS == {}
        assert HVAC_FAN_CARD_NUMBER_CONFIGS == {}
        assert HVAC_FAN_CARD_BOOLEAN_CONFIGS == {}

    def test_websocket_commands_empty(self):
        """Test HVAC_FAN_CARD_WEBSOCKET_COMMANDS is empty."""
        from custom_components.ramses_extras.features.hvac_fan_card.const import (
            HVAC_FAN_CARD_WEBSOCKET_COMMANDS,
        )

        assert HVAC_FAN_CARD_WEBSOCKET_COMMANDS == {}

    def test_device_entity_mapping_structure(self):
        """Test HVAC_FAN_CARD_DEVICE_ENTITY_MAPPING structure."""
        from custom_components.ramses_extras.features.hvac_fan_card.const import (
            HVAC_FAN_CARD_DEVICE_ENTITY_MAPPING,
        )

        assert "HvacVentilator" in HVAC_FAN_CARD_DEVICE_ENTITY_MAPPING
        mapping = HVAC_FAN_CARD_DEVICE_ENTITY_MAPPING["HvacVentilator"]

        # All entity lists should be empty since card doesn't create entities
        assert mapping["sensor"] == []
        assert mapping["switch"] == []
        assert mapping["number"] == []
        assert mapping["binary_sensor"] == []

    def test_hvac_fan_card_configs(self):
        """Test HVAC_FAN_CARD_CONFIGS structure."""
        from custom_components.ramses_extras.features.hvac_fan_card.const import (
            HVAC_FAN_CARD_CONFIGS,
        )

        assert len(HVAC_FAN_CARD_CONFIGS) == 1
        card_config = HVAC_FAN_CARD_CONFIGS[0]

        assert card_config["card_id"] == "hvac-fan-card"
        assert card_config["card_name"] == "HVAC Fan Card"
        assert card_config["location"] == "hvac_fan_card"
        assert card_config["preview"] is True
        assert "documentation_url" in card_config
        assert card_config["supported_device_types"] == ["HvacVentilator"]
        assert card_config["javascript_file"] == "hvac-fan-card.js"

    def test_feature_definition_structure(self):
        """Test FEATURE_DEFINITION has all required keys."""
        from custom_components.ramses_extras.features.hvac_fan_card.const import (
            FEATURE_DEFINITION,
        )

        assert FEATURE_DEFINITION["feature_id"] == "hvac_fan_card"
        assert "sensor_configs" in FEATURE_DEFINITION
        assert "switch_configs" in FEATURE_DEFINITION
        assert "number_configs" in FEATURE_DEFINITION
        assert "boolean_configs" in FEATURE_DEFINITION
        assert "device_entity_mapping" in FEATURE_DEFINITION
        assert "websocket_commands" in FEATURE_DEFINITION
        assert "card_config" in FEATURE_DEFINITION
        assert "required_entities" in FEATURE_DEFINITION
        assert "entity_mappings" in FEATURE_DEFINITION

        # Check card_config is set
        assert FEATURE_DEFINITION["card_config"]["card_id"] == "hvac-fan-card"

        # Check required_entities is empty
        assert FEATURE_DEFINITION["required_entities"] == {}

    def test_entity_mappings_completeness(self):
        """Test entity mappings contain all expected entities."""
        from custom_components.ramses_extras.features.hvac_fan_card.const import (
            FEATURE_DEFINITION,
        )

        mappings = FEATURE_DEFINITION["entity_mappings"]

        # Check absolute humidity sensors
        assert (
            mappings["indoor_abs_humid_entity"]
            == "sensor.indoor_absolute_humidity_{device_id}"
        )
        assert (
            mappings["outdoor_abs_humid_entity"]
            == "sensor.outdoor_absolute_humidity_{device_id}"
        )

        # Check temperature sensors
        assert mappings["indoor_temp_entity"] == "sensor.{device_id}_indoor_temp"
        assert mappings["outdoor_temp_entity"] == "sensor.{device_id}_outdoor_temp"

        # Check fan sensors
        assert mappings["fan_info_entity"] == "sensor.{device_id}_fan_info"
        assert mappings["fan_speed_entity"] == "sensor.{device_id}_fan_rate"

        # Check CO2 entities
        assert mappings["co2_entity"] == "sensor.{device_id}_co2_level"
        assert mappings["co2_control_entity"] == "switch.co2_control_{device_id}"

        # Check humidity control entities
        assert mappings["dehum_mode_entity"] == "switch.dehumidify_{device_id}"
        assert (
            mappings["dehum_active_entity"]
            == "binary_sensor.dehumidifying_active_{device_id}"
        )

    def test_load_feature_function(self):
        """Test load_feature function registers components correctly."""
        from custom_components.ramses_extras.features.hvac_fan_card.const import (
            HVAC_FAN_CARD_BOOLEAN_CONFIGS,
            HVAC_FAN_CARD_DEVICE_ENTITY_MAPPING,
            HVAC_FAN_CARD_NUMBER_CONFIGS,
            HVAC_FAN_CARD_SENSOR_CONFIGS,
            HVAC_FAN_CARD_SWITCH_CONFIGS,
            HVAC_FAN_CARD_WEBSOCKET_COMMANDS,
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
                "custom_components.ramses_extras.features.hvac_fan_card.hvac_fan_card_yaml.load_validator"
            ) as mock_load_validator,
        ):
            load_feature()

            # Check registry calls
            mock_registry.register_device_mappings.assert_called_once_with(
                HVAC_FAN_CARD_DEVICE_ENTITY_MAPPING
            )
            mock_registry.register_websocket_commands.assert_called_once_with(
                "hvac_fan_card", HVAC_FAN_CARD_WEBSOCKET_COMMANDS
            )
            mock_registry.register_feature.assert_called_once_with("hvac_fan_card")

            # Check card config registration
            assert mock_registry.register_card_config.call_count == 1
            mock_registry.register_card_config.assert_called_with(
                "hvac_fan_card", {"card_id": "hvac-fan-card"}
            )

            # Check validator loading
            mock_load_validator.assert_called_once()

    def test_all_exports(self):
        """Test __all__ contains all public exports."""
        from custom_components.ramses_extras.features.hvac_fan_card import const

        expected_exports = [
            "HVAC_FAN_CARD_SENSOR_CONFIGS",
            "HVAC_FAN_CARD_SWITCH_CONFIGS",
            "HVAC_FAN_CARD_NUMBER_CONFIGS",
            "HVAC_FAN_CARD_BOOLEAN_CONFIGS",
            "HVAC_FAN_CARD_DEVICE_ENTITY_MAPPING",
            "HVAC_FAN_CARD_WEBSOCKET_COMMANDS",
            "HVAC_FAN_CARD_CONFIGS",
            "FEATURE_DEFINITION",
            "load_feature",
        ]

        for export in expected_exports:
            assert hasattr(const, export), f"Missing export: {export}"
