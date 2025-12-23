"""Entity helper functions for Ramses Extras."""

import logging
import math

_LOGGER = logging.getLogger(__name__)


def calculate_absolute_humidity(
    temperature: float, relative_humidity: float
) -> float | None:
    """Calculate absolute humidity from temperature and relative humidity.

    Args:
        temperature: Temperature in degrees Celsius
        relative_humidity: Relative humidity as percentage (0-100)

    Returns:
        Absolute humidity in g/m³ or None if calculation fails
    """
    try:
        # Convert temperature to Kelvin
        temp_kelvin = temperature + 273.15

        # Magnus formula for saturation vapor pressure (hPa)
        a = 17.27
        b = 237.7

        # Calculate saturation vapor pressure
        gamma = (a * temperature) / (b + temperature)
        saturation_vapor_pressure = 6.112 * math.exp(gamma)

        # Calculate actual vapor pressure in Pa (convert hPa to Pa)
        vapor_pressure_hpa = saturation_vapor_pressure * (relative_humidity / 100.0)
        vapor_pressure_pa = vapor_pressure_hpa * 100  # Convert hPa to Pa

        # Calculate absolute humidity using correct formula
        # AH = (e * M) / (R * T)
        # Where:
        # e = vapor pressure (Pa)
        # M = molecular weight of water (18.015 g/mol)
        # R = gas constant (8.314 J/(mol·K))
        # T = temperature (K)

        molecular_weight_water = 18.015  # g/mol
        gas_constant = 8.314  # J/(mol·K)

        absolute_humidity = (vapor_pressure_pa * molecular_weight_water) / (
            gas_constant * temp_kelvin
        )

        if absolute_humidity < 0:
            _LOGGER.error(
                "Calculated negative absolute humidity: %.2f g/m³", absolute_humidity
            )
            return None

        _LOGGER.debug(
            "AH calculation: T=%.1f°C, RH=%.1f%%, e=%.1fPa -> AH=%.2fg/m³",
            temperature,
            relative_humidity,
            vapor_pressure_pa,
            absolute_humidity,
        )

        return round(absolute_humidity, 2)

    except (ValueError, OverflowError, ZeroDivisionError) as e:
        _LOGGER.error("Error calculating absolute humidity: %s", e)
        return None


def validate_humidity_value(value: float | None, entity_name: str) -> bool:
    """Validate humidity values are within reasonable ranges.

    Args:
        value: Humidity value to validate
        entity_name: Name of the entity for error messages

    Returns:
        True if value is valid, False otherwise
    """
    if value is None or not (0 <= value <= 100):
        _LOGGER.error(
            "Invalid humidity value %s for %s (must be 0-100%%)", value, entity_name
        )
        return False

    return True


def validate_temperature_value(value: float | None, entity_name: str) -> bool:
    """Validate temperature values are within reasonable ranges.

    Args:
        value: Temperature value to validate
        entity_name: Name of the entity for error messages

    Returns:
        True if value is valid, False otherwise
    """
    if value is None or not (-50 <= value <= 100):
        _LOGGER.error(
            "Invalid temperature %s°C for %s (must be -50 to 100°C)",
            value,
            entity_name,
        )
        return False

    return True
