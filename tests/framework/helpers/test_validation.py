"""Tests for common validation functions"""

import pytest

from custom_components.ramses_extras.framework.helpers.common.validation import (
    RamsesValidator,
    ValidationError,
)


def test_validate_device_id_valid():
    """Test validate_device_id with valid formats"""
    assert RamsesValidator.validate_device_id("32:153289") is True
    assert RamsesValidator.validate_device_id("32_153289") is True
    assert RamsesValidator.validate_device_id("32") is True
    assert RamsesValidator.validate_device_id("18:123456") is True


def test_validate_device_id_invalid():
    """Test validate_device_id with invalid formats"""
    assert RamsesValidator.validate_device_id("") is False
    assert RamsesValidator.validate_device_id("invalid") is False
    assert RamsesValidator.validate_device_id("32:abc") is False
    assert RamsesValidator.validate_device_id("abc:123") is False


def test_validate_entity_id_valid():
    """Test validate_entity_id with valid formats"""
    assert RamsesValidator.validate_entity_id("sensor.temperature") is True
    assert RamsesValidator.validate_entity_id("switch.living_room") is True
    assert RamsesValidator.validate_entity_id("binary_sensor.motion") is True
    assert RamsesValidator.validate_entity_id("climate.thermostat") is True


def test_validate_entity_id_invalid():
    """Test validate_entity_id with invalid formats"""
    assert RamsesValidator.validate_entity_id("") is False
    assert RamsesValidator.validate_entity_id("invalid") is False
    assert RamsesValidator.validate_entity_id("no_dot_here") is False
    assert RamsesValidator.validate_entity_id(".startswithdot") is False


def test_validation_error_exception():
    """Test ValidationError can be raised and caught"""
    with pytest.raises(ValidationError):
        raise ValidationError("Test error message")
