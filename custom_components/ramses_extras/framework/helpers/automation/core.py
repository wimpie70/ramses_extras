"""Core automation helper functions for Ramses Extras framework.

This module provides reusable automation utilities that are shared across
all features, including entity discovery, validation, and pattern matching.
"""

import importlib
import logging
from typing import Any, cast

_LOGGER = logging.getLogger(__name__)


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
    "_singularize_entity_type",
]
