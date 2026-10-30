"""Tests for common utility functions."""

from datetime import datetime

import pytest
from homeassistant.util import dt as dt_util

from custom_components.ramses_extras.framework.helpers.common.utils import (
    _singularize_entity_type,
    calculate_absolute_humidity,
    dtm_to_utc_str,
)


@pytest.fixture(autouse=True)
def _utc_default_tz():
    """Pin the HA default timezone so naive dtm expectations are stable."""
    old = dt_util.get_default_time_zone()
    dt_util.set_default_time_zone(dt_util.UTC)
    yield
    dt_util.set_default_time_zone(old)


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

    def test_calculate_absolute_humidity_zero_humidity(self):
        """Test calculation with zero humidity."""
        result = calculate_absolute_humidity(25.0, 0.0)
        assert result == 0.0

    def test_calculate_absolute_humidity_invalid_inputs(self):
        """Test calculation with invalid inputs."""
        # Invalid humidity (negative)
        result = calculate_absolute_humidity(25.0, -10.0)
        assert result is None

    def test_calculate_absolute_humidity_precision(self):
        """Test calculation precision and rounding."""
        result = calculate_absolute_humidity(22.5, 65.0)
        assert isinstance(result, float)
        assert result == 12.96


class TestSingularizeEntityType:
    """Test _singularize_entity_type function."""

    def test_singularize_common_types(self):
        """Test singularizing common entity types."""
        assert _singularize_entity_type("sensors") == "sensor"
        assert _singularize_entity_type("switches") == "switch"
        assert _singularize_entity_type("binary_sensors") == "binary_sensor"
        assert _singularize_entity_type("numbers") == "number"

    def test_singularize_already_singular(self):
        """Test with already singular types."""
        assert _singularize_entity_type("sensor") == "sensor"
        assert _singularize_entity_type("switch") == "switch"

    def test_singularize_unknown_type(self):
        """Test with unknown types (should return as is)."""
        assert _singularize_entity_type("unknown") == "unknown"
        assert _singularize_entity_type("") == ""


class TestDtmToUtcStr:
    """Test dtm_to_utc_str timestamp normalisation."""

    def test_naive_string_assumed_local(self):
        """Naive ISO strings are read as local time and emitted as UTC."""
        assert (
            dtm_to_utc_str("2026-01-20T10:00:00.000000")
            == "2026-01-20T10:00:00.000000+00:00"
        )

    def test_space_separated_naive_string(self):
        """HA-log style "YYYY-MM-DD HH:MM:SS" input is also normalised."""
        assert (
            dtm_to_utc_str("2026-01-20 10:00:00.123456")
            == "2026-01-20T10:00:00.123456+00:00"
        )

    def test_aware_utc_string_passthrough(self):
        """New-style +00:00 packet-log timestamps stay equivalent."""
        assert (
            dtm_to_utc_str("2026-10-28T09:30:00.000000+00:00")
            == "2026-10-28T09:30:00.000000+00:00"
        )

    def test_aware_non_utc_string_converted(self):
        """Non-UTC offsets are converted to UTC."""
        assert (
            dtm_to_utc_str("2026-01-20T12:00:00+02:00")
            == "2026-01-20T10:00:00.000000+00:00"
        )

    def test_naive_datetime_assumed_local(self):
        """Naive datetime objects (ramses_tx dt_now()) become UTC."""
        assert (
            dtm_to_utc_str(datetime(2026, 4, 18, 9, 0, 0))
            == "2026-04-18T09:00:00.000000+00:00"
        )

    def test_unparsable_returned_unchanged(self):
        """Best-effort: unparsable input passes through verbatim."""
        assert dtm_to_utc_str("not-a-datetime") == "not-a-datetime"
        assert dtm_to_utc_str("") == ""
