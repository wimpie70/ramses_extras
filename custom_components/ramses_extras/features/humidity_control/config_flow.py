"""Config flow for Humidity Control feature.

This implements a device-specific config flow that allows users to select
which devices they want to enable humidity control for, supporting the
lazy entity creation pattern.
"""

import logging
from typing import Any, cast

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from ...framework.helpers.config.feature_config_flow import FeatureConfigFlowBase
from ...framework.helpers.device_selection import DeviceSelectionManager

_LOGGER = logging.getLogger(__name__)


class HumidityControlConfigFlow(FeatureConfigFlowBase):
    """Config flow for Humidity Control feature with device selection."""

    def __init__(self, config_entry: ConfigEntry | None = None) -> None:
        """Initialize humidity control config flow."""
        super().__init__(config_entry)
        self._feature_id = "humidity_control"

    async def async_init_feature(
        self, hass: HomeAssistant, feature_id: str, feature_config: dict[str, Any]
    ) -> None:
        """Initialize feature-specific context."""
        await super().async_init_feature(hass, feature_id, feature_config)

        _LOGGER.info("🔧 Initialized Humidity Control config flow")

    async def _save_device_configuration(self) -> dict[str, Any]:
        """Save device configuration and create entities.

        Returns:
            Configuration dictionary with selected devices
        """
        if not self._hass:
            return {}

        _LOGGER.info(
            f"💾 Saving humidity control device configuration: "
            f"{self._pending_device_selection}"
        )

        # Create configuration with selected devices
        config = {
            "selected_devices": self._pending_device_selection,
            "feature_id": self._feature_id,
        }

        return config  # noqa: RET504

    async def async_step_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Handle confirmation step with humidity-specific details."""
        if user_input is not None:
            if user_input.get("confirm", False):
                config = await self._save_device_configuration()
                return cast(
                    dict[str, Any], self.async_create_entry(title="", data=config)
                )
            return cast(dict[str, Any], await self.async_step_user())

        # Build confirmation text specific to humidity control
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
            else "• No devices selected"
        )

        confirmation_text = (
            f"**Humidity Control Configuration**\n\n"
            f"Selected devices for humidity control:\n"
            f"{device_list}\n\n"
            f"Entities will be created only for the selected devices.\n"
            f"This includes:\n"
            f"• Humidity control switches\n"
            f"• Target humidity numbers\n"
            f"• Dehumidifying status sensors\n"
            f"• Brand-specific entities (Orcon/Zehnder)\n\n"
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
