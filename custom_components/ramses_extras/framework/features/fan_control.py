"""Fan Control Feature for Ramses Extras framework.

This module provides a fan control feature implementation using the framework's
base automation class, enabling advanced HVAC fan control operations including
speed management, mode control, and scheduling.
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from typing import Any, Optional, Set, cast

from homeassistant.core import HomeAssistant, State
from homeassistant.helpers import entity_registry

from ....const import AVAILABLE_FEATURES, FEATURE_ID_HVAC_FAN_CARD
from ....framework.helpers.automation import ExtrasBaseAutomation
from ....framework.helpers.common import RamsesValidator
from ....framework.helpers.device import find_ramses_device, get_device_type
from ....framework.helpers.entity import EntityHelpers
from ....helpers.entity import get_feature_entity_mappings

_LOGGER = logging.getLogger(__name__)


@dataclass
class FanMode:
    """Represents a fan operating mode."""

    name: str
    speed_range: tuple[int, int]  # (min_speed, max_speed)
    auto_speeds: list[int]
    description: str
    priority: int = 0


@dataclass
class FanSchedule:
    """Represents a fan control schedule."""

    name: str
    start_time: time
    end_time: time
    mode: str
    speed: int | None = None
    days: list[int] | None = None  # 0=Monday, 6=Sunday
    active: bool = True


class FanControlFeature(ExtrasBaseAutomation):
    """Fan Control feature using the framework.

    This implementation provides comprehensive fan control including:
    - Multiple fan speed modes
    - Automatic and manual operation
    - Scheduling capabilities
    - Integration with humidity control
    - Energy efficiency optimization
    """

    def __init__(
        self,
        hass: HomeAssistant,
        feature_id: str = FEATURE_ID_HVAC_FAN_CARD,
        binary_sensor: Any = None,
        debounce_seconds: int = 30,
    ) -> None:
        """Initialize the fan control feature.

        Args:
            hass: Home Assistant instance
            feature_id: Feature identifier
            binary_sensor: Optional binary sensor for status
            debounce_seconds: Debounce duration
        """
        super().__init__(hass, feature_id, binary_sensor, debounce_seconds)

        # Fan control configuration
        self._fan_config = self._get_fan_config()

        # Fan modes and schedules
        self._fan_modes = self._initialize_fan_modes()
        self._fan_schedules: list[FanSchedule] = []
        self._current_mode = "auto"
        self._current_speed = 0
        self._boost_until: datetime | None = None

        # Performance tracking
        self._performance_stats: dict[str, Any] = {
            "total_runtime": timedelta(),
            "mode_changes": 0,
            "speed_changes": 0,
            "efficiency_score": 0.0,
        }

        # State tracking
        self._last_device_check: dict[str, Any] = {}
        self._device_capabilities: dict[str, dict[str, Any]] = {}

        _LOGGER.info(f"FanControlFeature initialized with {len(self._fan_modes)} modes")

    def _get_fan_config(self) -> dict[str, Any]:
        """Get fan control configuration.

        Returns:
            Fan control configuration dictionary
        """
        feature_config = AVAILABLE_FEATURES.get(FEATURE_ID_HVAC_FAN_CARD, {})
        return {
            "min_speed": feature_config.get("min_speed", 0),
            "max_speed": feature_config.get("max_speed", 100),
            "default_speed": feature_config.get("default_speed", 50),
            "auto_modes": ["auto", "away", "boost", "eco"],
            "manual_speeds": [20, 30, 40, 50, 60, 70, 80, 90],
            "boost_duration": feature_config.get("boost_duration", 30),  # minutes
            "efficiency_threshold": feature_config.get("efficiency_threshold", 0.8),
            "integration_humidity_control": feature_config.get(
                "integration_humidity_control", True
            ),
        }

    def _initialize_fan_modes(self) -> list[FanMode]:
        """Initialize available fan modes.

        Returns:
            list of FanMode configurations
        """
        modes = [
            FanMode(
                name="off",
                speed_range=(0, 0),
                auto_speeds=[],
                description="Fan turned off",
                priority=0,
            ),
            FanMode(
                name="auto",
                speed_range=(20, 80),
                auto_speeds=[25, 35, 50, 65],
                description="Automatic speed control based on conditions",
                priority=10,
            ),
            FanMode(
                name="eco",
                speed_range=(15, 60),
                auto_speeds=[20, 30, 45],
                description="Energy-efficient operation",
                priority=8,
            ),
            FanMode(
                name="away",
                speed_range=(10, 40),
                auto_speeds=[15, 25],
                description="Low-energy operation for away periods",
                priority=6,
            ),
            FanMode(
                name="boost",
                speed_range=(70, 100),
                auto_speeds=[80, 90],
                description="Maximum ventilation for quick air changes",
                priority=9,
            ),
        ]

        # Add manual mode
        modes.append(
            FanMode(
                name="manual",
                speed_range=(
                    self._fan_config["min_speed"],
                    self._fan_config["max_speed"],
                ),
                auto_speeds=self._fan_config["manual_speeds"],
                description="Manual speed control",
                priority=7,
            )
        )

        return modes

    def _generate_entity_patterns(self) -> list[str]:
        """Generate entity patterns for fan control.

        Returns:
            list of entity patterns to listen for
        """
        patterns = [
            # Fan control entities
            "number.fan_speed_*",
            "number.boost_duration_*",
            "select.fan_mode_*",
            "switch.fan_boost_*",
            # Integration with humidity control
            "sensor.indoor_absolute_humidity_*",
            "sensor.outdoor_absolute_humidity_*",
            "binary_sensor.dehumidifying_active_*",
            # Device state entities
            "sensor.*_indoor_humidity",  # CC entities
        ]

        _LOGGER.debug(f"Generated fan control patterns: {patterns}")
        return patterns

    async def start(self) -> None:
        """Start the fan control feature.

        Initializes schedules, loads saved settings, and starts monitoring.
        """
        _LOGGER.info("🚀 Starting Fan Control feature")

        # Load saved configuration
        await self._load_fan_configuration()

        # Initialize device capabilities
        await self._initialize_device_capabilities()

        # Start base automation
        await super().start()

        # Start schedule monitoring
        asyncio.create_task(self._monitor_fan_schedules())

        _LOGGER.info("✅ Fan Control feature started successfully")

    async def _load_fan_configuration(self) -> None:
        """Load saved fan configuration."""
        # In a real implementation, this would load from persistent storage
        # For now, we'll use defaults and set a simple schedule

        # Default schedule for weekdays
        weekday_schedule = FanSchedule(
            name="Weekday Schedule",
            start_time=time(7, 0),  # 7:00 AM
            end_time=time(22, 0),  # 10:00 PM
            mode="auto",
            days=list(range(5)),  # Monday to Friday
        )
        self._fan_schedules.append(weekday_schedule)

        _LOGGER.debug(f"Loaded {len(self._fan_schedules)} fan schedules")

    async def _initialize_device_capabilities(self) -> None:
        """Initialize device capabilities from the framework."""
        try:
            # Get all Ramses devices
            devices = await find_ramses_device(self.hass, "HvacVentilator")

            for device in devices:
                device_id = device.id

                # Get device capabilities
                capabilities = {
                    "max_speed": self._fan_config["max_speed"],
                    "min_speed": self._fan_config["min_speed"],
                    "supports_modes": ["off", "auto", "boost", "manual"],
                    "supports_boost": True,
                    "supports_timer": True,
                }

                self._device_capabilities[device_id] = capabilities
                _LOGGER.debug(f"Initialized capabilities for device {device_id}")

        except Exception as e:
            _LOGGER.error(f"Failed to initialize device capabilities: {e}")

    async def _process_automation_logic(
        self, device_id: str, entity_states: dict[str, float]
    ) -> None:
        """Process fan control automation logic.

        Args:
            device_id: Device identifier
            entity_states: Validated entity state values
        """
        _LOGGER.info(
            f"Processing fan control logic - Feature: {self.feature_id}, "
            f"Device: {device_id}"
        )

        try:
            # Get current time and schedule
            current_mode = self._get_current_schedule_mode()

            # Get device state
            device_state = await self._get_device_state(device_id)
            if not device_state:
                return

            # Determine target mode and speed
            target_mode, target_speed = await self._determine_fan_operation(
                device_id, entity_states, current_mode, device_state
            )

            # Apply fan settings if changed
            await self._apply_fan_settings(device_id, target_mode, target_speed)

        except Exception as e:
            _LOGGER.error(f"Device {device_id}: Error in fan control logic - {e}")

    def _get_current_schedule_mode(self) -> str:
        """Get current mode based on schedule.

        Returns:
            Current mode from schedule or "auto" as default
        """
        now = datetime.now()
        current_time = now.time()
        current_day = now.weekday()  # 0=Monday, 6=Sunday

        for schedule in self._fan_schedules:
            if not schedule.active:
                continue

            # Check if current time is within schedule
            if schedule.days and current_day not in schedule.days:
                continue

            if schedule.start_time <= current_time <= schedule.end_time:
                return schedule.mode

        # No active schedule, return default
        return "auto"

    async def _get_device_state(self, device_id: str) -> dict[str, Any] | None:
        """Get current device state.

        Args:
            device_id: Device identifier

        Returns:
            Device state dictionary or None if not found
        """
        try:
            # Get entity mappings
            entity_mappings = get_feature_entity_mappings(self.feature_id, device_id)

            # Get current states
            states = {}
            for state_name, entity_id in entity_mappings.items():
                if entity_id:
                    state = self.hass.states.get(entity_id)
                    if state:
                        try:
                            states[state_name] = float(state.state)
                        except (ValueError, TypeError):
                            states[state_name] = state.state

            return {
                "states": states,
                "entity_mappings": entity_mappings,
                "last_update": datetime.now(),
            }

        except Exception as e:
            _LOGGER.error(f"Failed to get device state for {device_id}: {e}")
            return None

    async def _determine_fan_operation(
        self,
        device_id: str,
        entity_states: dict[str, float],
        schedule_mode: str,
        device_state: dict[str, Any],
    ) -> tuple[str, int]:
        """Determine optimal fan operation based on conditions.

        Args:
            device_id: Device identifier
            entity_states: Entity state values
            schedule_mode: Mode from schedule
            device_state: Current device state

        Returns:
            Tuple of (target_mode, target_speed)
        """
        current_time = datetime.now()

        # Check for boost override
        if self._boost_until and current_time < self._boost_until:
            return "boost", self._fan_config["max_speed"]
        if self._boost_until and current_time >= self._boost_until:
            self._boost_until = None
            _LOGGER.info("Boost period ended, returning to scheduled mode")

        # Base mode from schedule
        target_mode = schedule_mode

        # Adjust based on humidity if integrated
        if self._fan_config["integration_humidity_control"]:
            humidity_adjustment = self._get_humidity_adjustment(entity_states)
            if humidity_adjustment:
                target_mode = humidity_adjustment["mode"]
                target_speed = humidity_adjustment["speed"]
                _LOGGER.info(
                    f"Humidity adjustment applied: mode={target_mode}, "
                    f"speed={target_speed}"
                )
                return target_mode, target_speed

        # Determine speed based on mode
        target_speed = self._calculate_speed_for_mode(target_mode, device_state)

        return target_mode, target_speed

    def _get_humidity_adjustment(
        self, entity_states: dict[str, float]
    ) -> dict[str, Any] | None:
        """Get humidity-based fan adjustment.

        Args:
            entity_states: Entity state values

        Returns:
            Adjustment dictionary or None
        """
        indoor_abs = entity_states.get("indoor_abs")
        outdoor_abs = entity_states.get("outdoor_abs")

        if not indoor_abs or not outdoor_abs:
            return None

        # Calculate humidity differential
        humidity_diff = indoor_abs - outdoor_abs

        # High humidity differential = need more ventilation
        if humidity_diff > 3.0:
            return {"mode": "boost", "speed": 90}
        if humidity_diff > 1.5:
            return {"mode": "auto", "speed": 65}
        if humidity_diff < -1.0:
            return {"mode": "eco", "speed": 30}

        return None

    def _calculate_speed_for_mode(self, mode: str, device_state: dict[str, Any]) -> int:
        """Calculate speed for a given mode.

        Args:
            mode: Fan mode
            device_state: Device state

        Returns:
            Target speed
        """
        # Find mode configuration
        mode_config = next((m for m in self._fan_modes if m.name == mode), None)
        if not mode_config:
            return int(self._fan_config["default_speed"])

        if mode == "off":
            return 0
        if mode == "manual":
            # For manual mode, use current speed or default
            return self._current_speed or self._fan_config["default_speed"]
        if mode in ["auto", "boost", "eco", "away"]:
            # Use middle of speed range for auto modes
            min_speed, max_speed = mode_config.speed_range
            base_speed = (min_speed + max_speed) // 2

            # Apply device state adjustments
            states = device_state.get("states", {})

            # Adjust based on temperature if available
            temperature = states.get("temperature", 20.0)
            if temperature > 25:
                base_speed += 10
            elif temperature < 18:
                base_speed -= 10

            # Clamp to mode range
            return max(min_speed, min(max_speed, base_speed))

        return int(self._fan_config["default_speed"])

    async def _apply_fan_settings(
        self, device_id: str, target_mode: str, target_speed: int
    ) -> None:
        """Apply fan settings to device.

        Args:
            device_id: Device identifier
            target_mode: Target fan mode
            target_speed: Target fan speed
        """
        try:
            # Check if settings actually changed
            if (
                self._current_mode == target_mode
                and self._current_speed == target_speed
            ):
                return

            _LOGGER.info(
                f"Device {device_id}: Applying fan settings - "
                f"mode={target_mode}, speed={target_speed}%"
            )

            # Get entity mappings
            entity_mappings = get_feature_entity_mappings(self.feature_id, device_id)

            # Apply mode change
            if "fan_mode" in entity_mappings and "fan_mode_select" in entity_mappings:
                await self.hass.services.async_call(
                    "select",
                    "select_option",
                    {
                        "entity_id": entity_mappings["fan_mode_select"],
                        "option": target_mode,
                    },
                )
                mode_changes = cast(int, self._performance_stats["mode_changes"])
                self._performance_stats["mode_changes"] = mode_changes + 1

            # Apply speed change
            if target_mode != "off" and "fan_speed" in entity_mappings:
                await self.hass.services.async_call(
                    "number",
                    "set_value",
                    {"entity_id": entity_mappings["fan_speed"], "value": target_speed},
                )
                speed_changes = cast(int, self._performance_stats["speed_changes"])
                self._performance_stats["speed_changes"] = speed_changes + 1
            elif target_mode == "off" and "fan_mode" in entity_mappings:
                # Turn off fan
                await self.hass.services.async_call(
                    "fan", "turn_off", {"entity_id": entity_mappings["fan_mode"]}
                )

            # Update current state
            self._current_mode = target_mode
            self._current_speed = target_speed

            # Fire state change event
            self.hass.bus.async_fire(
                "ramses_extras_fan_state_changed",
                {
                    "device_id": device_id,
                    "mode": target_mode,
                    "speed": target_speed,
                    "timestamp": datetime.now().isoformat(),
                },
            )

        except Exception as e:
            _LOGGER.error(f"Device {device_id}: Failed to apply fan settings - {e}")

    async def _monitor_fan_schedules(self) -> None:
        """Monitor and apply fan schedules."""
        while self._active:
            try:
                # current_time = datetime.now()  # Unused variable
                current_mode = self._get_current_schedule_mode()

                # Check if we need to apply schedule changes
                if (
                    current_mode != self._current_mode
                    and self._current_mode != "manual"
                ):
                    _LOGGER.info(
                        f"Schedule change detected: {self._current_mode} -> "
                        f"{current_mode}"
                    )

                    # Trigger re-evaluation for all devices
                    await self._trigger_all_devices_recheck()

                # Wait 30 seconds before next check
                await asyncio.sleep(30)

            except asyncio.CancelledError:
                break
            except Exception as e:
                _LOGGER.error(f"Error in schedule monitoring: {e}")
                await asyncio.sleep(60)

    async def _trigger_all_devices_recheck(self) -> None:
        """Trigger re-evaluation for all devices."""
        # This would trigger the automation to run for all devices
        # In a real implementation, this would iterate through all known devices
        # and force a re-evaluation of their conditions

    async def _get_device_entity_states(self, device_id: str) -> dict[str, float]:
        """Get entity states for fan control with extended validation.

        Args:
            device_id: Device identifier

        Returns:
            Dictionary with entity state values
        """
        # Get base entity states using the framework method
        states = await super()._get_device_entity_states(device_id)

        # Add fan-specific state validation
        for state_name, value in states.items():
            if "speed" in state_name.lower():
                # Validate speed range
                validated_speed = max(
                    int(self._fan_config["min_speed"]),
                    min(int(self._fan_config["max_speed"]), value),
                )
                if validated_speed != value:
                    _LOGGER.debug(
                        f"Device {device_id}: Corrected {state_name} speed from "
                        f"{value} to {validated_speed}"
                    )
                    states[state_name] = validated_speed

        return cast(dict[str, float], states)

    # Public API methods
    def set_fan_mode(self, mode: str) -> bool:
        """Set fan mode.

        Args:
            mode: Fan mode to set

        Returns:
            True if mode was set successfully
        """
        if mode not in [m.name for m in self._fan_modes]:
            _LOGGER.warning(f"Invalid fan mode: {mode}")
            return False

        self._current_mode = mode
        _LOGGER.info(f"Fan mode set to: {mode}")
        return True

    def set_fan_speed(self, speed: int) -> bool:
        """Set fan speed.

        Args:
            speed: Fan speed percentage

        Returns:
            True if speed was set successfully
        """
        if not (
            self._fan_config["min_speed"] <= speed <= self._fan_config["max_speed"]
        ):
            _LOGGER.warning(f"Invalid fan speed: {speed}")
            return False

        self._current_speed = speed
        _LOGGER.info(f"Fan speed set to: {speed}%")
        return True

    def activate_boost(self, duration_minutes: int | None = None) -> bool:
        """Activate fan boost.

        Args:
            duration_minutes: Boost duration in minutes

        Returns:
            True if boost was activated
        """
        boost_duration = duration_minutes or self._fan_config["boost_duration"]
        self._boost_until = datetime.now() + timedelta(minutes=boost_duration)

        _LOGGER.info(f"Fan boost activated for {boost_duration} minutes")
        return True

    def add_schedule(self, schedule: FanSchedule) -> None:
        """Add a fan schedule.

        Args:
            schedule: FanSchedule to add
        """
        self._fan_schedules.append(schedule)
        _LOGGER.info(f"Added fan schedule: {schedule.name}")

    def get_current_mode(self) -> str:
        """Get current fan mode.

        Returns:
            Current fan mode
        """
        return self._current_mode

    def get_current_speed(self) -> int:
        """Get current fan speed.

        Returns:
            Current fan speed
        """
        return self._current_speed

    def get_fan_modes(self) -> list[str]:
        """Get available fan modes.

        Returns:
            list of available fan mode names
        """
        return [mode.name for mode in self._fan_modes]

    def get_performance_stats(self) -> dict[str, Any]:
        """Get fan control performance statistics.

        Returns:
            Dictionary with performance statistics
        """
        stats = self._performance_stats.copy()
        stats["current_mode"] = self._current_mode
        stats["current_speed"] = self._current_speed
        stats["active_schedules"] = len([s for s in self._fan_schedules if s.active])
        stats["devices_controlled"] = len(self._device_capabilities)
        return stats


# Feature registration helper
def create_fan_control_feature(
    hass: HomeAssistant,
    feature_id: str = FEATURE_ID_HVAC_FAN_CARD,
    binary_sensor: Any = None,
    debounce_seconds: int = 30,
) -> FanControlFeature:
    """Create a fan control feature instance.

    Args:
        hass: Home Assistant instance
        feature_id: Feature identifier
        binary_sensor: Optional binary sensor
        debounce_seconds: Debounce duration

    Returns:
        FanControlFeature instance
    """
    return FanControlFeature(
        hass=hass,
        feature_id=feature_id,
        binary_sensor=binary_sensor,
        debounce_seconds=debounce_seconds,
    )


# Framework feature registration
def register_fan_control_feature() -> None:
    """Register the fan control feature with the framework.

    This function registers the fan control feature so it can be
    discovered and managed by the framework's feature manager.
    """
    # entity_registry import is not needed here

    feature_config = {
        "name": "Fan Control",
        "description": "Advanced HVAC fan control with scheduling and automation",
        "class": "FanControlFeature",
        "factory": "create_fan_control_feature",
        "dependencies": ["humidity_control"],  # Optional dependency
        "capabilities": [
            "fan_control",
            "speed_management",
            "mode_selection",
            "scheduling",
            "boost_control",
            "efficiency_optimization",
        ],
    }

    entity_registry.register_feature_implementation(
        FEATURE_ID_HVAC_FAN_CARD, feature_config
    )

    _LOGGER.info("Fan control feature registered with framework")


__all__ = [
    "FanControlFeature",
    "FanMode",
    "FanSchedule",
    "create_fan_control_feature",
    "register_fan_control_feature",
]
