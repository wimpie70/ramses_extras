"""Base automation class for Ramses Extras framework.

This module provides a reusable base class that contains generic automation patterns
shared across all Ramses Extras automations, such as state change handling, entity
validation, lifecycle management, and timer debouncing.

The base class is designed to be extended by specific automation implementations
like humidity control, temperature control, etc.
"""

import asyncio
import logging
import time
from abc import ABC, abstractmethod

# Avoid circular imports by importing when needed in methods
from typing import Any

from homeassistant.core import HomeAssistant, State
from homeassistant.helpers.event import async_track_state_change

from ..helpers.automation.core import (
    _get_required_entities_from_feature,
    _singularize_entity_type,
)

_LOGGER = logging.getLogger(__name__)


class ExtrasBaseAutomation(ABC):
    """Abstract base class for Ramses Extras automations.

    This class provides generic automation patterns that are common across all
    Ramses Extras automations, including:
    - Lifecycle management (start/stop)
    - State change handling with debouncing
    - Entity validation and discovery
    - Timer management
    - Generic listener registration

    Derived classes must implement the abstract methods to provide
    feature-specific functionality.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        feature_id: str,
        binary_sensor: Any = None,
        debounce_seconds: int = 45,
    ) -> None:
        """Initialize the base automation.

        Args:
            hass: Home Assistant instance
            feature_id: Feature identifier (e.g., "humidity_control")
            binary_sensor: Optional binary sensor to update for automation status
            debounce_seconds: Debounce duration in seconds (default: 45)
        """
        self.hass = hass
        self.feature_id = feature_id
        self.binary_sensor = binary_sensor
        self.debounce_seconds = debounce_seconds

        # Generic automation state
        self._listeners: list[Any] = []  # State change listeners
        self._change_timers: dict[str, Any] = {}  # device_id -> timer for debouncing
        self._active = False
        self._specific_entity_ids: set[str] = set()

        # Cache for entity patterns
        self._entity_patterns: list[str] | None = None

        # Validation throttling
        self._last_validation_time: dict[str, float] = {}  # device_id -> timestamp
        self._validation_cooldown = 30  # seconds between validation for same device

        _LOGGER.info(
            f"ExtrasBaseAutomation initialized for feature: {feature_id}, "
            f"debounce: {debounce_seconds}s"
        )

    # ==================== LIFECYCLE MANAGEMENT ====================

    async def start(self) -> None:
        """Start the automation with entity verification.

        Starts the automation in non-blocking mode, verifying entities
        in the background and activating when ready.
        """
        if self._active:
            _LOGGER.warning(
                f"Automation {self.feature_id} already started, "
                f"skipping duplicate start"
            )
            return

        _LOGGER.info(f"🚀 Starting {self.feature_id} automation (non-blocking startup)")
        _LOGGER.info(f"📋 Entity patterns: {self.entity_patterns}")
        _LOGGER.info("🔧 Registering automation infrastructure")

        # Mark as active immediately
        self._active = True

        # Schedule entity verification in background
        self.hass.async_create_task(self._verify_entities_and_register_listeners())

        _LOGGER.info(f"✅ {self.feature_id} automation started successfully")
        _LOGGER.info(
            f"🎯 Will activate automatically when {self.feature_id} entities are ready"
        )

    async def stop(self) -> None:
        """Stop the automation and clean up all resources."""
        if not self._active:
            return

        _LOGGER.info(f"Stopping {self.feature_id} automation")

        # Remove all state listeners
        for listener in self._listeners:
            listener()
        self._listeners.clear()

        # Cancel all debouncing timers
        await self._cancel_all_timers()

        self._active = False
        self._specific_entity_ids.clear()

        _LOGGER.info(f"{self.feature_id} automation stopped")

    # ==================== ENTITY PATTERNS ====================

    @property
    def entity_patterns(self) -> list[str]:
        """Get entity patterns for this automation feature.

        Returns:
            List of entity patterns to listen for
        """
        if self._entity_patterns is None:
            self._entity_patterns = self._generate_entity_patterns()
        return self._entity_patterns

    def _generate_entity_patterns_default(self) -> list[str]:
        """Generate default entity patterns based on feature configuration.

        This method provides sensible defaults that derived classes can use.
        It is not abstract and provides a base implementation.

        Returns:
            List of entity patterns
        """
        patterns = []

        # Get required entities from the feature's own module
        required_entities = _get_required_entities_from_feature(self.feature_id)

        for entity_type, entity_names in required_entities.items():
            for entity_name in entity_names:
                # Use proper singularization for entity types
                entity_base_type = _singularize_entity_type(entity_type)
                patterns.append(f"{entity_base_type}.{entity_name}_*")

        return patterns

    def _generate_entity_patterns(self) -> list[str]:
        """Generate entity patterns based on feature configuration.

        This method delegates to the default implementation. Derived classes
        can override this method to provide custom patterns.

        Returns:
            List of entity patterns
        """
        return self._generate_entity_patterns_default()

    # ==================== ENTITY VERIFICATION ====================

    async def _wait_for_entities(self, timeout: int = 90) -> bool:
        """Wait for entities to be created before starting automation.

        Args:
            timeout: Maximum time to wait in seconds

        Returns:
            True if entities are ready, False if timeout occurred
        """
        _LOGGER.info(f"Waiting for {self.feature_id} entities (timeout: {timeout}s)")
        start_time = time.time()
        attempt = 0

        while time.time() - start_time < timeout:
            attempt += 1

            if await self._check_any_device_ready():
                _LOGGER.info(
                    f"{self.feature_id} automation: "
                    f"Entities ready after {attempt} attempts"
                )
                return True

            # Log progress every 10 attempts
            if attempt % 10 == 0:
                elapsed = time.time() - start_time
                _LOGGER.debug(
                    f"Still waiting for {self.feature_id} entities... "
                    f"({elapsed:.1f}s elapsed, {attempt} attempts)"
                )

            await asyncio.sleep(1)

        _LOGGER.warning(
            f"{self.feature_id} automation: "
            f"Timeout waiting for entities, proceeding anyway"
        )
        return False

    async def _check_any_device_ready(self) -> bool:
        """Check if any device has all required entities ready.

        Returns:
            True if at least one device is ready
        """
        # Get the first entity type to look for devices
        required_entities = _get_required_entities_from_feature(self.feature_id)

        _LOGGER.info(f"🔍 Required entities for {self.feature_id}: {required_entities}")

        if not required_entities:
            _LOGGER.warning(f"No required entities found for {self.feature_id}")
            return False

        # Check if any entity types actually have entity names
        entity_types_with_entities = [
            (entity_type, entity_names)
            for entity_type, entity_names in required_entities.items()
            if entity_names and len(entity_names) > 0
        ]

        if not entity_types_with_entities:
            _LOGGER.warning(
                f"No entity types have entities defined for {self.feature_id}: "
                f"{required_entities}"
            )
            return False

        # Use the first entity type that has entities as a starting point
        if not entity_types_with_entities:
            _LOGGER.warning(
                f"No entity types with entities found for {self.feature_id}"
            )
            return False

        first_entity_type, first_entity_names = entity_types_with_entities[0]

        # More robust check for empty or None entity names
        if not first_entity_names or len(first_entity_names) == 0:
            _LOGGER.warning(
                f"Entity type {first_entity_type} has no entity names defined"
            )
            return False

        first_entity_name = first_entity_names[0]
        entity_base_type = _singularize_entity_type(first_entity_type)

        # Look for entities of this type
        entities = self.hass.states.async_all(entity_base_type)
        matching_entities = [
            state
            for state in entities
            if state.entity_id.startswith(f"{entity_base_type}.{first_entity_name}_")
        ]

        _LOGGER.debug(
            f"Looking for {first_entity_type}.{first_entity_name}_* entities: "
            f"found {len(matching_entities)} matches"
        )

        if not matching_entities:
            _LOGGER.debug(
                f"No entities found matching pattern: "
                f"{entity_base_type}.{first_entity_name}_*"
            )
            return False

        # Check each device has all required entities
        for entity_state in matching_entities:
            device_id = self._extract_device_id(entity_state.entity_id)
            if device_id:
                validation_result = await self._validate_device_entities(device_id)
                if validation_result:
                    _LOGGER.info(
                        f"Device {device_id} has all {self.feature_id} entities ready"
                    )
                    return True
                _LOGGER.debug(
                    f"Device {device_id} missing some {self.feature_id} entities"
                )
            else:
                _LOGGER.debug(
                    f"Could not extract device_id from {entity_state.entity_id}"
                )

        return False

    # ==================== STATE CHANGE HANDLING ====================

    def _handle_state_change(
        self, entity_id: str, old_state: State | None, new_state: State | None
    ) -> None:
        """Handle state changes using generic automation patterns.

        This method provides the common state change handling logic that
        all automations can use, with debouncing and validation.

        Args:
            entity_id: Entity that changed state
            old_state: Previous state (if any)
            new_state: New state
        """
        _LOGGER.info(
            f"🔥 BASE _handle_state_change: {entity_id} -> "
            f"{new_state.state if new_state else 'None'}"
        )
        _LOGGER.info(
            f"🔥 BASE Automation {self.__class__.__name__} handling state change"
        )

        # Schedule async processing in a thread-safe manner
        def _create_async_task() -> None:
            self.hass.async_create_task(
                self._async_handle_state_change(entity_id, old_state, new_state)
            )

        self.hass.loop.call_soon_threadsafe(_create_async_task)

    async def _async_handle_state_change(
        self, entity_id: str, old_state: State | None, new_state: State | None
    ) -> None:
        """Handle state changes with automation-specific processing.

        This method provides the async processing logic that derived classes
        can extend or override for feature-specific needs.

        Args:
            entity_id: Entity that changed state
            old_state: Previous state (if any)
            new_state: New state
        """
        if not new_state:
            _LOGGER.debug(f"No new state for {entity_id}, skipping")
            return
        _LOGGER.debug(f"New state for {entity_id}")

        # Extract device_id from entity name
        device_id = self._extract_device_id(entity_id)
        if not device_id:
            _LOGGER.warning(f"Could not extract device_id from entity: {entity_id}")
            return

        # Check validation cooldown for this device
        current_time = time.time()
        last_validation = self._last_validation_time.get(device_id, 0)

        # Only validate entities if cooldown period has passed or first time
        should_validate = (current_time - last_validation) > self._validation_cooldown

        # Track if we've validated before and passed
        has_validated_successfully = last_validation > 0

        if should_validate:
            # Validate all entities exist for this device
            if not await self._validate_device_entities(device_id):
                _LOGGER.debug(
                    f"Device {device_id}: Entities not ready for {self.feature_id}"
                )
                # Update validation time to prevent immediate re-checks
                self._last_validation_time[device_id] = current_time
                return
            # Validation passed, update timestamp
            self._last_validation_time[device_id] = current_time
            has_validated_successfully = True
        else:
            _LOGGER.debug(
                f"Device {device_id}: Skipping validation (cooldown active) for"
                f" {self.feature_id}"
            )

        # Only proceed if we've successfully validated before or just
        #  validated successfully
        if not has_validated_successfully:
            _LOGGER.debug(
                f"Device {device_id}: No successful validation for {self.feature_id}, "
                "skipping processing"
            )
            return

        # Apply debouncing to prevent rapid changes (skip if debouncing is disabled)
        if self.debounce_seconds > 0:
            if device_id in self._change_timers:
                _LOGGER.debug(f"Device {device_id}: Debouncing - ignoring rapid change")
                return

            # Set debouncing timer
            self._change_timers[device_id] = self.hass.loop.call_later(
                self.debounce_seconds,
                lambda: self._change_timers.pop(device_id, None),
            )

        # Get all entity states for this device
        try:
            entity_states = await self._get_device_entity_states(device_id)
            _LOGGER.debug(f"Device {device_id}: Got entity states: {entity_states}")
        except ValueError as e:
            _LOGGER.warning(f"Device {device_id}: Invalid entity states - {e}")
            return

        # Call feature-specific processing logic
        await self._process_automation_logic(device_id, entity_states)

    async def _cancel_all_timers(self) -> None:
        """Cancel all pending debouncing timers."""
        for timer in self._change_timers.values():
            timer.cancel()
        self._change_timers.clear()
        _LOGGER.debug(f"Cancelled all debouncing timers for {self.feature_id}")

    # ==================== ENTITY MANAGEMENT ====================

    async def _verify_entities_and_register_listeners(self) -> None:
        """Verify entities and register specific listeners in background."""
        _LOGGER.debug(
            f"Starting {self.feature_id} entity verification and listener registration"
        )
        try:
            # Wait for entities to be ready
            entities_ready = await self._wait_for_entities()
            if entities_ready:
                _LOGGER.info(
                    f"{self.feature_id} automation: Entities verified and ready"
                )
                await self._register_specific_entity_listeners()
            else:
                _LOGGER.debug(
                    f"{self.feature_id} automation: Entities not yet available - "
                    "will activate when ready"
                )
        except Exception as e:
            _LOGGER.debug(
                f"{self.feature_id} automation: Entity verification failed: {e}"
            )

    async def _register_specific_entity_listeners(self) -> None:
        """Register listeners for specific entity IDs instead of patterns."""
        _LOGGER.info(f"🎯 Registering listeners for {self.feature_id}")
        _LOGGER.info(f"🎯 Entity patterns: {self.entity_patterns}")

        new_listeners_registered = False

        # Find all entities that match our patterns
        for pattern in self.entity_patterns:
            if pattern.endswith("*"):
                prefix = pattern[:-1]  # Remove the *
                entity_type = prefix.split(".")[0]
                entities = self.hass.states.async_all(entity_type)

                for entity in entities:
                    if entity.entity_id.startswith(prefix):
                        _LOGGER.info(
                            f"🔍 Found entity matching pattern: {entity.entity_id}"
                        )
                        if entity.entity_id not in self._specific_entity_ids:
                            _LOGGER.info(
                                f"🎯 Registering listener for {self.feature_id}: "
                                f"{entity.entity_id}"
                            )

                            listener = async_track_state_change(
                                self.hass, entity.entity_id, self._handle_state_change
                            )

                            if listener:
                                self._listeners.append(listener)
                                self._specific_entity_ids.add(entity.entity_id)
                                new_listeners_registered = True
                                _LOGGER.info(
                                    f"✅ Successfully registered listener for "
                                    f"{entity.entity_id}"
                                )
                            else:
                                _LOGGER.error(
                                    f"❌ Failed to create listener for: "
                                    f"{entity.entity_id}"
                                )
                        else:
                            _LOGGER.info(
                                f"⚠️ Listener already registered for {entity.entity_id}"
                            )
                    # else:
                    #     _LOGGER.debug(
                    #         f"❌ Entity {entity.entity_id}: no match prefix {prefix}"
                    #     )

        # Log summary
        if new_listeners_registered:
            _LOGGER.info(
                f"🎯 Total {len(self._specific_entity_ids)} entity listeners for "
                f"{self.feature_id}: {sorted(self._specific_entity_ids)}"
            )
        else:
            _LOGGER.warning(f"No new listeners registered for {self.feature_id}")

    def _entity_matches_patterns(self, entity_id: str) -> bool:
        """Check if an entity ID matches any of the automation patterns.

        Args:
            entity_id: Entity identifier to check

        Returns:
            True if entity matches any pattern
        """
        for pattern in self.entity_patterns:
            if pattern.endswith("*"):
                prefix = pattern[:-1]
                if entity_id.startswith(prefix):
                    return True
            elif entity_id == pattern:
                return True

        return False

    async def _validate_device_entities(self, device_id: str) -> bool:
        """Validate all required entities exist for a device.

        This method provides a generic validation framework that derived
        classes can extend with feature-specific validation logic.

        Args:
            device_id: Device identifier

        Returns:
            True if all entities exist, False otherwise
        """
        # Get required entities from the feature's const module
        required_entities = _get_required_entities_from_feature(self.feature_id)
        if not required_entities:
            _LOGGER.warning(
                f"No required entities found for feature: {self.feature_id}"
            )
            return False

        missing_entities = []

        for entity_type, entity_names in required_entities.items():
            entity_base_type = _singularize_entity_type(entity_type)

            for entity_name in entity_names:
                # Generate expected entity ID using the pattern
                #  from the humidity automation
                expected_entity_id = f"{entity_base_type}.{entity_name}_{device_id}"

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

    def _extract_device_id(self, entity_id: str) -> str | None:
        """Extract device_id from entity name using EntityHelpers.

        Args:
            entity_id: Entity identifier

        Returns:
            Device identifier in underscore format (e.g., "32_153289")
            or None if extraction fails
        """
        from custom_components.ramses_extras.framework.helpers.entity.core import (
            EntityHelpers,
        )

        parsed = EntityHelpers.parse_entity_id(entity_id)
        if parsed:
            _, _, device_id = parsed
            # Ensure we return a valid device_id or None
            if device_id and str(device_id).strip():
                return str(device_id)

        _LOGGER.warning(f"Could not extract device_id from entity: {entity_id}")
        return None

    # ==================== DATA ACCESS ====================

    async def _get_device_entity_states(self, device_id: str) -> dict[str, Any]:
        """Get all entity states for a device with validation.

        Args:
            device_id: Device identifier (e.g., "32_153289")

        Returns:
            Dictionary with entity state values (numeric or boolean)

        Raises:
            ValueError: If any entity is unavailable or has invalid values
        """
        from custom_components.ramses_extras.framework.helpers.entity.core import (
            get_feature_entity_mappings,
        )

        states = {}

        # Get dynamic state mappings from feature configuration
        state_mappings = await get_feature_entity_mappings(self.feature_id, device_id)

        for state_name, entity_id in state_mappings.items():
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

    def _extract_entity_type_from_id(self, entity_id: str) -> str:
        """Extract entity type from entity ID.

        Args:
            entity_id: Entity identifier (e.g., "switch.dehumidify_32_153289")

        Returns:
            Entity type ("sensor", "switch", "number", "binary_sensor")
        """
        if "." in entity_id:
            return entity_id.split(".")[0]
        return "unknown"

    def _convert_entity_state(self, entity_type: str, state_value: str) -> float | bool:
        """Convert entity state value based on entity type.

        Args:
            entity_type: Type of entity
            state_value: Raw state value from Home Assistant

        Returns:
            Converted value (float for sensor/number,
            bool for switch/binary_sensor)
        """
        # Handle boolean entities (switch and binary sensor)
        if entity_type in ["switch", "binary_sensor"]:
            return state_value.lower() in ["on", "true", "1", "yes"]

        # Handle numeric entities (sensor and number)
        if entity_type in ["sensor", "number"]:
            try:
                return float(state_value)
            except (ValueError, TypeError) as err:
                raise ValueError(
                    f"Entity {entity_type} has invalid numeric value: {state_value}"
                ) from err

        # Unknown entity type - try numeric conversion as fallback
        else:
            try:
                return float(state_value)
            except (ValueError, TypeError):
                # If numeric conversion fails, treat as boolean
                return state_value.lower() in ["on", "true", "1", "yes"]

    # ==================== BINARY SENSOR HELPERS ====================

    async def set_binary_sensor_state(self, entity_id: str, is_on: bool) -> bool:
        """Set binary sensor state using framework-compliant pattern.

        This helper method provides the correct way to update binary sensor state
        by calling the entity's set_state() method. Binary sensors don't have
        turn_on/turn_off services like switches, so they must be updated via
        their entity object.

        Args:
            entity_id: Binary sensor entity ID
             (e.g., "binary_sensor.hello_world_status_37_168270")
            is_on: Desired state (True for ON, False for OFF)

        Returns:
            True if state was updated successfully, False otherwise

        Example:
            await self.set_binary_sensor_state(
                "binary_sensor.hello_world_status_37_168270",
                True
            )
        """
        try:
            # Get the binary sensor entity from hass.data where it was stored
            # during platform setup (store_entities_for_automation=True)
            stored_entities = self.hass.data.get("ramses_extras", {}).get(
                "entities", {}
            )
            entity = stored_entities.get(entity_id)

            if entity and hasattr(entity, "set_state"):
                # Call the entity's set_state method to update the binary sensor
                entity.set_state(is_on)
                _LOGGER.info(
                    f"Updated binary sensor {entity_id} to {is_on} via set_state()"
                )
                return True
            _LOGGER.warning(
                f"Binary sensor entity {entity_id} not found or doesn't have "
                f"set_state method"
            )
            return False

        except Exception as e:
            _LOGGER.error(f"Failed to update binary sensor {entity_id}: {e}")
            return False

    async def toggle_binary_sensor_state(self, entity_id: str) -> bool:
        """Toggle binary sensor state using framework-compliant pattern.

        This helper method toggles the binary sensor state by first reading
        the current state and then setting the opposite state.

        Args:
            entity_id: Binary sensor entity ID

        Returns:
            True if state was toggled successfully, False otherwise
        """
        try:
            # Get current state
            state = self.hass.states.get(entity_id)
            if not state:
                _LOGGER.warning(f"Binary sensor {entity_id} not found")
                return False

            # Determine current state as boolean
            current_is_on = state.state.lower() in ["on", "true", "1"]

            # Toggle and set new state
            return await self.set_binary_sensor_state(entity_id, not current_is_on)

        except Exception as e:
            _LOGGER.error(f"Failed to toggle binary sensor {entity_id}: {e}")
            return False

    # ==================== ABSTRACT METHODS ====================

    @abstractmethod
    async def _process_automation_logic(
        self, device_id: str, entity_states: dict[str, Any]
    ) -> None:
        """Process automation logic specific to this feature.

        This method must be implemented by derived classes to provide
        feature-specific automation logic.

        Args:
            device_id: Device identifier
            entity_states: Validated entity state values (float or bool)
        """
        _LOGGER.debug("Abstract method _process_automation_logic called")
        # pass


__all__ = [
    "ExtrasBaseAutomation",
]
