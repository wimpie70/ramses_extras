"""Framework device helper module.

This module provides reusable device utilities that are shared across
all features, including device finding, validation, and type detection.
"""

from .core import (
    ensure_ramses_cc_loaded,
    find_ramses_device,
    get_all_device_ids,
    get_device_supported_entities,
    get_device_type,
    validate_device_entity_support,
    validate_device_for_service,
)

__all__ = [
    "find_ramses_device",
    "get_device_type",
    "validate_device_for_service",
    "get_all_device_ids",
    "ensure_ramses_cc_loaded",
    "get_device_supported_entities",
    "validate_device_entity_support",
]
