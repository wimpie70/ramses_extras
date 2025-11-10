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
from typing import Any, cast

from homeassistant.core import HomeAssistant, State
from homeassistant.helpers.event import async_track_state_change

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
            _LOGGER.warning(f"Automation {self.feature_id} already started")
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
        from custom_components.ramses_extras.const import AVAILABLE_FEATURES

        patterns = []

        # Add pattern for the feature's required entities
        feature = AVAILABLE_FEATURES.get(self.feature_id, {})
        required_entities = feature.get("required_entities", {})

        # Cast to proper type to satisfy mypy
        required_entities_dict = cast(dict[str, list[str]], required_entities)

        for entity_type, entity_names in required_entities_dict.items():
            for entity_name in entity_names:
                # Use wildcard pattern for dynamic device_id matching
                entity_base_type = entity_type.rstrip("s")  # "sensors" -> "sensor"
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
        from custom_components.ramses_extras.const import AVAILABLE_FEATURES

        # Get the first entity type to look for devices
        feature = AVAILABLE_FEATURES.get(self.feature_id, {})
        required_entities = feature.get("required_entities", {})

        # Cast to proper type to satisfy mypy
        required_entities_dict = cast(dict[str, list[str]], required_entities)

        if not required_entities_dict:
            return False

        # Use the first entity type as a starting point
        first_entity_type = list(required_entities_dict.keys())[0]
        first_entity_names = required_entities_dict[first_entity_type]
        if not first_entity_names:
            return False

        first_entity_name = first_entity_names[0]
        entity_base_type = first_entity_type.rstrip("s")

        # Look for entities of this type
        entities = self.hass.states.async_all(entity_base_type)
        matching_entities = [
            state
            for state in entities
            if state.entity_id.startswith(f"{entity_base_type}.{first_entity_name}_")
        ]

        if not matching_entities:
            return False

        # Check each device has all required entities
        for entity_state in matching_entities:
            device_id = self._extract_device_id(entity_state.entity_id)
            if device_id and await self._validate_device_entities(device_id):
                _LOGGER.debug(
                    f"Device {device_id} has all {self.feature_id} entities ready"
                )
                return True

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
        _LOGGER.debug(
            f"State change: {entity_id} -> {new_state.state if new_state else 'None'}"
        )
        _LOGGER.debug(f"Automation {self.__class__.__name__} handling state change")

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

        # Extract device_id from entity name
        device_id = self._extract_device_id(entity_id)
        if not device_id:
            _LOGGER.warning(f"Could not extract device_id from entity: {entity_id}")
            return

        # Validate all entities exist for this device
        if not await self._validate_device_entities(device_id):
            _LOGGER.debug(
                f"Device {device_id}: Entities not ready for {self.feature_id}"
            )
            return

        # Apply debouncing to prevent rapid changes
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
        new_listeners_registered = False

        # Find all entities that match our patterns
        for pattern in self.entity_patterns:
            if pattern.endswith("*"):
                prefix = pattern[:-1]  # Remove the *
                entity_type = prefix.split(".")[0]
                entities = self.hass.states.async_all(entity_type)

                for entity in entities:
                    if entity.entity_id.startswith(prefix):
                        if entity.entity_id not in self._specific_entity_ids:
                            _LOGGER.info(
                                f"📡 Registering listener for {self.feature_id}: "
                                f"{entity.entity_id}"
                            )

                            listener = async_track_state_change(
                                self.hass, entity.entity_id, self._handle_state_change
                            )

                            if listener:
                                self._listeners.append(listener)
                                self._specific_entity_ids.add(entity.entity_id)
                                new_listeners_registered = True
                            else:
                                _LOGGER.error(
                                    f"❌ Failed to create listener for: "
                                    f"{entity.entity_id}"
                                )

        # Log summary
        if new_listeners_registered:
            _LOGGER.info(
                f"🎯 Total {len(self._specific_entity_ids)} entity listeners for "
                f"{self.feature_id}: {sorted(self._specific_entity_ids)}"
            )

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
        from custom_components.ramses_extras.const import AVAILABLE_FEATURES
        from custom_components.ramses_extras.framework.helpers.entity.core import (
            EntityHelpers,
        )

        feature = AVAILABLE_FEATURES.get(self.feature_id, {})
        if not feature:
            _LOGGER.warning(f"No configuration found for feature: {self.feature_id}")
            return False

        required_entities = feature.get("required_entities", {})
        if not required_entities:
            _LOGGER.warning(
                f"No required entities defined for feature: {self.feature_id}"
            )
            return True  # No entities required

        # Cast to proper type to satisfy mypy
        required_entities_dict = cast(dict[str, list[str]], required_entities)
        missing_entities = []

        for entity_type, entity_names in required_entities_dict.items():
            entity_base_type = entity_type.rstrip("s")

            for entity_name in entity_names:
                # Generate expected entity ID
                expected_entity_id = EntityHelpers.generate_entity_name_from_template(
                    entity_base_type, entity_name, device_id
                )

                if expected_entity_id:
                    entity_exists = self.hass.states.get(expected_entity_id)
                    if not entity_exists:
                        missing_entities.append(expected_entity_id)
                else:
                    _LOGGER.warning(
                        f"Could not generate entity ID for "
                        f"{entity_base_type}.{entity_name}"
                    )
                    missing_entities.append(
                        f"{entity_base_type}.{entity_name}_{device_id}"
                    )

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

    async def _get_device_entity_states(self, device_id: str) -> dict[str, float]:
        """Get all entity states for a device with validation.

        Args:
            device_id: Device identifier (e.g., "32_153289")

        Returns:
            Dictionary with entity state values

        Raises:
            ValueError: If any entity is unavailable or has invalid values
        """
        from custom_components.ramses_extras.framework.helpers.entity.core import (
            get_feature_entity_mappings,
        )

        states = {}

        # Get dynamic state mappings from feature configuration
        state_mappings = get_feature_entity_mappings(self.feature_id, device_id)

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

    # ==================== ABSTRACT METHODS ====================

    @abstractmethod
    async def _process_automation_logic(
        self, device_id: str, entity_states: dict[str, float]
    ) -> None:
        """Process automation logic specific to this feature.

        This method must be implemented by derived classes to provide
        feature-specific automation logic.

        Args:
            device_id: Device identifier
            entity_states: Validated entity state values
        """
        _LOGGER.debug("Abstract method _process_automation_logic called")
        # pass


__all__ = [
    "ExtrasBaseAutomation",
]
