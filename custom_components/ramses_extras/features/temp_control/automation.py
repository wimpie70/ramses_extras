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
import time
from collections.abc import Mapping
from dataclasses import asdict
from typing import Any

from homeassistant.core import Event, HomeAssistant

from custom_components.ramses_extras.const import DOMAIN
from custom_components.ramses_extras.framework.base_classes.base_automation import (
    ExtrasBaseAutomation,
)
from custom_components.ramses_extras.framework.helpers.config.migration import (
    get_migrated_feature_section,
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

from .config import TempControlConfig
from .const import FEATURE_ID, TEMP_CONTROL_DEFAULTS

_LOGGER = logging.getLogger(__name__)


class TempControlAutomationManager(ExtrasBaseAutomation):
    def __init__(self, hass: HomeAssistant, config_entry: Any) -> None:
        super().__init__(
            hass=hass,
            feature_id=FEATURE_ID,
            binary_sensor=None,
            debounce_seconds=0,
        )

        self.config_entry = config_entry
        self.config = TempControlConfig(hass, config_entry)
        self.ramses_commands = RamsesCommands(hass)
        self.fan_speed_arbiter = get_fan_speed_arbiter(hass)

        self._automation_active = False
        self._last_bypass_change: dict[str, float] = {}
        self._last_bypass_command: dict[str, str] = {}
        self._mode: dict[str, str] = {}  # device_id -> idle/cooling/heating_retention

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
        return [
            "switch.temp_control_*",
            "select.temp_control_desired_speed_*",
            "sensor.*_indoor_temp",
            "sensor.*_supply_temp",
            "number.*_param_75",
            "sensor.*_indoor_humidity",
            "number.relative_humidity_minimum_*",
            "number.relative_humidity_maximum_*",
            "binary_sensor.dehumidifying_active_*",
            "binary_sensor.co2_active_*",
            "sensor.co2_zone_status_*",
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
        """

        from custom_components.ramses_extras.framework.helpers.entity.core import (
            get_feature_entity_mappings,
        )

        mappings = await get_feature_entity_mappings(
            self.feature_id, device_id, self.hass
        )

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
        if not self._automation_active or not self._is_feature_enabled():
            return

        if not bool(entity_states.get("temp_control")):
            await self._handle_disabled(device_id, reason="disabled")
            return

        settings = self.config.get_settings()
        now = time.time()

        indoor_temp = float(entity_states["indoor_temp"])
        outdoor_temp = float(entity_states["outdoor_temp"])
        supply_temp = float(entity_states["supply_temp"])
        comfort_temp = float(entity_states["comfort_temp"])

        # Determine desired mode
        # Treat "disabled" as "idle" — when the switch was off, there is no
        # hysteresis state to maintain and no min-interval to enforce.
        prev_mode = self._mode.get(device_id, "idle")
        if prev_mode == "disabled":
            prev_mode = "idle"
        desired_mode = "idle"

        # Heating retention has priority when too cold
        if indoor_temp <= comfort_temp - settings.comfort_delta_activate:
            desired_mode = "heating_retention"
        else:
            # Cooling: outdoor air must be cooler than indoor by the
            # configured delta AND above the safety floor (min_outdoor_temp).
            # We use outdoor_temp (not supply_temp) because when bypass is
            # closed, supply_temp ≈ indoor_temp due to heat recovery, making
            # the condition circular.  Opening the bypass is what brings
            # supply air closer to outdoor temp.
            if (
                indoor_temp >= comfort_temp + settings.comfort_delta_activate
                and outdoor_temp >= settings.min_outdoor_temp
                and outdoor_temp <= indoor_temp - settings.cooling_delta_activate
            ):
                desired_mode = "cooling"

        # Apply hysteresis based on previous mode
        if prev_mode == "cooling" and desired_mode != "cooling":
            if indoor_temp > comfort_temp + settings.comfort_delta_deactivate and (
                outdoor_temp <= indoor_temp - settings.cooling_delta_deactivate
            ):
                desired_mode = "cooling"

        if prev_mode == "heating_retention" and desired_mode != "heating_retention":
            if indoor_temp < comfort_temp - settings.comfort_delta_deactivate:
                desired_mode = "heating_retention"

        # Enforce minimum interval between bypass mode changes
        last_change = self._last_bypass_change.get(device_id, 0.0)
        if (
            desired_mode != prev_mode
            and (now - last_change) < settings.min_bypass_mode_interval_seconds
        ):
            desired_mode = prev_mode

        bypass_cmd = {
            "cooling": "fan_bypass_open",
            "heating_retention": "fan_bypass_close",
            "idle": "fan_bypass_auto",
            "disabled": "fan_bypass_auto",
        }[desired_mode]

        if (
            self._last_bypass_command.get(device_id) != bypass_cmd
            and desired_mode != prev_mode
        ):
            await self.ramses_commands.send_command(device_id, bypass_cmd)
            self._last_bypass_change[device_id] = now
            self._last_bypass_command[device_id] = bypass_cmd

        self._mode[device_id] = desired_mode

        # Fan speed demand only during cooling
        effective_speed_note = "no_speed_change"
        if desired_mode == "cooling":
            allow_speed = await self._allow_speed_increase(device_id, entity_states)
            if allow_speed:
                desired_speed = self._get_desired_speed_option(device_id)
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
                effective_speed_note = "gated_by_humidity_or_co2"
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
        self._mode[device_id] = "disabled"
        # Reset bypass change timestamp so the first mode change after
        # re-enabling is not blocked by the min-interval guard.
        self._last_bypass_change.pop(device_id, None)
        self._last_bypass_command.pop(device_id, None)

        attrs = {"mode": "disabled", "reason": reason}
        self._set_active_indicator(device_id, False, attrs)
        self._set_status_sensor(device_id, "disabled", attrs)

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

    async def _allow_speed_increase(
        self, device_id: str, entity_states: Mapping[str, float | bool]
    ) -> bool:
        # Humidity gate: within min/max AND humidity_control not active
        if bool(entity_states.get("dehumidifying_active")):
            return False

        indoor_rh = float(entity_states["indoor_rh"])
        min_rh = float(entity_states["min_rh"])
        max_rh = float(entity_states["max_rh"])

        humidity_ok = min_rh <= indoor_rh <= max_rh

        # Zones/areas: include enabled area sensors from sensor_control
        merged: dict[str, Any] = dict(self.config_entry.data or {})
        merged.update(self.config_entry.options or {})
        sensor_control_section = get_migrated_feature_section(merged, "sensor_control")
        if isinstance(sensor_control_section, dict):
            device_section = get_sensor_control_device_section(
                sensor_control_section, device_id
            )
            area_sensors = device_section.get(SENSOR_CONTROL_AREA_SENSORS_KEY)
            if isinstance(area_sensors, list):
                for area in area_sensors:
                    if not isinstance(area, dict) or area.get("enabled") is False:
                        continue
                    entity_id = str(area.get("humidity_entity") or "").strip()
                    if not entity_id:
                        continue
                    st = self.hass.states.get(entity_id)
                    if not st or st.state in {"unavailable", "unknown"}:
                        continue
                    try:
                        value = float(st.state)
                    except TypeError, ValueError:
                        continue
                    if not (min_rh <= value <= max_rh):
                        humidity_ok = False
                        break

        if not humidity_ok:
            return False

        # CO2 gate: if co2_control is active/triggered, do not request speed.
        if bool(entity_states.get("co2_active")):
            return False

        # Extra check: internal_triggered attribute, if present
        device_key = device_id.replace(":", "_")
        zone_status = self.hass.states.get(f"sensor.co2_zone_status_{device_key}")
        if zone_status and zone_status.attributes.get("internal_triggered") is True:
            return False

        return True

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


__all__ = ["TempControlAutomationManager"]
