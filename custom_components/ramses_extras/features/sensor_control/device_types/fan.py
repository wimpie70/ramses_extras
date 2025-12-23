from __future__ import annotations

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
            value="indoor_basic", label="Indoor temperature & humidity"
        ),
        selector.SelectOptionDict(
            value="outdoor_basic", label="Outdoor temperature & humidity"
        ),
        selector.SelectOptionDict(value="co2", label="CO2"),
        selector.SelectOptionDict(
            value="indoor_abs", label="Indoor absolute humidity inputs"
        ),
        selector.SelectOptionDict(
            value="outdoor_abs", label="Outdoor absolute humidity inputs"
        ),
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
        info_suffix = "Indoor temperature and humidity sources."
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
        info_suffix = "Outdoor temperature and humidity sources."
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
        info_suffix = "CO2 sensor source."
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
        info_suffix = "Indoor absolute humidity input sensors."
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
        info_suffix = "Outdoor absolute humidity input sensors."
    else:
        raise ValueError(f"Unsupported group_stage for FAN handler: {group_stage}")

    return schema, info_suffix
