"""Framework Helper Modules.

This package contains reusable helper utilities that are shared across
all Ramses Extras features, including:

- Entity helpers: Entity generation, state management, pattern matching
- Device helpers: Device parsing, validation, entity mapping
- Automation helpers: Automation patterns, lifecycle management
- Common utilities: Logging, validation, exceptions
"""

# Entity helpers
# Automation helpers
from .automation import ExtrasBaseAutomation

# Common utilities
from .common import (
    RamsesValidator,
    ValidationContext,
    ValidationError,
    async_validate_entity_states,
    create_validation_context,
    validate_device_id,
    validate_humidity_values,
)

# Device helpers
from .device import (
    ensure_ramses_cc_loaded,
    filter_devices_by_capability,
    find_ramses_device,
    get_all_device_ids,
    get_device_capabilities,
    get_device_supported_entities,
    get_device_type,
    validate_device_entity_support,
    validate_device_for_service,
)
from .entity import (
    EntityHelpers,
    filter_entities_by_patterns,
    generate_entity_id,
    generate_entity_patterns_for_feature,
    get_entities_for_device,
    get_entity_device_id,
    parse_entity_id,
)

__all__ = [
    # Entity helpers
    "EntityHelpers",
    "generate_entity_id",
    "parse_entity_id",
    "get_entity_device_id",
    "get_entities_for_device",
    "filter_entities_by_patterns",
    "generate_entity_patterns_for_feature",
    # Device helpers
    "find_ramses_device",
    "get_device_type",
    "validate_device_for_service",
    "get_all_device_ids",
    "ensure_ramses_cc_loaded",
    "get_device_capabilities",
    "filter_devices_by_capability",
    "get_device_supported_entities",
    "validate_device_entity_support",
    # Automation helpers
    "ExtrasBaseAutomation",
    # Common utilities - Validation
    "ValidationError",
    "RamsesValidator",
    "ValidationContext",
    "create_validation_context",
    "validate_device_id",
    "validate_humidity_values",
    "async_validate_entity_states",
]
