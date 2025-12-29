"""Framework common utilities module.

This module provides reusable utility functions that are shared across
all features, including logging, validation, and other common helpers.
"""

from .utils import _singularize_entity_type, calculate_absolute_humidity
from .validation import (
    RamsesValidator,
    ValidationContext,
    ValidationError,
    async_validate_entity_states,
    create_validation_context,
    validate_device_id,
)

__all__ = [
    # Validation utilities
    "ValidationError",
    "RamsesValidator",
    "ValidationContext",
    "create_validation_context",
    "validate_device_id",
    "async_validate_entity_states",
    # Common utilities
    "calculate_absolute_humidity",
    "_singularize_entity_type",
]
