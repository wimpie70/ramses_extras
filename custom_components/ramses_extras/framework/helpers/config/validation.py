"""Configuration validation utilities for Ramses Extras framework.

This module provides reusable validation patterns that are shared across
all features, including numeric ranges, boolean checks, and dependency validation.
"""

import logging
from typing import Any

_LOGGER = logging.getLogger(__name__)


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


__all__ = [
    "ConfigValidator",
]
