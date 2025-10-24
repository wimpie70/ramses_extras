"""Feature Manager for Ramses Extras integration."""

import logging
from typing import TYPE_CHECKING, Any, Dict

from ..const import AVAILABLE_FEATURES, DOMAIN

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)


class FeatureManager:
    """Manages enabled/disabled state of integration features."""

    def __init__(self, hass: "HomeAssistant") -> None:
        """Initialize feature manager."""
        self.hass = hass
        self._enabled_features: dict[str, bool] = {}

    def load_enabled_features(self, config_entry: "ConfigEntry") -> None:
        """Load enabled features from config entry."""
        self._enabled_features = config_entry.data.get("enabled_features", {})

        # Ensure all features are present (backward compatibility)
        for feature_key in AVAILABLE_FEATURES.keys():
            if feature_key not in self._enabled_features:
                feature_config = AVAILABLE_FEATURES[feature_key]
                default_enabled = feature_config.get("default_enabled", False)
                # Ensure default_enabled is a boolean
                self._enabled_features[feature_key] = (
                    bool(default_enabled) if default_enabled is not None else False
                )

        _LOGGER.info(f"Loaded enabled features: {self._enabled_features}")

    def is_feature_enabled(self, feature_key: str) -> bool:
        """Check if a feature is enabled."""
        return self._enabled_features.get(feature_key, False)

    def get_enabled_cards(self) -> list[str]:
        """Get list of enabled card features."""
        enabled_cards = []
        for feature_key, feature_config in AVAILABLE_FEATURES.items():
            if feature_config.get("category") == "cards" and self.is_feature_enabled(
                feature_key
            ):
                enabled_cards.append(feature_key)
        return enabled_cards

    def get_enabled_automations(self) -> list[str]:
        """Get list of enabled automation features."""
        enabled_automations = []
        for feature_key, feature_config in AVAILABLE_FEATURES.items():
            if feature_config.get(
                "category"
            ) == "automations" and self.is_feature_enabled(feature_key):
                enabled_automations.append(feature_key)
        return enabled_automations

    def get_enabled_features_by_category(self, category: str) -> list[str]:
        """Get list of enabled features for a specific category."""
        enabled_features = []
        for feature_key, feature_config in AVAILABLE_FEATURES.items():
            if feature_config.get("category") == category and self.is_feature_enabled(
                feature_key
            ):
                enabled_features.append(feature_key)
        return enabled_features

    def update_enabled_features(self, enabled_features: dict[str, bool]) -> None:
        """Update the enabled features state."""
        self._enabled_features.update(enabled_features)
        _LOGGER.info(f"Updated enabled features: {self._enabled_features}")
