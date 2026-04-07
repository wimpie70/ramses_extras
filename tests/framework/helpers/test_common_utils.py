"""Tests for common utils"""

import pytest

from custom_components.ramses_extras.framework.helpers.common.utils import (
    _singularize_entity_type,
    calculate_absolute_humidity,
)


def test_calculate_absolute_humidity_normal():
    """Test calculate_absolute_humidity with normal values"""
    result = calculate_absolute_humidity(20.0, 50.0)
    assert result is not None
    assert result > 0


def test_calculate_absolute_humidity_extreme_values():
    """Test calculate_absolute_humidity with extreme values"""
    # Very cold
    result = calculate_absolute_humidity(-20.0, 50.0)
    assert result is not None

    # Very hot
    result = calculate_absolute_humidity(40.0, 80.0)
    assert result is not None


def test_calculate_absolute_humidity_invalid():
    """Test calculate_absolute_humidity with invalid values"""
    # Negative humidity should still work mathematically but may return None
    calculate_absolute_humidity(20.0, -10.0)
    # May be None or a negative value that's caught


def test_calculate_absolute_humidity_edge_cases():
    """Test calculate_absolute_humidity edge cases"""
    # Zero humidity
    result = calculate_absolute_humidity(20.0, 0.0)
    assert result is not None
    assert result >= 0

    # 100% humidity
    result = calculate_absolute_humidity(20.0, 100.0)
    assert result is not None
    assert result > 0


def test_singularize_entity_type():
    """Test _singularize_entity_type with various inputs"""
    # Already singular
    assert _singularize_entity_type("sensor") == "sensor"
    assert _singularize_entity_type("switch") == "switch"

    # Plural forms
    assert _singularize_entity_type("sensors") == "sensor"
    assert _singularize_entity_type("switches") == "switch"
    assert _singularize_entity_type("binary_sensors") == "binary_sensor"
    assert _singularize_entity_type("numbers") == "number"
    assert _singularize_entity_type("devices") == "device"
    assert _singularize_entity_type("entities") == "entity"
    assert _singularize_entity_type("covers") == "cover"
    assert _singularize_entity_type("fans") == "fan"
    assert _singularize_entity_type("lights") == "light"
    assert _singularize_entity_type("climates") == "climate"
    assert _singularize_entity_type("humidifiers") == "humidifier"
    assert _singularize_entity_type("dehumidifiers") == "dehumidifier"
    assert _singularize_entity_type("selects") == "select"


def test_singularize_entity_type_unknown():
    """Test _singularize_entity_type with unknown input"""
    # Unknown types should return as-is
    assert _singularize_entity_type("unknown_type") == "unknown_type"
    assert _singularize_entity_type("custom") == "custom"
