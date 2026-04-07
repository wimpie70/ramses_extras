"""Remote binding YAML import/export and validation.

Provides validated YAML handling for remote (REM) bindings,
enabling advanced users to export and import REM configurations.
"""

from __future__ import annotations

from typing import Any, cast

import voluptuous as vol
import yaml

from ...framework.helpers.config.import_validation import (
    register_config_schema,
    register_config_validator,
)
from .const import FEATURE_ID

# Schema for validating REM entries on import
REM_ENTRY_SCHEMA = vol.Schema(
    {
        vol.Required("rem_id"): str,
        vol.Optional("enabled", default=True): bool,
        vol.Optional("source"): str,
        vol.Optional("zone_id"): str,
        vol.Optional("area_id"): str,
    },
    extra=vol.PREVENT_EXTRA,
)

FAN_REM_CONFIG_SCHEMA = vol.Schema(
    {
        vol.Required("REMs"): [REM_ENTRY_SCHEMA],
    }
)

REMOTE_BINDING_CONFIG_SCHEMA = vol.Schema(
    {
        vol.Optional("version", default=1): int,
        vol.Required("FANs"): {str: FAN_REM_CONFIG_SCHEMA},
    }
)


def remote_binding_validator(section: dict, hass: Any | None = None) -> list[str]:
    """Validate remote_binding configuration section.

    :param section: The remote_binding configuration section
    :param hass: Home Assistant instance (optional)
    :return: List of validation error messages
    """
    errors: list[str] = []

    if not isinstance(section, dict):
        errors.append("remote_binding configuration must be a dictionary")  # type: ignore[unreachable]
        return errors

    fans = section.get("FANs", {})
    if not isinstance(fans, dict):
        errors.append("remote_binding.FANs must be a dictionary")
        return errors

    seen_rems: set[str] = set()

    for fan_id, fan_data in fans.items():
        if not isinstance(fan_data, dict):
            errors.append(f"FAN '{fan_id}': configuration must be a dictionary")
            continue

        rems = fan_data.get("REMs", [])
        if not isinstance(rems, list):
            errors.append(f"FAN '{fan_id}': REMs must be a list")
            continue

        for rem in rems:
            if not isinstance(rem, dict):
                errors.append(f"FAN '{fan_id}': each REM must be a dictionary")
                continue

            rem_id = rem.get("rem_id")
            if not rem_id:
                errors.append(f"FAN '{fan_id}': REM missing rem_id")
                continue

            if rem_id in seen_rems:
                errors.append(f"REM '{rem_id}' assigned to multiple FANs")
            seen_rems.add(rem_id)

            zone_id = rem.get("zone_id")
            if zone_id is not None and (not isinstance(zone_id, str) or not zone_id):
                errors.append(
                    f"FAN '{fan_id}', REM '{rem_id}': invalid zone_id '{zone_id}'"
                )

            area_id = rem.get("area_id")
            if area_id is not None and (not isinstance(area_id, str) or not area_id):
                errors.append(
                    f"FAN '{fan_id}', REM '{rem_id}': invalid area_id '{area_id}'"
                )

    return errors


def export_remote_binding_to_yaml(
    bindings: dict[str, Any],
) -> str:
    """Export remote binding configuration to YAML format.

    :param bindings: Dictionary of FAN ID to REM configurations
    :return: YAML string representation of remote binding config
    """
    export_data = {
        "version": 1,
        "FANs": bindings,
    }

    return str(
        yaml.safe_dump(
            export_data,
            sort_keys=False,
            allow_unicode=True,
            default_flow_style=False,
        )
    )


def parse_remote_binding_yaml(yaml_content: str) -> dict[str, Any]:
    """Parse and validate remote binding YAML content.

    :param yaml_content: YAML string containing remote binding configuration
    :return: Validated remote binding configuration dictionary
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
        validated: dict[str, Any] = REMOTE_BINDING_CONFIG_SCHEMA(parsed)
    except vol.MultipleInvalid as e:
        raise ValueError(f"Schema validation failed: {e}") from e

    return validated


def merge_remote_binding_config(
    existing: dict[str, Any],
    imported: dict[str, Any],
    *,
    overwrite_existing: bool = False,
) -> dict[str, Any]:
    """Merge imported remote binding config with existing.

    :param existing: Existing remote binding configuration
    :param imported: Imported remote binding configuration
    :param overwrite_existing: If True, replace existing FAN configs
    :return: Merged remote binding configuration
    """
    result = dict(existing)

    imported_fans = imported.get("FANs", {})
    if "FANs" not in result:
        result["FANs"] = {}

    for fan_id, fan_config in imported_fans.items():
        if fan_id in result["FANs"] and not overwrite_existing:
            # Skip existing FANs if not overwriting
            continue
        result["FANs"][fan_id] = fan_config

    return result


def load_validator() -> None:
    """Register the remote_binding validator and schema with the framework."""
    register_config_validator("remote_binding", remote_binding_validator)
    register_config_schema("remote_binding", REMOTE_BINDING_CONFIG_SCHEMA)


__all__ = [
    "export_remote_binding_to_yaml",
    "parse_remote_binding_yaml",
    "merge_remote_binding_config",
    "remote_binding_validator",
    "REMOTE_BINDING_CONFIG_SCHEMA",
    "load_validator",
]
