"""Framework automation helper module.

This module provides reusable automation utilities that are shared across
all features, including entity discovery, validation, and pattern matching.
"""

import logging

from ..common import _singularize_entity_type

_LOGGER = logging.getLogger(__name__)


__all__ = [
    "_singularize_entity_type",
]
