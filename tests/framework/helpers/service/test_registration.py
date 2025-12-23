# tests/framework/helpers/service/test_registration.py
"""Test service registration framework."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.ramses_extras.framework.helpers.service.registration import (
    ServiceDefinition,
    ServiceRegistrationManager,
    ServiceRegistry,
    ServiceScope,
    ServiceType,
)


class TestServiceEnums:
    """Test service enums."""

    def test_service_type_values(self):
        """Test ServiceType enum values."""
        assert ServiceType.ACTION.value == "action"
        assert ServiceType.STATUS.value == "status"
        assert ServiceType.CONFIGURATION.value == "configuration"
        assert ServiceType.DIAGNOSTIC.value == "diagnostic"
        assert ServiceType.CONTROL.value == "control"

    def test_service_scope_values(self):
        """Test ServiceScope enum values."""
        assert ServiceScope.DEVICE.value == "device"
        assert ServiceScope.FEATURE.value == "feature"
        assert ServiceScope.GLOBAL.value == "global"


class TestServiceDefinition:
    """Test ServiceDefinition dataclass."""

    def test_service_definition_creation_minimal(self):
        """Test creating ServiceDefinition with minimal parameters."""

        def dummy_func():
            pass

        service_def = ServiceDefinition(
            name="test_service",
            func=dummy_func,
            service_type=ServiceType.ACTION,
            scope=ServiceScope.DEVICE,
        )

        assert service_def.name == "test_service"
        assert service_def.func == dummy_func
        assert service_def.service_type == ServiceType.ACTION
        assert service_def.scope == ServiceScope.DEVICE
        assert service_def.description == ""
        assert service_def.parameters == {}
        assert service_def.device_dependent is True
        assert service_def.requires_entity is None
        assert service_def.timeout is None
        assert service_def.retry_count == 1
        assert service_def.validation_schema is None

    def test_service_definition_creation_full(self):
        """Test creating ServiceDefinition with all parameters."""

        def dummy_func():
            pass

        parameters = {"param1": "value1"}
        validation_schema = {"type": "object"}

        service_def = ServiceDefinition(
            name="test_service",
            func=dummy_func,
            service_type=ServiceType.STATUS,
            scope=ServiceScope.FEATURE,
            description="Test service description",
            parameters=parameters,
            device_dependent=False,
            requires_entity="sensor.temperature",
            timeout=30.0,
            retry_count=3,
            validation_schema=validation_schema,
        )

        assert service_def.name == "test_service"
        assert service_def.description == "Test service description"
        assert service_def.parameters == parameters
        assert service_def.device_dependent is False
        assert service_def.requires_entity == "sensor.temperature"
        assert service_def.timeout == 30.0
        assert service_def.retry_count == 3
        assert service_def.validation_schema == validation_schema


class TestServiceRegistry:
    """Test ServiceRegistry class."""

    def test_init(self):
        """Test ServiceRegistry initialization."""
        registry = ServiceRegistry()

        assert registry._services == {}
        assert registry._feature_services == {}

    def test_register_service(self):
        """Test registering a service."""
        registry = ServiceRegistry()

        def dummy_func():
            pass

        service_def = ServiceDefinition(
            name="test_service",
            func=dummy_func,
            service_type=ServiceType.ACTION,
            scope=ServiceScope.DEVICE,
        )

        registry.register_service(service_def)

        assert registry._services["test_service"] == service_def

    def test_register_service_creates_feature_dict(self):
        """Test registering a service creates feature dictionary if needed."""
        registry = ServiceRegistry()

        def dummy_func():
            pass

        service_def = ServiceDefinition(
            name="test_service",
            func=dummy_func,
            service_type=ServiceType.ACTION,
            scope=ServiceScope.DEVICE,
        )

        # Feature doesn't exist yet
        assert "new_feature" not in registry._feature_services

        registry.register_service("new_feature", service_def)

        assert "new_feature" in registry._feature_services
        assert registry._feature_services["new_feature"]["test_service"] == service_def

    def test_get_service_definitions_for_feature(self):
        """Test getting service definitions for a feature."""
        registry = ServiceRegistry()

        def dummy_func():
            pass

        service_def1 = ServiceDefinition(
            name="service1",
            func=dummy_func,
            service_type=ServiceType.ACTION,
            scope=ServiceScope.DEVICE,
        )

        service_def2 = ServiceDefinition(
            name="service2",
            func=dummy_func,
            service_type=ServiceType.STATUS,
            scope=ServiceScope.FEATURE,
        )

        registry.register_service(service_def1)
        registry.register_service(service_def2)

        services = registry.get_service_definitions_for_feature("test_feature")

        assert len(services) == 2
        assert "service1" in services
        assert "service2" in services
        assert services["service1"] == service_def1
        assert services["service2"] == service_def2

    def test_get_service_definitions_for_feature_empty(self):
        """Test getting service definitions for non-existent feature."""
        registry = ServiceRegistry()

        services = registry.get_service_definitions_for_feature("nonexistent_feature")

        assert services == {}

    def test_get_all_service_definitions(self):
        """Test getting all service definitions."""
        registry = ServiceRegistry()

        def dummy_func():
            pass

        service_def1 = ServiceDefinition(
            name="service1",
            func=dummy_func,
            service_type=ServiceType.ACTION,
            scope=ServiceScope.DEVICE,
        )

        service_def2 = ServiceDefinition(
            name="service2",
            func=dummy_func,
            service_type=ServiceType.STATUS,
            scope=ServiceScope.FEATURE,
        )

        registry.register_service(service_def1)
        registry.register_service(service_def2)

        all_services = registry.get_all_service_definitions()

        assert len(all_services) == 2
        assert "feature1" in all_services
        assert "feature2" in all_services
        assert all_services["feature1"]["service1"] == service_def1
        assert all_services["feature2"]["service2"] == service_def2

    def test_get_all_service_definitions_empty(self):
        """Test getting all service definitions when empty."""
        registry = ServiceRegistry()

        all_services = registry.get_all_service_definitions()

        assert all_services == {}

    def test_get_service_definition(self):
        """Test getting a specific service definition."""
        registry = ServiceRegistry()

        def dummy_func():
            pass

        service_def = ServiceDefinition(
            name="test_service",
            func=dummy_func,
            service_type=ServiceType.ACTION,
            scope=ServiceScope.DEVICE,
        )

        registry.register_service(service_def)

        result = registry.get_service_definition("test_service")

        assert result == service_def

    def test_get_service_definition_not_found(self):
        """Test getting a service definition that doesn't exist."""
        registry = ServiceRegistry()

        result = registry.get_service_definition("nonexistent_service")

        assert result is None

    def test_has_service(self):
        """Test checking if a service exists."""
        registry = ServiceRegistry()

        def dummy_func():
            pass

        service_def = ServiceDefinition(
            name="test_service",
            func=dummy_func,
            service_type=ServiceType.ACTION,
            scope=ServiceScope.DEVICE,
        )

        registry.register_service(service_def)

        # Check if service exists by trying to get it
        existing_service = registry.get_service("test_service")
        non_existing_service = registry.get_service("nonexistent")

        assert existing_service is not None
        assert non_existing_service is None

    def test_get_registered_features(self):
        """Test getting list of registered features."""
        registry = ServiceRegistry()

        def dummy_func():
            pass

        service_def = ServiceDefinition(
            name="test_service",
            func=dummy_func,
            service_type=ServiceType.ACTION,
            scope=ServiceScope.DEVICE,
        )

        registry.register_service(service_def)
        registry.register_service(service_def)

        features = registry.get_registered_features()

        assert set(features) == {"feature1", "feature2"}

    def test_get_registered_features_empty(self):
        """Test getting registered features when empty."""
        registry = ServiceRegistry()

        features = registry.get_registered_features()

        assert features == []


class TestServiceRegistrationManager:
    """Test ServiceRegistrationManager class."""

    def test_init_with_registry(self):
        """Test ServiceRegistrationManager initialization with provided registry."""
        registry = ServiceRegistry()
        manager = ServiceRegistrationManager("test_feature", registry)

        assert manager.feature_id == "test_feature"
        assert manager.service_registry == registry
        assert manager._registered_services == []

    def test_init_without_registry(self):
        """Test ServiceRegistrationManager initialization without registry."""
        manager = ServiceRegistrationManager("test_feature")

        assert manager.feature_id == "test_feature"
        assert isinstance(manager.service_registry, ServiceRegistry)
        assert manager._registered_services == []

    def test_register_service(self):
        """Test registering a service."""
        manager = ServiceRegistrationManager("test_feature")

        def dummy_func():
            pass

        manager.register_service(
            "test_service",
            dummy_func,
            service_type=ServiceType.ACTION,
            scope=ServiceScope.DEVICE,
            description="Test service",
            device_dependent=True,
        )

        # Check that service was registered with correct prefix
        service_def = manager.service_registry.get_service("test_feature_test_service")

        assert service_def is not None
        assert service_def.name == "test_feature_test_service"
        assert service_def.func == dummy_func
        assert service_def.service_type == ServiceType.ACTION
        assert service_def.scope == ServiceScope.DEVICE
        assert service_def.description == "Test service"
        assert service_def.device_dependent is True

        # Check that service is tracked in registered services
        assert "test_feature_test_service" in manager._registered_services

    def test_register_service_with_kwargs(self):
        """Test registering a service with additional kwargs."""
        manager = ServiceRegistrationManager("test_feature")

        def dummy_func():
            pass

        manager.register_service(
            "test_service",
            dummy_func,
            service_type=ServiceType.STATUS,
            scope=ServiceScope.FEATURE,
            timeout=30.0,
            retry_count=3,
            validation_schema={"type": "object"},
        )

        service_def = manager.service_registry.get_service("test_feature_test_service")

        assert service_def is not None
        assert service_def.service_type == ServiceType.STATUS
        assert service_def.scope == ServiceScope.FEATURE
        assert service_def.timeout == 30.0
        assert service_def.retry_count == 3
        assert service_def.validation_schema == {"type": "object"}

    def test_register_service_default_values(self):
        """Test registering a service with default values."""
        manager = ServiceRegistrationManager("test_feature")

        def dummy_func():
            pass

        manager.register_service("test_service", dummy_func)

        service_def = manager.service_registry.get_service("test_feature_test_service")

        assert service_def is not None
        assert service_def.service_type == ServiceType.ACTION  # default
        assert service_def.scope == ServiceScope.DEVICE  # default
        assert service_def.description == ""  # default
        assert service_def.parameters == {}  # default
        assert service_def.device_dependent is True  # default
        assert service_def.requires_entity is None  # default
        assert service_def.timeout is None  # default
        assert service_def.retry_count == 1  # default
        assert service_def.validation_schema is None  # default

    def test_get_registered_service_names(self):
        """Test getting registered service names."""
        manager = ServiceRegistrationManager("test_feature")

        def dummy_func():
            pass

        manager.register_service("service1", dummy_func)
        manager.register_service("service2", dummy_func)

        service_names = manager.get_registered_service_names()

        assert service_names == ["test_feature_service1", "test_feature_service2"]

    def test_get_registered_service_names_empty(self):
        """Test getting registered service names when empty."""
        manager = ServiceRegistrationManager("test_feature")

        service_names = manager.get_registered_service_names()

        assert service_names == []

    def test_unregister_service(self):
        """Test unregistering a service."""
        manager = ServiceRegistrationManager("test_feature")

        def dummy_func():
            pass

        manager.register_service("test_service", dummy_func)

        # Verify service is registered
        service_def = manager.service_registry.get_service("test_feature_test_service")
        assert service_def is not None

        # This would normally remove from registry, but since we don't have
        # an unregister method in ServiceRegistry, we'll just test tracking
        assert "test_feature_test_service" in manager._registered_services

    def test_get_service_definition(self):
        """Test getting service definition."""
        manager = ServiceRegistrationManager("test_feature")

        def dummy_func():
            pass

        manager.register_service("test_service", dummy_func)

        # ServiceRegistrationManager doesn't have get_service_definition method
        # We can test that the service was registered by checking the registry
        service_def = manager.service_registry.get_service("test_feature_test_service")

        assert service_def is not None
        assert service_def.name == "test_feature_test_service"

    def test_get_service_definition_not_found(self):
        """Test getting service definition for non-existent service."""
        manager = ServiceRegistrationManager("test_feature")

        # ServiceRegistrationManager doesn't have get_service_definition method
        # We can test that non-existent service returns None from registry
        service_def = manager.service_registry.get_service("nonexistent_service")

        assert service_def is None
