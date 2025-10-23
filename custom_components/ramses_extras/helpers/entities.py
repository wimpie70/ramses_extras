"""
Entity calculation helpers for Ramses Extras integration.

This module contains calculation functions that were moved from JavaScript
to Python for better performance and accuracy.
"""

import math
from typing import Optional


def calculate_absolute_humidity(
    temp: float | None,
    humidity: float | None,
) -> float | None:
    """
    Calculate absolute humidity from temperature and relative humidity.

    Args:
        temp: Temperature in Celsius
        humidity: Relative humidity percentage (0-100)

    Returns:
        Absolute humidity in g/m³ or None if invalid input
    """
    if temp is None or humidity is None:
        return None

    try:
        temp_c = float(temp)
        rel_hum = float(humidity)

        if not (0 <= rel_hum <= 100):
            return None

        # Saturation vapor pressure (hPa) using Magnus formula
        es = 6.112 * math.exp((17.67 * temp_c) / (temp_c + 243.5))

        # Actual vapor pressure (hPa)
        e = (rel_hum / 100) * es

        # Absolute humidity (g/m³)
        # Using: AH = (2.1674 * e) / (273.15 + T) * 100
        ah = (2.1674 * e) / (273.15 + temp_c) * 100

        return round(ah, 1)

    except (ValueError, TypeError, ZeroDivisionError):
        return None


def calculate_heat_recovery_efficiency(
    supply_temp: float | None,
    exhaust_temp: float | None,
    outdoor_temp: float | None,
    indoor_temp: float | None,
) -> float:
    """
    Calculate heat recovery efficiency based on temperature differences.

    Args:
        supply_temp: Supply air temperature in Celsius
        exhaust_temp: Exhaust air temperature in Celsius
        outdoor_temp: Outdoor air temperature in Celsius
        indoor_temp: Indoor air temperature in Celsius

    Returns:
        Efficiency percentage (0-100) or 75 if data is invalid
    """
    # Check for invalid input values
    if any(
        temp is None for temp in [supply_temp, exhaust_temp, outdoor_temp, indoor_temp]
    ):
        return 75.0

    try:
        # At this point, mypy should know these are not None due to the check above
        supply = float(supply_temp)  # type: ignore[arg-type]
        exhaust = float(exhaust_temp)  # type: ignore[arg-type]
        outdoor = float(outdoor_temp)  # type: ignore[arg-type]
        indoor = float(indoor_temp)  # type: ignore[arg-type]

        # Check if indoor temperature makes sense (should be warmest in heating mode)
        if indoor <= supply:
            # Fallback to alternative calculation if indoor data seems wrong
            temp_diff = exhaust - outdoor
            if abs(temp_diff) < 0.1:
                return 75.0

            efficiency = (supply - outdoor) / (exhaust - outdoor) * 100
            return max(0, min(100, round(efficiency * 10) / 10))

        # Main efficiency calculation: (supply - outdoor) / (indoor - outdoor) * 100
        efficiency = (supply - outdoor) / (indoor - outdoor) * 100

        # Check if supply temperature makes sense
        # Shouldn't be warmer than indoor in normal operation
        if supply > indoor:
            # If supply is warmer than indoor, efficiency > 100% is possible
            # with additional heating. Cap at 100% for display purposes
            return max(0, min(100, round(efficiency * 10) / 10))

        return max(0, min(100, round(efficiency * 10) / 10))

    except (ValueError, TypeError, ZeroDivisionError):
        return 75.0
