"""Core service management framework for Ramses Extras.

This module provides the base framework for service management,
extracting common patterns from existing service implementations
to enable reuse across features and future service types.
"""

import logging
from typing import Any, Callable, Dict, List, Optional, Union, cast

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import SERVICE_TURN_OFF, SERVICE_TURN_ON
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import entity_registry

from ..entity.core import EntityHelpers
from ..ramses_commands import RamsesCommands

_LOGGER = logging.getLogger(__name__)


class ServiceExecutionContext:
    """Context for service execution with metadata."""

    def __init__(
        self,
        hass: HomeAssistant,
        service_name: str,
        device_id: str | None = None,
        config_entry: ConfigEntry | None = None,
    ) -> None:
        """Initialize service execution context.

        Args:
            hass: Home Assistant instance
            service_name: Name of the service being executed
            device_id: Optional device identifier
            config_entry: Optional configuration entry
        """
        self.hass = hass
        self.service_name = service_name
        self.device_id = device_id
        self.config_entry = config_entry
        self.start_time = hass.loop.time()
        self.metadata: dict[str, Any] = {}

    def add_metadata(self, key: str, value: Any) -> None:
        """Add metadata to the execution context.

        Args:
            key: Metadata key
            value: Metadata value
        """
        self.metadata[key] = value

    def get_execution_time(self) -> float:
        """Get execution time in seconds.

        Returns:
            Execution time in seconds
        """
        return float(self.hass.loop.time() - self.start_time)


class ExtrasServiceManager:
    """Base class for feature-specific service management.

    This class extracts common patterns from existing service managers
    and provides a framework for consistent service management.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        feature_id: str,
        config_entry: ConfigEntry | None = None,
    ) -> None:
        """Initialize service manager.

        Args:
            hass: Home Assistant instance
            feature_id: Feature identifier
            config_entry: Configuration entry
        """
        self.hass: HomeAssistant = hass
        self.feature_id = feature_id
        self.config_entry = config_entry or None

        # Initialize Ramses commands for device control
        self.ramses_commands = RamsesCommands(hass)

        # Service registry
        self._services: dict[str, Callable] = {}

        # Entity lookup cache
        self._entity_cache: dict[str, str] = {}

        # Service validation and error handling
        self._error_counts: dict[str, int] = {}

        _LOGGER.debug(f"Initialized {feature_id} service manager")

    def register_service(self, service_name: str, service_func: Callable) -> None:
        """Register a service method.

        Args:
            service_name: Name of the service
            service_func: Service function to register
        """
        self._services[service_name] = service_func
        _LOGGER.debug(
            f"Registered service '{service_name}' for feature '{self.feature_id}'"
        )

    def register_services_from_dict(self, services: dict[str, Callable]) -> None:
        """Register multiple services from a dictionary.

        Args:
            services: Dictionary mapping service names to functions
        """
        for service_name, service_func in services.items():
            self.register_service(service_name, service_func)

    def get_service(self, service_name: str) -> Callable | None:
        """Get a registered service by name.

        Args:
            service_name: Name of the service

        Returns:
            Service function or None if not found
        """
        return self._services.get(service_name)

    def get_all_services(self) -> list[str]:
        """Get list of all registered service names.

        Returns:
            List of service names
        """
        return list(self._services.keys())

    async def execute_service(
        self, service_name: str, device_id: str, **kwargs: Any
    ) -> bool | dict[str, Any]:
        """Execute a service with error handling and logging.

        Args:
            service_name: Name of the service to execute
            device_id: Device identifier
            **kwargs: Additional service parameters

        Returns:
            Service execution result
        """
        service_func = self.get_service(service_name)
        if not service_func:
            _LOGGER.error(
                f"Service '{service_name}' not found for feature '{self.feature_id}'"
            )
            return False

        # Create execution context
        context = ServiceExecutionContext(
            self.hass, service_name, device_id, self.config_entry
        )
        context.add_metadata("kwargs", kwargs)

        try:
            _LOGGER.info(f"Executing service '{service_name}' for device '{device_id}'")

            # Execute service
            result = await service_func(device_id, **kwargs)

            # Log execution time
            execution_time = context.get_execution_time()
            _LOGGER.debug(f"Service '{service_name}' executed in {execution_time:.2f}s")

            # Reset error count on success
            if service_name in self._error_counts:
                self._error_counts[service_name] = 0

            return cast(bool | dict[str, Any], result)

        except Exception as e:
            # Increment error count
            error_count = self._error_counts.get(service_name, 0) + 1
            self._error_counts[service_name] = error_count

            _LOGGER.error(
                f"Service '{service_name}' failed for device '{device_id}': {e}"
                f" (attempt #{error_count})"
            )
            return False

    async def find_entity_by_pattern(
        self, entity_type: str, entity_template: str, device_id: str
    ) -> str | None:
        """Find entity by pattern using EntityHelpers.

        Args:
            entity_type: Type of entity (sensor, switch, number, etc.)
            entity_template: Template for entity name
            device_id: Device identifier

        Returns:
            Entity ID or None if not found
        """
        # Convert device_id to underscore format
        device_id_underscore = device_id.replace(":", "_")

        # Generate entity pattern
        try:
            entity_pattern = EntityHelpers.generate_entity_name_from_template(
                entity_type, entity_template, device_id=device_id_underscore
            )

            # Check cache first
            cache_key = f"{entity_type}:{entity_template}:{device_id}"
            if cache_key in self._entity_cache:
                cached_entity = self._entity_cache[cache_key]
                # Verify cached entity still exists
                if self._validate_entity_exists(cached_entity):
                    return cached_entity

            # Find entity by pattern
            entity_id = await self._find_entity_by_exact_pattern(entity_pattern)

            # Cache successful lookups
            if entity_id:
                self._entity_cache[cache_key] = entity_id

            return entity_id

        except Exception as e:
            _LOGGER.error(f"Failed to find entity for pattern '{entity_template}': {e}")
            return None

    async def _find_entity_by_exact_pattern(self, pattern: str) -> str | None:
        """Find entity by exact pattern match.

        Args:
            pattern: Entity pattern to search for

        Returns:
            Entity ID or None if not found
        """
        # Get all states and find matching entity
        states = self.hass.states.async_all()
        for state in states:
            if state.entity_id == pattern:
                return str(state.entity_id)

        return None

    def _validate_entity_exists(self, entity_id: str) -> bool:
        """Validate that an entity exists.

        Args:
            entity_id: Entity identifier

        Returns:
            True if entity exists, False otherwise
        """
        try:
            entity_state = self.hass.states.get(entity_id)
            return entity_state is not None
        except Exception:
            return False

    async def call_ha_service(
        self,
        domain: str,
        service: str,
        entity_id: str | None = None,
        **service_data: Any,
    ) -> bool:
        """Call Home Assistant service with error handling.

        Args:
            domain: HA domain (switch, number, etc.)
            service: HA service name
            entity_id: Optional entity ID
            **service_data: Service data

        Returns:
            True if successful, False otherwise
        """
        try:
            # Prepare service data
            data = service_data.copy()
            if entity_id:
                data["entity_id"] = entity_id

            # Call service
            await self.hass.services.async_call(domain, service, data)

            _LOGGER.debug(f"Called HA service: {domain}.{service} with data: {data}")
            return True

        except Exception as e:
            _LOGGER.error(f"Failed to call HA service {domain}.{service}: {e}")
            return False

    async def get_entity_state(
        self, device_id: str, entity_type: str, entity_template: str
    ) -> dict[str, Any] | None:
        """Get state for a specific entity.

        Args:
            device_id: Device identifier
            entity_type: Type of entity
            entity_template: Template for entity name

        Returns:
            State dictionary or None if not found
        """
        entity_id = await self.find_entity_by_pattern(
            entity_type, entity_template, device_id
        )

        if not entity_id:
            return None

        state = self.hass.states.get(entity_id)
        if state:
            return {
                "entity_id": state.entity_id,
                "state": state.state,
                "attributes": dict(state.attributes),
            }

        return None

    async def get_device_status(self, device_id: str) -> dict[str, Any]:
        """Get comprehensive status for a device.

        Args:
            device_id: Device identifier

        Returns:
            Status dictionary
        """
        status = {
            "device_id": device_id,
            "feature_id": self.feature_id,
            "last_update": self.hass.loop.time(),
            "services": {},
            "entities": {},
            "errors": {},
        }

        # Get service status
        for service_name in self.get_all_services():
            service_func = self.get_service(service_name)
            error_count = self._error_counts.get(service_name, 0)
            status["services"][service_name] = {
                "available": service_func is not None,
                "error_count": error_count,
                "healthy": error_count == 0,
            }

        return status

    def get_service_descriptions(self) -> dict[str, str]:
        """Get descriptions of available services.

        Returns:
            Dictionary mapping service names to descriptions
        """
        descriptions = {}
        for service_name in self.get_all_services():
            service_func = self.get_service(service_name)
            if (
                service_func
                and hasattr(service_func, "__doc__")
                and service_func.__doc__
            ):
                descriptions[service_name] = service_func.__doc__.strip()
            else:
                descriptions[service_name] = f"Execute {service_name} service"

        return descriptions

    def clear_cache(self) -> None:
        """Clear entity lookup cache."""
        self._entity_cache.clear()
        _LOGGER.debug(f"Cleared entity cache for feature '{self.feature_id}'")

    def get_cache_stats(self) -> dict[str, Any]:
        """Get cache statistics.

        Returns:
            Cache statistics dictionary
        """
        return {
            "cache_size": len(self._entity_cache),
            "cache_keys": list(self._entity_cache.keys()),
            "error_counts": self._error_counts.copy(),
        }

    # Common service patterns that can be inherited

    async def service_turn_on(self, device_id: str, entity_template: str) -> bool:
        """Generic turn on service for an entity.

        Args:
            device_id: Device identifier
            entity_template: Entity template for the switch

        Returns:
            True if successful
        """
        entity_id = await self.find_entity_by_pattern(
            "switch", entity_template, device_id
        )
        if not entity_id:
            _LOGGER.error(
                f"Entity not found for template '{entity_template}' on device "
                f"{device_id}"
            )
            return False

        return await self.call_ha_service(
            "switch", SERVICE_TURN_ON, entity_id=entity_id
        )

    async def service_turn_off(self, device_id: str, entity_template: str) -> bool:
        """Generic turn off service for an entity.

        Args:
            device_id: Device identifier
            entity_template: Entity template for the switch

        Returns:
            True if successful
        """
        entity_id = await self.find_entity_by_pattern(
            "switch", entity_template, device_id
        )
        if not entity_id:
            _LOGGER.error(
                f"Entity not found for template '{entity_template}' on device "
                f"{device_id}"
            )
            return False

        return await self.call_ha_service(
            "switch", SERVICE_TURN_OFF, entity_id=entity_id
        )

    async def service_set_value(
        self, device_id: str, entity_template: str, value: float | int
    ) -> bool:
        """Generic set value service for a number entity.

        Args:
            device_id: Device identifier
            entity_template: Entity template for the number
            value: Value to set

        Returns:
            True if successful
        """
        entity_id = await self.find_entity_by_pattern(
            "number", entity_template, device_id
        )
        if not entity_id:
            _LOGGER.error(
                f"Entity not found for template '{entity_template}' on device "
                f"{device_id}"
            )
            return False

        return await self.call_ha_service(
            "number", "set_value", entity_id=entity_id, value=value
        )

    async def service_send_command(self, device_id: str, command: str) -> bool:
        """Send command to device via Ramses RF.

        Args:
            device_id: Device identifier
            command: Command to send

        Returns:
            True if successful
        """
        try:
            # Use Ramses commands framework
            success = await self.ramses_commands.send_command(device_id, command)  # type: ignore[attr-defined]
            if success:
                _LOGGER.info(f"Command '{command}' sent to device {device_id}")
            else:
                _LOGGER.warning(
                    f"Failed to send command '{command}' to device {device_id}"
                )
            return bool(success)
        except Exception as e:
            _LOGGER.error(f"Error sending command to device {device_id}: {e}")
            return False
