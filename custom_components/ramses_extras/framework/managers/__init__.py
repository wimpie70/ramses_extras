"""Framework managers module.

This module provides centralized managers for Ramses Extras framework,
including feature management, resource management, and coordination.
"""

from .feature_manager import (
    FeatureManager,
    get_feature_manager,
    reset_feature_manager,
)

__all__ = [
    "FeatureManager",
    "get_feature_manager",
    "reset_feature_manager",
]
