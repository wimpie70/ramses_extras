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
from datetime import timedelta

# Avoid circular imports by importing when needed in methods
from typing import Any

from homeassistant.core import CoreState, HomeAssistant, State
from homeassistant.helpers.event import async_track_state_change

from ...const import DOMAIN
from ..helpers.automation.core import (
    _singularize_entity_type,
)
from ..helpers.entity.core import (
    _get_required_entities_from_feature,
    get_required_entities_from_feature_sync,
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
        self._periodic_check_handle: Any = None  # Handle for periodic entity checks

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
        """Start the automation using HA events for reliable startup.

        Uses Home Assistant's startup events instead of complex validation
        cycles to prevent extensive reloading.
        """
        if self._active:
            _LOGGER.warning(
                f"Automation {self.feature_id} already started, "
                f"skipping duplicate start"
            )
            return

        _LOGGER.info(
            f"🚀 Starting {self.feature_id} automation (HA event-based startup)"
        )
        _LOGGER.info(f"📋 Entity patterns: {self.entity_patterns}")

        # Mark as active immediately
        self._active = True

        self.hass.data.setdefault(DOMAIN, {}).setdefault("feature_ready", {})[
            self.feature_id
        ] = False

        if getattr(self.hass, "state", None) == CoreState.running:
            _LOGGER.info(
                f"🏁 Home Assistant already running, initializing {self.feature_id} "
                "automation now"
            )
            await self._on_homeassistant_started(None)
            return

        # Listen for HA startup event instead of complex validation
        self.hass.bus.async_listen_once(
            "homeassistant_started", self._on_homeassistant_started
        )

        _LOGGER.info(f"✅ {self.feature_id} automation registered for HA startup")
        _LOGGER.info("🎯 Will initialize when Home Assistant is ready")

    async def _on_homeassistant_started(self, event: Any) -> None:
        """Handle Home Assistant startup event."""
        _LOGGER.info(
            f"🏠 Home Assistant started, initializing {self.feature_id} automation"
        )

        try:
            # Register entity listeners after HA is ready
            await self._register_entity_listeners()

            self.hass.data.setdefault(DOMAIN, {}).setdefault("feature_ready", {})[
                self.feature_id
            ] = True
            self.hass.bus.async_fire(
                "ramses_extras_feature_ready", {"feature_id": self.feature_id}
            )
            _LOGGER.info(f"✅ {self.feature_id} automation initialized successfully")
        except Exception as e:
            self.hass.data.setdefault(DOMAIN, {}).setdefault("feature_ready", {})[
                self.feature_id
            ] = False
            _LOGGER.error(f"❌ Failed to initialize {self.feature_id} automation: {e}")

    async def stop(self) -> None:
        """Stop the automation and clean up all resources."""
        if not self._active:
            return

        _LOGGER.info(f"Stopping {self.feature_id} automation")

        # Cancel periodic entity check if running
        if self._periodic_check_handle:
            self._periodic_check_handle()
            self._periodic_check_handle = None

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
        required_entities = get_required_entities_from_feature_sync(self.feature_id)

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

    async def _register_entity_listeners(self) -> None:
        """Register entity listeners after Home Assistant startup.

        Simple approach: register listeners for entity patterns and let HA
        handle entity availability. No complex validation cycles.
        """
        _LOGGER.info(f"🎯 Registering listeners for {self.feature_id}")
        _LOGGER.info(f"🎯 Entity patterns: {self.entity_patterns}")

        listeners_registered = 0

        # Register listeners for each entity pattern
        for pattern in self.entity_patterns:
            if pattern.endswith("*"):
                prefix = pattern[:-1]  # Remove the *
                entity_type = prefix.split(".")[0]
                entities = self.hass.states.async_all(entity_type)

                for entity in entities:
                    if entity.entity_id.startswith(prefix):
                        _LOGGER.debug(f"🔍 Found entity: {entity.entity_id}")
                        if entity.entity_id not in self._specific_entity_ids:
                            listener = async_track_state_change(
                                self.hass, entity.entity_id, self._handle_state_change
                            )

                            if listener:
                                self._listeners.append(listener)
                                self._specific_entity_ids.add(entity.entity_id)
                                listeners_registered += 1
                                _LOGGER.debug(
                                    f"✅ Registered listener: {entity.entity_id}"
                                )

        _LOGGER.info(
            f"✅ Registered {listeners_registered} entity listeners for "
            f"{self.feature_id}"
        )

        # If no entities found, set up a periodic check for entities
        if listeners_registered == 0:
            _LOGGER.info(
                f"No entities found yet for {self.feature_id}, "
                f"setting up periodic check"
            )
            self._setup_periodic_entity_check()

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

    def _setup_periodic_entity_check(self) -> None:
        """Set up periodic check for entities when none are found initially."""
        _LOGGER.info(f"Setting up periodic entity check for {self.feature_id}")

        # Use HA's async_track_time_interval for periodic checks
        self._periodic_check_handle = self.hass.helpers.event.async_track_time_interval(
            self._check_for_entities_periodically,
            timedelta(seconds=30),  # Check every 30 seconds
        )

    async def _check_for_entities_periodically(self, now: Any) -> None:
        """Periodic check for entities."""
        _LOGGER.debug(f"Periodic check for {self.feature_id} entities")

        # Try to register listeners again
        listeners_before = len(self._specific_entity_ids)
        await self._register_entity_listeners()
        listeners_after = len(self._specific_entity_ids)

        # Stop periodic checks once we have listeners
        if listeners_after > listeners_before and self._periodic_check_handle:
            _LOGGER.info(
                f"Found entities for {self.feature_id}, stopping periodic check"
            )
            self._periodic_check_handle()
            self._periodic_check_handle = None

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
        required_entities = await _get_required_entities_from_feature(self.feature_id)
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
