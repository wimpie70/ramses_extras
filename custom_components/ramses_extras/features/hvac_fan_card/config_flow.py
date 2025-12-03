"""Config flow for HVAC Fan Card feature.

This implements a simple config flow for the HVAC Fan Card feature.
Since this is a card-only feature, it doesn't require device selection
but can show status information about the card.
"""

import logging
from typing import Any, cast

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from ...framework.helpers.config.feature_config_flow import FeatureConfigFlowBase

_LOGGER = logging.getLogger(__name__)


class HvacFanCardConfigFlow(FeatureConfigFlowBase):
    """Config flow for HVAC Fan Card feature - card-only configuration."""

    def __init__(self, config_entry: ConfigEntry | None = None) -> None:
        """Initialize HVAC fan card config flow."""
        super().__init__(config_entry)
        self._feature_id = "hvac_fan_card"

    async def async_init_feature(
        self, hass: HomeAssistant, feature_id: str, feature_config: dict[str, Any]
    ) -> None:
        """Initialize feature-specific context."""
        await super().async_init_feature(hass, feature_id, feature_config)

        _LOGGER.info("🔧 Initialized HVAC Fan Card config flow")

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Handle the initial step - show card-only configuration info."""
        if user_input is not None:
            # Card-only feature, configuration is automatic
            return cast(
                dict[str, Any],
                self.async_create_entry(
                    title="",
                    data={"feature_id": self._feature_id, "card_only": True},
                ),
            )

        # Build info text for card-only feature
        info_text = (
            "**HVAC Fan Card Configuration**\n\n"
            "This is a card-only feature that automatically creates entities "
            "for all compatible devices.\n\n"
            "✅ **Status:** Ready\n\n"
            "The HVAC Fan Card will be available in your dashboard once the "
            "feature is enabled.\n"
            "No additional device configuration is required.\n\n"
            "**Features include:**\n"
            "• Advanced fan control interface\n"
            "• Real-time airflow visualization\n"
            "• Parameter configuration\n"
            "• Device-specific optimizations\n\n"
            "Proceed with card-only configuration?"
        )

        from voluptuous import vol

        schema = vol.Schema({})

        return cast(
            dict[str, Any],
            self.async_show_form(
                step_id="user",
                data_schema=schema,
                description_placeholders={"info": info_text},
            ),
        )

    async def async_step_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Handle confirmation step - card-only feature."""
        if user_input is not None:
            if user_input.get("confirm", False):
                config = {
                    "feature_id": self._feature_id,
                    "card_only": True,
                    "auto_configured": True,
                }
                return cast(
                    dict[str, Any], self.async_create_entry(title="", data=config)
                )
            return await self.async_step_user()

        confirmation_text = (
            "**HVAC Fan Card Configuration Summary**\n\n"
            "✅ Card-only feature configuration\n"
            "✅ No device selection required\n"
            "✅ Automatic entity creation for all compatible devices\n\n"
            "The HVAC Fan Card will be ready to use once you enable the feature.\n\n"
            "Proceed with this configuration?"
        )

        from voluptuous import vol

        schema = vol.Schema(
            {
                vol.Required("confirm", default=False): bool,
            }
        )

        return cast(
            dict[str, Any],
            self.async_show_form(
                step_id="confirm",
                data_schema=schema,
                description_placeholders={"info": confirmation_text},
            ),
        )

    async def _save_device_configuration(self) -> dict[str, Any]:
        """Save device configuration - not applicable for card-only feature.

        Returns:
            Configuration dictionary for card-only feature
        """
        config = {
            "feature_id": self._feature_id,
            "card_only": True,
            "auto_configured": True,
        }

        return config  # noqa: RET504
