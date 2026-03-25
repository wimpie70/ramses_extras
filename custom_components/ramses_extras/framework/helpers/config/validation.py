"""Configuration validation utilities for Ramses Extras framework.

This module provides reusable validation patterns that are shared across
all features, including numeric ranges, boolean checks, and dependency validation.
"""

import logging
import re
from typing import Any

from .model import (
    CONFIG_FANS_KEY,
    CONFIG_REMS_KEY,
    FEATURE_REMOTE_BINDING,
    FEATURE_SENSOR_CONTROL,
    FEATURE_ZONES,
    REMOTE_BINDING_REM_ID_KEY,
    SENSOR_CONTROL_AREA_SENSORS_KEY,
    ZONE_ID_KEY,
    get_feature_section,
    get_remote_binding_rems,
    get_sensor_control_device_section,
    get_zones_for_fan,
    normalize_device_id,
)

_LOGGER = logging.getLogger(__name__)
_DEVICE_ID_RE = re.compile(r"^\d{2}:\d{6}$")


class ConfigValidator:
    """Utility class for configuration validation patterns.

    This class provides common validation patterns that can be used by
    features to validate their configuration.
    """

    def __init__(self, feature_id: str) -> None:
        """Initialize the configuration validator.

        Args:
            feature_id: Feature identifier for logging
        """
        self.feature_id = feature_id

    def validate_numeric_range(
        self,
        config: dict[str, Any],
        key: str,
        min_val: float,
        max_val: float,
        required: bool = False,
    ) -> tuple[bool, str | None]:
        """Validate a numeric configuration value is within range.

        Args:
            config: Configuration dictionary
            key: Configuration key
            min_val: Minimum allowed value
            max_val: Maximum allowed value
            required: Whether the key is required

        Returns:
            Tuple of (is_valid, error_message)
        """
        if key not in config:
            if required:
                return False, f"'{key}' is required"
            return True, None

        value = config[key]
        if not isinstance(value, (int, float)):
            return False, f"'{key}' must be numeric, got {type(value).__name__}"

        if not (min_val <= value <= max_val):
            return False, (
                f"'{key}' must be between {min_val} and {max_val}, got {value}"
            )

        return True, None

    def validate_boolean(
        self,
        config: dict[str, Any],
        key: str,
        required: bool = False,
    ) -> tuple[bool, str | None]:
        """Validate a boolean configuration value.

        Args:
            config: Configuration dictionary
            key: Configuration key
            required: Whether the key is required

        Returns:
            Tuple of (is_valid, error_message)
        """
        if key not in config:
            if required:
                return False, f"'{key}' is required"
            return True, None

        value = config[key]
        if not isinstance(value, bool):
            return False, f"'{key}' must be boolean, got {type(value).__name__}"

        return True, None

    def validate_string(
        self,
        config: dict[str, Any],
        key: str,
        choices: list[str] | None = None,
        required: bool = False,
        min_length: int = 0,
        max_length: int | None = None,
    ) -> tuple[bool, str | None]:
        """Validate a string configuration value.

        Args:
            config: Configuration dictionary
            key: Configuration key
            choices: Optional list of valid choices
            required: Whether the key is required
            min_length: Minimum string length
            max_length: Maximum string length

        Returns:
            Tuple of (is_valid, error_message)
        """
        if key not in config:
            if required:
                return False, f"'{key}' is required"
            return True, None

        value = config[key]
        if not isinstance(value, str):
            return False, f"'{key}' must be string, got {type(value).__name__}"

        if len(value) < min_length:
            return False, f"'{key}' must be at least {min_length} characters long"

        if max_length and len(value) > max_length:
            return False, f"'{key}' must be at most {max_length} characters long"

        if choices and value not in choices:
            return False, f"'{key}' must be one of {choices}, got '{value}'"

        return True, None

    def validate_list(
        self,
        config: dict[str, Any],
        key: str,
        item_type: type | None = None,
        choices: list[Any] | None = None,
        required: bool = False,
        min_items: int = 0,
        max_items: int | None = None,
    ) -> tuple[bool, str | None]:
        """Validate a list configuration value.

        Args:
            config: Configuration dictionary
            key: Configuration key
            item_type: Expected type of list items
            choices: Optional list of valid choices for items
            required: Whether the key is required
            min_items: Minimum number of items
            max_items: Maximum number of items

        Returns:
            Tuple of (is_valid, error_message)
        """
        if key not in config:
            if required:
                return False, f"'{key}' is required"
            return True, None

        value = config[key]
        if not isinstance(value, list):
            return False, f"'{key}' must be list, got {type(value).__name__}"

        if len(value) < min_items:
            return False, f"'{key}' must have at least {min_items} items"

        if max_items and len(value) > max_items:
            return False, f"'{key}' must have at most {max_items} items"

        if item_type or choices:
            for i, item in enumerate(value):
                if item_type and not isinstance(item, item_type):
                    return False, (
                        f"'{key}[{i}]' must be {item_type.__name__}, "
                        f"got {type(item).__name__}"
                    )

                if choices and item not in choices:
                    return False, f"'{key}[{i}]' must be one of {choices}, got '{item}'"

        return True, None

    def validate_dependency(
        self,
        config: dict[str, Any],
        dependent_key: str,
        dependency_key: str,
        dependency_value: Any = True,
    ) -> tuple[bool, str | None]:
        """Validate that a dependency relationship is satisfied.

        Args:
            config: Configuration dictionary
            dependent_key: Key that depends on another key
            dependency_key: Key that is depended upon
            dependency_value: Value that the dependency key must have

        Returns:
            Tuple of (is_valid, error_message)
        """
        if dependent_key not in config:
            return True, None  # No dependency to check

        dependency_val = config.get(dependency_key)
        if dependency_val != dependency_value:
            return False, (
                f"'{dependent_key}' requires '{dependency_key}' to be "
                f"{dependency_value}, got {dependency_val}"
            )

        return True, None

    def validate_range_relationship(
        self,
        config: dict[str, Any],
        min_key: str,
        max_key: str,
        allow_equal: bool = False,
    ) -> tuple[bool, str | None]:
        """Validate that one numeric value is less than another.

        Args:
            config: Configuration dictionary
            min_key: Key for minimum value
            max_key: Key for maximum value
            allow_equal: Whether to allow equal values

        Returns:
            Tuple of (is_valid, error_message)
        """
        if min_key not in config or max_key not in config:
            return True, None  # No range to validate

        min_val = config[min_key]
        max_val = config[max_key]

        if not isinstance(min_val, (int, float)) or not isinstance(
            max_val, (int, float)
        ):
            return False, f"'{min_key}' and '{max_key}' must both be numeric"

        if allow_equal:
            if min_val > max_val:
                return False, f"'{min_key}' must be <= '{max_key}'"
        else:
            if min_val >= max_val:
                return False, f"'{min_key}' must be < '{max_key}'"

        return True, None

    def validate_all(
        self,
        config: dict[str, Any],
        validation_rules: dict[str, Any],
    ) -> tuple[bool, list[str]]:
        """Validate configuration against multiple rules.

        Args:
            config: Configuration dictionary
            validation_rules: Dictionary of validation rules

        Returns:
            Tuple of (is_valid, list_of_error_messages)
        """
        errors = []

        for key, rules in validation_rules.items():
            if isinstance(rules, dict):
                # Handle type validation
                if "type" in rules:
                    validation_type = rules["type"]
                    if validation_type == "numeric":
                        is_valid, error = self.validate_numeric_range(
                            config,
                            key,
                            rules.get("min", float("-inf")),
                            rules.get("max", float("inf")),
                            rules.get("required", False),
                        )
                        if not is_valid and error:
                            errors.append(error)
                    elif validation_type == "boolean":
                        is_valid, error = self.validate_boolean(
                            config, key, rules.get("required", False)
                        )
                        if not is_valid and error:
                            errors.append(error)
                    elif validation_type == "string":
                        is_valid, error = self.validate_string(
                            config,
                            key,
                            rules.get("choices"),
                            rules.get("required", False),
                            rules.get("min_length", 0),
                            rules.get("max_length"),
                        )
                        if not is_valid and error:
                            errors.append(error)
                    elif validation_type == "list":
                        is_valid, error = self.validate_list(
                            config,
                            key,
                            rules.get("item_type"),
                            rules.get("choices"),
                            rules.get("required", False),
                            rules.get("min_items", 0),
                            rules.get("max_items"),
                        )
                        if not is_valid and error:
                            errors.append(error)

                # Handle dependency validation
                if "dependency" in rules:
                    dep_config = rules["dependency"]
                    is_valid, error = self.validate_dependency(
                        config, key, dep_config["key"], dep_config.get("value", True)
                    )
                    if not is_valid and error:
                        errors.append(error)

                # Handle range relationship validation
                if "range_relationship" in rules:
                    range_config = rules["range_relationship"]
                    is_valid, error = self.validate_range_relationship(
                        config,
                        key,
                        range_config["other_key"],
                        range_config.get("allow_equal", False),
                    )
                    if not is_valid and error:
                        errors.append(error)
            else:
                # Handle legacy rules (not dict)
                pass

        return len(errors) == 0, errors

    def validate_device_id(
        self,
        config: dict[str, Any],
        key: str,
        required: bool = False,
    ) -> tuple[bool, str | None]:
        if key not in config:
            if required:
                return False, f"'{key}' is required"
            return True, None

        return self.validate_device_id_value(config[key], key)

    def validate_device_id_value(
        self,
        value: Any,
        field_name: str = "device_id",
    ) -> tuple[bool, str | None]:
        if not isinstance(value, str):
            return False, f"'{field_name}' must be string, got {type(value).__name__}"

        normalized = normalize_device_id(value)
        if not _DEVICE_ID_RE.match(normalized):
            return False, (f"'{field_name}' must look like '32:123456', got '{value}'")

        return True, None

    def validate_position_limits(
        self,
        config: dict[str, Any],
        min_key: str = "min_position",
        max_key: str = "max_position",
    ) -> tuple[bool, list[str]]:
        errors: list[str] = []

        min_value = config.get(min_key)
        max_value = config.get(max_key)

        for key, value in ((min_key, min_value), (max_key, max_value)):
            if value is None:
                continue
            if not isinstance(value, (int, float)):
                errors.append(f"'{key}' must be numeric")
                continue
            if not 0 <= value <= 100:
                errors.append(f"'{key}' must be between 0 and 100")

        if (
            isinstance(min_value, (int, float))
            and isinstance(max_value, (int, float))
            and min_value > max_value
        ):
            errors.append(f"'{min_key}' must be <= '{max_key}'")

        return len(errors) == 0, errors

    def validate_zone_fans(
        self,
        zones_section: dict[str, Any],
        sensor_control_section: dict[str, Any] | None = None,
    ) -> tuple[bool, list[str]]:
        errors: list[str] = []
        fan_mapping = zones_section.get(CONFIG_FANS_KEY)

        if fan_mapping is None:
            return True, errors
        if not isinstance(fan_mapping, dict):
            return False, [f"'{CONFIG_FANS_KEY}' must be a dictionary"]

        for fan_id, zones in fan_mapping.items():
            is_valid_fan_id, fan_id_error = self.validate_device_id_value(
                fan_id, "fan_id"
            )
            if not is_valid_fan_id and fan_id_error:
                errors.append(fan_id_error)
                continue

            normalized_fan_id = normalize_device_id(fan_id)
            if not isinstance(zones, list):
                errors.append(
                    f"'{CONFIG_FANS_KEY}[{normalized_fan_id}]' must be a list of zones"
                )
                continue

            for index, zone in enumerate(zones):
                if isinstance(zone, dict):
                    continue
                errors.append(
                    f"zone entry {index} for FAN {normalized_fan_id} must be a dict"
                )

            zone_ids: set[str] = set()
            normalized_zones = get_zones_for_fan(zones_section, normalized_fan_id)
            for index, zone in enumerate(normalized_zones):
                zone_id = zone.get(ZONE_ID_KEY)
                if not isinstance(zone_id, str) or not zone_id.strip():
                    errors.append(
                        "zone entry "
                        f"{index} for FAN {normalized_fan_id} must have "
                        "a non-empty 'zone_id'"
                    )
                    continue

                if zone_id in zone_ids:
                    errors.append(
                        f"duplicate zone_id '{zone_id}' for FAN {normalized_fan_id}"
                    )
                else:
                    zone_ids.add(zone_id)

                actuator = zone.get("actuator")
                if isinstance(actuator, dict):
                    _, actuator_errors = self.validate_position_limits(actuator)
                    for error in actuator_errors:
                        errors.append(
                            f"zone '{zone_id}' for FAN {normalized_fan_id}: {error}"
                        )

            if sensor_control_section is not None:
                errors.extend(
                    self._validate_area_sensor_zone_links(
                        normalized_fan_id,
                        zone_ids,
                        sensor_control_section,
                    )
                )

        return len(errors) == 0, errors

    def validate_remote_binding_fans(
        self,
        remote_binding_section: dict[str, Any],
    ) -> tuple[bool, list[str]]:
        errors: list[str] = []
        fan_mapping = remote_binding_section.get(CONFIG_FANS_KEY)

        if fan_mapping is None:
            return True, errors
        if not isinstance(fan_mapping, dict):
            return False, [f"'{CONFIG_FANS_KEY}' must be a dictionary"]

        primary_rem_to_fan: dict[str, str] = {}

        for fan_id, fan_section in fan_mapping.items():
            is_valid_fan_id, fan_id_error = self.validate_device_id_value(
                fan_id, "fan_id"
            )
            if not is_valid_fan_id and fan_id_error:
                errors.append(fan_id_error)
                continue

            normalized_fan_id = normalize_device_id(fan_id)
            if not isinstance(fan_section, dict):
                errors.append(
                    f"binding section for FAN {normalized_fan_id} must be a dict"
                )
                continue

            rems = fan_section.get(CONFIG_REMS_KEY)
            if rems is None:
                continue
            if not isinstance(rems, list):
                errors.append(
                    f"'{CONFIG_REMS_KEY}' for FAN {normalized_fan_id} must be a list"
                )
                continue

            for index, rem in enumerate(rems):
                if isinstance(rem, dict):
                    continue
                errors.append(
                    f"REM entry {index} for FAN {normalized_fan_id} must be a dict"
                )

            rem_ids_for_fan: set[str] = set()
            normalized_rems = get_remote_binding_rems(
                remote_binding_section, normalized_fan_id
            )
            for index, rem in enumerate(normalized_rems):
                rem_id = rem.get(REMOTE_BINDING_REM_ID_KEY)
                is_valid_rem_id, rem_id_error = self.validate_device_id_value(
                    rem_id, REMOTE_BINDING_REM_ID_KEY
                )
                if not is_valid_rem_id and rem_id_error:
                    errors.append(
                        f"FAN {normalized_fan_id} REM entry {index}: {rem_id_error}"
                    )
                    continue

                normalized_rem_id = normalize_device_id(str(rem_id))
                if normalized_rem_id in rem_ids_for_fan:
                    errors.append(
                        f"duplicate REM '{normalized_rem_id}' "
                        f"for FAN {normalized_fan_id}"
                    )
                else:
                    rem_ids_for_fan.add(normalized_rem_id)

                if rem.get("role") == "primary":
                    existing_fan_id = primary_rem_to_fan.get(normalized_rem_id)
                    if existing_fan_id and existing_fan_id != normalized_fan_id:
                        errors.append(
                            "primary REM "
                            f"'{normalized_rem_id}' cannot be assigned to both "
                            f"{existing_fan_id} and {normalized_fan_id}"
                        )
                    else:
                        primary_rem_to_fan[normalized_rem_id] = normalized_fan_id

        return len(errors) == 0, errors

    def _validate_area_sensor_zone_links(
        self,
        fan_id: str,
        zone_ids: set[str],
        sensor_control_section: dict[str, Any],
    ) -> list[str]:
        device_section = get_sensor_control_device_section(
            sensor_control_section, fan_id
        )
        area_sensors = device_section.get(SENSOR_CONTROL_AREA_SENSORS_KEY)
        if not isinstance(area_sensors, list):
            return []

        errors: list[str] = []
        for index, area in enumerate(area_sensors):
            if not isinstance(area, dict):
                continue

            zone_id = area.get(ZONE_ID_KEY)
            if zone_id is None:
                continue
            if not isinstance(zone_id, str) or not zone_id.strip():
                errors.append(
                    f"area sensor {index} for FAN {fan_id} has an invalid 'zone_id'"
                )
                continue
            if zone_id not in zone_ids:
                errors.append(
                    "area sensor "
                    f"{index} for FAN {fan_id} references unknown zone_id "
                    f"'{zone_id}'"
                )

        return errors

    def validate_canonical_config(
        self,
        canonical_config: dict[str, Any],
    ) -> tuple[bool, list[str]]:
        errors: list[str] = []

        sensor_control_section = get_feature_section(
            canonical_config,
            FEATURE_SENSOR_CONTROL,
        )
        zones_section = get_feature_section(canonical_config, FEATURE_ZONES)
        remote_binding_section = get_feature_section(
            canonical_config,
            FEATURE_REMOTE_BINDING,
        )

        _, zone_errors = self.validate_zone_fans(
            zones_section,
            sensor_control_section,
        )
        errors.extend(zone_errors)

        _, remote_binding_errors = self.validate_remote_binding_fans(
            remote_binding_section,
        )
        errors.extend(remote_binding_errors)

        return len(errors) == 0, errors


__all__ = [
    "ConfigValidator",
]
