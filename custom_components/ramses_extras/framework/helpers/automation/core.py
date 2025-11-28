"""Core automation helper functions for Ramses Extras framework.

This module provides reusable automation utilities that are shared across
all features, including entity discovery, validation, and pattern matching.
"""

import importlib
import logging
from typing import Any, cast

_LOGGER = logging.getLogger(__name__)


def _get_required_entities_from_feature(feature_id: str) -> dict[str, list[str]]:
    """Get required entities from the feature's own const.py module.

    Args:
        feature_id: Feature identifier

    Returns:
        Dictionary mapping entity types to entity names
    """
    try:
        # Import the feature's const module
        feature_module_path = (
            f"custom_components.ramses_extras.features.{feature_id}.const"
        )
        import importlib

        feature_module = importlib.import_module(feature_module_path)

        # Get the feature constants
        const_key = f"{feature_id.upper()}_CONST"
        feature_const = getattr(feature_module, const_key, None)

        if feature_const and "required_entities" in feature_const:
            _LOGGER.debug(
                f"Found required entities in {const_key} for {feature_id}: "
                f"{feature_const['required_entities']}"
            )
            return cast(dict[str, list[str]], feature_const["required_entities"])
    except Exception as e:
        _LOGGER.debug(f"Could not get required entities for {feature_id}: {e}")

    # Return empty dict for all failure cases
    return {}


def _singularize_entity_type(entity_type: str) -> str:
    """Convert plural entity type to singular form.

    Args:
        entity_type: Plural entity type (e.g., "switch", "sensor", "number")

    Returns:
        Singular entity type (e.g., "switch", "sensor", "number")
    """
    # Handle common entity type plurals
    entity_type_mapping = {
        "sensor": "sensor",
        "switch": "switch",
        "binary_sensor": "binary_sensor",
        "number": "number",
        "devices": "device",
        "entities": "entity",
        "covers": "cover",
        "fans": "fan",
        "lights": "light",
        "climate": "climate",
        "humidifiers": "humidifier",
        "dehumidifiers": "dehumidifier",
    }

    return entity_type_mapping.get(entity_type, entity_type)


__all__ = [
    "_get_required_entities_from_feature",
    "_singularize_entity_type",
]
