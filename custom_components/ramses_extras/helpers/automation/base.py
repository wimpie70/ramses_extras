"""Base automation class for Ramses Extras.

This module provides a reusable base class that encapsulates common
automation patterns, reducing code duplication across different features.
"""

import asyncio
import logging
import re
import time
from abc import abstractmethod
from typing import Any

from homeassistant.core import HomeAssistant, State, callback
from homeassistant.helpers.event import (
    async_track_state_change,
    async_track_state_change_event,
)

from ..entity import EntityHelpers

_LOGGER = logging.getLogger(__name__)


class ExtrasBaseAutomation:
    """Base automation class for Ramses Extras features.

    This class provides common automation patterns including:
    - Entity state change handling with debouncing
    - Device ID extraction and validation
    - Entity existence and state validation
    - Lifecycle management (start/stop)
    - Generic state change processing framework

    Subclasses must implement the abstract methods to provide
    feature-specific logic.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        feature_id: str,
        binary_sensor: Any = None,
        debounce_seconds: int = 30,
    ) -> None:
        """Initialize base automation.

        Args:
            hass: Home Assistant instance
            feature_id: Feature identifier for this automation
            binary_sensor: Optional binary sensor to control
            debounce_seconds: Default debounce interval for state changes
        """
        self.hass = hass
        self.feature_id = feature_id
        self.binary_sensor = binary_sensor
        self.debounce_seconds = debounce_seconds

        # State tracking
        self._active = False
        self._listeners: list[Any] = []
        self._change_timers: dict[str, Any] = {}
        self._specific_entity_ids: set[str] = set()

        # Entity pattern caching
        self._entity_patterns: list[str] | None = None
        self._state_mappings: dict[str, str] | None = None

        _LOGGER.info(f"Base automation initialized for feature: {feature_id}")

    @property
    def entity_patterns(self) -> list[str]:
        """Get entity patterns for this automation feature."""
        if self._entity_patterns is None:
            self._entity_patterns = self._generate_entity_patterns()
        return self._entity_patterns

    @abstractmethod
    def _generate_entity_patterns(self) -> list[str]:
        """Generate entity patterns for this automation feature.

        Returns:
            List of entity patterns to listen for
        """

    @abstractmethod
    async def _process_automation_logic(
        self, device_id: str, entity_states: dict[str, float]
    ) -> None:
        """Process automation logic for a device.

        Args:
            device_id: Device identifier
            entity_states: Current entity states for the device
        """

    async def start(self) -> None:
        """Start the automation.

        Begins listening for entity state changes and activates the automation.
        """
        if self._active:
            _LOGGER.warning(f"Automation {self.feature_id} already started")
            return

        _LOGGER.info(f"Starting automation: {self.feature_id}")
        _LOGGER.debug(f"Entity patterns: {self.entity_patterns}")

        # Register global state listeners
        await self._verify_entities_and_register_listeners()

        self._active = True
        _LOGGER.info(f"Automation {self.feature_id} started successfully")

    async def stop(self) -> None:
        """Stop the automation and clean up resources."""
        if not self._active:
            return

        _LOGGER.info(f"Stopping automation: {self.feature_id}")

        # Remove all state listeners
        for listener in self._listeners:
            listener()
        self._listeners.clear()

        # Cancel all debouncing timers
        await self._cancel_all_timers()

        self._active = False
        self._specific_entity_ids.clear()

        _LOGGER.info(f"Automation {self.feature_id} stopped")

    async def _verify_entities_and_register_listeners(self) -> None:
        """Verify entities exist and register specific listeners."""
        try:
            await asyncio.sleep(5)  # Allow entities to be created
            await self._register_specific_listeners()
        except Exception as e:
            _LOGGER.warning(f"Failed to register listeners: {e}")

    async def _register_specific_listeners(self) -> None:
        """Register listeners for specific entity IDs."""
        _LOGGER.debug("Registering specific entity listeners")

        # Get all current entities and find matches
        all_states = self.hass.states.async_all()
        matched_entities = set()

        for pattern in self.entity_patterns:
            for state in all_states:
                if self._entity_matches_pattern(state.entity_id, pattern):
                    matched_entities.add(state.entity_id)

        if matched_entities:
            self._specific_entity_ids = matched_entities
            _LOGGER.info(f"Found {len(matched_entities)} matching entities")

            # Register state change listeners for specific entities
            for entity_id in matched_entities:
                listener = async_track_state_change(
                    self.hass, entity_id, self._handle_state_change
                )
                self._listeners.append(listener)
        else:
            _LOGGER.warning("No entities found matching patterns")

    def _entity_matches_pattern(self, entity_id: str, pattern: str) -> bool:
        """Check if entity ID matches the given pattern.

        Args:
            entity_id: Entity ID to check
            pattern: Pattern to match against

        Returns:
            True if entity matches pattern
        """
        if pattern.endswith("*"):
            prefix = pattern[:-1]
            return entity_id.startswith(prefix)
        return entity_id == pattern

    async def _cancel_all_timers(self) -> None:
        """Cancel all debouncing timers."""
        for device_id, timer in self._change_timers.items():
            try:
                timer.cancel()
            except Exception as e:
                _LOGGER.debug(f"Failed to cancel timer for {device_id}: {e}")
        self._change_timers.clear()

    def _handle_state_change(
        self, entity_id: str, old_state: State | None, new_state: State | None
    ) -> None:
        """Handle entity state changes.

        This is the callback for Home Assistant state change events.
        It schedules async processing in a thread-safe manner.

        Args:
            entity_id: Entity that changed state
            old_state: Previous state
            new_state: New state
        """
        _LOGGER.debug(
            f"State change: {entity_id} -> {new_state.state if new_state else 'None'}"
        )

        # Update switch state if this is a switch change
        if entity_id.startswith("switch.") and new_state:
            self._update_switch_state(entity_id, new_state.state)

        # Schedule async processing
        def _create_async_task() -> None:
            self.hass.async_create_task(
                self._async_handle_state_change(entity_id, old_state, new_state)
            )

        self.hass.loop.call_soon_threadsafe(_create_async_task)

    def _update_switch_state(self, entity_id: str, new_state: str) -> None:
        """Update internal switch state tracking.

        Args:
            entity_id: Switch entity ID
            new_state: New state value
        """
        # This can be overridden by subclasses for specific switch logic

    async def _async_handle_state_change(
        self, entity_id: str, old_state: State | None, new_state: State | None
    ) -> None:
        """Handle state changes asynchronously.

        This method should be overridden by subclasses if they need
        custom state change processing logic.

        Args:
            entity_id: Entity that changed state
            old_state: Previous state
            new_state: New state
        """
        if not new_state:
            return

        # Extract device_id from entity name
        device_id = self._extract_device_id(entity_id)
        if not device_id:
            _LOGGER.warning(f"Could not extract device_id from: {entity_id}")
            return

        # Validate all entities exist for this device
        if not await self._validate_device_entities(device_id):
            _LOGGER.debug(f"Device {device_id}: Entities not ready")
            return

        # Check if we should process this change (override in subclass if needed)
        if not await self._should_process_state_change(entity_id, new_state, device_id):
            return

        # Apply debouncing
        if device_id in self._change_timers:
            _LOGGER.debug(f"Device {device_id}: Debouncing - ignoring rapid change")
            return

        # Set debouncing timer
        self._change_timers[device_id] = self.hass.loop.call_later(
            self.debounce_seconds,
            lambda: self._change_timers.pop(device_id, None),
        )

        # Get entity states and process
        try:
            entity_states = await self._get_device_entity_states(device_id)
            await self._process_automation_logic(device_id, entity_states)
        except ValueError as e:
            _LOGGER.warning(f"Device {device_id}: Invalid entity states - {e}")
        except Exception as e:
            _LOGGER.error(f"Device {device_id}: Error processing automation - {e}")

    async def _should_process_state_change(
        self, entity_id: str, new_state: State, device_id: str
    ) -> bool:
        """Check if this state change should be processed.

        This can be overridden by subclasses to implement custom logic
        (e.g., only process when switches are on).

        Args:
            entity_id: Entity that changed state
            new_state: New state
            device_id: Device identifier

        Returns:
            True if the state change should be processed
        """
        return True

    def _extract_device_id(self, entity_id: str) -> str | None:
        """Extract device_id from entity name.

        Args:
            entity_id: Entity identifier

        Returns:
            Device identifier in underscore format or None if extraction fails
        """
        parsed = EntityHelpers.parse_entity_id(entity_id)
        if parsed:
            _, _, device_id = parsed
            return device_id

        _LOGGER.warning(f"Could not extract device_id from entity: {entity_id}")
        return None

    async def _validate_device_entities(self, device_id: str) -> bool:
        """Validate that all required entities exist for a device.

        This method should be overridden by subclasses to provide
        feature-specific entity validation.

        Args:
            device_id: Device identifier

        Returns:
            True if all entities exist, False otherwise
        """
        # Basic implementation - subclasses should override
        return True

    async def _get_device_entity_states(self, device_id: str) -> dict[str, float]:
        """Get all entity states for a device with validation.

        This method should be overridden by subclasses to provide
        feature-specific entity state retrieval.

        Args:
            device_id: Device identifier

        Returns:
            Dictionary with entity state values

        Raises:
            ValueError: If any entity is unavailable or has invalid values
        """
        # Basic implementation - subclasses should override
        raise NotImplementedError("Subclasses must implement _get_device_entity_states")

    def get_automation_status(self) -> dict[str, Any]:
        """Get current automation status for debugging.

        Returns:
            Dictionary with automation status information
        """
        return {
            "feature_id": self.feature_id,
            "active": self._active,
            "listeners_count": len(self._listeners),
            "timers_count": len(self._change_timers),
            "entity_patterns": len(self.entity_patterns),
            "specific_entities": len(self._specific_entity_ids),
        }


# Legacy alias for backward compatibility
RamsesBaseAutomation = ExtrasBaseAutomation
