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
from typing import Any, Dict, List, Optional, Set

from homeassistant.core import HomeAssistant, State, callback
from homeassistant.helpers.event import async_track_state_change

_LOGGER = logging.getLogger(__name__)


class HumidityAutomationManager:
    """Manages hardcoded humidity automation logic.

    This class implements the exact decision logic from the mermaid diagram
    in humidity_decision_flow.md, replacing the YAML template system with
    direct Python automation.
    """

    # Global entity patterns to monitor across all devices
    ENTITY_PATTERNS = [
        "sensor.indoor_relative_humidity_*",
        "sensor.indoor_absolute_humidity_*",
        "sensor.outdoor_absolute_humidity_*",
        "number.absolute_humidity_offset_*",
        "number.max_humidity_*",
        "number.min_humidity_*",
        "switch.dehumidify_*",
    ]

    # Required entities for each device
    REQUIRED_ENTITIES = [
        "sensor.indoor_relative_humidity",
        "sensor.indoor_absolute_humidity",
        "sensor.outdoor_absolute_humidity",
        "number.absolute_humidity_offset",
        "number.max_humidity",
        "number.min_humidity",
        "switch.dehumidify",
        "binary_sensor.dehumidifying_active",
    ]

    def __init__(self, hass: HomeAssistant):
        """Initialize the humidity automation manager.

        Args:
            hass: Home Assistant instance
        """
        self.hass = hass
        self._listeners: list[Any] = []  # State change listeners
        self._change_timers: dict[str, Any] = {}  # device_id -> timer for debouncing
        self._active = False

    async def start(self) -> None:
        """Start the humidity automation.

        Waits for entities to be created, then registers global state listeners.
        """
        if self._active:
            _LOGGER.warning("Humidity automation already started")
            return

        _LOGGER.info("Starting humidity automation")
        _LOGGER.debug(
            "Registering global state listeners first for immediate responsiveness"
        )

        # Register global state listeners immediately (don't wait for entities)
        # This allows the automation to respond as soon as entities become available
        await self._register_global_listeners()

        # Try to wait for entities, but don't fail if they timeout
        entities_ready = await self._wait_for_entities()

        if not entities_ready:
            _LOGGER.info("Humidity automation started without entity verification")
            _LOGGER.info("Will activate when humidity control switches are turned ON")
        else:
            _LOGGER.info("Humidity automation ready for immediate operation")

        self._active = True
        _LOGGER.info("Humidity automation started successfully")

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

    async def _register_global_listeners(self) -> None:
        """Register global state change listeners for all entity patterns."""
        _LOGGER.debug("Registering global state listeners")

        for pattern in self.ENTITY_PATTERNS:
            listener = async_track_state_change(
                self.hass, pattern, self._handle_state_change
            )
            self._listeners.append(listener)

        _LOGGER.info(f"Registered {len(self._listeners)} state listeners")

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
            return

        # Extract device_id from entity name
        device_id = self._extract_device_id(entity_id)
        if not device_id:
            _LOGGER.warning(f"Could not extract device_id from entity: {entity_id}")
            return

        _LOGGER.debug(
            f"State change: {entity_id} -> {new_state.state} (device: {device_id})"
        )

        # Validate all entities exist for this device
        if not await self._validate_device_entities(device_id):
            _LOGGER.warning(f"Device {device_id} entities not ready")
            return

        # Reset logic: switch turned OFF (separate automation in YAML template)
        if entity_id == f"switch.dehumidify_{device_id}" and new_state.state == "off":
            _LOGGER.info(
                f"Device {device_id}: Dehumidify switch turned OFF - resetting fan"
            )
            await self._reset_fan_to_auto(device_id)
            return

        # Only process if switch is ON
        switch_state = self.hass.states.get(f"switch.dehumidify_{device_id}")
        if not switch_state or switch_state.state != "on":
            _LOGGER.debug(f"Device {device_id}: Dehumidify switch not ON - skipping")
            return

        # Apply 2-minute debouncing to prevent rapid fan changes
        if device_id in self._change_timers:
            _LOGGER.debug(f"Device {device_id}: Debouncing - ignoring rapid change")
            return

        # Set debouncing timer
        self._change_timers[device_id] = self.hass.loop.call_later(
            120,  # 2 minutes
            lambda: self._change_timers.pop(device_id, None),
        )

        # Get all entity states for this device
        try:
            entity_states = await self._get_device_entity_states(device_id)
        except ValueError as e:
            _LOGGER.warning(f"Device {device_id}: Invalid entity states - {e}")
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

        state_mappings = {
            "indoor_rh": f"sensor.indoor_relative_humidity_{device_id}",
            "indoor_abs": f"sensor.indoor_absolute_humidity_{device_id}",
            "outdoor_abs": f"sensor.outdoor_absolute_humidity_{device_id}",
            "max_humidity": f"number.max_humidity_{device_id}",
            "min_humidity": f"number.min_humidity_{device_id}",
            "offset": f"number.absolute_humidity_offset_{device_id}",
        }

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

        _LOGGER.debug(
            f"Device {device_id}: Processing humidity logic "
            f"RH={indoor_rh}%, Abs_in={indoor_abs}, Abs_out={outdoor_abs}, "
            f"Min={min_humidity}%, Max={max_humidity}%, Offset={offset}"
        )

        # EXACT MERMAID LOGIC IMPLEMENTATION

        # Decision D1: Indoor RH > Max?
        if indoor_rh > max_humidity:
            _LOGGER.debug(
                f"Device {device_id}: Indoor RH ({indoor_rh}) > Max ({max_humidity})"
            )

            # Decision I1: Indoor abs > Outdoor abs + Offset?
            if indoor_abs > outdoor_abs + offset:
                _LOGGER.info(
                    f"Device {device_id}: Active dehumidification - "
                    f"Indoor abs ({indoor_abs}) > Outdoor abs ({outdoor_abs}) + "
                    f"Offset ({offset})"
                )
                await self._set_fan_high(device_id, "Active dehumidification")
            else:
                _LOGGER.info(
                    f"Device {device_id}: Avoid bringing moisture - "
                    f"Indoor abs ({indoor_abs}) <= Outdoor abs ({outdoor_abs}) + "
                    f"Offset ({offset})"
                )
                await self._set_fan_low(device_id, "Avoid bringing moisture")

        # Decision F1: Indoor RH < Min?
        elif indoor_rh < min_humidity:
            _LOGGER.debug(
                f"Device {device_id}: Indoor RH ({indoor_rh}) < Min ({min_humidity})"
            )

            # Decision K1: Indoor abs < Outdoor abs - Offset?
            if indoor_abs < outdoor_abs - offset:
                _LOGGER.info(
                    f"Device {device_id}: Active humidification - "
                    f"Indoor abs ({indoor_abs}) < Outdoor abs ({outdoor_abs}) - "
                    f"Offset ({offset})"
                )
                await self._set_fan_high(device_id, "Active humidification")
            else:
                _LOGGER.info(
                    f"Device {device_id}: Avoid over-humidifying - "
                    f"Indoor abs ({indoor_abs}) >= Outdoor abs ({outdoor_abs}) - "
                    f"Offset ({offset})"
                )
                await self._set_fan_low(device_id, "Avoid over-humidifying")
        else:
            # No action: Indoor RH between Min/Max (acceptable range)
            _LOGGER.debug(
                f"Device {device_id}: Indoor RH ({indoor_rh}) between Min/Max range "
                f"({min_humidity}%-{max_humidity}%) - no action"
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

            # Update binary sensor: HIGH mode = active dehumidifying
            binary_entity_id = f"binary_sensor.dehumidifying_active_{device_id}"
            await self.hass.services.async_call(
                "binary_sensor", "turn_on", {"entity_id": binary_entity_id}
            )

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

            # Update binary sensor: LOW mode = not actively dehumidifying
            binary_entity_id = f"binary_sensor.dehumidifying_active_{device_id}"
            await self.hass.services.async_call(
                "binary_sensor", "turn_off", {"entity_id": binary_entity_id}
            )

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

            # Update binary sensor: OFF when not actively controlling
            binary_entity_id = f"binary_sensor.dehumidifying_active_{device_id}"
            await self.hass.services.async_call(
                "binary_sensor", "turn_off", {"entity_id": binary_entity_id}
            )

            _LOGGER.info(f"Device {device_id}: Fan reset to AUTO")

        except Exception as e:
            _LOGGER.error(f"Failed to reset fan AUTO for device {device_id}: {e}")

    async def _validate_device_entities(self, device_id: str) -> bool:
        """Validate all required entities exist for a device.

        Args:
            device_id: Device identifier

        Returns:
            True if all entities exist, False otherwise
        """
        missing_entities = []

        for entity_template in self.REQUIRED_ENTITIES:
            entity_id = f"{entity_template}_{device_id}"
            if not self.hass.states.get(entity_id):
                missing_entities.append(entity_id)

        if missing_entities:
            _LOGGER.debug(f"Device {device_id}: Missing entities - {missing_entities}")
            return False

        return True

    def _extract_device_id(self, entity_id: str) -> str | None:
        """Extract device_id from entity name.

        Expected format: {entity_type}.{entity_name}_{device_id}

        Args:
            entity_id: Entity identifier

        Returns:
            Device identifier (e.g., "32_153289") or None if extraction fails
        """
        # Pattern: entity_type.entity_name_deviceid
        # Example: switch.dehumidify_32_153289

        match = re.search(r"([^_]+)_(32_\d+)$", entity_id)
        if match:
            return match.group(2)  # "32_153289"

        # Alternative pattern for different entity names
        match = re.search(r"_([0-9]+_[0-9]+)$", entity_id)
        if match:
            return match.group(1)  # "32_153289"

        _LOGGER.warning(f"Could not extract device_id from entity: {entity_id}")
        return None
