"""Humidity Control Feature.

This module provides humidity control functionality including automation,
services, entities, and configuration specific to humidity management.

Updated to include platform exports for clean separation of HA integration
and feature-specific business logic. Includes Enhanced Device Discovery Architecture
support for event-driven device discovery and brand-specific customizations.

Brand-specific customizations are handled within this feature for self-containment.
"""

import logging
from typing import Any, cast

from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import (
    async_dispatcher_connect,
    async_dispatcher_send,
)

from custom_components.ramses_extras.const import EVENT_DEVICE_READY_FOR_ENTITIES

from .automation import HumidityAutomationManager
from .config import HumidityConfig
from .const import (
    ENHANCED_HUMIDITY_BOOLEAN_CONFIGS,
    ENHANCED_HUMIDITY_NUMBER_CONFIGS,
    ENHANCED_HUMIDITY_SWITCH_CONFIGS,
    HUMIDITY_BOOLEAN_CONFIGS,
    HUMIDITY_DEVICE_ENTITY_MAPPING,
    HUMIDITY_NUMBER_CONFIGS,
    HUMIDITY_SWITCH_CONFIGS,
    ORCON_DEVICE_MODELS,
    ZEHNDER_DEVICE_MODELS,
)
from .entities import HumidityEntities

# Import platform classes for HA integration
from .platforms import (
    HumidityControlBinarySensor,
    HumidityControlNumber,
    HumidityControlSwitch,
    binary_sensor_async_setup_entry,
    create_humidity_control_binary_sensor,
    create_humidity_number,
    create_humidity_sensor,
    create_humidity_switch,
    number_async_setup_entry,
    sensor_async_setup_entry,
    switch_async_setup_entry,
)
from .services import HumidityServices

_LOGGER = logging.getLogger(__name__)


# Feature-specific brand customizers are now defined in const.py


class OrconDeviceCustomizer:
    """Handle Orcon-specific device customizations for humidity control."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the Orcon device customizer.

        Args:
            hass: Home Assistant instance
        """
        self.hass: HomeAssistant = hass
        self.detected_devices: dict[str, Any] = {}

    async def customize_orcon_device(
        self, device: Any, event_data: dict[str, Any]
    ) -> dict[str, Any]:
        """Apply Orcon-specific customizations to device.

        Args:
            device: Device object with model property
            event_data: Event data to modify

        Returns:
            Modified event data dictionary
        """
        model_info = self._extract_orcon_model_info(device.model)

        if not model_info:
            _LOGGER.warning("Unknown Orcon model: %s", device.model)
            return event_data

        # Apply model-specific configuration
        event_data["model_config"] = model_info

        # Add Orcon-specific entities
        await self._add_orcon_entities(device, event_data, model_info)

        # Configure Orcon-specific behaviors
        await self._configure_orcon_behaviors(device, event_data, model_info)

        # Set Orcon-specific defaults
        await self._set_orcon_defaults(event_data, model_info)

        return event_data

    def _extract_orcon_model_info(self, model: str) -> dict[str, Any] | None:
        """Extract configuration from Orcon model string.

        Args:
            model: Device model string

        Returns:
            Model configuration dictionary or None
        """
        if not model:
            return None

        model_upper = model.upper()

        # Match against known models
        for model_key, config in ORCON_DEVICE_MODELS.items():
            if model_key in model_upper:
                return {"model_key": model_key, "model_string": model, **config}

        # Fallback for unknown models
        _LOGGER.warning("Unknown Orcon model variant: %s", model)
        return {
            "model_key": "unknown",
            "model_string": model,
            "max_fan_speed": 3,
            "humidity_range": (35, 75),
            "supported_modes": ["auto", "boost"],
            "special_entities": ["filter_timer"],
        }

    async def _add_orcon_entities(
        self, device: Any, event_data: dict[str, Any], model_info: dict[str, Any]
    ) -> None:
        """Add Orcon-specific entities to the event data.

        Args:
            device: Device object
            event_data: Event data to modify
            model_info: Model configuration information
        """
        device_id = device.id
        entities = event_data["entity_ids"]

        # Standard Orcon entities
        standard_entities = [
            f"sensor.orcon_filter_usage_{device_id}",
            f"sensor.orcon_operating_hours_{device_id}",
            f"select.orcon_operation_mode_{device_id}",
            f"number.orcon_target_humidity_{device_id}",
        ]

        entities.extend(standard_entities)

        # Model-specific entities
        special_entities = model_info.get("special_entities", [])
        for special_entity in special_entities:
            if special_entity == "filter_timer":
                entities.append(f"number.orcon_filter_timer_{device_id}")
            elif special_entity == "boost_timer":
                entities.append(f"number.orcon_boost_timer_{device_id}")
            elif special_entity == "eco_mode":
                entities.append(f"switch.orcon_eco_mode_{device_id}")

        # High-end model entities
        if model_info["model_key"] in ["HRV400", "HRV300"]:
            entities.extend(
                [
                    f"sensor.orcon_air_quality_index_{device_id}",
                    f"number.orcon_fan_speed_override_{device_id}",
                    f"switch.orcon_smart_boost_{device_id}",
                ]
            )

        _LOGGER.info(
            "Added %s entities for Orcon device %s",
            len(entities),
            device_id,
        )

    async def _configure_orcon_behaviors(
        self, device: Any, event_data: dict[str, Any], model_info: dict[str, Any]
    ) -> None:
        """Configure Orcon-specific behavior settings.

        Args:
            device: Device object
            event_data: Event data to modify
            model_info: Model configuration information
        """
        event_data["orcon_config"] = {
            "auto_mode_hysteresis": 5,  # % humidity difference
            "boost_trigger_humidity": 70,  # % humidity to trigger boost
            "eco_mode_target_reduction": 10,  # % target reduction in eco mode
            "filter_replacement_interval": 8760,  # hours (1 year)
            "max_boost_duration": 120,  # minutes
            "smart_boost_enabled": model_info["model_key"] in ["HRV400", "HRV300"],
        }

        # Fan speed configuration
        max_speed = model_info["max_fan_speed"]
        event_data["orcon_config"]["fan_speed_levels"] = list(range(1, max_speed + 1))

        # Mode-specific settings
        supported_modes = model_info["supported_modes"]
        mode_configs: dict[str, dict[str, Any]] = {}

        for mode in supported_modes:
            mode_configs[mode] = {
                "default_fan_speed": 2 if mode == "auto" else max_speed,
                "humidity_target_offset": 0
                if mode == "auto"
                else -5
                if mode == "eco"
                else +10,
                "duration_minutes": 0
                if mode == "auto"
                else 30
                if mode == "boost"
                else 60,
            }

        event_data["orcon_config"]["mode_configs"] = mode_configs

    async def _set_orcon_defaults(
        self, event_data: dict[str, Any], model_info: dict[str, Any]
    ) -> None:
        """Set Orcon-specific default values.

        Args:
            event_data: Event data to modify
            model_info: Model configuration information
        """
        humidity_range = model_info["humidity_range"]
        target_humidity = (humidity_range[0] + humidity_range[1]) // 2

        event_data["orcon_defaults"] = {
            "target_humidity": target_humidity,
            "auto_mode_enabled": True,
            "filter_monitoring_enabled": True,
            "boost_timer_default": 30,  # minutes
            "eco_mode_humidity_offset": -5,
            "night_mode_enabled": model_info["model_key"] == "HRV400",
            "preheat_enabled": True,
            "frost_protection_enabled": True,
        }

        # Brand-specific entity enablement
        event_data["default_enabled_entities"] = {
            f"switch.orcon_eco_mode_{event_data['device_id']}": model_info["model_key"]
            != "HRV200",
            f"select.orcon_operation_mode_{event_data['device_id']}": True,
            f"number.orcon_target_humidity_{event_data['device_id']}": True,
            f"sensor.orcon_air_quality_index_{event_data['device_id']}": model_info[
                "model_key"
            ]
            == "HRV400",
        }


class ZehnderDeviceCustomizer:
    """Handle Zehnder-specific device customizations for humidity control."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the Zehnder device customizer.

        Args:
            hass: Home Assistant instance
        """
        self.hass: HomeAssistant = hass
        self.detected_devices: dict[str, Any] = {}

    async def customize_zehnder_device(
        self, device: Any, event_data: dict[str, Any]
    ) -> dict[str, Any]:
        """Apply Zehnder-specific customizations to device.

        Args:
            device: Device object with model property
            event_data: Event data to modify

        Returns:
            Modified event data dictionary
        """
        model_info = self._extract_zehnder_model_info(device.model)

        if not model_info:
            _LOGGER.warning("Unknown Zehnder model: %s", device.model)
            return event_data

        # Apply model-specific configuration
        event_data["model_config"] = model_info

        # Add Zehnder-specific entities
        await self._add_zehnder_entities(device, event_data, model_info)

        # Configure Zehnder-specific behaviors
        await self._configure_zehnder_behaviors(device, event_data, model_info)

        # Set Zehnder-specific defaults
        await self._set_zehnder_defaults(event_data, model_info)

        return event_data

    def _extract_zehnder_model_info(self, model: str) -> dict[str, Any] | None:
        """Extract configuration from Zehnder model string.

        Args:
            model: Device model string

        Returns:
            Model configuration dictionary or None
        """
        if not model:
            return None

        model_upper = model.upper()

        # Match against known models
        for model_key, config in ZEHNDER_DEVICE_MODELS.items():
            if model_key.upper() in model_upper:
                return {"model_key": model_key, "model_string": model, **config}

        # Fallback for unknown models
        _LOGGER.warning("Unknown Zehnder model variant: %s", model)
        return {
            "model_key": "unknown",
            "model_string": model,
            "max_fan_speed": 3,
            "humidity_range": (35, 75),
            "supported_modes": ["auto", "boost"],
            "special_entities": ["filter_timer"],
        }

    async def _add_zehnder_entities(
        self, device: Any, event_data: dict[str, Any], model_info: dict[str, Any]
    ) -> None:
        """Add Zehnder-specific entities to the event data.

        Args:
            device: Device object
            event_data: Event data to modify
            model_info: Model configuration information
        """
        device_id = device.id
        entities = event_data["entity_ids"]

        # Standard Zehnder entities
        standard_entities = [
            f"sensor.zehnder_filter_usage_{device_id}",
            f"sensor.zehnder_operating_hours_{device_id}",
            f"select.zehnder_operation_mode_{device_id}",
            f"number.zehnder_target_humidity_{device_id}",
        ]

        entities.extend(standard_entities)

        # Model-specific entities
        special_entities = model_info.get("special_entities", [])
        for special_entity in special_entities:
            if special_entity == "filter_timer":
                entities.append(f"number.zehnder_filter_timer_{device_id}")
            elif special_entity == "co2_sensor":
                entities.append(f"sensor.zehnder_co2_level_{device_id}")
            elif special_entity == "auto_mode":
                entities.append(f"switch.zehnder_auto_mode_{device_id}")
            elif special_entity == "away_mode":
                entities.append(f"switch.zehnder_away_mode_{device_id}")

        # High-end model entities
        if model_info["model_key"] in ["ComfoAir Q450"]:
            entities.extend(
                [
                    f"sensor.zehnder_air_quality_index_{device_id}",
                    f"number.zehnder_fan_speed_override_{device_id}",
                    f"switch.zehnder_smart_boost_{device_id}",
                ]
            )

        _LOGGER.info(
            "Added %s entities for Zehnder device %s",
            len(entities),
            device_id,
        )

    async def _configure_zehnder_behaviors(
        self, device: Any, event_data: dict[str, Any], model_info: dict[str, Any]
    ) -> None:
        """Configure Zehnder-specific behavior settings.

        Args:
            device: Device object
            event_data: Event data to modify
            model_info: Model configuration information
        """
        event_data["zehnder_config"] = {
            "auto_mode_hysteresis": 3,  # % humidity difference
            "boost_trigger_humidity": 65,  # % humidity to trigger boost
            "eco_mode_target_reduction": 8,  # % target reduction in eco mode
            "filter_replacement_interval": 8760,  # hours (1 year)
            "max_boost_duration": 180,  # minutes
            "co2_control_enabled": "co2_sensor"
            in model_info.get("special_entities", []),
        }

        # Fan speed configuration
        max_speed = model_info["max_fan_speed"]
        event_data["zehnder_config"]["fan_speed_levels"] = list(range(1, max_speed + 1))

        # Mode-specific settings
        supported_modes = model_info["supported_modes"]
        mode_configs: dict[str, dict[str, Any]] = {}

        for mode in supported_modes:
            mode_configs[mode] = {
                "default_fan_speed": 2 if mode == "auto" else max_speed,
                "humidity_target_offset": 0
                if mode == "auto"
                else -3
                if mode == "eco"
                else +5,
                "duration_minutes": 0
                if mode == "auto"
                else 45
                if mode == "boost"
                else 60,
            }

        event_data["zehnder_config"]["mode_configs"] = mode_configs

    async def _set_zehnder_defaults(
        self, event_data: dict[str, Any], model_info: dict[str, Any]
    ) -> None:
        """Set Zehnder-specific default values.

        Args:
            event_data: Event data to modify
            model_info: Model configuration information
        """
        humidity_range = model_info["humidity_range"]
        target_humidity = (humidity_range[0] + humidity_range[1]) // 2

        event_data["zehnder_defaults"] = {
            "target_humidity": target_humidity,
            "auto_mode_enabled": True,
            "filter_monitoring_enabled": True,
            "boost_timer_default": 45,  # minutes
            "eco_mode_humidity_offset": -3,
            "away_mode_enabled": "away_mode" in model_info.get("special_entities", []),
            "co2_control_enabled": "co2_sensor"
            in model_info.get("special_entities", []),
        }

        # Brand-specific entity enablement
        event_data["default_enabled_entities"] = {
            f"switch.zehnder_auto_mode_{event_data['device_id']}": True,
            f"select.zehnder_operation_mode_{event_data['device_id']}": True,
            f"number.zehnder_target_humidity_{event_data['device_id']}": True,
            f"sensor.zehnder_co2_level_{event_data['device_id']}": "co2_sensor"
            in model_info.get("special_entities", []),
        }


def is_orcon_device(device: Any) -> bool:
    """Check if device is an Orcon brand device.

    Args:
        device: Device object

    Returns:
        True if device is Orcon brand, False otherwise
    """
    model = getattr(device, "model", None)
    if not model:
        return False

    model_lower = model.lower()
    orcon_patterns = ["orcon", "soler & palau"]
    return any(pattern in model_lower for pattern in orcon_patterns)


def is_zehnder_device(device: Any) -> bool:
    """Check if device is a Zehnder brand device.

    Args:
        device: Device object

    Returns:
        True if device is Zehnder brand, False otherwise
    """
    model = getattr(device, "model", None)
    if not model:
        return False

    model_lower = model.lower()
    zehnder_patterns = ["zehnder", "comfoair"]
    return any(pattern in model_lower for pattern in zehnder_patterns)


# Enhanced entity configurations are now defined in const.py


class EnhancedHumidityControl:
    """Enhanced Humidity Control feature with device discovery support."""

    def __init__(self, hass: HomeAssistant, config_entry: Any) -> None:
        """Initialize enhanced humidity control feature.

        Args:
            hass: Home Assistant instance
            config_entry: Configuration entry
        """
        self.hass = hass
        self.config_entry = config_entry
        self._entity_modifications: dict[str, Any] = {}
        self._brand_customizers: dict[str, Any] = {
            "orcon": OrconDeviceCustomizer(hass),
            "zehnder": ZehnderDeviceCustomizer(hass),
        }

        # Core components
        self.entities = HumidityEntities(hass, config_entry)
        self.automation = HumidityAutomationManager(hass, config_entry)
        self.services = None  # Will be initialized when needed
        self.config = HumidityConfig(hass, config_entry)

        _LOGGER.info("Enhanced Humidity Control feature initialized")

    async def async_setup(self) -> bool:
        """Set up the enhanced humidity control feature.

        Returns:
            True if setup successful, False otherwise
        """
        try:
            # Setup event listeners for device discovery
            await self._setup_event_listeners()

            # Start the automation
            await self.automation.start()

            _LOGGER.info("Enhanced Humidity Control feature setup complete")
            return True

        except Exception as e:
            _LOGGER.error("Failed to setup Enhanced Humidity Control feature: %s", e)
            return False

    async def _setup_event_listeners(self) -> None:
        """Setup event listeners for device discovery."""
        # Listen to device ready events
        async_dispatcher_connect(
            self.hass,
            EVENT_DEVICE_READY_FOR_ENTITIES,
            self._on_device_ready_for_entities,
        )

        _LOGGER.info("Device discovery event listeners setup complete")

    async def _on_device_ready_for_entities(self, event_data: dict[str, Any]) -> None:
        """Handle device ready for entities event.

        Args:
            event_data: Event data containing device information and entity IDs
        """
        device = event_data["device_object"]
        device_id = event_data["device_id"]

        # Check if this is for humidity control
        if event_data["handled_by"] != "humidity_control":
            return

        _LOGGER.info("Enhanced Humidity Control processing device %s", device_id)

        try:
            # Apply brand-specific logic
            if is_orcon_device(device):
                await self._handle_orcon_device(event_data)
            elif is_zehnder_device(device):
                await self._handle_zehnder_device(event_data)
            else:
                await self._handle_generic_device(event_data)

        except Exception as e:
            _LOGGER.error(
                "Failed to process device %s for humidity control: %s",
                device_id,
                e,
            )

    async def _handle_orcon_device(self, event_data: dict[str, Any]) -> None:
        """Apply Orcon-specific humidity control customizations.

        Args:
            event_data: Event data for Orcon device
        """
        device = event_data["device_object"]
        orcon_customizer = cast(OrconDeviceCustomizer, self._brand_customizers["orcon"])

        _LOGGER.info(
            "Applying Orcon-specific customizations for device %s",
            device.id,
        )

        # Apply Orcon customizations
        await orcon_customizer.customize_orcon_device(device, event_data)

        # Apply humidity-specific customizations
        await self._apply_humidity_customizations(event_data, "orcon")

    async def _handle_zehnder_device(self, event_data: dict[str, Any]) -> None:
        """Apply Zehnder-specific humidity control customizations.

        Args:
            event_data: Event data for Zehnder device
        """
        device = event_data["device_object"]
        zehnder_customizer = cast(
            ZehnderDeviceCustomizer, self._brand_customizers["zehnder"]
        )

        _LOGGER.info(
            "Applying Zehnder-specific customizations for device %s",
            device.id,
        )

        # Apply Zehnder customizations
        await zehnder_customizer.customize_zehnder_device(device, event_data)

        # Apply humidity-specific customizations
        await self._apply_humidity_customizations(event_data, "zehnder")

    async def _handle_generic_device(self, event_data: dict[str, Any]) -> None:
        """Apply generic humidity control customizations.

        Args:
            event_data: Event data for generic device
        """
        device = event_data["device_object"]

        _LOGGER.info("Applying generic customizations for device %s", device.id)

        # Apply basic humidity customizations
        await self._apply_humidity_customizations(event_data, "generic")

    async def _apply_humidity_customizations(
        self, event_data: dict[str, Any], brand: str
    ) -> None:
        """Apply humidity-specific customizations based on brand.

        Args:
            event_data: Event data to modify
            brand: Brand identifier (orcon, zehnder, generic)
        """
        device = event_data["device_object"]
        device_id = device.id

        # Brand-specific humidity control configurations
        brand_configs = {
            "orcon": {
                "target_humidity": 55,
                "boost_trigger_humidity": 70,
                "eco_mode_humidity_offset": -5,
                "smart_boost_enabled": True,
            },
            "zehnder": {
                "target_humidity": 50,
                "boost_trigger_humidity": 65,
                "eco_mode_humidity_offset": -3,
                "smart_boost_enabled": True,
            },
            "generic": {
                "target_humidity": 50,
                "boost_trigger_humidity": 65,
                "eco_mode_humidity_offset": 0,
                "smart_boost_enabled": False,
            },
        }

        config = brand_configs.get(brand, brand_configs["generic"])

        # Apply humidity-specific entity additions
        humidity_entities = [
            f"sensor.{brand}_humidity_efficiency_{device_id}",
            f"number.{brand}_humidity_target_{device_id}",
        ]

        # Add brand-specific entities based on capabilities
        if brand == "orcon":
            humidity_entities.extend(
                [
                    f"switch.{brand}_smart_humidity_{device_id}",
                    f"select.{brand}_humidity_mode_{device_id}",
                ]
            )
        elif brand == "zehnder":
            humidity_entities.extend(
                [
                    f"sensor.{brand}_co2_humidity_correlation_{device_id}",
                    f"switch.{brand}_auto_humidity_{device_id}",
                ]
            )

        event_data["entity_ids"].extend(humidity_entities)

        # Store brand-specific modifications
        self._entity_modifications[device_id] = {
            "brand": brand,
            "humidity_config": config,
            "custom_entities": humidity_entities,
        }

        _LOGGER.info(
            "Applied %s humidity customizations for device %s: %s additional entities",
            brand,
            device_id,
            len(humidity_entities),
        )

    def should_create_entity(
        self, device_id: str, entity_id: str, default_enabled: bool = True
    ) -> bool:
        """Determine if entity should be created based on modifications.

        Args:
            device_id: Device identifier
            entity_id: Entity identifier
            default_enabled: Default enabled state

        Returns:
            True if entity should be created, False otherwise
        """
        # Check if user has set explicit preferences
        device_modifications = self._entity_modifications.get(device_id, {})
        _LOGGER.debug("device modifications: %s", device_modifications)
        # For now, return default behavior
        # This can be extended to check user preferences
        return default_enabled

    async def async_cleanup(self) -> None:
        """Cleanup resources when feature is stopped."""
        _LOGGER.info("Cleaning up Enhanced Humidity Control feature")
        self._entity_modifications.clear()

    def get_brand_info(self, device_id: str) -> dict[str, Any]:
        """Get brand information for a device.

        Args:
            device_id: Device identifier

        Returns:
            Brand information dictionary
        """
        modifications = self._entity_modifications.get(device_id, {})
        brand_info: dict[str, Any] = modifications.get("humidity_config", {})
        return brand_info

    def get_entity_customizations(self, device_id: str) -> dict[str, Any]:
        """Get entity customizations for a device.

        Args:
            device_id: Device identifier

        Returns:
            Entity customizations dictionary
        """
        entity_customizations: dict[str, Any] = self._entity_modifications.get(
            device_id, {}
        )
        return entity_customizations


async def create_humidity_control_feature(
    hass: Any, config_entry: Any, skip_automation_setup: bool = False
) -> dict[str, Any]:
    """Factory function to create humidity control feature.

    Args:
        hass: Home Assistant instance
        config_entry: Configuration entry

    Returns:
        Humidity control feature instance with automation,
        entities, services, config, platforms, and enhanced functionality
    """
    # Create the core enhanced humidity control feature
    enhanced_feature = EnhancedHumidityControl(hass, config_entry)

    # Setup the enhanced feature (starts the automation) unless automation
    #  setup is skipped
    if not skip_automation_setup:
        await enhanced_feature.async_setup()

    # Also maintain compatibility with the original structure
    automation = enhanced_feature.automation  # Use the automation from enhanced feature

    return {
        "automation": automation,
        "entities": HumidityEntities(hass, config_entry),
        "services": HumidityServices(hass, config_entry),
        "config": HumidityConfig(hass, config_entry),
        "enhanced": enhanced_feature,  # Add the enhanced functionality
        "platforms": {
            "sensor": {
                "async_setup_entry": sensor_async_setup_entry,
                "create_sensor": create_humidity_sensor,
            },
            "binary_sensor": {
                "async_setup_entry": binary_sensor_async_setup_entry,
                "create_binary_sensor": create_humidity_control_binary_sensor,
                "entity_class": HumidityControlBinarySensor,
            },
            "switch": {
                "async_setup_entry": switch_async_setup_entry,
                "create_switch": create_humidity_switch,
                "entity_class": HumidityControlSwitch,
            },
            "number": {
                "async_setup_entry": number_async_setup_entry,
                "create_number": create_humidity_number,
                "entity_class": HumidityControlNumber,
            },
        },
    }


__all__ = [
    # Existing feature exports
    "HumidityAutomationManager",
    "HumidityEntities",
    "HumidityServices",
    "HumidityConfig",
    "HUMIDITY_SWITCH_CONFIGS",
    "HUMIDITY_NUMBER_CONFIGS",
    "HUMIDITY_BOOLEAN_CONFIGS",
    "HUMIDITY_DEVICE_ENTITY_MAPPING",
    # Platform class exports
    "HumidityControlBinarySensor",
    "HumidityControlSwitch",
    "HumidityControlNumber",
    # Platform setup exports
    "sensor_async_setup_entry",
    "binary_sensor_async_setup_entry",
    "switch_async_setup_entry",
    "number_async_setup_entry",
    # Platform factory exports
    "create_humidity_sensor",
    "create_humidity_control_binary_sensor",
    "create_humidity_switch",
    "create_humidity_number",
    # Enhanced feature exports
    "EnhancedHumidityControl",
    "ENHANCED_HUMIDITY_SWITCH_CONFIGS",
    "ENHANCED_HUMIDITY_NUMBER_CONFIGS",
    "ENHANCED_HUMIDITY_BOOLEAN_CONFIGS",
    # Brand model exports
    "ORCON_DEVICE_MODELS",
    "ZEHNDER_DEVICE_MODELS",
]
