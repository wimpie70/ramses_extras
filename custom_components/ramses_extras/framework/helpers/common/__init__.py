"""Framework common utilities module.

This module provides reusable utility functions that are shared across
all features, including logging, validation, and other common helpers.
"""

from .validation import (
    RamsesValidator,
    ValidationContext,
    ValidationError,
    async_validate_entity_states,
    create_validation_context,
    validate_device_id,
    validate_humidity_values,
)

__all__ = [
    # Validation utilities
    "ValidationError",
    "RamsesValidator",
    "ValidationContext",
    "create_validation_context",
    "validate_device_id",
    "validate_humidity_values",
    "async_validate_entity_states",
]
