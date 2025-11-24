# EntityManager API Reference

## Overview

The EntityManager is a centralized system for managing entity lifecycle with two primary use cases:

1. **Config Flow Operations**: Managing entity changes during feature configuration updates
2. **Startup Validation**: Validating and cleaning up entities after initial startup

It provides a clean, efficient alternative to scattered list management for tracking, creating, and removing entities based on feature changes.

## Class: EntityManager

### Constructor

```python
class EntityManager:
    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize EntityManager.

        Args:
            hass: Home Assistant instance
        """
        self.hass = hass
        self.all_possible_entities: dict[str, EntityInfo] = {}
        self.current_features: dict[str, bool] = {}
        self.target_features: dict[str, bool] = {}
```

**Parameters:**

- `hass` (HomeAssistant): The Home Assistant instance for accessing HA APIs

**Attributes:**

- `all_possible_entities` (dict[str, EntityInfo]): Complete catalog of all possible entities
- `current_features` (dict[str, bool]): Currently enabled features configuration
- `target_features` (dict[str, bool]): Target features configuration for comparison

## Data Structures

### EntityInfo TypedDict

```python
class EntityInfo(TypedDict):
    exists_already: bool      # Whether entity currently exists in HA
    enabled_by_feature: bool  # Whether entity should exist based on enabled features
    feature_id: str          # Which feature creates this entity
    entity_type: str         # sensor, switch, automation, card, etc.
    entity_name: str         # Base entity name
```

**Fields:**

- `exists_already`: Boolean indicating if entity currently exists in Home Assistant
- `enabled_by_feature`: Boolean indicating if entity should exist based on feature configuration
- `feature_id`: String identifier of the feature that creates this entity
- `entity_type`: String type of entity (sensor, switch, automation, card, etc.)
- `entity_name`: Base name of the entity without type prefix

## Core Methods

### build_entity_catalog()

```python
async def build_entity_catalog(
    self,
    available_features: dict[str, dict[str, Any]],
    current_features: dict[str, bool],
    target_features: dict[str, bool] | None = None,
) -> None:
    """Build complete entity catalog with existence and feature status.

    This method performs a comprehensive scan of all available features
    and builds a complete catalog of all possible entities, including:
    - Whether each entity currently exists in Home Assistant
    - Whether each entity should exist based on current feature configuration

    Args:
        available_features: All available features configuration from AVAILABLE_FEATURES
        current_features: Currently enabled features configuration
        target_features: Target enabled features (for feature change operations).
                        If None, defaults to current_features.

    Raises:
        Exception: If entity registry access fails (logged but not raised)

    Example:
        available_features = {
            "humidity_control": {
                "category": "sensor",
                "supported_device_types": ["HvacVentilator"]
            },
            "hvac_fan_card": {
                "category": "cards",
                "location": "hvac_fan_card"
            }
        }
        current_features = {"humidity_control": True, "hvac_fan_card": False}

        entity_manager = EntityManager(hass)
        await entity_manager.build_entity_catalog(available_features, current_features)

        # All entities now available in entity_manager.all_possible_entities

        # For feature change operations, specify target features
        target_features = {"humidity_control": False, "hvac_fan_card": True}
        await entity_manager.build_entity_catalog(
            available_features, current_features, target_features
        )
    """
```

**Process:**

1. Retrieves all existing entities from Home Assistant entity registry
2. Scans each available feature for its entities
3. Populates `all_possible_entities` with complete entity catalog
4. Sets initial `enabled_by_feature` based on current features

**Performance:** O(n\*m) where n=features, m=avg entities per feature

**Error Handling:**

- Entity registry access failures are logged but don't stop catalog building (returns empty set)
- Individual feature scanning errors are logged per feature but don't stop other features
- Device discovery failures fall back to entity registry discovery
- Broker access failures try multiple access patterns before giving up
- All operations are designed for graceful degradation - catalog building continues even with partial failures

### update_feature_targets()

```python
def update_feature_targets(self, target_features: dict[str, bool]) -> None:
    """Update the target features for entity comparison.

    This method updates the enabled_by_feature status for all entities
    based on the new target configuration, allowing proper comparison
    between current and target states.

    For features not explicitly specified in target_features, it uses
    the default_enabled value from AVAILABLE_FEATURES.

    Args:
        target_features: New target feature configuration

    Example:
        # After building catalog on current features
        await entity_manager.build_entity_catalog(available_features, current_features)

        # Update to new target configuration
        new_target = {"humidity_control": False, "hvac_fan_card": True}
        entity_manager.update_feature_targets(new_target)

        # Now entities_to_remove/entities_to_create reflect the change
        # Features not in target_features use their default_enabled values
    """
```

**Process:**

1. Updates `target_features` attribute
2. Iterates through all entities in catalog
3. For each entity, gets the feature's default_enabled from AVAILABLE_FEATURES
4. Updates `enabled_by_feature` based on target_features or default_enabled

**Performance:** O(k) where k=number of entities in catalog

### get_entities_to_remove()

```python
def get_entities_to_remove(self) -> list[str]:
    """Get list of entities to be removed.

    Entities to remove are those that exist_already but are not enabled_by_feature.
    This represents entities that currently exist but should be removed because
    their features have been disabled.

    Note: This method excludes entities from always-enabled features like 'default'
    and only returns platform entities (sensor, switch, etc.), not cards or automations.

    Returns:
        List of entity IDs that should be removed

    Example:
        to_remove = entity_manager.get_entities_to_remove()
        print(f"Removing {len(to_remove)} entities: {to_remove}")

        # Output: Removing 3 entities: ['sensor.humidity_32_153289', ...]
        # Note: Entities from 'default' feature are never included in removal lists
    """
```

**Logic:** `exists_already=True AND enabled_by_feature=False AND feature_id != "default" AND entity_type not in ("card", "automation")`

**Performance:** O(k) where k=number of entities

**Common Use Cases:**

- Displaying removal confirmation to users
- Logging entity cleanup operations
- Bulk entity removal operations

### get_entities_to_create()

```python
def get_entities_to_create(self) -> list[str]:
    """Get list of entities to be created.

    Entities to create are those that are enabled_by_feature but do not exist_already.
    This represents entities that should exist because their features have been enabled,
    but they don't currently exist in Home Assistant.

    Note: This method only returns platform entities (sensor, switch, etc.), not cards or automations.

    Returns:
        List of entity IDs that should be created

    Example:
        to_create = entity_manager.get_entities_to_create()
        print(f"Creating {len(to_create)} entities: {to_create}")

        # Output: Creating 5 entities: ['sensor.new_humidity_32_153289', ...]
    """
```

**Logic:** `enabled_by_feature=True AND exists_already=False AND entity_type not in ("card", "automation")`

**Performance:** O(k) where k=number of entities

**Common Use Cases:**

- Displaying creation confirmation to users
- Logging entity creation operations
- Scheduling entity creation

### get_entity_summary()

```python
def get_entity_summary(self) -> dict[str, int]:
    """Get summary of entity catalog status.

    Provides comprehensive statistics about the entity catalog state,
    useful for user feedback and logging.

    Note: This method only counts platform entities (sensor, switch, etc.),
    excluding cards, automations, and entities from always-enabled features like 'default'.

    Returns:
        Dictionary with counts for different entity states:
        - total_entities: Total number of possible entities
        - existing_enabled: Entities that exist and should continue to exist
        - existing_disabled: Entities that exist but should be removed
        - non_existing_enabled: Entities that don't exist but should be created
        - non_existing_disabled: Entities that don't exist and shouldn't exist

    Example:
        summary = entity_manager.get_entity_summary()
        print(f"Total entities: {summary['total_entities']}")
        print(f"Keeping: {summary['existing_enabled']}")
        print(f"Removing: {summary['existing_disabled']}")
        print(f"Creating: {summary['non_existing_enabled']}")

        # Output:
        # Total entities: 50
        # Keeping: 30
        # Removing: 5
        # Creating: 10
        # Note: Cards, automations, and 'default' feature entities are excluded
    """
```

**Returns:**

```python
{
    "total_entities": int,
    "existing_enabled": int,
    "existing_disabled": int,
    "non_existing_enabled": int,
    "non_existing_disabled": int
}
```

**Performance:** O(k) where k=number of entities

### apply_entity_changes()

```python
async def apply_entity_changes(self) -> None:
    """Apply removal and creation operations.

    This is the main method for applying entity changes. It:
    1. Gets entities to remove and create
    2. Groups entities by type for efficient bulk operations
    3. Applies removal operations for entities that should be removed
    4. Applies creation operations for entities that should be created
    5. Handles errors gracefully and logs results

    Note: Entity creation is typically handled by integration reload,
    so this method mainly updates the catalog and handles removals.

    Raises:
        Exception: Logs but doesn't raise exceptions for individual operations

    Example:
        entity_manager = EntityManager(hass)
        await entity_manager.build_entity_catalog(available_features, current_features)
        entity_manager.update_feature_targets(new_features)

        # Apply all changes
        await entity_manager.apply_entity_changes()
    """
```

**Process:**

1. Gets entities to remove/create using internal methods
2. Groups entities by type for efficient operations
3. Calls appropriate bulk removal/creation methods
4. Logs results and handles errors

**Performance:** O(k + r + c) where k=entities, r=removals, c=creations

## Internal Methods

### \_get_all_existing_entities()

```python
async def _get_all_existing_entities(self) -> set[str]:
    """Get all entity IDs that currently exist in Home Assistant.

    Returns:
        Set of existing entity IDs
    """
```

**Error Handling:** Returns empty set on registry access failures

### \_scan_feature_entities()

```python
async def _scan_feature_entities(
    self,
    feature_id: str,
    feature_config: dict[str, Any],
    existing_entities: set[str],
) -> None:
    """Scan a specific feature for its entities.

    This is an internal method called by build_entity_catalog for each feature.
    Only scans features that are currently enabled or will be enabled (target_enabled or current_enabled).
    Uses default_enabled from feature_config for features not explicitly configured.

    Args:
        feature_id: Feature identifier
        feature_config: Feature configuration
        existing_entities: Set of currently existing entity IDs
    """
```

**Feature Enablement Logic:**
- Gets `default_enabled` from feature_config (defaults to False)
- Checks `target_enabled = target_features.get(feature_id, default_enabled)`
- Checks `current_enabled = current_features.get(feature_id, default_enabled)`
- Only scans if `feature_is_enabled = target_enabled or current_enabled`

**Entity Type Handling:**

- **Cards**: File-based entities in /local/ramses_extras/features (if feature has cards)
- **Devices**: Entity mappings for discovered devices (always scanned for enabled features)

### \_find_automations_by_pattern()

```python
async def _find_automations_by_pattern(self, feature_id: str) -> list[str]:
    """Find automations matching a feature pattern.

    Args:
        feature_id: Feature identifier

    Returns:
        List of matching automation IDs
    """
```

### \_get_devices_for_feature()

```python
async def _get_devices_for_feature(
    self, feature_id: str, supported_devices: list[str]
) -> list[Any]:
    """Get devices that support a specific feature.

    Args:
        feature_id: Feature identifier
        supported_devices: List of supported device types

    Returns:
        List of devices
    """
```

### \_remove_entities()

```python
async def _remove_entities(self, entity_ids: list[str]) -> None:
    """Remove specified entities.

    Groups entities by type and calls appropriate removal methods.

    Args:
        entity_ids: List of entity IDs to remove
    """
```

**Entity Type Handling:**

- `_remove_card_entities()`: Removes card files
- `_remove_automation_entities()`: Removes automation patterns
- `_remove_regular_entities()`: Removes HA entities via registry

### \_create_entities()

```python
async def _create_entities(self, entity_ids: list[str]) -> None:
    """Create specified entities.

    Note: Entity creation typically happens through integration reload.
    This method mainly updates the catalog for tracking purposes.

    Args:
        entity_ids: List of entity IDs to create
    """
```

## Additional Internal Methods

The EntityManager implementation includes several additional internal methods for enhanced device discovery, feature scanning, and entity management:

### Device Discovery Methods

#### get_broker_for_entry()

```python
async def get_broker_for_entry(self, entry: Any) -> Any:
    """Get broker for a config entry using all possible methods.

    This method supports multiple versions of ramses_cc for backwards compatibility.
    Tries all possible broker access patterns from newest to oldest.

    Args:
        entry: Config entry

    Returns:
        Broker object or None
    """
```

**Access Patterns (tried in order):**
1. `hass.data["ramses_cc"][entry.entry_id]` (newest)
2. `hass.data["ramses_cc"]` directly (older structure)
3. `entry.broker` (older versions)
4. `hass.data["ramses_cc"][DOMAIN]` (very old)
5. Any attribute containing 'devices'

#### \_discover_devices_direct()

```python
async def _discover_devices_direct(self) -> list[Any]:
    """Direct device discovery as fallback for EntityManager.

    This method uses the same device discovery logic as the main integration.
    """
```

**Discovery Process:**
1. Access ramses_cc broker using all possible methods
2. Extract devices from broker (`_devices`, `devices`, etc.)
3. Filter for relevant device types (HvacVentilator, HvacController, etc.)
4. Return discovered devices

#### \_discover_devices_from_entity_registry()

```python
async def _discover_devices_from_entity_registry(self) -> list[str]:
    """Fallback method to discover devices from entity registry.

    Returns:
        List of device IDs
    """
```

**Process:**
- Scans entity registry for ramses_cc entities
- Extracts unique device IDs from entity device_id fields
- Returns list of device ID strings

### Feature Scanning Methods

#### \_get_supported_devices_from_feature()

```python
async def _get_supported_devices_from_feature(self, feature_id: str) -> list[str]:
    """Get supported device types from the feature's own const.py module.

    Uses required_entities approach for registry building.

    Args:
        feature_id: Feature identifier

    Returns:
        List of supported device types
    """
```

#### \_get_required_entities_for_feature()

```python
async def _get_required_entities_for_feature(
    self, feature_id: str
) -> dict[str, list[str]]:
    """Get required entities for a feature (async wrapper).

    Args:
        feature_id: Feature identifier

    Returns:
        Required entities dictionary mapping entity_type to list of entity names
    """
```

#### \_feature_has_cards()

```python
async def _feature_has_cards(self, feature_id: str) -> bool:
    """Check if a feature has card configurations defined.

    Args:
        feature_id: Feature identifier

    Returns:
        True if feature has card configurations, False otherwise
    """
```

### Entity Addition Methods

#### \_add_card_entities()

```python
async def _add_card_entities(
    self, feature_id: str, feature_config: dict[str, Any], enabled: bool
) -> None:
    """Add card entities for a feature.

    Args:
        feature_id: Feature identifier
        feature_config: Feature configuration
        enabled: Whether the feature is enabled
    """
```

**Process:**
- Creates card entity with ID `local_ramses_extras_features_{feature_id}`
- Sets `exists_already=False` (cards are file-based)
- Adds to `all_possible_entities` catalog

#### \_add_device_entities()

```python
async def _add_device_entities(
    self,
    feature_id: str,
    feature_config: dict[str, Any],
    enabled: bool,
    supported_devices: list[str],
) -> None:
    """Add device-based entities for a feature.

    Args:
        feature_id: Feature identifier
        feature_config: Feature configuration
        enabled: Whether the feature is enabled
        supported_devices: List of supported device types
    """
```

**Process:**
1. Gets devices for the feature
2. For each device, gets required entities from feature config
3. Generates entity IDs using standard naming pattern
4. Checks entity existence in registry
5. Handles entity ownership conflicts (prevents overwriting)
6. Adds entities to catalog

### Utility Methods

#### \_extract_device_id()

```python
def _extract_device_id(self, device: Any) -> str:
    """Extract device ID from device object or string with robust error handling.

    Args:
        device: Device object or device ID string

    Returns:
        Device ID as string
    """
```

**Extraction Priority:**
1. `device.id`
2. `device.device_id`
3. `device._id`
4. `device.name`
5. `str(device)`
6. Fallback: `"device_{id(device)}"`

#### \_extract_device_type()

```python
def _extract_device_type(self, device: Any) -> str:
    """Extract device type with robust error handling.

    Args:
        device: Device object

    Returns:
        Device type as string
    """
```

**Extraction Priority:**
1. `device.__class__.__name__`
2. `device.type`
3. `device.device_type`
4. `type(device).__name__`
5. Fallback: `"UnknownDevice"`

#### \_normalize_devices_list()

```python
def _normalize_devices_list(self, devices: Any) -> list[Any]:
    """Normalize different device storage formats to a list.

    Args:
        devices: Devices in various formats

    Returns:
        List of devices
    """
```

**Supported Formats:**
- `dict`: Returns `list(devices.values())`
- `list`: Returns as-is
- `set`: Converts to `list(devices)`
- Single object: Wraps in `[devices]`

## Usage Patterns

### Basic Config Flow Integration

```python
class RamsesExtrasOptionsFlowHandler(config_entries.OptionsFlow):
    async def async_step_features(self, user_input):
        # Check for feature changes
        if feature_changes_detected:
            # Initialize EntityManager
            self._entity_manager = EntityManager(self.hass)

            # Build catalog with current and target features
            await self._entity_manager.build_entity_catalog(
                AVAILABLE_FEATURES, current_features, target_features=new_features
            )

            # Update to target features (if not passed to build_entity_catalog)
            # self._entity_manager.update_feature_targets(new_features)

            # Get change lists
            self._entities_to_remove = self._entity_manager.get_entities_to_remove()
            self._entities_to_create = self._entity_manager.get_entities_to_create()

            return await self.async_step_confirm()
```

### Startup Validation Integration

```python
async def async_setup_entry(hass, entry):
    """Main integration setup entry point."""
    # ... existing startup flow (load features, discover devices, create entities) ...

    # STEP: Post-creation validation with EntityManager
    _LOGGER.info("🔍 Running EntityManager post-creation validation...")
    await _validate_startup_entities(hass, entry)

async def _validate_startup_entities(hass, entry):
    """Validate startup entity creation and fix discrepancies."""
    try:
        from .framework.helpers.entity.manager import EntityManager

        # Create EntityManager for validation
        entity_manager = EntityManager(hass)

        # Build catalog of what SHOULD exist vs what DOES exist
        await entity_manager.build_entity_catalog(
            AVAILABLE_FEATURES, entry.data.get("enabled_features", {})
        )

        # Get any discrepancies
        entities_to_remove = entity_manager.get_entities_to_remove()
        entities_to_create = entity_manager.get_entities_to_create()

        if entities_to_remove or entities_to_create:
            _LOGGER.warning(
                f"Startup validation found discrepancies: "
                f"remove {len(entities_to_remove)}, create {len(entities_to_create)}"
            )
            # Apply cleanup/creation as needed
            await entity_manager.apply_entity_changes()
        else:
            _LOGGER.info("✅ Startup validation: all entities match expected configuration")

    except Exception as e:
        _LOGGER.error(f"EntityManager startup validation failed: {e}")
        # Don't fail startup if validation fails
```

### Entity Summary for UI

```python
def build_confirmation_message(self):
    """Build user-friendly confirmation message using EntityManager."""
    if not self._entity_manager:
        return "No entity changes detected."

    summary = self._entity_manager.get_entity_summary()
    to_remove = self._entity_manager.get_entities_to_remove()
    to_create = self._entity_manager.get_entities_to_create()

    message_parts = []

    if to_remove:
        message_parts.append(f"**Remove {len(to_remove)} entities:**")
        message_parts.append(f"• {', '.join(to_remove[:3])}{'...' if len(to_remove) > 3 else ''}")

    if to_create:
        message_parts.append(f"**Create {len(to_create)} entities:**")
        message_parts.append(f"• {', '.join(to_create[:3])}{'...' if len(to_create) > 3 else ''}")

    message_parts.append(f"**Summary:** {summary['total_entities']} total, "
                        f"{summary['existing_enabled']} keep, "
                        f"{summary['existing_disabled']} remove, "
                        f"{summary['non_existing_enabled']} create")

    return "\n\n".join(message_parts)
```

### Error Handling Patterns

```python
try:
    entity_manager = EntityManager(self.hass)
    await entity_manager.build_entity_catalog(available_features, current_features)
    entity_manager.update_feature_targets(target_features)

    await entity_manager.apply_entity_changes()

except Exception as e:
    _LOGGER.error(f"EntityManager operation failed: {e}")
    # Continue with config flow, don't block user
```

### Performance Optimization

```python
# GOOD: Single EntityManager instance
entity_manager = EntityManager(self.hass)
await entity_manager.build_entity_catalog(features, current)
entity_manager.update_feature_targets(target)

# BAD: Multiple EntityManager instances
manager1 = EntityManager(self.hass)
await manager1.build_entity_catalog(features, current)
manager2 = EntityManager(self.hass)  # Overwrites first!
await manager2.build_entity_catalog(features, target)
```

## Integration with EntityHelpers

The EntityManager leverages existing EntityHelpers for consistency:

```python
from .core import EntityHelpers, generate_entity_patterns_for_feature, get_feature_entity_mappings

# EntityManager uses EntityHelpers internally
class EntityManager:
    async def _scan_feature_entities(self, feature_id, feature_config, existing_entities):
        # Use existing pattern matching
        patterns = generate_entity_patterns_for_feature(feature_id)
        filtered_entities = EntityHelpers.filter_entities_by_patterns(all_entities, patterns)

        # Use existing entity mappings
        entity_mappings = get_feature_entity_mappings(feature_id, device_id)
```

## Testing Patterns

### Unit Testing

```python
import pytest
from unittest.mock import AsyncMock, MagicMock

def test_entity_manager_basic():
    mock_hass = MagicMock()
    entity_manager = EntityManager(mock_hass)

    # Test initialization
    assert entity_manager.hass == mock_hass
    assert entity_manager.all_possible_entities == {}

    # Test change detection
    entity_manager.all_possible_entities = {
        "sensor.test": {
            "exists_already": True,
            "enabled_by_feature": False,
            "feature_id": "feature1",
            "entity_type": "sensor",
            "entity_name": "test"
        }
    }

    to_remove = entity_manager.get_entities_to_remove()
    assert "sensor.test" in to_remove
```

### Integration Testing

```python
@pytest.mark.asyncio
async def test_entity_manager_workflow():
    mock_hass = MagicMock()
    mock_hass.helpers.entity_registry.async_get.return_value.entities = {}

    entity_manager = EntityManager(mock_hass)

    available_features = {"test_feature": {"category": "sensor", "supported_device_types": []}}
    current_features = {"test_feature": False}
    target_features = {"test_feature": True}

    # Test complete workflow
    await entity_manager.build_entity_catalog(available_features, current_features)
    entity_manager.update_feature_targets(target_features)

    to_create = entity_manager.get_entities_to_create()
    to_remove = entity_manager.get_entities_to_remove()

    assert len(to_create) >= 0  # Depends on device scanning
    assert len(to_remove) == 0  # No entities to remove
```

## Error Handling and Logging

### Standard Log Messages

The EntityManager provides consistent logging:

```python
# Information messages
_LOGGER.info(f"Entity catalog built: {len(self.all_possible_entities)} possible entities")
_LOGGER.info(f"Entities to remove: {len(to_remove)}")
_LOGGER.info(f"Entities to create: {len(to_create)}")

# Warning messages
_LOGGER.warning(f"Could not get entity registry: {e}")
_LOGGER.warning(f"Could not find automations for {feature_id}: {e}")

# Error messages
_LOGGER.error(f"Failed to remove {entity_type} entities: {e}")
```

### Graceful Degradation

```python
async def build_entity_catalog(self, available_features, current_features):
    """Build entity catalog with graceful degradation."""
    try:
        # Try to get existing entities
        existing_entities = await self._get_all_existing_entities()
    except Exception as e:
        _LOGGER.warning(f"Entity registry access failed: {e}")
        existing_entities = set()  # Continue with empty set

    # Continue catalog building even if some features fail
    for feature_id, feature_config in available_features.items():
        try:
            await self._scan_feature_entities(feature_id, feature_config, existing_entities)
        except Exception as e:
            _LOGGER.error(f"Failed to scan feature {feature_id}: {e}")
            continue  # Skip this feature, continue with others
```

## Performance Considerations

### Memory Usage

- **Single Dictionary**: All entities stored in `all_possible_entities` dictionary
- **Type Safety**: EntityInfo TypedDict ensures consistent structure
- **Efficient Queries**: List comprehensions for change detection

### Computational Complexity

- **Catalog Building**: O(n\*m) where n=features, m=avg entities per feature
- **Target Updates**: O(k) where k=entities in catalog
- **Change Detection**: O(k) for each query (to_remove, to_create, summary)

### Best Practices

1. **Single Instance**: Use one EntityManager per config flow operation
2. **Bulk Operations**: Use `apply_entity_changes()` instead of individual operations
3. **Lazy Updates**: Only call `update_feature_targets()` when features actually change
4. **Error Handling**: Always wrap EntityManager calls in try/catch for graceful degradation

## Extensibility

### Adding New Entity Types

```python
# 1. Add to EntityInfo if needed
class EntityInfo(TypedDict):
    # ... existing fields
    new_field: str  # Optional new field for new entity type

# 2. Add scanning logic
async def _scan_feature_entities(self, feature_id, feature_config, existing_entities):
    if feature_config.get("category") == "new_type":
        await self._add_new_type_entities(feature_id, feature_config, existing_entities)
    else:
        # Existing logic

# 3. Add removal logic
async def _remove_entities(self, entity_ids):
    entities_by_type = self._group_entities_by_type(entity_ids)

    if "new_type" in entities_by_type:
        await self._remove_new_type_entities(entities_by_type["new_type"])
```

### Plugin Support

```python
class PluginEntityManager(EntityManager):
    """Extended EntityManager for plugin support."""

    def __init__(self, hass, plugin_registry):
        super().__init__(hass)
        self.plugin_registry = plugin_registry

    async def build_entity_catalog(self, available_features, current_features):
        """Build catalog including plugin entities."""
        await super().build_entity_catalog(available_features, current_features)

        # Add plugin entities
        for plugin in self.plugin_registry.get_active_plugins():
            await self._scan_plugin_entities(plugin)
```

## WebSocket Integration Troubleshooting

### Common WebSocket Errors

#### 1. "WebSocket message failed: Unknown error"

**Symptoms:**
```
❌ WebSocket message failed: Object { code: "unknown_error", message: "Unknown error" }
card-services.js:46:13
```

**Cause:** Missing required parameters in WebSocket call (typically `device_id`)

**Solution:**
```javascript
// INCORRECT - Missing device_id
await callWebSocket(hass, {
  type: 'ramses_extras/get_2411_schema',
});

// CORRECT - Include device_id
await callWebSocket(hass, {
  type: 'ramses_extras/get_2411_schema',
  device_id: this.config.device_id,
});
```

#### 2. "Failed to fetch parameter schema"

**Symptoms:**
```
Failed to fetch parameter schema: Object { code: "unknown_error", message: "Unknown error" }
hvac-fan-card.js:438:15
```

**Cause:** WebSocket command not properly registered or schema validation failing

**Solution:**
1. **Ensure WebSocket commands are registered:** Verify that `register_default_websocket_commands()` is called during module import
2. **Check schema creation:** Ensure voluptuous schemas are properly created, not plain dictionaries

#### 3. "Command registration failed"

**Symptoms:**
```
Failed to register WebSocket command: [command_name]
WebSocket integration setup failed
```

**Cause:** Issues with HA decorator pattern or feature-centric registration

**Solution:**
1. **Verify HA decorator usage:**
```python
# CORRECT - Use HA decorators properly
@websocket_api.websocket_command({
    vol.Required("type"): "ramses_extras/default/get_bound_rem",
    vol.Required("device_id"): str,
})
@websocket_api.async_response
async def ws_get_bound_rem_default(hass, connection, msg):
    # Handler implementation
```

2. **Check feature enablement:**
```python
# Verify feature is enabled in AVAILABLE_FEATURES
AVAILABLE_FEATURES = {
    "default": {
        "default_enabled": True,
        "websocket_commands": ["get_bound_rem", "get_2411_schema"],
    }
}
```

3. **Check integration setup:**
```python
# Ensure websocket_integration.py is called during setup
await async_setup_websocket_integration(hass)
```

### WebSocket Command Registration

#### Automatic Registration
WebSocket commands are automatically registered based on enabled features through the main integration:

```python
# In websocket_integration.py
async def async_register_websocket_commands(hass: HomeAssistant) -> None:
    """Register WebSocket commands for enabled features."""
    enabled_features = get_enabled_features(hass)

    if "default" in enabled_features:
        # Register default feature commands using HA decorators
        from .features.default.websocket_commands import get_default_websocket_commands
        default_commands = get_default_websocket_commands()
        for command_name, command_handler in default_commands.items():
            websocket_api.async_register_command(hass, command_handler)
```

#### Feature-Centric Architecture
Each feature defines its own WebSocket commands:

```python
# In features/default/websocket_commands.py
@websocket_api.websocket_command({
    vol.Required("type"): "ramses_extras/default/get_bound_rem",
    vol.Required("device_id"): str,
})
@websocket_api.async_response
async def ws_get_bound_rem_default(hass, connection, msg):
    """Handle get_bound_rem command with HA decorators."""
    # Implementation using HA's standard pattern
```

### Debugging WebSocket Issues

#### 1. Check Command Registration
```python
from custom_components.ramses_extras.websocket_integration import get_websocket_commands_info

info = get_websocket_commands_info()
print(f"Registered commands: {info}")
```

#### 2. Verify WebSocket Integration Status
```python
from custom_components.ramses_extras.websocket_integration import is_websocket_enabled

if is_websocket_enabled(hass):
    print("WebSocket integration is enabled")
else:
    print("WebSocket integration is not enabled")
```

#### 3. Check Home Assistant Logs
Look for WebSocket registration messages:
```
✅ WebSocket integration setup complete: X commands across Y features
```

### WebSocket Commands API

#### Architecture Overview

The Ramses Extras WebSocket API uses a **feature-centric architecture** where each feature defines its own WebSocket commands using Home Assistant's standard decorator pattern. This approach ensures:

- **Feature isolation**: Commands are organized by feature
- **HA compatibility**: Uses standard HA WebSocket decorators (`@websocket_api.websocket_command`, `@websocket_api.async_response`)
- **Dynamic discovery**: Commands are registered based on enabled features
- **Maintainability**: Each feature manages its own commands

#### Available Commands

**Default Feature Commands:**

- **`ramses_extras/default/get_bound_rem`**
  - **Purpose:** Get bound REM device information
  - **Parameters:** `device_id` (string)
  - **Returns:** `{"device_id": "string", "bound_rem": "string|null"}`

- **`ramses_extras/default/get_2411_schema`**
  - **Purpose:** Get device parameter schema for configuration
  - **Parameters:** `device_id` (string)
  - **Returns:** Dictionary of parameter definitions

- **`ramses_extras` (info command)**
  - **Purpose:** Get information about all available WebSocket commands
  - **Parameters:** None required
  - **Returns:** List of available commands and features

#### JavaScript Usage Example
```javascript
import { callWebSocket } from '/local/ramses_extras/helpers/card-services.js';

// Get bound REM device
const boundRem = await callWebSocket(hass, {
  type: 'ramses_extras/default/get_bound_rem',
  device_id: '32:153289',
});

// Get parameter schema
const schema = await callWebSocket(hass, {
  type: 'ramses_extras/default/get_2411_schema',
  device_id: '32:153289',
});

// Get command info
const commandsInfo = await callWebSocket(hass, {
  type: 'ramses_extras',
});
```

### Integration with EntityManager

WebSocket commands work alongside EntityManager for comprehensive device management:

```python
# EntityManager for entity lifecycle management
entity_manager = EntityManager(hass)
await entity_manager.build_entity_catalog(available_features, current_features)

# WebSocket commands for real-time device communication
# (Get parameter schemas, bound REM info, etc.)
```

## ✅ WebSocket Implementation - Production Ready

### Current State (Feature-Centric Architecture)

**✅ Implemented Features:**
1. **Feature-centric WebSocket architecture** - Each feature defines its own commands
2. **HA standard decorator pattern** - Using `@websocket_api.websocket_command` and `@websocket_api.async_response`
3. **Dynamic command registration** - Commands registered based on enabled features
4. **Proper error handling** - Graceful degradation and detailed logging
5. **Command discovery** - Info endpoint to discover available commands

**🎯 Architecture Benefits:**
1. **Maintainability** - Commands organized by feature
2. **Scalability** - Easy to add new features with their own WebSocket commands
3. **HA Compatibility** - Uses standard Home Assistant WebSocket API patterns
4. **Type Safety** - Proper voluptuous schema validation

### Implementation Details

**File Structure:**
```
websocket_integration.py           # Main integration and registration
features/default/websocket_commands.py    # Default feature commands
features/humidity_control/websocket_commands.py  # Future: humidity control commands
features/hvac_fan_card/websocket_commands.py     # Future: HVAC fan card commands
```

**Registration Flow:**
1. Integration setup calls `async_register_websocket_commands()`
2. System discovers enabled features from configuration
3. Each enabled feature's commands are imported and registered with HA
4. Commands use HA decorators for proper API integration

### Adding New WebSocket Commands

To add WebSocket commands for a new feature:

1. **Create feature websocket_commands.py:**
```python
# features/your_feature/websocket_commands.py
@websocket_api.websocket_command({
    vol.Required("type"): "ramses_extras/your_feature/your_command",
    vol.Required("device_id"): str,
})
@websocket_api.async_response
async def ws_your_command(hass, connection, msg):
    """Handle your custom command."""
    # Implementation here
```

2. **Add to feature config in const.py:**
```python
AVAILABLE_FEATURES["your_feature"] = {
    "websocket_commands": ["your_command"],
    # ... other config
}
```

3. **Commands are automatically registered when feature is enabled**

## Version Compatibility

### Backward Compatibility

- EntityManager maintains compatibility with existing config flows
- Graceful degradation when EntityManager unavailable
- Detailed error logging for debugging

### Future Extensibility

- Modular design allows easy addition of new entity types
- Plugin architecture support for third-party extensions
- API versioning for backward compatibility

This API reference provides comprehensive documentation for developers working with the EntityManager system.
