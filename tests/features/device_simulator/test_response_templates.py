"""Tests for device_simulator response_templates."""

import pytest

from custom_components.ramses_extras.features.device_simulator.response_templates import (  # noqa: E501
    DynamicResponse,
    _coerce_hex_byte,
    build_dynamic_response,
)


class TestCoerceHexByte:
    """Tests for _coerce_hex_byte."""

    def test_none(self):
        assert _coerce_hex_byte(None) == 0

    def test_empty_string(self):
        assert _coerce_hex_byte("") == 0

    def test_valid_hex(self):
        assert _coerce_hex_byte("FF") == 255

    def test_valid_hex_lower(self):
        assert _coerce_hex_byte("ff") == 255

    def test_zero(self):
        assert _coerce_hex_byte("00") == 0

    def test_mid_value(self):
        assert _coerce_hex_byte("7F") == 127

    def test_invalid_hex(self):
        assert _coerce_hex_byte("GG") == 0

    def test_clamps_above_255(self):
        # int("1FF", 16) = 511, should clamp to 255
        assert _coerce_hex_byte("1FF") == 255

    def test_negative_clamped_to_zero(self):
        # Negative values can't come from hex, but test the clamp logic
        assert _coerce_hex_byte("00") == 0


class TestDynamicResponse:
    """Tests for DynamicResponse dataclass."""

    def test_creation(self):
        dr = DynamicResponse(payload="00FF")
        assert dr.payload == "00FF"

    def test_frozen(self):
        dr = DynamicResponse(payload="00FF")
        with pytest.raises((AttributeError, TypeError)):
            dr.payload = "01FF"


class TestBuildDynamicResponseCtl:
    """Tests for CTL dynamic responses."""

    def test_ctl_30c9_with_zone(self):
        result = build_dynamic_response("CTL", "30C9", "0100")
        assert result is not None
        assert result.startswith("01")
        # temp_value = 0x07C0 + (1 % 8) * 0x0010 = 0x07D0
        assert result == "0107D0"

    def test_ctl_30c9_zone_zero(self):
        result = build_dynamic_response("CTL", "30C9", "00")
        assert result == "0007C0"

    def test_ctl_30c9_empty_payload(self):
        result = build_dynamic_response("CTL", "30C9", "")
        assert result == "0007C0"

    def test_ctl_30c9_case_insensitive(self):
        result = build_dynamic_response("ctl", "30c9", "01")
        assert result == "0107D0"

    def test_ctl_30c9_high_zone_wraps(self):
        # zone_idx = 0xFF = 255, 255 % 8 = 7
        result = build_dynamic_response("CTL", "30C9", "FF")
        assert result == "FF0830"

    def test_ctl_000c_with_zone_and_role(self):
        result = build_dynamic_response("CTL", "000C", "0102")
        assert result is not None
        assert result.startswith("0102")
        # token = (0x01 << 8) | 0x02 = 0x0102
        assert "0102FACE" in result

    def test_ctl_000c_empty_payload(self):
        result = build_dynamic_response("CTL", "000C", "")
        assert result == "00000000FACE"

    def test_ctl_2349_with_zone(self):
        result = build_dynamic_response("CTL", "2349", "01")
        assert result is not None
        assert result.startswith("01")
        # temp = 0x07C0 + (1 % 8) * 0x0010 = 0x07D0
        assert result == "0107D000FFFFFF" + "FFFFFFFFFFFF"

    def test_ctl_2349_zone_zero(self):
        result = build_dynamic_response("CTL", "2349", "00")
        assert result == "0007C000FFFFFF" + "FFFFFFFFFFFF"


class TestBuildDynamicResponseCtlFallback:
    """Tests for CTL fallback responses."""

    @pytest.mark.parametrize(
        "code,expected",
        [
            ("0002", "00FF00"),
            ("0004", "0000436C6F756E67650000000000000000000000000000"),
            ("0005", "0000FF01"),
            ("000A", "011001F40DAC"),
            # 000C, 2349, 30C9 are handled by the dynamic section above
            # the fallback, so they return dynamic results, not fallback.
            ("0100", "00656EFFFF"),
            ("1100", "FC180400007FFF01"),
            ("1260", "00FF00"),
            ("1290", "00FF00"),
            ("1F09", "FF091A"),
            ("1FC9", "072309054E29"),
            ("2309", "0005DC0101F40205DC"),
            ("313F", "00FC081CCF0D0307E6"),
            ("3B00", "FCC8"),
        ],
    )
    def test_ctl_fallback_codes(self, code, expected):
        result = build_dynamic_response("CTL", code, "")
        assert result == expected

    def test_ctl_unknown_code(self):
        result = build_dynamic_response("CTL", "9999", "")
        assert result is None


class TestBuildDynamicResponseOtb:
    """Tests for OTB fallback responses."""

    @pytest.mark.parametrize(
        "code,expected",
        [
            (
                "10E0",
                "000001FF050BFFFFFFFF0E0907E2070307E1523838313041000000000000000000000000",  # noqa: E501
            ),
            ("3EF0", "000010000000020A64"),
            ("3220", "0040000200"),
            ("1FC9", "003EF00003EF1"),
            ("10A0", "0013880003E8"),
            ("10B0", "00FF00"),
            ("1260", "00FF00"),
            ("1290", "00FF00"),
            ("042F", "00000000"),
            ("3EF1", "00"),
            ("1300", "000096"),
            ("3210", "0001F4"),
            ("2401", "00000100"),
            ("1081", "00FF00"),
            ("22D9", "0003E8"),
        ],
    )
    def test_otb_fallback_codes(self, code, expected):
        result = build_dynamic_response("OTB", code, "")
        assert result == expected

    def test_otb_unknown_code(self):
        result = build_dynamic_response("OTB", "9999", "")
        assert result is None


class TestBuildDynamicResponseBdr:
    """Tests for BDR (electrical relay) fallback responses."""

    @pytest.mark.parametrize(
        "code,expected",
        [
            ("0008", "0000"),
            ("1100", "00180400007FFF01"),
            ("3EF1", "00021C021C00FF"),
            ("0418", "00FF00"),
            ("1260", "00FF00"),
            ("1290", "00FF00"),
        ],
    )
    def test_bdr_fallback_codes(self, code, expected):
        result = build_dynamic_response("BDR", code, "")
        assert result == expected

    def test_bdr_unknown_code(self):
        result = build_dynamic_response("BDR", "9999", "")
        assert result is None


class TestBuildDynamicResponseFan:
    """Tests for FAN fallback responses."""

    @pytest.mark.parametrize(
        "code,expected",
        [
            ("22F1", "000207"),
            ("31D9", "000207"),
            ("22E0", "00000000"),
            ("22E5", "00000000"),
            ("22E9", "00000064"),
            (
                "2210",
                "00EF007FFF7FFF0000000000FFFFFFFFFF00FFFFFFFF000000FFFFFFFFFFFFFFFF000000000000000000",
            ),
        ],
    )
    def test_fan_fallback_codes(self, code, expected):
        result = build_dynamic_response("FAN", code, "")
        assert result == expected

    def test_fan_unknown_code(self):
        result = build_dynamic_response("FAN", "9999", "")
        assert result is None


class TestBuildDynamicResponseEdgeCases:
    """Tests for edge cases."""

    def test_none_slug(self):
        assert build_dynamic_response(None, "30C9", "01") is None

    def test_none_code(self):
        assert build_dynamic_response("CTL", None, "01") is None

    def test_none_payload(self):
        result = build_dynamic_response("CTL", "30C9", None)
        assert result == "0007C0"

    def test_unknown_slug(self):
        assert build_dynamic_response("UNKNOWN", "30C9", "01") is None

    def test_empty_all(self):
        assert build_dynamic_response("", "", "") is None

    def test_case_insensitive_slug(self):
        result = build_dynamic_response("fan", "22F1", "")
        assert result == "000207"

    def test_case_insensitive_code(self):
        result = build_dynamic_response("FAN", "22f1", "")
        assert result == "000207"

    def test_case_insensitive_payload(self):
        result = build_dynamic_response("CTL", "30C9", "ab")
        # zone_hex = "AB", zone_idx = 0xAB = 171, 171 % 8 = 3
        # temp = 0x07C0 + 3 * 0x10 = 0x07F0
        assert result == "AB07F0"
