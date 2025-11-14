"""Humidity Control Automation.

This module contains the automation logic for humidity control functionality,
migrated from the original humidity_automation.py but organized within the
feature-centric architecture.
"""

import asyncio
import logging
from typing import Any, cast

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry
from homeassistant.helpers.event import async_track_state_change_event

from custom_components.ramses_extras.framework.helpers.automation.base import (
    ExtrasBaseAutomation,
)
from custom_components.ramses_extras.framework.helpers.entity import EntityHelpers

from .config import HumidityConfig
from .const import HUMIDITY_CONTROL_CONST
from .services import HumidityServices

_LOGGER = logging.getLogger(__name__)


class HumidityAutomationManager(ExtrasBaseAutomation):
    """Manages humidity control automation logic.

    This class implements the decision logic from the original humidity automation
    but uses the framework's base automation class for consistency.
    """

    def __init__(self, hass: HomeAssistant, config_entry: Any) -> None:
        """Initialize humidity automation manager.

        Args:
            hass: Home Assistant instance
            config_entry: Configuration entry
        """
        super().__init__(
            hass=hass,
            feature_id=cast(str, HUMIDITY_CONTROL_CONST["feature_id"]),
            binary_sensor=None,  # Will be set when entities are available
            debounce_seconds=0,  # No debouncing needed - event-driven approach
        )

        self.config_entry = config_entry
        self.config = HumidityConfig(hass, config_entry)
        self.services = HumidityServices(hass, config_entry)

        # Humidity-specific state tracking
        self._dehumidify_active = False
        self._automation_active = False
        self._last_decision_state: dict[str, Any] | None = None
        self._decision_history: list[dict[str, Any]] = []

        # Binary sensor reference for direct control
        self._binary_sensor: Any = None

        # Performance tracking
        self._decision_count = 0
        self._active_cycles = 0

        _LOGGER.info("Enhanced Humidity Control automation initialized")

    def _singularize_entity_type(self, entity_type: str) -> str:
        """Convert plural entity type to singular form.

        Args:
            entity_type: Plural entity type (e.g., "switches", "sensors", "numbers")

        Returns:
            Singular entity type (e.g., "switch", "sensor", "number")
        """
        # Handle common entity type plurals
        entity_type_mapping = {
            "sensors": "sensor",
            "switches": "switch",
            "binary_sensors": "binary_sensor",
            "numbers": "number",
            "devices": "device",
            "entities": "entity",
        }

        return entity_type_mapping.get(entity_type, entity_type.rstrip("s"))

    def _generate_entity_patterns(self) -> list[str]:
        """Generate entity patterns for humidity control.

        Returns:
            List of entity patterns to listen for
        """
        patterns = [
            # Primary humidity entities with device-specific naming
            "sensor.indoor_absolute_humidity_*",
            "sensor.outdoor_absolute_humidity_*",
            "number.relative_humidity_minimum_*",
            "number.relative_humidity_maximum_*",
            "number.absolute_humidity_offset_*",
            "switch.dehumidify_*",
            "binary_sensor.dehumidifying_active_*",
            # Cross-device reference entities (ramses_cc entities)
            "sensor.*_indoor_humidity",  # CC sensor references
        ]

        _LOGGER.debug(f"Generated {len(patterns)} entity patterns for humidity control")
        _LOGGER.debug(f"Entity patterns: {patterns}")
        return patterns

    async def _check_any_device_ready(self) -> bool:
        """Check if any device has all required humidity control entities ready.

        Returns:
            True if at least one device is ready
        """
        # Use the humidity-specific entity patterns
        patterns = self.entity_patterns

        # Find any entities that match our patterns
        for pattern in patterns:
            if pattern.endswith("*"):
                prefix = pattern[:-1]  # Remove the *
                entity_type = prefix.split(".")[0]
                entities = self.hass.states.async_all(entity_type)

                matching_entities = [
                    state for state in entities if state.entity_id.startswith(prefix)
                ]

                if matching_entities:
                    # Check each matching entity's device has all required entities
                    for entity_state in matching_entities:
                        device_id = self._extract_device_id(entity_state.entity_id)
                        if device_id and await self._validate_device_entities(
                            device_id
                        ):
                            _LOGGER.info(
                                f"Enhanced Humidity Control: Device {device_id} "
                                f"has all {self.feature_id} entities ready"
                            )
                            return True

        return False

    async def _validate_device_entities(self, device_id: str) -> bool:
        """Validate all required entities exist for a humidity control device.

        Args:
            device_id: Device identifier

        Returns:
            True if all entities exist, False otherwise
        """
        # Use humidity control specific entity mappings
        from .const import HUMIDITY_CONTROL_CONST

        required_entities = cast(
            dict[str, list[str]], HUMIDITY_CONTROL_CONST.get("required_entities", {})
        )
        missing_entities = []

        for entity_type, entity_names in required_entities.items():
            # Convert plural to singular using the base class method
            entity_base_type = self._singularize_entity_type(entity_type)

            for entity_name in entity_names:
                # Generate expected entity ID using humidity control patterns
                expected_entity_id = f"{entity_base_type}.{entity_name}_{device_id}"
                _LOGGER.debug(f"Checking for entity: {expected_entity_id}")
                entity_exists = self.hass.states.get(expected_entity_id)
                if not entity_exists:
                    missing_entities.append(expected_entity_id)

        if missing_entities:
            _LOGGER.debug(
                f"Device {device_id}: Missing {self.feature_id} "
                f"entities - {missing_entities}"
            )
            return False

        return True

    async def _get_device_entity_states(self, device_id: str) -> dict[str, Any]:
        """Get all entity states for a humidity control device.

        Args:
            device_id: Device identifier (e.g., "32_153289")

        Returns:
            Dictionary with entity state values (numeric or boolean)

        Raises:
            ValueError: If any entity is unavailable or has invalid values
        """
        from .const import HUMIDITY_CONTROL_CONST

        states = {}

        # Get entity mappings from humidity control constants
        state_mappings = cast(
            dict[str, str], HUMIDITY_CONTROL_CONST.get("entity_mappings", {})
        )

        for state_name, entity_template in state_mappings.items():
            # Replace {device_id} placeholder in entity template
            entity_id = entity_template.format(device_id=device_id)
            state = self.hass.states.get(entity_id)

            if not state:
                raise ValueError(f"Entity {entity_id} not found")

            if state.state in ["unavailable", "unknown"]:
                raise ValueError(f"Entity {entity_id} state unavailable")

            # Determine entity type from entity_id and handle appropriately
            entity_type = self._extract_entity_type_from_id(entity_id)
            value = self._convert_entity_state(entity_type, state.state)
            states[state_name] = value

        return states

    async def start(self) -> None:
        """Start the humidity control automation.

        Initializes automation and begins monitoring.
        """
        _LOGGER.info("Starting humidity control automation")

        # Load configuration
        await self.config.async_load()

        # Start base automation
        await super().start()

        self._automation_active = True
        _LOGGER.info("Humidity control automation started")

    def set_binary_sensor(self, binary_sensor: Any) -> None:
        """Set the binary sensor instance for direct control.

        Args:
            binary_sensor: The binary sensor entity to control
        """
        self._binary_sensor = binary_sensor
        _LOGGER.debug("Binary sensor reference set for automation")

    async def stop(self) -> None:
        """Stop the humidity control automation.

        Shuts down automation and cleans up resources.
        """
        _LOGGER.info("Stopping humidity control automation")

        self._automation_active = False
        await super().stop()

        _LOGGER.info("Humidity control automation stopped")

    async def _process_automation_logic(
        self, device_id: str, entity_states: dict[str, Any]
    ) -> None:
        """Process humidity control automation logic for a device.

        Args:
            device_id: Device identifier
            entity_states: Validated entity state values (float or bool)
        """
        if not self._automation_active:
            return

        # Check if switch is manually OFF - if so,
        #  don't run automation but keep switch state
        switch_state = entity_states.get("dehumidify")
        if switch_state is not None:
            switch_is_on = bool(switch_state)

            # If switch is OFF, stop automation but don't turn the switch off
            #  (it's already off)
            if not switch_is_on:
                _LOGGER.debug(
                    f"Switch is OFF for device {device_id} - automation disabled"
                )
                if self._dehumidify_active:
                    # Stop dehumidification but don't touch the switch
                    #  (user manually turned it off)
                    await self._stop_dehumidification_without_switch_change(device_id)
                # Just update binary sensor to reflect inactive state
                await self._set_indicator_off(device_id)
                return

        # Switch is ON - run automation
        _LOGGER.info(
            f"Enhanced Humidity Control processing automation logic for "
            f"device {device_id}"
        )

        try:
            # Extract humidity values (these should be float)
            indoor_abs = float(entity_states.get("indoor_abs", 0.0))
            outdoor_abs = float(entity_states.get("outdoor_abs", 0.0))
            indoor_rh = float(entity_states.get("indoor_rh", 0.0))
            min_humidity = float(entity_states.get("min_humidity", 40.0))
            max_humidity = float(entity_states.get("max_humidity", 60.0))
            offset = float(entity_states.get("offset", 0.0))

            # Calculate decision with proper relative humidity logic
            decision = await self._evaluate_humidity_conditions(
                device_id,
                indoor_rh,
                indoor_abs,
                outdoor_abs,
                min_humidity,
                max_humidity,
                offset,
            )

            # Apply decision
            if decision["action"] == "dehumidify":
                # Activate dehumidification: set fan HIGH, binary sensor ON
                await self._activate_dehumidification(device_id, decision)
            elif decision["action"] == "stop":
                # Stop dehumidification: set fan LOW, binary sensor OFF
                # BUT DON'T TOUCH THE SWITCH - it's for automation enable/disable
                await self._set_fan_low_and_binary_off(device_id, decision)

            # Update indicator based on decision
            await self._update_automation_status(device_id, decision)

        except Exception as e:
            _LOGGER.error(f"Automation logic error: {e}")

    async def _set_indicator_off(self, device_id: str) -> None:
        """Set indicator to OFF when switch is off or automation stops."""
        if self._binary_sensor:
            try:
                await self._binary_sensor.async_turn_off()
                _LOGGER.debug(f"Set indicator OFF for device {device_id}")
            except Exception as e:
                _LOGGER.error(f"Failed to set indicator off: {e}")

    async def _evaluate_humidity_conditions(
        self,
        device_id: str,
        indoor_rh: float,
        indoor_abs: float,
        outdoor_abs: float,
        min_humidity: float,
        max_humidity: float,
        offset: float,
    ) -> dict[str, Any]:
        """Evaluate humidity conditions and make dehumidification decision.

        This implements proper decision logic with relative humidity priority.

        Args:
            device_id: Device identifier
            indoor_rh: Indoor relative humidity
            indoor_abs: Indoor absolute humidity
            outdoor_abs: Outdoor absolute humidity
            min_humidity: Minimum relative humidity threshold
            max_humidity: Maximum relative humidity threshold
            offset: Humidity offset adjustment

        Returns:
            Decision dictionary with action and reasoning
        """
        # Calculate humidity differential (outdoor - indoor)
        # Positive = outdoor more humid (avoid bringing in),
        # Negative = outdoor drier (good for ventilation)
        humidity_diff = outdoor_abs - indoor_abs

        # Apply offset
        adjusted_diff = humidity_diff + offset

        # Decision logic with RELATIVE HUMIDITY PRIORITY
        decision: dict[str, Any] = {
            "action": "stop",  # Default action
            "reasoning": [],
            "values": {
                "indoor_rh": indoor_rh,
                "indoor_abs": indoor_abs,
                "outdoor_abs": outdoor_abs,
                "humidity_diff": humidity_diff,  # outdoor - indoor
                "adjusted_diff": adjusted_diff,
                "min_humidity": min_humidity,
                "max_humidity": max_humidity,
                "offset": offset,
            },
            "confidence": 0.0,
        }

        # PRIORITY 1: High humidity check (relative humidity threshold) - ORIGINAL LOGIC
        if indoor_rh > max_humidity:
            if indoor_abs > outdoor_abs + offset:  # ORIGINAL COMPARISON
                decision["action"] = "dehumidify"
                decision["reasoning"].append(
                    f"High indoor RH: {indoor_rh:.1f}% > {max_humidity:.1f}% "
                    f"with indoor abs ({indoor_abs:.2f}) > outdoor abs "
                    f"({outdoor_abs:.2f}) + offset ({offset:.2f})"
                )
                decision["confidence"] = 0.9
            else:
                decision["action"] = "stop"
                decision["reasoning"].append(
                    f"High indoor RH: {indoor_rh:.1f}% > {max_humidity:.1f}% "
                    f"but indoor abs ({indoor_abs:.2f}) <= outdoor abs "
                    f"({outdoor_abs:.2f}) + offset ({offset:.2f})"
                )
                decision["confidence"] = 0.6

        # PRIORITY 2: Low humidity check (relative humidity threshold) - ORIGINAL LOGIC
        elif indoor_rh < min_humidity:
            if indoor_abs < outdoor_abs - offset:  # ORIGINAL COMPARISON
                decision["action"] = "dehumidify"  # Bring in humid air
                decision["reasoning"].append(
                    f"Low indoor RH: {indoor_rh:.1f}% < {min_humidity:.1f}% "
                    f"with indoor abs ({indoor_abs:.2f}) < outdoor abs "
                    f"({outdoor_abs:.2f}) - offset ({offset:.2f})"
                )
                decision["confidence"] = 0.8
            else:
                decision["action"] = "stop"
                decision["reasoning"].append(
                    f"Low indoor RH: {indoor_rh:.1f}% < {min_humidity:.1f}% "
                    f"but indoor abs ({indoor_abs:.2f}) >= outdoor abs "
                    f"({outdoor_abs:.2f}) - offset ({offset:.2f})"
                )
                decision["confidence"] = 0.7

        # PRIORITY 3: In acceptable range - use absolute humidity differential
        else:
            if adjusted_diff < -2.0:
                # Very dry outdoor air - activate dehumidification
                decision["action"] = "dehumidify"
                decision["reasoning"].append(
                    f"Very dry outdoor air: {adjusted_diff:.1f} < -2.0 "
                    f"(good for ventilation)"
                )
                decision["confidence"] = 0.7

            elif adjusted_diff < -1.0:
                # Moderately dry outdoor air - activate dehumidification
                decision["action"] = "dehumidify"
                decision["reasoning"].append(
                    f"Dry outdoor air: {adjusted_diff:.1f} < -1.0 "
                    f"(good for ventilation)"
                )
                decision["confidence"] = 0.6

            elif adjusted_diff > 1.0:
                # Outdoor air is more humid - stop dehumidification
                decision["action"] = "stop"
                decision["reasoning"].append(
                    f"Humid outdoor air: {adjusted_diff:.1f} > 1.0 (avoid bringing in)"
                )
                decision["confidence"] = 0.7

            else:
                # In acceptable range with balanced humidity
                decision["action"] = "stop"
                decision["reasoning"].append(
                    f"Humidity in acceptable range (RH: {indoor_rh:.1f}%, "
                    f"diff: {adjusted_diff:.2f})"
                )
                decision["confidence"] = 0.8

        # Additional checks for extreme absolute values
        if indoor_abs > 15.0:  # High absolute humidity
            decision["confidence"] = min(1.0, decision["confidence"] + 0.1)
            decision["reasoning"].append(
                f"High indoor absolute humidity: {indoor_abs:.1f} g/m³"
            )

        # Record decision
        self._decision_count += 1
        self._decision_history.append(decision)

        # Keep only recent decisions
        if len(self._decision_history) > 100:
            self._decision_history.pop(0)

        # Always log the decision for debugging
        _LOGGER.info(
            f"Decision for device {device_id}: {decision['action']} "
            f"(confidence: {decision['confidence']:.2f}, "
            f"diff: {decision['values']['adjusted_diff']:.2f}, "
            f"indoor RH: {indoor_rh:.1f}%)"
        )
        if decision["reasoning"]:
            reasoning = "; ".join(decision["reasoning"])
            _LOGGER.info(f"Reasoning: {reasoning}")

        return decision

    async def _activate_dehumidification(
        self, device_id: str, decision: dict[str, Any]
    ) -> None:
        """Activate dehumidification for a device.

        Args:
            device_id: Device identifier
            decision: Decision information
        """
        if self._dehumidify_active:
            return  # Already active

        try:
            # Turn on dehumidify switch
            await self.services.async_activate_dehumidification(device_id)

            self._dehumidify_active = True
            self._active_cycles += 1

            # Log activation
            reasoning = "; ".join(decision["reasoning"])
            _LOGGER.info(f"Dehumidification activated: {reasoning}")

        except Exception as e:
            _LOGGER.error(f"Failed to activate dehumidification: {e}")

    async def _deactivate_dehumidification(
        self, device_id: str, decision: dict[str, Any]
    ) -> None:
        """Deactivate dehumidification for a device.

        Args:
            device_id: Device identifier
            decision: Decision information
        """
        if not self._dehumidify_active:
            return  # Already inactive

        try:
            # Turn off dehumidify switch
            await self.services.async_deactivate_dehumidification(device_id)

            self._dehumidify_active = False

            # Log deactivation
            reasoning = "; ".join(decision["reasoning"])
            _LOGGER.info(f"Dehumidification deactivated: {reasoning}")

        except Exception as e:
            _LOGGER.error(f"Failed to deactivate dehumidification: {e}")

    async def _set_fan_low_and_binary_off(
        self, device_id: str, decision: dict[str, Any]
    ) -> None:
        """Set fan to low speed and turn off binary sensor (don't touch switch).

        Args:
            device_id: Device identifier
            decision: Decision information
        """
        try:
            # Set fan to low speed (stop dehumidification)
            await self.services.async_set_fan_speed(device_id, "low")

            # Binary sensor will be updated by _update_automation_status
            self._dehumidify_active = False

            # Log the change
            reasoning = "; ".join(decision["reasoning"])
            _LOGGER.info(
                f"Fan set to LOW speed (dehumidification stopped): {reasoning}"
            )

        except Exception as e:
            _LOGGER.error(f"Failed to set fan low speed: {e}")

    async def _stop_dehumidification_without_switch_change(
        self, device_id: str
    ) -> None:
        """Stop dehumidification without changing switch state.

        Args:
            device_id: Device identifier
        """
        if not self._dehumidify_active:
            return  # Already inactive

        try:
            # Just stop dehumidification, don't touch the switch
            # (user manually turned switch off, so we respect that)
            await self.services.async_deactivate_dehumidification(device_id)

            self._dehumidify_active = False

            _LOGGER.info(
                f"Dehumidification stopped for {device_id} "
                f"(switch already off, respecting user choice)"
            )

        except Exception as e:
            _LOGGER.error(f"Failed to stop dehumidification: {e}")

    async def _update_automation_status(
        self, device_id: str, decision: dict[str, Any]
    ) -> None:
        """Update automation status entity.

        Args:
            device_id: Device identifier
            decision: Decision information
        """
        # Update binary sensor directly if available
        if self._binary_sensor:
            try:
                is_active = decision["action"] == "dehumidify"
                if is_active:
                    await self._binary_sensor.async_turn_on()
                else:
                    await self._binary_sensor.async_turn_off()
                _LOGGER.debug(
                    f"Updated binary sensor for {device_id}: "
                    f"{'on' if is_active else 'off'}"
                )
            except Exception as e:
                _LOGGER.error(f"Failed to update binary sensor: {e}")

    # Public API methods
    async def async_set_min_humidity(self, device_id: str, value: float) -> bool:
        """Set minimum humidity threshold.

        Args:
            device_id: Device identifier
            value: Minimum humidity value

        Returns:
            True if successful
        """
        try:
            return bool(await self.services.async_set_min_humidity(device_id, value))
        except Exception as e:
            _LOGGER.error(f"Failed to set min humidity: {e}")
            return False

    async def async_set_max_humidity(self, device_id: str, value: float) -> bool:
        """Set maximum humidity threshold.

        Args:
            device_id: Device identifier
            value: Maximum humidity value

        Returns:
            True if successful
        """
        try:
            return bool(await self.services.async_set_max_humidity(device_id, value))
        except Exception as e:
            _LOGGER.error(f"Failed to set max humidity: {e}")
            return False

    async def async_set_offset(self, device_id: str, value: float) -> bool:
        """Set humidity offset adjustment.

        Args:
            device_id: Device identifier
            value: Offset value

        Returns:
            True if successful
        """
        try:
            return bool(await self.services.async_set_offset(device_id, value))
        except Exception as e:
            _LOGGER.error(f"Failed to set offset: {e}")
            return False

    def is_automation_active(self) -> bool:
        """Check if automation is currently active.

        Returns:
            True if automation is active
        """
        return self._automation_active

    def is_dehumidifying(self) -> bool:
        """Check if dehumidification is currently active.

        Returns:
            True if dehumidifying
        """
        return self._dehumidify_active

    def get_decision_history(self, limit: int = 10) -> list[dict[str, Any]]:
        """Get recent decision history.

        Args:
            limit: Maximum number of decisions to return

        Returns:
            List of recent decisions
        """
        return self._decision_history[-limit:] if self._decision_history else []

    def get_automation_statistics(self) -> dict[str, Any]:
        """Get automation performance statistics.

        Returns:
            Statistics dictionary
        """
        return {
            "decisions_made": self._decision_count,
            "active_cycles": self._active_cycles,
            "is_active": self._automation_active,
            "is_dehumidifying": self._dehumidify_active,
            "recent_decisions": len(self._decision_history),
        }


# Feature registration
def create_humidity_control_automation(
    hass: HomeAssistant, config_entry: Any
) -> HumidityAutomationManager:
    """Create humidity control automation instance.

    Args:
        hass: Home Assistant instance
        config_entry: Configuration entry

    Returns:
        HumidityAutomationManager instance
    """
    return HumidityAutomationManager(hass, config_entry)


__all__ = [
    "HumidityAutomationManager",
    "create_humidity_control_automation",
]
