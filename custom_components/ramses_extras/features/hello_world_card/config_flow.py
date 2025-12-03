"""Config flow for Hello World Card feature.

This implements an optional device-specific config flow that allows users to select
which devices they want to enable hello world card entities for, supporting the
lazy entity creation pattern for this template feature.
"""

import logging
from typing import Any, cast

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from ...framework.helpers.config.feature_config_flow import FeatureConfigFlowBase
from ...framework.helpers.device_selection import DeviceSelectionManager

_LOGGER = logging.getLogger(__name__)


class HelloWorldCardConfigFlow(FeatureConfigFlowBase):
    """Config flow for Hello World Card feature with optional device selection."""

    def __init__(self, config_entry: ConfigEntry | None = None) -> None:
        """Initialize hello world card config flow."""
        super().__init__(config_entry)
        self._feature_id = "hello_world_card"

    async def async_init_feature(
        self, hass: HomeAssistant, feature_id: str, feature_config: dict[str, Any]
    ) -> None:
        """Initialize feature-specific context."""
        await super().async_init_feature(hass, feature_id, feature_config)

        _LOGGER.info("🔧 Initialized Hello World Card config flow")

    async def _save_device_configuration(self) -> dict[str, Any]:
        """Save device configuration and create entities.

        Returns:
            Configuration dictionary with selected devices
        """
        if not self._hass:
            return {}

        _LOGGER.info(
            f"💾 Saving Hello World Card device configuration: "
            f"{self._pending_device_selection}"
        )

        # Create configuration with selected devices
        config = {
            "selected_devices": self._pending_device_selection,
            "feature_id": self._feature_id,
            # Hello World Card can optionally be used without device selection
            "requires_device_selection": False,
        }

        return config  # noqa: RET504

    async def async_step_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Handle confirmation step with hello world card specific details."""
        if user_input is not None:
            if user_input.get("confirm", False):
                config = await self._save_device_configuration()
                return cast(
                    dict[str, Any], self.async_create_entry(title="", data=config)
                )
            return cast(dict[str, Any], await self.async_step_user())

        # Build confirmation text specific to Hello World Card
        selected_devices_info = []
        for device_id in self._pending_device_selection:
            device = next(
                (d for d in self._discovered_devices if d["device_id"] == device_id),
                None,
            )
            if device:
                device_info = f"• {device['name']} ({device['device_type']})"
                if device.get("zone"):
                    device_info += f" (Zone: {device['zone']})"
                selected_devices_info.append(device_info)

        device_list = (
            "\n".join(selected_devices_info)
            if selected_devices_info
            else "• No devices selected - using template defaults"
        )

        confirmation_text = (
            f"**Hello World Card Configuration**\n\n"
            f"Selected devices for Hello World Card entities:\n"
            f"{device_list}\n\n"
            f"Entities will be created for:\n"
            f"• Hello World switch entities\n"
            f"• Binary sensor states\n"
            f"• Number controls (optional)\n"
            f"• Sensor readings\n\n"
            f"Note: Hello World Card entities are template entities.\n"
            f"Device selection is optional - entities will work with or without "
            f"specific devices.\n\n"
            f"Proceed with this configuration?"
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
