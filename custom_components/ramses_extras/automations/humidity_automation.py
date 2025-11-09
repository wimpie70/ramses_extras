"""Humidity Automation Manager for Ramses Extras integration.

This module provides hardcoded automation logic for humidity control,
replacing the problematic YAML template approach with direct Python implementation.

The automation monitors humidity conditions and automatically adjusts ventilation
settings based on the decision logic defined in humidity_decision_flow.md.
"""

import asyncio
import logging
import re
import time
from typing import Any, Dict, List, Optional, Set, cast

from homeassistant.core import HomeAssistant, State, callback
from homeassistant.helpers import entity_registry
from homeassistant.helpers.event import (
    async_track_state_change,
    async_track_state_change_event,
)

from ..const import (
    AVAILABLE_FEATURES,
    DEVICE_ENTITY_MAPPING,
    FEATURE_ID_HUMIDITY_CONTROL,
)
from ..helpers.automation import ExtrasBaseAutomation
from ..helpers.entity import EntityHelpers, get_feature_entity_mappings

_LOGGER = logging.getLogger(__name__)

# Humidity automation configuration constants
HUMIDITY_DEBOUNCE_SECONDS = 15


class HumidityAutomationManager(ExtrasBaseAutomation):
    """Manages hardcoded humidity automation logic.

    This class implements the exact decision logic from the mermaid diagram
    in humidity_decision_flow.md, replacing the YAML template system with
    direct Python automation.

    Inherits generic automation patterns from ExtrasBaseAutomation.
    """

    def __init__(
        self, hass: HomeAssistant, binary_sensor: Any = None, switch_state: bool = False
    ) -> None:
        """Initialize the humidity automation manager.

        Args:
            hass: Home Assistant instance
            binary_sensor: The binary sensor entity to update
            switch_state: The current state of the switch (True for ON, False for OFF)
        """
        # Initialize base automation with humidity control feature
        super().__init__(
            hass=hass,
            feature_id=FEATURE_ID_HUMIDITY_CONTROL,
            binary_sensor=binary_sensor,
            debounce_seconds=HUMIDITY_DEBOUNCE_SECONDS,
        )

        # Humidity-specific state tracking
        self.switch_state = switch_state
        _LOGGER.info(
            f"HumidityAutomationManager __init__ binary_sensor: {binary_sensor}, "
            f"switch_state: {switch_state}"
        )

        # Cache for dynamically generated entity patterns and mappings
        self._state_mappings: dict[str, str] | None = None
        self._entity_configs: dict[str, dict[str, Any]] | None = None

    def _get_entity_name_from_const(self, const_entity_name: str) -> str:
        """Convert const.py entity name to actual entity name from configs.

        In the new system, const entity names ARE the actual entity names.
        This method just returns the input for compatibility.
        Used by tests to verify entity name transformation.
        """
        return const_entity_name

    def _get_state_mappings(self, device_id: str) -> dict[str, str]:
        """Generate state mappings dynamically using AVAILABLE_FEATURES.

        This method is now a wrapper for the moved
        get_state_to_entity_mappings_v2 function.
        Kept for backward compatibility.
        """
        return get_feature_entity_mappings("humidity_control", device_id)

    async def _delayed_listener_test(self) -> None:
        """Run listener test with a small delay to ensure entities are created."""
        await asyncio.sleep(5)  # Wait 5 seconds for entities to be created
        await self._test_listeners_now()

        # Immediately evaluate current humidity conditions if switch is on
        await self._evaluate_current_conditions()

    async def _evaluate_current_conditions(self) -> None:
        """Evaluate current humidity conditions immediately when automation starts."""
        if not self.binary_sensor:
            return

        # Extract device_id from binary sensor object, not treat it as a string
        if hasattr(self.binary_sensor, "_device_id"):
            device_id = self.binary_sensor._device_id.replace(
                ":", "_"
            )  # Convert colon to underscore
        else:
            # Fallback: treat as string (for backwards compatibility)
            device_id = str(self.binary_sensor).replace(":", "_")

        # Check if switch is on using the passed switch_state
        if not self.switch_state:
            _LOGGER.debug(
                f"Switch not on (state: {self.switch_state}), "
                f"skipping initial evaluation"
            )
            return

        _LOGGER.debug(f"Evaluating current conditions for device: {device_id}")

        # Validate entities
        if not await self._validate_device_entities(device_id):
            _LOGGER.debug(
                f"Entities not ready for device {device_id}, "
                f"skipping initial evaluation"
            )
            return

        # Get states and process
        try:
            entity_states = await self._get_device_entity_states(device_id)
            _LOGGER.info(f"Initial evaluation for device {device_id}: {entity_states}")
            await self._process_automation_logic(device_id, entity_states)
        except Exception as e:
            _LOGGER.debug(
                f"Could not evaluate current conditions for device {device_id}: {e}"
            )

    # ==================== ABSTRACT METHOD IMPLEMENTATIONS ====================

    def _generate_entity_patterns(self) -> list[str]:
        """Generate entity patterns specific to humidity control.

        Overrides base class to provide humidity-specific patterns including
        CC entities and Extras entities.
        """
        patterns = []

        # Add CC entity pattern for relative humidity
        patterns.append("*_indoor_humidity")  # CC: sensor.32_153289_indoor_humidity

        # Add Extras entity patterns using const.py feature definition
        humidity_feature = cast(
            dict[str, Any], AVAILABLE_FEATURES[FEATURE_ID_HUMIDITY_CONTROL]
        )
        required_entities = cast(
            dict[str, list[str]], humidity_feature.get("required_entities", {})
        )

        for entity_type, entity_names in required_entities.items():
            for entity_name in entity_names:
                # Use wildcard pattern for dynamic device_id matching
                patterns.append(f"{entity_type.rstrip('s')}.{entity_name}_*")

        return patterns

    async def _process_automation_logic(
        self, device_id: str, entity_states: dict[str, float]
    ) -> None:
        """Process humidity automation logic.

        This is the abstract method implementation from ExtrasBaseAutomation.
        Implements the humidity-specific decision tree logic.
        """
        await self._process_humidity_logic(device_id, entity_states)

    # ==================== HUMIDITY-SPECIFIC LOGIC ====================

    def _handle_state_change(
        self, entity_id: str, old_state: State | None, new_state: State | None
    ) -> None:
        """Handle state changes following exact mermaid decision flow."""
        # 📋 CRITICAL DEBUG: This should be called for every entity state change
        _LOGGER.info(
            f"🔍 STATE CHANGE DETECTED: {entity_id} -> "
            f"{new_state.state if new_state else 'None'}"
        )
        _LOGGER.debug(
            f"🔍 Debug: Listener called for {entity_id} in automation "
            f"{self.__class__.__name__}"
        )

        # 🔍 DEBUG: Special logging for number entity changes
        if entity_id.startswith("number."):
            _LOGGER.info(
                f"🔍 NUMBER ENTITY CHANGE: {entity_id} from "
                f"{old_state.state if old_state else 'None'} to "
                f"{new_state.state if new_state else 'None'}"
            )

        # Update switch_state if this is a switch change
        if entity_id.startswith("switch.dehumidify_") and new_state:
            old_switch_state = getattr(self, "switch_state", False)
            self.switch_state = new_state.state == "on"
            _LOGGER.debug(
                f"Updated switch_state from {old_switch_state} to {self.switch_state}"
            )

        # 🔍 DEBUG: Log device_id extraction attempt
        device_id = self._extract_device_id(entity_id)
        _LOGGER.debug(f"🔍 Device ID extraction for {entity_id}: {device_id}")
        if not device_id:
            _LOGGER.warning(
                f"🔍 WARNING: Could not extract device_id from {entity_id} "
                f"- this may prevent state change processing"
            )

        # Schedule async processing with proper thread safety
        # Create a callback that will be called safely from the main thread
        def _create_async_task() -> None:
            self.hass.async_create_task(
                self._async_handle_state_change(entity_id, old_state, new_state)
            )

        # Use call_soon_threadsafe to ensure thread-safe execution
        self.hass.loop.call_soon_threadsafe(_create_async_task)

    async def _async_handle_state_change(
        self, entity_id: str, old_state: State | None, new_state: State | None
    ) -> None:
        """Handle state changes following exact mermaid decision flow.

        This method implements the decision logic from humidity_decision_flow.md:
        1. Extract device_id from entity name
        2. Validate all entities exist for this device
        3. Check if dehumidify switch is ON (only process when ON)
        4. Apply 45-second debouncing
        5. Get all entity states
        6. Execute exact mermaid decision logic
        7. Control fan and update binary sensor

        Args:
            entity_id: Entity that changed state
            old_state: Previous state (if any)
            new_state: New state
        """
        if not new_state:
            _LOGGER.debug(f"🔍 No new state for {entity_id}, skipping")
            return

        # 🔍 COMPREHENSIVE DEBUGGING
        _LOGGER.info(
            f"🔍 ASYNC PROCESSING: {entity_id} -> {new_state.state} "
            f"(was: {old_state.state if old_state else 'None'})"
        )

        # Extract device_id from entity name
        device_id = self._extract_device_id(entity_id)
        if not device_id:
            _LOGGER.warning(
                f"🔍 CRITICAL: Could not extract device_id from entity: {entity_id}"
            )
            # 🔍 DEBUG: Try to show what patterns we're looking for
            _LOGGER.debug(
                "🔍 Expected patterns should match entities like: "
                "number.relative_humidity_maximum_32_153289 or "
                "number.32:153289_rel_humid_max"
            )
            return

        _LOGGER.info(f"🔍 SUCCESS: Extracted device_id {device_id} from {entity_id}")

        # 🔍 ENHANCED SWITCH STATE LOGGING
        switch_state = self.hass.states.get(f"switch.dehumidify_{device_id}")
        _LOGGER.info(
            f"Device {device_id}: Switch state check - hass.states: "
            f"{switch_state.state if switch_state else 'NOT FOUND'}, automation "
            f"attribute: {getattr(self, 'switch_state', 'NOT SET')}"
        )

        # Validate all entities exist for this device
        if not await self._validate_device_entities(device_id):
            _LOGGER.warning(f"🔍 CRITICAL: Device {device_id}: Entities not ready")
            return

        _LOGGER.info(f"🔍 SUCCESS: Device {device_id}: All entities validated")

        # Reset logic: switch turned OFF (separate automation in YAML template)
        if entity_id == f"switch.dehumidify_{device_id}" and new_state.state == "off":
            _LOGGER.info(
                f"Device {device_id}: Dehumidify switch turned OFF - resetting fan"
            )
            await self._reset_fan_to_auto(device_id)
            return

        # 🔍 ENHANCED SWITCH CHECK LOGIC
        should_process = False
        if hasattr(self, "switch_state") and self.switch_state:
            _LOGGER.info(
                f"Device {device_id}: Switch is ON (using tracked state: "
                f"{self.switch_state})"
            )
            should_process = True
        else:
            # Fallback to hass.states.get() for older automation instances
            switch_state = self.hass.states.get(f"switch.dehumidify_{device_id}")
            if switch_state and switch_state.state == "on":
                _LOGGER.info(
                    f"Device {device_id}: Switch is ON (using hass.states: "
                    f"{switch_state.state})"
                )
                should_process = True
            else:
                _LOGGER.info(
                    f"Device {device_id}: Switch is OFF or not found - "
                    f"tracked: {getattr(self, 'switch_state', 'NOT SET')}, "
                    f"hass.states: "
                    f"{switch_state.state if switch_state else 'NOT FOUND'} - "
                    f"skipping automation"
                )
                return

        if not should_process:
            _LOGGER.debug(f"Device {device_id}: Skipping processing - switch not ON")
            return

        _LOGGER.info(f"🔍 SUCCESS: Device {device_id}: Will process state change")

        # Apply 45-second debouncing to prevent rapid fan changes
        if device_id in self._change_timers:
            _LOGGER.debug(f"Device {device_id}: Debouncing - ignoring rapid change")
            return

        _LOGGER.info(
            f"🔍 SUCCESS: Device {device_id}: Starting humidity processing (switch ON)"
        )

        # Set debouncing timer
        self._change_timers[device_id] = self.hass.loop.call_later(
            HUMIDITY_DEBOUNCE_SECONDS,
            lambda: self._change_timers.pop(device_id, None),
        )

        # Get all entity states for this device
        try:
            entity_states = await self._get_device_entity_states(device_id)
            _LOGGER.info(
                f"🔍 SUCCESS: Device {device_id}: Got entity states: {entity_states}"
            )
        except ValueError as e:
            _LOGGER.warning(
                f"🔍 CRITICAL: Device {device_id}: Invalid entity states - {e}"
            )
            return

        # Apply exact mermaid decision logic
        await self._process_automation_logic(device_id, entity_states)

    async def _process_humidity_logic(
        self, device_id: str, entity_states: dict[str, float]
    ) -> None:
        """Process humidity logic following exact mermaid decision flow.

        Implements the decision tree from humidity_decision_flow.md:
        - Indoor RH > Max? → Check Indoor abs vs Outdoor abs + Offset
        - Indoor RH < Min? → Check Indoor abs vs Outdoor abs - Offset
        - Between Min/Max? → No action (acceptable range)

        Args:
            device_id: Device identifier
            entity_states: Validated entity state values
        """
        indoor_rh = entity_states["indoor_rh"]
        indoor_abs = entity_states["indoor_abs"]
        outdoor_abs = entity_states["outdoor_abs"]
        max_humidity = entity_states["max_humidity"]
        min_humidity = entity_states["min_humidity"]
        offset = entity_states["offset"]

        _LOGGER.info(
            f"Device {device_id}: Processing humidity logic - "
            f"Indoor RH={indoor_rh}%, Indoor Abs={indoor_abs}g/m³, "
            f"Outdoor Abs={outdoor_abs}g/m³, Min={min_humidity}%, "
            f"Max={max_humidity}%, Offset={offset}"
        )
        _LOGGER.info(
            f"Device {device_id}: Decision thresholds - "
            f"High threshold = {max_humidity}%, Low threshold = {min_humidity}%, "
            f"Dehumidify threshold = {outdoor_abs} + {offset} = "
            f"{outdoor_abs + offset}, "
            f"Humidify threshold = {outdoor_abs} - {offset} = {outdoor_abs - offset}"
        )

        # EXACT MERMAID LOGIC IMPLEMENTATION

        # Decision D1: Indoor RH > Max?
        if indoor_rh > max_humidity:
            _LOGGER.info(
                f"Device {device_id}: DECISION D1 - Indoor RH ({indoor_rh}%) > "
                f"Max ({max_humidity}%) → CHECK DEHUMIDIFICATION"
            )

            # Decision I1: Indoor abs > Outdoor abs + Offset?
            dehumidify_threshold = outdoor_abs + offset
            _LOGGER.info(
                f"Device {device_id}: DECISION I1 - "
                f"Indoor abs ({indoor_abs}) vs Dehumidify threshold "
                f"({outdoor_abs} + {offset} = {dehumidify_threshold})"
            )

            if indoor_abs > outdoor_abs + offset:
                _LOGGER.info(
                    f"Device {device_id}: ✅ ACTIVE DEHUMIDIFICATION - "
                    f"Indoor abs ({indoor_abs}) > Outdoor abs "
                    f"({outdoor_abs}) + Offset ({offset}) "
                    f"→ Setting fan to HIGH"
                )
                await self._set_fan_high(device_id, "Active dehumidification")
            else:
                _LOGGER.info(
                    f"Device {device_id}: 🔄 AVOID MOISTURE - "
                    f"Indoor abs ({indoor_abs}) <= Outdoor abs "
                    f"({outdoor_abs}) + Offset ({offset}) "
                    f"→ Setting fan to LOW"
                )
                await self._set_fan_low(device_id, "Avoid bringing moisture")

        # Decision F1: Indoor RH < Min?
        elif indoor_rh < min_humidity:
            _LOGGER.info(
                f"Device {device_id}: DECISION F1 - Indoor RH ({indoor_rh}%) < "
                f"Min ({min_humidity}%) → CHECK HUMIDIFICATION"
            )

            # Decision K1: Indoor abs < Outdoor abs - Offset?
            humidify_threshold = outdoor_abs - offset
            _LOGGER.info(
                f"Device {device_id}: DECISION K1 - "
                f"Indoor abs ({indoor_abs}) vs Humidify threshold "
                f"({outdoor_abs} - {offset} = {humidify_threshold})"
            )

            if indoor_abs < outdoor_abs - offset:
                _LOGGER.info(
                    f"Device {device_id}: ✅ ACTIVE HUMIDIFICATION - "
                    f"Indoor abs ({indoor_abs}) < Outdoor abs "
                    f"({outdoor_abs}) - Offset ({offset}) "
                    f"→ Setting fan to HIGH"
                )
                await self._set_fan_high(device_id, "Active humidification")
            else:
                _LOGGER.info(
                    f"Device {device_id}: 🔄 AVOID OVER-HUMIDIFYING - "
                    f"Indoor abs ({indoor_abs}) >= Outdoor abs "
                    f"({outdoor_abs}) - Offset ({offset}) "
                    f"→ Setting fan to LOW"
                )
                await self._set_fan_low(device_id, "Avoid over-humidifying")
        else:
            # Indoor RH between Min/Max (acceptable range)

            # NEW: Fallback check - if binary sensor is ON (active dehumidification),
            # set fan to LOW. This handles the case where humidity is now acceptable
            # but the fan was left in HIGH mode from previous active dehumidification
            if self.binary_sensor and self.binary_sensor.is_on:
                _LOGGER.info(
                    f"Device {device_id}: 🔄 FALLBACK - Binary sensor is ON but RH is "
                    f"acceptable - Setting fan to LOW"
                )
                await self._set_fan_low(device_id, "Fallback: Acceptable RH range")
            else:
                _LOGGER.debug(
                    f"Device {device_id}: ✅ Binary sensor is OFF - no fallback needed"
                )

    async def _set_fan_high(self, device_id: str, reason: str) -> None:
        """Set fan to HIGH mode via fan_services.py.

        Args:
            device_id: Device identifier
            reason: Reason for setting HIGH mode
        """
        try:
            from ..services.fan_services import async_set_fan_speed_mode

            # Convert underscore device_id to colon format for fan service
            colon_device_id = device_id.replace("_", ":")

            _LOGGER.info(
                f"Setting fan HIGH for device {device_id} ({colon_device_id}) - "
                f"{reason}"
            )

            await async_set_fan_speed_mode(
                self.hass,
                colon_device_id,  # "32:153289"
                "high",
                reason=f"Humidity automation: {reason}",
            )

            # Update binary sensor to show active dehumidification
            if self.binary_sensor:
                await self.binary_sensor.async_turn_on()

            _LOGGER.info(f"Device {device_id}: Fan set HIGH - {reason}")

        except Exception as e:
            _LOGGER.error(f"Failed to set fan HIGH for device {device_id}: {e}")

    async def _set_fan_low(self, device_id: str, reason: str) -> None:
        """Set fan to LOW mode via fan_services.py.

        Args:
            device_id: Device identifier
            reason: Reason for setting LOW mode
        """
        try:
            from ..services.fan_services import async_set_fan_speed_mode

            # Convert underscore device_id to colon format for fan service
            colon_device_id = device_id.replace("_", ":")

            _LOGGER.info(
                f"Setting fan LOW for device {device_id} ({colon_device_id}) - {reason}"
            )

            await async_set_fan_speed_mode(
                self.hass,
                colon_device_id,  # "32:153289"
                "low",
                reason=f"Humidity automation: {reason}",
            )

            # Update binary sensor to show not actively dehumidifying
            if self.binary_sensor:
                await self.binary_sensor.async_turn_off()

            _LOGGER.info(f"Device {device_id}: Fan set LOW - {reason}")

        except Exception as e:
            _LOGGER.error(f"Failed to set fan LOW for device {device_id}: {e}")

    async def _reset_fan_to_auto(self, device_id: str) -> None:
        """Reset fan to AUTO when switch turned OFF.

        Args:
            device_id: Device identifier
        """
        try:
            from ..services.fan_services import async_set_fan_speed_mode

            # Convert underscore device_id to colon format for fan service
            colon_device_id = device_id.replace("_", ":")

            _LOGGER.info(
                f"Resetting fan to AUTO for device {device_id} ({colon_device_id})"
            )

            await async_set_fan_speed_mode(
                self.hass,
                colon_device_id,  # "32:153289"
                "auto",
                reason="Humidity automation: Switch turned OFF",
            )

            # Update binary sensor to show not actively controlling
            if self.binary_sensor:
                await self.binary_sensor.async_turn_off()

            _LOGGER.info(f"Device {device_id}: Fan reset to AUTO")

        except Exception as e:
            _LOGGER.error(f"Failed to reset fan AUTO for device {device_id}: {e}")

    async def _get_device_entity_states(self, device_id: str) -> dict[str, float]:
        """Get all entity states for a device with validation.

        Args:
            device_id: Device identifier (e.g., "32_153289")

        Returns:
            Dictionary with entity state values

        Raises:
            ValueError: If any entity is unavailable or has invalid values
        """
        states = {}

        # Get dynamic state mappings from const.py (now using moved function)
        state_mappings = get_feature_entity_mappings("humidity_control", device_id)

        for state_name, entity_id in state_mappings.items():
            state = self.hass.states.get(entity_id)

            if not state:
                raise ValueError(f"Entity {entity_id} not found")

            if state.state in ["unavailable", "unknown"]:
                raise ValueError(f"Entity {entity_id} state unavailable")

            try:
                value = float(state.state)
                states[state_name] = value
            except (ValueError, TypeError) as err:
                raise ValueError(
                    f"Entity {entity_id} has invalid numeric value: {state.state}"
                ) from err

        return states

    async def _validate_device_entities(self, device_id: str) -> bool:
        """Validate all required entities exist for a device.

        Uses the new entity generation helpers for consistent validation.

        Args:
            device_id: Device identifier

        Returns:
            True if all entities exist, False otherwise
        """
        missing_entities = []

        # CC entity: relative humidity sensor (unchanged)
        cc_entity_id = f"sensor.{device_id}_indoor_humidity"
        cc_exists = self.hass.states.get(cc_entity_id)
        _LOGGER.debug(
            f"Device {device_id}: CC entity {cc_entity_id} exists: "
            f"{cc_exists is not None}"
        )
        if not cc_exists:
            missing_entities.append(cc_entity_id)

        # Get humidity control feature definition
        humidity_feature = cast(
            dict[str, Any], AVAILABLE_FEATURES.get("humidity_control", {})
        )
        required_entities = cast(
            dict[str, list[str]], humidity_feature.get("required_entities", {})
        )

        # Check each required entity type using the new naming system
        # Direct mapping to new entity names (no more const_to_new_mapping needed)
        new_entity_mapping = {
            "indoor_abs_humid": ("sensor", "indoor_absolute_humidity"),
            "outdoor_abs_humid": ("sensor", "outdoor_absolute_humidity"),
            "rel_humid_min": ("number", "relative_humidity_minimum"),
            "rel_humid_max": ("number", "relative_humidity_maximum"),
            "abs_humid_offset": ("number", "absolute_humidity_offset"),
            "dehumidify": ("switch", "dehumidify"),
            "dehumidifying_active": ("binary_sensor", "dehumidifying_active"),
        }

        for entity_type, entity_list in required_entities.items():
            for const_entity_name in entity_list:
                # Get the new entity type and name from direct mapping
                if const_entity_name in new_entity_mapping:
                    entity_type_new, entity_name_new = new_entity_mapping[
                        const_entity_name
                    ]

                    # Entity names in const.py ARE the actual entity names
                    actual_entity_name = const_entity_name

                    # Generate the expected entity ID using helpers
                    expected_entity_id = (
                        EntityHelpers.generate_entity_name_from_template(
                            entity_type_new, actual_entity_name, device_id
                        )
                    )

                    if expected_entity_id:
                        # Check if this entity exists
                        entity_exists = self.hass.states.get(expected_entity_id)
                        if not entity_exists:
                            missing_entities.append(expected_entity_id)
                        else:
                            _LOGGER.debug(
                                f"Device {device_id}: Found expected entity "
                                f"{expected_entity_id}"
                            )
                    else:
                        _LOGGER.warning(
                            f"Device {device_id}: Could not generate entity ID for "
                            f"{entity_type_new}.{entity_name_new}"
                        )
                        missing_entities.append(
                            f"{entity_type_new}.{entity_name_new}_{device_id}"
                        )

        if missing_entities:
            _LOGGER.debug(f"Device {device_id}: Missing entities - {missing_entities}")
            return False

        return True

    async def _test_listeners_now(self) -> None:
        """Test if listeners are working by manually checking all number entities."""
        _LOGGER.info("🔍 TESTING LISTENERS: Manual check of all number entities")

        all_number_entities = self.hass.states.async_all("number")
        _LOGGER.info(f"🔍 Found {len(all_number_entities)} number entities total")

        # Show ALL number entities first
        _LOGGER.info("🔍 ALL NUMBER ENTITIES:")
        for i, entity in enumerate(all_number_entities):
            _LOGGER.info(f"   {i + 1:2d}. {entity.entity_id} = {entity.state}")

        # Find humidity-related entities
        humidity_entities = [
            e for e in all_number_entities if "humidity" in e.entity_id.lower()
        ]
        _LOGGER.info(
            f"🔍 Found {len(humidity_entities)} humidity-related number entities:"
        )
        for entity in humidity_entities:
            _LOGGER.info(f"   - {entity.entity_id} = {entity.state}")

        # Test each pattern against each entity
        _LOGGER.info(
            f"🔍 Testing {len(self.entity_patterns)} patterns against entities:"
        )
        for pattern in self.entity_patterns:
            _LOGGER.info(f"   Pattern: {pattern}")
            matches = 0
            for entity in all_number_entities:
                if pattern.endswith("*"):
                    prefix = pattern[:-1]  # Remove the *
                    _LOGGER.debug(
                        f"   Testing {entity.entity_id} startswith {prefix}: "
                        f"{entity.entity_id.startswith(prefix)}"
                    )
                    if entity.entity_id.startswith(prefix):
                        _LOGGER.info(f"   ✅ {entity.entity_id} matches {pattern}")
                        matches += 1
                elif entity.entity_id == pattern:
                    _LOGGER.info(f"   ✅ {entity.entity_id} exactly matches {pattern}")
                    matches += 1
            _LOGGER.info(f"   Pattern {pattern} matched {matches} entities")

        # Now try to find patterns that actually match
        _LOGGER.info("🔍 REVERSE TEST: What patterns would match existing entities?")
        for entity in all_number_entities:
            for pattern in self.entity_patterns:
                if pattern.endswith("*"):
                    prefix = pattern[:-1]  # Remove the *
                    if entity.entity_id.startswith(prefix):
                        _LOGGER.info(
                            f"   ✅ {entity.entity_id} matches pattern {pattern}"
                        )
