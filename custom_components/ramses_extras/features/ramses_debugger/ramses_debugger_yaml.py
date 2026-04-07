"""Ramses Debugger feature YAML import/export and validation.

This module handles YAML export, import, and validation for the ramses_debugger feature.
Each feature is responsible for its own import/export YAML and validator.
"""

from __future__ import annotations

from typing import Any, cast

import voluptuous as vol

from ...framework.helpers.config.import_validation import (
    register_config_validator,
)
from .const import FEATURE_ID

# Ramses Debugger YAML Schema

RAMSES_DEBUGGER_CONFIG_SCHEMA = vol.Schema(
    {
        vol.Optional("enabled", default=False): bool,
        vol.Optional("debug_level", default="info"): vol.In(
            ["debug", "info", "warning", "error"]
        ),
        vol.Optional("log_packets", default=False): bool,
    }
)


def ramses_debugger_validator(section: dict, hass: Any | None = None) -> list[str]:
    """Validate ramses_debugger configuration section.

    :param section: The ramses_debugger configuration section
    :param hass: Home Assistant instance (optional)
    :return: List of validation error messages
    """
    errors: list[str] = []

    if not isinstance(section, dict):
        errors.append("ramses_debugger configuration must be a dictionary")  # type: ignore[unreachable]
        return errors

    # Validate debug_level if present
    debug_level = section.get("debug_level")
    valid_levels = ("debug", "info", "warning", "error")
    if debug_level is not None and debug_level not in valid_levels:
        errors.append(
            f"ramses_debugger.debug_level must be one of: {', '.join(valid_levels)}"
        )

    return errors


def export_ramses_debugger_to_yaml(config: dict) -> dict:
    """Export ramses_debugger configuration to YAML-compatible dict.

    :param config: The ramses_debugger configuration section
    :return: YAML-compatible dictionary
    """
    return {
        "enabled": config.get("enabled", False),
        "debug_level": config.get("debug_level", "info"),
        "log_packets": config.get("log_packets", False),
    }


def parse_ramses_debugger_yaml(yaml_data: dict) -> dict[str, Any]:
    """Parse ramses_debugger YAML data into canonical config format.

    :param yaml_data: Raw YAML data for ramses_debugger section
    :return: Canonical ramses_debugger configuration
    """
    result = RAMSES_DEBUGGER_CONFIG_SCHEMA(yaml_data)
    return cast(dict[str, Any], result)


def merge_ramses_debugger_config(existing: dict, imported: dict) -> dict:
    """Merge imported ramses_debugger config with existing.

    :param existing: Existing ramses_debugger configuration
    :param imported: Imported ramses_debugger configuration
    :return: Merged configuration
    """
    merged = dict(existing)
    merged.update(imported)
    return merged


def load_validator() -> None:
    """Register the ramses_debugger validator with the framework."""
    register_config_validator(FEATURE_ID, ramses_debugger_validator)
