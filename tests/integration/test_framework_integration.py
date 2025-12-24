"""Integration tests for Ramses Extras components working together."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from custom_components.ramses_extras.features.sensor_control.resolver import (
    SensorControlResolver,
)
from custom_components.ramses_extras.framework.helpers.config.core import (
    ExtrasConfigManager,
)
from custom_components.ramses_extras.framework.helpers.entity.core import (
    EntityHelpers,
)
from custom_components.ramses_extras.framework.helpers.service.core import (
    ExtrasServiceManager,
)


class TestFrameworkIntegration:
    """Test cases for framework components working together."""

    def setup_method(self):
        """Set up test fixtures."""
        self.hass = MagicMock()
        self.config_entry = MagicMock()
        self.config_entry.options = {
            "sensor_control": {"sources": {}, "abs_humidity_inputs": {}}
        }
        self.hass.data = {"ramses_extras": {"config_entry": self.config_entry}}

    @pytest.mark.asyncio
    async def test_config_manager_with_entity_helpers(self):
        """Test config manager working with entity helpers."""
        # Create config manager
        config_manager = ExtrasConfigManager(
            self.hass,
            self.config_entry,
            "test_feature",
            {"enabled": True, "entity_prefix": "test"},
        )

        await config_manager.async_load()

        # Test entity name generation using config values
        entity_name = EntityHelpers.generate_entity_name_from_template(
            "sensor", "{device_id}_temperature", device_id="32_153289"
        )

        assert entity_name == "sensor.32_153289_temperature"

    @pytest.mark.asyncio
    async def test_service_manager_with_config_manager(self):
        """Test service manager integration with config manager."""
        # Create config manager
        config_manager = ExtrasConfigManager(
            self.hass,
            self.config_entry,
            "test_feature",
            {"enabled": True, "service_timeout": 30},
        )
        await config_manager.async_load()

        # Create service manager
        service_manager = ExtrasServiceManager(
            self.hass, "test_feature", self.config_entry
        )

        # Test that service manager can access config
        assert service_manager.config_entry == self.config_entry
        assert service_manager.hass == self.hass

    @pytest.mark.asyncio
    async def test_sensor_control_resolver_with_config(self):
        """Test sensor control resolver working with config system."""
        # Set up config with sensor control data
        sensor_control_config = {
            "sources": {
                "32_153_08": {
                    "indoor_temperature": {
                        "kind": "external_entity",
                        "entity_id": "sensor.room_temp",
                    }
                }
            },
            "abs_humidity_inputs": {
                "32_153_08": {
                    "indoor_abs_humidity": {
                        "temperature": {"kind": "internal"},
                        "humidity": {
                            "kind": "external",
                            "entity_id": "sensor.room_humidity",
                        },
                    }
                }
            },
        }

        self.config_entry.options = {"sensor_control": sensor_control_config}

        # Create resolver
        resolver = SensorControlResolver(self.hass)

        # Mock entity existence check
        resolver._entity_exists = MagicMock(return_value=True)

        # Test resolution
        result = await resolver.resolve_entity_mappings("32:153:08", "FAN")

        assert "mappings" in result
        assert "sources" in result
        assert "abs_humidity_inputs" in result

        # Check that external entity override worked
        assert result["sources"]["indoor_temperature"]["kind"] == "external_entity"
        assert (
            result["sources"]["indoor_temperature"]["entity_id"] == "sensor.room_temp"
        )

        # Check absolute humidity derived mapping
        assert result["sources"]["indoor_abs_humidity"]["kind"] == "derived"

    @pytest.mark.asyncio
    async def test_entity_helpers_with_service_manager(self):
        """Test entity helpers working with service manager."""
        # Create service manager
        service_manager = ExtrasServiceManager(
            self.hass, "test_feature", self.config_entry
        )

        # Mock entity finding
        service_manager._find_entity_by_exact_pattern = AsyncMock(
            return_value="sensor.32_153289_temp"
        )

        # Test entity finding through service manager
        entity_id = await service_manager.find_entity_by_pattern(
            "sensor", "{device_id}_temp", "32_153289"
        )

        assert entity_id == "sensor.32_153289_temp"

        # Test entity state retrieval
        mock_state = MagicMock()
        mock_state.entity_id = "sensor.32_153289_temp"
        mock_state.state = "25.5"
        mock_state.attributes = {"unit": "°C"}
        self.hass.states.get.return_value = mock_state

        state = await service_manager.get_entity_state(
            "32_153289", "sensor", "{device_id}_temp"
        )

        assert state is not None
        assert state["entity_id"] == "sensor.32_153289_temp"
        assert state["state"] == "25.5"


class TestFeatureIntegration:
    """Test cases for features working together."""

    def setup_method(self):
        """Set up test fixtures."""
        self.hass = MagicMock()
        self.config_entry = MagicMock()
        self.hass.data = {}
        self.hass.async_create_task = MagicMock()

    @pytest.mark.asyncio
    async def test_sensor_control_with_entity_helpers(self):
        """Test sensor control resolver working with entity helpers."""
        # Set up config entry with sensor control
        sensor_control_config = {
            "sources": {
                "32_153_08": {
                    "indoor_temperature": {
                        "kind": "external_entity",
                        "entity_id": "sensor.external_temp",
                    }
                }
            }
        }

        self.config_entry.options = {"sensor_control": sensor_control_config}
        self.hass.data = {"ramses_extras": {"config_entry": self.config_entry}}

        # Create resolver
        resolver = SensorControlResolver(self.hass)
        resolver._entity_exists = MagicMock(return_value=True)

        # Test resolution
        result = await resolver.resolve_entity_mappings("32:153:08", "FAN")

        # Verify external entity is used
        assert result["mappings"]["indoor_temperature"] == "sensor.external_temp"
        assert result["sources"]["indoor_temperature"]["kind"] == "external_entity"

    @pytest.mark.asyncio
    async def test_config_validation_with_entity_naming(self):
        """Test config validation working with entity naming patterns."""
        # Test valid entity name generation and validation
        entity_id = EntityHelpers.generate_entity_name_from_template(
            "sensor", "{device_id}_temperature", device_id="32_153289"
        )

        assert entity_id == "sensor.32_153289_temperature"

        # Test validation
        validation = EntityHelpers.validate_entity_name(entity_id)

        assert validation["is_valid"] is True
        assert validation["entity_type"] == "sensor"
        assert validation["device_id"] == "32_153289"

    @pytest.mark.asyncio
    async def test_service_execution_with_entity_resolution(self):
        """Test service execution working with entity resolution."""
        # Create service manager
        service_manager = ExtrasServiceManager(
            self.hass, "humidity_control", self.config_entry
        )

        # Mock entity finding
        service_manager.find_entity_by_pattern = AsyncMock(
            return_value="switch.32_153289_fan"
        )
        service_manager.call_ha_service = AsyncMock(return_value=True)

        # Test service execution
        result = await service_manager.service_turn_on("32_153289", "{device_id}_fan")

        assert result is True
        service_manager.find_entity_by_pattern.assert_called_once_with(
            "switch", "{device_id}_fan", "32_153289"
        )
        service_manager.call_ha_service.assert_called_once_with(
            "switch", "turn_on", entity_id="switch.32_153289_fan"
        )


class TestEndToEndIntegration:
    """Test cases for end-to-end integration scenarios."""

    def setup_method(self):
        """Set up test fixtures."""
        self.hass = MagicMock()
        self.config_entry = MagicMock()
        self.hass.data = {}
        self.hass.async_create_task = MagicMock()
        self.hass.states.async_all = MagicMock(return_value=[])

    @pytest.mark.asyncio
    async def test_device_entity_discovery_workflow(self):
        """Test complete workflow for device entity discovery."""
        device_id = "32_153289"

        # Mock some entities in HA
        mock_entities = [
            MagicMock(entity_id="sensor.32_153289_indoor_temp", state="22.5"),
            MagicMock(entity_id="sensor.32_153289_outdoor_temp", state="15.0"),
            MagicMock(entity_id="switch.32_153289_fan_mode", state="on"),
        ]
        self.hass.states.async_all.return_value = mock_entities

        # Test entity discovery
        entities = EntityHelpers.get_entities_for_device(self.hass, device_id)

        assert "sensor.32_153289_indoor_temp" in entities
        assert "sensor.32_153289_outdoor_temp" in entities
        assert "switch.32_153289_fan_mode" in entities

    @pytest.mark.asyncio
    async def test_config_to_entity_workflow(self):
        """Test workflow from configuration to entity creation."""
        # Set up config
        config_manager = ExtrasConfigManager(
            self.hass,
            self.config_entry,
            "test_feature",
            {"enabled": True, "device_id": "32_153289"},
        )
        await config_manager.async_load()

        # Generate entity using config
        device_id = config_manager.get("device_id")
        entity_id = EntityHelpers.generate_entity_name_from_template(
            "sensor", "{device_id}_status", device_id=device_id
        )

        assert entity_id == "sensor.32_153289_status"

        # Validate entity
        validation = EntityHelpers.validate_entity_name(entity_id)
        assert validation["is_valid"] is True

    @pytest.mark.asyncio
    async def test_service_to_device_workflow(self):
        """Test workflow from service call to device operation."""
        # Create service manager
        service_manager = ExtrasServiceManager(
            self.hass, "test_feature", self.config_entry
        )

        # Mock Ramses commands
        service_manager.ramses_commands.send_command = AsyncMock(return_value=True)

        # Execute service
        result = await service_manager.service_send_command("32_153289", "set_speed_5")

        assert result is True
        service_manager.ramses_commands.send_command.assert_called_once_with(
            "32_153289", "set_speed_5"
        )
