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

    Currently only CTL devices synthesize RP payloads for 000C/30C9 so that
    ramses_rf discovery can progress without needing a full device database.
    """

    slug_norm = (slug or "").upper()
    code_norm = (code or "").upper()
    payload = (request_payload or "").upper()

    if slug_norm != "CTL":
        return None

    if code_norm == "30C9":
        zone_hex = (payload[:2] or "00").zfill(2)
        zone_idx = _coerce_hex_byte(zone_hex)
        # Encode temperature in centi-degrees so each zone gets a deterministic value
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

    return None
