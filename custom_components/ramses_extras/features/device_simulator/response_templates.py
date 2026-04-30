from __future__ import annotations

from dataclasses import dataclass

"""Helpers for synthesizing dynamic RP payloads."""


@dataclass(frozen=True)
class DynamicResponse:
    """Structured dynamic response (for future extensibility)."""

    payload: str


def _coerce_hex_byte(value: str | None) -> int:
    """Convert a 1-byte hex string into an int with graceful fallback."""

    if not value:
        return 0
    try:
        return max(0, min(255, int(value, 16)))
    except ValueError:
        return 0


def build_dynamic_response(
    slug: str | None, code: str | None, request_payload: str | None
) -> str | None:
    """Return a minimal synthetic payload when the DB lacks a template.

    Currently synthesizes RP payloads for:
    - CTL: 000C, 30C9, 2349 (zone/heating discovery)
    - FAN: 22F1, 31D9, 22E0, 22E5, 22E9 (HVAC discovery fallbacks)
    """

    slug_norm = (slug or "").upper()
    code_norm = (code or "").upper()
    payload = (request_payload or "").upper()

    # ─────────────────────────────────────────────────────────────────────────
    # CTL (Heat) responses
    # ─────────────────────────────────────────────────────────────────────────
    if slug_norm == "CTL":
        if code_norm == "30C9":
            zone_hex = (payload[:2] or "00").zfill(2)
            zone_idx = _coerce_hex_byte(zone_hex)
            # Encode temperature in centi-degrees so each zone gets a deterministic value  # noqa: E501
            temp_value = 0x07C0 + (zone_idx % 8) * 0x0010  # ~20°C baseline
            return f"{zone_hex}{temp_value:04X}"

        if code_norm == "000C":
            zone_hex = (payload[:2] or "00").zfill(2)
            role_hex = (payload[2:4] or "00").zfill(2)
            token = (_coerce_hex_byte(zone_hex) << 8) | _coerce_hex_byte(role_hex)
            suffix = f"{token:04X}FACE"
            return f"{zone_hex}{role_hex}{suffix}"

        if code_norm == "2349":
            zone_hex = (payload[:2] or "00").zfill(2)
            zone_idx = _coerce_hex_byte(zone_hex)
            temp_value = 0x07C0 + (zone_idx % 8) * 0x0010
            # Follow schedule (mode 00), indefinite (duration/expiry all F)
            return (
                f"{zone_hex}{temp_value:04X}00"  # zone + setpoint + mode
                f"FFFFFF"  # duration sentinel
                f"FFFFFFFFFFFF"  # until sentinel (no expiry)
            )

    # ─────────────────────────────────────────────────────────────────────────
    # CTL (Heat) responses - fallback when DB entry missing
    # ─────────────────────────────────────────────────────────────────────────
    if slug_norm == "CTL":
        if code_norm == "0002":
            # Device status: minimal response
            return "00FF00"

        if code_norm == "0004":
            # Zone name: return generic zone name
            return "0000436C6F756E67650000000000000000000000000000"

        if code_norm == "0005":
            # Zone config: minimal response
            return "0000FF01"

        if code_norm == "000A":
            # Zone setpoint: return 20°C (0x07C0)
            return "011001F40DAC"

        if code_norm == "000C":
            # Zone mode: minimal response
            return "00FF00"

        if code_norm == "0100":
            # Locale: en_GB
            return "00656EFFFF"

        if code_norm == "1100":
            # Relay demand: 0% demand
            return "FC180400007FFF01"

        if code_norm == "1260":
            # DHW setpoint: minimal response
            return "00FF00"

        if code_norm == "1290":
            # DHW mode: minimal response
            return "00FF00"

        if code_norm == "1F09":
            # Sync interval: ~1200s
            return "FF091A"

        if code_norm == "1FC9":
            # Multi-code response
            return "072309054E29"

        if code_norm == "2309":
            # Zone demand: minimal response
            return "0005DC0101F40205DC"

        if code_norm == "2349":
            # Zone setpoint override: minimal response
            return "0007D000FFFFFF"

        if code_norm == "30C9":
            # Zone temperature: ~20°C
            return "0007BB"

        if code_norm == "313F":
            # Clock/programme: minimal response
            return "00FC081CCF0D0307E6"

        if code_norm == "3B00":
            # Boiler fault: no fault
            return "FCC8"

    # ─────────────────────────────────────────────────────────────────────────
    # OTB (Heat) responses - fallback when DB entry missing
    # ─────────────────────────────────────────────────────────────────────────
    if slug_norm == "OTB":
        if code_norm == "10E0":
            # Device info: R8810/R8820
            return "000001FF050BFFFFFFFF0E0907E2070307E1523838313041000000000000000000000000"  # noqa: E501

        if code_norm == "3EF0":
            # OpenTherm status: minimal response
            return "00"

        if code_norm == "3220":
            # OpenTherm diagnostic: minimal response
            return "00401200F8"

        if code_norm == "1FC9":
            # Multi-code response
            return "003EF00003EF1"

        if code_norm == "10A0":
            # Outside air temperature: ~19°C
            return "0013880003E8"

        if code_norm == "10B0":
            # Return water temperature: minimal response
            return "00FF00"

        if code_norm == "1260":
            # Boiler setpoint: minimal response
            return "00FF00"

        if code_norm == "1290":
            # Boiler mode: minimal response
            return "00FF00"

        if code_norm == "042F":
            # Device status: minimal response
            return "00000000"

        if code_norm == "3EF1":
            # Extended OpenTherm: minimal response
            return "00"

    # ─────────────────────────────────────────────────────────────────────────
    # FAN (HVAC) responses - fallback when DB entry missing
    # ─────────────────────────────────────────────────────────────────────────
    if slug_norm == "FAN":
        if code_norm == "22F1":
            # Fan mode: return orcon scheme medium speed (0x0207)
            # RP format: ^00[0-9A-F]{4}$
            return "000207"

        if code_norm == "31D9":
            # Fan state: return orcon scheme medium speed (0x0207)
            # RP format: ^(00|01|15|16|17|21)[0-9A-F]{4}(([0-9A-F]{2})(00|20){0,12}(00|01|04|08)?)?$  # noqa: E501
            return "000207"

        if code_norm == "22E0":
            # Bypass position: 0% open
            # RP format: ^00[0-9A-F]{6}$
            return "00000000"

        if code_norm == "22E5":
            # Remaining minutes: 0 minutes
            # RP format: ^00[0-9A-F]{6}$
            return "00000000"

        if code_norm == "22E9":
            # Speed cap: 100%
            # RP format: ^00[0-9A-F]{6}$
            return "00000064"

        if code_norm == "2210":
            # Air quality / exhaust fan speed: minimal 42-byte response
            # RP format: ^00[0-9A-F]{82}$ (42 bytes = 84 hex chars)
            return "00EF007FFF7FFF0000000000FFFFFFFFFF00FFFFFFFF000000FFFFFFFFFFFFFFFF000000000000000000"  # noqa: E501

    return None
