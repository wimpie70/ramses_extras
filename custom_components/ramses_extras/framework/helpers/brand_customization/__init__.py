"""Brand customization framework for Ramses Extras.

This module provides a framework for extracting and reusing brand-specific
customization patterns across different features and device types.

Common patterns extracted:
- Brand detection and model identification
- Model configuration and fallback handling
- Entity generation for brand-specific devices
- Behavior configuration and defaults
"""

from .core import (
    BrandCustomizerManager,
    ExtrasBrandCustomizer,
)
from .detection import (
    BrandPatterns,
    detect_brand_from_device,
    detect_brand_from_model,
)
from .entities import (
    EntityGenerationManager,
    StandardEntityTemplates,
)
from .models import (
    DefaultModelConfig,
    ModelConfigManager,
)

__all__ = [
    # Core framework
    "ExtrasBrandCustomizer",
    "BrandCustomizerManager",
    # Detection utilities
    "detect_brand_from_device",
    "detect_brand_from_model",
    "BrandPatterns",
    # Model configuration
    "ModelConfigManager",
    "DefaultModelConfig",
    # Entity generation
    "EntityGenerationManager",
    "StandardEntityTemplates",
]
