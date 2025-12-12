"""Configuration management framework for Ramses Extras.

This module provides reusable configuration utilities that are shared across
all features, including configuration validation, schema generation, and
default configuration templates.
"""

from .core import ExtrasConfigManager
from .schema import ConfigSchema
from .validation import ConfigValidator

__all__ = [
    "ExtrasConfigManager",
    "ConfigValidator",
    "ConfigSchema",
]
