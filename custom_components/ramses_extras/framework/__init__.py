"""Ramses Extras Framework.

This package contains the core framework components that are shared
across all Ramses Extras features, including helpers, managers, and
base classes.

The framework provides:
- Entity management and registry
- Device utilities and parsers
- Automation patterns and lifecycle management
- Common utilities and base classes
"""

from .entity_registry import (
    entity_registry,
    get_all_entities,
    get_device_mapping,
    get_entity_config,
    get_entity_type,
    get_registry_statistics,
    register_entity,
)

__all__ = [
    "entity_registry",
    "get_entity_config",
    "get_device_mapping",
    "get_all_entities",
    "register_entity",
    "get_entity_type",
    "get_registry_statistics",
]
