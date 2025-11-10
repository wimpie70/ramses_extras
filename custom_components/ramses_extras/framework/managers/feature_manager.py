"""Feature Manager for Ramses Extras framework.

This module provides a centralized manager for all Ramses Extras features,
handling feature registration, lifecycle management, and coordination.
"""

import asyncio
import logging
from typing import Any

from homeassistant.core import HomeAssistant

from custom_components.ramses_extras.const import AVAILABLE_FEATURES
from custom_components.ramses_extras.framework import entity_registry

_LOGGER = logging.getLogger(__name__)


class FeatureManager:
    """Manages all Ramses Extras features in a centralized manner.

    The Feature Manager provides:
    - Feature registration and discovery
    - Feature lifecycle management
    - Feature coordination and communication
    - Resource management and cleanup
    """

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the feature manager.

        Args:
            hass: Home Assistant instance
        """
        self.hass = hass
        self._features: dict[str, Any] = {}
        self._feature_states: dict[str, str] = {}
        self._feature_dependencies: dict[str, list[str]] = {}
        self._active = False

        _LOGGER.info("FeatureManager initialized")

    def register_feature(self, feature_id: str, feature_instance: Any) -> None:
        """Register a feature with the manager.

        Args:
            feature_id: Unique identifier for the feature
            feature_instance: Instance of the feature
        """
        if feature_id in self._features:
            _LOGGER.warning(f"Feature {feature_id} already registered, overwriting")

        self._features[feature_id] = feature_instance
        self._feature_states[feature_id] = "registered"
        entity_registry.register_feature(feature_id)

        _LOGGER.info(f"Registered feature: {feature_id}")

    def unregister_feature(self, feature_id: str) -> None:
        """Unregister a feature from the manager.

        Args:
            feature_id: Identifier of the feature to unregister
        """
        if feature_id not in self._features:
            _LOGGER.warning(f"Feature {feature_id} not found for unregistration")
            return

        # Stop the feature if it's running
        if self._feature_states.get(feature_id) == "active":
            self.hass.async_create_task(self.stop_feature(feature_id))

        del self._features[feature_id]
        del self._feature_states[feature_id]

        _LOGGER.info(f"Unregistered feature: {feature_id}")

    def get_feature(self, feature_id: str) -> Any | None:
        """Get a registered feature instance.

        Args:
            feature_id: Feature identifier

        Returns:
            Feature instance or None if not found
        """
        return self._features.get(feature_id)

    def list_features(self) -> list[str]:
        """Get list of all registered feature IDs.

        Returns:
            List of feature IDs
        """
        return list(self._features.keys())

    def get_feature_state(self, feature_id: str) -> str | None:
        """Get the current state of a feature.

        Args:
            feature_id: Feature identifier

        Returns:
            Feature state or None if not found
        """
        return self._feature_states.get(feature_id)

    async def start_all_features(self) -> None:
        """Start all registered features.

        This method will start all features that have been registered
        and are not already active.
        """
        if self._active:
            _LOGGER.warning("FeatureManager already active")
            return

        _LOGGER.info("Starting all registered features")
        self._active = True

        # Start features in dependency order
        await self._start_features_by_dependency()

    async def start_feature(self, feature_id: str) -> bool:
        """Start a specific feature.

        Args:
            feature_id: Feature identifier

        Returns:
            True if feature started successfully, False otherwise
        """
        if feature_id not in self._features:
            _LOGGER.error(f"Feature {feature_id} not registered")
            return False

        if self._feature_states.get(feature_id) == "active":
            _LOGGER.warning(f"Feature {feature_id} already active")
            return True

        _LOGGER.info(f"Starting feature: {feature_id}")

        try:
            feature = self._features[feature_id]

            # Call start method if it exists
            if hasattr(feature, "start") and asyncio.iscoroutinefunction(feature.start):
                await feature.start()
            elif hasattr(feature, "start"):
                feature.start()

            self._feature_states[feature_id] = "active"
            _LOGGER.info(f"Feature {feature_id} started successfully")
            return True

        except Exception as e:
            _LOGGER.error(f"Failed to start feature {feature_id}: {e}")
            self._feature_states[feature_id] = "error"
            return False

    async def stop_feature(self, feature_id: str) -> bool:
        """Stop a specific feature.

        Args:
            feature_id: Feature identifier

        Returns:
            True if feature stopped successfully, False otherwise
        """
        if feature_id not in self._features:
            _LOGGER.error(f"Feature {feature_id} not registered")
            return False

        if self._feature_states.get(feature_id) != "active":
            _LOGGER.warning(f"Feature {feature_id} not active")
            return True

        _LOGGER.info(f"Stopping feature: {feature_id}")

        try:
            feature = self._features[feature_id]

            # Call stop method if it exists
            if hasattr(feature, "stop") and asyncio.iscoroutinefunction(feature.stop):
                await feature.stop()
            elif hasattr(feature, "stop"):
                feature.stop()

            self._feature_states[feature_id] = "stopped"
            _LOGGER.info(f"Feature {feature_id} stopped successfully")
            return True

        except Exception as e:
            _LOGGER.error(f"Failed to stop feature {feature_id}: {e}")
            return False

    async def stop_all_features(self) -> None:
        """Stop all active features."""
        if not self._active:
            return

        _LOGGER.info("Stopping all features")

        # Stop features in reverse dependency order
        for feature_id in reversed(self.list_features()):
            await self.stop_feature(feature_id)

        self._active = False
        _LOGGER.info("All features stopped")

    def set_feature_dependency(self, feature_id: str, depends_on: list[str]) -> None:
        """Set feature dependencies for proper startup order.

        Args:
            feature_id: Feature that has dependencies
            depends_on: List of feature IDs this feature depends on
        """
        self._feature_dependencies[feature_id] = depends_on
        _LOGGER.debug(f"Set dependencies for {feature_id}: {depends_on}")

    async def _start_features_by_dependency(self) -> None:
        """Start features in dependency order."""
        if not self._feature_dependencies:
            # No dependencies, start all features
            for feature_id in self._features:
                await self.start_feature(feature_id)
            return

        # Start features in dependency order
        started: set[str] = set()

        # Keep trying to start features until all are started or no progress made
        while len(started) < len(self._features):
            progress_made = False

            for feature_id, feature in self._features.items():
                if feature_id in started:
                    continue

                dependencies = self._feature_dependencies.get(feature_id, [])

                # Check if all dependencies are met
                if all(dep in started for dep in dependencies):
                    if await self.start_feature(feature_id):
                        started.add(feature_id)
                        progress_made = True

            if not progress_made:
                _LOGGER.warning(
                    "Could not resolve all feature dependencies, "
                    "starting remaining features"
                )
                break

    def get_features_by_type(self, feature_type: str) -> list[str]:
        """Get features by their type/category.

        Args:
            feature_type: Type of features to find

        Returns:
            List of feature IDs of the specified type
        """
        matching_features = []

        for feature_id in self._features:
            feature_config = AVAILABLE_FEATURES.get(feature_id, {})
            if feature_config.get("category") == feature_type:
                matching_features.append(feature_id)

        return matching_features

    def get_feature_statistics(self) -> dict[str, Any]:
        """Get statistics about registered features.

        Returns:
            Dictionary with feature statistics
        """
        states: dict[str, int] = {}
        for state in self._feature_states.values():
            states[state] = states.get(state, 0) + 1

        return {
            "total_features": len(self._features),
            "feature_states": states,
            "active": self._active,
            "feature_list": self.list_features(),
            "dependencies": self._feature_dependencies.copy(),
        }


# Global feature manager instance
_feature_manager: FeatureManager | None = None


def get_feature_manager(hass: HomeAssistant) -> FeatureManager:
    """Get the global feature manager instance.

    Args:
        hass: Home Assistant instance

    Returns:
        FeatureManager instance
    """
    global _feature_manager
    if _feature_manager is None:
        _feature_manager = FeatureManager(hass)
    return _feature_manager


def reset_feature_manager() -> None:
    """Reset the global feature manager instance (for testing)."""
    global _feature_manager
    _feature_manager = None


__all__ = [
    "FeatureManager",
    "get_feature_manager",
    "reset_feature_manager",
]
