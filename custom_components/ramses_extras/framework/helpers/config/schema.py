"""Configuration schema generation for Ramses Extras framework.

This module provides reusable schema generation patterns that are shared across
all features, including UI schema generation for Home Assistant configuration flows.
"""

import logging
from typing import Any, Union

_LOGGER = logging.getLogger(__name__)


class ConfigSchema:
    """Utility class for generating configuration schemas.

    This class provides common schema generation patterns that can be used by
    features to generate UI schemas for their configuration.
    """

    def __init__(self, feature_id: str) -> None:
        """Initialize the configuration schema generator.

        Args:
            feature_id: Feature identifier
        """
        self.feature_id = feature_id

    def generate_basic_schema(
        self,
        fields: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        """Generate a basic configuration schema.

        Args:
            fields: Dictionary of field definitions

        Returns:
            Complete schema dictionary
        """
        properties = {}
        required_fields = []

        for field_key, field_config in fields.items():
            # Generate property schema
            property_schema = self._generate_property_schema(field_key, field_config)
            properties[field_key] = property_schema

            # Track required fields
            if field_config.get("required", False):
                required_fields.append(field_key)

        schema = {
            "type": "object",
            "properties": properties,
        }

        if required_fields:
            schema["required"] = required_fields

        return schema

    def _generate_property_schema(
        self, key: str, config: dict[str, Any]
    ) -> dict[str, Any]:
        """Generate a property schema for a specific field.

        Args:
            key: Field key
            config: Field configuration

        Returns:
            Property schema dictionary
        """
        field_type = config.get("type", "string")
        schema = {"title": config.get("title", key.replace("_", " ").title())}

        # Add description if provided
        if "description" in config:
            schema["description"] = config["description"]

        # Add type-specific properties
        if field_type == "boolean":
            schema["type"] = "boolean"
            schema["default"] = config.get("default", False)

        elif field_type == "numeric":
            schema["type"] = "number"
            if "min" in config:
                schema["minimum"] = config["min"]
            if "max" in config:
                schema["maximum"] = config["max"]
            if "step" in config:
                schema["multipleOf"] = config["step"]
            schema["default"] = config.get("default", 0)

        elif field_type == "integer":
            schema["type"] = "integer"
            if "min" in config:
                schema["minimum"] = config["min"]
            if "max" in config:
                schema["maximum"] = config["max"]
            schema["default"] = config.get("default", 0)

        elif field_type == "string":
            schema["type"] = "string"
            if "min_length" in config:
                schema["minLength"] = config["min_length"]
            if "max_length" in config:
                schema["maxLength"] = config["max_length"]
            schema["default"] = config.get("default", "")

            # Add choices if provided
            if "choices" in config:
                schema["enum"] = config["choices"]

        elif field_type == "list":
            schema["type"] = "array"
            if "item_type" in config:
                schema["items"] = {"type": config["item_type"]}
            schema["default"] = config.get("default", [])

        # Add entity selector if specified
        if "entity_type" in config:
            schema["entity_type"] = config["entity_type"]
            schema["selector"] = {
                "entity": {"filter": {"domain": config["entity_type"]}}
            }

        # Add device selector if specified
        if "device_type" in config:
            schema["device_type"] = config["device_type"]
            schema["selector"] = {"device": {"integration": "ramses_extras"}}

        return schema

    def generate_automation_schema(self) -> dict[str, Any]:
        """Generate a standard automation configuration schema.

        Returns:
            Schema dictionary for automation settings
        """
        fields = {
            "enabled": {
                "type": "boolean",
                "title": f"Enable {self.feature_id.title().replace('_', ' ')}",
                "description": f"Enable or disable the {self.feature_id} feature",
                "default": True,
                "required": False,
            },
            "automation_enabled": {
                "type": "boolean",
                "title": "Enable Automation",
                "description": "Enable automatic control for this feature",
                "default": True,
                "required": False,
            },
            "debounce_seconds": {
                "type": "numeric",
                "title": "Debounce Duration",
                "description": "Time to wait between automation triggers (seconds)",
                "min": 5,
                "max": 300,
                "step": 5,
                "default": 30,
                "required": False,
            },
        }

        return self.generate_basic_schema(fields)

    def generate_threshold_schema(self, threshold_type: str) -> dict[str, Any]:
        """Generate a threshold configuration schema.

        Args:
            threshold_type: Type of threshold (e.g., "humidity", "temperature")

        Returns:
            Schema dictionary for threshold settings
        """
        fields = {
            "default_min_threshold": {
                "type": "numeric",
                "title": f"Default Minimum {threshold_type.title()}",
                "description": f"Default minimum {threshold_type} threshold",
                "min": 0,
                "max": 100,
                "default": 40,
                "required": False,
            },
            "default_max_threshold": {
                "type": "numeric",
                "title": f"Default Maximum {threshold_type.title()}",
                "description": f"Default maximum {threshold_type} threshold",
                "min": 0,
                "max": 100,
                "default": 60,
                "required": False,
            },
        }

        schema = self.generate_basic_schema(fields)

        # Add advanced options section
        advanced_fields = {
            "activation_threshold": {
                "type": "numeric",
                "title": f"{threshold_type.title()} Activation Threshold",
                "description": f"Threshold to trigger {threshold_type} activation",
                "min": 0.1,
                "max": 10.0,
                "step": 0.1,
                "default": 1.0,
                "required": False,
            },
            "deactivation_threshold": {
                "type": "numeric",
                "title": f"{threshold_type.title()} Deactivation Threshold",
                "description": f"Threshold to trigger {threshold_type} deactivation",
                "min": -10.0,
                "max": -0.1,
                "step": 0.1,
                "default": -1.0,
                "required": False,
            },
        }

        schema["advanced"] = {
            "type": "object",
            "title": "Advanced Settings",
            "description": "Advanced threshold and control settings",
            "properties": {},
        }

        for field_key, field_config in advanced_fields.items():
            property_schema = self._generate_property_schema(field_key, field_config)
            schema["advanced"]["properties"][field_key] = property_schema

        return schema

    def generate_performance_schema(self) -> dict[str, Any]:
        """Generate a performance configuration schema.

        Returns:
            Schema dictionary for performance settings
        """
        fields = {
            "update_interval": {
                "type": "integer",
                "title": "Update Interval",
                "description": "How often to update entity states (seconds)",
                "min": 1,
                "max": 300,
                "default": 5,
                "required": False,
            },
            "max_history": {
                "type": "integer",
                "title": "Maximum History",
                "description": "Maximum number of historical readings to keep",
                "min": 10,
                "max": 1000,
                "default": 100,
                "required": False,
            },
            "enable_logging": {
                "type": "boolean",
                "title": "Enable Debug Logging",
                "description": "Enable detailed logging for debugging",
                "default": False,
                "required": False,
            },
        }

        return self.generate_basic_schema(fields)

    def generate_sensor_schema(self) -> dict[str, Any]:
        """Generate a sensor configuration schema.

        Returns:
            Schema dictionary for sensor settings
        """
        fields = {
            "indoor_sensor_entity": {
                "type": "string",
                "title": "Indoor Sensor Entity",
                "description": "Entity ID for indoor sensor",
                "required": False,
            },
            "outdoor_sensor_entity": {
                "type": "string",
                "title": "Outdoor Sensor Entity",
                "description": "Entity ID for outdoor sensor",
                "required": False,
            },
            "sensor_update_interval": {
                "type": "numeric",
                "title": "Sensor Update Interval",
                "description": "How often to read sensor values (seconds)",
                "min": 1,
                "max": 60,
                "default": 10,
                "required": False,
            },
        }

        return self.generate_basic_schema(fields)

    def generate_safety_schema(self) -> dict[str, Any]:
        """Generate a safety configuration schema.

        Returns:
            Schema dictionary for safety settings
        """
        fields = {
            "max_runtime_minutes": {
                "type": "integer",
                "title": "Maximum Runtime",
                "description": "Maximum continuous runtime in minutes",
                "min": 1,
                "max": 1440,
                "default": 120,
                "required": False,
            },
            "cooldown_period_minutes": {
                "type": "integer",
                "title": "Cooldown Period",
                "description": "Minimum time between activations in minutes",
                "min": 1,
                "max": 60,
                "default": 15,
                "required": False,
            },
            "emergency_stop_enabled": {
                "type": "boolean",
                "title": "Emergency Stop",
                "description": "Enable emergency stop functionality",
                "default": True,
                "required": False,
            },
        }

        return self.generate_basic_schema(fields)


# Pre-built schemas for common feature types
def get_humidity_control_schema() -> dict[str, Any]:
    """Get a standard humidity control configuration schema.

    Returns:
        Complete schema for humidity control feature
    """
    schema_gen = ConfigSchema("humidity_control")

    schema: dict[str, Any] = {
        "type": "object",
        "properties": {},
        "sections": dict[str, Any](),
    }

    # Basic automation settings
    schema["sections"]["basic"] = {
        "type": "object",
        "title": "Basic Settings",
        "description": "Basic configuration for humidity control",
        "properties": schema_gen.generate_basic_schema(
            {
                "enabled": {
                    "type": "boolean",
                    "title": "Enable Humidity Control",
                    "description": "Enable or disable humidity control",
                    "default": True,
                },
                "automation_enabled": {
                    "type": "boolean",
                    "title": "Enable Automation",
                    "description": "Enable automatic humidity control",
                    "default": True,
                },
            }
        )["properties"],
    }

    # Threshold settings
    schema["sections"]["thresholds"] = {
        "type": "object",
        "title": "Humidity Thresholds",
        "description": "Humidity threshold settings",
        "properties": schema_gen.generate_threshold_schema("humidity")["properties"],
    }

    # Performance settings
    schema["sections"]["performance"] = {
        "type": "object",
        "title": "Performance Settings",
        "description": "Performance and logging settings",
        "properties": schema_gen.generate_performance_schema()["properties"],
    }

    return schema


def get_temperature_control_schema() -> dict[str, Any]:
    """Get a standard temperature control configuration schema.

    Returns:
        Complete schema for temperature control feature
    """
    schema_gen = ConfigSchema("temperature_control")

    schema: dict[str, Any] = {
        "type": "object",
        "properties": {},
        "sections": dict[str, Any](),
    }

    # Basic automation settings
    schema["sections"]["basic"] = {
        "type": "object",
        "title": "Basic Settings",
        "description": "Basic configuration for temperature control",
        "properties": schema_gen.generate_basic_schema(
            {
                "enabled": {
                    "type": "boolean",
                    "title": "Enable Temperature Control",
                    "description": "Enable or disable temperature control",
                    "default": True,
                },
                "automation_enabled": {
                    "type": "boolean",
                    "title": "Enable Automation",
                    "description": "Enable automatic temperature control",
                    "default": True,
                },
            }
        )["properties"],
    }

    # Threshold settings
    schema["sections"]["thresholds"] = {
        "type": "object",
        "title": "Temperature Thresholds",
        "description": "Temperature threshold settings",
        "properties": schema_gen.generate_threshold_schema("temperature")["properties"],
    }

    # Performance settings
    schema["sections"]["performance"] = {
        "type": "object",
        "title": "Performance Settings",
        "description": "Performance and logging settings",
        "properties": schema_gen.generate_performance_schema()["properties"],
    }

    return schema


__all__ = [
    "ConfigSchema",
    "get_humidity_control_schema",
    "get_temperature_control_schema",
]
