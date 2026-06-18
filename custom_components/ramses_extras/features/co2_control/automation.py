"""CO2 Control Automation.

This module contains the automation logic for CO2-based ventilation control.
CO2 control has priority over humidity control in the ventilation system.
"""

import asyncio
import logging
from collections.abc import Mapping
from datetime import datetime, timedelta
from typing import Any, cast

from homeassistant.core import Event, HomeAssistant, State
from homeassistant.helpers.event import async_track_state_change_event

from custom_components.ramses_extras.const import DOMAIN
from custom_components.ramses_extras.framework.base_classes.base_automation import (
    ExtrasBaseAutomation,
)
from custom_components.ramses_extras.framework.helpers.config.migration import (
    migrate_feature_section,
)
from custom_components.ramses_extras.framework.helpers.config.model import (
    SENSOR_CONTROL_AREA_SENSORS_KEY,
    get_sensor_control_device_section,
)
from custom_components.ramses_extras.framework.helpers.fan_speed_arbiter import (
    get_fan_speed_arbiter,
)
from custom_components.ramses_extras.framework.helpers.ramses_commands import (
    RamsesCommands,
)
from custom_components.ramses_extras.framework.helpers.zone_demand import (
    DemandSource,
    get_zone_demand_registry,
)

from .config import CO2Config
from .const import FEATURE_DEFINITION
from .zone_manager import CO2ZoneManager

# Feature ID used by this module
FEATURE_SENSOR_CONTROL = "sensor_control"

_LOGGER = logging.getLogger(__name__)


class CO2AutomationManager(ExtrasBaseAutomation):
    """Manages CO2 control automation logic.

    This class implements CO2-based ventilation control with priority over
    humidity control. It monitors multiple CO2 sensors across zones and
    triggers ventilation when thresholds are exceeded.
    """

    def __init__(self, hass: HomeAssistant, config_entry: Any) -> None:
        """Initialize CO2 automation manager.

        :param hass: Home Assistant instance
        :param config_entry: Configuration entry
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
        self.fan_speed_arbiter = get_fan_speed_arbiter(hass)

        # CO2-specific state tracking
        self._co2_active = False
        self._automation_active = False
        self._zone_managers: dict[str, CO2ZoneManager] = {}
        self._state_change_listeners: list[Any] = []
        self._source_listener_entities: dict[str, set[str]] = {}
        self._latest_sensor_control_context: dict[str, dict[str, Any] | None] = {}
        self._source_trigger_states: dict[str, dict[str, bool]] = {}
        self._trigger_meta: dict[str, dict[str, Any]] = {}

        self._zone_demand_registry = get_zone_demand_registry(hass)
        self._co2_demand_zones: dict[str, set[str]] = {}

        # Reference to humidity automation for priority coordination
        self.humidity_manager = None

        # Runtime tracking
        self._activation_time: datetime | None = None
        self._last_fan_speed: int | None = None

        _LOGGER.info("CO2 Control automation initialized")

    def set_humidity_manager(self, humidity_manager: Any) -> None:
        """Set reference to humidity automation manager for priority coordination.

        :param humidity_manager: HumidityAutomationManager instance
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

    async def start(self) -> None:
        """Start CO2 control automation."""
        _LOGGER.info("Starting CO2 control automation")

        if not self._is_feature_enabled():
            _LOGGER.info(
                "CO2 control feature is not enabled, skipping automation startup"
            )
            return

        await self.config.async_load()
        self._automation_active = True

        self.hass.data.setdefault(DOMAIN, {})["co2_automation"] = self

        await self.async_setup()
        await super().start()

        _LOGGER.info("CO2 control automation started")

    async def stop(self) -> None:
        """Stop CO2 control automation."""
        self._automation_active = False

        for listener in self._state_change_listeners:
            listener()
        self._state_change_listeners.clear()
        self._source_listener_entities.clear()

        for device_id in list(self._co2_demand_zones):
            self._sync_zone_demands(device_id, [])

        # Clear fan speed demands for all devices
        devices_with_demands = self.fan_speed_arbiter.get_all_devices_with_demands()
        for device_id in devices_with_demands:
            # Check if this device has CO2 control demands
            demands = self.fan_speed_arbiter.get_active_demands(device_id)
            co2_demands = [d for d in demands if d.feature_id == self.feature_id]
            if co2_demands:
                _LOGGER.debug(
                    "Clearing CO2 control fan demand for device %s",
                    device_id,
                )
                await self.fan_speed_arbiter.async_clear_demand(
                    device_id,
                    feature_id=self.feature_id,
                )

        await super().stop()

    async def _on_homeassistant_started(self, event: Event | None) -> None:
        """Initialize listeners then evaluate current CO2 states once."""
        await super()._on_homeassistant_started(event)
        if not self._automation_active or not self._is_feature_enabled():
            return

        for device_id in self._iter_candidate_device_ids():
            try:
                await self._evaluate_co2_control(device_id)
            except Exception as err:
                _LOGGER.error(
                    "Startup CO2 evaluation failed for %s: %s", device_id, err
                )

    def is_automation_active(self) -> bool:
        """Return whether CO2 automation manager is active."""
        return self._automation_active

    def _iter_candidate_device_ids(self) -> list[str]:
        """Return candidate device IDs for startup CO2 evaluation."""
        ids: set[str] = set(self._zone_managers.keys())

        devices = self.hass.data.get(DOMAIN, {}).get("devices", [])
        for device in devices:
            if isinstance(device, dict):
                device_id = str(device.get("device_id") or "").strip()
            else:
                device_id = str(device)
            if device_id:
                ids.add(device_id)

        return sorted(ids)

    def _is_automation_enabled_for_device(self, device_id: str) -> bool:
        """Return whether CO2 automation should run for this device."""
        if self.config.automation_enabled:
            return True

        switch_entity = f"switch.co2_control_{device_id.replace(':', '_').lower()}"
        switch_state = self.hass.states.get(switch_entity)
        return bool(switch_state and switch_state.state == "on")

    async def _get_device_entity_states(
        self, device_id: str
    ) -> dict[str, float | bool]:
        """Get input entity states needed for change-processing.

        CO2 automation evaluates triggers via direct source lookups, so diagnostic
        output entities like `sensor.co2_zone_status_*` must not block processing
        when they are temporarily unknown/unavailable.
        """
        from custom_components.ramses_extras.framework.helpers.entity.core import (
            get_feature_entity_mappings,
        )

        states: dict[str, float | bool] = {}
        state_mappings = await get_feature_entity_mappings(
            self.feature_id,
            device_id,
            self.hass,
        )

        input_state_names = {
            "co2_control",
            "co2_threshold",
            "co2_activation_hysteresis",
            "co2_deactivation_hysteresis",
        }

        for state_name, entity_id in state_mappings.items():
            if state_name not in input_state_names:
                continue

            state = self.hass.states.get(entity_id)
            if not state or state.state in {"unavailable", "unknown", "uninitialized"}:
                continue

            entity_type = self._extract_entity_type_from_id(entity_id)
            try:
                states[state_name] = self._convert_entity_state(
                    entity_type,
                    state.state,
                )
            except ValueError:
                continue

        return states

    async def _async_handle_state_change(
        self, entity_id: str, old_state: State | None, new_state: State | None
    ) -> None:
        """Handle state changes with automation-specific processing.

        This method provides the async processing logic that derived classes
        can extend or override for feature-specific needs.

        :param entity_id: Entity that changed state
        :param old_state: Previous state (if any)
        :param new_state: New state
        """
        # Check if feature is still enabled first
        if not self._is_feature_enabled():
            _LOGGER.debug(
                "Feature %s disabled, ignoring state change for %s",
                self.feature_id,
                entity_id,
            )
            return

        # Handle CO2 switch changes immediately (bypass validation cooldown)
        if "switch.co2_control_" in entity_id:
            device_id = self._extract_device_id(entity_id)
            if device_id:
                _LOGGER.debug(
                    "CO2 switch changed for %s, processing immediately",
                    device_id,
                )
                try:
                    entity_states = await self._get_device_entity_states(device_id)
                    await self._process_automation_logic(device_id, entity_states)
                except Exception as e:
                    _LOGGER.error(
                        "Error processing CO2 switch change for %s: %s",
                        device_id,
                        e,
                    )
                return

        # Call parent implementation for other entities
        await super()._async_handle_state_change(entity_id, old_state, new_state)

    async def _process_automation_logic(
        self, device_id: str, entity_states: Mapping[str, float | bool]
    ) -> None:
        """Process CO2 logic for changed entities."""
        if not self._automation_active or not self._is_feature_enabled():
            return

        if self.fan_speed_arbiter.is_manual_override_active(device_id):
            _LOGGER.debug(
                "Manual override active - skipping CO2 control logic for %s",
                device_id,
            )
            return

        if not self.fan_speed_arbiter.is_extras_control_enabled(device_id):
            _LOGGER.debug(
                "Extras control disabled - skipping CO2 control logic for %s",
                device_id,
            )
            return

        # Check transport availability before processing
        if not self.is_device_transport_available(device_id):
            _LOGGER.debug(
                "Transport unavailable - skipping CO2 control logic for %s",
                device_id,
            )
            return

        _ = entity_states
        await self._evaluate_co2_control(device_id)

    async def async_setup(self) -> bool:
        """Set up CO2 automation.

        :return: True if setup successful
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
        domain_data = self.hass.data.get(DOMAIN, {})
        devices = domain_data.get("devices", [])

        for device in devices:
            if isinstance(device, dict):
                device_id = str(device.get("device_id") or "").strip()
            else:
                device_id = str(device)
            if not device_id:
                continue

            co2_config = self.config_entry.options.get("co2_control", {})
            device_co2_config = co2_config.get(device_id, {})

            if device_co2_config.get("enabled", False):
                zone_manager = CO2ZoneManager(self.hass, device_id, device_co2_config)
                self._zone_managers[device_id] = zone_manager
                _LOGGER.info("Created zone manager for device %s", device_id)

    async def _setup_sensor_listeners(self) -> None:
        """Set up state change listeners for all CO2 sensors."""
        setup_source_devices: set[str] = set()

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

            await self._setup_source_listeners_for_device(device_id)
            setup_source_devices.add(device_id)

        domain_devices = self.hass.data.get(DOMAIN, {}).get("devices", [])
        for device in domain_devices:
            if isinstance(device, dict):
                device_id = str(device.get("device_id") or "").strip()
            else:
                device_id = str(device)

            if not device_id or device_id in setup_source_devices:
                continue

            await self._setup_source_listeners_for_device(device_id)

    async def _setup_source_listeners_for_device(self, device_id: str) -> None:
        """Set up listeners for area/internal CO2 sources from sensor_control."""
        sensor_ctx = await self._get_sensor_control_context(device_id)
        self._latest_sensor_control_context[device_id] = sensor_ctx
        await self._register_source_listeners(device_id, sensor_ctx)

    async def _register_source_listeners(
        self,
        device_id: str,
        sensor_ctx: dict[str, Any] | None,
    ) -> None:
        """Register listeners for source entities discovered from sensor control."""
        if not sensor_ctx:
            return

        entities: set[str] = set()
        mappings = cast(dict[str, str], sensor_ctx.get("mappings") or {})
        internal_entity = str(mappings.get("co2") or "").strip()
        if internal_entity:
            entities.add(internal_entity)

        area_sensors = cast(
            list[dict[str, Any]],
            (sensor_ctx or {}).get("area_sensors") or [],
        )
        for area_sensor in area_sensors:
            if not bool(area_sensor.get("area_co2_enabled", False)):
                continue
            co2_entity = str(area_sensor.get("co2_entity") or "").strip()
            if co2_entity:
                entities.add(co2_entity)

            threshold_entity = str(
                area_sensor.get("co2_threshold_entity") or ""
            ).strip()
            if threshold_entity:
                entities.add(threshold_entity)

        if not entities:
            return

        existing = self._source_listener_entities.setdefault(device_id, set())
        new_entities = entities - existing
        if not new_entities:
            return

        listener = async_track_state_change_event(
            self.hass,
            list(new_entities),
            self._handle_co2_sensor_change,
        )
        self._state_change_listeners.append(listener)
        existing.update(new_entities)

    async def _handle_co2_sensor_change(self, event: Event) -> None:
        """Handle CO2 sensor state change.

        :param event: State change event
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

        for device_id, sensor_ctx in self._latest_sensor_control_context.items():
            if self._entity_in_sensor_context(entity_id, sensor_ctx):
                await self._evaluate_co2_control(device_id)
                return

    def _entity_in_sensor_context(
        self, entity_id: str | None, sensor_ctx: dict[str, Any] | None
    ) -> bool:
        if not entity_id or not sensor_ctx:
            return False

        mappings = cast(dict[str, str], sensor_ctx.get("mappings") or {})
        if entity_id == str(mappings.get("co2") or ""):
            return True

        area_sensors = cast(
            list[dict[str, Any]],
            (sensor_ctx or {}).get("area_sensors") or [],
        )
        for area_sensor in area_sensors:
            if not bool(area_sensor.get("area_co2_enabled", False)):
                continue
            if entity_id == str(area_sensor.get("co2_entity") or ""):
                return True

        return False

    async def _get_sensor_control_context(
        self, device_id: str
    ) -> dict[str, Any] | None:
        """Get merged mappings + area_sensors from sensor_control resolver."""
        try:
            if not self._is_sensor_control_enabled():
                return None

            from custom_components.ramses_extras.features.sensor_control import (
                resolver as sensor_control_resolver,
            )

            device_type = self._get_device_type_for_sensor_control(device_id)
            if not device_type:
                return None

            resolver = sensor_control_resolver.SensorControlResolver(self.hass)
            sensor_result = await resolver.resolve_entity_mappings(
                device_id, device_type
            )

            resolved_area_sensors = cast(
                list[dict[str, Any]],
                (sensor_result or {}).get("area_sensors") or [],
            )
            if not resolved_area_sensors:
                resolved_area_sensors = self._get_raw_area_sensors_from_options(
                    device_id
                )

            return {
                "mappings": (sensor_result or {}).get("mappings") or {},
                "sources": (sensor_result or {}).get("sources") or {},
                "raw_internal": (sensor_result or {}).get("raw_internal") or {},
                "area_sensors": resolved_area_sensors,
            }
        except Exception as err:
            _LOGGER.error(
                "Error getting sensor_control context for %s: %s", device_id, err
            )
            return None

    def _get_raw_area_sensors_from_options(
        self,
        device_id: str,
    ) -> list[dict[str, Any]]:
        """Read raw area sensor config directly from options as a fallback."""
        # Strip device type suffix (e.g., " (HVC)") before lookup
        clean_device_id = device_id
        if device_id and " (" in device_id:
            clean_device_id = device_id.split(" (")[0]

        sensor_control = self._get_sensor_control_config(clean_device_id)
        if not sensor_control:
            return []

        area_sensors = get_sensor_control_device_section(
            sensor_control,
            clean_device_id,
        ).get(SENSOR_CONTROL_AREA_SENSORS_KEY)
        if not isinstance(area_sensors, list):
            return []

        return [item for item in area_sensors if isinstance(item, dict)]

    def _get_sensor_control_config(
        self,
        device_id: str | None = None,
    ) -> dict[str, Any]:
        """Get sensor_control config from the most relevant config entry."""
        entries: list[Any] = [self.config_entry]

        domain_data = self.hass.data.get(DOMAIN, {})
        hass_config_entry = domain_data.get("config_entry")
        if hass_config_entry is not None:
            entries.append(hass_config_entry)

        config_entries = getattr(self.hass, "config_entries", None)
        async_entries = getattr(config_entries, "async_entries", None)
        if callable(async_entries):
            resolved_entries = async_entries(DOMAIN)
            if isinstance(resolved_entries, list):
                entries.extend(resolved_entries)

        normalized_keys: set[str] = set()
        if device_id:
            normalized_keys = {
                str(device_id),
                str(device_id).replace(":", "_"),
                str(device_id).replace("_", ":"),
            }

        fallback_config: dict[str, Any] | None = None
        seen_entries: set[int] = set()

        for entry in entries:
            if entry is None:
                continue

            entry_marker = id(entry)
            if entry_marker in seen_entries:
                continue
            seen_entries.add(entry_marker)

            options = getattr(entry, "options", {}) or {}
            data = getattr(entry, "data", {}) or {}
            sensor_control = self._extract_sensor_control_section(
                options
            ) or self._extract_sensor_control_section(data)
            if not isinstance(sensor_control, dict):
                continue

            sensor_control = migrate_feature_section(
                FEATURE_SENSOR_CONTROL,
                sensor_control,
            )

            if fallback_config is None:
                fallback_config = sensor_control

            if not normalized_keys:
                return sensor_control

            if device_id and get_sensor_control_device_section(
                sensor_control, device_id
            ):
                return sensor_control

        return fallback_config or {}

    def _extract_sensor_control_section(
        self,
        payload: dict[str, Any],
    ) -> dict[str, Any] | None:
        sensor_control = payload.get("sensor_control")
        if isinstance(sensor_control, dict):
            return sensor_control

        root_section = payload.get("ramses_extras")
        if not isinstance(root_section, dict):
            return None

        features = root_section.get("features")
        if not isinstance(features, dict):
            return None

        sensor_control = features.get("sensor_control")
        return sensor_control if isinstance(sensor_control, dict) else None

    def _get_device_type_for_sensor_control(self, device_id: str) -> str | None:
        devices = self.hass.data.get(DOMAIN, {}).get("devices", [])

        # Strip device type suffix for consistent lookup
        clean_device_id = device_id
        if device_id and " (" in device_id:
            clean_device_id = device_id.split(" (")[0]

        target_colon = str(clean_device_id).replace("_", ":")

        for device in devices:
            if isinstance(device, dict):
                raw_id = device.get("device_id")
                device_type = device.get("type")
            else:
                raw_id = device
                device_type = getattr(device, "type", None)

            if raw_id is None:
                continue

            # Also normalize the stored device ID for comparison
            stored_id = str(raw_id)
            if " (" in stored_id:
                stored_id = stored_id.split(" (")[0]

            if stored_id.replace("_", ":") == target_colon:
                return str(device_type) if device_type else None

        return None

    def _is_sensor_control_enabled(self) -> bool:
        """Check if sensor_control feature is enabled."""
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

    async def _evaluate_co2_control(self, device_id: str) -> None:
        """Evaluate CO2 control and adjust fan speed if needed.

        :param device_id: Device identifier (may include device type suffix)
        """
        # Normalize device_id by stripping device type suffix
        clean_device_id = device_id
        if device_id and " (" in device_id:
            clean_device_id = device_id.split(" (")[0]

        if not self._is_automation_enabled_for_device(clean_device_id):
            await self._clear_disabled_co2_state(clean_device_id)
            return

        zone_manager = self._zone_managers.get(clean_device_id)
        triggered_zones: list[str] = []
        if zone_manager:
            triggered_zones = await zone_manager.check_zone_triggers(
                self.config.activation_hysteresis,
                self.config.deactivation_hysteresis,
            )

        sensor_ctx = await self._get_sensor_control_context(clean_device_id)
        self._latest_sensor_control_context[clean_device_id] = sensor_ctx
        await self._register_source_listeners(clean_device_id, sensor_ctx)
        triggered_sources = self._evaluate_trigger_sources(clean_device_id, sensor_ctx)
        _LOGGER.debug(
            "CO2 source evaluation for %s: area_sensors=%d, triggered_sources=%s",
            clean_device_id,
            len(
                cast(
                    list[dict[str, Any]],
                    (sensor_ctx or {}).get("area_sensors") or [],
                )
            ),
            [
                {
                    "source_id": item.get("source_id"),
                    "entity_id": item.get("entity_id"),
                    "value": item.get("value"),
                    "threshold": item.get("threshold"),
                }
                for item in triggered_sources
            ],
        )

        was_active = self._co2_active
        self._co2_active = bool(triggered_zones or triggered_sources)

        self._sync_zone_demands(clean_device_id, triggered_sources)

        await self._update_automation_status(
            clean_device_id,
            triggered_zones,
            triggered_sources,
            sensor_ctx,
        )

        # State change logging
        if self._co2_active and not was_active:
            self._activation_time = datetime.now()
            _LOGGER.info(
                "CO2 control activated for %s - zones: %s, sources: %s",
                clean_device_id,
                triggered_zones,
                [item.get("source_id") for item in triggered_sources],
            )
            # Notify humidity control to pause
            await self._notify_priority_takeover()

        elif not self._co2_active and was_active:
            _LOGGER.info("CO2 control deactivated for device %s", clean_device_id)
            # Notify humidity control it can resume
            await self._notify_priority_release()

        # Calculate and set fan speed
        if self._co2_active:
            if zone_manager:
                await self._adjust_fan_speed(clean_device_id, zone_manager)
            else:
                await self._boost_from_triggers(clean_device_id)
        else:
            # Return to idle/normal speed
            await self._return_to_idle(clean_device_id)

    async def _clear_disabled_co2_state(self, device_id: str) -> None:
        """Clear CO2 runtime state when per-device automation is disabled."""
        was_active = self._co2_active
        self._co2_active = False
        self._source_trigger_states[device_id] = {}

        self._sync_zone_demands(device_id, [])

        sensor_ctx = self._latest_sensor_control_context.get(device_id)
        await self._update_automation_status(device_id, [], [], sensor_ctx)

        if was_active:
            _LOGGER.info("CO2 control disabled for device %s", device_id)
            await self._notify_priority_release()

        await self._return_to_idle(device_id)

    def _evaluate_trigger_sources(
        self, device_id: str, sensor_ctx: dict[str, Any] | None
    ) -> list[dict[str, Any]]:
        """Evaluate all CO2 trigger sources from sensor_control context."""
        source_states = self._source_trigger_states.setdefault(device_id, {})
        triggered: list[dict[str, Any]] = []

        threshold_default = self._get_threshold_value(device_id)

        area_sensors = []
        if sensor_ctx and isinstance(sensor_ctx.get("area_sensors"), list):
            area_sensors = cast(
                list[dict[str, Any]],
                sensor_ctx.get("area_sensors") or [],
            )

        for area_sensor in area_sensors:
            if not bool(area_sensor.get("area_co2_enabled", False)):
                continue

            entity_id = str(area_sensor.get("co2_entity") or "").strip()
            if not entity_id:
                continue

            area_id = str(area_sensor.get("area_id") or entity_id).strip()
            label = str(area_sensor.get("label") or area_id)
            zone_id = str(area_sensor.get("zone_id") or "").strip() or None
            threshold = self._resolve_area_threshold(area_sensor, threshold_default)

            source_result = self._evaluate_source_trigger(
                source_states,
                area_id,
                label,
                entity_id,
                threshold,
                zone_id,
            )
            if source_result is not None:
                triggered.append(source_result)

        mappings = (
            cast(dict[str, str], sensor_ctx.get("mappings") or {}) if sensor_ctx else {}
        )
        internal_entity = str(mappings.get("co2") or "").strip()
        if not internal_entity:
            internal_entity = f"sensor.{device_id.replace(':', '_').lower()}_co2_level"

        internal_result = self._evaluate_source_trigger(
            source_states,
            "internal_co2",
            "Device CO2",
            internal_entity,
            threshold_default,
            None,
        )
        if internal_result is not None:
            triggered.append(internal_result)

        return triggered

    def _resolve_area_threshold(
        self,
        area_sensor: dict[str, Any],
        threshold_default: int,
    ) -> int:
        """Resolve per-area threshold from entity, static value, or default."""
        threshold_entity = str(area_sensor.get("co2_threshold_entity") or "").strip()
        if threshold_entity:
            state = self.hass.states.get(threshold_entity)
            if state and state.state not in {"unavailable", "unknown", "uninitialized"}:
                try:
                    return int(float(state.state))
                except TypeError, ValueError:
                    pass

        try:
            return int(area_sensor.get("co2_threshold") or threshold_default)
        except TypeError, ValueError:
            return threshold_default

    def _evaluate_source_trigger(
        self,
        source_states: dict[str, bool],
        source_id: str,
        label: str,
        entity_id: str,
        threshold: int,
        zone_id: str | None,
    ) -> dict[str, Any] | None:
        """Evaluate and update hysteresis trigger state for one source."""
        state = self.hass.states.get(entity_id)
        if not state or state.state in {"unavailable", "unknown", "uninitialized"}:
            source_states[source_id] = False
            return None

        try:
            co2_value = float(state.state)
        except TypeError, ValueError:
            source_states[source_id] = False
            return None

        activation_threshold = threshold + self.config.activation_hysteresis
        deactivation_threshold = threshold + self.config.deactivation_hysteresis

        was_active = source_states.get(source_id, False)
        is_active = was_active
        if not was_active and co2_value >= activation_threshold:
            is_active = True
        elif was_active and co2_value <= deactivation_threshold:
            is_active = False

        source_states[source_id] = is_active
        if not is_active:
            return None

        return {
            "source_id": source_id,
            "label": label,
            "entity_id": entity_id,
            "value": round(co2_value, 1),
            "threshold": threshold,
            "zone_id": zone_id,
        }

    def _sync_zone_demands(
        self, device_id: str, triggered_sources: list[dict[str, Any]]
    ) -> None:
        new_zones: set[str] = {
            str(item.get("zone_id")).strip()
            for item in triggered_sources
            if str(item.get("zone_id") or "").strip()
        }
        prev_zones = self._co2_demand_zones.get(device_id, set())

        for zone_id in sorted(prev_zones - new_zones):
            self._zone_demand_registry.clear_demand(
                device_id, zone_id, DemandSource.CO2
            )

        for item in triggered_sources:
            zone_id_raw = str(item.get("zone_id") or "").strip()
            if not zone_id_raw:
                continue

            metadata: dict[str, Any] = {
                "source_id": item.get("source_id"),
                "label": item.get("label"),
                "entity_id": item.get("entity_id"),
                "value": item.get("value"),
                "threshold": item.get("threshold"),
            }

            self._zone_demand_registry.set_demand(
                device_id,
                zone_id_raw,
                DemandSource.CO2,
                True,
                metadata=metadata,
            )

        if new_zones:
            self._co2_demand_zones[device_id] = new_zones
        else:
            self._co2_demand_zones.pop(device_id, None)

    def _get_threshold_value(self, device_id: str) -> int:
        """Resolve threshold from number entity when available."""
        entity_id = f"number.co2_threshold_{device_id.replace(':', '_').lower()}"
        state = self.hass.states.get(entity_id)
        if state and state.state not in {"unavailable", "unknown", "uninitialized"}:
            try:
                return int(float(state.state))
            except TypeError, ValueError:
                pass
        return int(self.config.default_threshold)

    async def _update_automation_status(
        self,
        device_id: str,
        triggered_zones: list[str],
        triggered_sources: list[dict[str, Any]],
        sensor_ctx: dict[str, Any] | None,
    ) -> None:
        """Update CO2 status entities with detailed trigger attributes."""
        trigger_ids = [
            str(item.get("source_id"))
            for item in triggered_sources
            if item.get("source_id")
        ]
        trigger_labels = [
            str(item.get("label")) for item in triggered_sources if item.get("label")
        ]
        trigger_entities = [
            str(item.get("entity_id"))
            for item in triggered_sources
            if item.get("entity_id")
        ]

        attrs: dict[str, Any] = {
            "active_trigger_source_id": trigger_ids[0] if trigger_ids else None,
            "active_trigger_source_ids": trigger_ids,
            "active_trigger_labels": trigger_labels,
            "active_trigger_labels_text": ", ".join(trigger_labels)
            if trigger_labels
            else None,
            "active_trigger_entity_ids": trigger_entities,
            "triggered_zone_ids": triggered_zones,
            "triggered_zone_count": len(triggered_zones),
            "triggered_source_count": len(triggered_sources),
            "triggered_sources": triggered_sources,
            "internal_co2_entity": self._resolve_internal_co2_entity(
                sensor_ctx, device_id
            ),
            "internal_triggered": "internal_co2" in trigger_ids,
        }
        self._trigger_meta[device_id] = attrs

        device_suffix = device_id.replace(":", "_").lower()
        active_entity_id = f"binary_sensor.co2_active_{device_suffix}"
        status_entity_id = f"sensor.co2_zone_status_{device_suffix}"

        zone_status = "idle"
        if triggered_sources:
            zone_status = "active: " + ", ".join(
                f"{item.get('label')} ({int(float(item.get('value', 0)))}ppm)"
                for item in triggered_sources
            )
        elif triggered_zones:
            zone_status = "zones active: " + ", ".join(triggered_zones)

        entities = self.hass.data.get(DOMAIN, {}).get("entities", {})
        active_entity = entities.get(active_entity_id)
        status_entity = entities.get(status_entity_id)

        if active_entity and hasattr(active_entity, "set_state"):
            active_entity.set_state(self._co2_active, attrs)
        if status_entity and hasattr(status_entity, "set_zone_status"):
            status_entity.set_zone_status(zone_status, attrs)

    def _resolve_internal_co2_entity(
        self, sensor_ctx: dict[str, Any] | None, device_id: str
    ) -> str:
        mappings = (
            cast(dict[str, str], sensor_ctx.get("mappings") or {}) if sensor_ctx else {}
        )
        internal_entity = str(mappings.get("co2") or "").strip()
        if internal_entity:
            return internal_entity
        return f"sensor.{device_id.replace(':', '_').lower()}_co2_level"

    async def _boost_from_triggers(self, device_id: str) -> None:
        """Fallback boost command when no zone manager is configured."""
        target_speed = 3
        if target_speed == self._last_fan_speed:
            return

        success = await self.fan_speed_arbiter.async_set_demand(
            device_id,
            feature_id=self.feature_id,
            source_id="co2_control",
            requested_speed="fan_medium",
            priority=30,
            reason="co2_trigger",
        )
        if success:
            self._last_fan_speed = target_speed

    async def _adjust_fan_speed(
        self, device_id: str, zone_manager: CO2ZoneManager
    ) -> None:
        """Adjust fan speed based on CO2 levels.

        :param device_id: Device identifier
        :param zone_manager: Zone manager instance
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
            success = await self.fan_speed_arbiter.async_set_demand(
                device_id,
                feature_id=self.feature_id,
                source_id="co2_control",
                requested_speed=command_name,
                priority=30,
                reason="co2_trigger",
                metadata={"target_speed": target_speed},
            )
            if success:
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

        :param device_id: Device identifier
        """
        idle_speed = 1
        if self._last_fan_speed != idle_speed:
            success = await self.fan_speed_arbiter.async_clear_demand(
                device_id,
                feature_id=self.feature_id,
                source_id="co2_control",
            )
            if success:
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

        :return: True if CO2 control is active
        """
        return self._co2_active

    def get_status(self) -> dict[str, Any]:
        """Get current CO2 control status.

        :return: Status dictionary
        """
        return {
            "enabled": self.config.enabled,
            "automation_enabled": self.config.automation_enabled,
            "is_active": self._automation_active,
            "active": self._co2_active,
            "activation_time": (
                self._activation_time.isoformat() if self._activation_time else None
            ),
            "last_fan_speed": self._last_fan_speed,
            "trigger_meta": self._trigger_meta,
            "fan_arbiter": {
                device_id: self.fan_speed_arbiter.get_device_debug_state(device_id)
                for device_id in self._iter_candidate_device_ids()
            },
            "zones": {
                device_id: zone_manager.get_zone_status()
                for device_id, zone_manager in self._zone_managers.items()
            },
        }

    async def async_unload(self) -> bool:
        """Unload CO2 automation.

        :return: True if unload successful
        """
        # Remove state change listeners
        for listener in self._state_change_listeners:
            listener()
        self._state_change_listeners.clear()
        self._source_listener_entities.clear()

        _LOGGER.info("CO2 automation unloaded")
        return True


__all__ = ["CO2AutomationManager"]
