"""Full configuration YAML import utilities.

Provides validated YAML import for the complete ramses_extras configuration,
enabling advanced users to import full setups from YAML files.
"""

from __future__ import annotations

from typing import Any

import voluptuous as vol
import yaml

from .model import (
    CONFIG_FEATURES_KEY,
    CONFIG_ROOT_KEY,
    CONFIG_SCHEMA_VERSION_KEY,
    FEATURE_REMOTE_BINDING,
    FEATURE_SENSOR_CONTROL,
    FEATURE_ZONES,
)
from .zones_yaml import ZONE_ENTRY_SCHEMA

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


def merge_full_config(
    existing_config: dict[str, Any],
    imported_config: dict[str, Any],
    *,
    merge_strategy: str = "merge",
) -> dict[str, Any]:
    """Merge imported full config with existing configuration.

    Args:
        existing_config: Current configuration dictionary
        imported_config: New configuration to import
        merge_strategy: How to merge - "merge" (combine) or "replace" (overwrite)

    Returns:
        Merged configuration dictionary
    """
    if merge_strategy == "replace":
        return dict(imported_config)

    # Merge strategy
    result = dict(existing_config)

    # Get root sections
    existing_root = existing_config.get(CONFIG_ROOT_KEY, {})
    imported_root = imported_config.get(CONFIG_ROOT_KEY, {})

    # Merge features
    existing_features = existing_root.get(CONFIG_FEATURES_KEY, {})
    imported_features = imported_root.get(CONFIG_FEATURES_KEY, {})

    merged_features = dict(existing_features)

    for feature_id, feature_data in imported_features.items():
        if feature_id in merged_features:
            # Deep merge feature sections
            merged_features[feature_id] = _deep_merge_feature(
                merged_features[feature_id], feature_data, feature_id
            )
        else:
            merged_features[feature_id] = dict(feature_data)

    # Build result
    result[CONFIG_ROOT_KEY] = {
        CONFIG_SCHEMA_VERSION_KEY: existing_root.get(CONFIG_SCHEMA_VERSION_KEY, 1),
        CONFIG_FEATURES_KEY: merged_features,
    }

    return result


def _deep_merge_feature(
    existing: dict[str, Any],
    imported: dict[str, Any],
    feature_id: str,
) -> dict[str, Any]:
    """Deep merge a single feature section.

    Feature-specific merge logic:
    - sensor_control: merge per-device sections
    - remote_binding: merge per-FAN REM lists, avoid duplicates
    - zones: merge per-FAN zone lists, avoid duplicates
    """
    result = dict(existing)

    if feature_id == FEATURE_SENSOR_CONTROL:
        # Merge per-device sections
        for key in ["devices", "sources", "abs_humidity_inputs", "area_sensors"]:
            if key in imported:
                existing_section = result.get(key, {})
                imported_section = imported[key]
                if isinstance(existing_section, dict) and isinstance(
                    imported_section, dict
                ):
                    merged_section = dict(existing_section)
                    merged_section.update(imported_section)
                    result[key] = merged_section
                else:
                    result[key] = imported_section

    elif feature_id == FEATURE_REMOTE_BINDING:
        # Merge FAN bindings, avoiding duplicate REM IDs
        existing_fans = result.get("FANs", {})
        imported_fans = imported.get("FANs", {})

        merged_fans = dict(existing_fans)
        for fan_id, fan_data in imported_fans.items():
            if fan_id not in merged_fans:
                merged_fans[fan_id] = fan_data
            else:
                # Merge REMs, avoiding duplicates by rem_id
                existing_rems = {
                    r.get("rem_id"): r
                    for r in merged_fans[fan_id].get("REMs", [])
                    if r.get("rem_id")
                }
                for rem in fan_data.get("REMs", []):
                    rem_id = rem.get("rem_id")
                    if rem_id and rem_id not in existing_rems:
                        if "REMs" not in merged_fans[fan_id]:
                            merged_fans[fan_id]["REMs"] = []
                        merged_fans[fan_id]["REMs"].append(rem)
                        existing_rems[rem_id] = rem

        result["FANs"] = merged_fans

    elif feature_id == FEATURE_ZONES:
        # Merge zones per FAN, avoiding duplicate zone_ids
        existing_fans = result.get("FANs", {})
        imported_fans = imported.get("FANs", {})

        merged_fans = dict(existing_fans)
        for fan_id, zones in imported_fans.items():
            if fan_id not in merged_fans:
                merged_fans[fan_id] = list(zones)
            else:
                # Merge zones, avoiding duplicates by zone_id
                existing_zone_ids = {
                    z.get("zone_id"): z for z in merged_fans[fan_id] if z.get("zone_id")
                }
                for zone in zones:
                    zone_id = zone.get("zone_id")
                    if zone_id and zone_id not in existing_zone_ids:
                        merged_fans[fan_id].append(zone)
                        existing_zone_ids[zone_id] = zone

        result["FANs"] = merged_fans

    else:
        # Generic shallow merge for unknown features
        result.update(imported)

    return result


def validate_full_config_import(
    config: dict[str, Any],
    hass: Any | None = None,
) -> list[str]:
    """Validate a full configuration import.

    Args:
        config: Configuration dictionary to validate
        hass: Optional Home Assistant instance for entity/device validation

    Returns:
        List of validation warnings/errors (empty if valid)
    """
    errors: list[str] = []

    root = config.get(CONFIG_ROOT_KEY, {})
    features = root.get(CONFIG_FEATURES_KEY, {})

    # Validate zones
    zones = features.get(FEATURE_ZONES, {})
    for fan_id, zone_list in zones.get("FANs", {}).items():
        for zone in zone_list:
            zone_id = zone.get("zone_id")
            zone_type = zone.get("type")

            # Validate min/max positions for controllable valves
            if zone_type in ("custom_valve", "shelly_2pm_gen3"):
                min_pos = zone.get("min_position", 0)
                max_pos = zone.get("max_position", 100)
                if min_pos > max_pos:
                    errors.append(
                        f"Zone '{zone_id}' (FAN {fan_id}): "
                        f"min_position ({min_pos}) > max_position ({max_pos})"
                    )
                if not (0 <= min_pos <= 100) or not (0 <= max_pos <= 100):
                    errors.append(
                        f"Zone '{zone_id}' (FAN {fan_id}): "
                        f"positions must be between 0-100"
                    )

    # Validate remote bindings
    bindings = features.get(FEATURE_REMOTE_BINDING, {})
    seen_rems: set[str] = set()
    for fan_id, fan_data in bindings.get("FANs", {}).items():
        for rem in fan_data.get("REMs", []):
            rem_id = rem.get("rem_id")
            if rem_id:
                if rem_id in seen_rems:
                    # Warn about duplicate REM assignments
                    errors.append(
                        f"REM '{rem_id}' assigned to multiple FANs "
                        f"(conflict with FAN {fan_id})"
                    )
                seen_rems.add(rem_id)

    # Validate sensor_control references if hass available
    if hass is not None:
        sensor_control = features.get(FEATURE_SENSOR_CONTROL, {})
        for fan_id, areas in sensor_control.get("area_sensors", {}).items():
            for area in areas:
                for entity_key in [
                    "temperature_entity",
                    "humidity_entity",
                    "co2_entity",
                ]:
                    entity_id = area.get(entity_key)
                    if entity_id and not hass.states.get(entity_id):
                        errors.append(
                            f"Area '{area.get('source_id')}' (FAN {fan_id}): "
                            f"{entity_key} '{entity_id}' not found"
                        )

    return errors


__all__ = [
    "merge_full_config",
    "parse_full_config_yaml",
    "RAMSES_EXTRAS_CONFIG_SCHEMA",
    "validate_full_config_import",
]
