"""Core brand customization framework for Ramses Extras.

This module provides the base framework for brand-specific device customizations,
extracting common patterns from existing brand customizers to enable reuse
across features and future brand support.
"""

import logging
from typing import Any, cast

from homeassistant.core import HomeAssistant

from .detection import BrandPatterns, detect_brand_from_device
from .entities import EntityGenerationManager
from .models import DefaultModelConfig, ModelConfigManager

_LOGGER = logging.getLogger(__name__)


class ExtrasBrandCustomizer:
    """Base class for brand-specific device customizations.

    This class extracts common patterns from existing brand customizers
    and provides a framework for consistent brand-specific customization.
    """

    def __init__(self, hass: HomeAssistant, brand_name: str) -> None:
        """Initialize brand customizer.

        Args:
            hass: Home Assistant instance
            brand_name: Brand identifier (e.g., "orcon", "zehnder")
        """
        self.hass: HomeAssistant = hass
        self.brand_name: str = brand_name
        self.detected_devices: dict[str, Any] = {}
        self.model_config_manager = ModelConfigManager(brand_name)
        self.entity_manager = EntityGenerationManager(brand_name)

    async def customize_device(
        self, device: Any, event_data: dict[str, Any]
    ) -> dict[str, Any]:
        """Apply brand-specific customizations to device.

        This is the main entry point for applying brand customizations.
        Subclasses should override this method to call the specific
        customization methods as needed.

        Args:
            device: Device object with model property
            event_data: Event data to modify

        Returns:
            Modified event data dictionary
        """
        _LOGGER.debug(
            f"Applying {self.brand_name} customizations for device {device.id}"
        )

        # Extract model configuration
        model_info = self._extract_model_info(device.model)
        if not model_info:
            _LOGGER.warning(f"Unknown {self.brand_name} model: {device.model}")
            return event_data

        # Apply model-specific configuration
        event_data["model_config"] = model_info

        # Add brand-specific entities
        await self._add_brand_entities(device, event_data, model_info)

        # Configure brand-specific behaviors
        await self._configure_brand_behaviors(device, event_data, model_info)

        # Set brand-specific defaults
        await self._set_brand_defaults(event_data, model_info)

        _LOGGER.info(f"Applied {self.brand_name} customizations for device {device.id}")
        return event_data

    def _extract_model_info(self, model: str) -> dict[str, Any] | None:
        """Extract configuration from device model string.

        Args:
            model: Device model string

        Returns:
            Model configuration dictionary or None
        """
        if not model:
            return None

        return self.model_config_manager.get_model_config(model)

    async def _add_brand_entities(
        self, device: Any, event_data: dict[str, Any], model_info: dict[str, Any]
    ) -> None:
        """Add brand-specific entities to the event data.

        Args:
            device: Device object
            event_data: Event data to modify
            model_info: Model configuration information
        """
        device_id = device.id
        entities = event_data["entity_ids"]

        # Generate standard entities for this brand
        standard_entities = self.entity_manager.generate_standard_entities(
            device_id, model_info
        )
        entities.extend(standard_entities)

        # Generate model-specific entities
        special_entities = self.entity_manager.generate_special_entities(
            device_id, model_info
        )
        entities.extend(special_entities)

        # Generate high-end model entities
        if model_info["model_key"] in model_info.get("high_end_models", []):
            high_end_entities = self.entity_manager.generate_high_end_entities(
                device_id, model_info
            )
            entities.extend(high_end_entities)

        _LOGGER.info(
            f"Added {len(entities)} entities for {self.brand_name} device {device_id}"
        )

    async def _configure_brand_behaviors(
        self, device: Any, event_data: dict[str, Any], model_info: dict[str, Any]
    ) -> None:
        """Configure brand-specific behavior settings.

        Args:
            device: Device object
            event_data: Event data to modify
            model_info: Model configuration information
        """
        # Set brand-specific behavior configuration
        behavior_config = self._get_brand_behavior_config(model_info)
        event_data[f"{self.brand_name}_config"] = behavior_config

        # Configure fan speed levels
        max_speed = model_info.get("max_fan_speed", 3)
        behavior_config["fan_speed_levels"] = list(range(1, max_speed + 1))

        # Set mode-specific configurations
        mode_configs = self._get_mode_configs(model_info, max_speed)
        behavior_config["mode_configs"] = mode_configs

    async def _set_brand_defaults(
        self, event_data: dict[str, Any], model_info: dict[str, Any]
    ) -> None:
        """Set brand-specific default values.

        Args:
            event_data: Event data to modify
            model_info: Model configuration information
        """
        # Set brand-specific defaults
        defaults = self._get_brand_defaults(model_info)
        event_data[f"{self.brand_name}_defaults"] = defaults

        # Configure entity enablement
        entity_enablement = self._get_entity_enablement(
            event_data["device_id"], model_info
        )
        event_data["default_enabled_entities"] = entity_enablement

    def _get_brand_behavior_config(self, model_info: dict[str, Any]) -> dict[str, Any]:
        """Get brand-specific behavior configuration.

        Args:
            model_info: Model configuration information

        Returns:
            Behavior configuration dictionary
        """
        # Default configuration - should be overridden by subclasses
        return {
            "auto_mode_hysteresis": 5,
            "boost_trigger_humidity": 70,
            "eco_mode_humidity_offset": -5,
            "filter_replacement_interval": 8760,  # hours (1 year)
            "max_boost_duration": 120,  # minutes
        }

    def _get_mode_configs(
        self, model_info: dict[str, Any], max_speed: int
    ) -> dict[str, dict[str, Any]]:
        """Get mode-specific configurations.

        Args:
            model_info: Model configuration information
            max_speed: Maximum fan speed

        Returns:
            Mode configurations dictionary
        """
        # Default mode configurations - should be overridden by subclasses
        supported_modes = model_info.get("supported_modes", ["auto", "boost"])
        mode_configs = {}

        for mode in supported_modes:
            mode_configs[mode] = {
                "default_fan_speed": 2 if mode == "auto" else max_speed,
                "humidity_target_offset": 0 if mode == "auto" else -5,
                "duration_minutes": 0 if mode == "auto" else 30,
            }

        return mode_configs

    def _get_brand_defaults(self, model_info: dict[str, Any]) -> dict[str, Any]:
        """Get brand-specific default values.

        Args:
            model_info: Model configuration information

        Returns:
            Default values dictionary
        """
        # Default values - should be overridden by subclasses
        humidity_range = model_info.get("humidity_range", (35, 75))
        target_humidity = (humidity_range[0] + humidity_range[1]) // 2

        return {
            "target_humidity": target_humidity,
            "auto_mode_enabled": True,
            "filter_monitoring_enabled": True,
            "boost_timer_default": 30,  # minutes
            "eco_mode_humidity_offset": -5,
        }

    def _get_entity_enablement(
        self, device_id: str, model_info: dict[str, Any]
    ) -> dict[str, bool]:
        """Get brand-specific entity enablement configuration.

        Args:
            device_id: Device identifier
            model_info: Model configuration information

        Returns:
            Entity enablement dictionary
        """
        # Default entity enablement - should be overridden by subclasses
        return {
            f"{self.brand_name}_operation_mode": True,
            f"{self.brand_name}_target_humidity": True,
        }


class BrandCustomizerManager:
    """Manager for multiple brand customizers.

    This class provides a centralized way to manage and coordinate
    multiple brand customizers for different device types.
    """

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize brand customizer manager.

        Args:
            hass: Home Assistant instance
        """
        self.hass = hass
        self.customizers: dict[str, ExtrasBrandCustomizer] = {}

    def register_customizer(self, customizer: ExtrasBrandCustomizer) -> None:
        """Register a brand customizer.

        Args:
            customizer: Brand customizer to register
        """
        self.customizers[customizer.brand_name] = customizer
        _LOGGER.info(f"Registered {customizer.brand_name} brand customizer")

    async def customize_device(
        self, device: Any, event_data: dict[str, Any]
    ) -> dict[str, Any]:
        """Apply appropriate brand customizations to device.

        Args:
            device: Device object
            event_data: Event data to modify

        Returns:
            Modified event data dictionary
        """
        # Detect brand from device
        brand_name = detect_brand_from_device(device)
        if not brand_name:
            _LOGGER.debug(f"No brand detected for device {device.id}")
            return event_data

        # Get appropriate customizer
        customizer = self.customizers.get(brand_name)
        if not customizer:
            _LOGGER.warning(f"No customizer registered for brand: {brand_name}")
            return event_data

        # Apply brand customizations
        return await customizer.customize_device(device, event_data)

    def get_customizer(self, brand_name: str) -> ExtrasBrandCustomizer | None:
        """Get brand customizer by name.

        Args:
            brand_name: Brand identifier

        Returns:
            Brand customizer or None if not found
        """
        return self.customizers.get(brand_name)

    def get_registered_brands(self) -> list[str]:
        """Get list of registered brand names.

        Returns:
            List of registered brand names
        """
        return list(self.customizers.keys())
