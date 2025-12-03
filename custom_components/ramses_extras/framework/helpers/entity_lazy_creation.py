"""Lazy Entity Creation Manager - Generic patterns for selective entity creation."""

import logging
from typing import Any, Callable

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import Entity

_LOGGER = logging.getLogger(__name__)


class LazyEntityCreationManager:
    """Manages lazy entity creation based on device selection.

    This framework provides generic, reusable patterns for lazy entity creation
    that all features can use. Feature-specific entity creation logic should be
    implemented in the individual feature folders, not in this framework.
    """

    def __init__(self, hass: HomeAssistant):
        """Initialize lazy entity creation manager.

        Args:
            hass: Home Assistant instance
        """
        self.hass = hass
        self._pending_entities: dict[str, dict] = {}  # feature_id -> device_config
        self._entity_factories: dict[
            str, Callable
        ] = {}  # feature_id -> factory function
        self._creation_callbacks: dict[str, Callable] = {}  # feature_id -> callback

    async def register_feature_factory(
        self,
        feature_id: str,
        factory_func: Callable,
        creation_callback: Callable | None = None,
    ) -> None:
        """Register a feature's entity factory function.

        Args:
            feature_id: Feature identifier
            factory_func: Async function that creates entities for a device
                Format: async def factory(hass, config_entry, feature_id,
                 device_id) -> list[Entity]
            creation_callback: Optional callback after entity creation
                Format: async def callback(feature_id, device_id, created_entities)
        """
        self._entity_factories[feature_id] = factory_func
        if creation_callback:
            self._creation_callbacks[feature_id] = creation_callback
        _LOGGER.info(f"📦 Registered entity factory for feature: {feature_id}")

    async def create_entities_for_selection(
        self, feature_id: str, selected_devices: list[str], config_entry: ConfigEntry
    ) -> dict[str, list[Entity]]:
        """Create entities for selected devices only.

        Args:
            feature_id: Feature identifier
            selected_devices: List of device IDs to create entities for
            config_entry: Configuration entry for the integration

        Returns:
            Dictionary mapping device_id -> list of created entities
        """
        _LOGGER.info(
            f"🎯 Creating entities for {feature_id} on devices: {selected_devices}"
        )

        factory_func = self._entity_factories.get(feature_id)
        if not factory_func:
            _LOGGER.error(f"❌ No factory registered for feature: {feature_id}")
            return {}

        created_entities = {}

        for device_id in selected_devices:
            try:
                _LOGGER.info(
                    f"🔧 Creating entities for {feature_id} on device: {device_id}"
                )

                # Call feature-specific factory function
                device_entities = await factory_func(
                    self.hass, config_entry, feature_id, device_id
                )

                if device_entities:
                    created_entities[device_id] = device_entities
                    _LOGGER.info(
                        f"✅ Created {len(device_entities)} entities for {device_id}"
                    )

                    # Call creation callback if registered
                    creation_callback = self._creation_callbacks.get(feature_id)
                    if creation_callback:
                        await creation_callback(feature_id, device_id, device_entities)

            except Exception as e:
                _LOGGER.error(
                    f"❌ Failed to create entities for {feature_id} on {device_id}: {e}"
                )

        total_entities = sum(len(entities) for entities in created_entities.values())
        _LOGGER.info(
            f"🎯 Entity creation complete: {total_entities} entities across "
            f"{len(created_entities)} devices"
        )

        return created_entities

    async def remove_entities_for_unselected(
        self, feature_id: str, unselected_devices: list[str]
    ) -> None:
        """Remove entities for devices no longer selected.

        Args:
            feature_id: Feature identifier
            unselected_devices: List of device IDs to remove entities for
        """
        _LOGGER.info(
            f"🗑️ Removing entities for {feature_id} from unselected devices: "
            f"{unselected_devices}"
        )

        for device_id in unselected_devices:
            try:
                # Find and remove entities for this device
                entities_removed = await self._remove_device_entities(
                    feature_id, device_id
                )
                if entities_removed > 0:
                    _LOGGER.info(
                        f"🗑️ Removed {entities_removed} entities for {device_id}"
                    )

            except Exception as e:
                _LOGGER.error(
                    f"❌ Failed to remove entities for {feature_id} on {device_id}: {e}"
                )

    async def _remove_device_entities(self, feature_id: str, device_id: str) -> int:
        """Remove entities for a specific device.

        Args:
            feature_id: Feature identifier
            device_id: Device ID to remove entities for

        Returns:
            Number of entities removed
        """
        # This is a framework method - feature-specific logic should be in features
        # For now, we'll provide a generic implementation that can be extended

        entities_removed = 0
        entity_registry = self.hass.data.get("entity_registry")

        if not entity_registry:
            _LOGGER.warning("⚠️ Entity registry not available for cleanup")
            return 0

        try:
            # Get all entities and filter by feature and device
            for entity_entry in entity_registry.entities.values():
                if self._is_feature_entity(entity_entry, feature_id, device_id):
                    entity_registry.async_remove(entity_entry.entity_id)
                    entities_removed += 1

        except Exception as e:
            _LOGGER.error(f"❌ Error during entity removal: {e}")

        return entities_removed

    def _is_feature_entity(
        self, entity_entry: Any, feature_id: str, device_id: str
    ) -> bool:
        """Check if an entity belongs to a specific feature and device.

        This is a framework-level check. Features should implement their own
        more specific entity identification logic.

        Args:
            entity_entry: Entity registry entry
            feature_id: Feature identifier
            device_id: Device ID

        Returns:
            True if entity belongs to the feature and device
        """
        # Generic pattern: check entity_id contains feature and device identifiers
        entity_id = entity_entry.entity_id.lower()
        device_id_normalized = device_id.replace(":", "_").replace("-", "_")

        # Framework features should use consistent naming patterns
        return feature_id in entity_id and device_id_normalized in entity_id

    async def get_device_entity_status(
        self, feature_id: str, device_id: str
    ) -> dict[str, Any]:
        """Get status of entities for a specific feature and device.

        Args:
            feature_id: Feature identifier
            device_id: Device ID

        Returns:
            Dictionary with entity status information
        """
        entity_registry = self.hass.data.get("entity_registry")
        if not entity_registry:
            return {"exists": False, "entities": []}

        entities = []
        for entity_entry in entity_registry.entities.values():
            if self._is_feature_entity(entity_entry, feature_id, device_id):
                entities.append(
                    {
                        "entity_id": entity_entry.entity_id,
                        "domain": entity_entry.domain,
                        "unique_id": entity_entry.unique_id,
                    }
                )

        return {
            "exists": len(entities) > 0,
            "entities": entities,
            "count": len(entities),
        }

    def get_pending_configuration(self) -> dict[str, dict]:
        """Get pending entity configurations for all features.

        Returns:
            Dictionary mapping feature_id -> pending configuration
        """
        return self._pending_entities.copy()

    async def cleanup_stale_entities(self) -> int:
        """Clean up entities that no longer have valid configurations.

        Returns:
            Number of entities cleaned up
        """
        _LOGGER.info("🧹 Starting cleanup of stale entities")

        cleaned_entities = 0
        entity_registry = self.hass.data.get("entity_registry")

        if not entity_registry:
            _LOGGER.warning("⚠️ Entity registry not available for cleanup")
            return 0

        try:
            for entity_entry in list(entity_registry.entities.values()):
                if await self._is_entity_stale(entity_entry):
                    entity_registry.async_remove(entity_entry.entity_id)
                    cleaned_entities += 1

        except Exception as e:
            _LOGGER.error(f"❌ Error during stale entity cleanup: {e}")

        if cleaned_entities > 0:
            _LOGGER.info(f"🧹 Cleaned up {cleaned_entities} stale entities")
        else:
            _LOGGER.info("🧹 No stale entities found")

        return cleaned_entities

    async def _is_entity_stale(self, entity_entry: Any) -> bool:
        """Check if an entity is stale (no longer valid).

        Args:
            entity_entry: Entity registry entry

        Returns:
            True if entity is stale
        """
        # This is a framework-level check
        # Features should implement their own stale detection logic
        # For now, we'll mark entities as stale if they belong to disabled features

        # Extract feature_id from entity_id (framework convention)
        entity_id = entity_entry.entity_id.lower()

        # Check if this looks like a Ramses Extras entity
        if "ramses_extras" not in entity_id:
            return False

        # If we can't determine the feature, don't remove it
        feature_id = self._extract_feature_id(entity_id)
        if not feature_id:
            return False

        # Check if feature is currently enabled (this would require
        # feature registry access)
        # For now, we'll be conservative and not remove unknown entities
        return False

    def _extract_feature_id(self, entity_id: str) -> str | None:
        """Extract feature ID from entity ID.

        Args:
            entity_id: Entity ID to parse

        Returns:
            Feature ID or None if not found
        """
        # Framework convention: entity IDs should contain feature identifiers
        # This is a generic implementation - features can override this
        parts = entity_id.split(".")
        if len(parts) >= 2:
            domain = parts[0]  # noqa: F841
            name_parts = parts[1].split("_")

            # Look for known feature patterns
            if "hello_world" in name_parts:
                return "hello_world_card"
            if "humidity" in name_parts:
                return "humidity_control"
            if "hvac" in name_parts:
                return "hvac_fan_card"

        return None


# Utility functions for framework consumers
async def create_lazy_entity_manager(hass: HomeAssistant) -> LazyEntityCreationManager:
    """Create a lazy entity creation manager instance.

    This is the preferred way to create LazyEntityCreationManager instances
    to ensure consistent initialization.

    Args:
        hass: Home Assistant instance

    Returns:
        LazyEntityCreationManager instance
    """
    return LazyEntityCreationManager(hass)
