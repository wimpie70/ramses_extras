# Part of the Ramses Extra integration
# See https://github.com/wimpie70/ramses_extras for more information
#
"""Hello World Card automation - demonstrates automation-driven entity control.

This module provides the automation manager for the Hello World feature, showcasing
how to implement automation-driven entity control patterns in Ramses Extras.

:platform: Home Assistant
:feature: Hello World Automation
:pattern: Event-Driven Architecture
:components: Automation Manager, State Monitoring, Entity Coordination
"""

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
            feature_id="hello_world",
            binary_sensor=None,  # Will be set when entities are available
            debounce_seconds=0,  # No debouncing needed - event-driven approach
        )

        self.config_entry = config_entry
        self._automation_active = False

        _LOGGER.info("Hello World Card automation initialized")

    def _is_feature_enabled(self) -> bool:
        """Check if hello_world feature is enabled in config.

        This method checks the configuration entry to determine if the Hello World
        feature is enabled. It looks for the feature in the 'enabled_features'
        dictionary within the config entry data.

        Returns:
            bool: True if the feature is enabled, False otherwise.

        Note:
            If there are any errors accessing the configuration data, the method
            returns False as a safe default and logs a warning.
        """
        try:
            enabled_features = self.config_entry.data.get("enabled_features", {})
            result: bool = enabled_features.get("hello_world", False)
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
        ]

        _LOGGER.debug(
            f"Generated {len(patterns)} entity patterns for Hello World automation"
        )
        return patterns

    async def start(self) -> None:
        """Start the Hello World automation.

        Initializes automation and begins monitoring.
        """
        _LOGGER.info("Starting Hello World automation")

        # Check if hello_world feature is enabled
        if not self._is_feature_enabled():
            _LOGGER.info(
                "Hello World feature is not enabled, skipping automation start"
            )
            return

        _LOGGER.info("Hello World feature is enabled, proceeding with startup")

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
            binary_sensor_should_be_on = switch_state

            _LOGGER.debug(
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
        # Check if feature is still enabled first
        if not self._is_feature_enabled():
            _LOGGER.debug(
                f"Feature {self.feature_id} disabled, ignoring "
                f"state change for {entity_id}"
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

        This updates the binary sensor state using the framework's helper method.

        Args:
            device_id: Device identifier
            should_be_on: Whether binary sensor should be on
        """
        try:
            # Generate the binary sensor entity ID
            entity_id = f"binary_sensor.hello_world_status_{device_id}"

            # Use framework base class helper to set binary sensor state
            success = await self.set_binary_sensor_state(entity_id, should_be_on)

            if not success:
                _LOGGER.warning(f"Failed to update binary sensor {entity_id}")

        except Exception as e:
            _LOGGER.error(
                f"Failed to trigger binary sensor update for {device_id}: {e}"
            )
            import traceback

            _LOGGER.debug(f"Traceback: {traceback.format_exc()}")

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
