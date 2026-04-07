"""HVAC Fan Card YAML import/export and validation.

This module handles YAML export, import, and validation for the hvac_fan_card feature.
Each feature is responsible for its own import/export YAML and validator.
"""

from __future__ import annotations

from typing import Any, cast

import voluptuous as vol

from ...framework.helpers.config.import_validation import (
    register_config_validator,
)
from .const import FEATURE_ID

# HVAC Fan Card YAML Schema
# The HVAC Fan Card is a UI card feature with minimal configuration

HVAC_FAN_CARD_CONFIG_SCHEMA = vol.Schema(
    {
        vol.Optional("enabled", default=False): bool,
        vol.Optional("fan_id"): str,
        vol.Optional("card_config", default={}): dict,
    }
)


def hvac_fan_card_validator(section: dict, hass: Any | None = None) -> list[str]:
    """Validate hvac_fan_card configuration section.

    :param section: The hvac_fan_card configuration section
    :param hass: Home Assistant instance (optional)
    :return: List of validation error messages
    """
    errors: list[str] = []

    if not isinstance(section, dict):
        errors.append("hvac_fan_card configuration must be a dictionary")  # type: ignore[unreachable]
        return errors

    # Validate card_config if present
    card_config = section.get("card_config")
    if card_config is not None and not isinstance(card_config, dict):
        errors.append("hvac_fan_card.card_config must be a dictionary")

    return errors


def export_hvac_fan_card_to_yaml(config: dict) -> dict[str, Any]:
    """Export hvac_fan_card configuration to YAML-compatible dict.

    :param config: The hvac_fan_card configuration section
    :return: YAML-compatible dictionary
    """
    return {
        "enabled": config.get("enabled", False),
        "fan_id": config.get("fan_id"),
        "card_config": config.get("card_config", {}),
    }


def parse_hvac_fan_card_yaml(yaml_data: dict) -> dict[str, Any]:
    """Parse hvac_fan_card YAML data into canonical config format.

    :param yaml_data: Raw YAML data for hvac_fan_card section
    :return: Canonical hvac_fan_card configuration
    """
    result = HVAC_FAN_CARD_CONFIG_SCHEMA(yaml_data)
    return cast(dict[str, Any], result)


def merge_hvac_fan_card_config(existing: dict, imported: dict) -> dict[str, Any]:
    """Merge imported hvac_fan_card config with existing.

    :param existing: Existing hvac_fan_card configuration
    :param imported: Imported hvac_fan_card configuration
    :return: Merged configuration
    """
    merged = dict(existing)
    if "card_config" in imported:
        if "card_config" not in merged:
            merged["card_config"] = {}
    # Update other fields
    for key in ["enabled", "fan_id"]:
        if key in imported:
            merged[key] = imported[key]
    return merged


def load_validator() -> None:
    """Register the hvac_fan_card validator with the framework."""
    register_config_validator(FEATURE_ID, hvac_fan_card_validator)
