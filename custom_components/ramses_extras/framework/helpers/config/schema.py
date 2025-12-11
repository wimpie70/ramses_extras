"""Configuration schema generation for Ramses Extras framework.

This module provides reusable schema generation patterns that are shared across
all features, including UI schema generation for Home Assistant configuration flows.
"""

import logging
from typing import Any

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


__all__ = [
    "ConfigSchema",
]
