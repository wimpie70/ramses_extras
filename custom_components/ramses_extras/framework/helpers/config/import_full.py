"""Full configuration YAML import utilities.

Provides validated YAML import for the complete ramses_extras configuration,
enabling advanced users to import full setups from YAML files.

Each feature validates its own section via registered validators.
Features must register their schemas using register_config_schema() and
validators using register_config_validator().
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import voluptuous as vol
import yaml

from .import_validation import validate_import_config
from .model import (
    CONFIG_FEATURES_KEY,
    CONFIG_ROOT_KEY,
    CONFIG_SCHEMA_VERSION_KEY,
)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant


# Framework-level validation only - feature schemas registered dynamically
# Features call register_config_schema(feature_id, schema) to register

# Full config schema - uses dynamically registered feature schemas
RAMSES_EXTRAS_CONFIG_SCHEMA = vol.Schema(
    {
        vol.Required(CONFIG_ROOT_KEY): {
            vol.Optional(CONFIG_SCHEMA_VERSION_KEY, default=1): vol.All(
                int, vol.Range(min=1, max=1)
            ),
            vol.Optional(CONFIG_FEATURES_KEY): vol.Schema({}, extra=vol.ALLOW_EXTRA),
        }
    },
    extra=vol.ALLOW_EXTRA,
)


def _build_features_schema() -> vol.Schema:
    """Build features schema dynamically from registered schemas."""
    from .import_validation import get_registered_schemas

    feature_schemas: dict[Any, Any] = {str: vol.Any(dict, list)}
    for feature_id, schema in get_registered_schemas().items():
        feature_schemas[vol.Optional(feature_id)] = schema

    return vol.Schema(feature_schemas, extra=vol.ALLOW_EXTRA)


# Feature validators are registered dynamically by features
# No hardcoded feature validators in framework code


def parse_full_config_yaml(yaml_content: str) -> dict[str, Any]:
    """Parse and validate full ramses_extras YAML configuration.

    Args:
        yaml_content: YAML string containing full ramses_extras configuration

    Returns:
        Validated configuration dictionary

    Raises:
        ValueError: If YAML is invalid or doesn't match schema
    """
    try:
        parsed = yaml.safe_load(yaml_content)
    except yaml.YAMLError as e:
        raise ValueError(f"Invalid YAML syntax: {e}") from e

    if not isinstance(parsed, dict):
        raise ValueError("YAML content must be a dictionary")

    # Validate against schema
    try:
        validated: dict[str, Any] = RAMSES_EXTRAS_CONFIG_SCHEMA(parsed)
    except vol.MultipleInvalid as e:
        raise ValueError(f"Schema validation failed: {e}") from e

    return validated


def validate_full_config_import(
    config: dict[str, Any],
    hass: Any | None = None,
) -> list[str]:
    """Validate a full configuration import using registered validators.

    Args:
        config: Configuration dictionary to validate
        hass: Optional Home Assistant instance for entity/device validation

    Returns:
        List of validation warnings/errors (empty if valid)
    """
    from .import_validation import format_validation_errors

    result = validate_import_config(config, hass)
    return format_validation_errors(result)


def validate_full_config_import_detailed(
    config: dict[str, Any],
    hass: Any | None = None,
) -> dict[str, Any]:
    """Validate a full configuration import with detailed results.

    Args:
        config: Configuration dictionary to validate
        hass: Optional Home Assistant instance for entity/device validation

    Returns:
        Detailed validation result with per-feature breakdown:
        {
            "valid": bool,
            "framework_errors": list[str],
            "feature_errors": dict[str, list[str]],
            "total_errors": int,
        }
    """
    return validate_import_config(config, hass)


__all__ = [
    "parse_full_config_yaml",
    "RAMSES_EXTRAS_CONFIG_SCHEMA",
    "validate_full_config_import",
    "validate_full_config_import_detailed",
]
