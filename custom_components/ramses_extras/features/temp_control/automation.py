"""Temperature control automation.

Controls FAN bypass based on comfort temperature:

- cooling: force bypass open when indoor above comfort and supply can cool
- heating_retention: force bypass close when indoor below comfort
- idle: bypass auto

Optionally requests fan speed increases during cooling when humidity and CO2
conditions allow it.
"""

from __future__ import annotations

import logging
import math
import time
from collections.abc import Mapping
from dataclasses import asdict
from typing import Any, cast

from homeassistant.core import Event, HomeAssistant

from custom_components.ramses_extras.const import DOMAIN
from custom_components.ramses_extras.framework.base_classes.base_automation import (
    ExtrasBaseAutomation,
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

from .config import TempControlConfig
from .const import FEATURE_ID, TEMP_CONTROL_DEFAULTS

_LOGGER = logging.getLogger(__name__)


class TempControlAutomationManager(ExtrasBaseAutomation):
    @staticmethod
    def _calc_dewpoint_c(temp_c: float, rh_percent: float) -> float | None:
        if not (0.0 < rh_percent <= 100.0):
            return None
        a = 17.62
        b = 243.12
        gamma = (a * temp_c) / (b + temp_c) + math.log(rh_percent / 100.0)
        return (b * gamma) / (a - gamma)

    def __init__(self, hass: HomeAssistant, config_entry: Any) -> None:
        super().__init__(
            hass=hass,
            feature_id=FEATURE_ID,
            binary_sensor=None,
            debounce_seconds=30,
        )

        self.config_entry = config_entry
        self.config = TempControlConfig(hass, config_entry)
        self.ramses_commands = RamsesCommands(hass)
        self.fan_speed_arbiter = get_fan_speed_arbiter(hass)
        self._zone_demand_registry = get_zone_demand_registry(hass)

        self._automation_active = False
        self._last_bypass_change: dict[str, float] = {}
        self._last_bypass_command: dict[str, str] = {}
        self._last_bypass_command_time: dict[str, float] = {}
        self._mode: dict[str, str] = {}  # device_id -> idle/cooling/heating_retention
        # Track which zones currently have a temp_control demand
        self._temp_demand_zones: dict[str, set[str]] = {}
        # Re-entrancy guard: prevent concurrent _process_automation_logic runs
        self._processing_devices: set[str] = set()

    def is_automation_active(self) -> bool:
        return self._automation_active

    def _is_feature_enabled(self) -> bool:
        try:
            domain_data = self.hass.data.get(DOMAIN, {})
            enabled_features = domain_data.get("enabled_features")
            if not isinstance(enabled_features, dict):
                enabled_features = (
                    self.config_entry.options.get("enabled_features")
                    or self.config_entry.data.get("enabled_features")
                    or {}
                )
            return enabled_features.get(FEATURE_ID, False) is True
        except Exception as err:
            _LOGGER.warning("Could not check temp_control feature status: %s", err)
            return False

    def _generate_entity_patterns(self) -> list[str]:
        # Track temps + core controls; naming can vary by sensor_control.
        # Also track bypass position for the state-based manual override
        # safety net (detect external bypass changes).
        return [
            "switch.temp_control_*",
            "select.temp_control_desired_speed_*",
            "sensor.*_indoor_temp",
            "sensor.*_outdoor_temp",
            "sensor.*_supply_temp",
            "number.*_param_75",
            "sensor.*_indoor_humidity",
            "number.relative_humidity_minimum_*",
            "number.relative_humidity_maximum_*",
            "binary_sensor.dehumidifying_active_*",
            "binary_sensor.co2_active_*",
            "sensor.co2_zone_status_*",
            "binary_sensor.*_bypass_position",
        ]

    async def start(self) -> None:
        if not self._is_feature_enabled():
            _LOGGER.info(
                "temp_control feature not enabled; skipping automation startup"
            )
            return

        self._automation_active = True
        await super().start()

    async def stop(self) -> None:
        self._automation_active = False

        for device_id in list(self._mode):
            await self._clear_speed_demand(device_id)
            await self._clear_all_zone_demands(device_id)
            # Release the bypass back to the device's own control so it
            # is not left in a forced open/close state when temp_control
            # stops.  Only send if we were actively forcing a bypass state
            # (cooling/heating_retention); in idle we already sent auto.
            if self._mode.get(device_id) in {"cooling", "heating_retention"}:
                await self._release_bypass(device_id)

        await super().stop()

    async def _on_homeassistant_started(self, event: Event | None) -> None:
        await super()._on_homeassistant_started(event)
        if not self._automation_active or not self._is_feature_enabled():
            return

        # Evaluate once on startup for any enabled devices (switch on).
        for device_id in self._iter_candidate_device_ids():
            try:
                entity_states = await self._get_device_entity_states(device_id)
            except ValueError:
                continue
            await self._process_automation_logic(device_id, entity_states)

    async def _reconcile_startup_states(self, device_id: str | None = None) -> None:
        """Re-evaluate automation after manual override is released.

        Called by _async_resume_feature_control when the user presses Auto
        or when a remote override timeout expires.
        """
        if not self._automation_active or not self._is_feature_enabled():
            return

        if device_id:
            device_ids = [device_id]
        else:
            device_ids = self._iter_candidate_device_ids()

        for dev_id in device_ids:
            try:
                entity_states = await self._get_device_entity_states(dev_id)
            except ValueError:
                continue
            await self._process_automation_logic(dev_id, entity_states)

    async def _async_handle_state_change(
        self, entity_id: str, old_state: Any, new_state: Any
    ) -> None:
        """Override to detect external bypass changes (safety net).

        If the bypass position entity changes while temp_control is on,
        and the change was not caused by a command we just sent, turn
        temp_control off for that device.
        """
        # Skip if the state value didn't actually change
        if (
            new_state is not None
            and old_state is not None
            and old_state.state == new_state.state
        ):
            return

        import time as _time

        if (
            entity_id.startswith("binary_sensor.")
            and entity_id.endswith("_bypass_position")
            and old_state is not None
            and new_state is not None
        ):
            device_id = self._extract_device_id(entity_id)
            if device_id:
                device_id = device_id.replace("_", ":")
                # Is temp_control currently on for this device?
                switch_id = f"switch.temp_control_{device_id.replace(':', '_')}"
                switch_state = self.hass.states.get(switch_id)
                if switch_state and switch_state.state == "on":
                    # Only treat bypass changes as a manual override when
                    # temp_control is actively forcing a bypass state
                    # (cooling = bypass open, heating_retention = bypass
                    # close).  In "idle" mode we sent fan_bypass_auto, so
                    # the FAN device is free to move the bypass damper on
                    # its own — those changes are expected, not manual
                    # overrides, and must not disable temp_control.
                    # This also covers bypass movements induced by other
                    # features (e.g. humidity_control veto forcing fan_low)
                    # when the device repositions the damper in response.
                    current_mode = self._mode.get(device_id, "idle")
                    if current_mode in {"cooling", "heating_retention"}:
                        # Was this change caused by our own command?
                        last_cmd_time = self._last_bypass_command_time.get(
                            device_id, 0.0
                        )
                        now = _time.time()
                        # Allow a 10s window for our command to take effect
                        if now - last_cmd_time > 10.0:
                            _LOGGER.info(
                                "External bypass change detected for %s "
                                "(mode=%s, no recent temp_control command); "
                                "turning temp_control off",
                                device_id,
                                current_mode,
                            )
                            await self.hass.services.async_call(
                                "switch",
                                "turn_off",
                                {"entity_id": switch_id},
                            )
                            return

        # Bypass debounce for user-initiated switch toggles — these should
        # be processed immediately, not delayed by sensor-fluctuation debounce.
        if entity_id.startswith("switch.temp_control_"):
            device_id = self._extract_device_id(entity_id)
            if device_id:
                device_id = device_id.replace("_", ":")
                try:
                    entity_states = await self._get_device_entity_states(device_id)
                except ValueError:
                    return
                await self._process_automation_logic(device_id, entity_states)
                return

        await super()._async_handle_state_change(entity_id, old_state, new_state)

    def _iter_candidate_device_ids(self) -> list[str]:
        ids: set[str] = set()

        for state in self.hass.states.async_all("switch"):
            if state.entity_id.startswith("switch.temp_control_"):
                dev_id = self._extract_device_id(state.entity_id)
                if dev_id:
                    ids.add(dev_id.replace("_", ":"))

        devices = self.hass.data.get(DOMAIN, {}).get("devices", [])
        for device in devices:
            if isinstance(device, dict):
                raw = device.get("device_id")
            else:
                raw = getattr(device, "device_id", None) or getattr(device, "id", None)
            if raw:
                ids.add(str(raw).replace("_", ":"))

        return sorted({i for i in ids if i})

    async def _get_device_entity_states(
        self, device_id: str
    ) -> dict[str, float | bool]:
        """Return numeric/bool inputs used by the automation.

        Uses FEATURE_DEFINITION.entity_mappings to resolve entity IDs.
        Applies sensor_control overlays so external sensors are used when
        configured.
        """

        from custom_components.ramses_extras.framework.helpers.entity.core import (
            get_feature_entity_mappings,
        )

        mappings = await get_feature_entity_mappings(
            self.feature_id, device_id, self.hass
        )

        # Apply sensor_control overlays for indoor/outdoor temp + humidity
        sensor_ctx = await self._get_sensor_control_context(device_id)
        if sensor_ctx:
            metric_mappings = cast(dict[str, str], sensor_ctx.get("mappings") or {})
            # sensor_control uses metric names like "indoor_temperature";
            # our feature uses "indoor_temp" — translate.
            temp_entity = metric_mappings.get("indoor_temperature")
            if temp_entity:
                mappings["indoor_temp"] = temp_entity
            outdoor_entity = metric_mappings.get("outdoor_temperature")
            if outdoor_entity:
                mappings["outdoor_temp"] = outdoor_entity
            humidity_entity = metric_mappings.get("indoor_humidity")
            if humidity_entity:
                mappings["indoor_rh"] = humidity_entity

        def _get_state(entity_id: str) -> Any:
            state = self.hass.states.get(entity_id)
            return state.state if state else None

        def _as_bool(entity_id: str) -> bool:
            raw = _get_state(entity_id)
            return str(raw).lower() in {"on", "true", "1", "yes"}

        def _as_float(entity_id: str) -> float:
            raw = _get_state(entity_id)
            if raw in (None, "unavailable", "unknown"):
                raise ValueError(f"Entity {entity_id} state unavailable")
            return float(raw)

        resolved: dict[str, float | bool] = {}

        # Core controls
        resolved["temp_control"] = _as_bool(mappings["temp_control"])

        # Temperatures
        resolved["indoor_temp"] = _as_float(mappings["indoor_temp"])
        resolved["outdoor_temp"] = _as_float(mappings["outdoor_temp"])
        resolved["supply_temp"] = _as_float(mappings["supply_temp"])
        resolved["comfort_temp"] = _as_float(mappings["comfort_temp"])

        # Humidity
        resolved["indoor_rh"] = _as_float(mappings["indoor_rh"])
        resolved["min_rh"] = _as_float(mappings["min_rh"])
        resolved["max_rh"] = _as_float(mappings["max_rh"])
        resolved["dehumidifying_active"] = _as_bool(mappings["dehumidifying_active"])

        # CO2
        # co2_active may not exist if co2_control is disabled; treat as off.
        try:
            resolved["co2_active"] = _as_bool(mappings["co2_active"])
        except Exception:
            resolved["co2_active"] = False

        return resolved

    async def _process_automation_logic(
        self, device_id: str, entity_states: Mapping[str, float | bool]
    ) -> None:
        # Re-entrancy guard: skip if already processing this device
        if device_id in self._processing_devices:
            _LOGGER.debug("Already processing %s, skipping re-entrant call", device_id)
            return

        self._processing_devices.add(device_id)
        try:
            await self._process_automation_logic_inner(device_id, entity_states)
        finally:
            self._processing_devices.discard(device_id)

    async def _process_automation_logic_inner(
        self, device_id: str, entity_states: Mapping[str, float | bool]
    ) -> None:
        if not self._automation_active or not self._is_feature_enabled():
            return

        if not bool(entity_states.get("temp_control")):
            await self._handle_disabled(device_id, reason="disabled")
            return

        # Skip if a manual override is active (remote control, card button, etc.)
        if self.fan_speed_arbiter.is_manual_override_active(device_id):
            _LOGGER.debug(
                "Manual override active - skipping temp_control for %s",
                device_id,
            )
            return

        # Skip if extras control is disabled (e.g. away/timer mode)
        if not self.fan_speed_arbiter.is_extras_control_enabled(device_id):
            _LOGGER.debug(
                "Extras control disabled - skipping temp_control for %s",
                device_id,
            )
            return

        settings = self.config.get_settings()
        now = time.time()

        indoor_temp = float(entity_states["indoor_temp"])
        outdoor_temp = float(entity_states["outdoor_temp"])
        supply_temp = float(entity_states["supply_temp"])
        comfort_temp = float(entity_states["comfort_temp"])
        indoor_rh = float(entity_states["indoor_rh"])

        # Per-area evaluation: if sensor_control areas are configured with
        # temperature entities, evaluate each area separately and aggregate.
        area_results = await self._evaluate_areas(device_id, settings, outdoor_temp)

        # Determine desired mode
        # Treat "disabled" as "idle" — when the switch was off, there is no
        # hysteresis state to maintain and no min-interval to enforce.
        prev_mode = self._mode.get(device_id, "idle")
        if prev_mode == "disabled":
            prev_mode = "idle"
        desired_mode = "idle"

        if area_results:
            # Aggregate per-area decisions: cooling has priority over
            # heating_retention (if any area needs cooling, cool the house).
            any_cooling = any(r["decision"] == "cooling" for r in area_results)
            any_heating = any(
                r["decision"] == "heating_retention" for r in area_results
            )
            if any_cooling:
                desired_mode = "cooling"
            elif any_heating:
                desired_mode = "heating_retention"

            # Publish/clear zone demands for areas that need actuation
            await self._publish_zone_demands(device_id, area_results, desired_mode)
        else:
            # Single-target logic (no areas configured)
            # Heating retention has priority when too cold
            if indoor_temp <= comfort_temp - settings.comfort_delta_activate:
                desired_mode = "heating_retention"
            else:
                # Cooling: indoor must be above comfort by the activate delta.
                # Two cooling sources:
                #   1. Outdoor air cooler than indoor (free cooling)
                #   2. Supply air cooler than indoor (evaporative cooler,
                #      ground-coupled heat exchanger, etc.)
                # Either source is sufficient to enter cooling mode.
                if indoor_temp >= comfort_temp + settings.comfort_delta_activate:
                    outdoor_can_cool = (
                        outdoor_temp >= settings.min_outdoor_temp
                        and outdoor_temp
                        <= indoor_temp - settings.cooling_delta_activate
                    )
                    supply_can_cool = (
                        supply_temp >= settings.min_supply_temp
                        and supply_temp
                        <= indoor_temp - settings.supply_cooler_delta_activate
                    )
                    if outdoor_can_cool or supply_can_cool:
                        desired_mode = "cooling"

            # Apply hysteresis based on previous mode
            if prev_mode == "cooling" and desired_mode != "cooling":
                if indoor_temp > comfort_temp + settings.comfort_delta_deactivate:
                    outdoor_can_cool = outdoor_temp <= (
                        indoor_temp - settings.cooling_delta_deactivate
                    )
                    supply_can_cool = supply_temp <= (
                        indoor_temp - settings.supply_cooler_delta_deactivate
                    )
                    if outdoor_can_cool or supply_can_cool:
                        desired_mode = "cooling"

            if prev_mode == "heating_retention" and desired_mode != "heating_retention":
                if indoor_temp < comfort_temp - settings.comfort_delta_deactivate:
                    desired_mode = "heating_retention"

            # Clear any stale zone demands when running in single-target mode
            await self._clear_all_zone_demands(device_id)

        if desired_mode == "cooling" and getattr(
            settings, "dewpoint_guard_enabled", False
        ):
            dewpoint = self._calc_dewpoint_c(indoor_temp, indoor_rh)
            margin = float(getattr(settings, "dewpoint_margin_c", 1.0))
            if dewpoint is not None and supply_temp < dewpoint + margin:
                _LOGGER.debug(
                    "Temp_control for %s: dewpoint guard cancelling cooling "
                    "(supply=%.1f < dewpoint+margin=%.1f+%.1f=%.1f)",
                    device_id,
                    supply_temp,
                    dewpoint,
                    margin,
                    dewpoint + margin,
                )
                desired_mode = "idle"
                await self._clear_all_zone_demands(device_id)

        _LOGGER.debug(
            "Decision for %s: mode=%s (prev=%s, indoor=%.1f, outdoor=%.1f, "
            "supply=%.1f, comfort=%.1f, RH=%.1f%%, areas=%d)",
            device_id,
            desired_mode,
            prev_mode,
            indoor_temp,
            outdoor_temp,
            supply_temp,
            comfort_temp,
            indoor_rh,
            len(area_results),
        )

        # Enforce minimum interval between bypass mode changes
        last_change = self._last_bypass_change.get(device_id, 0.0)
        if (
            desired_mode != prev_mode
            and (now - last_change) < settings.min_bypass_mode_interval_seconds
        ):
            _LOGGER.debug(
                "Temp_control for %s: suppressing %s->%s (min interval %.0fs)",
                device_id,
                prev_mode,
                desired_mode,
                settings.min_bypass_mode_interval_seconds,
            )
            desired_mode = prev_mode

        bypass_cmd = {
            "cooling": "fan_bypass_open",
            "heating_retention": "fan_bypass_close",
            "idle": "fan_bypass_auto",
            "disabled": "fan_bypass_auto",
        }[desired_mode]

        # Send bypass command only when the mode changed AND either the
        # command name is different or enough time has passed since the
        # last identical command (safety net against rapid oscillation
        # when min_bypass_mode_interval_seconds is set very low).
        bypass_dedup_seconds = 5.0
        last_cmd = self._last_bypass_command.get(device_id)
        last_cmd_time = self._last_bypass_command_time.get(device_id, 0.0)
        command_changed = last_cmd != bypass_cmd
        dedup_expired = (now - last_cmd_time) >= bypass_dedup_seconds

        if desired_mode != prev_mode and (command_changed or dedup_expired):
            _LOGGER.debug(
                "Temp_control for %s: sending bypass %s (%s->%s)",
                device_id,
                bypass_cmd,
                prev_mode,
                desired_mode,
            )
            await self.ramses_commands.send_command(device_id, bypass_cmd)
            self._last_bypass_change[device_id] = now
            self._last_bypass_command[device_id] = bypass_cmd
            self._last_bypass_command_time[device_id] = now

        self._mode[device_id] = desired_mode

        # Fan speed demand only during cooling — the arbiter resolves
        # conflicts with humidity_control / co2_control demands.
        effective_speed_note = "no_speed_change"
        if desired_mode == "cooling":
            desired_speed = self._get_desired_speed_option(device_id)
            _LOGGER.debug(
                "Temp_control for %s: requesting fan %s (cooling mode)",
                device_id,
                desired_speed,
            )
            await self.fan_speed_arbiter.async_set_demand(
                device_id,
                feature_id=self.feature_id,
                source_id="temp_control",
                requested_speed=desired_speed,
                priority=20,
                reason="temp_control_cooling",
            )
            await self.fan_speed_arbiter.async_commit_state(device_id, apply=True)
            effective_speed_note = "requested"
        else:
            await self._clear_speed_demand(device_id)

        active = desired_mode in {"cooling", "heating_retention"}

        attrs = {
            "mode": desired_mode,
            "desired_bypass_mode": (
                "open"
                if desired_mode == "cooling"
                else "close"
                if desired_mode == "heating_retention"
                else "auto"
            ),
            "last_command": bypass_cmd,
            "desired_speed": self._get_desired_speed_option(device_id),
            "effective_speed_note": effective_speed_note,
            "temperatures": {
                "indoor": indoor_temp,
                "supply": supply_temp,
                "comfort": comfort_temp,
            },
            "settings": asdict(settings),
        }

        self._set_active_indicator(device_id, active, attrs)
        self._set_status_sensor(device_id, desired_mode, attrs)

    async def _handle_disabled(self, device_id: str, reason: str) -> None:
        await self._clear_speed_demand(device_id)
        await self._clear_all_zone_demands(device_id)
        prev_mode = self._mode.get(device_id)
        self._mode[device_id] = "disabled"
        # Reset bypass change timestamp so the first mode change after
        # re-enabling is not blocked by the min-interval guard.
        self._last_bypass_change.pop(device_id, None)
        self._last_bypass_command.pop(device_id, None)

        # Release the bypass back to the device's own control so it is
        # not left in a forced open/close state.  Only send if we were
        # actively forcing a bypass state; in idle we already sent auto,
        # and on a fresh startup (no prev_mode) the device is already
        # autonomous.
        if prev_mode in {"cooling", "heating_retention"}:
            await self._release_bypass(device_id)

        attrs = {"mode": "disabled", "reason": reason}
        self._set_active_indicator(device_id, False, attrs)
        self._set_status_sensor(device_id, "disabled", attrs)

    async def _release_bypass(self, device_id: str) -> None:
        """Send fan_bypass_auto so the device resumes autonomous bypass control.

        Used when temp_control stops or is disabled while it was actively
        forcing a bypass state (cooling/heating_retention).  Without this
        the bypass damper is left in the last forced position.
        """
        try:
            await self.ramses_commands.send_command(device_id, "fan_bypass_auto")
        except Exception as err:
            _LOGGER.warning(
                "Failed to release bypass to auto for %s: %s", device_id, err
            )

    async def _clear_speed_demand(self, device_id: str) -> None:
        try:
            await self.fan_speed_arbiter.async_clear_demand(
                device_id,
                feature_id=self.feature_id,
            )
        except Exception:
            return

    def _get_desired_speed_option(self, device_id: str) -> str:
        device_key = device_id.replace(":", "_")
        entity_id = f"select.temp_control_desired_speed_{device_key}"
        state = self.hass.states.get(entity_id)
        if state and state.state in {"low", "medium", "high"}:
            return str(state.state)
        # Fall back to the configured default
        settings = self.config.get_settings()
        default_speed = getattr(settings, "default_desired_speed", "high")
        return default_speed if default_speed in {"low", "medium", "high"} else "high"

    def _set_active_indicator(
        self, device_id: str, active: bool, attrs: dict[str, Any]
    ) -> None:
        entity_id = f"binary_sensor.temp_control_active_{device_id.replace(':', '_')}"
        entity = (
            self.hass.data.get(DOMAIN, {}).get("entities", {}).get(entity_id)
            if hasattr(self.hass, "data")
            else None
        )
        if entity is not None and hasattr(entity, "set_state"):
            try:
                entity.set_state(active, attrs)
            except Exception:
                entity.set_state(active)

    def _set_status_sensor(
        self, device_id: str, status: str, attrs: dict[str, Any]
    ) -> None:
        entity_id = f"sensor.temp_control_status_{device_id.replace(':', '_')}"
        entity = (
            self.hass.data.get(DOMAIN, {}).get("entities", {}).get(entity_id)
            if hasattr(self.hass, "data")
            else None
        )
        if entity is not None and hasattr(entity, "set_status"):
            try:
                entity.set_status(status, attrs)
            except Exception:
                entity.set_native_value(status)

    # ---- sensor_control integration ----

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
            if isinstance(enabled_features, dict):
                return enabled_features.get("sensor_control") is True
            if isinstance(enabled_features, list):
                return "sensor_control" in enabled_features
            return False
        except Exception:
            return False

    def _get_device_type_for_sensor_control(self, device_id: str) -> str | None:
        """Get device type for sensor_control resolver."""
        devices = self.hass.data.get(DOMAIN, {}).get("devices", [])
        target_colon = str(device_id).replace("_", ":")

        for device in devices:
            if isinstance(device, dict):
                raw_id = device.get("device_id")
                device_type = device.get("type")
            else:
                raw_id = device
                device_type = getattr(device, "_SLUG", None) or getattr(
                    device, "type", None
                )

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

    async def _get_sensor_control_context(
        self, device_id: str
    ) -> dict[str, Any] | None:
        """Get sensor_control overrides for a device.

        Calls the SensorControlResolver directly to get external entity
        mappings for indoor/outdoor temperature and humidity.
        """
        try:
            if not self._is_sensor_control_enabled():
                return None

            from custom_components.ramses_extras.features.sensor_control import (
                resolver as sensor_control_resolver,
            )

            device_type = self._get_device_type_for_sensor_control(device_id)
            # Default to "FAN" if device type can't be determined — the
            # resolver still processes overrides regardless of device type.
            if not device_type:
                device_type = "FAN"

            resolver = sensor_control_resolver.SensorControlResolver(self.hass)
            sensor_result = await resolver.resolve_entity_mappings(
                device_id, device_type
            )

            return {
                "mappings": sensor_result.get("mappings", {}),
                "sources": sensor_result.get("sources", {}),
                "area_sensors": sensor_result.get("area_sensors", []),
            }
        except Exception as err:
            _LOGGER.error(
                "Error getting sensor_control context for %s: %s",
                device_id,
                err,
            )
            return None

    async def _evaluate_areas(
        self,
        device_id: str,
        settings: Any,
        outdoor_temp: float,
    ) -> list[dict[str, Any]]:
        """Evaluate per-area temperature conditions.

        Returns a list of dicts with keys:
        - area_id, zone_id, area_temp, area_comfort, decision, reason
        Returns an empty list if no areas are configured or no area has
        a temperature entity.
        """
        sensor_ctx = await self._get_sensor_control_context(device_id)
        if not sensor_ctx:
            return []

        area_sensors = sensor_ctx.get("area_sensors") or []
        if not isinstance(area_sensors, list):
            return []

        # Get the FAN global comfort temp as fallback for areas without
        # their own comfort_temperature_entity.
        global_comfort_entity = f"number.{device_id.replace(':', '_')}_param_75"
        global_comfort_state = self.hass.states.get(global_comfort_entity)
        global_comfort: float | None = None
        if global_comfort_state and global_comfort_state.state not in (
            None,
            "unavailable",
            "unknown",
        ):
            try:
                global_comfort = float(global_comfort_state.state)
            except ValueError, TypeError:
                global_comfort = None

        results: list[dict[str, Any]] = []

        for area in area_sensors:
            if not isinstance(area, dict):
                continue
            if not area.get("enabled", True):
                continue

            temp_entity = area.get("temperature_entity")
            if not temp_entity:
                continue

            temp_state = self.hass.states.get(temp_entity)
            if not temp_state or temp_state.state in (None, "unavailable", "unknown"):
                continue

            try:
                area_temp = float(temp_state.state)
            except ValueError, TypeError:
                continue

            # Resolve comfort temp: area's comfort_temperature_entity → global
            comfort_entity = area.get("comfort_temperature_entity")
            area_comfort: float | None = None
            if comfort_entity:
                comfort_state = self.hass.states.get(comfort_entity)
                if comfort_state and comfort_state.state not in (
                    None,
                    "unavailable",
                    "unknown",
                ):
                    try:
                        area_comfort = float(comfort_state.state)
                    except ValueError, TypeError:
                        pass

            if area_comfort is None:
                if global_comfort is not None:
                    area_comfort = global_comfort
                else:
                    continue  # No comfort temp available for this area

            # Evaluate this area
            decision = "idle"
            reason = ""

            if area_temp <= area_comfort - settings.comfort_delta_activate:
                decision = "heating_retention"
                reason = (
                    f"area {area.get('area_id')} too cold "
                    f"({area_temp} < {area_comfort})"
                )
            elif (
                area_temp >= area_comfort + settings.comfort_delta_activate
                and outdoor_temp >= settings.min_outdoor_temp
                and outdoor_temp <= area_temp - settings.cooling_delta_activate
            ):
                decision = "cooling"
                reason = (
                    f"area {area.get('area_id')} too warm "
                    f"({area_temp} > {area_comfort})"
                )

            if decision == "idle":
                continue  # Skip areas that don't need action

            results.append(
                {
                    "area_id": area.get("area_id"),
                    "zone_id": area.get("zone_id"),
                    "area_temp": area_temp,
                    "area_comfort": area_comfort,
                    "decision": decision,
                    "reason": reason,
                }
            )

        return results

    async def _publish_zone_demands(
        self,
        device_id: str,
        area_results: list[dict[str, Any]],
        desired_mode: str,
    ) -> None:
        """Publish/clear zone demands based on per-area evaluation.

        Only areas with a zone_id get zone demands.  Areas without a
        zone_id influence the bypass decision but don't open zone valves.
        """
        if not self._zone_demand_registry:
            return

        new_demand_zones: set[str] = set()

        for result in area_results:
            zone_id = result.get("zone_id")
            if not zone_id:
                continue

            if desired_mode in ("cooling", "heating_retention"):
                new_demand_zones.add(zone_id)
                self._zone_demand_registry.set_demand(
                    device_id,
                    zone_id,
                    DemandSource.OTHER,
                    True,
                    metadata={
                        "kind": "temperature",
                        "area_id": result.get("area_id"),
                        "area_temp": result.get("area_temp"),
                        "area_target": result.get("area_comfort"),
                        "decision": result.get("decision"),
                        "reason": result.get("reason"),
                    },
                )

        # Clear demands for zones that no longer need action
        prev_zones = self._temp_demand_zones.get(device_id, set())
        for zone_id in prev_zones - new_demand_zones:
            self._zone_demand_registry.clear_demand(
                device_id, zone_id, DemandSource.OTHER
            )

        self._temp_demand_zones[device_id] = new_demand_zones

    async def _clear_all_zone_demands(self, device_id: str) -> None:
        """Clear all temp_control zone demands for a device."""
        if not self._zone_demand_registry:
            return

        prev_zones = self._temp_demand_zones.pop(device_id, set())
        for zone_id in prev_zones:
            self._zone_demand_registry.clear_demand(
                device_id, zone_id, DemandSource.OTHER
            )


__all__ = ["TempControlAutomationManager"]
