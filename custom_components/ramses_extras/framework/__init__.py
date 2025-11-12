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

# Import the standalone Ramses EntityRegistry as the main registry
from ..extras_registry import extras_registry as entity_registry

# Export the main registry for framework access
__all__ = [
    "entity_registry",
]
