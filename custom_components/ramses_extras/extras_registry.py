"""Standalone EntityRegistry - no package dependencies with auto-import."""

import importlib
import logging
import threading
import time
from typing import Any

_LOGGER = logging.getLogger(__name__)


class RamsesEntityRegistry:
    """Standalone entity registry for Ramses Extras features."""

    def __init__(self) -> None:
        self._sensor_configs: dict[str, dict[str, Any]] = {}
        self._switch_configs: dict[str, dict[str, Any]] = {}
        self._number_configs: dict[str, dict[str, Any]] = {}
        self._boolean_configs: dict[str, dict[str, Any]] = {}
        self._device_mappings: dict[str, dict[str, Any]] = {}
        self._card_configs: dict[str, dict[str, Any]] = {}
        self._websocket_commands: dict[str, dict[str, str]] = {}
        self._lock = threading.Lock()
        self._loaded_features: set[str] = set()

    def register_sensor_configs(self, configs: dict[str, dict[str, Any]]) -> None:
        """Register sensor configurations."""
        with self._lock:
            self._sensor_configs.update(configs)

    def register_switch_configs(self, configs: dict[str, dict[str, Any]]) -> None:
        """Register switch configurations."""
        with self._lock:
            self._switch_configs.update(configs)

    def register_number_configs(self, configs: dict[str, dict[str, Any]]) -> None:
        """Register number configurations."""
        with self._lock:
            self._number_configs.update(configs)

    def register_boolean_configs(self, configs: dict[str, dict[str, Any]]) -> None:
        """Register boolean configurations."""
        with self._lock:
            self._boolean_configs.update(configs)

    def register_device_mappings(self, mappings: dict[str, dict[str, Any]]) -> None:
        """Register device mappings, merging entity lists for each device type."""
        with self._lock:
            for device_type, entity_mapping in mappings.items():
                if device_type not in self._device_mappings:
                    # New device type, just add it
                    self._device_mappings[device_type] = entity_mapping.copy()
                else:
                    # Device type exists, merge the entity lists
                    existing_mapping = self._device_mappings[device_type]
                    for entity_type, entities in entity_mapping.items():
                        if entity_type not in existing_mapping:
                            existing_mapping[entity_type] = entities.copy()
                        else:
                            # Merge entity lists, avoiding duplicates
                            existing_entities = existing_mapping[entity_type]
                            for entity in entities:
                                if entity not in existing_entities:
                                    existing_entities.append(entity)

    def register_card_config(
        self, feature_name: str, card_config: dict[str, Any]
    ) -> None:
        """Register card configuration for a feature."""
        with self._lock:
            self._card_configs[feature_name] = card_config

    def register_feature(self, feature_name: str) -> None:
        """Mark a feature as registered."""
        with self._lock:
            self._loaded_features.add(feature_name)

    def register_websocket_commands(
        self, feature_name: str, commands: dict[str, str]
    ) -> None:
        """Register WebSocket command metadata for a feature."""
        with self._lock:
            self._websocket_commands[feature_name] = dict(commands)

    def load_feature_definitions(
        self, feature_name: str, feature_module_path: str
    ) -> None:
        """Load entity definitions from a feature module
        (lazy loading to avoid circular imports)."""
        _LOGGER.debug(f"Loading feature '{feature_name}'...")

        start_time = time.time()

        with self._lock:
            if feature_name in self._loaded_features:
                _LOGGER.debug(f"Feature '{feature_name}' already loaded, skipping")
                return  # Already loaded

            _LOGGER.debug(f"Loading feature '{feature_name}'...")

            try:
                # Import the feature module lazily to avoid circular imports
                feature_module_path = (
                    f"custom_components.ramses_extras.features.{feature_name}.const"
                )
                feature_module = importlib.import_module(feature_module_path)

                # Load feature's sensor configurations
                sensor_key = f"{feature_name.upper()}_SENSOR_CONFIGS"
                if hasattr(feature_module, sensor_key):
                    sensor_configs = getattr(feature_module, sensor_key)
                    self._sensor_configs.update(sensor_configs)
                    _LOGGER.debug(
                        f"Loaded {len(sensor_configs)} sensor configs "
                        f"for '{feature_name}'"
                    )

                # Load feature's switch configurations
                switch_key = f"{feature_name.upper()}_SWITCH_CONFIGS"
                if hasattr(feature_module, switch_key):
                    switch_configs = getattr(feature_module, switch_key)
                    self._switch_configs.update(switch_configs)
                    _LOGGER.debug(
                        f"Loaded {len(switch_configs)} switch configs "
                        f"for '{feature_name}'"
                    )

                # Load feature's number configurations
                number_key = f"{feature_name.upper()}_NUMBER_CONFIGS"
                if hasattr(feature_module, number_key):
                    number_configs = getattr(feature_module, number_key)
                    self._number_configs.update(number_configs)
                    _LOGGER.debug(
                        f"Loaded {len(number_configs)} number configs "
                        f"for '{feature_name}'"
                    )

                # Load feature's boolean configurations
                boolean_key = f"{feature_name.upper()}_BOOLEAN_CONFIGS"
                if hasattr(feature_module, boolean_key):
                    boolean_configs = getattr(feature_module, boolean_key)
                    self._boolean_configs.update(boolean_configs)
                    _LOGGER.debug(
                        f"Loaded {len(boolean_configs)} boolean configs "
                        f"for '{feature_name}'"
                    )

                # Load feature's device mappings
                mapping_key = f"{feature_name.upper()}_DEVICE_ENTITY_MAPPING"
                if hasattr(feature_module, mapping_key):
                    device_mapping = getattr(feature_module, mapping_key)
                    self._device_mappings.update(device_mapping)
                    _LOGGER.debug(f"Loaded device mappings for '{feature_name}'")

                # Load feature's card configuration
                card_config_key = f"{feature_name.upper()}_CARD_CONFIG"
                if hasattr(feature_module, card_config_key):
                    card_config = getattr(feature_module, card_config_key)
                    self._card_configs[feature_name] = card_config
                    _LOGGER.debug(f"Loaded card configuration for '{feature_name}'")

                # Load feature's WebSocket commands
                websocket_key = f"{feature_name.upper()}_WEBSOCKET_COMMANDS"
                if hasattr(feature_module, websocket_key):
                    websocket_commands = getattr(feature_module, websocket_key)
                    self._websocket_commands[feature_name] = websocket_commands
                    _LOGGER.info(
                        f"Loaded {len(websocket_commands)} WebSocket commands "
                        f"for '{feature_name}': {list(websocket_commands.keys())}"
                    )
                else:
                    _LOGGER.debug(
                        f"No WebSocket commands found for '{feature_name}' "
                        f"(key: {websocket_key})"
                    )

                self._loaded_features.add(feature_name)
                total_time = time.time() - start_time
                _LOGGER.debug(
                    f"Successfully loaded feature '{feature_name}' in {total_time:.2f}s"
                )

            except ImportError as e:
                _LOGGER.warning(f"ImportError loading feature '{feature_name}': {e}")
            except Exception as e:
                _LOGGER.error(f"Error loading feature '{feature_name}': {e}")
                _LOGGER.exception(f"Full exception details for '{feature_name}':")
            finally:
                total_time = time.time() - start_time
                if total_time > 5.0:
                    _LOGGER.warning(
                        f"Feature '{feature_name}' took {total_time:.2f}s to load!"
                    )

    def load_all_features(self, enabled_features: list[str]) -> None:
        """Load definitions from all enabled features (lazy loading).

        This method avoids circular imports by using lazy loading.
        """
        overall_start_time = time.time()
        _LOGGER.debug(f"Starting to load all features: {enabled_features}")

        # FIXED: Remove the lock from load_all_features to avoid nested lock deadlock
        # The load_feature_definitions method already handles its own locking

        # Always load default feature definitions first
        if "default" not in self._loaded_features:
            _LOGGER.debug("Loading default feature first...")
            self.load_feature_definitions(
                "default", "custom_components.ramses_extras.features.default"
            )
        else:
            _LOGGER.debug("Default feature already loaded")

        # Load each enabled feature
        _LOGGER.debug(f"Loading {len(enabled_features)} enabled features...")
        for i, feature_name in enumerate(enabled_features):
            _LOGGER.debug(
                f"Processing feature {i + 1}/{len(enabled_features)}: '{feature_name}'"
            )

            if feature_name not in self._loaded_features:
                _LOGGER.debug(f"Loading feature: '{feature_name}'")
                feature_start_time = time.time()

                feature_module_path = (
                    f"custom_components.ramses_extras.features.{feature_name}"
                )
                self.load_feature_definitions(feature_name, feature_module_path)

                feature_time = time.time() - feature_start_time
                if feature_time > 2.0:
                    _LOGGER.warning(
                        f"Feature '{feature_name}' took {feature_time:.2f}s to load!"
                    )
            else:
                _LOGGER.debug(f"Feature '{feature_name}' already loaded, skipping")

        total_time = time.time() - overall_start_time
        _LOGGER.debug(f"Completed loading all features in {total_time:.2f}s")
        _LOGGER.debug(f"Loaded features: {list(self._loaded_features)}")

    def clear(self) -> None:
        """Clear all loaded definitions and reset state."""
        with self._lock:
            _LOGGER.debug("Clearing EntityRegistry state...")
            self._sensor_configs.clear()
            self._switch_configs.clear()
            self._number_configs.clear()
            self._boolean_configs.clear()
            self._device_mappings.clear()
            self._card_configs.clear()
            self._websocket_commands.clear()
            self._loaded_features.clear()
            _LOGGER.debug("EntityRegistry state cleared")

    def get_all_sensor_configs(self) -> dict[str, dict[str, Any]]:
        """Get all sensor configurations."""
        with self._lock:
            return self._sensor_configs.copy()

    def get_all_switch_configs(self) -> dict[str, dict[str, Any]]:
        """Get all switch configurations."""
        with self._lock:
            return self._switch_configs.copy()

    def get_all_number_configs(self) -> dict[str, dict[str, Any]]:
        """Get all number configurations."""
        with self._lock:
            return self._number_configs.copy()

    def get_all_boolean_configs(self) -> dict[str, dict[str, Any]]:
        """Get all boolean configurations."""
        with self._lock:
            return self._boolean_configs.copy()

    def get_all_device_mappings(self) -> dict[str, dict[str, Any]]:
        """Get all device to entity mappings."""
        with self._lock:
            return self._device_mappings.copy()

    def get_loaded_features(self) -> list[str]:
        """Get list of loaded features."""
        with self._lock:
            return list(self._loaded_features)

    def get_card_config(self, feature_name: str) -> dict[str, Any] | None:
        """Get card configuration for a specific feature."""
        with self._lock:
            return self._card_configs.get(feature_name)

    def get_all_card_configs(self) -> dict[str, dict[str, Any]]:
        """Get all card configurations."""
        with self._lock:
            return self._card_configs.copy()

    def get_websocket_commands_for_feature(self, feature_name: str) -> dict[str, str]:
        """Get WebSocket command metadata for a feature."""
        with self._lock:
            return self._websocket_commands.get(feature_name, {}).copy()

    def get_all_websocket_commands(self) -> dict[str, dict[str, str]]:
        """Get WebSocket command metadata for all features."""
        with self._lock:
            return {
                name: commands.copy()
                for name, commands in self._websocket_commands.items()
            }

    def get_features_with_websocket_commands(self) -> list[str]:
        """List features that expose WebSocket commands."""
        with self._lock:
            return [
                feature_name
                for feature_name, commands in self._websocket_commands.items()
                if commands
            ]

    def clear_all(self) -> None:
        """Clear all configurations (useful for testing)."""
        with self._lock:
            self._sensor_configs.clear()
            self._switch_configs.clear()
            self._number_configs.clear()
            self._boolean_configs.clear()
            self._device_mappings.clear()
            self._card_configs.clear()
            self._loaded_features.clear()


# Global registry instance
extras_registry = RamsesEntityRegistry()
