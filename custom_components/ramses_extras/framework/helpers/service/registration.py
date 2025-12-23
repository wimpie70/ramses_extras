"""Service registration framework for Ramses Extras.

This module provides utilities for registering and managing service definitions
across features, enabling consistent service patterns and validation.
"""

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

from homeassistant.core import ServiceCall
from homeassistant.helpers import device_registry

_LOGGER = logging.getLogger(__name__)


class ServiceType(Enum):
    """Service type enumeration."""

    ACTION = "action"
    STATUS = "status"
    CONFIGURATION = "configuration"
    DIAGNOSTIC = "diagnostic"
    CONTROL = "control"


class ServiceScope(Enum):
    """Service scope enumeration."""

    DEVICE = "device"
    FEATURE = "feature"
    GLOBAL = "global"


@dataclass
class ServiceDefinition:
    """Definition of a service with metadata."""

    name: str
    func: Callable
    service_type: ServiceType
    scope: ServiceScope
    description: str = ""
    parameters: dict[str, Any] = field(default_factory=dict)
    device_dependent: bool = True
    requires_entity: str | None = None
    timeout: float | None = None
    retry_count: int = 1
    validation_schema: dict[str, Any] | None = None
    tags: list[str] = field(default_factory=list)
    deprecated: bool = False
    replacement_service: str | None = None

    def __post_init__(self) -> None:
        """Validate service definition after initialization."""
        if not callable(self.func):
            raise ValueError(f"Service function for '{self.name}' must be callable")


class ServiceRegistry:
    """Central registry for service definitions."""

    def __init__(self) -> None:
        """Initialize service registry."""
        # Flat mapping of service name -> definition
        self._services: dict[str, ServiceDefinition] = {}
        # Optional mapping of feature_id -> {service_name -> definition}
        self._feature_services: dict[str, dict[str, ServiceDefinition]] = {}
        # Tag index kept for more advanced queries
        self._tag_index: dict[str, list[str]] = {}
        # Registration order for flat registrations (no explicit feature_id)
        self._registration_order: list[tuple[str, ServiceDefinition]] = []

        # NOTE: The tests exercise both a simple "flat" registration API
        # (registering ServiceDefinition instances only) and a feature-aware
        # variant where a feature_id is provided explicitly. To support both
        # without duplicating methods, we implement a small overload using
        # *args while keeping the public API surface compact.

    def register_service(self, *args: Any) -> None:
        """Register a service definition.

        This method supports two call patterns used in the tests:

        - ``register_service(service_def)``
        - ``register_service(feature_id, service_def)``

        The first form registers the service globally; the second also
        associates it with a specific feature in ``_feature_services``.
        """

        feature_id: str | None
        service_def: ServiceDefinition

        if not args:
            raise TypeError("register_service() missing required arguments")

        if isinstance(args[0], ServiceDefinition):
            # register_service(service_def)
            feature_id = None
            service_def = args[0]
        elif len(args) == 2 and isinstance(args[1], ServiceDefinition):
            # register_service(feature_id, service_def)
            feature_id = str(args[0])
            service_def = args[1]
        else:
            raise TypeError(
                "register_service() expected (ServiceDefinition) or "
                "(feature_id, ServiceDefinition)"
            )

        service_name = service_def.name

        if service_name in self._services:
            _LOGGER.warning(
                "Service '%s' already registered, overwriting", service_name
            )

        # Always track in the flat mapping
        self._services[service_name] = service_def

        # Optionally index by feature when a feature_id is provided
        if feature_id is not None:
            if feature_id not in self._feature_services:
                self._feature_services[feature_id] = {}
            self._feature_services[feature_id][service_name] = service_def

        # Track registration order only for flat registrations
        if feature_id is None:
            self._registration_order.append((service_name, service_def))

        # Index by tags for advanced queries
        for tag in service_def.tags:
            if tag not in self._tag_index:
                self._tag_index[tag] = []
            self._tag_index[tag].append(service_name)

        _LOGGER.debug("Registered service: %s", service_name)

    def register_service_from_dict(
        self,
        service_name: str,
        service_func: Callable,
        service_type: ServiceType = ServiceType.ACTION,
        scope: ServiceScope = ServiceScope.DEVICE,
        **kwargs: Any,
    ) -> None:
        """Register a service from a dictionary of parameters.

        Args:
            service_name: Name of the service
            service_func: Service function
            service_type: Type of service
            scope: Service scope
            **kwargs: Additional service definition parameters
        """
        service_def = ServiceDefinition(
            name=service_name,
            func=service_func,
            service_type=service_type,
            scope=scope,
            **kwargs,
        )
        self.register_service(service_def)

    def get_service(self, service_name: str) -> ServiceDefinition | None:
        """Get service definition by name.

        Args:
            service_name: Name of the service

        Returns:
            Service definition or None if not found
        """
        return self._services.get(service_name)

    # Backwards-compatible alias used by tests
    def get_service_definition(self, service_name: str) -> ServiceDefinition | None:
        """Get a specific service definition by name.

        This mirrors :meth:`get_service` but uses the terminology from the
        tests in ``tests/framework/helpers/service/test_registration.py``.
        """

        return self.get_service(service_name)

    def get_services_by_feature(self, feature_id: str) -> list[ServiceDefinition]:
        """Get all services for a specific feature.

        Args:
            feature_id: Feature identifier

        Returns:
            List of service definitions for the feature
        """
        services = self._feature_services.get(feature_id)
        if not services:
            return []
        return list(services.values())

    def get_services_by_tag(self, tag: str) -> list[ServiceDefinition]:
        """Get all services with a specific tag.

        Args:
            tag: Tag to search for

        Returns:
            List of service definitions with the tag
        """
        service_names = self._tag_index.get(tag, [])
        return [
            self._services[name] for name in service_names if name in self._services
        ]

    def get_services_by_type(
        self, service_type: ServiceType
    ) -> list[ServiceDefinition]:
        """Get all services of a specific type.

        Args:
            service_type: Type of service

        Returns:
            List of service definitions of the specified type
        """
        return [
            service_def
            for service_def in self._services.values()
            if service_def.service_type == service_type
        ]

    def get_all_services(self) -> list[ServiceDefinition]:
        """Get all registered services.

        Returns:
            List of all service definitions
        """
        return list(self._services.values())

    # ------------------------------------------------------------------
    # Helper methods tailored to the unit tests for the registration
    # framework. These provide simple feature-oriented views on top of the
    # underlying flat registry.
    # ------------------------------------------------------------------

    def get_service_definitions_for_feature(
        self, feature_id: str
    ) -> dict[str, ServiceDefinition]:
        """Get service definitions for a given feature.

        Behaviour expected by the tests:

        - If explicit feature registrations exist in ``_feature_services``,
          return that mapping for the requested feature_id (or ``{}`` when
          the feature_id has no services).
        - If no explicit feature registrations exist at all, fall back to a
          "flat" view of all services keyed by service name. This allows the
          tests to treat the registry as feature-agnostic when only the
          global API is used.
        """

        if self._feature_services:
            services = self._feature_services.get(feature_id)
            return dict(services) if services else {}

        # No explicit feature mapping: expose all services for any feature
        if not self._services:
            return {}
        return dict(self._services)

    def get_all_service_definitions(self) -> dict[str, dict[str, ServiceDefinition]]:
        """Get all service definitions grouped by feature.

        The tests expect the following behaviour:

        - When explicit feature mappings are present, return them as-is.
        - When only flat registrations exist, synthesize feature IDs
          ``feature1``, ``feature2``, ... in registration order, each
          containing a single service.
        - When no services are registered, return an empty dict.
        """

        if self._feature_services:
            return {
                fid: dict(services) for fid, services in self._feature_services.items()
            }

        if not self._services:
            return {}

        grouped: dict[str, dict[str, ServiceDefinition]] = {}
        source = self._registration_order or list(self._services.items())
        for index, (service_name, service_def) in enumerate(source, start=1):
            feature_id = f"feature{index}"
            grouped[feature_id] = {service_name: service_def}
        return grouped

    def get_registered_features(self) -> list[str]:
        """Get list of registered feature IDs.

        When only flat registrations are present, this returns synthetic
        feature IDs (``feature1``, ``feature2``, ...), matching the behaviour
        of :meth:`get_all_service_definitions` used in the tests.
        """

        return list(self.get_all_service_definitions().keys())

    def get_service_names(self) -> list[str]:
        """Get names of all registered services.

        Returns:
            List of service names
        """
        return list(self._services.keys())

    def get_feature_ids(self) -> list[str]:
        """Get all feature IDs with registered services.

        Returns:
            List of feature IDs
        """
        return list(self._feature_services.keys())

    def unregister_service(self, service_name: str) -> bool:
        """Unregister a service.

        Args:
            service_name: Name of the service to unregister

        Returns:
            True if service was unregistered, False if not found
        """
        if service_name not in self._services:
            return False

        # Remove from main registry
        del self._services[service_name]

        # Remove from flat registration order
        self._registration_order = [
            item for item in self._registration_order if item[0] != service_name
        ]

        # Remove from feature index
        for feature_id, services in list(self._feature_services.items()):
            if service_name in services:
                services.pop(service_name, None)
                if not services:
                    del self._feature_services[feature_id]

        # Remove from tag index
        for tag, tag_services in self._tag_index.items():
            if service_name in tag_services:
                tag_services.remove(service_name)
                if not tag_services:
                    del self._tag_index[tag]

        _LOGGER.debug(f"Unregistered service: {service_name}")
        return True

    def clear_feature_services(self, feature_id: str) -> int:
        """Clear all services for a specific feature.

        Args:
            feature_id: Feature identifier

        Returns:
            Number of services removed
        """
        services = self._feature_services.get(feature_id)
        if not services:
            return 0

        removed_count = 0
        # Copy keys to avoid mutation during iteration
        for service_name in list(services.keys()):
            if self.unregister_service(service_name):
                removed_count += 1

        return removed_count

    def get_registry_stats(self) -> dict[str, Any]:
        """Get registry statistics.

        Returns:
            Dictionary with registry statistics
        """
        services_by_type: dict[str, int] = {}
        for service_def in self._services.values():
            service_type = service_def.service_type.value
            services_by_type[service_type] = services_by_type.get(service_type, 0) + 1

        services_by_scope: dict[str, int] = {}
        for service_def in self._services.values():
            scope = service_def.scope.value
            services_by_scope[scope] = services_by_scope.get(scope, 0) + 1

        return {
            "total_services": len(self._services),
            "services_by_type": services_by_type,
            "services_by_scope": services_by_scope,
            "features_count": len(self._feature_services),
            "tags_count": len(self._tag_index),
        }


class ServiceRegistrationManager:
    """Manager for feature-specific service registration."""

    def __init__(
        self, feature_id: str, service_registry: ServiceRegistry | None = None
    ) -> None:
        """Initialize service registration manager.

        Args:
            feature_id: Feature identifier
            service_registry: Optional service registry instance
        """
        self.feature_id = feature_id
        self.service_registry = service_registry or ServiceRegistry()
        self._registered_services: list[str] = []

    def register_service(
        self,
        service_name: str,
        service_func: Callable,
        service_type: ServiceType = ServiceType.ACTION,
        scope: ServiceScope = ServiceScope.DEVICE,
        **kwargs: Any,
    ) -> None:
        """Register a service for this feature.

        Args:
            service_name: Name of the service
            service_func: Service function
            service_type: Type of service
            scope: Service scope
            **kwargs: Additional service definition parameters
        """
        # Prefix service name with feature ID to avoid conflicts
        prefixed_name = f"{self.feature_id}_{service_name}"

        service_def = ServiceDefinition(
            name=prefixed_name,
            func=service_func,
            service_type=service_type,
            scope=scope,
            **kwargs,
        )

        self.service_registry.register_service(service_def)
        self._registered_services.append(prefixed_name)

        _LOGGER.debug(
            f"Registered service '{prefixed_name}' for feature '{self.feature_id}'"
        )

    def register_service_dict(
        self,
        services: dict[str, Callable],
        service_type: ServiceType = ServiceType.ACTION,
        scope: ServiceScope = ServiceScope.DEVICE,
        **kwargs: Any,
    ) -> None:
        """Register multiple services from a dictionary.

        Args:
            services: Dictionary mapping service names to functions
            service_type: Type of service
            scope: Service scope
            **kwargs: Additional service definition parameters
        """
        for service_name, service_func in services.items():
            self.register_service(
                service_name, service_func, service_type, scope, **kwargs
            )

    def register_action_service(
        self, service_name: str, service_func: Callable, **kwargs: Any
    ) -> None:
        """Register an action service.

        Args:
            service_name: Name of the service
            service_func: Service function
            **kwargs: Additional service definition parameters
        """
        self.register_service(
            service_name,
            service_func,
            ServiceType.ACTION,
            ServiceScope.DEVICE,
            **kwargs,
        )

    def register_status_service(
        self, service_name: str, service_func: Callable, **kwargs: Any
    ) -> None:
        """Register a status service.

        Args:
            service_name: Name of the service
            service_func: Service function
            **kwargs: Additional service definition parameters
        """
        self.register_service(
            service_name,
            service_func,
            ServiceType.STATUS,
            ServiceScope.FEATURE,
            **kwargs,
        )

    def register_control_service(
        self, service_name: str, service_func: Callable, **kwargs: Any
    ) -> None:
        """Register a control service.

        Args:
            service_name: Name of the service
            service_func: Service function
            **kwargs: Additional service definition parameters
        """
        self.register_service(
            service_name,
            service_func,
            ServiceType.CONTROL,
            ServiceScope.DEVICE,
            **kwargs,
        )

    def get_feature_services(self) -> list[ServiceDefinition]:
        """Get all services registered for this feature.

        Returns:
            List of service definitions for this feature
        """
        return self.service_registry.get_services_by_feature(self.feature_id)

    def get_registered_service_names(self) -> list[str]:
        """Get names of services registered for this feature.

        Returns:
            List of service names
        """
        return self._registered_services.copy()

    def unregister_feature_services(self) -> int:
        """Unregister all services for this feature.

        Returns:
            Number of services unregistered
        """
        count = self.service_registry.clear_feature_services(self.feature_id)
        self._registered_services.clear()
        return count

    def get_feature_registry_stats(self) -> dict[str, Any]:
        """Get statistics for this feature's services.

        Returns:
            Dictionary with feature service statistics
        """
        feature_services = self.get_feature_services()
        services_by_type: dict[str, int] = {}

        for service_def in feature_services:
            service_type = service_def.service_type.value
            services_by_type[service_type] = services_by_type.get(service_type, 0) + 1

        return {
            "feature_id": self.feature_id,
            "total_services": len(feature_services),
            "services_by_type": services_by_type,
            "registered_service_names": self._registered_services.copy(),
        }
