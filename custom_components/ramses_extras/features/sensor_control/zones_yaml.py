"""Zone configuration YAML export/import utilities.

Provides validated YAML handling for zones configuration,
enabling advanced users to export and import zone setups.
"""

from __future__ import annotations

from typing import Any

import voluptuous as vol
import yaml

from ...framework.helpers.config.import_validation import (
    register_config_schema,
    register_config_validator,
)
from .const import FEATURE_ID

# Schema for validating zone entries on import
ZONE_ENTRY_SCHEMA = vol.Schema(
    {
        vol.Required("zone_id"): str,
        vol.Required("type"): vol.In(
            ["orcon_native", "custom_valve", "shelly_2pm_gen3", "paired_valves"]
        ),
        vol.Optional("enabled", default=True): bool,
        vol.Optional("fan_id"): str,
        # orcon_native specific
        vol.Optional("native_zone_id"): vol.Maybe(str),
        # custom_valve / shelly_2pm_gen3 specific
        vol.Optional("open_entity"): vol.Maybe(str),
        vol.Optional("close_entity"): vol.Maybe(str),
        vol.Optional("position_entity"): vol.Maybe(str),
        # paired_valves specific (inlet/outlet valve pairs)
        vol.Optional("inlet_valve_entity"): vol.Maybe(str),
        vol.Optional("outlet_valve_entity"): vol.Maybe(str),
        vol.Optional("min_position", default=0): vol.All(
            int, vol.Range(min=0, max=100)
        ),
        vol.Optional("max_position", default=100): vol.All(
            int, vol.Range(min=0, max=100)
        ),
        # extra_config for valve homing and behavior
        vol.Optional("extra_config"): vol.Schema(
            {
                vol.Optional("home_mode"): vol.In(["always", "on_demand", "never"]),
                vol.Optional("home_position"): vol.All(int, vol.Range(min=0, max=100)),
                vol.Optional("home_tolerance"): vol.All(int, vol.Range(min=0, max=100)),
                vol.Optional("home_timeout_s"): vol.All(
                    vol.Coerce(float), vol.Range(min=0)
                ),
                vol.Optional("home_poll_s"): vol.All(
                    vol.Coerce(float), vol.Range(min=0.1)
                ),
                vol.Optional("home_interval_s"): vol.All(
                    vol.Coerce(float), vol.Range(min=0)
                ),
                vol.Optional("invert_logic"): bool,
            },
            extra=vol.ALLOW_EXTRA,
        ),
    },
    extra=vol.PREVENT_EXTRA,
)

ZONES_CONFIG_SCHEMA = vol.Schema(
    {
        vol.Optional("version", default=1): int,
        vol.Optional("fan_id"): str,
        vol.Required("zones"): [ZONE_ENTRY_SCHEMA],
    }
)


def zones_validator(section: dict, hass: Any | None = None) -> list[str]:
    """Validate zones configuration section.

    :param section: The zones configuration section
    :param hass: Home Assistant instance (optional)
    :return: List of validation error messages
    """
    errors = []

    zones = section.get("zones", [])
    if not isinstance(zones, list):
        errors.append("zones must be a list")
        return errors

    for zone in zones:
        if not isinstance(zone, dict):
            errors.append("zone entry must be a dict")
            continue

        zone_id = zone.get("zone_id")
        if not zone_id:
            errors.append("missing zone_id")
            continue

        zone_type = zone.get("type")
        if zone_type not in (
            "orcon_native",
            "custom_valve",
            "shelly_2pm_gen3",
            "paired_valves",
        ):
            errors.append(f"Zone '{zone_id}': invalid type '{zone_type}'")

        min_pos = zone.get("min_position", 0)
        max_pos = zone.get("max_position", 100)
        if min_pos > max_pos:
            errors.append(
                f"Zone '{zone_id}': min_position ({min_pos}) > max_position ({max_pos})"
            )

    return errors


def export_zones_to_yaml(
    zones: list[dict[str, Any]],
    fan_id: str | None = None,
) -> str:
    """Export zones configuration to YAML format.

    :param zones: List of zone configuration dictionaries
    :param fan_id: Optional FAN ID to include in metadata
    :return: YAML string representation of zones config
    """
    export_data: dict[str, Any] = {
        "version": 1,
        "zones": zones,
    }

    if fan_id:
        export_data["fan_id"] = fan_id

    return str(
        yaml.safe_dump(
            export_data,
            sort_keys=False,
            allow_unicode=True,
            default_flow_style=False,
        )
    )


def parse_zones_yaml(yaml_content: str) -> dict[str, Any]:
    """Parse and validate zones YAML content.

    :param yaml_content: YAML string containing zones configuration
    :return: Validated zones configuration dictionary
    :raises ValueError: If YAML is invalid or doesn't match schema
    """
    try:
        parsed = yaml.safe_load(yaml_content)
    except yaml.YAMLError as e:
        raise ValueError(f"Invalid YAML syntax: {e}") from e

    if not isinstance(parsed, dict):
        raise ValueError("YAML content must be a dictionary")

    # Validate against schema
    try:
        validated: dict[str, Any] = ZONES_CONFIG_SCHEMA(parsed)
    except vol.MultipleInvalid as e:
        raise ValueError(f"Schema validation failed: {e}") from e

    return validated


def merge_zones_config(
    existing_zones: list[dict[str, Any]],
    imported_zones: list[dict[str, Any]],
    fan_id: str,
    *,
    overwrite_existing: bool = False,
) -> list[dict[str, Any]]:
    """Merge imported zones with existing configuration.

    :param existing_zones: Current zones configuration list
    :param imported_zones: New zones to import
    :param fan_id: FAN ID to associate with imported zones
    :param overwrite_existing: If True, replace zones with same zone_id;
                           if False, skip duplicates
    :return: Merged zones configuration list
    """
    result = list(existing_zones)

    existing_ids = {z.get("zone_id") for z in result if z.get("zone_id")}

    for zone in imported_zones:
        zone = dict(zone)  # Copy to avoid modifying original

        zone_id = zone.get("zone_id")

        if zone_id in existing_ids:
            if overwrite_existing:
                # Remove existing zone with this ID
                result = [z for z in result if not (z.get("zone_id") == zone_id)]
                result.append(zone)
            # else: skip duplicate
        else:
            result.append(zone)
            existing_ids.add(zone_id)

    return result


def validate_zone_references(
    zones: list[dict[str, Any]],
    hass: Any | None = None,
) -> list[str]:
    """Validate that zone entity references exist in Home Assistant.

    :param zones: List of zone configurations to validate
    :param hass: Optional Home Assistant instance for entity lookup
    :return: List of validation error messages (empty if all valid)
    """
    errors: list[str] = []

    if hass is None:
        # Skip entity validation if no hass instance available
        return errors

    for zone in zones:
        zone_id = zone.get("zone_id", "unknown")
        zone_type = zone.get("type")

        if zone_type in ("custom_valve", "shelly_2pm_gen3"):
            open_entity = zone.get("open_entity")
            close_entity = zone.get("close_entity")
            position_entity = zone.get("position_entity")

            if open_entity and not hass.states.get(open_entity):
                errors.append(
                    f"Zone '{zone_id}': open_entity '{open_entity}' not found"
                )
            if close_entity and not hass.states.get(close_entity):
                errors.append(
                    f"Zone '{zone_id}': close_entity '{close_entity}' not found"
                )
            if position_entity and not hass.states.get(position_entity):
                errors.append(
                    f"Zone '{zone_id}': position_entity '{position_entity}' not found"
                )

        if zone_type == "paired_valves":
            inlet_entity = zone.get("inlet_valve_entity")
            outlet_entity = zone.get("outlet_valve_entity")

            if inlet_entity and not hass.states.get(inlet_entity):
                errors.append(
                    f"Zone '{zone_id}': inlet_valve_entity '{inlet_entity}' not found"
                )
            if outlet_entity and not hass.states.get(outlet_entity):
                errors.append(
                    f"Zone '{zone_id}': outlet_valve_entity '{outlet_entity}' not found"
                )

    return errors


def load_validator() -> None:
    """Register the zones validator and schema with the framework."""
    register_config_validator("zones", zones_validator)
    register_config_schema("zones", ZONES_CONFIG_SCHEMA)


__all__ = [
    "export_zones_to_yaml",
    "parse_zones_yaml",
    "merge_zones_config",
    "validate_zone_references",
    "zones_validator",
    "ZONE_ENTRY_SCHEMA",
    "ZONES_CONFIG_SCHEMA",
    "load_validator",
]
