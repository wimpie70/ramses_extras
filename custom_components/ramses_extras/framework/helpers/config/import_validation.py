"""Configuration import validation framework.

Provides a registry-based validation system where:
- Framework validates base structure (schema version, root keys)
- Each feature registers its own validator for its section
- All validation runs before any save, with aggregated feedback
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

# Registry of feature validators: feature_id -> validator function
_feature_validators: dict[
    str,
    Callable[[dict[str, Any], HomeAssistant | None], list[str]],
] = {}

# Registry of feature schemas: feature_id -> voluptuous schema
_feature_schemas: dict[str, Any] = {}


def register_config_validator(
    feature_id: str,
    validator: Callable[[dict[str, Any], HomeAssistant | None], list[str]],
) -> None:
    """Register a validator function for a feature's config section.

    :param feature_id: Feature identifier (e.g., 'zones', 'sensor_control')
    :param validator: Function taking (section, hass) and returning errors

    Example:
        def validate_zones(section: dict, hass: HomeAssistant | None) -> list[str]:
            errors = []
            for zone in section.get("zones", []):
                if not zone.get("zone_id"):
                    errors.append("Zone missing zone_id")
            return errors

        register_config_validator("zones", validate_zones)
    """
    _feature_validators[feature_id] = validator


def register_config_schema(feature_id: str, schema: Any) -> None:
    """Register a voluptuous schema for a feature's config section.

    :param feature_id: Feature identifier (e.g., 'zones', 'sensor_control')
    :param schema: Voluptuous schema for validating the feature's config

    Example:
        import voluptuous as vol

        ZONES_SCHEMA = vol.Schema({
            vol.Optional("FANs"): {str: [dict]},
        }, extra=vol.ALLOW_EXTRA)

        register_config_schema("zones", ZONES_SCHEMA)
    """
    _feature_schemas[feature_id] = schema


def unregister_config_validator(feature_id: str) -> None:
    """Remove a registered validator."""
    _feature_validators.pop(feature_id, None)


def unregister_config_schema(feature_id: str) -> None:
    """Remove a registered schema."""
    _feature_schemas.pop(feature_id, None)


def get_registered_validators() -> dict[
    str, Callable[[dict[str, Any], HomeAssistant | None], list[str]]
]:
    """Get all registered validators."""
    return dict(_feature_validators)


def get_registered_schemas() -> dict[str, Any]:
    """Get all registered schemas."""
    return dict(_feature_schemas)


def validate_import_config(
    config: dict[str, Any],
    hass: HomeAssistant | None = None,
) -> dict[str, Any]:
    """Validate full config import using registered feature validators.

    :param config: The configuration to validate
    :param hass: Optional Home Assistant instance for entity/device validation
    :return: Validation result dictionary:
        {
            "valid": bool,
            "framework_errors": list[str],
            "feature_errors": dict[str, list[str]],
            "total_errors": int,
        }
    """
    from .model import CONFIG_FEATURES_KEY, CONFIG_ROOT_KEY, CONFIG_SCHEMA_VERSION_KEY

    framework_errors: list[str] = []
    feature_errors: dict[str, list[str]] = {}

    # Framework-level validation
    root = config.get(CONFIG_ROOT_KEY)
    if not isinstance(root, dict):
        framework_errors.append("Missing or invalid 'ramses_extras' root key")
        return {
            "valid": False,
            "framework_errors": framework_errors,
            "feature_errors": {},
            "total_errors": len(framework_errors),
        }

    # Check schema version
    schema_version = root.get(CONFIG_SCHEMA_VERSION_KEY)
    if schema_version is not None and schema_version != 1:
        framework_errors.append(
            f"Unsupported schema version: {schema_version}. Expected: 1"
        )

    # Get features container
    features = root.get(CONFIG_FEATURES_KEY, {})
    if not isinstance(features, dict):
        framework_errors.append("Invalid 'features' section")
        return {
            "valid": False,
            "framework_errors": framework_errors,
            "feature_errors": {},
            "total_errors": len(framework_errors),
        }

    # Run feature-specific validators
    for feature_id, feature_data in features.items():
        validator = _feature_validators.get(feature_id)
        if validator:
            try:
                errors = validator(feature_data, hass)
                if errors:
                    feature_errors[feature_id] = errors
            except Exception as e:
                # Catch validator exceptions to prevent one failing
                # validator from stopping others
                feature_errors[feature_id] = [f"Validator error: {e}"]
        # Unknown features are allowed (extensibility), just log at debug level

    total_errors = len(framework_errors) + sum(len(e) for e in feature_errors.values())

    return {
        "valid": total_errors == 0,
        "framework_errors": framework_errors,
        "feature_errors": feature_errors,
        "total_errors": total_errors,
    }


def format_validation_errors(result: dict[str, Any]) -> list[str]:
    """Format validation result into a flat list of error strings.

    :param result: Validation result from validate_import_config()
    :return: List of formatted error strings
    """
    errors: list[str] = []

    for err in result.get("framework_errors", []):
        errors.append(f"[Framework] {err}")

    for feature_id, feature_errs in result.get("feature_errors", {}).items():
        for err in feature_errs:
            errors.append(f"[{feature_id}] {err}")

    return errors


__all__ = [
    "register_config_validator",
    "register_config_schema",
    "unregister_config_validator",
    "unregister_config_schema",
    "get_registered_validators",
    "get_registered_schemas",
    "validate_import_config",
    "format_validation_errors",
]
