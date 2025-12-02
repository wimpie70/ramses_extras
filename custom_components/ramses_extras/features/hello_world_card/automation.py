# Part of the Ramses Extra integration
# See https://github.com/wimpie70/ramses_extras for more information
#
"""Hello World Card automation - demonstrates automation-driven entity control."""

import logging
from typing import Any, cast

from homeassistant.core import HomeAssistant, State

from custom_components.ramses_extras.framework.base_classes.base_automation import (
    ExtrasBaseAutomation,
)

_LOGGER = logging.getLogger(__name__)


class HelloWorldAutomationManager(ExtrasBaseAutomation):
    """Manages Hello World automation logic.

    This automation demonstrates how to listen to switch changes and trigger
    binary sensor updates, showcasing the automation-driven architecture pattern.
    """

    def __init__(self, hass: HomeAssistant, config_entry: Any) -> None:
        """Initialize Hello World automation manager.

        Args:
            hass: Home Assistant instance
            config_entry: Configuration entry
        """
        super().__init__(
            hass=hass,
            feature_id="hello_world_card",
            binary_sensor=None,  # Will be set when entities are available
            debounce_seconds=0,  # No debouncing needed - event-driven approach
        )

        self.config_entry = config_entry
        self._automation_active = False

        _LOGGER.info("Hello World Card automation initialized")

    def _is_feature_enabled(self) -> bool:
        """Check if hello_world_card feature is enabled in config."""
        try:
            enabled_features = self.config_entry.data.get("enabled_features", {})
            result: bool = enabled_features.get("hello_world_card", False)
            return result
        except Exception as e:
            _LOGGER.warning(f"Could not check feature status: {e}")
            return False

    def _generate_entity_patterns(self) -> list[str]:
        """Generate entity patterns for Hello World automation.

        Returns:
            List of entity patterns to listen for
        """
        patterns = [
            # Hello World switch entities
            "switch.hello_world_switch_*",
            # Optional: also listen to binary sensor for verification
            "binary_sensor.hello_world_status_*",
        ]

        _LOGGER.debug(
            f"Generated {len(patterns)} entity patterns for Hello World automation"
        )
        _LOGGER.debug(f"Entity patterns: {patterns}")
        return patterns

    async def _check_any_device_ready(self) -> bool:
        """Check if any device has Hello World entities ready.

        Returns:
            True if at least one device is ready
        """
        # Check if feature is still enabled first
        if not self._is_feature_enabled():
            _LOGGER.debug("Hello World feature disabled, stopping device checks")
            return False

        _LOGGER.info(f"🔍 _check_any_device_ready called for {self.feature_id}")

        # Look for Hello World switch entities
        switch_entities = self.hass.states.async_all("switch")

        for switch_state in switch_entities:
            if switch_state.entity_id.startswith("switch.hello_world_switch_"):
                device_id = self._extract_device_id(switch_state.entity_id)
                if device_id:
                    _LOGGER.info(
                        f"🔍 Found Hello World switch for device "
                        f"{device_id}: {switch_state.entity_id}"
                    )
                    return True

        _LOGGER.debug("No Hello World switch entities found")
        return False

    async def _validate_device_entities(self, device_id: str) -> bool:
        """Validate Hello World entities exist for a device.

        Args:
            device_id: Device identifier

        Returns:
            True if required entities exist, False otherwise
        """
        # Check for Hello World entities
        switch_entity_id = f"switch.hello_world_switch_{device_id}"
        binary_sensor_entity_id = f"binary_sensor.hello_world_status_{device_id}"

        switch_exists = bool(self.hass.states.get(switch_entity_id))
        binary_sensor_exists = bool(self.hass.states.get(binary_sensor_entity_id))

        _LOGGER.debug(
            f"Device {device_id}: switch={switch_exists}, "
            f"binary_sensor={binary_sensor_exists}"
        )

        return switch_exists and binary_sensor_exists

    async def _get_device_entity_states(self, device_id: str) -> dict[str, Any]:
        """Get Hello World entity states for a device.

        Args:
            device_id: Device identifier

        Returns:
            Dictionary with entity state values
        """
        states = {}

        # Get switch state
        switch_entity_id = f"switch.hello_world_switch_{device_id}"
        switch_state = self.hass.states.get(switch_entity_id)

        if switch_state:
            states["switch"] = switch_state.state == "on"
        else:
            raise ValueError(f"Switch entity {switch_entity_id} not found")

        # Get binary sensor state (for verification)
        binary_sensor_entity_id = f"binary_sensor.hello_world_status_{device_id}"
        binary_sensor_state = self.hass.states.get(binary_sensor_entity_id)

        if binary_sensor_state:
            states["binary_sensor"] = binary_sensor_state.state == "on"

        return states

    async def start(self) -> None:
        """Start the Hello World automation.

        Initializes automation and begins monitoring.
        """
        _LOGGER.info("Starting Hello World automation")

        # Check if hello_world_card feature is enabled
        if not self._is_feature_enabled():
            _LOGGER.info(
                "Hello World Card feature is not enabled, skipping automation start"
            )
            return

        _LOGGER.info("Hello World Card feature is enabled, proceeding with startup")

        # Start base automation
        await super().start()

        self._automation_active = True
        _LOGGER.info("Hello World automation started")

    async def stop(self) -> None:
        """Stop the Hello World automation.

        Shuts down automation and cleans up resources.
        """
        _LOGGER.info("Stopping Hello World automation")

        self._automation_active = False
        await super().stop()

        _LOGGER.info("Hello World automation stopped")

    async def _process_automation_logic(
        self, device_id: str, entity_states: dict[str, Any]
    ) -> None:
        """Process Hello World automation logic for a device.

        This demonstrates a simple automation that responds to switch changes
        and triggers binary sensor updates. In a real feature, this would
        contain the actual business logic.

        Args:
            device_id: Device identifier
            entity_states: Entity state values
        """
        if not self._automation_active or not self._is_feature_enabled():
            return

        try:
            switch_state = entity_states.get("switch", False)

            # Simple automation logic: binary sensor follows switch state
            # In a real feature, this could be more complex logic
            binary_sensor_should_be_on = switch_state

            _LOGGER.info(
                f"Hello World automation processing for device {device_id}: "
                f"switch={switch_state} → binary_sensor={binary_sensor_should_be_on}"
            )

            # Trigger binary sensor update via automation
            await self._trigger_binary_sensor_update(
                device_id, binary_sensor_should_be_on
            )

        except Exception as e:
            _LOGGER.error(f"Automation logic error for device {device_id}: {e}")

    async def _async_handle_state_change(
        self, entity_id: str, old_state: State | None, new_state: State | None
    ) -> None:
        """Handle state changes with Hello World automation-specific processing.

        Args:
            entity_id: Entity that changed state
            old_state: Previous state (if any)
            new_state: New state
        """
        _LOGGER.info(
            f"HelloWorldAutomationManager _async_handle_state_change called for "
            f"entity_id={entity_id}"
        )

        # Check if feature is still enabled first
        if not self._is_feature_enabled():
            _LOGGER.debug(
                f"Feature {self.feature_id} "
                f"disabled, ignoring state change for {entity_id}"
            )
            return

        # Only process Hello World switch changes
        if not entity_id.startswith("switch.hello_world_switch_"):
            _LOGGER.debug(f"Ignoring non-Hello World switch: {entity_id}")
            return

        # Call parent implementation
        await super()._async_handle_state_change(entity_id, old_state, new_state)

    async def _trigger_binary_sensor_update(
        self, device_id: str, should_be_on: bool
    ) -> None:
        """Trigger binary sensor update via automation.

        Args:
            device_id: Device identifier
            should_be_on: Whether binary sensor should be on
        """
        try:
            # Get binary sensor entity from stored references
            entity_id = f"binary_sensor.hello_world_status_{device_id}"
            binary_sensor_entity = (
                self.hass.data.get("ramses_extras", {})
                .get("entities", {})
                .get(entity_id)
            )

            if binary_sensor_entity:
                # Use the automation-triggered state update method
                binary_sensor_entity.set_state(should_be_on)
                _LOGGER.info(
                    f"Automation triggered binary sensor {entity_id}: "
                    f"{'on' if should_be_on else 'off'}"
                )
            else:
                _LOGGER.warning(
                    f"Binary sensor entity {entity_id} not found in stored entities"
                )
        except Exception as e:
            _LOGGER.error(
                f"Failed to trigger binary sensor update for {device_id}: {e}"
            )

    # Public API methods for external control
    async def async_trigger_binary_sensor(self, device_id: str, state: bool) -> bool:
        """Manually trigger binary sensor update via automation.

        Args:
            device_id: Device identifier
            state: Desired binary sensor state

        Returns:
            True if successful
        """
        try:
            if not self._automation_active:
                _LOGGER.warning("Automation not active, cannot trigger binary sensor")
                return False

            await self._trigger_binary_sensor_update(device_id, state)
            return True
        except Exception as e:
            _LOGGER.error(f"Failed to manually trigger binary sensor: {e}")
            return False

    def is_automation_active(self) -> bool:
        """Check if automation is currently active.

        Returns:
            True if automation is active
        """
        return self._automation_active


# Feature registration
def create_hello_world_automation(
    hass: HomeAssistant, config_entry: Any
) -> HelloWorldAutomationManager:
    """Create Hello World automation instance.

    Args:
        hass: Home Assistant instance
        config_entry: Configuration entry

    Returns:
        HelloWorldAutomationManager instance
    """
    return HelloWorldAutomationManager(hass, config_entry)


__all__ = [
    "HelloWorldAutomationManager",
    "create_hello_world_automation",
]
