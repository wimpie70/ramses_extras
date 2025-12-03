"""Entity registry integration for Ramses Extras framework.

This module provides registry integration patterns for entity management,
extracting common registry operations from existing implementations
to enable consistent entity registration and lookup across features.
"""

import logging
from typing import Any, cast

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry

from .core import EntityHelpers

_LOGGER = logging.getLogger(__name__)


class EntityRegistryManager:
    """Manager for Home Assistant entity registry integration.

    This class provides centralized registry operations for entities,
    handling registration, lookup, validation, and cleanup of entities
    across all Ramses Extras features.
    """

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize entity registry manager.

        Args:
            hass: Home Assistant instance
        """
        self.hass = hass
        self._entity_registry = None
        self._feature_entities: dict[str, set[str]] = {}
        self._entity_configs: dict[str, dict[str, Any]] = {}

    def _get_registry(self) -> entity_registry.EntityRegistry:
        """Get the Home Assistant entity registry instance.

        Returns:
            Entity registry instance
        """
        if self._entity_registry is None:
            self._entity_registry = entity_registry.async_get(self.hass)
        return self._entity_registry

    def register_feature_entities(self, feature_id: str, entity_ids: list[str]) -> None:
        """Register a feature's entities for tracking.

        Args:
            feature_id: Feature identifier
            entity_ids: List of entity IDs that belong to this feature
        """
        self._feature_entities[feature_id] = set(entity_ids)
        _LOGGER.debug(
            f"Registered {len(entity_ids)} entities for feature '{feature_id}'"
        )

    def unregister_feature_entities(self, feature_id: str) -> None:
        """Unregister a feature's entities.

        Args:
            feature_id: Feature identifier
        """
        if feature_id in self._feature_entities:
            count = len(self._feature_entities[feature_id])
            del self._feature_entities[feature_id]
            _LOGGER.debug(f"Unregistered {count} entities for feature '{feature_id}'")

    def get_entity_registry_entry(self, entity_id: str) -> Any | None:
        """Get entity registry entry for an entity.

        Args:
            entity_id: Entity identifier

        Returns:
            Entity registry entry or None if not found
        """
        try:
            registry = self._get_registry()
            return registry.entities.get(entity_id)
        except Exception as e:
            _LOGGER.error(f"Failed to get registry entry for {entity_id}: {e}")
            return None

    def validate_entity_exists(self, entity_id: str) -> bool:
        """Validate that an entity exists in the registry.

        Args:
            entity_id: Entity identifier

        Returns:
            True if entity exists, False otherwise
        """
        try:
            registry_entry = self.get_entity_registry_entry(entity_id)
            return registry_entry is not None
        except Exception as e:
            _LOGGER.error(f"Entity validation failed for {entity_id}: {e}")
            return False

    def get_entities_for_feature(self, feature_id: str) -> list[str]:
        """Get all entity IDs registered for a feature.

        Args:
            feature_id: Feature identifier

        Returns:
            List of entity IDs for the feature
        """
        return list(self._feature_entities.get(feature_id, []))

    def get_all_feature_entities(self) -> dict[str, set[str]]:
        """Get all entities registered for all features.

        Returns:
            Dictionary mapping feature IDs to sets of entity IDs
        """
        return self._feature_entities.copy()

    def get_entity_config(self, entity_id: str) -> dict[str, Any]:
        """Get configuration for an entity.

        Args:
            entity_id: Entity identifier

        Returns:
            Entity configuration dictionary
        """
        return self._entity_configs.get(entity_id, {})

    def set_entity_config(self, entity_id: str, config: dict[str, Any]) -> None:
        """Set configuration for an entity.

        Args:
            entity_id: Entity identifier
            config: Entity configuration
        """
        self._entity_configs[entity_id] = config
        _LOGGER.debug(f"Set config for entity {entity_id}: {config}")

    async def validate_feature_entities(
        self, feature_id: str, expected_entities: list[str]
    ) -> dict[str, bool]:
        """Validate that all expected entities exist and are properly configured.

        Args:
            feature_id: Feature identifier
            expected_entities: List of expected entity IDs

        Returns:
            Dictionary mapping entity IDs to validation status
        """
        validation_results = {}

        for entity_id in expected_entities:
            try:
                # Check if entity exists in registry
                registry_entry = self.get_entity_registry_entry(entity_id)
                exists = registry_entry is not None

                # Check if entity has proper configuration
                has_config = entity_id in self._entity_configs

                # Check if entity state is available
                entity_state = self.hass.states.get(entity_id)
                state_available = (
                    entity_state is not None and entity_state.state != "unavailable"
                )

                # Overall validation status
                is_valid = exists and (has_config or state_available)
                validation_results[entity_id] = is_valid

                if not is_valid:
                    _LOGGER.warning(
                        f"Entity {entity_id} validation failed - "
                        f"exists: {exists}, has_config: {has_config}, "
                        f"state_available: {state_available}"
                    )

            except Exception as e:
                _LOGGER.error(f"Validation failed for entity {entity_id}: {e}")
                validation_results[entity_id] = False

        return validation_results

    async def cleanup_orphaned_entities(
        self, feature_id: str | None = None
    ) -> list[str]:
        """Clean up orphaned or invalid entities.

        Args:
            feature_id: Specific feature to clean up (None for all features)

        Returns:
            List of entity IDs that were cleaned up
        """
        cleaned_entities = []
        registry = self._get_registry()

        try:
            # Determine which entities to check
            entities_to_check = []
            if feature_id:
                entities_to_check = self.get_entities_for_feature(feature_id)
            else:
                # Check all feature entities
                for feature_entities in self._feature_entities.values():
                    entities_to_check.extend(feature_entities)

            _LOGGER.debug(f"Checking {len(entities_to_check)} entities for cleanup")

            # Check each entity
            for entity_id in entities_to_check:
                should_cleanup = await self._should_cleanup_entity(entity_id)
                if should_cleanup:
                    try:
                        registry.async_remove(entity_id)
                        cleaned_entities.append(entity_id)
                        _LOGGER.info(f"Cleaned up orphaned entity: {entity_id}")
                    except Exception as e:
                        _LOGGER.error(f"Failed to cleanup entity {entity_id}: {e}")

        except Exception as e:
            _LOGGER.error(f"Error during entity cleanup: {e}")

        return cleaned_entities

    async def _should_cleanup_entity(self, entity_id: str) -> bool:
        """Determine if an entity should be cleaned up.

        Args:
            entity_id: Entity identifier

        Returns:
            True if entity should be cleaned up, False otherwise
        """
        try:
            # Check if entity exists in registry
            registry_entry = self.get_entity_registry_entry(entity_id)
            if not registry_entry:
                return False  # Already gone

            # Check if entity state is unavailable for extended period
            # This is a simplified check - in practice you might want
            # more sophisticated logic
            entity_state = self.hass.states.get(entity_id)
            if entity_state and entity_state.state == "unavailable":
                # Could add timestamp checking here
                return True

            # Check if entity belongs to a disabled feature
            # This would require tracking feature enablement status
            # For now, we skip this check

            return False

        except Exception as e:
            _LOGGER.error(
                f"Error checking if entity {entity_id} should be cleaned up: {e}"
            )
            return False

    async def get_entity_statistics(self) -> dict[str, Any]:
        """Get statistics about entity registry usage.

        Returns:
            Dictionary with entity statistics
        """
        try:
            registry = self._get_registry()
            total_entities = len(registry.entities)

            # Count entities by feature
            feature_counts = {}
            for feature_id, entities in self._feature_entities.items():
                valid_count = 0
                for entity_id in entities:
                    if self.validate_entity_exists(entity_id):
                        valid_count += 1
                feature_counts[feature_id] = {
                    "registered": len(entities),
                    "valid": valid_count,
                    "invalid": len(entities) - valid_count,
                }

            # Count entities by domain
            domain_counts: dict[str, int] = {}
            for entity in registry.entities.values():
                domain = entity.domain
                domain_counts[domain] = domain_counts.get(domain, 0) + 1

            return {
                "total_entities_in_registry": total_entities,
                "total_feature_entities": sum(
                    len(entities) for entities in self._feature_entities.values()
                ),
                "feature_breakdown": feature_counts,
                "domain_breakdown": domain_counts,
                "tracked_features": list(self._feature_entities.keys()),
            }

        except Exception as e:
            _LOGGER.error(f"Error getting entity statistics: {e}")
            return {}

    def find_entities_by_pattern(
        self, patterns: list[str], feature_id: str | None = None
    ) -> list[str]:
        """Find entities matching given patterns.

        Args:
            patterns: List of patterns to match against entity IDs
            feature_id: Optional feature ID to limit search

        Returns:
            List of matching entity IDs
        """
        matching_entities = []

        # Get entities to search
        entities_to_search = []
        if feature_id:
            entities_to_search = self.get_entities_for_feature(feature_id)
        else:
            # Search all registered feature entities
            for feature_entities in self._feature_entities.values():
                entities_to_search.extend(feature_entities)

        # Apply patterns
        for entity_id in entities_to_search:
            for pattern in patterns:
                if self._entity_matches_pattern(entity_id, pattern):
                    matching_entities.append(entity_id)
                    break

        return matching_entities

    def _entity_matches_pattern(self, entity_id: str, pattern: str) -> bool:
        """Check if an entity ID matches a pattern.

        Args:
            entity_id: Entity identifier
            pattern: Pattern to match

        Returns:
            True if entity matches pattern, False otherwise
        """
        # Handle wildcard patterns
        if pattern.endswith("*"):
            prefix = pattern[:-1]
            return entity_id.startswith(prefix)
        if pattern.startswith("*"):
            suffix = pattern[1:]
            return entity_id.endswith(suffix)
        return entity_id == pattern

    async def migrate_entity_registry_data(
        self, old_entity_ids: list[str], new_entity_ids: list[str]
    ) -> bool:
        """Migrate entity registry data from old entity IDs to new ones.

        Args:
            old_entity_ids: List of old entity IDs
            new_entity_ids: List of new entity IDs (corresponding to old IDs)

        Returns:
            True if migration successful, False otherwise
        """
        if len(old_entity_ids) != len(new_entity_ids):
            _LOGGER.error("Old and new entity ID lists must have same length")
            return False

        try:
            registry = self._get_registry()
            success_count = 0

            for old_id, new_id in zip(old_entity_ids, new_entity_ids, strict=True):
                try:
                    # Get old registry entry
                    old_entry = self.get_entity_registry_entry(old_id)
                    if not old_entry:
                        _LOGGER.warning(f"Old entity {old_id} not found in registry")
                        continue

                    # Update entity ID in registry
                    registry.async_update_entity(old_id, new_entity_id=new_id)
                    success_count += 1

                    _LOGGER.info(f"Migrated entity: {old_id} -> {new_id}")

                except Exception as e:
                    _LOGGER.error(f"Failed to migrate entity {old_id}: {e}")

            success = success_count == len(old_entity_ids)
            _LOGGER.info(
                f"Entity migration {'SUCCESS' if success else 'PARTIAL'}: "
                f"{success_count}/{len(old_entity_ids)}"
            )
            return success

        except Exception as e:
            _LOGGER.error(f"Error during entity registry migration: {e}")
            return False

    def get_entity_device_mapping(self, entity_ids: list[str]) -> dict[str, str | None]:
        """Get device mapping for entities.

        Args:
            entity_ids: List of entity IDs

        Returns:
            Dictionary mapping entity IDs to device IDs
        """
        device_mapping = {}

        for entity_id in entity_ids:
            try:
                registry_entry = self.get_entity_registry_entry(entity_id)
                if registry_entry:
                    device_id = registry_entry.device_id
                    device_mapping[entity_id] = device_id
                else:
                    device_mapping[entity_id] = None
            except Exception as e:
                _LOGGER.error(f"Error getting device mapping for {entity_id}: {e}")
                device_mapping[entity_id] = None

        return device_mapping


# Convenience functions for common registry operations


async def register_feature_with_registry(
    hass: HomeAssistant,
    feature_id: str,
    entity_ids: list[str],
    config: dict[str, Any] | None = None,
) -> EntityRegistryManager:
    """Register a feature and its entities with the registry manager.

    Args:
        hass: Home Assistant instance
        feature_id: Feature identifier
        entity_ids: List of entity IDs for the feature
        config: Optional feature configuration

    Returns:
        EntityRegistryManager instance
    """
    registry_manager = EntityRegistryManager(hass)
    registry_manager.register_feature_entities(feature_id, entity_ids)

    # Set feature configuration if provided
    if config:
        for entity_id in entity_ids:
            registry_manager.set_entity_config(entity_id, config)

    return registry_manager


async def validate_and_cleanup_registry(
    hass: HomeAssistant, feature_id: str
) -> tuple[list[str], dict[str, bool]]:
    """Validate a feature's entities and clean up any orphaned ones.

    Args:
        hass: Home Assistant instance
        feature_id: Feature identifier

    Returns:
        Tuple of (cleaned_entities, validation_results)
    """
    registry_manager = EntityRegistryManager(hass)

    # Get feature entities
    entity_ids = registry_manager.get_entities_for_feature(feature_id)

    # Validate entities
    validation_results = await registry_manager.validate_feature_entities(
        feature_id, entity_ids
    )

    # Clean up orphaned entities
    cleaned_entities = await registry_manager.cleanup_orphaned_entities(feature_id)

    return cleaned_entities, validation_results


def get_entity_registry_summary(hass: HomeAssistant) -> dict[str, Any]:
    """Get a summary of the entity registry state.

    Args:
        hass: Home Assistant instance

    Returns:
        Entity registry summary
    """
    registry_manager = EntityRegistryManager(hass)
    return cast(
        dict[str, Any],
        hass.loop.run_until_complete(registry_manager.get_entity_statistics()),
    )
