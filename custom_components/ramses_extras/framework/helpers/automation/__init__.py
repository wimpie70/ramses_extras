"""Framework automation helper module.

This module provides reusable automation utilities that are shared across
all features, including entity discovery, validation, and pattern matching.
"""

from .core import _get_required_entities_from_feature, _singularize_entity_type

__all__ = [
    "_get_required_entities_from_feature",
    "_singularize_entity_type",
]
