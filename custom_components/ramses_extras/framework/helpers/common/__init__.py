"""Framework common utilities module.

This module provides reusable utility functions that are shared across
all features, including logging, validation, and other common helpers.
"""

from .logging import (
    LogContext,
    create_logging_context,
    log_method,
)
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
    # Logging utilities
    "LogContext",
    "create_logging_context",
    "log_method",
    # Validation utilities
    "ValidationError",
    "RamsesValidator",
    "ValidationContext",
    "create_validation_context",
    "validate_device_id",
    "validate_humidity_values",
    "async_validate_entity_states",
]
