"""Brand detection utilities for Ramses Extras framework.

This module provides utilities for detecting device brands from device objects
or model strings, extracting common patterns from existing brand detection logic.
"""

import logging
from typing import Any

from .models import DefaultModelConfig

_LOGGER = logging.getLogger(__name__)


class BrandPatterns:
    """Container for brand detection patterns.

    This class defines the patterns used to detect different device brands
    from model strings or device properties.
    """

    # Brand detection patterns (model string substrings to match)
    BRAND_PATTERNS = {
        "orcon": ["orcon", "soler & palau"],
        "zehnder": ["zehnder", "comfoair"],
        "generic": [],  # Default for unknown brands
    }

    @classmethod
    def get_brand_patterns(cls, brand_name: str) -> list[str]:
        """Get detection patterns for a specific brand.

        Args:
            brand_name: Brand identifier

        Returns:
            List of patterns to match
        """
        return cls.BRAND_PATTERNS.get(brand_name, [])

    @classmethod
    def add_brand_pattern(cls, brand_name: str, pattern: str) -> None:
        """Add a new detection pattern for a brand.

        Args:
            brand_name: Brand identifier
            pattern: Pattern to add
        """
        if brand_name not in cls.BRAND_PATTERNS:
            cls.BRAND_PATTERNS[brand_name] = []
        if pattern not in cls.BRAND_PATTERNS[brand_name]:
            cls.BRAND_PATTERNS[brand_name].append(pattern)
            _LOGGER.debug(f"Added pattern '{pattern}' for brand '{brand_name}'")

    @classmethod
    def get_all_brands(cls) -> list[str]:
        """Get list of all supported brands.

        Returns:
            List of supported brand names
        """
        return list(cls.BRAND_PATTERNS.keys())


def detect_brand_from_device(device: Any) -> str | None:
    """Detect device brand from device object.

    Args:
        device: Device object with model property

    Returns:
        Brand identifier or None if not detected
    """
    model = getattr(device, "model", None)
    if not model:
        _LOGGER.debug("Device has no model attribute")
        return None

    return detect_brand_from_model(model)


def detect_brand_from_model(model: str) -> str | None:
    """Detect device brand from model string.

    This function extracts the common brand detection logic from
    existing customizers and provides a centralized implementation.

    Args:
        model: Device model string

    Returns:
        Brand identifier or None if not detected
    """
    if not model:
        _LOGGER.debug("Model string is empty")
        return None

    model_lower = model.lower()

    # Check each brand's patterns
    for brand_name, patterns in BrandPatterns.BRAND_PATTERNS.items():
        # Skip generic brand as it's the fallback
        if brand_name == "generic":
            continue

        for pattern in patterns:
            if pattern.lower() in model_lower:
                _LOGGER.debug(
                    f"Detected brand '{brand_name}' from pattern '{pattern}' "
                    f"in model '{model}'"
                )
                return brand_name

    # Log that we couldn't detect the brand
    _LOGGER.debug(f"Could not detect brand from model '{model}'")

    # Return None to indicate no specific brand was detected
    # The calling code can decide whether to use a generic approach
    return None


def detect_brand_with_fallback(model: str) -> str:
    """Detect device brand with fallback to generic.

    Args:
        model: Device model string

    Returns:
        Brand identifier (generic if not detected)
    """
    brand = detect_brand_from_model(model)
    return brand if brand is not None else "generic"


def is_device_brand_supported(brand_name: str) -> bool:
    """Check if a brand is supported by the framework.

    Args:
        brand_name: Brand identifier

    Returns:
        True if brand is supported, False otherwise
    """
    return brand_name in BrandPatterns.BRAND_PATTERNS


def get_brand_detection_confidence(model: str, brand_name: str) -> float:
    """Get confidence score for brand detection.

    Args:
        model: Device model string
        brand_name: Brand identifier to check

    Returns:
        Confidence score between 0.0 and 1.0
    """
    if not model or not brand_name:
        return 0.0

    patterns = BrandPatterns.get_brand_patterns(brand_name)
    if not patterns:
        return 0.0

    model_lower = model.lower()
    matches = 0

    for pattern in patterns:
        if pattern.lower() in model_lower:
            matches += 1

    # Calculate confidence based on pattern matches
    confidence = matches / len(patterns) if patterns else 0.0
    return min(confidence, 1.0)


def get_best_brand_match(model: str) -> tuple[str, float]:
    """Get the best brand match for a model string.

    Args:
        model: Device model string

    Returns:
        Tuple of (brand_name, confidence_score)
    """
    if not model:
        return "generic", 0.0

    best_brand = "generic"
    best_confidence = 0.0

    # Check each supported brand
    for brand_name in BrandPatterns.get_all_brands():
        # Skip generic in confidence calculation
        if brand_name == "generic":
            continue

        confidence = get_brand_detection_confidence(model, brand_name)
        if confidence > best_confidence:
            best_confidence = confidence
            best_brand = brand_name

    # If no good match found, use generic
    if best_confidence < 0.1:  # Threshold for considering a match
        return "generic", 0.0

    _LOGGER.debug(
        f"Best brand match for '{model}': '{best_brand}' "
        f"(confidence: {best_confidence:.2f})"
    )
    return best_brand, best_confidence


# Convenience functions for specific brands


def is_orcon_device(device: Any) -> bool:
    """Check if device is an Orcon brand device.

    Args:
        device: Device object

    Returns:
        True if device is Orcon brand, False otherwise
    """
    return detect_brand_from_device(device) == "orcon"


def is_zehnder_device(device: Any) -> bool:
    """Check if device is a Zehnder brand device.

    Args:
        device: Device object

    Returns:
        True if device is Zehnder brand, False otherwise
    """
    return detect_brand_from_device(device) == "zehnder"


def is_generic_device(device: Any) -> bool:
    """Check if device is a generic/unknown brand device.

    Args:
        device: Device object

    Returns:
        True if device is generic/unknown brand, False otherwise
    """
    brand = detect_brand_from_device(device)
    return brand is None or brand == "generic"


def detect_and_register_model(model: str, brand_name: str) -> dict[str, Any]:
    """Detect and register a model configuration.

    Args:
        model: Device model string
        brand_name: Brand identifier

    Returns:
        Model configuration dictionary
    """
    # This could be extended to automatically register new models
    # For now, just return the default configuration
    return DefaultModelConfig.get_fallback_config(model, brand_name)
