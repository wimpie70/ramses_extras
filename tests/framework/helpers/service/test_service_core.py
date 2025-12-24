"""Tests for service helper core utilities in framework/helpers/service/core.py."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall

from custom_components.ramses_extras.framework.helpers.service.core import (
    ExtrasServiceManager,
    ServiceExecutionContext,
)


class TestServiceExecutionContext:
    """Test cases for ServiceExecutionContext."""

    def setup_method(self):
        """Set up test fixtures."""
        self.hass = MagicMock()
        self.hass.loop.time.return_value = 1000.0
        self.service_name = "test_service"
        self.device_id = "32_153289"

    def test_init(self):
        """Test initialization of ServiceExecutionContext."""
        context = ServiceExecutionContext(self.hass, self.service_name, self.device_id)

        assert context.hass == self.hass
        assert context.service_name == self.service_name
        assert context.device_id == self.device_id
        assert context.start_time == 1000.0
        assert context.metadata == {}

    def test_add_metadata(self):
        """Test adding metadata to context."""
        context = ServiceExecutionContext(self.hass, self.service_name)

        context.add_metadata("key1", "value1")
        context.add_metadata("key2", 42)

        assert context.metadata["key1"] == "value1"
        assert context.metadata["key2"] == 42

    def test_get_execution_time(self):
        """Test getting execution time."""
        context = ServiceExecutionContext(self.hass, self.service_name)

        # Simulate time passing
        self.hass.loop.time.return_value = 1005.5

        execution_time = context.get_execution_time()
        assert execution_time == 5.5


class TestExtrasServiceManager:
    """Test cases for ExtrasServiceManager."""

    def setup_method(self):
        """Set up test fixtures."""
        self.hass = MagicMock()
        self.feature_id = "test_feature"
        self.config_entry = MagicMock()

    def test_init(self):
        """Test initialization of ExtrasServiceManager."""
        manager = ExtrasServiceManager(self.hass, self.feature_id, self.config_entry)

        assert manager.hass == self.hass
        assert manager.feature_id == self.feature_id
        assert manager.config_entry == self.config_entry
        assert manager._services == {}
        assert manager._entity_cache == {}
        assert manager._error_counts == {}

    def test_register_service(self):
        """Test registering a service."""
        manager = ExtrasServiceManager(self.hass, self.feature_id)
        service_func = MagicMock()

        manager.register_service("test_service", service_func)

        assert "test_service" in manager._services
        assert manager._services["test_service"] == service_func

    def test_register_services_from_dict(self):
        """Test registering multiple services from dictionary."""
        manager = ExtrasServiceManager(self.hass, self.feature_id)
        services = {
            "service1": MagicMock(),
            "service2": MagicMock(),
        }

        manager.register_services_from_dict(services)

        assert "service1" in manager._services
        assert "service2" in manager._services

    def test_get_service_existing(self):
        """Test getting an existing service."""
        manager = ExtrasServiceManager(self.hass, self.feature_id)
        service_func = MagicMock()
        manager._services["test_service"] = service_func

        result = manager.get_service("test_service")
        assert result == service_func

    def test_get_service_nonexistent(self):
        """Test getting a nonexistent service."""
        manager = ExtrasServiceManager(self.hass, self.feature_id)

        result = manager.get_service("nonexistent_service")
        assert result is None

    def test_get_all_services(self):
        """Test getting all service names."""
        manager = ExtrasServiceManager(self.hass, self.feature_id)
        manager._services = {
            "service1": MagicMock(),
            "service2": MagicMock(),
        }

        result = manager.get_all_services()
        assert set(result) == {"service1", "service2"}

    @pytest.mark.asyncio
    async def test_execute_service_success(self):
        """Test successful service execution."""
        manager = ExtrasServiceManager(self.hass, self.feature_id)
        service_func = AsyncMock(return_value=True)
        manager._services["test_service"] = service_func

        result = await manager.execute_service(
            "test_service", "32_153289", param="value"
        )

        assert result is True
        service_func.assert_called_once_with("32_153289", param="value")

    @pytest.mark.asyncio
    async def test_execute_service_not_found(self):
        """Test executing a nonexistent service."""
        manager = ExtrasServiceManager(self.hass, self.feature_id)

        result = await manager.execute_service("nonexistent_service", "32_153289")

        assert result is False

    @pytest.mark.asyncio
    async def test_execute_service_with_exception(self):
        """Test service execution with exception."""
        manager = ExtrasServiceManager(self.hass, self.feature_id)
        service_func = AsyncMock(side_effect=Exception("Test error"))
        manager._services["test_service"] = service_func

        result = await manager.execute_service("test_service", "32_153289")

        assert result is False
        assert manager._error_counts["test_service"] == 1

    @pytest.mark.asyncio
    async def test_execute_service_error_recovery(self):
        """Test that error count resets after successful execution."""
        manager = ExtrasServiceManager(self.hass, self.feature_id)
        service_func = AsyncMock(return_value=True)
        manager._services["test_service"] = service_func
        manager._error_counts["test_service"] = 2  # Simulate previous errors

        result = await manager.execute_service("test_service", "32_153289")

        assert result is True
        assert manager._error_counts["test_service"] == 0

    @pytest.mark.asyncio
    async def test_find_entity_by_pattern_cached(self):
        """Test finding entity by pattern with cache hit."""
        manager = ExtrasServiceManager(self.hass, self.feature_id)
        cache_key = "sensor:{device_id}_temp:32_153289"
        manager._entity_cache[cache_key] = "sensor.32_153289_temp"

        # Mock entity existence validation
        manager._validate_entity_exists = MagicMock(return_value=True)

        result = await manager.find_entity_by_pattern(
            "sensor", "{device_id}_temp", "32_153289"
        )

        assert result == "sensor.32_153289_temp"
        manager._validate_entity_exists.assert_called_once_with("sensor.32_153289_temp")

    @pytest.mark.asyncio
    async def test_find_entity_by_pattern_new_lookup(self):
        """Test finding entity by pattern with new lookup."""
        manager = ExtrasServiceManager(self.hass, self.feature_id)

        # Mock the entity lookup
        manager._find_entity_by_exact_pattern = AsyncMock(
            return_value="sensor.32_153289_temp"
        )

        result = await manager.find_entity_by_pattern(
            "sensor", "{device_id}_temp", "32_153289"
        )

        assert result == "sensor.32_153289_temp"
        assert "sensor:{device_id}_temp:32_153289" in manager._entity_cache

    @pytest.mark.asyncio
    async def test_find_entity_by_pattern_not_found(self):
        """Test finding entity by pattern when not found."""
        manager = ExtrasServiceManager(self.hass, self.feature_id)
        manager._find_entity_by_exact_pattern = AsyncMock(return_value=None)

        result = await manager.find_entity_by_pattern(
            "sensor", "{device_id}_temp", "32_153289"
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_find_entity_by_pattern_exception(self):
        """Test finding entity by pattern with exception."""
        manager = ExtrasServiceManager(self.hass, self.feature_id)

        # Mock EntityHelpers to raise exception
        with patch(
            "custom_components.ramses_extras.framework.helpers.service.core.EntityHelpers"
        ) as mock_helpers:
            mock_helpers.generate_entity_name_from_template.side_effect = Exception(
                "Template error"
            )

            result = await manager.find_entity_by_pattern(
                "sensor", "{device_id}_temp", "32_153289"
            )

            assert result is None

    @pytest.mark.asyncio
    async def test_find_entity_by_exact_pattern_found(self):
        """Test finding entity by exact pattern match."""
        manager = ExtrasServiceManager(self.hass, self.feature_id)
        self.hass.states = MagicMock()

        # Create mock state
        mock_state = MagicMock()
        mock_state.entity_id = "sensor.32_153289_temp"
        self.hass.states.async_all.return_value = [mock_state]

        result = await manager._find_entity_by_exact_pattern("sensor.32_153289_temp")

        assert result == "sensor.32_153289_temp"

    @pytest.mark.asyncio
    async def test_find_entity_by_exact_pattern_not_found(self):
        """Test finding entity by exact pattern when not found."""
        manager = ExtrasServiceManager(self.hass, self.feature_id)
        self.hass.states = MagicMock()
        self.hass.states.async_all.return_value = []

        result = await manager._find_entity_by_exact_pattern("sensor.nonexistent")

        assert result is None

    def test_validate_entity_exists_true(self):
        """Test validating entity exists when it does."""
        manager = ExtrasServiceManager(self.hass, self.feature_id)
        self.hass.states = MagicMock()

        mock_state = MagicMock()
        self.hass.states.get.return_value = mock_state

        result = manager._validate_entity_exists("sensor.test")

        assert result is True
        self.hass.states.get.assert_called_once_with("sensor.test")

    def test_validate_entity_exists_false(self):
        """Test validating entity exists when it doesn't."""
        manager = ExtrasServiceManager(self.hass, self.feature_id)
        self.hass.states = MagicMock()
        self.hass.states.get.return_value = None

        result = manager._validate_entity_exists("sensor.nonexistent")

        assert result is False

    def test_validate_entity_exists_exception(self):
        """Test validating entity exists with exception."""
        manager = ExtrasServiceManager(self.hass, self.feature_id)
        self.hass.states = MagicMock()
        self.hass.states.get.side_effect = Exception("State error")

        result = manager._validate_entity_exists("sensor.error")

        assert result is False

    @pytest.mark.asyncio
    async def test_call_ha_service_success(self):
        """Test calling HA service successfully."""
        manager = ExtrasServiceManager(self.hass, self.feature_id)
        self.hass.services = MagicMock()
        self.hass.services.async_call = AsyncMock()

        result = await manager.call_ha_service(
            "switch", "turn_on", entity_id="switch.test", brightness=50
        )

        assert result is True
        self.hass.services.async_call.assert_called_once_with(
            "switch", "turn_on", {"entity_id": "switch.test", "brightness": 50}
        )

    @pytest.mark.asyncio
    async def test_call_ha_service_without_entity_id(self):
        """Test calling HA service without entity_id."""
        manager = ExtrasServiceManager(self.hass, self.feature_id)
        self.hass.services = MagicMock()
        self.hass.services.async_call = AsyncMock()

        result = await manager.call_ha_service("switch", "turn_on", brightness=50)

        assert result is True
        self.hass.services.async_call.assert_called_once_with(
            "switch", "turn_on", {"brightness": 50}
        )

    @pytest.mark.asyncio
    async def test_call_ha_service_exception(self):
        """Test calling HA service with exception."""
        manager = ExtrasServiceManager(self.hass, self.feature_id)
        self.hass.services = MagicMock()
        self.hass.services.async_call = AsyncMock(
            side_effect=Exception("Service error")
        )

        result = await manager.call_ha_service("switch", "turn_on")

        assert result is False

    @pytest.mark.asyncio
    async def test_get_entity_state_found(self):
        """Test getting entity state when found."""
        manager = ExtrasServiceManager(self.hass, self.feature_id)
        self.hass.states = MagicMock()

        # Mock entity finding
        manager.find_entity_by_pattern = AsyncMock(return_value="sensor.32_153289_temp")

        # Mock state
        mock_state = MagicMock()
        mock_state.entity_id = "sensor.32_153289_temp"
        mock_state.state = "25.5"
        mock_state.attributes = {"unit": "°C"}
        self.hass.states.get.return_value = mock_state

        result = await manager.get_entity_state(
            "32_153289", "sensor", "{device_id}_temp"
        )

        assert result is not None
        assert result["entity_id"] == "sensor.32_153289_temp"
        assert result["state"] == "25.5"
        assert result["attributes"] == {"unit": "°C"}

    @pytest.mark.asyncio
    async def test_get_entity_state_not_found(self):
        """Test getting entity state when not found."""
        manager = ExtrasServiceManager(self.hass, self.feature_id)
        manager.find_entity_by_pattern = AsyncMock(return_value=None)

        result = await manager.get_entity_state(
            "32_153289", "sensor", "{device_id}_temp"
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_get_device_status(self):
        """Test getting device status."""
        manager = ExtrasServiceManager(self.hass, self.feature_id)
        manager._services = {"service1": MagicMock(), "service2": MagicMock()}
        manager._error_counts = {"service1": 2}

        result = await manager.get_device_status("32_153289")

        assert result["device_id"] == "32_153289"
        assert result["feature_id"] == "test_feature"
        assert "last_update" in result
        assert "services" in result
        assert "entities" in result
        assert "errors" in result

        # Check service status
        assert result["services"]["service1"]["available"] is True
        assert result["services"]["service1"]["error_count"] == 2
        assert result["services"]["service1"]["healthy"] is False

        assert result["services"]["service2"]["available"] is True
        assert result["services"]["service2"]["error_count"] == 0
        assert result["services"]["service2"]["healthy"] is True

    def test_get_service_descriptions_with_docstrings(self):
        """Test getting service descriptions with docstrings."""
        manager = ExtrasServiceManager(self.hass, self.feature_id)

        service_func = MagicMock()
        service_func.__doc__ = "Test service description"
        manager._services = {"test_service": service_func}

        result = manager.get_service_descriptions()

        assert result["test_service"] == "Test service description"

    def test_get_service_descriptions_without_docstrings(self):
        """Test getting service descriptions without docstrings."""
        manager = ExtrasServiceManager(self.hass, self.feature_id)

        service_func = MagicMock()
        service_func.__doc__ = None
        manager._services = {"test_service": service_func}

        result = manager.get_service_descriptions()

        assert result["test_service"] == "Execute test_service service"

    def test_clear_cache(self):
        """Test clearing entity cache."""
        manager = ExtrasServiceManager(self.hass, self.feature_id)
        manager._entity_cache = {"key1": "value1", "key2": "value2"}

        manager.clear_cache()

        assert manager._entity_cache == {}

    def test_get_cache_stats(self):
        """Test getting cache statistics."""
        manager = ExtrasServiceManager(self.hass, self.feature_id)
        manager._entity_cache = {"key1": "value1"}
        manager._error_counts = {"service1": 3}

        result = manager.get_cache_stats()

        assert result["cache_size"] == 1
        assert result["cache_keys"] == ["key1"]
        assert result["error_counts"] == {"service1": 3}

    @pytest.mark.asyncio
    async def test_service_turn_on_success(self):
        """Test turn on service success."""
        manager = ExtrasServiceManager(self.hass, self.feature_id)

        # Mock entity finding and HA service call
        manager.find_entity_by_pattern = AsyncMock(return_value="switch.32_153289_fan")
        manager.call_ha_service = AsyncMock(return_value=True)

        result = await manager.service_turn_on("32_153289", "{device_id}_fan")

        assert result is True
        manager.find_entity_by_pattern.assert_called_once_with(
            "switch", "{device_id}_fan", "32_153289"
        )
        manager.call_ha_service.assert_called_once_with(
            "switch", "turn_on", entity_id="switch.32_153289_fan"
        )

    @pytest.mark.asyncio
    async def test_service_turn_on_entity_not_found(self):
        """Test turn on service when entity not found."""
        manager = ExtrasServiceManager(self.hass, self.feature_id)
        manager.find_entity_by_pattern = AsyncMock(return_value=None)

        result = await manager.service_turn_on("32_153289", "{device_id}_fan")

        assert result is False

    @pytest.mark.asyncio
    async def test_service_turn_off_success(self):
        """Test turn off service success."""
        manager = ExtrasServiceManager(self.hass, self.feature_id)

        manager.find_entity_by_pattern = AsyncMock(return_value="switch.32_153289_fan")
        manager.call_ha_service = AsyncMock(return_value=True)

        result = await manager.service_turn_off("32_153289", "{device_id}_fan")

        assert result is True
        manager.call_ha_service.assert_called_once_with(
            "switch", "turn_off", entity_id="switch.32_153289_fan"
        )

    @pytest.mark.asyncio
    async def test_service_set_value_success(self):
        """Test set value service success."""
        manager = ExtrasServiceManager(self.hass, self.feature_id)

        manager.find_entity_by_pattern = AsyncMock(
            return_value="number.32_153289_speed"
        )
        manager.call_ha_service = AsyncMock(return_value=True)

        result = await manager.service_set_value("32_153289", "{device_id}_speed", 75)

        assert result is True
        manager.call_ha_service.assert_called_once_with(
            "number", "set_value", entity_id="number.32_153289_speed", value=75
        )

    @pytest.mark.asyncio
    async def test_service_send_command_success(self):
        """Test send command service success."""
        manager = ExtrasServiceManager(self.hass, self.feature_id)
        manager.ramses_commands.send_command = AsyncMock(return_value=True)

        result = await manager.service_send_command("32_153289", "test_command")

        assert result is True
        manager.ramses_commands.send_command.assert_called_once_with(
            "32_153289", "test_command"
        )

    @pytest.mark.asyncio
    async def test_service_send_command_failure(self):
        """Test send command service failure."""
        manager = ExtrasServiceManager(self.hass, self.feature_id)
        manager.ramses_commands.send_command = AsyncMock(return_value=False)

        result = await manager.service_send_command("32_153289", "test_command")

        assert result is False

    @pytest.mark.asyncio
    async def test_service_send_command_exception(self):
        """Test send command service with exception."""
        manager = ExtrasServiceManager(self.hass, self.feature_id)
        manager.ramses_commands.send_command = AsyncMock(
            side_effect=Exception("Command error")
        )

        result = await manager.service_send_command("32_153289", "test_command")

        assert result is False
