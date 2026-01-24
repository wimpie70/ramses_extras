# Device Feature Management

This page is derived from `docs/RAMSES_EXTRAS_ARCHITECTURE.md` section 6.

## Overview

Ramses Extras supports **per-device feature management**, allowing users to enable
features only for specific devices.

Internally:

- `DeviceFeatureMatrix` stores which devices have which features enabled.
- `SimpleEntityManager` orchestrates entity lifecycle based on that matrix.

## Device filtering

Each feature can specify which device types it supports using
`allowed_device_slugs`.

Example:

```python
AVAILABLE_FEATURES = {
    "humidity_control": {
        "allowed_device_slugs": ["FAN"],
        # ...
    },
    "hello_world": {
        "allowed_device_slugs": ["*"],
        # ...
    },
}
```

## DeviceFeatureMatrix

The `DeviceFeatureMatrix` tracks which features are enabled for which devices.

High-level usage:

```python
matrix.enable_feature_for_device("fan_device_1", "humidity_control")

features = matrix.get_enabled_features_for_device("fan_device_1")
# Returns: {"humidity_control": True}
```

## Per-device feature enablement (UI flow)

Users can enable features for specific devices through the config flow:

1. Select features.
2. For each feature, select which devices to enable it for.
3. Confirm the changes.
4. The system creates entities only for the selected device/feature combinations.

The generic feature selection step exists, but the actual entity lifecycle flows
through `SimpleEntityManager.validate_entities_on_startup()` and
`SimpleEntityManager.calculate_entity_changes()`.

## Matrix state management (persistence)

The matrix state is stored in the Home Assistant config entry under the
`device_feature_matrix` key so configuration persists across restarts.

## Contents

- Device filtering
- DeviceFeatureMatrix
- Per-device feature enablement
- Matrix state management

Back to: [Home](Home.md)
Prev: [Framework Foundation](Framework-Foundation.md)
Next: [Entity Management](Entity-Management.md)
