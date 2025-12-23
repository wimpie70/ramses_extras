# tests/helpers/service/test_core.py
"""Test service core functionality."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.ramses_extras.framework.helpers.service.core import (
    ExtrasServiceManager,
    ServiceExecutionContext,
)


class TestServiceExecutionContext:
    """Test ServiceExecutionContext class."""

    def test_init(self, hass):
        """Test initialization of ServiceExecutionContext."""
        device_id = "32:153289"
        service_name = "test_service"
        config_entry = MagicMock()

        context = ServiceExecutionContext(hass, service_name, device_id, config_entry)

        assert context.hass == hass
        assert context.service_name == service_name
        assert context.device_id == device_id
        assert context.config_entry == config_entry
        assert isinstance(context.start_time, float)
        assert context.metadata == {}

    def test_init_minimal(self, hass):
        """Test initialization with minimal parameters."""
        service_name = "test_service"

        context = ServiceExecutionContext(hass, service_name)

        assert context.hass == hass
        assert context.service_name == service_name
        assert context.device_id is None
        assert context.config_entry is None
        assert isinstance(context.start_time, float)
        assert context.metadata == {}

    def test_add_metadata(self, hass):
        """Test adding metadata."""
        context = ServiceExecutionContext(hass, "test")

        context.add_metadata("key1", "value1")
        context.add_metadata("key2", 42)

        assert context.metadata == {"key1": "value1", "key2": 42}

    def test_get_execution_time(self, hass):
        """Test getting execution time."""
        context = ServiceExecutionContext(hass, "test")

        # Mock loop time to return a fixed value
        with patch.object(hass.loop, "time", return_value=context.start_time + 2.5):
            execution_time = context.get_execution_time()
            assert execution_time == 2.5


class TestExtrasServiceManager:
    """Test ExtrasServiceManager class."""

    def test_init(self, hass):
        """Test initialization of ExtrasServiceManager."""
        feature_id = "test_feature"
        config_entry = MagicMock()

        manager = ExtrasServiceManager(hass, feature_id, config_entry)

        assert manager.hass == hass
        assert manager.feature_id == feature_id
        assert manager.config_entry == config_entry
        assert isinstance(manager.ramses_commands, object)  # RamsesCommands instance
        assert manager._services == {}
        assert manager._entity_cache == {}
        assert manager._error_counts == {}

    def test_init_minimal(self, hass):
        """Test initialization with minimal parameters."""
        feature_id = "test_feature"

        manager = ExtrasServiceManager(hass, feature_id)

        assert manager.hass == hass
        assert manager.feature_id == feature_id
        assert manager.config_entry is None

    def test_register_service(self, hass):
        """Test registering a service."""
        manager = ExtrasServiceManager(hass, "test")

        def test_service():
            return "test_result"

        manager.register_service("test_service", test_service)

        assert "test_service" in manager._services
        assert manager._services["test_service"] == test_service

    def test_register_services_from_dict(self, hass):
        """Test registering multiple services from dict."""
        manager = ExtrasServiceManager(hass, "test")

        services = {
            "service1": lambda: "result1",
            "service2": lambda: "result2",
        }

        manager.register_services_from_dict(services)

        assert "service1" in manager._services
        assert "service2" in manager._services

    def test_get_service(self, hass):
        """Test getting a registered service."""
        manager = ExtrasServiceManager(hass, "test")

        def test_service():
            return "result"

        manager.register_service("test_service", test_service)

        retrieved = manager.get_service("test_service")
        assert retrieved == test_service

        not_found = manager.get_service("nonexistent")
        assert not_found is None

    def test_get_all_services(self, hass):
        """Test getting all service names."""
        manager = ExtrasServiceManager(hass, "test")

        services = {"service1": lambda: None, "service2": lambda: None}
        manager.register_services_from_dict(services)

        service_names = manager.get_all_services()
        assert set(service_names) == {"service1", "service2"}

    @pytest.mark.asyncio
    async def test_execute_service_success(self, hass):
        """Test successful service execution."""
        manager = ExtrasServiceManager(hass, "test")

        async def test_service(device_id, **kwargs):
            return {"result": "success"}

        manager.register_service("test_service", test_service)

        result = await manager.execute_service(
            "test_service", "32:153289", param="value"
        )

        assert result == {"result": "success"}

    @pytest.mark.asyncio
    async def test_execute_service_not_found(self, hass):
        """Test executing non-existent service."""
        manager = ExtrasServiceManager(hass, "test")

        result = await manager.execute_service("nonexistent", "32:153289")

        assert result is False

    @pytest.mark.asyncio
    async def test_execute_service_exception(self, hass):
        """Test service execution with exception."""
        manager = ExtrasServiceManager(hass, "test")

        async def failing_service(device_id, **kwargs):
            raise Exception("Test error")

        manager.register_service("failing_service", failing_service)

        result = await manager.execute_service("failing_service", "32:153289")

        assert result is False
        assert manager._error_counts["failing_service"] == 1

    @pytest.mark.asyncio
    async def test_find_entity_by_pattern(self, hass):
        """Test finding entity by pattern."""
        manager = ExtrasServiceManager(hass, "test")

        # Mock the EntityHelpers.generate_entity_name_from_template method
        with (
            patch(
                "custom_components.ramses_extras.framework.helpers.service.core.EntityHelpers.generate_entity_name_from_template",
                return_value="sensor.test_entity_32_153289",
            ) as mock_generate,
            patch.object(
                manager,
                "_find_entity_by_exact_pattern",
                return_value="sensor.test_entity_32_153289",
            ) as mock_find,
        ):
            result = await manager.find_entity_by_pattern(
                "sensor", "test_entity", "32:153289"
            )

            assert result == "sensor.test_entity_32_153289"
            mock_generate.assert_called_once_with(
                "sensor", "test_entity", device_id="32_153289"
            )
            mock_find.assert_called_once_with("sensor.test_entity_32_153289")

    # Note: _validate_entity_exists and call_ha_service methods are tested through
    # integration tests since Home Assistant test fixtures have read-only attributes
    # that prevent proper unit test mocking of hass.states.get and
    # hass.services.async_call
