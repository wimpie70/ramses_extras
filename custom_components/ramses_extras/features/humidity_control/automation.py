"""Humidity Control Automation.

This module contains the automation logic for humidity control functionality,
migrated from the original humidity_automation.py but organized within the
feature-centric architecture.
"""

import asyncio
import logging
import time
from collections.abc import Callable, Mapping
from datetime import datetime, timedelta
from typing import Any, cast

from homeassistant.core import Event, HomeAssistant, State
from homeassistant.helpers import entity_registry
from homeassistant.helpers.event import async_track_time_interval

from custom_components.ramses_extras.const import DOMAIN
from custom_components.ramses_extras.framework.base_classes.base_automation import (
    ExtrasBaseAutomation,
)
from custom_components.ramses_extras.framework.helpers.device.core import (
    find_ramses_device,
    get_device_type,
)
from custom_components.ramses_extras.framework.helpers.fan_speed_arbiter import (
    get_fan_speed_arbiter,
)
from custom_components.ramses_extras.framework.helpers.ramses_commands import (
    RamsesCommands,
)

from .config import HumidityConfig
from .const import FEATURE_DEFINITION
from .services import HumidityServices

_LOGGER = logging.getLogger(__name__)


def is_supported_humidity_device(hass: object, device_id: str) -> bool:
    normalized_device_id = device_id.replace("_", ":")
    device = find_ramses_device(hass, normalized_device_id)
    return get_device_type(device) == "HvacVentilator"


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
            feature_id=cast(str, FEATURE_DEFINITION["feature_id"]),
            binary_sensor=None,  # Will be set when entities are available
            debounce_seconds=0,  # No debouncing needed - event-driven approach
        )

        self.config_entry = config_entry
        self.config = HumidityConfig(hass, config_entry)
        self.services = HumidityServices(hass, config_entry)

        # Initialize Ramses commands for direct device control
        self.ramses_commands = RamsesCommands(hass)
        self.fan_speed_arbiter = get_fan_speed_arbiter(hass)

        # Humidity-specific state tracking
        self._dehumidify_active = False
        self._automation_active = False
        self._last_decision_state: dict[str, Any] | None = None
        self._decision_history: list[dict[str, Any]] = []
        self._latest_sensor_control_context: dict[str, dict[str, Any] | None] = {}
        self._area_history: dict[str, dict[str, list[dict[str, float]]]] = {}
        self._active_area_spikes: dict[str, list[dict[str, Any]] | dict[str, Any]] = {}
        self._area_spike_check_handles: dict[str, Callable[[], None]] = {}

        # Performance tracking
        self._decision_count = 0
        self._active_cycles = 0

        # CO2 priority coordination
        self.co2_manager = None
        self._paused_for_co2 = False

        _LOGGER.info("Enhanced Humidity Control automation initialized")
        _LOGGER.info("Feature enabled status: %s", self._is_feature_enabled())

    def _is_feature_enabled(self) -> bool:
        """Check if humidity_control feature is enabled in config."""
        try:
            domain_data = self.hass.data.get(DOMAIN, {})
            enabled_features = domain_data.get("enabled_features")
            if not isinstance(enabled_features, dict):
                enabled_features = (
                    self.config_entry.options.get("enabled_features")
                    or self.config_entry.data.get("enabled_features")
                    or {}
                )

            return enabled_features.get("humidity_control", False) is True
        except Exception as e:
            _LOGGER.warning("Could not check feature status: %s", e)
            return False

    def _generate_entity_patterns(self) -> list[str]:
        """Generate entity patterns for humidity control.

        Returns:
            List of entity patterns to listen for
        """
        patterns = [
            # Default feature sensors (absolute humidity)
            "sensor.indoor_absolute_humidity_*",
            "sensor.outdoor_absolute_humidity_*",
            # Humidity control entities
            "number.relative_humidity_minimum_*",
            "number.relative_humidity_maximum_*",
            "number.absolute_humidity_offset_*",
            "switch.dehumidify_*",
            # Ramses CC sensor entities (both old and new naming)
            "sensor.*_indoor_humidity",
            "sensor.fan_*_indoor_humidity",
        ]

        sensor_control_config = (
            self.config_entry.options.get("sensor_control")
            or self.config_entry.data.get("sensor_control")
            or {}
        )
        area_sensor_map = sensor_control_config.get("area_sensors") or {}
        if isinstance(area_sensor_map, dict):
            for area_sensors in area_sensor_map.values():
                if not isinstance(area_sensors, list):
                    continue
                for item in area_sensors:
                    if not isinstance(item, dict):
                        continue
                    temp_entity = str(item.get("temperature_entity") or "").strip()
                    humidity_entity = str(item.get("humidity_entity") or "").strip()
                    if temp_entity:
                        patterns.append(temp_entity)
                    if humidity_entity:
                        patterns.append(humidity_entity)

        _LOGGER.debug(
            "Generated %s entity patterns for humidity control",
            len(patterns),
        )
        _LOGGER.debug("Entity patterns: %s", patterns)
        return patterns

    def _extract_device_id(self, entity_id: str) -> str | None:
        device_id = super()._extract_device_id(entity_id)
        if isinstance(device_id, str) and device_id:
            return device_id

        sensor_control_config = (
            self.config_entry.options.get("sensor_control")
            or self.config_entry.data.get("sensor_control")
            or {}
        )
        area_sensor_map = sensor_control_config.get("area_sensors") or {}
        if not isinstance(area_sensor_map, dict):
            return None

        for raw_device_id, area_sensors in area_sensor_map.items():
            if not isinstance(area_sensors, list):
                continue
            for item in area_sensors:
                if not isinstance(item, dict):
                    continue
                if entity_id in {
                    str(item.get("temperature_entity") or "").strip(),
                    str(item.get("humidity_entity") or "").strip(),
                }:
                    return cast(str, raw_device_id).replace(":", "_")

        return None

    async def _check_any_device_ready(self) -> bool:
        """Check if any device has all required humidity control entities ready.

        Returns:
            True if at least one device is ready
        """
        # Check if feature is still enabled first
        if not self._is_feature_enabled():
            _LOGGER.debug("Humidity control feature disabled, stopping device checks")
            return False

        _LOGGER.debug("Checking whether any device is ready for %s", self.feature_id)
        _LOGGER.debug("Entity patterns being checked: %s", self.entity_patterns)

        # Use the humidity-specific entity patterns
        patterns = self.entity_patterns

        # Find any entities that match our patterns
        for pattern in patterns:
            if pattern.endswith("*"):
                prefix = pattern[:-1]  # Remove the *
                entity_type = prefix.split(".")[0]
                entities = self.hass.states.async_all(entity_type)

                if "*" in pattern:
                    # Handle wildcard patterns
                    if pattern.startswith(f"{entity_type}."):
                        # Pattern like "sensor.*_indoor_humidity"
                        if ".*_" in pattern:
                            # Extract suffix after .*
                            suffix = pattern.split(".*_", 1)[1]
                            matching_entities = [
                                state
                                for state in entities
                                if state.entity_id.endswith(f"_{suffix}")
                            ]
                        else:
                            # Pattern like "sensor.indoor_absolute_humidity_*"
                            matching_entities = [
                                state
                                for state in entities
                                if state.entity_id.startswith(prefix)
                            ]
                    else:
                        # Fallback for other wildcard patterns
                        matching_entities = [
                            state
                            for state in entities
                            if state.entity_id.startswith(prefix[:-1])
                        ]
                else:
                    matching_entities = [
                        state
                        for state in entities
                        if state.entity_id.startswith(prefix)
                    ]

                if matching_entities:
                    _LOGGER.debug(
                        "Found %d matching entities for pattern %s",
                        len(matching_entities),
                        pattern,
                    )
                    # Check each matching entity's device has all required entities
                    for entity_state in matching_entities:
                        device_id = self._extract_device_id(entity_state.entity_id)
                        _LOGGER.debug(
                            "Checking device_id=%s from entity %s",
                            device_id,
                            entity_state.entity_id,
                        )
                        if device_id:
                            validation_result = await self._validate_device_entities(
                                device_id
                            )
                            _LOGGER.debug(
                                "Validation result for %s: %s",
                                device_id,
                                validation_result,
                            )
                            if validation_result:
                                _LOGGER.info(
                                    "Humidity control: device %s has all %s "
                                    "entities ready",
                                    device_id,
                                    self.feature_id,
                                )
                                return True
                        else:
                            _LOGGER.warning(
                                "Could not extract device_id from %s",
                                entity_state.entity_id,
                            )
                else:
                    _LOGGER.debug("No matching entities found for pattern %s", pattern)

        return False

    async def _validate_device_entities(self, device_id: str) -> bool:
        """Validate all required entities exist for a humidity control device.

        Args:
            device_id: Device identifier

        Returns:
            True if all entities exist, False otherwise
        """
        from custom_components.ramses_extras.framework.helpers.entity.core import (
            get_feature_entity_mappings,
            get_required_entity_ids_for_feature_device,
        )

        entity_mappings = await get_feature_entity_mappings(
            self.feature_id,
            device_id,
            self.hass,
        )
        required_entity_ids = await get_required_entity_ids_for_feature_device(
            self.feature_id,
            device_id,
        )
        missing_entities = []

        # Get entity registry
        registry = entity_registry.async_get(self.hass)

        _LOGGER.debug("Validating entities for device_id=%s", device_id)

        # Check entities from required_entities (created by humidity_control feature)
        for expected_entity_id in required_entity_ids:
            # Check entity registry instead of states
            entity_entry = registry.async_get(expected_entity_id)
            if not entity_entry:
                _LOGGER.debug("Missing entity: %s", expected_entity_id)
                missing_entities.append(expected_entity_id)

        # Check entities from entity_mappings (created by default feature)
        for state_name, expected_entity_id in entity_mappings.items():
            # Check entity registry instead of states
            entity_entry = registry.async_get(expected_entity_id)
            if not entity_entry:
                _LOGGER.debug("Missing mapped entity: %s", expected_entity_id)
                missing_entities.append(expected_entity_id)

        if missing_entities:
            # Only log missing entities once per device to avoid log spam
            # Store missing entities per device to track what we've already logged
            if not hasattr(self, "_logged_missing_entities"):
                self._logged_missing_entities: dict[str, list[str]] = {}

            device_key = f"{device_id}_{self.feature_id}"
            already_logged = self._logged_missing_entities.get(device_key)

            if already_logged != missing_entities:
                _LOGGER.debug(
                    "Device %s: Missing %s entities - %s",
                    device_id,
                    self.feature_id,
                    missing_entities,
                )
                self._logged_missing_entities[device_key] = missing_entities
            return False

        return True

    async def _get_device_entity_states(self, device_id: str) -> dict[str, Any]:
        """Get all entity states for a humidity control device.

        Args:
            device_id: Device identifier (e.g., "32_153289")

        Returns:
            Dictionary with entity state values (numeric or boolean)

        Raises:
            ValueError: If any entity is unavailable or has invalid values
        """
        states: dict[str, Any] = {}

        from custom_components.ramses_extras.framework.helpers.entity.core import (
            get_feature_entity_mappings,
        )

        # Base mappings from feature definition (centralized helper)
        state_mappings = await get_feature_entity_mappings(
            self.feature_id,
            device_id,
            self.hass,
        )

        # Optional context from sensor_control via WebSocket helper to align
        # indoor_rh with the same indoor_humidity source used elsewhere.
        sensor_ctx = await self._get_sensor_control_context(device_id)
        self._latest_sensor_control_context[device_id] = sensor_ctx
        if sensor_ctx:
            metric_mappings = cast(dict[str, str], sensor_ctx.get("mappings") or {})
            indoor_humidity_entity = metric_mappings.get("indoor_humidity")
            if indoor_humidity_entity:
                state_mappings["indoor_rh"] = indoor_humidity_entity

        for state_name, entity_id in state_mappings.items():
            state = self.hass.states.get(entity_id)

            if not state:
                raise ValueError(f"Entity {entity_id} not found")

            if state.state in ["unavailable", "unknown"]:
                raise ValueError(f"Entity {entity_id} state unavailable")

            entity_type = self._extract_entity_type_from_id(entity_id)
            value = self._convert_entity_state(entity_type, state.state)
            states[state_name] = value

        return states

    async def _get_sensor_control_context(
        self, device_id: str
    ) -> dict[str, Any] | None:
        """Get merged mappings + abs_humidity_inputs from sensor_control.

        Uses the same WebSocket command as the frontend so that humidity_control
        benefits from the exact same resolver logic as the cards.
        """
        try:
            if not self._is_sensor_control_enabled():
                return None

            from custom_components.ramses_extras.framework.helpers.websocket_base import (  # noqa: E501
                GetEntityMappingsCommand,
            )

            cmd = GetEntityMappingsCommand(
                self.hass,
                self.feature_id,
                overlay_provider=self._get_sensor_control_overlay,
            )

            class MockConnection:  # pragma: no cover - simple data holder
                def __init__(self) -> None:
                    self.result: dict[str, Any] | None = None

                def send_result(self, msg_id: str, result: dict[str, Any]) -> None:
                    self.result = result

            connection = MockConnection()
            msg = {
                "id": "humidity_control_sensor_context",
                "device_id": device_id,
            }

            await cmd.execute(connection, msg)

            if not connection.result or not connection.result.get("success"):
                _LOGGER.warning(
                    "Failed to get sensor_control context for %s", device_id
                )
                return None

            return connection.result
        except Exception as err:  # pragma: no cover - defensive logging
            _LOGGER.error(
                "Error getting sensor_control context for %s: %s", device_id, err
            )
            return None

    def _get_device_type_for_sensor_control(self, device_id: str) -> str | None:
        devices = self.hass.data.get(DOMAIN, {}).get("devices", [])
        target_colon = str(device_id).replace("_", ":")

        for device in devices:
            if isinstance(device, dict):
                raw_id = device.get("device_id")
                device_type = device.get("type")
            else:
                raw_id = device
                device_type = getattr(device, "type", None)

            if raw_id is None:
                continue

            if isinstance(raw_id, str):
                resolved_id = raw_id
            else:
                resolved_id = None
                for attr in ("id", "device_id", "_id", "name"):
                    if hasattr(raw_id, attr):
                        value = getattr(raw_id, attr)
                        if value is not None:
                            resolved_id = str(value)
                            break
                if resolved_id is None:
                    resolved_id = str(raw_id)

            if resolved_id and resolved_id.replace("_", ":") == target_colon:
                return str(device_type) if device_type else None

        return None

    async def _get_sensor_control_overlay(
        self, device_id: str, base_mappings: dict[str, str]
    ) -> dict[str, Any]:
        try:
            from custom_components.ramses_extras.features.sensor_control import (
                resolver as sensor_control_resolver,
            )

            device_type = self._get_device_type_for_sensor_control(device_id)
            if not device_type:
                return {}

            resolver = sensor_control_resolver.SensorControlResolver(self.hass)
            sensor_result = await resolver.resolve_entity_mappings(
                device_id, device_type
            )

            merged_mappings = base_mappings.copy()
            merged_mappings.update(sensor_result["mappings"])

            return {
                "mappings": merged_mappings,
                "sources": sensor_result["sources"],
                "raw_internal": sensor_result.get("raw_internal"),
                "abs_humidity_inputs": sensor_result.get("abs_humidity_inputs", {}),
                "area_sensors": sensor_result.get("area_sensors", []),
            }
        except Exception as err:
            _LOGGER.error(
                "Failed to apply sensor_control overlays for %s: %s",
                device_id,
                err,
                exc_info=True,
            )
            return {}

    def _is_sensor_control_enabled(self) -> bool:
        """Check if sensor_control feature is enabled.

        Returns:
            True if sensor_control is enabled, False otherwise
        """
        try:
            config_entry = self.hass.data.get(DOMAIN, {}).get("config_entry")
            if not config_entry:
                return False

            enabled_features = (
                config_entry.data.get("enabled_features")
                or config_entry.options.get("enabled_features")
                or {}
            )

            return bool(enabled_features.get("sensor_control", False))
        except Exception:
            return False

    async def start(self) -> None:
        """Start the humidity control automation.

        Initializes automation and begins monitoring.
        """
        _LOGGER.info("Starting humidity control automation")

        # Check if humidity_control feature is enabled
        if not self._is_feature_enabled():
            _LOGGER.info(
                "Humidity control feature is not enabled, skipping automation start"
            )
            return

        _LOGGER.info("Humidity control feature is enabled, proceeding with startup")

        # Load configuration
        await self.config.async_load()

        _LOGGER.info("Configuration loaded, starting base automation")

        self._automation_active = True
        try:
            await super().start()
        except Exception:
            self._automation_active = False
            raise

        _LOGGER.info("Humidity control automation started")

    async def _on_homeassistant_started(self, event: Event | None) -> None:
        await super()._on_homeassistant_started(event)
        if not self._automation_active or not self._is_feature_enabled():
            return
        await self._reconcile_startup_states()

    async def stop(self) -> None:
        """Stop the humidity control automation.

        Shuts down automation and cleans up resources.
        """
        _LOGGER.info("Stopping humidity control automation")

        self._automation_active = False
        for device_id in list(self._active_area_spikes):
            self._clear_active_area_spike(device_id)
        await super().stop()

        _LOGGER.info("Humidity control automation stopped")

    async def _process_automation_logic(
        self, device_id: str, entity_states: Mapping[str, float | bool]
    ) -> None:
        """Process humidity control automation logic for a device.

        Args:
            device_id: Device identifier
            entity_states: Validated entity state values (float or bool)
        """
        _LOGGER.debug(
            "_process_automation_logic: active=%s, enabled=%s",
            self._automation_active,
            self._is_feature_enabled(),
        )
        if not self._automation_active or not self._is_feature_enabled():
            return

        # Check if switch is manually OFF - if so,
        #  don't run automation but keep switch state
        switch_state = entity_states.get("dehumidify")
        if switch_state is not None:
            switch_is_on = bool(switch_state)

            # If switch is OFF, stop automation but don't turn the switch off
            #  (it's already off)
            if not switch_is_on:
                _LOGGER.debug(
                    "Switch is OFF for device %s - automation disabled",
                    device_id,
                )
                if self._dehumidify_active:
                    # Stop dehumidification but don't touch the switch
                    #  (user manually turned it off)
                    await self._stop_dehumidification_without_switch_change(device_id)
                self._clear_active_area_spike(device_id)
                # Just update binary sensor to reflect inactive state
                await self._set_indicator_off(device_id)
                return

        # Switch is ON - run automation

        try:
            # Extract humidity values (these should be float)
            indoor_abs = float(entity_states.get("indoor_abs", 0.0))
            outdoor_abs = float(entity_states.get("outdoor_abs", 0.0))
            indoor_rh = float(entity_states.get("indoor_rh", 0.0))
            min_humidity = float(entity_states.get("min_humidity", 40.0))
            max_humidity = float(entity_states.get("max_humidity", 60.0))
            offset = float(entity_states.get("offset", 0.0))

            # Calculate decision with proper relative humidity logic
            decision = await self._evaluate_humidity_conditions(
                device_id,
                indoor_rh,
                indoor_abs,
                outdoor_abs,
                min_humidity,
                max_humidity,
                offset,
            )

            # Apply decision
            if decision["action"] == "dehumidify":
                # Activate dehumidification: set fan HIGH, binary sensor ON
                await self._activate_dehumidification(device_id, decision)
            elif decision["action"] == "stop":
                await self._set_fan_low_and_binary_off(device_id, decision)

            # Update indicator based on decision
            await self._update_automation_status(device_id, decision)

        except Exception as e:
            _LOGGER.error("Automation logic error: %s", e)

    async def _reconcile_startup_states(self) -> None:
        device_ids: set[str] = set()
        for state in self.hass.states.async_all("switch"):
            if not state.entity_id.startswith("switch.dehumidify_"):
                continue
            device_id = self._extract_device_id(state.entity_id)
            if device_id:
                device_ids.add(device_id)

        for device_id in sorted(device_ids):
            if not is_supported_humidity_device(self.hass, device_id):
                _LOGGER.debug(
                    "Skipping startup reconciliation for non-humidity device %s",
                    device_id,
                )
                continue

            try:
                entity_states = await self._get_device_entity_states(device_id)
            except ValueError as err:
                _LOGGER.debug(
                    "Skipping startup reconciliation for %s: %s", device_id, err
                )
                continue

            if not bool(entity_states.get("dehumidify")):
                await self._enforce_switch_off_state(device_id)
                await self._set_indicator_off(device_id)
                continue

            await self._process_automation_logic(device_id, entity_states)

    async def _enforce_switch_off_state(self, device_id: str) -> None:
        success = await self.fan_speed_arbiter.async_clear_demand(
            device_id,
            feature_id=self.feature_id,
        )
        if not success:
            _LOGGER.warning(
                "Failed to enforce OFF balance state for device %s during startup",
                device_id,
            )
        self._dehumidify_active = False

    async def _set_indicator_off(self, device_id: str) -> None:
        """Set indicator to OFF when switch is off or automation stops."""
        try:
            entity_id = f"binary_sensor.dehumidifying_active_{device_id}"
            binary_sensor_entity = (
                self.hass.data.get("ramses_extras", {})
                .get("entities", {})
                .get(entity_id)
            )

            if binary_sensor_entity:
                binary_sensor_entity.set_state(
                    False, self._build_indicator_attributes(device_id, None)
                )
                _LOGGER.debug("Set indicator OFF for device %s", device_id)
            else:
                _LOGGER.warning(
                    "Binary sensor entity %s not found for setting off",
                    entity_id,
                )
        except Exception as e:
            _LOGGER.error("Failed to set indicator off for %s: %s", device_id, e)

    async def _evaluate_humidity_conditions(
        self,
        device_id: str,
        indoor_rh: float,
        indoor_abs: float,
        outdoor_abs: float,
        min_humidity: float,
        max_humidity: float,
        offset: float,
    ) -> dict[str, Any]:
        """Evaluate humidity conditions and make dehumidification decision.

        This implements proper decision logic with relative humidity priority.

        Args:
            device_id: Device identifier
            indoor_rh: Indoor relative humidity
            indoor_abs: Indoor absolute humidity
            outdoor_abs: Outdoor absolute humidity
            min_humidity: Minimum relative humidity threshold
            max_humidity: Maximum relative humidity threshold
            offset: Humidity offset adjustment

        Returns:
            Decision dictionary with action and reasoning
        """
        humidity_diff = outdoor_abs - indoor_abs
        adjusted_diff = humidity_diff + offset
        decision: dict[str, Any] = {
            "action": "stop",  # Default action
            "reasoning": [],
            "values": {
                "indoor_rh": indoor_rh,
                "indoor_abs": indoor_abs,
                "outdoor_abs": outdoor_abs,
                "humidity_diff": humidity_diff,  # outdoor - indoor
                "adjusted_diff": adjusted_diff,
                "min_humidity": min_humidity,
                "max_humidity": max_humidity,
                "offset": offset,
            },
            "confidence": 0.0,
            "control_mode": "idle",
        }

        # PRIORITY 1: High humidity check (relative humidity threshold) - ORIGINAL LOGIC
        if indoor_rh > max_humidity:
            if indoor_abs > outdoor_abs + offset:  # ORIGINAL COMPARISON
                decision["action"] = "dehumidify"
                decision["reasoning"].append(
                    f"High indoor RH: {indoor_rh:.1f}% > {max_humidity:.1f}% "
                    f"with indoor abs ({indoor_abs:.2f}) > outdoor abs "
                    f"({outdoor_abs:.2f}) + offset ({offset:.2f})"
                )
                decision["confidence"] = 0.9
                decision["control_mode"] = "balance"
            else:
                decision["action"] = "stop"
                decision["reasoning"].append(
                    f"High indoor RH: {indoor_rh:.1f}% > {max_humidity:.1f}% "
                    f"but indoor abs ({indoor_abs:.2f}) <= outdoor abs "
                    f"({outdoor_abs:.2f}) + offset ({offset:.2f})"
                )
                decision["confidence"] = 0.6

        # PRIORITY 2: Low humidity check (relative humidity threshold) - ORIGINAL LOGIC
        elif indoor_rh < min_humidity:
            if indoor_abs < outdoor_abs - offset:  # ORIGINAL COMPARISON
                decision["action"] = "dehumidify"  # Bring in humid air
                decision["reasoning"].append(
                    f"Low indoor RH: {indoor_rh:.1f}% < {min_humidity:.1f}% "
                    f"with indoor abs ({indoor_abs:.2f}) < outdoor abs "
                    f"({outdoor_abs:.2f}) - offset ({offset:.2f})"
                )
                decision["confidence"] = 0.8
                decision["control_mode"] = "balance"
            else:
                decision["action"] = "stop"
                decision["reasoning"].append(
                    f"Low indoor RH: {indoor_rh:.1f}% < {min_humidity:.1f}% "
                    f"but indoor abs ({indoor_abs:.2f}) >= outdoor abs "
                    f"({outdoor_abs:.2f}) - offset ({offset:.2f})"
                )
                decision["confidence"] = 0.7

        # PRIORITY 3: In acceptable range - Stay at normal speed
        else:
            decision["action"] = "stop"
            decision["reasoning"].append(
                f"Humidity in acceptable range (RH: {indoor_rh:.1f}%, "
                f"range: {min_humidity:.1f}% - {max_humidity:.1f}%)"
            )
            decision["confidence"] = 1.0

        # Additional checks for extreme absolute values
        if indoor_abs > 15.0:  # High absolute humidity
            decision["confidence"] = min(1.0, decision["confidence"] + 0.1)
            decision["reasoning"].append(
                f"High indoor absolute humidity: {indoor_abs:.1f} g/m³"
            )

        area_sensor_states = self._get_area_sensor_states(device_id)
        self._update_area_sensor_history(device_id, area_sensor_states)

        active_spikes = self._evaluate_active_area_spikes(
            device_id=device_id,
            outdoor_abs=outdoor_abs,
            offset=offset,
            max_humidity=max_humidity,
            area_sensor_states=area_sensor_states,
        )
        detected_spikes = self._detect_area_spikes(
            device_id=device_id,
            indoor_abs=indoor_abs,
            outdoor_abs=outdoor_abs,
            offset=offset,
            max_humidity=max_humidity,
            area_sensor_states=area_sensor_states,
        )
        combined_spikes = self._merge_area_spikes(active_spikes, detected_spikes)

        if combined_spikes:
            self._set_active_area_spikes(device_id, combined_spikes)
            self._schedule_area_spike_recheck(
                device_id,
                min(
                    int(item.get("check_interval_minutes") or 1)
                    for item in combined_spikes
                ),
            )
            primary_spike = combined_spikes[0]
            trigger_labels = [
                str(item.get("label") or item.get("source_id"))
                for item in combined_spikes
            ]
            decision = {
                "action": "dehumidify",
                "reasoning": [
                    (
                        "Area spike active for "
                        f"{', '.join(trigger_labels)}; primary trigger "
                        f"{primary_spike['label']} is "
                        f"{primary_spike['rise_percent']:.1f}% above baseline"
                    )
                ],
                "values": {
                    **decision["values"],
                    "active_area_sensor": primary_spike["source_id"],
                    "active_area_abs": primary_spike["current_abs"],
                    "active_area_baseline_abs": primary_spike["baseline_abs"],
                    "active_area_rise_percent": primary_spike["rise_percent"],
                },
                "confidence": 1.0,
                "control_mode": "spike_boost",
                "active_trigger": primary_spike,
                "active_triggers": combined_spikes,
            }
        else:
            self._clear_active_area_spike(device_id)

        # Record decision
        self._decision_count += 1
        self._decision_history.append(decision)

        # Keep only recent decisions
        if len(self._decision_history) > 100:
            self._decision_history.pop(0)

        # Always log the decision for debugging
        _LOGGER.debug(
            "Decision for device %s: %s (confidence: %.2f, diff: %.2f, "
            "indoor RH: %.1f%%)",
            device_id,
            decision["action"],
            decision["confidence"],
            decision["values"]["adjusted_diff"],
            indoor_rh,
        )
        if decision["reasoning"]:
            reasoning = "; ".join(decision["reasoning"])
            _LOGGER.debug("Reasoning: %s", reasoning)

        return decision

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
        # State change handling - logging removed to reduce log volume

        # Check if feature is still enabled first
        if not self._is_feature_enabled():
            _LOGGER.debug(
                "Feature %s disabled, ignoring state change for %s",
                self.feature_id,
                entity_id,
            )
            return

        # Call parent implementation
        await super()._async_handle_state_change(entity_id, old_state, new_state)

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
            success = await self.fan_speed_arbiter.async_set_demand(
                device_id,
                feature_id=self.feature_id,
                source_id="humidity_control",
                requested_speed="fan_high",
                priority=20,
                reason="humidity_dehumidify",
                metadata=decision,
            )
            if success:
                self._dehumidify_active = True
                switch_success = await self.services.async_activate_dehumidification(
                    device_id
                )
                if not switch_success:
                    self._dehumidify_active = False
                    rollback = await self.fan_speed_arbiter.async_clear_demand(
                        device_id,
                        feature_id=self.feature_id,
                        source_id="humidity_control",
                    )
                    if not rollback:
                        _LOGGER.warning(
                            "Failed to roll back fan state after switch activation "
                            "failure for device %s",
                            device_id,
                        )
                    return
            else:
                _LOGGER.warning(
                    "Failed to set fan speed to high for device %s",
                    device_id,
                )
                await self.services.async_deactivate_dehumidification(device_id)
                self._dehumidify_active = False

            self._active_cycles += 1

            # Log activation
            reasoning = "; ".join(decision["reasoning"])
            _LOGGER.info("Dehumidification activated: %s", reasoning)

        except Exception as e:
            _LOGGER.error("Failed to activate dehumidification: %s", e)

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
            success = await self.fan_speed_arbiter.async_clear_demand(
                device_id,
                feature_id=self.feature_id,
                source_id="humidity_control",
            )
            if not success:
                _LOGGER.warning(
                    "Failed to set fan to auto mode for device %s",
                    device_id,
                )
            self._dehumidify_active = False
            await self.services.async_deactivate_dehumidification(device_id)

            reasoning = "; ".join(decision["reasoning"])
            _LOGGER.info("Dehumidification deactivated: %s", reasoning)

        except Exception as e:
            _LOGGER.error("Failed to deactivate dehumidification: %s", e)

    async def _set_fan_low_and_binary_off(
        self, device_id: str, decision: dict[str, Any]
    ) -> None:
        """Set fan to low speed and turn off binary sensor (don't touch switch).

        Args:
            device_id: Device identifier
            decision: Decision information
        """
        try:
            success = await self.fan_speed_arbiter.async_set_demand(
                device_id,
                feature_id=self.feature_id,
                source_id="humidity_control",
                requested_speed="fan_low",
                priority=5,
                reason="humidity_balance_idle",
                metadata=decision,
            )
            if not success:
                _LOGGER.warning(
                    "Failed to set fan to low mode for device %s",
                    device_id,
                )

            self._dehumidify_active = False
            if decision.get("control_mode") != "spike_boost":
                self._clear_active_area_spike(device_id)

            reasoning = "; ".join(decision["reasoning"])
            _LOGGER.info(
                "Fan set to LOW mode (humidity balancing stopped): %s",
                reasoning,
            )

        except Exception as e:
            _LOGGER.error("Failed to set fan to auto mode: %s", e)

    async def _stop_dehumidification_without_switch_change(
        self, device_id: str
    ) -> None:
        """Stop dehumidification without changing switch state.

        Args:
            device_id: Device identifier
        """
        if not self._dehumidify_active:
            return  # Already inactive

        try:
            success = await self.fan_speed_arbiter.async_clear_demand(
                device_id,
                feature_id=self.feature_id,
                source_id="humidity_control",
            )
            if not success:
                _LOGGER.warning(
                    "Failed to set fan to auto mode for device %s",
                    device_id,
                )

            self._dehumidify_active = False

            _LOGGER.info(
                "Humidity balancing stopped for %s (switch already off, "
                "respecting user choice)",
                device_id,
            )

        except Exception as e:
            _LOGGER.error("Failed to stop dehumidification: %s", e)

    async def _update_automation_status(
        self, device_id: str, decision: dict[str, Any]
    ) -> None:
        """Update automation status entity.

        Args:
            device_id: Device identifier
            decision: Decision information
        """
        # Update binary sensor directly via stored entity reference
        try:
            is_active = decision["action"] == "dehumidify"
            entity_id = f"binary_sensor.dehumidifying_active_{device_id}"

            # Get entity from stored references
            binary_sensor_entity = (
                self.hass.data.get("ramses_extras", {})
                .get("entities", {})
                .get(entity_id)
            )

            if binary_sensor_entity:
                binary_sensor_entity.set_state(
                    is_active,
                    self._build_indicator_attributes(device_id, decision),
                )
                _LOGGER.debug(
                    "Updated binary sensor %s: %s",
                    entity_id,
                    "on" if is_active else "off",
                )
            else:
                _LOGGER.warning(
                    "Binary sensor entity %s not found in stored entities",
                    entity_id,
                )
        except Exception as e:
            _LOGGER.error("Failed to update binary sensor for %s: %s", device_id, e)

    def _get_area_sensor_states(self, device_id: str) -> list[dict[str, Any]]:
        sensor_ctx = self._latest_sensor_control_context.get(device_id) or {}
        area_sensors = sensor_ctx.get("area_sensors") or []
        if not isinstance(area_sensors, list):
            return []

        result: list[dict[str, Any]] = []
        for item in area_sensors:
            if not isinstance(item, dict):
                continue
            temp_entity = str(item.get("temperature_entity") or "").strip()
            humidity_entity = str(item.get("humidity_entity") or "").strip()
            if not temp_entity or not humidity_entity:
                continue

            temp_state = self.hass.states.get(temp_entity)
            humidity_state = self.hass.states.get(humidity_entity)
            current_abs = self._calculate_absolute_humidity_from_states(
                temp_state, humidity_state
            )
            current_rh: float | None = None
            if humidity_state and humidity_state.state not in [
                "unavailable",
                "unknown",
                "uninitialized",
            ]:
                try:
                    current_rh = float(humidity_state.state)
                except ValueError:
                    current_rh = None
            result.append(
                {
                    **item,
                    "current_abs": current_abs,
                    "current_rh": current_rh,
                }
            )

        return result

    def _calculate_absolute_humidity_from_states(
        self, temp_state: State | None, humidity_state: State | None
    ) -> float | None:
        if not temp_state or not humidity_state:
            return None
        if temp_state.state in ["unavailable", "unknown", "uninitialized"]:
            return None
        if humidity_state.state in ["unavailable", "unknown", "uninitialized"]:
            return None

        try:
            temp = float(temp_state.state)
            humidity = float(humidity_state.state)
        except ValueError:
            return None

        if not (0 <= humidity <= 100):
            return None

        from custom_components.ramses_extras.framework.helpers.common import (
            calculate_absolute_humidity,
        )

        result = calculate_absolute_humidity(temp, humidity)
        return float(result) if result is not None else None

    def _update_area_sensor_history(
        self, device_id: str, area_sensor_states: list[dict[str, Any]]
    ) -> None:
        device_history = self._area_history.setdefault(device_id, {})
        now = time.time()
        max_window_seconds = max(
            [
                int(item.get("spike_window_minutes") or 1) * 60
                for item in area_sensor_states
                if item.get("spike_window_minutes") is not None
            ]
            or [60]
        )
        trim_before = now - max_window_seconds - 60

        for item in area_sensor_states:
            source_id = str(item.get("source_id") or "").strip()
            current_abs = item.get("current_abs")
            if not source_id or current_abs is None:
                continue
            source_history = device_history.setdefault(source_id, [])
            source_history.append({"ts": now, "abs": float(current_abs)})
            device_history[source_id] = [
                entry for entry in source_history if entry["ts"] >= trim_before
            ]

    def _detect_area_spikes(
        self,
        device_id: str,
        indoor_abs: float,
        outdoor_abs: float,
        offset: float,
        max_humidity: float,
        area_sensor_states: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        spikes: list[dict[str, Any]] = []
        device_history = self._area_history.get(device_id, {})

        for item in area_sensor_states:
            source_id = str(item.get("source_id") or "").strip()
            if not source_id or not bool(item.get("enabled", True)):
                continue

            current_abs = item.get("current_abs")
            if current_abs is None:
                continue
            history = device_history.get(source_id, [])
            if not history:
                continue

            window_minutes = int(item.get("spike_window_minutes") or 1)
            threshold_percent = float(item.get("spike_rise_percent") or 0.0)
            window_start = time.time() - (window_minutes * 60)
            window_values = [
                entry["abs"] for entry in history if entry["ts"] >= window_start
            ]
            if not window_values:
                continue

            baseline_abs = min(window_values)
            if baseline_abs <= 0:
                continue

            rise_percent = ((float(current_abs) - baseline_abs) / baseline_abs) * 100.0
            if rise_percent < threshold_percent:
                continue
            if float(current_abs) <= max(indoor_abs, outdoor_abs + offset):
                continue
            current_rh = item.get("current_rh")
            if current_rh is None:
                _LOGGER.debug(
                    "Ignoring area spike candidate for %s/%s: missing current RH",
                    device_id,
                    source_id,
                )
                continue
            if float(current_rh) <= max_humidity:
                _LOGGER.debug(
                    (
                        "Ignoring area spike candidate for %s/%s: RH %.1f%% "
                        "<= max %.1f%%"
                    ),
                    device_id,
                    source_id,
                    float(current_rh),
                    max_humidity,
                )
                continue

            spikes.append(
                {
                    "source_id": source_id,
                    "label": str(item.get("label") or source_id),
                    "baseline_abs": baseline_abs,
                    "current_abs": float(current_abs),
                    "current_rh": float(current_rh),
                    "rise_percent": rise_percent,
                    "spike_window_minutes": window_minutes,
                    "check_interval_minutes": int(
                        item.get("check_interval_minutes") or 1
                    ),
                    "temperature_entity": item.get("temperature_entity"),
                    "humidity_entity": item.get("humidity_entity"),
                    "zone_id": item.get("zone_id"),
                    "triggered_at": time.time(),
                }
            )

        return sorted(
            spikes,
            key=lambda item: (
                float(item.get("rise_percent") or 0.0),
                float(item.get("current_abs") or 0.0),
            ),
            reverse=True,
        )

    def _detect_area_spike(
        self,
        device_id: str,
        indoor_abs: float,
        outdoor_abs: float,
        offset: float,
        area_sensor_states: list[dict[str, Any]],
        max_humidity: float = 60.0,
    ) -> dict[str, Any] | None:
        spikes = self._detect_area_spikes(
            device_id=device_id,
            indoor_abs=indoor_abs,
            outdoor_abs=outdoor_abs,
            offset=offset,
            max_humidity=max_humidity,
            area_sensor_states=area_sensor_states,
        )
        return spikes[0] if spikes else None

    def _get_active_area_spikes(self, device_id: str) -> list[dict[str, Any]]:
        active_spikes = self._active_area_spikes.get(device_id)
        if isinstance(active_spikes, list):
            return [item for item in active_spikes if isinstance(item, dict)]
        if isinstance(active_spikes, dict):
            return [active_spikes]
        return []

    def _format_active_trigger_label(self, trigger: dict[str, Any]) -> str:
        label = str(trigger.get("label") or trigger.get("source_id") or "Unknown")
        current_rh = trigger.get("current_rh")
        if current_rh is None:
            return label
        try:
            rh_value = float(current_rh)
        except (TypeError, ValueError):
            return label
        return f"{label} ({rh_value:.0f}%)"

    def _set_active_area_spikes(
        self, device_id: str, active_spikes: list[dict[str, Any]]
    ) -> None:
        if active_spikes:
            self._active_area_spikes[device_id] = active_spikes
        else:
            self._active_area_spikes.pop(device_id, None)

    def _merge_area_spikes(
        self,
        active_spikes: list[dict[str, Any]],
        detected_spikes: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        merged: dict[str, dict[str, Any]] = {}
        for item in [*active_spikes, *detected_spikes]:
            source_id = str(item.get("source_id") or "").strip()
            if not source_id:
                continue
            existing = merged.get(source_id)
            if existing is None or (
                float(item.get("rise_percent") or 0.0)
                >= float(existing.get("rise_percent") or 0.0)
            ):
                merged[source_id] = item

        return sorted(
            merged.values(),
            key=lambda item: (
                float(item.get("rise_percent") or 0.0),
                float(item.get("current_abs") or 0.0),
            ),
            reverse=True,
        )

    def _evaluate_active_area_spikes(
        self,
        device_id: str,
        outdoor_abs: float,
        offset: float,
        max_humidity: float,
        area_sensor_states: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        retained: list[dict[str, Any]] = []
        active_spikes = self._get_active_area_spikes(device_id)
        if not active_spikes:
            return retained

        for active_spike in active_spikes:
            source_id = active_spike.get("source_id")
            matching_sensor = next(
                (
                    item
                    for item in area_sensor_states
                    if item.get("source_id") == source_id
                ),
                None,
            )
            if not matching_sensor or matching_sensor.get("current_abs") is None:
                continue

            current_abs = float(matching_sensor["current_abs"])
            current_rh = matching_sensor.get("current_rh")
            if current_abs <= outdoor_abs + offset:
                continue
            if current_rh is not None and float(current_rh) <= max_humidity:
                _LOGGER.debug(
                    "Clearing active area spike for %s/%s: RH %.1f%% <= max %.1f%%",
                    device_id,
                    source_id,
                    float(current_rh),
                    max_humidity,
                )
                continue

            updated_spike = active_spike.copy()
            updated_spike["current_abs"] = current_abs
            updated_spike["current_rh"] = current_rh
            retained.append(updated_spike)

        return retained

    def _evaluate_active_area_spike(
        self,
        device_id: str,
        indoor_abs: float,
        outdoor_abs: float,
        offset: float,
        area_sensor_states: list[dict[str, Any]],
        max_humidity: float = 60.0,
    ) -> dict[str, Any] | None:
        retained = self._evaluate_active_area_spikes(
            device_id=device_id,
            outdoor_abs=outdoor_abs,
            offset=offset,
            max_humidity=max_humidity,
            area_sensor_states=area_sensor_states,
        )
        if not retained:
            return None

        primary_spike = retained[0]
        current_abs = float(primary_spike.get("current_abs") or 0.0)
        current_rh = primary_spike.get("current_rh")
        return {
            "action": "dehumidify",
            "reasoning": [
                "Active area spikes remain above recovery target: "
                + ", ".join(
                    str(item.get("label") or item.get("source_id")) for item in retained
                )
            ],
            "values": {
                "indoor_abs": indoor_abs,
                "outdoor_abs": outdoor_abs,
                "offset": offset,
                "active_area_sensor": primary_spike["source_id"],
                "active_area_abs": current_abs,
                "active_area_baseline_abs": float(
                    primary_spike.get("baseline_abs") or 0.0
                ),
                "active_area_relative_humidity": current_rh,
            },
            "confidence": 0.95,
            "control_mode": "spike_boost",
            "active_trigger": primary_spike.copy(),
            "active_triggers": [item.copy() for item in retained],
        }

    def _schedule_area_spike_recheck(
        self, device_id: str, check_interval_minutes: int
    ) -> None:
        self._cancel_area_spike_recheck(device_id)
        interval_minutes = max(1, check_interval_minutes)

        def _schedule_recheck(_: datetime) -> None:
            def _create_task() -> None:
                self.hass.async_create_task(self._async_recheck_area_spike(device_id))

            self.hass.loop.call_soon_threadsafe(_create_task)

        self._area_spike_check_handles[device_id] = async_track_time_interval(
            self.hass,
            _schedule_recheck,
            timedelta(minutes=interval_minutes),
        )

    def _cancel_area_spike_recheck(self, device_id: str) -> None:
        handle = self._area_spike_check_handles.pop(device_id, None)
        if handle:
            handle()

    async def _async_recheck_area_spike(self, device_id: str) -> None:
        if not self._automation_active or not self._is_feature_enabled():
            return

        try:
            entity_states = await self._get_device_entity_states(device_id)
        except ValueError as err:
            _LOGGER.debug("Skipping area spike recheck for %s: %s", device_id, err)
            return

        await self._process_automation_logic(device_id, entity_states)

    def _clear_active_area_spike(self, device_id: str) -> None:
        self._set_active_area_spikes(device_id, [])
        self._cancel_area_spike_recheck(device_id)

    def _build_indicator_attributes(
        self, device_id: str, decision: dict[str, Any] | None
    ) -> dict[str, Any]:
        attrs: dict[str, Any] = {
            "control_mode": "idle",
            "active_trigger_source_id": None,
            "active_trigger_label": None,
            "active_trigger_source_ids": [],
            "active_trigger_labels": [],
            "active_trigger_labels_text": None,
            "active_trigger_abs_humidity": None,
            "active_trigger_baseline_abs_humidity": None,
            "active_trigger_rise_percent": None,
            "next_check_interval_minutes": None,
        }
        if not decision:
            return attrs

        attrs["control_mode"] = decision.get("control_mode", "idle")
        active_trigger = decision.get("active_trigger")
        active_triggers_raw = decision.get("active_triggers")
        active_triggers = (
            [item for item in active_triggers_raw if isinstance(item, dict)]
            if isinstance(active_triggers_raw, list)
            else []
        )
        if isinstance(active_trigger, dict):
            attrs["active_trigger_source_id"] = active_trigger.get("source_id")
            attrs["active_trigger_label"] = active_trigger.get("label")
            attrs["active_trigger_abs_humidity"] = active_trigger.get("current_abs")
            attrs["active_trigger_baseline_abs_humidity"] = active_trigger.get(
                "baseline_abs"
            )
            attrs["active_trigger_rise_percent"] = active_trigger.get("rise_percent")
            attrs["next_check_interval_minutes"] = active_trigger.get(
                "check_interval_minutes"
            )
        elif self._get_active_area_spikes(device_id):
            active_spike = self._get_active_area_spikes(device_id)[0]
            attrs["control_mode"] = "spike_boost"
            attrs["active_trigger_source_id"] = active_spike.get("source_id")
            attrs["active_trigger_label"] = active_spike.get("label")
            attrs["active_trigger_abs_humidity"] = active_spike.get("current_abs")
            attrs["active_trigger_baseline_abs_humidity"] = active_spike.get(
                "baseline_abs"
            )
            attrs["active_trigger_rise_percent"] = active_spike.get("rise_percent")
            attrs["next_check_interval_minutes"] = active_spike.get(
                "check_interval_minutes"
            )

        if not active_triggers:
            active_triggers = self._get_active_area_spikes(device_id)

        if active_triggers:
            attrs["active_trigger_source_ids"] = [
                item.get("source_id")
                for item in active_triggers
                if item.get("source_id")
            ]
            attrs["active_trigger_labels"] = [
                self._format_active_trigger_label(item)
                for item in active_triggers
                if item.get("label") or item.get("source_id")
            ]
            attrs["active_trigger_labels_text"] = ", ".join(
                str(item) for item in attrs["active_trigger_labels"]
            )
            attrs["next_check_interval_minutes"] = min(
                int(item.get("check_interval_minutes") or 1) for item in active_triggers
            )
        return attrs

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
            _LOGGER.error("Failed to set min humidity: %s", e)
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
            _LOGGER.error("Failed to set max humidity: %s", e)
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
            _LOGGER.error("Failed to set offset: %s", e)
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
            "paused_for_co2": self._paused_for_co2,
            "fan_arbiter": self.fan_speed_arbiter.get_debug_state(),
        }

    def set_co2_manager(self, co2_manager: Any) -> None:
        """Set reference to CO2 automation manager for priority coordination.

        Args:
            co2_manager: CO2AutomationManager instance
        """
        self.co2_manager = co2_manager
        _LOGGER.debug("CO2 manager reference set for priority coordination")

    async def pause_for_co2(self) -> None:
        """Record that CO2 became active while humidity stays arbiter-managed."""
        self._paused_for_co2 = False
        _LOGGER.debug("CO2 control active - humidity remains arbiter-managed")

    async def resume_from_co2(self) -> None:
        """Re-evaluate humidity control after CO2 control changed state."""
        self._paused_for_co2 = False
        if self._automation_active and self._is_feature_enabled():
            await self._reconcile_startup_states()

    def check_priority(self) -> bool:
        """Check if humidity control has priority to operate.

        Returns:
            True if humidity control can operate, False if paused for CO2
        """
        return True


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
