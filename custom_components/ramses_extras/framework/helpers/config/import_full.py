"""Full configuration YAML import utilities.

Provides validated YAML import for the complete ramses_extras configuration,
enabling advanced users to import full setups from YAML files.

Each feature validates its own section via registered validators.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import voluptuous as vol
import yaml

from .import_validation import (
    register_config_validator,
    validate_import_config,
)
from .model import (
    CONFIG_FEATURES_KEY,
    CONFIG_ROOT_KEY,
    CONFIG_SCHEMA_VERSION_KEY,
    FEATURE_REMOTE_BINDING,
    FEATURE_SENSOR_CONTROL,
    FEATURE_ZONES,
)
from .zones_yaml import ZONE_ENTRY_SCHEMA

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant


# Schema for sensor_control sources
SENSOR_SOURCE_SCHEMA = vol.Schema(
    {
        vol.Required("kind"): vol.In(["internal", "external"]),
        vol.Optional("entity_id"): vol.Maybe(str),
    },
    extra=vol.ALLOW_EXTRA,
)

# Schema for abs_humidity_inputs
ABS_HUMIDITY_INPUT_SCHEMA = vol.Schema(
    {
        vol.Required("temperature"): SENSOR_SOURCE_SCHEMA,
        vol.Required("humidity"): SENSOR_SOURCE_SCHEMA,
    },
    extra=vol.ALLOW_EXTRA,
)

# Schema for area_sensors
AREA_SENSOR_SCHEMA = vol.Schema(
    {
        vol.Required("source_id"): str,
        vol.Optional("label"): str,
        vol.Optional("enabled", default=True): bool,
        vol.Optional("zone_id"): vol.Maybe(str),
        vol.Optional("temperature_entity"): vol.Maybe(str),
        vol.Optional("humidity_entity"): vol.Maybe(str),
        vol.Optional("area_co2_enabled", default=False): bool,
        vol.Optional("co2_entity"): vol.Maybe(str),
        vol.Optional("co2_threshold"): vol.Maybe(vol.All(int, vol.Range(min=0))),
    },
    extra=vol.ALLOW_EXTRA,
)

# Schema for sensor_control feature section
SENSOR_CONTROL_SCHEMA = vol.Schema(
    {
        vol.Optional("devices"): vol.Schema(
            {str: vol.Any(dict, list)}, extra=vol.ALLOW_EXTRA
        ),
        vol.Optional("sources"): vol.Schema(
            {str: vol.Any(dict, list)}, extra=vol.ALLOW_EXTRA
        ),
        vol.Optional("abs_humidity_inputs"): vol.Schema(
            {str: ABS_HUMIDITY_INPUT_SCHEMA}, extra=vol.ALLOW_EXTRA
        ),
        vol.Optional("area_sensors"): vol.Schema(
            {str: [AREA_SENSOR_SCHEMA]}, extra=vol.ALLOW_EXTRA
        ),
    },
    extra=vol.ALLOW_EXTRA,
)

# Schema for remote_binding REM entries
REM_BINDING_SCHEMA = vol.Schema(
    {
        vol.Required("rem_id"): str,
        vol.Optional("role", default="primary"): vol.In(
            ["primary", "secondary", "boost_only"]
        ),
        vol.Optional("enabled", default=True): bool,
        vol.Optional("source", default="manual_config"): str,
    },
    extra=vol.ALLOW_EXTRA,
)

# Schema for remote_binding feature section
REMOTE_BINDING_SCHEMA = vol.Schema(
    {
        vol.Optional("FANs"): vol.Schema(
            {
                str: {
                    vol.Optional("REMs"): [REM_BINDING_SCHEMA],
                }
            },
            extra=vol.ALLOW_EXTRA,
        ),
    },
    extra=vol.ALLOW_EXTRA,
)

# Schema for zones feature section
ZONES_SCHEMA = vol.Schema(
    {
        vol.Optional("FANs"): vol.Schema(
            {
                str: [ZONE_ENTRY_SCHEMA],
            },
            extra=vol.ALLOW_EXTRA,
        ),
    },
    extra=vol.ALLOW_EXTRA,
)

# Full config schema
RAMSES_EXTRAS_CONFIG_SCHEMA = vol.Schema(
    {
        vol.Required(CONFIG_ROOT_KEY): {
            vol.Optional(CONFIG_SCHEMA_VERSION_KEY, default=1): vol.All(
                int, vol.Range(min=1, max=1)
            ),
            vol.Optional(CONFIG_FEATURES_KEY): {
                vol.Optional(FEATURE_SENSOR_CONTROL): SENSOR_CONTROL_SCHEMA,
                vol.Optional(FEATURE_REMOTE_BINDING): REMOTE_BINDING_SCHEMA,
                vol.Optional(FEATURE_ZONES): ZONES_SCHEMA,
            },
        }
    },
    extra=vol.ALLOW_EXTRA,
)


def _validate_zones_section(
    section: dict[str, Any], hass: HomeAssistant | None
) -> list[str]:
    """Validate zones feature section.

    Args:
        section: The zones feature configuration section
        hass: Optional Home Assistant instance

    Returns:
        List of validation errors (empty if valid)
    """
    errors: list[str] = []

    for fan_id, zone_list in section.get("FANs", {}).items():
        if not isinstance(zone_list, list):
            errors.append(f"FAN '{fan_id}': zones must be a list")
            continue

        for zone in zone_list:
            if not isinstance(zone, dict):
                errors.append(f"FAN '{fan_id}': invalid zone entry")
                continue

            zone_id = zone.get("zone_id")
            zone_type = zone.get("type")

            if not zone_id:
                errors.append(f"FAN '{fan_id}': zone missing zone_id")
                continue

            # Validate zone type
            valid_types = ["orcon_native", "custom_valve", "shelly_2pm_gen3"]
            if zone_type not in valid_types:
                errors.append(
                    f"Zone '{zone_id}' (FAN {fan_id}): "
                    f"invalid type '{zone_type}'. Must be one of: {valid_types}"
                )
                continue

            # Validate min/max positions for controllable valves
            if zone_type in ("custom_valve", "shelly_2pm_gen3"):
                min_pos = zone.get("min_position", 0)
                max_pos = zone.get("max_position", 100)

                if not (0 <= min_pos <= 100) or not (0 <= max_pos <= 100):
                    errors.append(
                        f"Zone '{zone_id}' (FAN {fan_id}): "
                        f"positions must be between 0-100"
                    )
                elif min_pos > max_pos:
                    errors.append(
                        f"Zone '{zone_id}' (FAN {fan_id}): "
                        f"min_position ({min_pos}) > max_position ({max_pos})"
                    )

            # Validate entity references if hass available
            if hass is not None:
                for entity_key in ["open_entity", "close_entity", "position_entity"]:
                    entity_id = zone.get(entity_key)
                    if entity_id and not hass.states.get(entity_id):
                        errors.append(
                            f"Zone '{zone_id}' (FAN {fan_id}): "
                            f"{entity_key} '{entity_id}' not found"
                        )

    return errors


def _validate_remote_binding_section(
    section: dict[str, Any], hass: HomeAssistant | None
) -> list[str]:
    """Validate remote_binding feature section.

    Args:
        section: The remote_binding feature configuration section
        hass: Optional Home Assistant instance

    Returns:
        List of validation errors (empty if valid)
    """
    errors: list[str] = []
    seen_rems: set[str] = set()

    for fan_id, fan_data in section.get("FANs", {}).items():
        if not isinstance(fan_data, dict):
            errors.append(f"FAN '{fan_id}': invalid binding data")
            continue

        rems = fan_data.get("REMs", [])
        if not isinstance(rems, list):
            errors.append(f"FAN '{fan_id}': REMs must be a list")
            continue

        for rem in rems:
            if not isinstance(rem, dict):
                errors.append(f"FAN '{fan_id}': invalid REM entry")
                continue

            rem_id = rem.get("rem_id")
            if not rem_id:
                errors.append(f"FAN '{fan_id}': REM missing rem_id")
                continue

            # Check for duplicate REM assignments
            if rem_id in seen_rems:
                errors.append(
                    f"REM '{rem_id}' assigned to multiple FANs "
                    f"(conflict with FAN {fan_id})"
                )
            seen_rems.add(rem_id)

            # Validate role
            valid_roles = ["primary", "secondary", "boost_only"]
            role = rem.get("role", "primary")
            if role not in valid_roles:
                errors.append(
                    f"REM '{rem_id}' (FAN {fan_id}): "
                    f"invalid role '{role}'. Must be one of: {valid_roles}"
                )

    return errors


def _validate_sensor_control_section(
    section: dict[str, Any], hass: HomeAssistant | None
) -> list[str]:
    """Validate sensor_control feature section.

    Args:
        section: The sensor_control feature configuration section
        hass: Optional Home Assistant instance

    Returns:
        List of validation errors (empty if valid)
    """
    errors: list[str] = []

    # Validate abs_humidity_inputs
    for input_id, input_data in section.get("abs_humidity_inputs", {}).items():
        if not isinstance(input_data, dict):
            errors.append(f"Abs humidity input '{input_id}': invalid data format")
            continue

        for sensor_type in ["temperature", "humidity"]:
            sensor_config = input_data.get(sensor_type)
            if not isinstance(sensor_config, dict):
                errors.append(
                    f"Abs humidity input '{input_id}': "
                    f"missing {sensor_type} configuration"
                )
                continue

            kind = sensor_config.get("kind")
            if kind not in ("internal", "external"):
                errors.append(
                    f"Abs humidity input '{input_id}' {sensor_type}: "
                    f"invalid kind '{kind}'. Must be 'internal' or 'external'"
                )

            # Validate entity references if hass available
            if hass is not None:
                entity_id = sensor_config.get("entity_id")
                if entity_id and not hass.states.get(entity_id):
                    errors.append(
                        f"Abs humidity input '{input_id}' {sensor_type}: "
                        f"entity '{entity_id}' not found"
                    )

    # Validate area_sensors
    for fan_id, areas in section.get("area_sensors", {}).items():
        if not isinstance(areas, list):
            errors.append(f"Area sensors FAN '{fan_id}': must be a list of areas")
            continue

        for area in areas:
            if not isinstance(area, dict):
                errors.append(f"Area sensors FAN '{fan_id}': invalid area entry")
                continue

            source_id = area.get("source_id")
            if not source_id:
                errors.append(f"Area sensors FAN '{fan_id}': area missing source_id")
                continue

            # Validate entity references if hass available
            if hass is not None:
                for entity_key in [
                    "temperature_entity",
                    "humidity_entity",
                    "co2_entity",
                ]:
                    entity_id = area.get(entity_key)
                    if entity_id and not hass.states.get(entity_id):
                        errors.append(
                            f"Area '{source_id}' (FAN {fan_id}): "
                            f"{entity_key} '{entity_id}' not found"
                        )

    return errors


# Register feature validators
register_config_validator(FEATURE_ZONES, _validate_zones_section)
register_config_validator(FEATURE_REMOTE_BINDING, _validate_remote_binding_section)
register_config_validator(FEATURE_SENSOR_CONTROL, _validate_sensor_control_section)


def parse_full_config_yaml(yaml_content: str) -> dict[str, Any]:
    """Parse and validate full ramses_extras YAML configuration.

    Args:
        yaml_content: YAML string containing full ramses_extras configuration

    Returns:
        Validated configuration dictionary

    Raises:
        ValueError: If YAML is invalid or doesn't match schema
    """
    try:
        parsed = yaml.safe_load(yaml_content)
    except yaml.YAMLError as e:
        raise ValueError(f"Invalid YAML syntax: {e}") from e

    if not isinstance(parsed, dict):
        raise ValueError("YAML content must be a dictionary")

    # Validate against schema
    try:
        validated: dict[str, Any] = RAMSES_EXTRAS_CONFIG_SCHEMA(parsed)
    except vol.MultipleInvalid as e:
        raise ValueError(f"Schema validation failed: {e}") from e

    return validated


def validate_full_config_import(
    config: dict[str, Any],
    hass: Any | None = None,
) -> list[str]:
    """Validate a full configuration import using registered validators.

    Args:
        config: Configuration dictionary to validate
        hass: Optional Home Assistant instance for entity/device validation

    Returns:
        List of validation warnings/errors (empty if valid)
    """
    from .import_validation import format_validation_errors

    result = validate_import_config(config, hass)
    return format_validation_errors(result)


def validate_full_config_import_detailed(
    config: dict[str, Any],
    hass: Any | None = None,
) -> dict[str, Any]:
    """Validate a full configuration import with detailed results.

    Args:
        config: Configuration dictionary to validate
        hass: Optional Home Assistant instance for entity/device validation

    Returns:
        Detailed validation result with per-feature breakdown:
        {
            "valid": bool,
            "framework_errors": list[str],
            "feature_errors": dict[str, list[str]],
            "total_errors": int,
        }
    """
    return validate_import_config(config, hass)


__all__ = [
    "parse_full_config_yaml",
    "RAMSES_EXTRAS_CONFIG_SCHEMA",
    "validate_full_config_import",
    "validate_full_config_import_detailed",
]
