"""Framework entity registry - aggregates definitions from all features."""

import importlib
from typing import Any


class EntityDefinitionRegistry:
    """Aggregates entity definitions from all enabled features."""

    def __init__(self) -> None:
        self._sensor_configs: dict[str, dict[str, Any]] = {}
        self._switch_configs: dict[str, dict[str, Any]] = {}
        self._number_configs: dict[str, dict[str, Any]] = {}
        self._boolean_configs: dict[str, dict[str, Any]] = {}
        self._device_mappings: dict[str, dict[str, Any]] = {}

    def load_feature_definitions(
        self, feature_name: str, feature_module_path: str
    ) -> None:
        """Load entity definitions from a feature module."""
        try:
            # Import the feature module
            feature_module = importlib.import_module(feature_module_path)

            # Load feature's sensor configurations
            sensor_key = f"{feature_name.upper()}_SENSOR_CONFIGS"
            if hasattr(feature_module, sensor_key):
                sensor_configs = getattr(feature_module, sensor_key)
                self._sensor_configs.update(sensor_configs)

            # Load feature's switch configurations
            switch_key = f"{feature_name.upper()}_SWITCH_CONFIGS"
            if hasattr(feature_module, switch_key):
                switch_configs = getattr(feature_module, switch_key)
                self._switch_configs.update(switch_configs)

            # Load feature's number configurations
            number_key = f"{feature_name.upper()}_NUMBER_CONFIGS"
            if hasattr(feature_module, number_key):
                number_configs = getattr(feature_module, number_key)
                self._number_configs.update(number_configs)

            # Load feature's boolean configurations
            boolean_key = f"{feature_name.upper()}_BOOLEAN_CONFIGS"
            if hasattr(feature_module, boolean_key):
                boolean_configs = getattr(feature_module, boolean_key)
                self._boolean_configs.update(boolean_configs)

            # Load feature's device mappings
            mapping_key = f"{feature_name.upper()}_DEVICE_ENTITY_MAPPING"
            if hasattr(feature_module, mapping_key):
                device_mapping = getattr(feature_module, mapping_key)
                self._device_mappings.update(device_mapping)

        except ImportError:
            # Feature module not available or not loaded
            pass

    def load_all_features(self, enabled_features: list[str]) -> None:
        """Load definitions from all enabled features."""
        # Always load default feature definitions first
        self.load_feature_definitions(
            "default", "custom_components.ramses_extras.features.default"
        )

        # Load each enabled feature
        for feature_name in enabled_features:
            feature_module_path = (
                f"custom_components.ramses_extras.features.{feature_name}"
            )
            self.load_feature_definitions(feature_name, feature_module_path)

    def get_all_sensor_configs(self) -> dict[str, dict[str, Any]]:
        """Get all sensor configurations."""
        return self._sensor_configs.copy()

    def get_all_switch_configs(self) -> dict[str, dict[str, Any]]:
        """Get all switch configurations."""
        return self._switch_configs.copy()

    def get_all_number_configs(self) -> dict[str, dict[str, Any]]:
        """Get all number configurations."""
        return self._number_configs.copy()

    def get_all_boolean_configs(self) -> dict[str, dict[str, Any]]:
        """Get all boolean configurations."""
        return self._boolean_configs.copy()

    def get_all_device_mappings(self) -> dict[str, dict[str, Any]]:
        """Get all device to entity mappings."""
        return self._device_mappings.copy()


# Global registry instance
entity_registry = EntityDefinitionRegistry()
