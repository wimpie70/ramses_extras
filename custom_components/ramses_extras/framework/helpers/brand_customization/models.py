"""Model configuration management for Ramses Extras brand customization.

This module provides utilities for managing model-specific configurations,
extracting patterns from existing brand customizers to enable consistent
model detection and configuration handling.
"""

import logging
from typing import Any, Dict

from .detection import DefaultModelConfig, detect_brand_from_model

_LOGGER = logging.getLogger(__name__)


class ModelConfigManager:
    """Manager for model-specific configurations.

    This class handles model detection, configuration lookup,
    and fallback handling for brand-specific devices.
    """

    def __init__(self, brand_name: str) -> None:
        """Initialize model configuration manager.

        Args:
            brand_name: Brand identifier
        """
        self.brand_name = brand_name
        self.model_configs: dict[str, dict[str, Any]] = {}
        self._initialize_brand_configs()

    def _initialize_brand_configs(self) -> None:
        """Initialize brand-specific model configurations."""
        if self.brand_name == "orcon":
            self._init_orcon_configs()
        elif self.brand_name == "zehnder":
            self._init_zehnder_configs()
        else:
            # Generic or unknown brand - use defaults
            _LOGGER.debug(f"Using default configs for brand: {self.brand_name}")

    def _init_orcon_configs(self) -> None:
        """Initialize Orcon-specific model configurations."""
        # These would typically be loaded from a configuration file
        # For now, using the known configurations from the existing customizer
        orcon_configs = {
            "HRV200": {
                "max_fan_speed": 2,
                "humidity_range": (40, 70),
                "supported_modes": ["auto", "boost"],
                "special_entities": ["filter_timer"],
                "high_end_models": [],
            },
            "HRV300": {
                "max_fan_speed": 3,
                "humidity_range": (35, 75),
                "supported_modes": ["auto", "boost", "eco"],
                "special_entities": ["filter_timer", "boost_timer"],
                "high_end_models": ["HRV300"],
            },
            "HRV400": {
                "max_fan_speed": 4,
                "humidity_range": (30, 80),
                "supported_modes": ["auto", "boost", "eco"],
                "special_entities": ["filter_timer", "boost_timer", "eco_mode"],
                "high_end_models": ["HRV400"],
            },
        }

        self.model_configs.update(orcon_configs)

    def _init_zehnder_configs(self) -> None:
        """Initialize Zehnder-specific model configurations."""
        # These would typically be loaded from a configuration file
        # For now, using the known configurations from the existing customizer
        zehnder_configs = {
            "ComfoAir Q350": {
                "max_fan_speed": 3,
                "humidity_range": (40, 75),
                "supported_modes": ["auto", "boost"],
                "special_entities": ["filter_timer", "co2_sensor"],
                "high_end_models": [],
            },
            "ComfoAir Q450": {
                "max_fan_speed": 4,
                "humidity_range": (35, 80),
                "supported_modes": ["auto", "boost", "eco"],
                "special_entities": [
                    "filter_timer",
                    "co2_sensor",
                    "auto_mode",
                    "away_mode",
                ],
                "high_end_models": ["ComfoAir Q450"],
            },
            "ComfoAir Q600": {
                "max_fan_speed": 5,
                "humidity_range": (30, 85),
                "supported_modes": ["auto", "boost", "eco"],
                "special_entities": [
                    "filter_timer",
                    "co2_sensor",
                    "auto_mode",
                    "away_mode",
                ],
                "high_end_models": ["ComfoAir Q600"],
            },
        }

        self.model_configs.update(zehnder_configs)

    def get_model_config(self, model: str) -> dict[str, Any] | None:
        """Get configuration for a specific model.

        Args:
            model: Device model string

        Returns:
            Model configuration dictionary or None if not found
        """
        if not model:
            _LOGGER.debug("Model string is empty")
            return None

        # Try exact match first
        for model_key, config in self.model_configs.items():
            if model_key.upper() == model.upper():
                return self._create_model_config(model, model_key, config)

        # Try partial match
        model_upper = model.upper()
        for model_key, config in self.model_configs.items():
            if model_key.upper() in model_upper:
                return self._create_model_config(model, model_key, config)

        # No match found - return fallback configuration
        return self._create_fallback_config(model)

    def _create_model_config(
        self, model: str, model_key: str, config: dict[str, Any]
    ) -> dict[str, Any]:
        """Create a complete model configuration.

        Args:
            model: Original model string
            model_key: Matched model key
            config: Base configuration

        Returns:
            Complete model configuration
        """
        result = config.copy()
        result.update(
            {
                "model_key": model_key,
                "model_string": model,
                "brand": self.brand_name,
            }
        )

        _LOGGER.debug(f"Matched {self.brand_name} model: {model} -> {model_key}")
        return result

    def _create_fallback_config(self, model: str) -> dict[str, Any]:
        """Create fallback configuration for unknown models.

        Args:
            model: Unknown model string

        Returns:
            Fallback configuration
        """
        _LOGGER.warning(f"Unknown {self.brand_name} model variant: {model}")

        fallback_config = DefaultModelConfig.get_fallback_config(model, self.brand_name)
        fallback_config["model_key"] = "unknown"
        fallback_config["model_string"] = model
        fallback_config["brand"] = self.brand_name

        return fallback_config

    def register_model_config(self, model_key: str, config: dict[str, Any]) -> None:
        """Register a new model configuration.

        Args:
            model_key: Model key to register
            config: Model configuration
        """
        self.model_configs[model_key] = config
        _LOGGER.debug(f"Registered config for {self.brand_name} model: {model_key}")

    def get_all_model_keys(self) -> list[str]:
        """Get list of all registered model keys.

        Returns:
            List of model keys
        """
        return list(self.model_configs.keys())

    def has_model_config(self, model: str) -> bool:
        """Check if a model configuration exists.

        Args:
            model: Device model string

        Returns:
            True if configuration exists, False otherwise
        """
        return self.get_model_config(model) is not None

    def get_model_capabilities(self, model: str) -> dict[str, Any]:
        """Get capabilities for a model.

        Args:
            model: Device model string

        Returns:
            Model capabilities dictionary
        """
        config = self.get_model_config(model)
        if not config:
            return {}

        return {
            "max_fan_speed": config.get("max_fan_speed", 3),
            "supported_modes": config.get("supported_modes", ["auto"]),
            "humidity_range": config.get("humidity_range", (35, 75)),
            "special_entities": config.get("special_entities", []),
            "is_high_end": config.get("model_key") in config.get("high_end_models", []),
        }

    def compare_models(self, model1: str, model2: str) -> dict[str, Any]:
        """Compare two models and return differences.

        Args:
            model1: First model string
            model2: Second model string

        Returns:
            Comparison results dictionary
        """
        config1 = self.get_model_config(model1) or {}
        config2 = self.get_model_config(model2) or {}

        comparison = {
            "models": [model1, model2],
            "max_fan_speed": [
                config1.get("max_fan_speed"),
                config2.get("max_fan_speed"),
            ],
            "humidity_range": [
                config1.get("humidity_range"),
                config2.get("humidity_range"),
            ],
            "supported_modes": [
                config1.get("supported_modes"),
                config2.get("supported_modes"),
            ],
            "special_entities": [
                config1.get("special_entities"),
                config2.get("special_entities"),
            ],
        }

        # Calculate feature differences
        modes1 = set(config1.get("supported_modes", []))
        modes2 = set(config2.get("supported_modes", []))
        comparison["mode_differences"] = {
            "only_in_model1": list(modes1 - modes2),
            "only_in_model2": list(modes2 - modes1),
            "common": list(modes1 & modes2),
        }

        entities1 = set(config1.get("special_entities", []))
        entities2 = set(config2.get("special_entities", []))
        comparison["entity_differences"] = {
            "only_in_model1": list(entities1 - entities2),
            "only_in_model2": list(entities2 - entities1),
            "common": list(entities1 & entities2),
        }

        return comparison


def auto_detect_and_register_model(
    model: str, brand_name: str | None = None
) -> dict[str, Any]:
    """Automatically detect and register a model configuration.

    Args:
        model: Device model string
        brand_name: Optional brand identifier (auto-detected if not provided)

    Returns:
        Model configuration dictionary
    """
    # Auto-detect brand if not provided
    if brand_name is None:
        brand_name = detect_brand_from_model(model) or "generic"

    # Create manager and get config
    manager = ModelConfigManager(brand_name)
    config = manager.get_model_config(model)

    if config and config.get("model_key") != "unknown":
        _LOGGER.info(
            f"Auto-detected model: {model} -> {config['model_key']} ({brand_name})"
        )
    else:
        _LOGGER.info(f"Using fallback config for model: {model} ({brand_name})")

    return config or {}


def get_model_template(model_key: str, brand_name: str) -> dict[str, Any]:
    """Get a template configuration for a model key.

    Args:
        model_key: Model key
        brand_name: Brand identifier

    Returns:
        Template configuration dictionary
    """
    manager = ModelConfigManager(brand_name)
    return manager.model_configs.get(
        model_key, DefaultModelConfig.GENERIC_CONFIG.copy()
    )


def validate_model_config(config: dict[str, Any]) -> bool:
    """Validate a model configuration.

    Args:
        config: Model configuration to validate

    Returns:
        True if valid, False otherwise
    """
    required_fields = ["model_key", "model_string"]

    for field in required_fields:
        if field not in config:
            _LOGGER.error(f"Missing required field '{field}' in model config")
            return False

    # Validate numeric fields
    numeric_fields = ["max_fan_speed"]
    for field in numeric_fields:
        if field in config:
            try:
                float(config[field])
            except (ValueError, TypeError):
                _LOGGER.error(
                    f"Invalid numeric value for field '{field}': {config[field]}"
                )
                return False

    # Validate range fields
    range_fields = ["humidity_range"]
    for field in range_fields:
        if field in config:
            value = config[field]
            if not isinstance(value, (tuple, list)) or len(value) != 2:
                _LOGGER.error(f"Invalid range value for field '{field}': {value}")
                return False

    return True
