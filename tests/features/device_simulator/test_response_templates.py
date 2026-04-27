"""Tests for device_simulator response_templates module."""

from custom_components.ramses_extras.features.device_simulator.response_templates import (  # noqa: E501
    _coerce_hex_byte,
    build_dynamic_response,
)


def test_coerce_hex_byte_none():
    """Test _coerce_hex_byte with None value (covers line 19)."""
    result = _coerce_hex_byte(None)
    assert result == 0


def test_coerce_hex_byte_empty():
    """Test _coerce_hex_byte with empty string (covers line 19)."""
    result = _coerce_hex_byte("")
    assert result == 0


def test_coerce_hex_byte_invalid():
    """Test _coerce_hex_byte with invalid hex string (covers lines 22-23)."""
    result = _coerce_hex_byte("ZZ")
    assert result == 0


def test_coerce_hex_byte_valid():
    """Test _coerce_hex_byte with valid hex string."""
    result = _coerce_hex_byte("FF")
    assert result == 255


def test_build_dynamic_response_non_ctl():
    """Test build_dynamic_response for non-CTL device (covers line 67)."""
    result = build_dynamic_response("FAN", "000C", "00")
    assert result is None


def test_build_dynamic_response_ctl_30c9():
    """Test build_dynamic_response for CTL device with code 30C9."""
    result = build_dynamic_response("CTL", "30C9", "00")
    assert result is not None
    assert len(result) == 6  # zone_hex + temp_value (4 hex)


def test_build_dynamic_response_ctl_000c():
    """Test build_dynamic_response for CTL device with code 000C."""
    result = build_dynamic_response("CTL", "000C", "0000")
    assert result is not None
    assert len(result) == 12  # zone_hex + role_hex + suffix


def test_build_dynamic_response_ctl_2349():
    """Test build_dynamic_response for CTL device with code 2349."""
    result = build_dynamic_response("CTL", "2349", "00")
    assert result is not None
    assert (
        len(result) == 26
    )  # zone_hex (2) + temp_value (4) + mode (2) + duration (6) + until (12)


def test_build_dynamic_response_unrecognized_code():
    """Test build_dynamic_response for unrecognized code (covers line 67)."""
    result = build_dynamic_response("CTL", "9999", "00")
    assert result is None
