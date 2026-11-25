"""CO2 Control Configuration Management."""

import logging
from typing import Any

from homeassistant.core import HomeAssistant

from .const import CO2_CONTROL_DEFAULTS, CO2_CONTROL_VALIDATION_RULES

_LOGGER = logging.getLogger(__name__)


class CO2Config:
    """Manage CO2 control configuration."""

    def __init__(self, hass: HomeAssistant, device_id: str, config: dict[str, Any]):
        """Initialize CO2 configuration.

        :param hass: Home Assistant instance
        :param device_id: Device identifier
        :param config: Configuration dictionary
        """
        self.hass = hass
        self.device_id = device_id
        self._config = self._merge_with_defaults(config)

    def _merge_with_defaults(self, config: dict[str, Any]) -> dict[str, Any]:
        """Merge user config with defaults.

        :param config: User configuration
        :return: Merged configuration dictionary
        """
        merged = CO2_CONTROL_DEFAULTS.copy()
        if config:
            merged.update(config)
        return merged

    @property
    def enabled(self) -> bool:
        """Check if CO2 control is enabled."""
        return bool(self._config.get("enabled", False))

    @property
    def automation_enabled(self) -> bool:
        """Check if CO2 automation is enabled."""
        return bool(self._config.get("automation_enabled", False))

    @property
    def default_threshold(self) -> int:
        """Get default CO2 threshold in ppm."""
        return int(self._config.get("default_threshold", 800))

    @property
    def activation_hysteresis(self) -> int:
        """Get activation hysteresis in ppm."""
        return int(self._config.get("activation_hysteresis", 25))

    @property
    def deactivation_hysteresis(self) -> int:
        """Get deactivation hysteresis in ppm."""
        return int(self._config.get("deactivation_hysteresis", -25))

    @property
    def max_runtime_minutes(self) -> int:
        """Get maximum runtime in minutes."""
        return int(self._config.get("max_runtime_minutes", 120))

    @property
    def cooldown_period_minutes(self) -> int:
        """Get cooldown period in minutes."""
        return int(self._config.get("cooldown_period_minutes", 15))

    @property
    def fan_mode(self) -> str:
        """Get the fan mode demanded while CO2 control is active.

        ``auto`` keeps the proportional speed calculation; ``low`` /
        ``medium`` / ``high`` force a fixed mode (issue 354).
        """
        mode = str(self._config.get("fan_mode", "auto"))
        return mode if mode in ("auto", "low", "medium", "high") else "auto"

    @property
    def medium_threshold(self) -> int:
        """Get the ppm level above which medium is demanded (issue 354)."""
        return int(self._config.get("medium_threshold", 1000))

    @property
    def high_threshold(self) -> int:
        """Get the ppm level above which high is demanded (issue 354)."""
        return int(self._config.get("high_threshold", 1200))

    @property
    def priority_over_humidity(self) -> bool:
        """Check if CO2 has priority over humidity control."""
        return bool(self._config.get("priority_over_humidity", True))

    def update_config(self, updates: dict[str, Any]) -> None:
        """Update configuration.

        :param updates: Configuration updates
        """
        self._config.update(updates)
        _LOGGER.debug("Updated CO2 config for device %s: %s", self.device_id, updates)

    async def async_load(self) -> bool:
        """Load config asynchronously for automation startup compatibility."""
        return True

    def validate(self) -> tuple[bool, list[str]]:
        """Validate configuration.

        :return: Tuple of (is_valid, error_messages)
        """
        errors = []

        # Validate threshold range
        threshold = self.default_threshold
        if not 400 <= threshold <= 2000:
            errors.append(f"CO2 threshold {threshold} out of range (400-2000 ppm)")

        # Validate hysteresis
        if self.activation_hysteresis < 0:
            errors.append("Activation hysteresis must be positive")

        if self.deactivation_hysteresis > 0:
            errors.append("Deactivation hysteresis must be negative")

        return len(errors) == 0, errors

    def to_dict(self) -> dict[str, Any]:
        """Convert configuration to dictionary.

        :return: Configuration dictionary
        """
        return self._config.copy()


__all__ = ["CO2Config"]
