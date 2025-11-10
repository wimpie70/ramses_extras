"""Framework entity helper module.

This module provides reusable entity utilities that are shared across
all features, including entity ID generation, state management, and
pattern matching functionality.
"""

from .entity_core import (
    EntityHelpers,
    filter_entities_by_patterns,
    generate_entity_id,
    generate_entity_patterns_for_feature,
    get_entities_for_device,
    get_entity_device_id,
    parse_entity_id,
)

__all__ = [
    "EntityHelpers",
    "generate_entity_id",
    "parse_entity_id",
    "get_entity_device_id",
    "get_entities_for_device",
    "filter_entities_by_patterns",
    "generate_entity_patterns_for_feature",
]
