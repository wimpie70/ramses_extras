"""Configuration management core for Ramses Extras framework.

This module provides the ExtrasConfigManager base class that can be extended
by features to provide generic configuration management functionality.
"""

import logging
from copy import deepcopy
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_ENABLED,
    CONF_ID,
    CONF_NAME,
)
from homeassistant.core import HomeAssistant

from .export import build_exportable_config, export_config_to_yaml
from .migration import migrate_to_canonical_config
from .model import (
    get_fan_ids,
    get_remote_binding_rem_ids,
    get_remote_binding_rems,
    get_sensor_control_device_section,
    get_zone_ids_for_fan,
    get_zones_for_fan,
    normalize_device_id,
)
from .model import (
    get_fan_section as get_model_fan_section,
)
from .model import (
    get_feature_section as get_canonical_feature_section,
)
from .model import (
    set_feature_section as set_canonical_feature_section,
)
from .validation import ConfigValidator

# Feature IDs used by this module
FEATURE_SENSOR_CONTROL = "sensor_control"
FEATURE_ZONES = "zones"
FEATURE_REMOTE_BINDING = "remote_binding"

_LOGGER = logging.getLogger(__name__)


class ExtrasConfigManager:
    """Generic configuration manager for Ramses Extras features.

    This base class provides configuration management patterns that are shared
    across all features, including loading, validation, and access patterns.

    Features should extend this class and provide their own default configuration
    and validation rules.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        feature_id: str,
        default_config: dict[str, Any],
    ) -> None:
        """Initialize the configuration manager.

        Args:
            hass: Home Assistant instance
            config_entry: Configuration entry
            feature_id: Feature identifier (e.g., "humidity_control")
            default_config: Default configuration dictionary
        """
        self.hass = hass
        self.config_entry = config_entry
        self.feature_id = feature_id
        self._default_config = default_config.copy()
        self._config: dict[str, Any] = {}

        _LOGGER.info(f"Initialized {feature_id} configuration manager")

    async def async_load(self) -> None:
        """Load configuration from config entry and defaults.

        Merges default configuration with user configuration from config entry.
        """
        _LOGGER.info(f"Loading {self.feature_id} configuration")

        try:
            # Start with default config
            self._config = self._default_config.copy()

            # Update with config entry data if available
            if self.config_entry.data:
                self._config.update(self.config_entry.data)
                _LOGGER.debug(
                    f"Updated {self.feature_id} config with data: "
                    f"{self.config_entry.data}"
                )

            # Update with config entry options if available
            if self.config_entry.options:
                self._config.update(self.config_entry.options)
                _LOGGER.debug(
                    f"Updated {self.feature_id} config with options: "
                    f"{self.config_entry.options}"
                )

            _LOGGER.info(f"Configuration loaded: {len(self._config)} settings")

        except Exception as e:
            _LOGGER.error(f"Failed to load {self.feature_id} configuration: {e}")
            # Fall back to defaults
            self._config = self._default_config.copy()

    async def async_save(self) -> bool:
        """Save current configuration.

        This would update the config entry with current settings.
        For now, it just validates the configuration.

        Returns:
            True if successful
        """
        try:
            # Validate configuration
            if not self.validate_config():
                return False

            # This would update the config entry
            # Implementation depends on HA's config entry update mechanism
            _LOGGER.info(f"{self.feature_id} configuration validation passed")
            return True

        except Exception as e:
            _LOGGER.error(f"Failed to save {self.feature_id} configuration: {e}")
            return False

    def validate_config(self) -> bool:
        """Validate current configuration.

        Features should override this method to provide feature-specific validation.
        The base implementation provides general validation patterns.

        Returns:
            True if configuration is valid
        """
        try:
            # Check for basic boolean values if they exist
            if "enabled" in self._config and not isinstance(
                self._config["enabled"], bool
            ):
                _LOGGER.error(
                    f"{self.feature_id} configuration error: 'enabled' must be boolean"
                )
                return False

            # Check for basic numeric ranges if they exist
            if "min_value" in self._config and "max_value" in self._config:
                min_val = self._config["min_value"]
                max_val = self._config["max_value"]
                if not isinstance(min_val, (int, float)) or not isinstance(
                    max_val, (int, float)
                ):
                    _LOGGER.error(
                        f"{self.feature_id} configuration error: "
                        "'min_value' and 'max_value' must be numeric"
                    )
                    return False

                if min_val >= max_val:
                    _LOGGER.error(
                        f"{self.feature_id} configuration error: "
                        "'max_value' must be > 'min_value'"
                    )
                    return False

            _LOGGER.debug(f"{self.feature_id} configuration validation successful")
            return True

        except Exception as e:
            _LOGGER.error(f"{self.feature_id} configuration validation error: {e}")
            return False

    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value.

        Args:
            key: Configuration key
            default: Default value if key not found

        Returns:
            Configuration value
        """
        return self._config.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """Set configuration value.

        Args:
            key: Configuration key
            value: Value to set
        """
        self._config[key] = value
        _LOGGER.debug(f"{self.feature_id} configuration updated: {key} = {value}")

    def get_all(self) -> dict[str, Any]:
        """Get all configuration values.

        Returns:
            Complete configuration dictionary
        """
        return self._config.copy()

    def get_canonical_config(self) -> dict[str, Any]:
        return migrate_to_canonical_config(self.get_all())

    def get_exportable_config(self) -> dict[str, Any]:
        return build_exportable_config(self.get_all())

    def export_config_as_yaml(self) -> str:
        return export_config_to_yaml(self.get_all())

    def validate_canonical_config(self) -> tuple[bool, list[str]]:
        validator = ConfigValidator(self.feature_id)
        return validator.validate_canonical_config(self.get_canonical_config())

    def validate_feature_section_canonical(
        self, feature_id: str
    ) -> tuple[bool, list[str]]:
        validator = ConfigValidator(feature_id)
        canonical_config = self.get_canonical_config()

        if feature_id == "zones":
            return validator.validate_zone_fans(
                self.get_feature_section(feature_id, canonical=True),
                self.get_feature_section("sensor_control", canonical=True),
            )

        if feature_id == "remote_binding":
            return validator.validate_remote_binding_fans(
                self.get_feature_section(feature_id, canonical=True),
            )

        return validator.validate_canonical_config(canonical_config)

    def get_feature_section(
        self, feature_id: str, *, canonical: bool = False
    ) -> dict[str, Any]:
        if canonical:
            return get_canonical_feature_section(
                self.get_canonical_config(), feature_id
            )

        section = self._config.get(feature_id)
        if isinstance(section, dict):
            return deepcopy(section)

        root_section = get_canonical_feature_section(self._config, feature_id)
        if root_section:
            return deepcopy(root_section)
        return {}

    def set_feature_section(
        self,
        feature_id: str,
        section_data: dict[str, Any],
        *,
        canonical: bool = False,
    ) -> None:
        if canonical:
            canonical_config = self.get_canonical_config()
            set_canonical_feature_section(canonical_config, feature_id, section_data)
            self._config = canonical_config
            return

        if get_canonical_feature_section(self._config, feature_id):
            set_canonical_feature_section(self._config, feature_id, section_data)
            return

        self._config[feature_id] = deepcopy(section_data)

    def get_fan_section(
        self, feature_id: str, device_id: str, *, canonical: bool = True
    ) -> dict[str, Any] | list[Any]:
        section = self.get_feature_section(feature_id, canonical=canonical)
        normalized_device_id = normalize_device_id(device_id)

        if feature_id == FEATURE_SENSOR_CONTROL:
            return get_sensor_control_device_section(section, normalized_device_id)

        return get_model_fan_section(section, normalized_device_id)

    def list_configured_fans(
        self, feature_id: str, *, canonical: bool = True
    ) -> list[str]:
        section = self.get_feature_section(feature_id, canonical=canonical)
        return get_fan_ids(section)

    def get_fan_zones(self, device_id: str) -> list[dict[str, Any]]:
        """Get zones configured for a FAN device.

        Uses the shared zones helper for normalized FAN→zone lookup.

        Args:
            device_id: FAN device ID (canonical or legacy format)

        Returns:
            List of zone configuration dictionaries
        """
        section = self.get_feature_section(FEATURE_ZONES, canonical=True)
        return get_zones_for_fan(section, device_id)

    def get_fan_zone_ids(self, device_id: str) -> list[str]:
        """Get zone IDs configured for a FAN device.

        Uses the shared zones helper for normalized zone ID extraction.

        Args:
            device_id: FAN device ID (canonical or legacy format)

        Returns:
            List of unique zone IDs
        """
        section = self.get_feature_section(FEATURE_ZONES, canonical=True)
        return get_zone_ids_for_fan(section, device_id)

    def get_fan_remote_bindings(self, device_id: str) -> list[dict[str, Any]]:
        """Get REM bindings configured for a FAN device.

        Uses the shared remote_binding helper for normalized FAN→REM lookup.

        Args:
            device_id: FAN device ID (canonical or legacy format)

        Returns:
            List of REM binding dictionaries with normalized rem_id
        """
        section = self.get_feature_section(FEATURE_REMOTE_BINDING, canonical=True)
        return get_remote_binding_rems(section, device_id)

    def get_fan_remote_binding_ids(self, device_id: str) -> list[str]:
        """Get REM IDs bound to a FAN device.

        Uses the shared remote_binding helper for normalized REM ID extraction.

        Args:
            device_id: FAN device ID (canonical or legacy format)

        Returns:
            List of unique REM IDs
        """
        section = self.get_feature_section(FEATURE_REMOTE_BINDING, canonical=True)
        return get_remote_binding_rem_ids(section, device_id)

    def update(self, updates: Any) -> None:
        """Update multiple configuration values.

        Args:
            updates: Dictionary of updates
        """
        if not isinstance(updates, dict):
            _LOGGER.warning(
                f"{self.feature_id} configuration update ignored: "
                f"updates must be a dictionary, got {type(updates)}"
            )
            return

        self._config.update(updates)
        _LOGGER.info(
            f"{self.feature_id} configuration updated with {len(updates)} values"
        )

    def is_enabled(self) -> bool:
        """Check if feature is enabled.

        Returns:
            True if enabled
        """
        return bool(self.get("enabled", False))

    def is_automation_enabled(self) -> bool:
        """Check if automation is enabled.

        Returns:
            True if automation is enabled
        """
        return self.is_enabled() and self.get("automation_enabled", False)

    def reset_to_defaults(self) -> None:
        """Reset configuration to default values.

        Restores all configuration to default values.
        """
        _LOGGER.info(f"Resetting {self.feature_id} configuration to defaults")
        self._config = self._default_config.copy()

    def get_config_schema_dict(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "enabled": {
                    "type": "boolean",
                    "title": f"Enable {self.feature_id.title().replace('_', ' ')}",
                    "description": f"Enable or disable the {self.feature_id} feature",
                },
            },
        }

    def get_config_schema(self) -> dict[str, Any]:
        """Get configuration schema for UI.

        Features should override this method to provide feature-specific schemas.
        The base implementation provides a generic schema.

        Returns:
            Configuration schema dictionary
        """
        return self.get_config_schema_dict()

    def get_numeric_validation(self, key: str, min_val: float, max_val: float) -> bool:
        """Validate a numeric configuration value is within range.

        Args:
            key: Configuration key
            min_val: Minimum allowed value
            max_val: Maximum allowed value

        Returns:
            True if valid
        """
        value = self._config.get(key)
        if not isinstance(value, (int, float)):
            _LOGGER.error(
                f"{self.feature_id} configuration error: '{key}' must be numeric"
            )
            return False

        if not (min_val <= value <= max_val):
            _LOGGER.error(
                f"{self.feature_id} configuration error: '{key}' must be between "
                f"{min_val} and {max_val}"
            )
            return False

        return True

    def get_boolean_validation(self, key: str) -> bool:
        """Validate a boolean configuration value.

        Args:
            key: Configuration key

        Returns:
            True if valid
        """
        value = self._config.get(key)
        if not isinstance(value, bool):
            _LOGGER.error(
                f"{self.feature_id} configuration error: '{key}' must be boolean"
            )
            return False

        return True

    def get_string_validation(
        self,
        key: str,
        choices: list | None = None,
        min_length: int = 0,
        max_length: int | None = None,
    ) -> bool:
        """Validate a string configuration value.

        Args:
            key: Configuration key
            choices: Optional list of valid choices
            min_length: Minimum allowed length (default 0)
            max_length: Maximum allowed length (default None for no limit)

        Returns:
            True if valid
        """
        value = self._config.get(key)
        if not isinstance(value, str):
            _LOGGER.error(
                f"{self.feature_id} configuration error: '{key}' must be string"
            )
            return False

        if len(value) < min_length:
            _LOGGER.error(
                f"{self.feature_id} configuration error: '{key}' must be at least "
                f"{min_length} characters long"
            )
            return False

        if max_length is not None and len(value) > max_length:
            _LOGGER.error(
                f"{self.feature_id} configuration error: '{key}' must be at most "
                f"{max_length} characters long"
            )
            return False

        if choices and value not in choices:
            _LOGGER.error(
                f"{self.feature_id} configuration error: '{key}' must be one of "
                f"{choices}, got '{value}'"
            )
            return False

        return True


# Configuration factory function
def create_config_manager(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    feature_id: str,
    default_config: dict[str, Any],
) -> ExtrasConfigManager:
    """Create a configuration manager instance.

    Args:
        hass: Home Assistant instance
        config_entry: Configuration entry
        feature_id: Feature identifier
        default_config: Default configuration

    Returns:
        ExtrasConfigManager instance
    """
    return ExtrasConfigManager(hass, config_entry, feature_id, default_config)


__all__ = [
    "ExtrasConfigManager",
    "create_config_manager",
]
