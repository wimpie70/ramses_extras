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

from ..const import AVAILABLE_FEATURES, DEVICE_ENTITY_MAPPING

_LOGGER = logging.getLogger(__name__)


class HumidityAutomationManager:
    """Manages hardcoded humidity automation logic.

    This class implements the exact decision logic from the mermaid diagram
    in humidity_decision_flow.md, replacing the YAML template system with
    direct Python automation.
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
        self.hass = hass
        self.binary_sensor = binary_sensor
        self.switch_state = switch_state
        _LOGGER.info(
            f"HumidityAutomationManager __init__ binary_sensor: {binary_sensor}, "
            f"switch_state: {switch_state}"
        )
        self._listeners: list[Any] = []  # State change listeners
        self._change_timers: dict[str, Any] = {}  # device_id -> timer for debouncing
        self._active = False

        # Cache for dynamically generated entity patterns and mappings
        self._entity_patterns: list[str] | None = None
        self._required_entities: list[str] | None = None
        self._state_mappings: dict[str, str] | None = None
        self._entity_configs: dict[str, dict[str, Any]] | None = None

    @property
    def entity_patterns(self) -> list[str]:
        """Generate entity patterns dynamically from const.py definitions."""
        if self._entity_patterns is None:
            self._entity_patterns = self._generate_entity_patterns()
        return self._entity_patterns

    @property
    def required_entities(self) -> list[str]:
        """Generate required entities dynamically from const.py definitions."""
        if self._required_entities is None:
            self._required_entities = self._generate_required_entities()
        return self._required_entities

    def _generate_entity_patterns(self) -> list[str]:
        """Generate entity patterns based on const.py definitions."""
        patterns = []

        # Add CC entity pattern for relative humidity
        patterns.append("*_indoor_humidity")  # CC: sensor.32_153289_indoor_humidity

        # Get humidity control feature definition
        humidity_feature = cast(
            dict[str, Any], AVAILABLE_FEATURES.get("humidity_control", {})
        )
        required_entities = cast(
            dict[str, list[str]], humidity_feature.get("required_entities", {})
        )

        # Add Extras entity patterns based on required entities -
        # but use actual entity names (name first, then device_id)
        for entity_type, entity_list in required_entities.items():
            for const_entity_name in entity_list:
                # Convert const.py names to actual entity names
                actual_entity_name = self._get_entity_name_from_const(const_entity_name)

                if entity_type == "sensors":
                    patterns.append(f"sensor.{actual_entity_name}_*")
                elif entity_type == "switches":
                    patterns.append(f"switch.{actual_entity_name}_*")
                elif entity_type == "numbers":
                    patterns.append(f"number.{actual_entity_name}_*")
                elif entity_type == "binary_sensors":
                    patterns.append(f"binary_sensor.{actual_entity_name}_*")

        return patterns

    def _generate_required_entities(self) -> list[str]:
        """Generate required entities based on const.py definitions."""
        entities = []

        # Add CC entity for relative humidity
        entities.append("indoor_humidity")  # CC: sensor.32_153289_indoor_humidity

        # Get humidity control feature definition
        humidity_feature = cast(
            dict[str, Any], AVAILABLE_FEATURES.get("humidity_control", {})
        )
        required_entities = cast(
            dict[str, list[str]], humidity_feature.get("required_entities", {})
        )

        # Add Extras entities based on required entities - but use actual entity names
        for entity_type, entity_list in required_entities.items():
            for const_entity_name in entity_list:
                # Convert const.py names to actual entity names
                actual_entity_name = self._get_entity_name_from_const(const_entity_name)

                if entity_type == "sensors":
                    entities.append(f"sensor.{actual_entity_name}")
                elif entity_type == "switches":
                    entities.append(f"switch.{actual_entity_name}")
                elif entity_type == "numbers":
                    entities.append(f"number.{actual_entity_name}")
                elif entity_type == "binary_sensors":
                    entities.append(f"binary_sensor.{actual_entity_name}")

        return entities

    def _get_entity_name_from_const(self, const_entity_name: str) -> str:
        """Convert const.py entity name to actual entity_id name.

        Args:
            const_entity_name: Entity name from const.py (e.g., "indoor_abs_humid")

        Returns:
            Actual entity name used in entity_id (e.g., "indoor_absolute_humidity")
        """
        # Map from const.py names to actual entity_id names
        name_mapping = {
            "indoor_abs_humid": "indoor_absolute_humidity",
            "outdoor_abs_humid": "outdoor_absolute_humidity",
            "rel_humid_min": "relative_humidity_minimum",
            "rel_humid_max": "relative_humidity_maximum",
            "abs_humid_offset": "absolute_humidity_offset",
        }

        return name_mapping.get(const_entity_name, const_entity_name)

    def _get_state_mappings(self, device_id: str) -> dict[str, str]:
        """Generate state mappings dynamically using const.py entity names.

        This method uses the const.py definitions to generate the correct entity IDs
        that match what the entity managers actually create.

        Args:
            device_id: Device identifier (e.g., "32_153289")

        Returns:
            Dictionary mapping state names to entity IDs
        """
        # Get humidity control feature definition
        humidity_feature = cast(
            dict[str, Any], AVAILABLE_FEATURES.get("humidity_control", {})
        )
        required_entities = cast(
            dict[str, list[str]], humidity_feature.get("required_entities", {})
        )

        # Map state names to const.py entity types
        state_to_entity_mapping = {
            "indoor_abs": "indoor_abs_humid",
            "outdoor_abs": "outdoor_abs_humid",
            "max_humidity": "rel_humid_max",
            "min_humidity": "rel_humid_min",
            "offset": "abs_humid_offset",
        }

        # Convert plural entity type to singular for prefix mapping
        plural_to_singular = {
            "sensors": "sensor",
            "switches": "switch",
            "numbers": "number",
            "binary_sensors": "binary_sensor",
        }

        # Map entity types to correct prefixes (singular, not plural)
        prefix_mapping = {
            "sensor": "sensor",
            "number": "number",
            "switch": "switch",
            "binary_sensor": "binary_sensor",
        }

        mappings = {
            # CC entity: relative humidity sensor
            "indoor_rh": f"sensor.{device_id}_indoor_humidity",
        }

        # Generate entity IDs for each state using the const.py definitions
        for state_name, const_entity_type in state_to_entity_mapping.items():
            # Check if this entity type is required
            if self._is_entity_type_required(const_entity_type, required_entities):
                # Get the actual entity name from const.py name
                actual_entity_name = self._get_entity_name_from_const(const_entity_type)

                # Find which entity type group this belongs to
                singular_entity_type = None
                for plural_type, singular_type in plural_to_singular.items():
                    if const_entity_type in required_entities.get(plural_type, []):
                        singular_entity_type = singular_type
                        break

                # Default to number if not found
                if not singular_entity_type:
                    if const_entity_type in ["indoor_abs_humid", "outdoor_abs_humid"]:
                        singular_entity_type = "sensor"
                    elif const_entity_type in [
                        "rel_humid_min",
                        "rel_humid_max",
                        "abs_humid_offset",
                    ]:
                        singular_entity_type = "number"
                    elif const_entity_type == "dehumidify":
                        singular_entity_type = "switch"
                    elif const_entity_type == "dehumidifying_active":
                        singular_entity_type = "binary_sensor"
                    else:
                        singular_entity_type = "number"  # Default

                # Get the correct entity prefix
                entity_prefix = prefix_mapping.get(
                    singular_entity_type, singular_entity_type
                )

                # Construct the full entity ID
                # CORRECT FORMAT: {prefix}.{entity_name}_{device_id}
                # (not {device_id}_{entity_name})
                mappings[state_name] = (
                    f"{entity_prefix}.{actual_entity_name}_{device_id}"
                )

        return mappings

    def _is_entity_type_required(
        self, entity_type: str, required_entities: dict[str, list[str]]
    ) -> bool:
        """Check if an entity type is required for humidity control.

        Args:
            entity_type: Entity type to check (e.g., "indoor_abs_humid")
            required_entities: Required entities from const.py

        Returns:
            True if entity type is required, False otherwise
        """
        for entity_list in required_entities.values():
            if entity_type in entity_list:
                return True
        return False

    async def start(self) -> None:
        """Start the humidity automation.

        Starts immediately without waiting for entities to avoid blocking HA startup.
        """
        if self._active:
            _LOGGER.warning("Humidity automation already started")
            return

        _LOGGER.info(
            "🚀 Starting humidity automation immediately (non-blocking startup)"
        )
        _LOGGER.info(f"📋 Entity patterns to listen for: {self.entity_patterns}")
        _LOGGER.info(
            "🔧 Registering global state listeners for immediate responsiveness"
        )

        # Register global state listeners immediately (don't wait for entities)
        # This allows the automation to respond as soon as entities become available
        await self._register_global_listeners()

        # Start in non-blocking mode - will activate automatically
        #  when entities are available
        self._active = True
        _LOGGER.info("✅ Humidity automation started successfully (non-blocking)")
        _LOGGER.info(
            "🎯 Will activate automatically when humidity control "
            "switches are turned ON"
        )

        # Schedule entity verification and listener testing to happen in the background
        # This won't block startup but will verify entities and
        # test listeners when ready
        self.hass.async_create_task(self._verify_entities_async())

        # Test listeners after entities are available (with a small delay)
        self.hass.async_create_task(self._delayed_listener_test())

    async def _delayed_listener_test(self) -> None:
        """Run listener test with a small delay to ensure entities are created."""
        await asyncio.sleep(5)  # Wait 5 seconds for entities to be created
        await self._test_listeners_now()

        # Immediately evaluate current humidity conditions if switch is on
        await self._evaluate_current_conditions()

    async def stop(self) -> None:
        """Stop the humidity automation and clean up resources."""
        if not self._active:
            return

        _LOGGER.info("Stopping humidity automation")

        # Remove all state listeners
        for listener in self._listeners:
            listener()
        self._listeners.clear()

        # Cancel all debouncing timers
        await self._cancel_all_timers()

        self._active = False
        _LOGGER.info("Humidity automation stopped")

    async def _wait_for_entities(self, timeout: int = 90) -> bool:
        """Wait for entities to be created before starting automation.

        Args:
            timeout: Maximum time to wait in seconds

        Returns:
            True if entities are ready, False if timeout occurred
        """
        _LOGGER.info(f"Waiting for humidity entities (timeout: {timeout}s)")
        start_time = time.time()
        attempt = 0

        while time.time() - start_time < timeout:
            attempt += 1

            # Check if we have any devices with all required entities
            if await self._check_any_device_ready():
                _LOGGER.info(
                    f"Humidity automation: Entities ready after {attempt} attempts"
                )
                return True

            # Log progress every 10 attempts
            if attempt % 10 == 0:
                elapsed = time.time() - start_time
                _LOGGER.debug(
                    f"Still waiting for entities... ({elapsed:.1f}s elapsed, "
                    f"{attempt} attempts)"
                )

            await asyncio.sleep(1)

        _LOGGER.warning(
            "Humidity automation: Timeout waiting for entities, proceeding anyway"
        )
        _LOGGER.info(
            "Starting automation without entity verification - "
            "will activate when entities become available"
        )
        return False

    async def _check_any_device_ready(self) -> bool:
        """Check if any device has all required entities ready.

        Returns:
            True if at least one device is ready
        """
        # Look for humidity control switches
        switches = self.hass.states.async_all("switch")
        dehumidify_switches = [
            state
            for state in switches
            if state.entity_id.startswith("switch.dehumidify_")
        ]

        if not dehumidify_switches:
            return False

        # Check each device has all required entities
        for switch_state in dehumidify_switches:
            device_id = self._extract_device_id(switch_state.entity_id)
            if device_id and await self._validate_device_entities(device_id):
                _LOGGER.debug(f"Device {device_id} has all entities ready")
                return True

        return False

    async def _verify_entities_async(self) -> None:
        """Verify entities in background without blocking startup."""
        _LOGGER.debug("Starting background entity verification")
        try:
            entities_ready = await self._wait_for_entities()
            if entities_ready:
                _LOGGER.info("Humidity automation: Entities verified and ready")
            else:
                _LOGGER.debug(
                    "Humidity automation: Entities not yet available - "
                    "will activate when ready"
                )
        except Exception as e:
            _LOGGER.debug(
                f"Humidity automation: Background entity verification failed: {e}"
            )

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
            await self._process_humidity_logic(device_id, entity_states)
        except Exception as e:
            _LOGGER.debug(
                f"Could not evaluate current conditions for device {device_id}: {e}"
            )

    async def _register_global_listeners(self) -> None:
        """Register global state change listeners for all entity patterns."""
        _LOGGER.info("🔧 Registering global state listeners for humidity automation")
        _LOGGER.info(f"📋 Entity patterns to register: {self.entity_patterns}")

        # 🔍 ADDITIONAL DEBUG: Log the actual patterns being generated
        for pattern in self.entity_patterns:
            _LOGGER.info(
                f"🔍 PATTERN: '{pattern}' should match entities like: "
                f"{pattern.replace('*', '32_153289')}"
            )

        for pattern in self.entity_patterns:
            _LOGGER.info(f"📡 Registering listener for pattern: {pattern}")

            # 📋 CRITICAL DEBUG: Add extra logging to listener registration
            _LOGGER.debug(
                f"🔍 About to call async_track_state_change for pattern: {pattern}"
            )

            listener = async_track_state_change(
                self.hass, pattern, self._handle_state_change
            )

            # Verify listener was created
            if listener:
                self._listeners.append(listener)
                _LOGGER.info(f"✅ Registered listener for pattern: {pattern}")
                _LOGGER.debug(f"🔍 Listener created successfully for {pattern}")
            else:
                _LOGGER.error(f"❌ Failed to create listener for pattern: {pattern}")

        _LOGGER.info(f"📡 Total state listeners registered: {len(self._listeners)}")

        # 📋 CRITICAL DEBUG: Log all registered listeners
        for i, pattern in enumerate(self.entity_patterns):
            if i < len(self._listeners):
                _LOGGER.debug(f"🔍 Listener {i + 1}: {pattern} -> {self._listeners[i]}")

    async def _cancel_all_timers(self) -> None:
        """Cancel all pending debouncing timers."""
        for timer in self._change_timers.values():
            timer.cancel()
        self._change_timers.clear()
        _LOGGER.debug("Cancelled all debouncing timers")

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

        # Schedule async processing to avoid blocking the event loop
        self.hass.async_create_task(
            self._async_handle_state_change(entity_id, old_state, new_state)
        )

    async def _async_handle_state_change(
        self, entity_id: str, old_state: State | None, new_state: State | None
    ) -> None:
        """Handle state changes following exact mermaid decision flow.

        This method implements the decision logic from humidity_decision_flow.md:
        1. Extract device_id from entity name
        2. Validate all entities exist for this device
        3. Check if dehumidify switch is ON (only process when ON)
        4. Apply 2-minute debouncing
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

        # Apply 2-minute debouncing to prevent rapid fan changes
        if device_id in self._change_timers:
            _LOGGER.debug(f"Device {device_id}: Debouncing - ignoring rapid change")
            return

        _LOGGER.info(
            f"🔍 SUCCESS: Device {device_id}: Starting humidity processing (switch ON)"
        )

        # Set debouncing timer
        self._change_timers[device_id] = self.hass.loop.call_later(
            120,  # 2 minutes
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
        await self._process_humidity_logic(device_id, entity_states)

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

        # Get dynamic state mappings from const.py
        state_mappings = self._get_state_mappings(device_id)

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
            # No action: Indoor RH between Min/Max (acceptable range)
            _LOGGER.info(
                f"Device {device_id}: 🎯 NO ACTION - Indoor RH ({indoor_rh}%) between "
                f"Min/Max range ({min_humidity}%-{max_humidity}%) → "
                f"Acceptable humidity level"
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

    async def _validate_device_entities(self, device_id: str) -> bool:
        """Validate all required entities exist for a device.

        Uses dynamic entity generation based on const.py definitions.

        Args:
            device_id: Device identifier

        Returns:
            True if all entities exist, False otherwise
        """
        missing_entities = []

        # CC entity: relative humidity sensor
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

        # Debug: log all available entities for this device
        all_entities = self.hass.states.async_all()
        device_entities = [
            e.entity_id for e in all_entities if device_id in e.entity_id
        ]
        _LOGGER.debug(f"Device {device_id}: Found {len(device_entities)} entities")

        # Check each required entity type
        for entity_type, entity_list in required_entities.items():
            for const_entity_name in entity_list:
                # Get the actual entity name from const.py name
                actual_entity_name = self._get_entity_name_from_const(const_entity_name)

                # Convert plural entity type to singular for prefix mapping
                # "sensors" -> "sensor", "switches" -> "switch", etc.
                plural_to_singular = {
                    "sensors": "sensor",
                    "switches": "switch",
                    "numbers": "number",
                    "binary_sensors": "binary_sensor",
                }

                # Get the correct singular entity type
                singular_entity_type = plural_to_singular.get(entity_type, entity_type)

                # Map entity types to correct prefixes (singular, not plural)
                prefix_mapping = {
                    "sensor": "sensor",
                    "number": "number",
                    "switch": "switch",
                    "binary_sensor": "binary_sensor",
                }

                # Get the correct entity prefix
                entity_prefix = prefix_mapping.get(
                    singular_entity_type, singular_entity_type
                )

                # Construct the full entity ID
                # CORRECT FORMAT: {prefix}.{entity_name}_{device_id}
                # (not {device_id}_{entity_name})
                expected_entity_id = f"{entity_prefix}.{actual_entity_name}_{device_id}"

                # Check if this entity exists
                entity_exists = self.hass.states.get(expected_entity_id)
                _LOGGER.debug(
                    f"Device {device_id}: Expected {expected_entity_id} exists: "
                    f"{entity_exists is not None}"
                )

                if not entity_exists:
                    missing_entities.append(expected_entity_id)
                else:
                    _LOGGER.debug(
                        f"Device {device_id}: Found expected entity "
                        f"{expected_entity_id}"
                    )

        if missing_entities:
            _LOGGER.debug(f"Device {device_id}: Missing entities - {missing_entities}")
            return False

        return True

    def _extract_device_id(self, entity_id: str) -> str | None:
        """Extract device_id from entity name.

        Expected formats:
        - {entity_type}.{entity_name}_{device_id} (e.g.,
        number.relative_humidity_maximum_32_153289)
        - {entity_type}.{entity_name}:{device_id} (e.g.,
         number.32:153289_rel_humid_max)

        Args:
            entity_id: Entity identifier

        Returns:
            Device identifier in underscore format (e.g., "32_153289")
            or None if extraction fails
        """
        # Pattern 1: entity_type.entity_name_deviceid (underscore format)
        # Example: number.relative_humidity_maximum_32_153289
        match = re.search(r"([^_]+)_(32_\d+)$", entity_id)
        if match:
            return match.group(2)  # "32_153289"

        # Pattern 2: entity_type.entity_name_deviceid (colon format)
        # Example: number.32:153289_rel_humid_max
        match = re.search(r"([^:]+):([0-9]+:[0-9]+)_", entity_id)
        if match:
            return match.group(2).replace(":", "_")  # "32_153289"

        # Pattern 3: entity_type.32_153289_entityname (reverse order)
        # Example: switch.32_153289_dehumidify
        match = re.search(r"\.(\d+_\d+)_", entity_id)
        if match:
            return match.group(1)  # "32_153289"

        # Pattern 4: entity_type.32:153289_entityname (reverse order, colon)
        # Example: switch.32:153289_dehumidify
        match = re.search(r"\.(\d+:\d+)_", entity_id)
        if match:
            return match.group(1).replace(":", "_")  # "32_153289"

        # Pattern 5: entity_type.entityname_32:153289 (colon at end)
        match = re.search(r"_(\d+:\d+)$", entity_id)
        if match:
            return match.group(1).replace(":", "_")  # "32_153289"

        _LOGGER.warning(f"Could not extract device_id from entity: {entity_id}")
        return None

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
