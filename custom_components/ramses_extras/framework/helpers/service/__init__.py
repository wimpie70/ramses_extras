"""Service framework for Ramses Extras.

This module provides a framework for extracting and reusing service
patterns across different features and device types.

Common patterns extracted:
- Service registration and management
- Entity lookup and pattern matching
- Service execution and command handling
- Status reporting and monitoring
"""

from .core import (
    ExtrasServiceManager,
    ServiceExecutionContext,
)
from .registration import (
    ServiceDefinition,
    ServiceRegistrationManager,
    ServiceRegistry,
)
from .validation import (
    ServiceValidator,
    ValidationResult,
    validate_service_call,
)

__all__ = [
    # Core service management
    "ExtrasServiceManager",
    "ServiceExecutionContext",
    # Service registration
    "ServiceRegistry",
    "ServiceRegistrationManager",
    "ServiceDefinition",
    # Service validation
    "ServiceValidator",
    "ValidationResult",
    "validate_service_call",
]
