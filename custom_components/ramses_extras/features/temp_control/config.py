"""Temp control configuration helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from custom_components.ramses_extras.framework.helpers.config.migration import (
    get_migrated_feature_section,
)

from .const import TEMP_CONTROL_DEFAULTS


@dataclass(frozen=True, slots=True)
class TempControlSettings:
    comfort_delta_activate: float
    comfort_delta_deactivate: float
    supply_cooler_delta_activate: float
    supply_cooler_delta_deactivate: float
    min_supply_temp: float
    min_bypass_mode_interval_seconds: int


class TempControlConfig:
    """Load temp_control settings from the config entry (canonical feature section)."""

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry) -> None:
        self.hass = hass
        self.config_entry = config_entry

    def get_settings(self) -> TempControlSettings:
        merged: dict[str, Any] = dict(self.config_entry.data or {})
        merged.update(self.config_entry.options or {})

        section = get_migrated_feature_section(merged, "temp_control")

        def _get_float(key: str, default: float) -> float:
            raw = section.get(key, TEMP_CONTROL_DEFAULTS.get(key, default))
            try:
                return float(raw)
            except TypeError, ValueError:
                return float(default)

        def _get_int(key: str, default: int) -> int:
            raw = section.get(key, TEMP_CONTROL_DEFAULTS.get(key, default))
            try:
                return int(raw)
            except TypeError, ValueError:
                return int(default)

        return TempControlSettings(
            comfort_delta_activate=_get_float("comfort_delta_activate", 1.0),
            comfort_delta_deactivate=_get_float("comfort_delta_deactivate", 0.5),
            supply_cooler_delta_activate=_get_float(
                "supply_cooler_delta_activate", 1.0
            ),
            supply_cooler_delta_deactivate=_get_float(
                "supply_cooler_delta_deactivate", 0.5
            ),
            min_supply_temp=_get_float("min_supply_temp", 10.0),
            min_bypass_mode_interval_seconds=_get_int(
                "min_bypass_mode_interval_seconds", 180
            ),
        )


__all__ = ["TempControlConfig", "TempControlSettings"]
