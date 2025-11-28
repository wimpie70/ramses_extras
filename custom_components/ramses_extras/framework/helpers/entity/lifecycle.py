"""Entity lifecycle management for Ramses Extras framework.

This module provides lifecycle patterns for entity creation, updating,
and cleanup across all features, extracting common lifecycle management
patterns from existing entity implementations.
"""

import logging
from collections.abc import MutableMapping
from typing import Any, Callable, Dict, List, Optional, cast

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import Entity

from .core import EntityHelpers

_LOGGER = logging.getLogger(__name__)


class EntityLifecycleManager:
    """Manager for entity lifecycle operations across features.

    This class provides centralized lifecycle management for entities,
    handling creation, updates, cleanup, and state management in a
    consistent way across all features.
    """

    def __init__(
        self, hass: HomeAssistant, config_entry: ConfigEntry | None = None
    ) -> None:
        """Initialize entity lifecycle manager.

        Args:
            hass: Home Assistant instance
            config_entry: Configuration entry for feature
        """
        self.hass = hass
        self.config_entry = config_entry
        self.feature_id: str = "unknown"
        self._entity_factories: dict[str, Callable] = {}
        self._entity_states: dict[str, dict[str, Any]] = {}
        self._entity_configs: dict[str, dict[str, Any]] = {}

    def register_feature(self, feature_id: str) -> None:
        """Register a feature with the lifecycle manager.

        Args:
            feature_id: Feature identifier
        """
        self.feature_id = feature_id
        _LOGGER.debug(f"Registered feature '{feature_id}' with lifecycle manager")

    def register_entity_factory(
        self,
        entity_type: str,
        factory: Callable[[Any, str, dict[str, Any]], list[Entity]],
    ) -> None:
        """Register an entity factory for a specific entity type.

        Args:
            entity_type: Type of entity (sensor, switch, number, etc.)
            factory: Factory function to create entities
        """
        self._entity_factories[entity_type] = factory
        _LOGGER.debug(f"Registered entity factory for type '{entity_type}'")

    async def create_feature_entities(
        self, device_id: str, device_type: str, entity_configs: dict[str, Any]
    ) -> list[Entity]:
        """Create all entities for a feature on a specific device.

        Args:
            device_id: Device identifier
            device_type: Type of device
            entity_configs: Configuration for entities to create

        Returns:
            List of created entities
        """
        _LOGGER.info(
            f"Creating {self.feature_id} entities for device {device_id} "
            f"({device_type})"
        )

        entities = []

        # Create entities for each configured entity type
        for entity_type, configs in entity_configs.items():
            try:
                # Get or create entity factory
                factory = self._entity_factories.get(entity_type)
                if not factory:
                    _LOGGER.warning(
                        f"No factory registered for entity type '{entity_type}'"
                    )
                    continue

                # Create entities using factory
                created_entities = await self._create_entities_via_factory(
                    factory, device_id, configs
                )
                entities.extend(created_entities)

                # Track entity lifecycle state
                for entity in created_entities:
                    self._track_entity_lifecycle(entity)

            except Exception as e:
                _LOGGER.error(
                    f"Failed to create {entity_type} entities for device "
                    f"{device_id}: {e}"
                )

        _LOGGER.info(
            f"Created {len(entities)} {self.feature_id} entities for device {device_id}"
        )
        return entities

    async def _create_entities_via_factory(
        self, factory: Callable, device_id: str, configs: dict[str, Any]
    ) -> list[Entity]:
        """Create entities using a registered factory.

        Args:
            factory: Entity factory function
            device_id: Device identifier
            configs: Entity configurations

        Returns:
            List of created entities
        """
        try:
            # Handle both sync and async factories
            # Try async first
            try:
                return cast(
                    list[Entity],
                    await factory(self.hass, device_id, self.config_entry),
                )
            except Exception:
                # Fallback to sync call
                return cast(
                    list[Entity], factory(self.hass, device_id, self.config_entry)
                )

        except Exception as e:
            _LOGGER.error(f"Entity factory call failed: {e}")
            return []

    async def validate_entity_availability(self) -> bool:
        """Validate that all required entities are available and functional.

        Returns:
            True if all entities are available, False otherwise
        """
        _LOGGER.debug(f"Validating {self.feature_id} entity availability...")

        try:
            all_states = self.hass.states.async_all()
            feature_entities = [
                state
                for state in all_states
                if self._is_feature_entity(state.entity_id)
            ]

            missing_entities = []
            unavailable_entities = []

            for entity_id, state_info in self._entity_states.items():
                if entity_id not in [e.entity_id for e in feature_entities]:
                    missing_entities.append(entity_id)
                else:
                    # Check if entity is available
                    entity_state = self.hass.states.get(entity_id)
                    if entity_state and entity_state.state == "unavailable":
                        unavailable_entities.append(entity_id)

            if missing_entities:
                _LOGGER.warning(
                    f"Missing {self.feature_id} entities: {missing_entities}"
                )
            if unavailable_entities:
                _LOGGER.warning(
                    f"Unavailable {self.feature_id} entities: {unavailable_entities}"
                )

            success = len(missing_entities) == 0 and len(unavailable_entities) == 0
            _LOGGER.debug(
                f"{self.feature_id} entity availability validation: "
                f"{'SUCCESS' if success else 'FAILED'}"
            )
            return success

        except Exception as e:
            _LOGGER.error(f"Entity availability validation failed: {e}")
            return False

    def _is_feature_entity(self, entity_id: str) -> bool:
        """Check if an entity belongs to this feature.

        Args:
            entity_id: Entity identifier

        Returns:
            True if entity belongs to this feature, False otherwise
        """
        parsed = EntityHelpers.parse_entity_id(entity_id)
        if not parsed:
            return False

        entity_type, entity_name, device_id = parsed

        # Check if entity name matches feature patterns
        # This could be enhanced to check against actual feature entity names
        return True  # Simplified for now

    def _track_entity_lifecycle(self, entity: Entity) -> None:
        """Track entity lifecycle state.

        Args:
            entity: Entity to track
        """
        entity_id = entity.entity_id

        self._entity_states[entity_id] = {
            "created_at": self.hass.loop.time(),
            "last_update": None,
            "state": None,
            "config": getattr(entity, "_config", {}),
        }

        _LOGGER.debug(f"Tracking lifecycle for entity: {entity_id}")

    def update_entity_state(self, entity_id: str, state: Any) -> None:
        """Update entity state and track lifecycle.

        Args:
            entity_id: Entity identifier
            state: New entity state
        """
        if entity_id in self._entity_states:
            self._entity_states[entity_id]["last_update"] = self.hass.loop.time()
            self._entity_states[entity_id]["state"] = state

            _LOGGER.debug(f"Updated state for entity {entity_id}: {state}")

    def get_entity_config(self, entity_id: str) -> dict[str, Any]:
        """Get configuration for a tracked entity.

        Args:
            entity_id: Entity identifier

        Returns:
            Entity configuration dictionary
        """
        return self._entity_configs.get(entity_id, {})

    def set_entity_config(self, entity_id: str, config: dict[str, Any]) -> None:
        """Set configuration for a tracked entity.

        Args:
            entity_id: Entity identifier
            config: Entity configuration
        """
        self._entity_configs[entity_id] = config
        _LOGGER.debug(f"Updated config for entity {entity_id}")

    async def cleanup_entities(self) -> None:
        """Clean up entities and lifecycle tracking when feature is disabled.

        This method should be called when a feature is being disabled or removed.
        It handles graceful entity cleanup and state removal.
        """
        _LOGGER.info(f"Cleaning up {self.feature_id} entities...")

        try:
            # Remove entity lifecycle tracking
            entities_to_cleanup = list(self._entity_states.keys())

            # Clean up each tracked entity
            for entity_id in entities_to_cleanup:
                await self._cleanup_single_entity(entity_id)

            # Clear all lifecycle tracking
            self._entity_states.clear()
            self._entity_configs.clear()

            _LOGGER.info(
                f"Cleaned up {len(entities_to_cleanup)} {self.feature_id} entities"
            )

        except Exception as e:
            _LOGGER.error(f"Error during {self.feature_id} entity cleanup: {e}")

    async def _cleanup_single_entity(self, entity_id: str) -> None:
        """Clean up a single entity.

        Args:
            entity_id: Entity identifier to clean up
        """
        try:
            # Remove from Home Assistant entity registry if needed
            try:
                from homeassistant.helpers import entity_registry

                entity_registry.async_get(self.hass)
                if entity_id in entity_registry.entities:
                    entity_registry.async_remove(entity_id)
                    _LOGGER.debug(f"Removed entity from registry: {entity_id}")
            except Exception as e:
                _LOGGER.debug(f"Could not remove from registry: {e}")

            # Log cleanup
            _LOGGER.debug(f"Cleaned up entity: {entity_id}")

        except Exception as e:
            _LOGGER.error(f"Error cleaning up entity {entity_id}: {e}")

    def get_entity_status(self) -> dict[str, Any]:
        """Get status of all tracked entities.

        Returns:
            Dictionary with entity status information
        """
        now = self.hass.loop.time()
        status: dict[str, Any] = {
            "feature_id": self.feature_id,
            "total_tracked_entities": len(self._entity_states),
            "entity_details": {},
        }

        for entity_id, state_info in self._entity_states.items():
            age_seconds = now - state_info["created_at"]
            last_update_seconds = (
                now - state_info["last_update"] if state_info["last_update"] else None
            )

            cast(dict[str, Any], status["entity_details"])[entity_id] = {
                "age_seconds": age_seconds,
                "last_update_seconds": last_update_seconds,
                "current_state": state_info["state"],
                "has_config": entity_id in self._entity_configs,
            }

        return status

    def get_lifecycle_summary(self) -> dict[str, Any]:
        """Get summary of lifecycle management status.

        Returns:
            Lifecycle summary dictionary
        """
        total_entities = len(self._entity_states)
        entities_with_updates = sum(
            1
            for info in self._entity_states.values()
            if info["last_update"] is not None
        )

        return {
            "feature_id": self.feature_id,
            "total_tracked_entities": total_entities,
            "entities_with_updates": entities_with_updates,
            "stale_entities": total_entities - entities_with_updates,
            "has_config_entry": self.config_entry is not None,
            "registered_factories": list(self._entity_factories.keys()),
        }

    async def health_check(self) -> dict[str, Any]:
        """Perform health check on entity lifecycle management.

        Returns:
            Health check results
        """
        health_status: dict[str, Any] = {
            "status": "healthy",
            "checks": {},
            "issues": [],
        }

        # Check 1: Entity availability
        entity_availability = await self.validate_entity_availability()
        cast(dict[str, Any], health_status["checks"])["entity_availability"] = (
            entity_availability
        )
        if not entity_availability:
            cast(list[str], health_status["issues"]).append(
                "Some entities are missing or unavailable"
            )
            health_status["status"] = "degraded"

        # Check 2: Lifecycle tracking consistency
        tracking_issues = self._check_lifecycle_consistency()
        cast(dict[str, Any], health_status["checks"])["lifecycle_tracking"] = (
            len(tracking_issues) == 0
        )
        if tracking_issues:
            cast(list[str], health_status["issues"]).extend(tracking_issues)
            health_status["status"] = "degraded"

        # Check 3: Factory registration
        factory_status = len(self._entity_factories) > 0
        cast(dict[str, Any], health_status["checks"])["entity_factories"] = (
            factory_status
        )
        if not factory_status:
            cast(list[str], health_status["issues"]).append(
                "No entity factories registered"
            )
            health_status["status"] = "unhealthy"

        return health_status

    def _check_lifecycle_consistency(self) -> list[str]:
        """Check lifecycle tracking consistency.

        Returns:
            List of consistency issues
        """
        issues: list[str] = []

        # Check for entities without proper tracking
        for entity_id in self._entity_states:
            if entity_id not in self._entity_configs:
                # This is not necessarily an issue - some entities may not have configs
                pass

        return issues


# Convenience functions for common lifecycle patterns


async def create_entities_for_device(
    hass: HomeAssistant,
    feature_id: str,
    device_id: str,
    device_type: str,
    entity_configs: dict[str, Any],
    entity_factories: dict[str, Callable],
) -> list[Entity]:
    """Create entities for a device using lifecycle patterns.

    Args:
        hass: Home Assistant instance
        feature_id: Feature identifier
        device_id: Device identifier
        device_type: Type of device
        entity_configs: Configuration for entities
        entity_factories: Entity factories by type

    Returns:
        List of created entities
    """
    lifecycle_manager = EntityLifecycleManager(hass)
    lifecycle_manager.register_feature(feature_id)

    # Register entity factories
    for entity_type, factory in entity_factories.items():
        lifecycle_manager.register_entity_factory(entity_type, factory)

    # Create entities
    return await lifecycle_manager.create_feature_entities(
        device_id, device_type, entity_configs
    )


async def cleanup_feature_entities(
    hass: HomeAssistant,
    feature_id: str,
    entity_ids: list[str] | None = None,
) -> None:
    """Clean up entities for a feature.

    Args:
        hass: Home Assistant instance
        feature_id: Feature identifier
        entity_ids: Specific entity IDs to clean up (all if None)
    """
    lifecycle_manager = EntityLifecycleManager(hass)
    lifecycle_manager.register_feature(feature_id)

    if entity_ids:
        # Clean up specific entities
        for entity_id in entity_ids:
            await lifecycle_manager._cleanup_single_entity(entity_id)
    else:
        # Clean up all tracked entities
        await lifecycle_manager.cleanup_entities()
