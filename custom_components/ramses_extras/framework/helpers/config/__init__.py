"""Configuration management framework for Ramses Extras.

This module provides reusable configuration utilities that are shared across
all features, including configuration validation, schema generation, and
default configuration templates.
"""

from .core import ExtrasConfigManager
from .export import build_exportable_config, export_config_to_yaml
from .import_full import (
    merge_full_config,
    parse_full_config_yaml,
    validate_full_config_import,
)
from .migration import migrate_to_canonical_config
from .model import find_areas_for_zone, find_entities_for_zone
from .validation import ConfigValidator

__all__ = [
    "ExtrasConfigManager",
    "ConfigValidator",
    "build_exportable_config",
    "export_config_to_yaml",
    "find_areas_for_zone",
    "find_entities_for_zone",
    "merge_full_config",
    "migrate_to_canonical_config",
    "parse_full_config_yaml",
    "validate_full_config_import",
]
