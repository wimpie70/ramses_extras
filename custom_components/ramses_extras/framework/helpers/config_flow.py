"""Config flow utilities for Ramses Extras feature configuration."""

import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers import selector

from custom_components.ramses_extras.const import AVAILABLE_FEATURES
from custom_components.ramses_extras.framework.helpers.device.filter import DeviceFilter
from custom_components.ramses_extras.framework.helpers.entity.device_feature_matrix import (  # noqa: E501
    DeviceFeatureMatrix,
)

_LOGGER = logging.getLogger(__name__)


class ConfigFlowHelper:
    """Helper class for config flow operations."""

    def __init__(self, hass: Any, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize the config flow helper.

        Args:
            hass: Home Assistant instance
            config_entry: Current config entry
        """
        self.hass = hass
        self.config_entry = config_entry
        self.device_feature_matrix = DeviceFeatureMatrix()
        self.device_filter = DeviceFilter()

    def get_feature_config_schema(
        self, feature_id: str, devices: list[Any]
    ) -> vol.Schema:
        """Generate configuration schema for a specific feature.

        Args:
            feature_id: Feature identifier
            devices: List of available devices

        Returns:
            Voluptuous schema for feature configuration
        """
        feature_config = AVAILABLE_FEATURES.get(feature_id, {})
        feature_name = feature_config.get("name", feature_id)  # noqa: F841

        # Filter devices for this feature
        filtered_devices = self.device_filter.filter_devices_for_feature(
            feature_config, devices
        )

        # Create device selection options
        device_options = [
            selector.SelectOptionDict(
                value=device_id, label=self._get_device_label(device)
            )
            for device in filtered_devices
            if (device_id := self._extract_device_id(device))
        ]

        # Add schema for device selection
        schema = vol.Schema(
            {
                vol.Required("enabled_devices", default=[]): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=device_options,
                        multiple=True,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
            }
        )

        return schema  # noqa: RET504

    def _extract_device_id(self, device: Any) -> str | None:
        """Extract device ID from device object.

        Args:
            device: Device object

        Returns:
            Device ID as string or None
        """
        if isinstance(device, str):
            return device

        if hasattr(device, "id"):
            return str(device.id)
        if hasattr(device, "device_id"):
            return str(device.device_id)
        if hasattr(device, "_id"):
            return str(device._id)
        if hasattr(device, "name"):
            return str(device.name)

        return None

    def _get_device_label(self, device: Any) -> str:
        """Get display label for a device.

        Args:
            device: Device object

        Returns:
            Display label for the device
        """
        if isinstance(device, str):
            return device

        if hasattr(device, "name"):
            return str(device.name)
        if hasattr(device, "device_id"):
            return str(device.device_id)
        if hasattr(device, "id"):
            return str(device.id)

        return "Unknown Device"

    def get_feature_info(self, feature_id: str) -> dict[str, Any]:
        """Get information about a specific feature.

        Args:
            feature_id: Feature identifier

        Returns:
            Dictionary with feature information
        """
        feature_config = AVAILABLE_FEATURES.get(feature_id, {})
        return {
            "name": feature_config.get("name", feature_id),
            "description": feature_config.get("description", ""),
            "allowed_device_slugs": feature_config.get("allowed_device_slugs", ["*"]),
            "has_device_config": feature_config.get("has_device_config", False),
        }

    def get_enabled_devices_for_feature(self, feature_id: str) -> list[str]:
        """Get devices currently enabled for a specific feature.

        Args:
            feature_id: Feature identifier

        Returns:
            List of device IDs enabled for this feature
        """
        return self.device_feature_matrix.get_enabled_devices_for_feature(feature_id)

    def set_enabled_devices_for_feature(
        self, feature_id: str, device_ids: list[str]
    ) -> None:
        """Set devices enabled for a specific feature.

        Args:
            feature_id: Feature identifier
            device_ids: List of device IDs to enable
        """
        # Clear existing devices for this feature
        for device_id in self.device_feature_matrix.get_enabled_devices_for_feature(
            feature_id
        ):
            self.device_feature_matrix.remove_feature_for_device(device_id, feature_id)

        # Set new devices
        for device_id in device_ids:
            self.device_feature_matrix.enable_feature_for_device(device_id, feature_id)

    def is_device_enabled_for_feature(self, device_id: str, feature_id: str) -> bool:
        """Check if a device is enabled for a specific feature.

        Args:
            device_id: Device identifier
            feature_id: Feature identifier

        Returns:
            True if device is enabled for feature, False otherwise
        """
        return self.device_feature_matrix.is_device_enabled_for_feature(
            device_id, feature_id
        )

    def get_all_feature_device_combinations(self) -> list[tuple[str, str]]:
        """Get all enabled feature/device combinations.

        Returns:
            List of (feature_id, device_id) tuples
        """
        return self.device_feature_matrix.get_all_enabled_combinations()

    def get_devices_for_feature_selection(
        self, feature_config: dict[str, Any], all_devices: list[Any]
    ) -> list[Any]:
        """Get devices that are compatible with a feature for selection UI.

        Args:
            feature_config: Feature configuration
            all_devices: All available devices

        Returns:
            List of devices compatible with the feature
        """
        return self.device_filter.filter_devices_for_feature(
            feature_config, all_devices
        )

    def get_feature_selection_schema(
        self, current_features: dict[str, bool]
    ) -> vol.Schema:
        """Generate schema for main feature selection.

        Args:
            current_features: Currently enabled features

        Returns:
            Voluptuous schema for feature selection
        """
        # Get current selected features for the selector default
        current_selected = [
            k for k, v in current_features.items() if v and k != "default"
        ]

        # Build options for multi-select
        feature_options = []
        for feature_key, feature_config in AVAILABLE_FEATURES.items():
            # Skip default feature from user configuration
            if feature_key == "default":
                continue

            feature_name = str(feature_config.get("name", feature_key))
            description = str(feature_config.get("description", ""))
            if description:
                short_desc = (
                    description[:60] + "..." if len(description) > 60 else description
                )
                label = f"{feature_name} - {short_desc}"
            else:
                label = feature_name

            feature_options.append(
                selector.SelectOptionDict(value=feature_key, label=label)
            )

        schema = vol.Schema(
            {
                vol.Optional(
                    "features", default=current_selected
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=feature_options,
                        multiple=True,
                    )
                ),
            }
        )

        return schema  # noqa: RET504

    def build_feature_info_text(self) -> str:
        """Build detailed feature information text for UI.

        Returns:
            Formatted text with feature information
        """
        feature_summaries = []
        for feature_key, feature_config in AVAILABLE_FEATURES.items():
            # Skip default feature from user display
            if feature_key == "default":
                continue

            name = str(feature_config.get("name", feature_key))
            description = str(feature_config.get("description", ""))

            detail_parts = [f"**{name}**"]
            if description:
                detail_parts.append(description)

            # Add supported device types
            supported_devices = feature_config.get("allowed_device_slugs", ["*"])
            if isinstance(supported_devices, list) and supported_devices:
                if supported_devices == ["*"]:
                    detail_parts.append("Device Types: All device types")
                else:
                    detail_parts.append(
                        f"Device Types: {', '.join(str(d) for d in supported_devices)}"
                    )

            feature_summaries.append("• " + "\n  ".join(detail_parts))

        features_info = "\n\n".join(feature_summaries)

        info_text = "Configure which Ramses Extras features are enabled."
        info_text += "\n📖 For detailed documentation, visit: https://github.com/wimpie70/ramses_extras/wiki"
        info_text += f"\n\n**Available Features:**\n{features_info}"

        return info_text

    def get_feature_device_matrix_state(self) -> dict[str, dict[str, bool]]:
        """Get the current device/feature matrix state.

        Returns:
            Dictionary representing the current matrix state
        """
        return self.device_feature_matrix.get_matrix_state()

    def restore_matrix_state(self, state: dict[str, dict[str, bool]]) -> None:
        """Restore device/feature matrix from saved state.

        Args:
            state: Matrix state to restore
        """
        self.device_feature_matrix.matrix = state.copy()

    def get_feature_device_summary(self) -> str:
        """Get summary of feature/device enablement.

        Returns:
            Formatted summary text
        """
        combinations = self.get_all_feature_device_combinations()
        if not combinations:
            return "No feature/device combinations configured."

        summary_parts = []
        feature_devices: dict[str, list[str]] = {}

        # Group by feature
        for feature_id, device_id in combinations:
            if feature_id not in feature_devices:
                feature_devices[feature_id] = []
            feature_devices[feature_id].append(device_id)

        for feature_id, devices in feature_devices.items():
            feature_name = AVAILABLE_FEATURES.get(feature_id, {}).get(
                "name", feature_id
            )
            summary_parts.append(f"**{feature_name}**: {len(devices)} devices")

        return "Feature/Device Configuration:\n• " + "\n• ".join(summary_parts)

    def discover_feature_config_flows(self) -> dict[str, Any]:
        """Discover feature-specific config flow implementations
         (only for features that need them).

        Returns:
            Dictionary mapping feature_id to config flow class
        """
        import importlib
        import inspect
        from typing import Any

        feature_config_flows = {}

        for feature_id, feature_config in AVAILABLE_FEATURES.items():
            # Skip features that don't need config flow
            if not feature_config.get("has_device_config", False):
                continue

            # Skip default feature
            if feature_id == "default":
                continue

            # Try to import the feature's config flow module
            try:
                module_path = (
                    f"custom_components.ramses_extras.features.{feature_id}.config_flow"
                )
                module = importlib.import_module(module_path)

                # Look for the config flow class
                config_flow_class = None
                for name, obj in inspect.getmembers(module):
                    if (
                        inspect.isclass(obj)
                        and hasattr(obj, "get_feature_config_schema")
                        and hasattr(obj, "get_feature_info")
                    ):
                        config_flow_class = obj
                        break

                if config_flow_class:
                    feature_config_flows[feature_id] = config_flow_class
                    _LOGGER.info(f"Discovered config flow for feature: {feature_id}")
                else:
                    _LOGGER.debug(
                        f"No valid config flow class found for feature: {feature_id}"
                    )

            except ImportError:
                _LOGGER.debug(f"No config flow found for feature: {feature_id}")
            except Exception as e:
                _LOGGER.error(f"Error loading config flow for {feature_id}: {e}")

        return feature_config_flows
