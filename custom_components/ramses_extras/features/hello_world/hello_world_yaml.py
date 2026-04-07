"""Hello World feature YAML import/export and validation.

This module handles YAML export, import, and validation for the hello_world feature.
Each feature is responsible for its own import/export YAML and validator.
"""

from __future__ import annotations

from typing import Any, cast

import voluptuous as vol

from ...framework.helpers.config.import_validation import (
    register_config_validator,
)
from .const import FEATURE_ID

# Hello World YAML Schema

HELLO_WORLD_CONFIG_SCHEMA = vol.Schema(
    {
        vol.Optional("enabled", default=False): bool,
        vol.Optional("greeting", default="Hello World"): str,
    }
)


def hello_world_validator(section: dict, hass: Any | None = None) -> list[str]:
    """Validate hello_world configuration section.

    :param section: The hello_world configuration section
    :param hass: Home Assistant instance (optional)
    :return: List of validation error messages
    """
    errors: list[str] = []

    if not isinstance(section, dict):
        errors.append("hello_world configuration must be a dictionary")  # type: ignore[unreachable]
        return errors

    # Validate greeting if present
    greeting = section.get("greeting")
    if greeting is not None and not isinstance(greeting, str):
        errors.append("hello_world.greeting must be a string")

    return errors


def export_hello_world_to_yaml(config: dict) -> dict:
    """Export hello_world configuration to YAML-compatible dict.

    :param config: The hello_world configuration section
    :return: YAML-compatible dictionary
    """
    return {
        "enabled": config.get("enabled", False),
        "greeting": config.get("greeting", "Hello World"),
    }


def parse_hello_world_yaml(yaml_data: dict) -> dict[Any, Any]:
    """Parse hello_world YAML data into canonical config format.

    :param yaml_data: Raw YAML data for hello_world section
    :return: Canonical hello_world configuration
    """
    result = HELLO_WORLD_CONFIG_SCHEMA(yaml_data)
    return cast(dict[Any, Any], result)


def merge_hello_world_config(existing: dict, imported: dict) -> dict:
    """Merge imported hello_world config with existing.

    :param existing: Existing hello_world configuration
    :param imported: Imported hello_world configuration
    :return: Merged configuration
    """
    merged = dict(existing)
    merged.update(imported)
    return merged


def load_validator() -> None:
    """Register the hello_world validator with the framework."""
    register_config_validator(FEATURE_ID, hello_world_validator)
