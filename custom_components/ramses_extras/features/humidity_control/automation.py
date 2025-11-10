"""Humidity Control Automation.

This module contains the automation logic for humidity control functionality,
migrated from the original humidity_automation.py but organized within the
feature-centric architecture.
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional, cast

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry
from homeassistant.helpers.event import async_track_state_change_event

from ...helpers.automation import ExtrasBaseAutomation
from ...helpers.entity import EntityHelpers
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
            debounce_seconds=30,
        )

        self.config_entry = config_entry
        self.config = HumidityConfig(hass, config_entry)
        self.services = HumidityServices(hass, config_entry)

        # Humidity-specific state tracking
        self._dehumidify_active = False
        self._automation_active = False
        self._last_decision_state: dict[str, Any] | None = None
        self._decision_history: list[dict[str, Any]] = []

        # Performance tracking
        self._decision_count = 0
        self._active_cycles = 0

        _LOGGER.info("HumidityControl automation initialized")

    def _generate_entity_patterns(self) -> list[str]:
        """Generate entity patterns for humidity control.

        Returns:
            List of entity patterns to listen for
        """
        patterns = [
            # Primary humidity entities
            "sensor.indoor_absolute_humidity_*",
            "sensor.outdoor_absolute_humidity_*",
            "number.relative_humidity_minimum_*",
            "number.relative_humidity_maximum_*",
            "number.absolute_humidity_offset_*",
            "switch.dehumidify_*",
            "binary_sensor.dehumidifying_active_*",
            # Cross-device reference entities
            "sensor.*_indoor_humidity",  # CC sensor references
        ]

        _LOGGER.debug(f"Generated {len(patterns)} entity patterns")
        return patterns

    async def start(self) -> None:
        """Start the humidity control automation.

        Initializes automation and begins monitoring.
        """
        _LOGGER.info("Starting humidity control automation")

        # Load configuration
        await self.config.async_load()

        # Start base automation
        await super().start()

        # Initialize binary sensor if configured
        if self.config_entry.options.get("enable_automation_status"):
            await self._initialize_automation_status_sensor()

        self._automation_active = True
        _LOGGER.info("Humidity control automation started")

    async def stop(self) -> None:
        """Stop the humidity control automation.

        Shuts down automation and cleans up resources.
        """
        _LOGGER.info("Stopping humidity control automation")

        self._automation_active = False
        await super().stop()

        _LOGGER.info("Humidity control automation stopped")

    async def _initialize_automation_status_sensor(self) -> None:
        """Initialize automation status binary sensor.

        Creates a binary sensor to show automation status.
        """
        # This would create a binary sensor entity showing automation status
        # Implementation would integrate with the entities module

    async def _process_automation_logic(
        self, device_id: str, entity_states: dict[str, float]
    ) -> None:
        """Process humidity control automation logic for a device.

        Args:
            device_id: Device identifier
            entity_states: Validated entity state values
        """
        if not self._automation_active:
            return

        # Automation event logging
        _LOGGER.info(f"Processing humidity automation logic for device {device_id}")

        try:
            # Extract humidity values
            indoor_abs = entity_states.get("indoor_abs", 0.0)
            outdoor_abs = entity_states.get("outdoor_abs", 0.0)
            min_humidity = entity_states.get("min_humidity", 40.0)
            max_humidity = entity_states.get("max_humidity", 60.0)
            offset = entity_states.get("offset", 0.0)

            # Calculate decision
            decision = await self._evaluate_humidity_conditions(
                indoor_abs, outdoor_abs, min_humidity, max_humidity, offset
            )

            # Apply decision
            if decision["action"] == "dehumidify":
                await self._activate_dehumidification(device_id, decision)
            elif decision["action"] == "stop":
                await self._deactivate_dehumidification(device_id, decision)

            # Update status
            await self._update_automation_status(device_id, decision)

        except Exception as e:
            _LOGGER.error(f"Automation logic error: {e}")

    async def _evaluate_humidity_conditions(
        self,
        indoor_abs: float,
        outdoor_abs: float,
        min_humidity: float,
        max_humidity: float,
        offset: float,
    ) -> dict[str, Any]:
        """Evaluate humidity conditions and make dehumidification decision.

        This implements the decision logic from the original humidity automation.

        Args:
            indoor_abs: Indoor absolute humidity
            outdoor_abs: Outdoor absolute humidity
            min_humidity: Minimum relative humidity threshold
            max_humidity: Maximum relative humidity threshold
            offset: Humidity offset adjustment

        Returns:
            Decision dictionary with action and reasoning
        """
        # Calculate humidity differential
        humidity_diff = indoor_abs - outdoor_abs

        # Apply offset
        adjusted_diff = humidity_diff + offset

        # Decision logic from original automation
        decision = {
            "action": "stop",  # Default action
            "reasoning": [],
            "values": {
                "indoor_abs": indoor_abs,
                "outdoor_abs": outdoor_abs,
                "humidity_diff": humidity_diff,
                "adjusted_diff": adjusted_diff,
                "min_humidity": min_humidity,
                "max_humidity": max_humidity,
                "offset": offset,
            },
            "confidence": 0.0,
        }

        # Rule-based decision making
        if adjusted_diff > 2.0:
            # High humidity differential - activate dehumidification
            decision["action"] = "dehumidify"
            decision["reasoning"].append(  # type: ignore[attr-defined]
                f"High humidity differential: {adjusted_diff:.1f} > 2.0"
            )
            decision["confidence"] = 0.9

        elif adjusted_diff > 1.0:
            # Moderate differential - consider activating
            decision["action"] = "dehumidify"
            decision["reasoning"].append(  # type: ignore[attr-defined]
                f"Moderate humidity differential: {adjusted_diff:.1f} > 1.0"
            )
            decision["confidence"] = 0.7

        elif adjusted_diff < -1.0:
            # Negative differential - stop dehumidification
            decision["action"] = "stop"
            decision["reasoning"].append(  # type: ignore[attr-defined]
                f"Low humidity differential: {adjusted_diff:.1f} < -1.0"
            )
            decision["confidence"] = 0.8

        # Additional checks for extreme values
        if indoor_abs > 15.0:  # High absolute humidity
            decision["confidence"] = min(1.0, decision["confidence"] + 0.1)  # type: ignore[operator]
            decision["reasoning"].append(  # type: ignore[attr-defined]
                f"High indoor absolute humidity: {indoor_abs:.1f} g/m³"
            )

        # Record decision
        self._decision_count += 1
        self._decision_history.append(decision)

        # Keep only recent decisions
        if len(self._decision_history) > 100:
            self._decision_history.pop(0)

            _LOGGER.debug(
                f"Decision: {decision['action']} "
                f"(confidence: {decision['confidence']:.2f})",
            )

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
            _LOGGER.error(_LOGGER, f"Failed to deactivate dehumidification: {e}")

    async def _update_automation_status(
        self, device_id: str, decision: dict[str, Any]
    ) -> None:
        """Update automation status entity.

        Args:
            device_id: Device identifier
            decision: Decision information
        """
        # Update binary sensor if available
        if self.binary_sensor:
            try:
                # state = "ON" if decision["action"] == "dehumidify" else "OFF" # Unused
                self.binary_sensor.async_write_ha_state()
            except Exception as e:
                _LOGGER.error(f"Failed to update status sensor: {e}")

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
