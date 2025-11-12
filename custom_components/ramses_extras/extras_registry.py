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
        """Register device mappings."""
        with self._lock:
            self._device_mappings.update(mappings)

    def register_feature(self, feature_name: str) -> None:
        """Mark a feature as registered."""
        with self._lock:
            self._loaded_features.add(feature_name)

    def load_feature_definitions(
        self, feature_name: str, feature_module_path: str
    ) -> None:
        """Load entity definitions from a feature module
        (lazy loading to avoid circular imports)."""
        _LOGGER.info(
            f"🔍 Starting to load feature definitions for "
            f"'{feature_name}' from {feature_module_path}"
        )

        start_time = time.time()

        with self._lock:
            if feature_name in self._loaded_features:
                _LOGGER.info(f"✅ Feature '{feature_name}' already loaded, skipping")
                return  # Already loaded

            _LOGGER.info(f"🔄 Loading feature '{feature_name}'...")

            try:
                _LOGGER.info(f"📦 Attempting to import module: {feature_module_path}")
                # Import the feature module lazily to avoid circular imports
                feature_module = importlib.import_module(feature_module_path)
                _LOGGER.info(
                    f"✅ Successfully imported module for '{feature_name}' "
                    f"({time.time() - start_time:.2f}s)"
                )

                # Load feature's sensor configurations
                _LOGGER.info(f"🔍 Checking for sensor configs for '{feature_name}'...")
                sensor_key = f"{feature_name.upper()}_SENSOR_CONFIGS"
                if hasattr(feature_module, sensor_key):
                    _LOGGER.info(f"📡 Found sensor configs for '{feature_name}'")
                    sensor_configs = getattr(feature_module, sensor_key)
                    self._sensor_configs.update(sensor_configs)
                    _LOGGER.info(
                        f"📡 Loaded {len(sensor_configs)} sensor configs "
                        f"for '{feature_name}'"
                    )
                else:
                    _LOGGER.info(f"📡 No sensor configs found for '{feature_name}'")

                # Load feature's switch configurations
                _LOGGER.info(f"🔍 Checking for switch configs for '{feature_name}'...")
                switch_key = f"{feature_name.upper()}_SWITCH_CONFIGS"
                if hasattr(feature_module, switch_key):
                    _LOGGER.info(f"🔌 Found switch configs for '{feature_name}'")
                    switch_configs = getattr(feature_module, switch_key)
                    self._switch_configs.update(switch_configs)
                    _LOGGER.info(
                        f"🔌 Loaded {len(switch_configs)} switch configs "
                        f"for '{feature_name}'"
                    )
                else:
                    _LOGGER.info(f"🔌 No switch configs found for '{feature_name}'")

                # Load feature's number configurations
                _LOGGER.info(f"🔍 Checking for number configs for '{feature_name}'...")
                number_key = f"{feature_name.upper()}_NUMBER_CONFIGS"
                if hasattr(feature_module, number_key):
                    _LOGGER.info(f"🔢 Found number configs for '{feature_name}'")
                    number_configs = getattr(feature_module, number_key)
                    self._number_configs.update(number_configs)
                    _LOGGER.info(
                        f"🔢 Loaded {len(number_configs)} number configs "
                        f"for '{feature_name}'"
                    )
                else:
                    _LOGGER.info(f"🔢 No number configs found for '{feature_name}'")

                # Load feature's boolean configurations
                _LOGGER.info(f"🔍 Checking for boolean configs for '{feature_name}'...")
                boolean_key = f"{feature_name.upper()}_BOOLEAN_CONFIGS"
                if hasattr(feature_module, boolean_key):
                    _LOGGER.info(f"🔘 Found boolean configs for '{feature_name}'")
                    boolean_configs = getattr(feature_module, boolean_key)
                    self._boolean_configs.update(boolean_configs)
                    _LOGGER.info(
                        f"🔘 Loaded {len(boolean_configs)} boolean configs "
                        f"for '{feature_name}'"
                    )
                else:
                    _LOGGER.info(f"🔘 No boolean configs found for '{feature_name}'")

                # Load feature's device mappings
                _LOGGER.info(f"🔍 Checking for device mappings for '{feature_name}'...")
                mapping_key = f"{feature_name.upper()}_DEVICE_ENTITY_MAPPING"
                if hasattr(feature_module, mapping_key):
                    _LOGGER.info(f"🗺️ Found device mappings for '{feature_name}'")
                    device_mapping = getattr(feature_module, mapping_key)
                    self._device_mappings.update(device_mapping)
                    _LOGGER.info(f"🗺️ Loaded device mappings for '{feature_name}'")
                else:
                    _LOGGER.info(f"🗺️ No device mappings found for '{feature_name}'")

                self._loaded_features.add(feature_name)
                total_time = time.time() - start_time
                _LOGGER.info(
                    f"✅ Successfully loaded feature '{feature_name}' "
                    f"in {total_time:.2f}s"
                )

            except ImportError as e:
                _LOGGER.warning(f"⚠️  ImportError loading feature '{feature_name}': {e}")
            except Exception as e:
                _LOGGER.error(f"❌ Error loading feature '{feature_name}': {e}")
                _LOGGER.exception(f"Full exception details for '{feature_name}':")
            finally:
                total_time = time.time() - start_time
                if total_time > 5.0:
                    _LOGGER.warning(
                        f"⏰ Feature '{feature_name}' took {total_time:.2f}s to load!"
                    )

    def load_all_features(self, enabled_features: list[str]) -> None:
        """Load definitions from all enabled features (lazy loading).

        This method avoids circular imports by using lazy loading.
        """
        overall_start_time = time.time()
        _LOGGER.info(f"🚀 Starting to load all features: {enabled_features}")

        # FIXED: Remove the lock from load_all_features to avoid nested lock deadlock
        # The load_feature_definitions method already handles its own locking

        # Always load default feature definitions first
        if "default" not in self._loaded_features:
            _LOGGER.info("🔧 Loading default feature first...")
            self.load_feature_definitions(
                "default", "custom_components.ramses_extras.features.default"
            )
        else:
            _LOGGER.info("✅ Default feature already loaded")

        # Load each enabled feature
        _LOGGER.info(f"🔧 Loading {len(enabled_features)} enabled features...")
        for i, feature_name in enumerate(enabled_features):
            _LOGGER.info(
                f"🔄 Processing feature {i + 1}/{len(enabled_features)}: "
                f"'{feature_name}'"
            )

            if feature_name not in self._loaded_features:
                _LOGGER.info(f"📦 Loading feature: '{feature_name}'")
                feature_start_time = time.time()

                feature_module_path = (
                    f"custom_components.ramses_extras.features.{feature_name}"
                )
                self.load_feature_definitions(feature_name, feature_module_path)

                feature_time = time.time() - feature_start_time
                if feature_time > 2.0:
                    _LOGGER.warning(
                        f"⏰ Feature '{feature_name}' took {feature_time:.2f}s!"
                    )
            else:
                _LOGGER.info(f"✅ Feature '{feature_name}' already loaded, skipping")

        total_time = time.time() - overall_start_time
        _LOGGER.info(f"✅ Completed loading all features in {total_time:.2f}s")
        _LOGGER.info(f"📊 Loaded features: {list(self._loaded_features)}")

    def clear(self) -> None:
        """Clear all loaded definitions and reset state."""
        with self._lock:
            _LOGGER.info("🧹 Clearing EntityRegistry state...")
            self._sensor_configs.clear()
            self._switch_configs.clear()
            self._number_configs.clear()
            self._boolean_configs.clear()
            self._device_mappings.clear()
            self._loaded_features.clear()
            _LOGGER.info("✅ EntityRegistry state cleared")

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

    def clear_all(self) -> None:
        """Clear all configurations (useful for testing)."""
        with self._lock:
            self._sensor_configs.clear()
            self._switch_configs.clear()
            self._number_configs.clear()
            self._boolean_configs.clear()
            self._device_mappings.clear()
            self._loaded_features.clear()


# Global registry instance
extras_registry = RamsesEntityRegistry()
