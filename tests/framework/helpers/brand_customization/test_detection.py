"""Tests for Brand Customization Detection utilities."""

import logging
from unittest.mock import MagicMock

import pytest

from custom_components.ramses_extras.framework.helpers.brand_customization.detection import (  # noqa: E501
    BrandPatterns,
    detect_brand_from_device,
    detect_brand_from_model,
    detect_brand_with_fallback,
    get_best_brand_match,
    get_brand_detection_confidence,
    is_device_brand_supported,
    is_generic_device,
    is_orcon_device,
    is_zehnder_device,
)


class TestBrandPatterns:
    """Test cases for BrandPatterns."""

    def test_get_brand_patterns(self):
        """Test getting brand patterns."""
        patterns = BrandPatterns.get_brand_patterns("orcon")
        assert "orcon" in patterns
        assert "soler & palau" in patterns

        assert BrandPatterns.get_brand_patterns("nonexistent") == []

    def test_add_brand_pattern(self):
        """Test adding brand pattern."""
        BrandPatterns.add_brand_pattern("new_brand", "new_pattern")
        assert "new_pattern" in BrandPatterns.get_brand_patterns("new_brand")

        # Test adding existing pattern (no-op)
        initial_count = len(BrandPatterns.get_brand_patterns("new_brand"))
        BrandPatterns.add_brand_pattern("new_brand", "new_pattern")
        assert len(BrandPatterns.get_brand_patterns("new_brand")) == initial_count

    def test_get_all_brands(self):
        """Test getting all brands."""
        brands = BrandPatterns.get_all_brands()
        assert "orcon" in brands
        assert "zehnder" in brands
        assert "generic" in brands


class TestDetectionUtilities:
    """Test cases for detection utilities."""

    def test_detect_brand_from_model(self, caplog):
        """Test detecting brand from model string."""
        caplog.set_level(logging.DEBUG)

        assert detect_brand_from_model("Orcon HRV300") == "orcon"
        assert detect_brand_from_model("Zehnder Q350") == "zehnder"
        assert detect_brand_from_model("ComfoAir Q450") == "zehnder"
        assert detect_brand_from_model("Unknown") is None
        assert detect_brand_from_model("") is None

    def test_detect_brand_from_device(self):
        """Test detecting brand from device object."""
        device = MagicMock()
        device.model = "Orcon HRV400"
        assert detect_brand_from_device(device) == "orcon"

        device.model = None
        assert detect_brand_from_device(device) is None

        del device.model
        assert detect_brand_from_device(device) is None

    def test_detect_brand_with_fallback(self):
        """Test detecting brand with fallback."""
        assert detect_brand_with_fallback("Orcon HRV") == "orcon"
        assert detect_brand_with_fallback("Unknown") == "generic"

    def test_is_brand_supported(self):
        """Test checking if brand is supported."""
        assert is_device_brand_supported("orcon") is True
        assert is_device_brand_supported("zehnder") is True
        assert is_device_brand_supported("nonexistent") is False

    def test_get_brand_detection_confidence(self):
        """Test getting confidence score."""
        # Exact match (one pattern matches)
        assert get_brand_detection_confidence("Orcon HRV", "orcon") == 0.5
        # No match
        assert get_brand_detection_confidence("Zehnder HRV", "orcon") == 0.0
        # Empty inputs
        assert get_brand_detection_confidence("", "orcon") == 0.0
        assert get_brand_detection_confidence("Orcon", "") == 0.0
        assert get_brand_detection_confidence("Orcon", "nonexistent") == 0.0

    def test_get_best_brand_match(self):
        """Test getting best brand match."""
        brand, confidence = get_best_brand_match("Orcon HRV")
        assert brand == "orcon"
        assert confidence > 0

        brand, confidence = get_best_brand_match("Zehnder Q350")
        assert brand == "zehnder"
        assert confidence > 0

        brand, confidence = get_best_brand_match("Unknown")
        assert brand == "generic"
        assert confidence == 0.0

        assert get_best_brand_match("") == ("generic", 0.0)

    def test_convenience_functions(self):
        """Test convenience brand check functions."""
        device = MagicMock()

        device.model = "Orcon HRV"
        assert is_orcon_device(device) is True
        assert is_zehnder_device(device) is False
        assert is_generic_device(device) is False

        device.model = "Zehnder Q350"
        assert is_orcon_device(device) is False
        assert is_zehnder_device(device) is True
        assert is_generic_device(device) is False

        device.model = "Unknown"
        assert is_orcon_device(device) is False
        assert is_zehnder_device(device) is False
        assert is_generic_device(device) is True
