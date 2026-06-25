"""Common utility functions for Ramses Extras."""

import logging
import math

_LOGGER = logging.getLogger(__name__)


def calculate_absolute_humidity(
    temperature: float, relative_humidity: float
) -> float | None:
    """Calculate absolute humidity from temperature and relative humidity.

    :param temperature: Temperature in degrees Celsius
    :param relative_humidity: Relative humidity as percentage (0-100)
    :return: Absolute humidity in g/m³ or None if calculation fails
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

        return round(absolute_humidity, 2)

    except (ValueError, OverflowError, ZeroDivisionError) as e:
        _LOGGER.error("Error calculating absolute humidity: %s", e)
        return None


def _singularize_entity_type(entity_type: str) -> str:
    """Convert plural entity type to singular form.

    :param entity_type: Plural entity type (e.g., "switches", "sensors", "numbers")
    :return: Singular entity type (e.g., "switch", "sensor", "number")
    """
    # Handle common entity type plurals
    entity_type_mapping = {
        "sensor": "sensor",
        "sensors": "sensor",
        "switch": "switch",
        "switches": "switch",
        "binary_sensor": "binary_sensor",
        "binary_sensors": "binary_sensor",
        "number": "number",
        "numbers": "number",
        "devices": "device",
        "entities": "entity",
        "covers": "cover",
        "fans": "fan",
        "lights": "light",
        "climate": "climate",
        "climates": "climate",
        "humidifiers": "humidifier",
        "dehumidifiers": "dehumidifier",
        "select": "select",
        "selects": "select",
    }

    return entity_type_mapping.get(entity_type, entity_type)
