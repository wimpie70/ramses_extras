from __future__ import annotations

from collections.abc import Callable
from typing import Any

import voluptuous as vol
from homeassistant.helpers import selector


def get_group_options(device_id: str) -> list[selector.SelectOptionDict]:
    """Return group options for FAN devices.

    The options are generic and do not depend on the specific device yet, but the
    device_id is accepted for future extensibility.
    """
    return [
        selector.SelectOptionDict(
            value="internal_fan_sensors", label="Internal fan sensors"
        ),
        selector.SelectOptionDict(value="area_sensors", label="Area sensors"),
        selector.SelectOptionDict(value="zones", label="Zones"),
        selector.SelectOptionDict(value="rems", label="REMs"),
        selector.SelectOptionDict(value="done", label="Finish editing device"),
    ]


def _source_from_input(
    data: dict[str, Any], kind_key: str, ent_key: str, allow_none: bool
) -> dict[str, Any]:
    """Build a source descriptor from form input.

    This mirrors the logic previously in the sensor_control config flow.
    """
    kind = str(data.get(kind_key) or "internal")
    if kind == "none" and allow_none:
        return {"kind": "none"}
    if kind == "external":
        ent = data.get(ent_key)
        if ent:
            return {"kind": "external", "entity_id": str(ent)}
        # No valid external entity selected, fall back to internal
        return {"kind": "internal"}
    return {"kind": "internal"}


def _abs_temp_part_from_input(
    data: dict[str, Any], kind_key: str, ent_key: str
) -> dict[str, Any]:
    """Build temperature-side input for absolute humidity from form input.

    kind options:
    - "internal": use internal temperature sensor
    - "external_temp": use external temperature entity
    - "external_abs": use external absolute humidity entity directly
    """
    kind = str(data.get(kind_key) or "internal")
    ent = data.get(ent_key)

    if kind == "internal":
        return {"kind": "internal"}

    if kind in {"external_temp", "external_abs", "external"}:
        if ent:
            # "external" from older configs is treated as "external_temp"
            normalized = "external_temp" if kind == "external" else kind
            return {"kind": normalized, "entity_id": str(ent)}
        # No valid external entity selected, fall back to internal
        return {"kind": "internal"}

    return {"kind": "internal"}


def _abs_humidity_part_from_input(
    data: dict[str, Any], kind_key: str, ent_key: str
) -> dict[str, Any]:
    """Build humidity-side input for absolute humidity from form input.

    kind options:
    - "internal": use internal relative humidity sensor
    - "external": use external relative humidity sensor
    - "none": do not use humidity (metric may be disabled or direct abs)
    """
    kind = str(data.get(kind_key) or "internal")
    ent = data.get(ent_key)

    if kind == "internal":
        return {"kind": "internal"}

    if kind == "external":
        if ent:
            return {"kind": "external", "entity_id": str(ent)}
        return {"kind": "internal"}

    if kind == "none":
        return {"kind": "none"}

    return {"kind": "internal"}


def _get_kind(
    device_sources: dict[str, dict[str, Any]], metric: str, default: str = "internal"
) -> str:
    raw = device_sources.get(metric) or {}
    kind = raw.get("kind")
    return str(kind) if kind else default


def _get_entity(device_sources: dict[str, dict[str, Any]], metric: str) -> str | None:
    raw = device_sources.get(metric) or {}
    ent = raw.get("entity_id")
    return str(ent) if ent else None


def _get_abs_part(
    device_abs_inputs: dict[str, dict[str, Any]], metric: str, part: str
) -> dict[str, Any]:
    metric_cfg = device_abs_inputs.get(metric) or {}
    part_cfg = metric_cfg.get(part) or {}
    if not isinstance(part_cfg, dict):
        return {}
    return part_cfg


def _get_abs_kind(
    device_abs_inputs: dict[str, dict[str, Any]], metric: str, part: str
) -> str:
    return str(_get_abs_part(device_abs_inputs, metric, part).get("kind") or "internal")


def _get_abs_entity(
    device_abs_inputs: dict[str, dict[str, Any]], metric: str, part: str
) -> str | None:
    ent = _get_abs_part(device_abs_inputs, metric, part).get("entity_id")
    return str(ent) if ent else None


def handle_group_submission(
    group_stage: str,
    user_input: dict[str, Any],
    device_sources: dict[str, dict[str, Any]],
    device_abs_inputs: dict[str, dict[str, Any]],
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    """Apply submitted values for a group to the device mappings.

    Returns updated (device_sources, device_abs_inputs).
    """
    # Work on local copies to avoid unexpected side effects
    new_sources = dict(device_sources)
    new_abs = dict(device_abs_inputs)

    if group_stage == "indoor_basic":
        new_sources["indoor_temperature"] = _source_from_input(
            user_input,
            "indoor_temperature_kind",
            "indoor_temperature_entity",
            False,
        )
        new_sources["indoor_humidity"] = _source_from_input(
            user_input,
            "indoor_humidity_kind",
            "indoor_humidity_entity",
            False,
        )
    elif group_stage == "outdoor_basic":
        new_sources["outdoor_temperature"] = _source_from_input(
            user_input,
            "outdoor_temperature_kind",
            "outdoor_temperature_entity",
            False,
        )
        new_sources["outdoor_humidity"] = _source_from_input(
            user_input,
            "outdoor_humidity_kind",
            "outdoor_humidity_entity",
            False,
        )
    elif group_stage == "co2":
        new_sources["co2"] = _source_from_input(
            user_input,
            "co2_kind",
            "co2_entity",
            True,
        )
    elif group_stage == "indoor_abs":
        temp_cfg = _abs_temp_part_from_input(
            user_input,
            "indoor_abs_humidity_temperature_kind",
            "indoor_abs_humidity_temperature_entity",
        )
        hum_cfg = _abs_humidity_part_from_input(
            user_input,
            "indoor_abs_humidity_humidity_kind",
            "indoor_abs_humidity_humidity_entity",
        )

        if temp_cfg.get("kind") == "external_abs":
            hum_cfg = {"kind": "none"}
        elif hum_cfg.get("kind") == "none":
            temp_cfg = {"kind": "none"}

        new_abs["indoor_abs_humidity"] = {
            "temperature": temp_cfg,
            "humidity": hum_cfg,
        }
    elif group_stage == "outdoor_abs":
        temp_cfg = _abs_temp_part_from_input(
            user_input,
            "outdoor_abs_humidity_temperature_kind",
            "outdoor_abs_humidity_temperature_entity",
        )
        hum_cfg = _abs_humidity_part_from_input(
            user_input,
            "outdoor_abs_humidity_humidity_kind",
            "outdoor_abs_humidity_humidity_entity",
        )

        if temp_cfg.get("kind") == "external_abs":
            hum_cfg = {"kind": "none"}
        elif hum_cfg.get("kind") == "none":
            temp_cfg = {"kind": "none"}

        new_abs["outdoor_abs_humidity"] = {
            "temperature": temp_cfg,
            "humidity": hum_cfg,
        }

    return new_sources, new_abs


def build_group_schema(
    group_stage: str,
    device_sources: dict[str, dict[str, Any]],
    device_abs_inputs: dict[str, dict[str, Any]],
    kind_options: list[selector.SelectOptionDict],
    kind_options_with_none: list[selector.SelectOptionDict],
    sensor_selector: selector.EntitySelector,
    translate: Callable[[str, str], str] | None = None,
) -> tuple[vol.Schema, str]:
    """Return the schema and info suffix for a given group.

    This mirrors the "per-group schemas" section from the original config flow.
    """
    if group_stage == "indoor_basic":
        indoor_temp_default = _get_entity(device_sources, "indoor_temperature")
        indoor_hum_default = _get_entity(device_sources, "indoor_humidity")

        indoor_temp_key = (
            vol.Optional("indoor_temperature_entity")
            if indoor_temp_default is None
            else vol.Optional("indoor_temperature_entity", default=indoor_temp_default)
        )
        indoor_hum_key = (
            vol.Optional("indoor_humidity_entity")
            if indoor_hum_default is None
            else vol.Optional("indoor_humidity_entity", default=indoor_hum_default)
        )

        schema = vol.Schema(
            {
                vol.Required(
                    "indoor_temperature_kind",
                    default=_get_kind(device_sources, "indoor_temperature"),
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=kind_options,
                        multiple=False,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                indoor_temp_key: sensor_selector,
                vol.Required(
                    "indoor_humidity_kind",
                    default=_get_kind(device_sources, "indoor_humidity"),
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=kind_options,
                        multiple=False,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                indoor_hum_key: sensor_selector,
            }
        )
        info_suffix = (
            translate("indoor_basic", "Indoor temperature and humidity sources.")
            if translate
            else "Indoor temperature and humidity sources."
        )
    elif group_stage == "outdoor_basic":
        outdoor_temp_default = _get_entity(device_sources, "outdoor_temperature")
        outdoor_hum_default = _get_entity(device_sources, "outdoor_humidity")

        outdoor_temp_key = (
            vol.Optional("outdoor_temperature_entity")
            if outdoor_temp_default is None
            else vol.Optional(
                "outdoor_temperature_entity", default=outdoor_temp_default
            )
        )
        outdoor_hum_key = (
            vol.Optional("outdoor_humidity_entity")
            if outdoor_hum_default is None
            else vol.Optional("outdoor_humidity_entity", default=outdoor_hum_default)
        )

        schema = vol.Schema(
            {
                vol.Required(
                    "outdoor_temperature_kind",
                    default=_get_kind(device_sources, "outdoor_temperature"),
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=kind_options,
                        multiple=False,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                outdoor_temp_key: sensor_selector,
                vol.Required(
                    "outdoor_humidity_kind",
                    default=_get_kind(device_sources, "outdoor_humidity"),
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=kind_options,
                        multiple=False,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                outdoor_hum_key: sensor_selector,
            }
        )
        info_suffix = (
            translate("outdoor_basic", "Outdoor temperature and humidity sources.")
            if translate
            else "Outdoor temperature and humidity sources."
        )
    elif group_stage == "co2":
        co2_default = _get_entity(device_sources, "co2")
        co2_entity_key = (
            vol.Optional("co2_entity")
            if co2_default is None
            else vol.Optional("co2_entity", default=co2_default)
        )

        schema = vol.Schema(
            {
                vol.Required(
                    "co2_kind",
                    default=_get_kind(device_sources, "co2"),
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=kind_options_with_none,
                        multiple=False,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                co2_entity_key: sensor_selector,
            }
        )
        info_suffix = (
            translate(
                "co2",
                "CO2 sensor source. Tip: use the entity picker search and type 'co2'.",
            )
            if translate
            else "CO2 sensor source. Tip: use the entity picker search and type 'co2'."
        )
    elif group_stage == "indoor_abs":
        indoor_abs_temp_default = _get_abs_entity(
            device_abs_inputs, "indoor_abs_humidity", "temperature"
        )
        indoor_abs_hum_default = _get_abs_entity(
            device_abs_inputs, "indoor_abs_humidity", "humidity"
        )

        indoor_abs_temp_key = (
            vol.Optional("indoor_abs_humidity_temperature_entity")
            if indoor_abs_temp_default is None
            else vol.Optional(
                "indoor_abs_humidity_temperature_entity",
                default=indoor_abs_temp_default,
            )
        )
        indoor_abs_hum_key = (
            vol.Optional("indoor_abs_humidity_humidity_entity")
            if indoor_abs_hum_default is None
            else vol.Optional(
                "indoor_abs_humidity_humidity_entity",
                default=indoor_abs_hum_default,
            )
        )

        temp_kind_default = _get_abs_kind(
            device_abs_inputs, "indoor_abs_humidity", "temperature"
        )
        if temp_kind_default == "external":
            temp_kind_default = "external_temp"

        abs_temp_kind_options = [
            selector.SelectOptionDict(value="internal", label="Internal (temperature)"),
            selector.SelectOptionDict(
                value="external_temp", label="External temperature"
            ),
            selector.SelectOptionDict(
                value="external_abs",
                label="External absolute humidity",
            ),
        ]

        abs_hum_kind_options = [
            selector.SelectOptionDict(value="internal", label="Internal (%)"),
            selector.SelectOptionDict(value="external", label="External (%)"),
            selector.SelectOptionDict(value="none", label="None"),
        ]

        schema = vol.Schema(
            {
                vol.Required(
                    "indoor_abs_humidity_temperature_kind",
                    default=temp_kind_default,
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=abs_temp_kind_options,
                        multiple=False,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                indoor_abs_temp_key: sensor_selector,
                vol.Required(
                    "indoor_abs_humidity_humidity_kind",
                    default=_get_abs_kind(
                        device_abs_inputs, "indoor_abs_humidity", "humidity"
                    ),
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=abs_hum_kind_options,
                        multiple=False,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                indoor_abs_hum_key: sensor_selector,
            }
        )
        info_suffix = (
            translate("indoor_abs", "Indoor absolute humidity input sensors.")
            if translate
            else "Indoor absolute humidity input sensors."
        )
    elif group_stage == "outdoor_abs":
        outdoor_abs_temp_default = _get_abs_entity(
            device_abs_inputs, "outdoor_abs_humidity", "temperature"
        )
        outdoor_abs_hum_default = _get_abs_entity(
            device_abs_inputs, "outdoor_abs_humidity", "humidity"
        )

        outdoor_abs_temp_key = (
            vol.Optional("outdoor_abs_humidity_temperature_entity")
            if outdoor_abs_temp_default is None
            else vol.Optional(
                "outdoor_abs_humidity_temperature_entity",
                default=outdoor_abs_temp_default,
            )
        )
        outdoor_abs_hum_key = (
            vol.Optional("outdoor_abs_humidity_humidity_entity")
            if outdoor_abs_hum_default is None
            else vol.Optional(
                "outdoor_abs_humidity_humidity_entity",
                default=outdoor_abs_hum_default,
            )
        )

        temp_kind_default = _get_abs_kind(
            device_abs_inputs, "outdoor_abs_humidity", "temperature"
        )
        if temp_kind_default == "external":
            temp_kind_default = "external_temp"

        abs_temp_kind_options = [
            selector.SelectOptionDict(
                value="internal",
                label="Internal (temperature)",
            ),
            selector.SelectOptionDict(
                value="external_temp",
                label="External temperature",
            ),
            selector.SelectOptionDict(
                value="external_abs",
                label="External absolute humidity",
            ),
        ]

        abs_hum_kind_options = [
            selector.SelectOptionDict(value="internal", label="Internal (%)"),
            selector.SelectOptionDict(value="external", label="External (%)"),
            selector.SelectOptionDict(value="none", label="None"),
        ]

        schema = vol.Schema(
            {
                vol.Required(
                    "outdoor_abs_humidity_temperature_kind",
                    default=temp_kind_default,
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=abs_temp_kind_options,
                        multiple=False,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                outdoor_abs_temp_key: sensor_selector,
                vol.Required(
                    "outdoor_abs_humidity_humidity_kind",
                    default=_get_abs_kind(
                        device_abs_inputs, "outdoor_abs_humidity", "humidity"
                    ),
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=abs_hum_kind_options,
                        multiple=False,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                outdoor_abs_hum_key: sensor_selector,
            }
        )
        info_suffix = (
            translate("outdoor_abs", "Outdoor absolute humidity input sensors.")
            if translate
            else "Outdoor absolute humidity input sensors."
        )
    else:
        raise ValueError(f"Unsupported group_stage for FAN handler: {group_stage}")

    return schema, info_suffix


async def handle_internal_fan_sensors(
    flow: Any,
    selected_device_id: str,
    device_sources: dict[str, Any],
    device_abs_inputs: dict[str, Any],
    user_input: dict[str, Any] | None,
) -> Any:
    """Handle internal fan sensors: temp/humidity/CO2/abs humidity config."""
    import logging

    _logger = logging.getLogger(__name__)
    _logger.debug(
        "handle_internal_fan_sensors called with user_input=%s", user_input is not None
    )

    import voluptuous as vol
    from homeassistant.helpers import selector

    if user_input is not None:
        # Save all the sensor configurations
        updated_sources = dict(device_sources)
        updated_abs_inputs = dict(device_abs_inputs)

        # Indoor temperature
        updated_sources["indoor_temperature"] = _source_from_input(
            user_input, "indoor_temperature_kind", "indoor_temperature_entity", False
        )

        # Indoor humidity
        updated_sources["indoor_humidity"] = _source_from_input(
            user_input, "indoor_humidity_kind", "indoor_humidity_entity", True
        )
        # Indoor humidity spike detection settings
        updated_sources["indoor_humidity"]["spike_enabled"] = bool(
            user_input.get("indoor_humidity_spike_enabled", False)
        )
        updated_sources["indoor_humidity"]["spike_rise_percent"] = float(
            user_input.get("indoor_humidity_spike_rise_percent") or 10.0
        )
        updated_sources["indoor_humidity"]["spike_window_minutes"] = int(
            user_input.get("indoor_humidity_spike_window_minutes") or 5
        )

        # Outdoor temperature
        updated_sources["outdoor_temperature"] = _source_from_input(
            user_input, "outdoor_temperature_kind", "outdoor_temperature_entity", True
        )

        # Outdoor humidity
        updated_sources["outdoor_humidity"] = _source_from_input(
            user_input, "outdoor_humidity_kind", "outdoor_humidity_entity", True
        )

        # CO2
        updated_sources["co2"] = _source_from_input(
            user_input, "co2_kind", "co2_entity", True
        )

        # Indoor absolute humidity
        updated_abs_inputs["indoor_abs_humidity"] = {
            "temperature": _source_from_input(
                user_input,
                "indoor_abs_humidity_temperature_kind",
                "indoor_abs_humidity_temperature_entity",
                False,
            ),
            "humidity": _source_from_input(
                user_input,
                "indoor_abs_humidity_humidity_kind",
                "indoor_abs_humidity_humidity_entity",
                True,
            ),
        }

        # Outdoor absolute humidity
        updated_abs_inputs["outdoor_abs_humidity"] = {
            "temperature": _source_from_input(
                user_input,
                "outdoor_abs_humidity_temperature_kind",
                "outdoor_abs_humidity_temperature_entity",
                False,
            ),
            "humidity": _source_from_input(
                user_input,
                "outdoor_abs_humidity_humidity_kind",
                "outdoor_abs_humidity_humidity_entity",
                True,
            ),
        }

        # Update the config
        from ....framework.helpers.config.migration import (
            get_migrated_feature_section,
        )
        from ....framework.helpers.config.model import (
            SENSOR_CONTROL_ABS_HUMIDITY_INPUTS_KEY,
            SENSOR_CONTROL_SOURCES_KEY,
            normalize_device_id,
            set_feature_section,
        )

        options = dict(flow._config_entry.options)
        sensor_control_section = get_migrated_feature_section(options, "sensor_control")
        devices_config = sensor_control_section.get("devices", {})
        # Use normalize_device_id (colons) to match the migrated section keys
        norm_device_id = normalize_device_id(selected_device_id)
        device_config = devices_config.get(norm_device_id, {})

        device_config[SENSOR_CONTROL_SOURCES_KEY] = updated_sources
        device_config[SENSOR_CONTROL_ABS_HUMIDITY_INPUTS_KEY] = updated_abs_inputs
        devices_config[norm_device_id] = device_config
        sensor_control_section["devices"] = devices_config

        # Use set_feature_section to update the config
        set_feature_section(options, "sensor_control", sensor_control_section)
        flow.hass.config_entries.async_update_entry(flow._config_entry, options=options)

        # Return to group selection
        flow._sensor_control_group_stage = "select_group"
        from ..config_flow import async_step_sensor_control_config

        return await async_step_sensor_control_config(flow, None)

    # Build the form schema
    sensor_selector = selector.EntitySelector(
        selector.EntitySelectorConfig(domain=["sensor", "number", "input_number"])
    )

    # Get default values
    indoor_temp_cfg = device_sources.get("indoor_temperature", {})
    indoor_hum_cfg = device_sources.get("indoor_humidity", {})
    indoor_hum_spike_enabled = bool(indoor_hum_cfg.get("spike_enabled", False))
    indoor_hum_spike_rise = float(indoor_hum_cfg.get("spike_rise_percent", 10.0))
    indoor_hum_spike_window = int(indoor_hum_cfg.get("spike_window_minutes", 5))
    outdoor_temp_cfg = device_sources.get("outdoor_temperature", {})
    outdoor_hum_cfg = device_sources.get("outdoor_humidity", {})
    co2_cfg = device_sources.get("co2", {})
    indoor_abs_cfg = device_abs_inputs.get("indoor_abs_humidity", {})
    outdoor_abs_cfg = device_abs_inputs.get("outdoor_abs_humidity", {})

    # Temperature kind options
    temp_kind_options = [
        selector.SelectOptionDict(value="internal", label="Internal (from FAN)"),
        selector.SelectOptionDict(value="external", label="External (from HA entity)"),
        selector.SelectOptionDict(value="derived", label="Derived (calculated)"),
    ]

    # Humidity kind options
    hum_kind_options = [
        selector.SelectOptionDict(value="internal", label="Internal (from FAN)"),
        selector.SelectOptionDict(value="external", label="External (from HA entity)"),
        selector.SelectOptionDict(value="none", label="None (disabled)"),
    ]

    # CO2 kind options
    co2_kind_options = [
        selector.SelectOptionDict(value="internal", label="Internal (from FAN)"),
        selector.SelectOptionDict(value="external", label="External (from HA entity)"),
        selector.SelectOptionDict(value="none", label="None (disabled)"),
    ]

    # Absolute humidity temperature kind options
    abs_temp_kind_options = [
        selector.SelectOptionDict(value="internal", label="Internal (from FAN)"),
        selector.SelectOptionDict(value="external", label="External (from HA entity)"),
        selector.SelectOptionDict(
            value="external_temp", label="External temperature only"
        ),
        selector.SelectOptionDict(
            value="external_abs", label="External absolute humidity"
        ),
    ]

    # Absolute humidity humidity kind options
    abs_hum_kind_options = [
        selector.SelectOptionDict(value="internal", label="Internal (from FAN)"),
        selector.SelectOptionDict(value="external", label="External (from HA entity)"),
        selector.SelectOptionDict(value="none", label="None (disabled)"),
    ]

    schema = vol.Schema(
        {
            # Indoor sensors
            vol.Required(
                "indoor_temperature_kind",
                default=indoor_temp_cfg.get("kind", "internal"),
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=temp_kind_options, mode="dropdown"
                )
            ),
            vol.Optional(
                "indoor_temperature_entity",
                default=indoor_temp_cfg.get("entity_id"),
            ): sensor_selector,
            vol.Required(
                "indoor_humidity_kind", default=indoor_hum_cfg.get("kind", "internal")
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(options=hum_kind_options, mode="dropdown")
            ),
            vol.Optional(
                "indoor_humidity_entity",
                default=indoor_hum_cfg.get("entity_id"),
            ): sensor_selector,
            # Indoor humidity spike detection
            vol.Required(
                "indoor_humidity_spike_enabled", default=indoor_hum_spike_enabled
            ): selector.BooleanSelector(),
            vol.Required(
                "indoor_humidity_spike_rise_percent",
                default=indoor_hum_spike_rise,
            ): vol.All(vol.Coerce(float), vol.Range(min=1, max=100)),
            vol.Required(
                "indoor_humidity_spike_window_minutes",
                default=indoor_hum_spike_window,
            ): vol.All(vol.Coerce(int), vol.Range(min=1, max=60)),
            # Outdoor sensors
            vol.Required(
                "outdoor_temperature_kind",
                default=outdoor_temp_cfg.get("kind", "internal"),
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=temp_kind_options, mode="dropdown"
                )
            ),
            vol.Optional(
                "outdoor_temperature_entity",
                default=outdoor_temp_cfg.get("entity_id"),
            ): sensor_selector,
            vol.Required(
                "outdoor_humidity_kind", default=outdoor_hum_cfg.get("kind", "internal")
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(options=hum_kind_options, mode="dropdown")
            ),
            vol.Optional(
                "outdoor_humidity_entity",
                default=outdoor_hum_cfg.get("entity_id"),
            ): sensor_selector,
            # CO2
            vol.Required(
                "co2_kind", default=co2_cfg.get("kind", "internal")
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(options=co2_kind_options, mode="dropdown")
            ),
            vol.Optional(
                "co2_entity", default=co2_cfg.get("entity_id")
            ): sensor_selector,
            # Indoor absolute humidity
            vol.Required(
                "indoor_abs_humidity_temperature_kind",
                default=indoor_abs_cfg.get("temperature", {}).get("kind", "internal"),
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=abs_temp_kind_options, mode="dropdown"
                )
            ),
            vol.Optional(
                "indoor_abs_humidity_temperature_entity",
                default=indoor_abs_cfg.get("temperature", {}).get("entity_id"),
            ): sensor_selector,
            vol.Required(
                "indoor_abs_humidity_humidity_kind",
                default=indoor_abs_cfg.get("humidity", {}).get("kind", "internal"),
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=abs_hum_kind_options, mode="dropdown"
                )
            ),
            vol.Optional(
                "indoor_abs_humidity_humidity_entity",
                default=indoor_abs_cfg.get("humidity", {}).get("entity_id"),
            ): sensor_selector,
            # Outdoor absolute humidity
            vol.Required(
                "outdoor_abs_humidity_temperature_kind",
                default=outdoor_abs_cfg.get("temperature", {}).get("kind", "internal"),
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=abs_temp_kind_options, mode="dropdown"
                )
            ),
            vol.Optional(
                "outdoor_abs_humidity_temperature_entity",
                default=outdoor_abs_cfg.get("temperature", {}).get("entity_id"),
            ): sensor_selector,
            vol.Required(
                "outdoor_abs_humidity_humidity_kind",
                default=outdoor_abs_cfg.get("humidity", {}).get("kind", "internal"),
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=abs_hum_kind_options, mode="dropdown"
                )
            ),
            vol.Optional(
                "outdoor_abs_humidity_humidity_entity",
                default=outdoor_abs_cfg.get("humidity", {}).get("entity_id"),
            ): sensor_selector,
        }
    )

    info_text = (
        "Internal Fan Sensors\n\n"
        f"Configure internal sensor sources for device: `{selected_device_id}`\n\n"
        "Define what sensors should be used. Instead of the standard internal sensors"
        " you can map other (external) sensors of your choice."
    )

    _logger.debug("Returning form for internal_fan_sensors")
    return flow.async_show_form(
        step_id="feature_config",
        data_schema=schema,
        description_placeholders={"info": info_text},
    )
