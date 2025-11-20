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
) -> None:
    """Build complete entity catalog with existence and feature status.

    This method performs a comprehensive scan of all available features
    and builds a complete catalog of all possible entities, including:
    - Whether each entity currently exists in Home Assistant
    - Whether each entity should exist based on current feature configuration

    Args:
        available_features: All available features configuration from AVAILABLE_FEATURES
        current_features: Currently enabled features configuration

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
    """
```

**Process:**

1. Retrieves all existing entities from Home Assistant entity registry
2. Scans each available feature for its entities
3. Populates `all_possible_entities` with complete entity catalog
4. Sets initial `enabled_by_feature` based on current features

**Performance:** O(n\*m) where n=features, m=avg entities per feature

**Error Handling:**

- Entity registry access failures are logged but don't stop catalog building
- Individual feature scanning errors are logged per feature

### update_feature_targets()

```python
def update_feature_targets(self, target_features: dict[str, bool]) -> None:
    """Update the target features for entity comparison.

    This method updates the enabled_by_feature status for all entities
    based on the new target configuration, allowing proper comparison
    between current and target states.

    Args:
        target_features: New target feature configuration

    Example:
        # After building catalog on current features
        await entity_manager.build_entity_catalog(available_features, current_features)

        # Update to new target configuration
        new_target = {"humidity_control": False, "hvac_fan_card": True}
        entity_manager.update_feature_targets(new_target)

        # Now entities_to_remove/entities_to_create reflect the change
    """
```

**Process:**

1. Updates `target_features` attribute
2. Iterates through all entities in catalog
3. Updates `enabled_by_feature` based on new target configuration

**Performance:** O(k) where k=number of entities in catalog

### get_entities_to_remove()

```python
def get_entities_to_remove(self) -> list[str]:
    """Get list of entities to be removed.

    Entities to remove are those that exist_already but are not enabled_by_feature.
    This represents entities that currently exist but should be removed because
    their features have been disabled.

    Returns:
        List of entity IDs that should be removed

    Example:
        to_remove = entity_manager.get_entities_to_remove()
        print(f"Removing {len(to_remove)} entities: {to_remove}")

        # Output: Removing 3 entities: ['sensor.humidity_32_153289', ...]
    """
```

**Logic:** `exists_already=True AND enabled_by_feature=False`

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

    Returns:
        List of entity IDs that should be created

    Example:
        to_create = entity_manager.get_entities_to_create()
        print(f"Creating {len(to_create)} entities: {to_create}")

        # Output: Creating 5 entities: ['sensor.new_humidity_32_153289', ...]
    """
```

**Logic:** `enabled_by_feature=True AND exists_already=False`

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

    Args:
        feature_id: Feature identifier
        feature_config: Feature configuration
        existing_entities: Set of currently existing entity IDs
    """
```

**Entity Type Handling:**

- **Cards**: File-based entities in www/community
- **Automations**: YAML-based automation patterns
- **Devices**: Entity mappings for discovered devices

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

## Usage Patterns

### Basic Config Flow Integration

```python
class RamsesExtrasOptionsFlowHandler(config_entries.OptionsFlow):
    async def async_step_features(self, user_input):
        # Check for feature changes
        if feature_changes_detected:
            # Initialize EntityManager
            self._entity_manager = EntityManager(self.hass)

            # Build catalog on current features
            await self._entity_manager.build_entity_catalog(
                AVAILABLE_FEATURES, current_features
            )

            # Update to target features
            self._entity_manager.update_feature_targets(new_features)

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
