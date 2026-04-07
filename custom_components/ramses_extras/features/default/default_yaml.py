"""Default feature YAML import/export and validation.

This module handles YAML export, import, and validation for the default feature.
The default feature is always enabled and provides base entity definitions.
"""

from __future__ import annotations

from typing import Any, cast

import voluptuous as vol

from ...framework.helpers.config.import_validation import (
    register_config_validator,
)
from .const import FEATURE_ID

# Default feature YAML Schema
# The default feature has minimal configuration since it's always enabled

DEFAULT_FEATURE_CONFIG_SCHEMA = vol.Schema(
    {
        vol.Optional("enabled", default=True): bool,
        vol.Optional("entities", default={}): dict,
    }
)


def default_validator(section: dict, hass: Any | None = None) -> list[str]:
    """Validate default feature configuration section.

    :param section: The default configuration section
    :param hass: Home Assistant instance (optional)
    :return: List of validation error messages
    """
    errors: list[str] = []

    # Default feature is always enabled, just validate structure
    if not isinstance(section, dict):
        errors.append("default configuration must be a dictionary")  # type: ignore[unreachable]
        return errors

    # Validate entities section if present
    entities = section.get("entities")
    if entities is not None and not isinstance(entities, dict):
        errors.append("default.entities must be a dictionary")

    return errors


def export_default_to_yaml(config: dict) -> dict:
    """Export default configuration to YAML-compatible dict.

    :param config: The default configuration section
    :return: YAML-compatible dictionary
    """
    return {
        "enabled": config.get("enabled", True),
        "entities": config.get("entities", {}),
    }


def parse_default_yaml(yaml_data: dict) -> dict[Any, Any]:
    """Parse default YAML data into canonical config format.

    :param yaml_data: Raw YAML data for default section
    :return: Canonical default configuration
    """
    # Validate against schema
    result = DEFAULT_FEATURE_CONFIG_SCHEMA(yaml_data)
    return cast(dict[Any, Any], result)


def merge_default_config(existing: dict, imported: dict) -> dict:
    """Merge imported default config with existing.

    :param existing: Existing default configuration
    :param imported: Imported default configuration
    :return: Merged configuration
    """
    merged = dict(existing)
    if "entities" in imported:
        if "entities" not in merged:
            merged["entities"] = {}
        merged["entities"].update(imported["entities"])
    return merged


def load_validator() -> None:
    """Register the default feature validator with the framework."""
    register_config_validator(FEATURE_ID, default_validator)
