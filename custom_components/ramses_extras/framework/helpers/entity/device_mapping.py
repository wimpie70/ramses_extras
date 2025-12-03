"""Device/Feature Matrix for per-device feature tracking."""

from typing import cast


class DeviceFeatureMatrix:
    """Track which features are enabled for which devices."""

    def __init__(self) -> None:
        """Initialize the device/feature matrix."""
        self.matrix: dict[
            str, dict[str, bool]
        ] = {}  # {device_id: {feature_id: enabled}}

    def enable_feature_for_device(self, device_id: str, feature_id: str) -> None:
        """Enable a feature for a specific device."""
        if device_id not in self.matrix:
            self.matrix[device_id] = {}
        self.matrix[device_id][feature_id] = True

    def enable_device_for_feature(self, feature_id: str, device_id: str) -> None:
        """Enable a device for a specific feature (convenience method)."""
        self.enable_feature_for_device(device_id, feature_id)

    def get_enabled_features_for_device(self, device_id: str) -> dict[str, bool]:
        """Get all enabled features for a device."""
        return self.matrix.get(device_id, {})

    def get_enabled_devices_for_feature(self, feature_id: str) -> list[str]:
        """Get all devices that have this feature enabled."""
        devices = []
        for device_id, features in self.matrix.items():
            if feature_id in features and features[feature_id]:
                devices.append(device_id)
        return devices

    def is_feature_enabled_for_device(self, feature_id: str, device_id: str) -> bool:
        """Check if feature is enabled for specific device."""
        return self.matrix.get(device_id, {}).get(feature_id, False)

    def is_device_enabled_for_feature(self, device_id: str, feature_id: str) -> bool:
        """Check if device is enabled for specific feature (readable alias)."""
        return self.is_feature_enabled_for_device(feature_id, device_id)

    def get_all_enabled_combinations(self) -> list[tuple[str, str]]:
        """Get all enabled feature/device combinations."""
        combinations = []
        for device_id, features in self.matrix.items():
            for feature_id, enabled in features.items():
                if enabled:
                    combinations.append((device_id, feature_id))
        return combinations

    def clear_matrix(self) -> None:
        """Clear the entire matrix."""
        self.matrix = {}

    def remove_feature_for_device(self, device_id: str, feature_id: str) -> None:
        """Remove a feature from a specific device."""
        if device_id in self.matrix and feature_id in self.matrix[device_id]:
            del self.matrix[device_id][feature_id]
            if not self.matrix[device_id]:  # Clean up empty device entries
                del self.matrix[device_id]

    def get_matrix_state(self) -> dict[str, dict[str, bool]]:
        """Get the current matrix state for debugging/serialization."""
        # Return deep copy to prevent modification of original
        return {
            device_id: features.copy() for device_id, features in self.matrix.items()
        }

    def __str__(self) -> str:
        """String representation of the matrix."""
        return (
            f"DeviceFeatureMatrix({len(self.matrix)} devices, "
            f"{len(self.get_all_enabled_combinations())} combinations)"
        )
