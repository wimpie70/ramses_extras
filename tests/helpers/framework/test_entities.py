# tests/helpers/framework/test_entities.py
"""Test entity helper functions."""

import math

import pytest

from custom_components.ramses_extras.framework.helpers.entities import (
    calculate_absolute_humidity,
    validate_humidity_value,
    validate_temperature_value,
)


class TestCalculateAbsoluteHumidity:
    """Test calculate_absolute_humidity function."""

    def test_calculate_absolute_humidity_normal_conditions(self):
        """Test calculation with normal temperature and humidity."""
        # Standard room conditions: 20°C, 50% RH
        result = calculate_absolute_humidity(20.0, 50.0)
        assert result == 8.63

    def test_calculate_absolute_humidity_high_temperature(self):
        """Test calculation with high temperature and humidity."""
        # Hot and humid: 30°C, 80% RH
        result = calculate_absolute_humidity(30.0, 80.0)
        assert result == 24.21

    def test_calculate_absolute_humidity_low_temperature(self):
        """Test calculation with low temperature and humidity."""
        # Cold and dry: 0°C, 20% RH
        result = calculate_absolute_humidity(0.0, 20.0)
        assert result == 0.97

    def test_calculate_absolute_humidity_edge_cases(self):
        """Test calculation with edge case values."""
        # Very dry air
        result = calculate_absolute_humidity(25.0, 1.0)
        assert result == 0.23

        # Very humid air
        result = calculate_absolute_humidity(25.0, 99.0)
        assert result == 22.75

    def test_calculate_absolute_humidity_zero_humidity(self):
        """Test calculation with zero humidity."""
        result = calculate_absolute_humidity(25.0, 0.0)
        assert result == 0.0

    def test_calculate_absolute_humidity_invalid_inputs(self):
        """Test calculation with invalid inputs."""
        # The function doesn't validate input ranges, just tries to calculate
        # Invalid temperature (very low)
        result = calculate_absolute_humidity(-100.0, 50.0)
        assert result == 0.0  # Function allows extreme temperatures

        # Invalid humidity (negative)
        result = calculate_absolute_humidity(25.0, -10.0)
        assert result is None  # Invalid humidity causes calculation issues

        # Invalid humidity (too high)
        result = calculate_absolute_humidity(25.0, 150.0)
        assert result == 34.47  # Function allows humidity > 100%

    def test_calculate_absolute_humidity_mathematical_edge_cases(self):
        """Test mathematical edge cases."""
        # Very low temperature (approaching absolute zero)
        result = calculate_absolute_humidity(-273.0, 50.0)
        assert result is not None  # Function allows extreme temperatures

        # High temperature
        result = calculate_absolute_humidity(100.0, 50.0)
        assert result is not None

    def test_calculate_absolute_humidity_precision(self):
        """Test calculation precision and rounding."""
        result = calculate_absolute_humidity(22.5, 65.0)
        # Should be rounded to 2 decimal places
        assert isinstance(result, float)
        assert result == 12.96


class TestValidateHumidityValue:
    """Test validate_humidity_value function."""

    def test_validate_humidity_value_valid_range(self):
        """Test validation with valid humidity values."""
        assert validate_humidity_value(0.0, "test_entity") is True
        assert validate_humidity_value(50.0, "test_entity") is True
        assert validate_humidity_value(100.0, "test_entity") is True
        assert validate_humidity_value(0.1, "test_entity") is True
        assert validate_humidity_value(99.9, "test_entity") is True

    def test_validate_humidity_value_invalid_range(self):
        """Test validation with invalid humidity values."""
        assert validate_humidity_value(-1.0, "test_entity") is False
        assert validate_humidity_value(-10.0, "test_entity") is False
        assert validate_humidity_value(100.1, "test_entity") is False
        assert validate_humidity_value(150.0, "test_entity") is False

    def test_validate_humidity_value_none_value(self):
        """Test validation with None value."""
        assert validate_humidity_value(None, "test_entity") is False

    def test_validate_humidity_value_boundary_values(self):
        """Test validation with boundary values."""
        # Exact boundaries should be valid
        assert validate_humidity_value(0.0, "test_entity") is True
        assert validate_humidity_value(100.0, "test_entity") is True

        # Slightly outside boundaries should be invalid
        assert validate_humidity_value(-0.1, "test_entity") is False
        assert validate_humidity_value(100.1, "test_entity") is False


class TestValidateTemperatureValue:
    """Test validate_temperature_value function."""

    def test_validate_temperature_value_valid_range(self):
        """Test validation with valid temperature values."""
        assert validate_temperature_value(-50.0, "test_entity") is True
        assert validate_temperature_value(0.0, "test_entity") is True
        assert validate_temperature_value(25.0, "test_entity") is True
        assert validate_temperature_value(100.0, "test_entity") is True
        assert validate_temperature_value(-49.9, "test_entity") is True
        assert validate_temperature_value(99.9, "test_entity") is True

    def test_validate_temperature_value_invalid_range(self):
        """Test validation with invalid temperature values."""
        assert validate_temperature_value(-50.1, "test_entity") is False
        assert validate_temperature_value(-100.0, "test_entity") is False
        assert validate_temperature_value(100.1, "test_entity") is False
        assert validate_temperature_value(150.0, "test_entity") is False

    def test_validate_temperature_value_none_value(self):
        """Test validation with None value."""
        assert validate_temperature_value(None, "test_entity") is False

    def test_validate_temperature_value_boundary_values(self):
        """Test validation with boundary values."""
        # Exact boundaries should be valid
        assert validate_temperature_value(-50.0, "test_entity") is True
        assert validate_temperature_value(100.0, "test_entity") is True

        # Slightly outside boundaries should be invalid
        assert validate_temperature_value(-50.1, "test_entity") is False
        assert validate_temperature_value(100.1, "test_entity") is False
