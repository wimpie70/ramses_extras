"""Device filtering utilities for feature-specific device selection."""

import logging
from typing import Any, Dict, List

_LOGGER = logging.getLogger(__name__)


class DeviceFilter:
    """Filter devices based on feature requirements."""

    @staticmethod
    def filter_devices_for_feature(
        feature_config: dict[str, Any], devices: list[Any]
    ) -> list[Any]:
        """Filter devices by allowed slugs.

        Args:
            feature_config: Feature configuration with allowed_device_slugs
            devices: List of device objects to filter

        Returns:
            List of devices that match the feature's requirements
        """
        allowed_slugs = feature_config.get("allowed_device_slugs", ["*"])

        if "*" in allowed_slugs:
            _LOGGER.debug("Wildcard device filtering - allowing all devices")
            return devices

        filtered_devices = []
        for device in devices:
            device_slugs = DeviceFilter._get_device_slugs(device)
            if any(slug in device_slugs for slug in allowed_slugs):
                filtered_devices.append(device)
                _LOGGER.debug(f"Device {device} matches feature requirements")

        _LOGGER.info(
            f"Filtered {len(devices)} devices to {len(filtered_devices)} matching devices"  # noqa: E501
        )
        return filtered_devices

    @staticmethod
    def _get_device_slugs(device: Any) -> list[str]:
        """Extract slugs from device object.

        Args:
            device: Device object or device ID string

        Returns:
            List of device slugs
        """
        if isinstance(device, str):
            # Device ID string - assume it's a slug
            return [device]

        # Try to get slugs from device object
        if hasattr(device, "slugs"):
            slugs = getattr(device, "slugs", [])
            return slugs if isinstance(slugs, list) else [str(slugs)]

        if hasattr(device, "slug"):
            return [device.slug]

        if hasattr(device, "device_type"):
            return [device.device_type]

        if hasattr(device, "type"):
            return [device.type]

        # Fallback to class name
        if hasattr(device, "__class__"):
            class_name = device.__class__.__name__
            return [class_name]

        _LOGGER.warning(f"Could not determine slugs for device: {device}")
        return ["unknown"]

    @staticmethod
    def is_device_allowed_for_feature(
        device: Any, feature_config: dict[str, Any]
    ) -> bool:
        """Check if a single device is allowed for a feature.

        Args:
            device: Device object or ID
            feature_config: Feature configuration

        Returns:
            True if device is allowed, False otherwise
        """
        allowed_slugs = feature_config.get("allowed_device_slugs", ["*"])
        if "*" in allowed_slugs:
            return True

        device_slugs = DeviceFilter._get_device_slugs(device)
        return any(slug in device_slugs for slug in allowed_slugs)

    @staticmethod
    def get_supported_device_types(feature_config: dict[str, Any]) -> list[str]:
        """Get supported device types for a feature.

        Args:
            feature_config: Feature configuration

        Returns:
            List of supported device types/slugs
        """
        slugs = feature_config.get("allowed_device_slugs", ["*"])
        return slugs if isinstance(slugs, list) else [slugs]
