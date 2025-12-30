"""Tests for framework/helpers/common/utils.py."""

import pytest

from custom_components.ramses_extras.framework.helpers.common.utils import (
    _singularize_entity_type,
    calculate_absolute_humidity,
)


def test_calculate_absolute_humidity():
    """Test absolute humidity calculation."""
    # Test normal values
    # 20C, 50% RH -> ~8.65 g/m3
    ah = calculate_absolute_humidity(20.0, 50.0)
    assert ah is not None
    assert 8.6 <= ah <= 8.7

    # Test edge cases
    assert calculate_absolute_humidity(0.0, 0.0) == 0.0
    assert calculate_absolute_humidity(100.0, 100.0) is not None

    # Test error cases (negative humidity)
    assert calculate_absolute_humidity(20.0, -10.0) is None

    # Test exception handling (ZeroDivisionError at absolute zero)
    assert calculate_absolute_humidity(-273.15, 50.0) is None


def test_singularize_entity_type():
    """Test singularization of entity types."""
    assert _singularize_entity_type("sensors") == "sensor"
    assert _singularize_entity_type("sensor") == "sensor"
    assert _singularize_entity_type("switches") == "switch"
    assert _singularize_entity_type("switch") == "switch"
    assert _singularize_entity_type("binary_sensors") == "binary_sensor"
    assert _singularize_entity_type("numbers") == "number"
    assert _singularize_entity_type("devices") == "device"
    assert _singularize_entity_type("entities") == "entity"
    assert _singularize_entity_type("fans") == "fan"
    assert _singularize_entity_type("climates") == "climate"
    assert _singularize_entity_type("unknown") == "unknown"
