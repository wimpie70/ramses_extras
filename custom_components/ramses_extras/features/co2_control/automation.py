"""CO2 Control Automation.

This module contains the automation logic for CO2-based ventilation control.
CO2 control has priority over humidity control in the ventilation system.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any, cast

from homeassistant.core import Event, HomeAssistant, State
from homeassistant.helpers.event import async_track_state_change_event

from custom_components.ramses_extras.const import DOMAIN
from custom_components.ramses_extras.framework.base_classes.base_automation import (
    ExtrasBaseAutomation,
)
from custom_components.ramses_extras.framework.helpers.ramses_commands import (
    RamsesCommands,
)

from .config import CO2Config
from .const import FEATURE_DEFINITION
from .zone_manager import CO2ZoneManager

_LOGGER = logging.getLogger(__name__)


class CO2AutomationManager(ExtrasBaseAutomation):
    """Manages CO2 control automation logic.

    This class implements CO2-based ventilation control with priority over
    humidity control. It monitors multiple CO2 sensors across zones and
    triggers ventilation when thresholds are exceeded.
    """

    def __init__(self, hass: HomeAssistant, config_entry: Any) -> None:
        """Initialize CO2 automation manager.

        Args:
            hass: Home Assistant instance
            config_entry: Configuration entry
        """
        super().__init__(
            hass=hass,
            feature_id=cast(str, FEATURE_DEFINITION["feature_id"]),
            binary_sensor=None,
            debounce_seconds=0,
        )

        self.config_entry = config_entry
        self.config = CO2Config(hass, "", config_entry.options.get("co2_control", {}))

        # Initialize Ramses commands for direct device control
        self.ramses_commands = RamsesCommands(hass)

        # CO2-specific state tracking
        self._co2_active = False
        self._automation_active = False
        self._zone_managers: dict[str, CO2ZoneManager] = {}
        self._state_change_listeners: list[Any] = []

        # Reference to humidity automation for priority coordination
        self.humidity_manager = None

        # Runtime tracking
        self._activation_time: datetime | None = None
        self._last_fan_speed: int | None = None

        _LOGGER.info("CO2 Control automation initialized")

    def set_humidity_manager(self, humidity_manager: Any) -> None:
        """Set reference to humidity automation manager for priority coordination.

        Args:
            humidity_manager: HumidityAutomationManager instance
        """
        self.humidity_manager = humidity_manager
        _LOGGER.debug("Humidity manager reference set for priority coordination")

    def _is_feature_enabled(self) -> bool:
        """Check if CO2 control feature is enabled in config."""
        try:
            domain_data = self.hass.data.get(DOMAIN, {})
            enabled_features = domain_data.get("enabled_features")
            if not isinstance(enabled_features, dict):
                enabled_features = (
                    self.config_entry.options.get("enabled_features")
                    or self.config_entry.data.get("enabled_features")
                    or {}
                )

            return enabled_features.get("co2_control", False) is True
        except Exception as e:
            _LOGGER.warning("Could not check CO2 feature status: %s", e)
            return False

    async def async_setup(self) -> bool:
        """Set up CO2 automation.

        Returns:
            True if setup successful
        """
        if not self._is_feature_enabled():
            _LOGGER.info("CO2 control feature is not enabled, skipping setup")
            return False

        # Initialize zone managers for each device
        await self._setup_zone_managers()

        # Set up state change listeners for CO2 sensors
        await self._setup_sensor_listeners()

        _LOGGER.info("CO2 automation setup complete")
        return True

    async def _setup_zone_managers(self) -> None:
        """Set up zone managers for each configured device."""
        # Get devices from hass.data
        domain_data = self.hass.data.get(DOMAIN, {})
        devices = domain_data.get("devices", {})

        for device_id, device_data in devices.items():
            co2_config = self.config_entry.options.get("co2_control", {})
            device_co2_config = co2_config.get(device_id, {})

            if device_co2_config.get("enabled", False):
                zone_manager = CO2ZoneManager(self.hass, device_id, device_co2_config)
                self._zone_managers[device_id] = zone_manager
                _LOGGER.info("Created zone manager for device %s", device_id)

    async def _setup_sensor_listeners(self) -> None:
        """Set up state change listeners for all CO2 sensors."""
        for device_id, zone_manager in self._zone_managers.items():
            for zone in zone_manager.zones.values():
                if zone.sensor_entity:
                    listener = async_track_state_change_event(
                        self.hass,
                        [zone.sensor_entity],
                        self._handle_co2_sensor_change,
                    )
                    self._state_change_listeners.append(listener)
                    _LOGGER.debug(
                        "Listening to CO2 sensor %s for zone %s",
                        zone.sensor_entity,
                        zone.zone_id,
                    )

    async def _handle_co2_sensor_change(self, event: Event) -> None:
        """Handle CO2 sensor state change.

        Args:
            event: State change event
        """
        entity_id = event.data.get("entity_id")
        new_state = event.data.get("new_state")

        if not new_state:
            return

        # Find which zone this sensor belongs to
        for device_id, zone_manager in self._zone_managers.items():
            for zone_id, zone in zone_manager.zones.items():
                if zone.sensor_entity == entity_id:
                    await zone_manager.update_from_state(zone_id, new_state)
                    await self._evaluate_co2_control(device_id)
                    return

    async def _evaluate_co2_control(self, device_id: str) -> None:
        """Evaluate CO2 control and adjust fan speed if needed.

        Args:
            device_id: Device identifier
        """
        if not self.config.automation_enabled:
            return

        zone_manager = self._zone_managers.get(device_id)
        if not zone_manager:
            return

        # Check for triggered zones
        triggered_zones = await zone_manager.check_zone_triggers(
            self.config.activation_hysteresis,
            self.config.deactivation_hysteresis,
        )

        was_active = self._co2_active
        self._co2_active = len(triggered_zones) > 0

        # State change logging
        if self._co2_active and not was_active:
            self._activation_time = datetime.now()
            _LOGGER.info(
                "CO2 control activated for device %s - triggered zones: %s",
                device_id,
                triggered_zones,
            )
            # Notify humidity control to pause
            await self._notify_priority_takeover()

        elif not self._co2_active and was_active:
            _LOGGER.info("CO2 control deactivated for device %s", device_id)
            # Notify humidity control it can resume
            await self._notify_priority_release()

        # Calculate and set fan speed
        if self._co2_active:
            await self._adjust_fan_speed(device_id, zone_manager)
        else:
            # Return to idle/normal speed
            await self._return_to_idle(device_id)

    async def _adjust_fan_speed(
        self, device_id: str, zone_manager: CO2ZoneManager
    ) -> None:
        """Adjust fan speed based on CO2 levels.

        Args:
            device_id: Device identifier
            zone_manager: Zone manager instance
        """
        # Calculate required fan speed
        base_speed = 2  # Base speed when CO2 triggered
        max_speed = 5  # Maximum fan speed

        target_speed = await zone_manager.calculate_combined_fan_speed(
            base_speed, max_speed
        )

        # Map speed to command name
        speed_commands = {
            1: "fan_low",
            2: "fan_low",
            3: "fan_medium",
            4: "fan_high",
            5: "fan_high",
        }
        command_name = speed_commands.get(target_speed, "fan_medium")

        # Only send command if speed changed
        if target_speed != self._last_fan_speed:
            result = await self.ramses_commands.send_command(device_id, command_name)
            if result.success:
                self._last_fan_speed = target_speed
                _LOGGER.info(
                    "Set fan speed to %s for device %s (CO2 control)",
                    target_speed,
                    device_id,
                )
            else:
                _LOGGER.error("Failed to set fan speed for device %s", device_id)

    async def _return_to_idle(self, device_id: str) -> None:
        """Return fan to idle speed.

        Args:
            device_id: Device identifier
        """
        idle_speed = 1
        if self._last_fan_speed != idle_speed:
            result = await self.ramses_commands.send_command(device_id, "fan_auto")
            if result.success:
                self._last_fan_speed = idle_speed
                _LOGGER.info("Returned fan to idle speed for device %s", device_id)

    async def _notify_priority_takeover(self) -> None:
        """Notify humidity control that CO2 has taken priority."""
        humidity_mgr = self.humidity_manager
        if humidity_mgr is not None:
            await humidity_mgr.pause_for_co2()  # type: ignore[unreachable]
            _LOGGER.debug("Notified humidity control of CO2 priority takeover")

    async def _notify_priority_release(self) -> None:
        """Notify humidity control that CO2 has released priority."""
        humidity_mgr = self.humidity_manager
        if humidity_mgr is not None:
            await humidity_mgr.resume_from_co2()  # type: ignore[unreachable]
            _LOGGER.debug("Notified humidity control of CO2 priority release")

    def is_active(self) -> bool:
        """Check if CO2 control is currently active.

        Returns:
            True if CO2 control is active
        """
        return self._co2_active

    def get_status(self) -> dict[str, Any]:
        """Get current CO2 control status.

        Returns:
            Status dictionary
        """
        return {
            "enabled": self.config.enabled,
            "automation_enabled": self.config.automation_enabled,
            "active": self._co2_active,
            "activation_time": (
                self._activation_time.isoformat() if self._activation_time else None
            ),
            "last_fan_speed": self._last_fan_speed,
            "zones": {
                device_id: zone_manager.get_zone_status()
                for device_id, zone_manager in self._zone_managers.items()
            },
        }

    async def async_unload(self) -> bool:
        """Unload CO2 automation.

        Returns:
            True if unload successful
        """
        # Remove state change listeners
        for listener in self._state_change_listeners:
            listener()
        self._state_change_listeners.clear()

        _LOGGER.info("CO2 automation unloaded")
        return True


__all__ = ["CO2AutomationManager"]
