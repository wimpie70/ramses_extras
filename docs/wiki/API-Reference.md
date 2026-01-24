# API Reference

This page is derived from `docs/RAMSES_EXTRAS_ARCHITECTURE.md` section 12.

This is a **high-level** reference of commonly used (or externally visible)
interfaces. The internal framework evolves quickly; for full details, refer to
the source and docstrings.

## DeviceFeatureMatrix API

Core responsibilities:

- track which features are enabled for which devices
- serialize/restore matrix state

Key methods:

- `enable_feature_for_device(device_id, feature_id)`
- `get_enabled_features_for_device(device_id) -> dict[str, bool]`
- `get_enabled_devices_for_feature(feature_id) -> list[str]`
- `is_feature_enabled_for_device(feature_id, device_id) -> bool`
- `get_all_enabled_combinations() -> list[tuple[str, str]]`
- `get_matrix_state() -> dict[str, dict[str, bool]]`
- `restore_matrix_state(state)`

## SimpleEntityManager API

Core responsibilities:

- reconcile "required entities" vs "current entities"
- create/remove entities via HA registries

Common entry points:

- `validate_entities_on_startup()`
- `calculate_entity_changes(old_state, new_state)`
- `create_entities_for_feature(feature_id, device_ids)`
- `remove_entities_for_feature(feature_id, device_ids)`

## WebSocket commands API

The integration exposes a set of WebSocket commands for UI components and
debugging.

Common command types (examples):

- `ramses_extras/default/get_bound_rem`
- `ramses_extras/default/get_2411_schema`
- `ramses_extras/default/get_enabled_features`
- `ramses_extras/default/get_cards_enabled`
- `ramses_extras/get_available_devices`
- `ramses_extras/get_entity_mappings`

These commands are intended to be consumed from Lovelace cards via
`callWebSocket()`.

## Device handler API

Device handlers are used during discovery / creation and may emit events like:

- `ramses_device_ready_for_entities`

Event payloads typically include `device_id`, `device_type`, and the list of
`entity_ids` associated with that device.

## Contents

- DeviceFeatureMatrix API
- SimpleEntityManager API
- WebSocket commands API
- Device handler API

Back to: [Home](Home.md)
Prev: [Debugging and Troubleshooting](Debugging-and-Troubleshooting.md)
Next: [Implementation Details](Implementation-Details.md)
