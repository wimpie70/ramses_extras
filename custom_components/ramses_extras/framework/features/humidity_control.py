"""Humidity Control Feature for Ramses Extras framework.

This module provides a humidity control feature implementation using the framework's
base automation class, demonstrating how to create feature implementations that
leverage the consolidated framework utilities.
"""

import asyncio
import logging
from typing import Any, cast

from homeassistant.core import HomeAssistant, State
from homeassistant.helpers import entity_registry

from ....const import AVAILABLE_FEATURES, FEATURE_ID_HUMIDITY_CONTROL
from ....framework.helpers.automation import ExtrasBaseAutomation
from ....framework.helpers.common import RamsesValidator
from ....framework.helpers.entity import EntityHelpers
from ....helpers.entity import get_feature_entity_mappings

_LOGGER = logging.getLogger(__name__)


class HumidityControlFeature(ExtrasBaseAutomation):
    """Humidity Control feature using the framework.

    This implementation demonstrates how to create a feature using the
    ExtrasBaseAutomation class and framework utilities.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        feature_id: str = FEATURE_ID_HUMIDITY_CONTROL,
        binary_sensor: Any = None,
        debounce_seconds: int = 45,
    ) -> None:
        """Initialize the humidity control feature.

        Args:
            hass: Home Assistant instance
            feature_id: Feature identifier
            binary_sensor: Optional binary sensor for status
            debounce_seconds: Debounce duration
        """
        super().__init__(hass, feature_id, binary_sensor, debounce_seconds)

        # Humidity control specific configuration
        self._humidity_config = self._get_humidity_config()

        _LOGGER.info(
            f"HumidityControlFeature initialized with config: {self._humidity_config}"
        )

    def _get_humidity_config(self) -> dict[str, Any]:
        """Get humidity control configuration.

        Returns:
            Humidity control configuration dictionary
        """
        feature_config = AVAILABLE_FEATURES.get(FEATURE_ID_HUMIDITY_CONTROL, {})
        return {
            "min_humidity": feature_config.get("min_humidity", 30.0),
            "max_humidity": feature_config.get("max_humidity", 70.0),
            "hysteresis": feature_config.get("hysteresis", 5.0),
            "dehumidify_threshold": feature_config.get("dehumidify_threshold", 60.0),
        }

    def _generate_entity_patterns(self) -> list[str]:
        """Generate entity patterns for humidity control.

        Returns:
            List of entity patterns to listen for
        """
        patterns = []

        # Add patterns for humidity control entities
        base_patterns = [
            "sensor.indoor_absolute_humidity_*",
            "sensor.outdoor_absolute_humidity_*",
            "number.relative_humidity_minimum_*",
            "number.relative_humidity_maximum_*",
            "number.absolute_humidity_offset_*",
            "switch.dehumidify_*",
            "binary_sensor.dehumidifying_active_*",
        ]

        # Add pattern for CC entity
        patterns.append("*_indoor_humidity")

        # Add the base patterns
        patterns.extend(base_patterns)

        _LOGGER.debug(f"Generated humidity control patterns: {patterns}")
        return patterns

    async def _process_automation_logic(
        self, device_id: str, entity_states: dict[str, float]
    ) -> None:
        """Process humidity control logic.

        This method implements the humidity control decision logic,
        evaluating when to activate/deactivate dehumidification.

        Args:
            device_id: Device identifier
            entity_states: Validated entity state values
        """
        _LOGGER.info(
            f"Processing humidity logic - Feature: {self.feature_id}, "
            f"Device: {device_id}"
        )

        try:
            # Extract humidity values
            indoor_abs = entity_states.get("indoor_abs")
            outdoor_abs = entity_states.get("outdoor_abs")
            min_humidity = entity_states.get("min_humidity")
            max_humidity = entity_states.get("max_humidity")
            offset = entity_states.get("offset", 0.0)

            # Validate required values
            if not all([indoor_abs, outdoor_abs, min_humidity, max_humidity]):
                _LOGGER.warning(f"Device {device_id}: Missing required humidity values")
                return

            # Apply offset to outdoor absolute humidity
            adjusted_outdoor_abs = (outdoor_abs or 0.0) + (offset or 0.0)

            # Calculate indoor relative humidity from absolute humidity
            indoor_rh = self._calculate_relative_humidity(
                indoor_abs or 0.0, 20.0
            )  # Assuming 20°C

            # Make dehumidification decision
            should_dehumidify = self._should_dehumidify(
                indoor_rh,
                min_humidity or 0.0,
                max_humidity or 0.0,
                adjusted_outdoor_abs,
            )

            # Log the decision
            _LOGGER.info(
                f"Device {device_id}: Indoor RH: {indoor_rh:.1f}%, "
                f"Min: {min_humidity}%, Max: {max_humidity}%, "
                f"Outdoor abs: {adjusted_outdoor_abs:.2f}g/m³, "
                f"Dehumidify: {should_dehumidify}"
            )

            # Execute dehumidification action
            await self._execute_dehumidification_action(device_id, should_dehumidify)

        except Exception as e:
            _LOGGER.error(f"Device {device_id}: Error in humidity logic - {e}")

    def _calculate_relative_humidity(
        self, absolute_humidity: float, temperature: float
    ) -> float:
        """Calculate relative humidity from absolute humidity and temperature.

        Args:
            absolute_humidity: Absolute humidity in g/m³
            temperature: Temperature in Celsius

        Returns:
            Relative humidity percentage
        """
        # Simple approximation using saturation vapor pressure formula
        # This is a simplified calculation for demonstration

        # Saturation vapor pressure at temperature (Magnus formula approximation)
        sat_vapor_pressure = 6.112 * (17.67 * temperature) / (243.5 + temperature)

        # Convert absolute humidity to partial vapor pressure
        # RH = (abs_humidity * 0.461 * (temp + 273.15) / sat_vapor_pressure) * 100
        rh = (
            absolute_humidity * 0.461 * (temperature + 273.15) / sat_vapor_pressure
        ) * 100

        # Clamp to valid range
        return max(0.0, min(100.0, rh))

    def _should_dehumidify(
        self,
        indoor_rh: float,
        min_humidity: float,
        max_humidity: float,
        outdoor_abs: float,
    ) -> bool:
        """Determine if dehumidification should be activated.

        Args:
            indoor_rh: Indoor relative humidity percentage
            min_humidity: Minimum humidity threshold
            max_humidity: Maximum humidity threshold
            outdoor_abs: Outdoor absolute humidity

        Returns:
            True if dehumidification should be activated
        """
        hysteresis = self._humidity_config["hysteresis"]

        # Basic logic: activate if above max threshold
        if indoor_rh > max_humidity:
            return True

        # Deactivate if below min threshold (with hysteresis)
        if indoor_rh < (min_humidity - hysteresis):
            return False

        # If we're in the middle range, check outdoor conditions
        if indoor_rh > min_humidity:
            # If outdoor absolute humidity is low, we can dehumidify
            # If outdoor absolute humidity is high, outdoor air will add moisture
            return outdoor_abs < 8.0  # Threshold for "low" outdoor humidity

        return False

    async def _execute_dehumidification_action(
        self, device_id: str, should_dehumidify: bool
    ) -> None:
        """Execute the dehumidification action.

        Args:
            device_id: Device identifier
            should_dehumidify: Whether to activate dehumidification
        """
        try:
            # Get the dehumidify switch entity
            entity_mappings = get_feature_entity_mappings(self.feature_id, device_id)
            dehumidify_entity = entity_mappings.get("dehumidify")

            if not dehumidify_entity:
                _LOGGER.warning(f"Device {device_id}: No dehumidify entity found")
                return

            # Get current state
            current_state = self.hass.states.get(dehumidify_entity)
            current_is_on = current_state and current_state.state == "on"

            # Only change state if it's different
            if current_is_on != should_dehumidify:
                _LOGGER.info(
                    f"Device {device_id}: Setting dehumidify to {should_dehumidify} "
                    f"via {dehumidify_entity}"
                )

                # Call service to set the switch
                if should_dehumidify:
                    await self.hass.services.async_call(
                        "switch", "turn_on", {"entity_id": dehumidify_entity}
                    )
                else:
                    await self.hass.services.async_call(
                        "switch", "turn_off", {"entity_id": dehumidify_entity}
                    )
            else:
                _LOGGER.debug(
                    f"Device {device_id}: Dehumidify state already {should_dehumidify}"
                )

        except Exception as e:
            _LOGGER.error(
                f"Device {device_id}: Error executing dehumidification action - {e}"
            )

    async def _get_device_entity_states(self, device_id: str) -> dict[str, float]:
        """Get entity states for humidity control with extended validation.

        Args:
            device_id: Device identifier

        Returns:
            Dictionary with entity state values
        """
        # Get base entity states using the framework method
        states = await super()._get_device_entity_states(device_id)

        # Add additional validation for humidity values
        for state_name, value in states.items():
            if "humidity" in state_name:
                # Validate humidity range
                validated_value = RamsesValidator.validate_humidity_value(value)
                if validated_value != value:
                    _LOGGER.debug(
                        f"Device {device_id}: Corrected {state_name} from "
                        f"{value} to {validated_value}"
                    )
                    states[state_name] = validated_value

        return dict(states)  # Explicitly convert to dict[str, float]


# Feature registration helper
def create_humidity_control_feature(
    hass: HomeAssistant,
    feature_id: str = FEATURE_ID_HUMIDITY_CONTROL,
    binary_sensor: Any = None,
    debounce_seconds: int = 45,
) -> HumidityControlFeature:
    """Create a humidity control feature instance.

    Args:
        hass: Home Assistant instance
        feature_id: Feature identifier
        binary_sensor: Optional binary sensor
        debounce_seconds: Debounce duration

    Returns:
        HumidityControlFeature instance
    """
    return HumidityControlFeature(
        hass=hass,
        feature_id=feature_id,
        binary_sensor=binary_sensor,
        debounce_seconds=debounce_seconds,
    )


# Framework feature registration
def register_humidity_control_feature() -> None:
    """Register the humidity control feature with the framework.

    This function registers the humidity control feature so it can be
    discovered and managed by the framework's feature manager.
    """
    # entity_registry import not needed here

    feature_config = {
        "name": "Humidity Control",
        "description": "Automated humidity control using absolute humidity calcs",
        "class": "HumidityControlFeature",
        "factory": "create_humidity_control_feature",
        "dependencies": [],  # No dependencies
        "capabilities": [
            "humidity_monitoring",
            "dehumidification_control",
            "humidity_automation",
        ],
    }

    entity_registry.register_feature_implementation(
        FEATURE_ID_HUMIDITY_CONTROL, feature_config
    )

    _LOGGER.info("Humidity control feature registered with framework")


__all__ = [
    "HumidityControlFeature",
    "create_humidity_control_feature",
    "register_humidity_control_feature",
]
