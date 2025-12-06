# Ramses Extras Config Flow - Matrix Integration Implementation Plan

## 📋 Executive Summary

**Current State:** Core infrastructure exists (DeviceFeatureMatrix, EntityManager, ConfigFlowHelper) but needs proper integration.

**Problem:** Matrix operations are not connected to entity lifecycle and state persistence.

**Solution:** Implement matrix state persistence, matrix-driven entity operations, and config flow integration.

## 🎯 Implementation Goals

### 1. Matrix State Persistence
**Objective:** Save and restore matrix state across config flow sessions and restarts.

### 2. Matrix-Driven Entity Operations
**Objective:** Make EntityManager use matrix combinations to determine entity creation/removal.

### 3. Config Flow Matrix Integration
**Objective:** Connect feature/device selection to matrix-driven entity operations.

## 🔧 Detailed Implementation Plan

### Phase 1: Matrix State Persistence (1 day)

#### Task 1.1: Add Matrix State Saving
**File:** `config_flow.py` (Add at EOF)
```python
def _save_matrix_state(self):
    """Save current matrix state to config entry data."""
    matrix_state = self._get_config_flow_helper().get_feature_device_matrix_state()
    new_data = dict(self._config_entry.data)
    new_data["device_feature_matrix"] = matrix_state
    self.hass.config_entries.async_update_entry(self._config_entry, data=new_data)
```

#### Task 1.2: Add Matrix State Restoration
**File:** `config_flow.py` (Add at EOF)
```python
def _restore_matrix_state(self):
    """Restore matrix state from config entry."""
    matrix_state = self._config_entry.data.get("device_feature_matrix", {})
    if matrix_state:
        self._get_config_flow_helper().restore_matrix_state(matrix_state)
        _LOGGER.info(f"Restored matrix state with {len(matrix_state)} devices")
```

#### Task 1.3: Integrate Matrix Restoration on Startup
**File:** `__init__.py` (Modify `_validate_startup_entities()`)
```python
# Add after entity_manager creation, before build_entity_catalog
matrix_state = entry.data.get("device_feature_matrix", {})
if matrix_state:
    entity_manager.restore_device_feature_matrix_state(matrix_state)
    _LOGGER.info(f"Restored matrix state with {len(matrix_state)} devices")
```

#### Task 1.4: Call Matrix Saving in Config Flow
**File:** `config_flow.py` (Modify `async_step_feature_config()`)
```python
# Add after matrix updates (around line where set_enabled_devices_for_feature is called)
self._save_matrix_state()
```

### Phase 2: Matrix-Driven Entity Operations (2 days)

#### Task 2.1: Modify Entity Creation Logic
**File:** `entity/manager.py` (Replace `get_entities_to_create()`)
```python
def get_entities_to_create(self) -> list[str]:
    """Get entities to create based on matrix combinations."""
    to_create = []
    combinations = self.device_feature_matrix.get_all_enabled_combinations()

    for device_id, feature_id in combinations:
        # Generate entity IDs for this feature/device combination
        entity_ids = self._generate_entity_ids_for_combination(feature_id, device_id)
        to_create.extend(entity_ids)

    return to_create
```

#### Task 2.2: Modify Entity Removal Logic
**File:** `entity/manager.py` (Replace `get_entities_to_remove()`)
```python
def get_entities_to_remove(self) -> list[str]:
    """Get entities to remove based on matrix combinations."""
    to_remove = []
    all_combinations = self.device_feature_matrix.get_all_enabled_combinations()

    # Get all existing entities that are tracked
    for entity_id, info in self.all_possible_entities.items():
        # Check if this entity's feature/device combination is still enabled
        if (info["feature_id"], self._extract_device_id_from_entity(entity_id)) not in all_combinations:
            to_remove.append(entity_id)

    return to_remove
```

#### Task 2.3: Add Entity ID Generation Helper
**File:** `entity/manager.py` (Add at EOF)
```python
def _generate_entity_ids_for_combination(self, feature_id: str, device_id: str) -> list[str]:
    """Generate entity IDs for a specific feature/device combination."""
    entity_ids = []
    # Get required entities from feature configuration
    required_entities = self._get_required_entities_for_feature(feature_id)

    for entity_type, entity_names in required_entities.items():
        for entity_name in entity_names:
            # Generate entity ID using standard pattern
            entity_id = f"{entity_type}.{entity_name}_{device_id.replace(':', '_')}"
            entity_ids.append(entity_id)

    return entity_ids

def _extract_device_id_from_entity(self, entity_id: str) -> str:
    """Extract device ID from entity ID."""
    # Entity ID format: entity_type.entity_name_device_id
    parts = entity_id.split('_')
    if len(parts) >= 2:
        return parts[-1]  # Last part is device ID
    return entity_id
```

### Phase 3: Config Flow Matrix Integration (1 day)

#### Task 3.1: Connect Feature Config to Matrix Operations
**File:** `config_flow.py` (Modify `async_step_feature_config()`)
```python
# Add after matrix update in async_step_feature_config()
if user_input is not None:
    # ... existing matrix update code ...

    # Get matrix-based entity changes
    entity_manager = EntityManager(self.hass)
    entities_to_create = entity_manager.get_entities_to_create()
    entities_to_remove = entity_manager.get_entities_to_remove()

    # Store for confirmation step
    self._matrix_entities_to_create = entities_to_create
    self._matrix_entities_to_remove = entities_to_remove

    # Show matrix-based confirmation
    return await self._show_matrix_based_confirmation()
```

#### Task 3.2: Add Matrix-Based Confirmation
**File:** `config_flow.py` (Add at EOF)
```python
async def _show_matrix_based_confirmation(self) -> config_entries.FlowResult:
    """Show confirmation with matrix-based entity changes."""
    entities_to_create = getattr(self, '_matrix_entities_to_create', [])
    entities_to_remove = getattr(self, '_matrix_entities_to_remove', [])

    info_text = "🔄 **Matrix-Based Entity Changes**\n\n"

    if entities_to_create:
        info_text += f"📝 **Entities to create**: {len(entities_to_create)}\n"
        info_text += f"- {', '.join(entities_to_create[:5])}"
        if len(entities_to_create) > 5:
            info_text += f" and {len(entities_to_create) - 5} more"

    if entities_to_remove:
        info_text += f"\n\n🗑️ **Entities to remove**: {len(entities_to_remove)}\n"
        info_text += f"- {', '.join(entities_to_remove[:5])}"
        if len(entities_to_remove) > 5:
            info_text += f" and {len(entities_to_remove) - 5} more"

    # Add matrix state summary
    matrix = self._get_config_flow_helper().device_feature_matrix
    info_text += f"\n\n📊 **Matrix State**: {len(matrix.get_all_enabled_combinations())} active combinations"

    return self.async_show_form(
        step_id="matrix_confirm",
        data_schema=vol.Schema({}),
        description_placeholders={"info": info_text},
    )
```

#### Task 3.3: Add Matrix Confirmation Handler
**File:** `config_flow.py` (Add at EOF)
```python
async def async_step_matrix_confirm(
    self, user_input: dict[str, Any] | None = None
) -> config_entries.FlowResult:
    """Handle matrix-based confirmation."""
    if user_input is not None:
        # Apply matrix-based entity changes
        entity_manager = EntityManager(self.hass)
        await entity_manager.apply_entity_changes()

        # Save final matrix state
        self._save_matrix_state()

        # Clear temporary data
        self._matrix_entities_to_create = []
        self._matrix_entities_to_remove = []

        return await self.async_step_main_menu()

    return await self._show_matrix_based_confirmation()
```

## ✅ Implementation Checklist

```markdown
## Matrix Integration Implementation Checklist

### Phase 1: Matrix State Persistence
- [ ] Add `_save_matrix_state()` method to config_flow.py
- [ ] Add `_restore_matrix_state()` method to config_flow.py
- [ ] Integrate matrix restoration in `__init__.py`
- [ ] Call matrix saving after config flow updates
- [ ] Test matrix state persistence

### Phase 2: Matrix-Driven Entity Operations
- [ ] Modify `get_entities_to_create()` in entity/manager.py
- [ ] Modify `get_entities_to_remove()` in entity/manager.py
- [ ] Add `_generate_entity_ids_for_combination()` helper
- [ ] Add `_extract_device_id_from_entity()` helper
- [ ] Test matrix-driven entity operations

### Phase 3: Config Flow Matrix Integration
- [ ] Connect feature config to matrix operations
- [ ] Add `_show_matrix_based_confirmation()` method
- [ ] Add `async_step_matrix_confirm()` handler
- [ ] Test config flow matrix integration
- [ ] Test matrix-based confirmation display

### Testing and Validation
- [ ] Test matrix state persistence across sessions
- [ ] Test matrix-driven entity creation/removal
- [ ] Test config flow matrix integration
- [ ] Test startup matrix restoration
- [ ] Run full test suite and validate
```

## 📊 Success Metrics

### Matrix State Persistence
- ✅ Matrix state saved in config entry: `device_feature_matrix` key exists
- ✅ Matrix state restored on startup: Log shows restored devices
- ✅ Matrix survives config flow: State consistent across sessions

### Matrix-Driven Entity Operations
- ✅ Entity creation based on combinations: `get_entities_to_create()` uses matrix
- ✅ Entity removal based on combinations: `get_entities_to_remove()` uses matrix
- ✅ No orphaned entities: All entities match matrix combinations

### Config Flow Integration
- ✅ Feature selection updates matrix: Matrix changes after device selection
- ✅ Matrix changes trigger entity ops: Confirmation shows entity changes
- ✅ Matrix-based confirmation: Shows correct entity lists

## 🎯 Implementation Strategy

**Add Code at End of Files:**
- All new methods appended at EOF to avoid line shifting
- Clear method signatures for easy identification
- Comprehensive implementation checklist

**Testing Approach:**
- Test matrix persistence by checking config entry data
- Test entity operations by verifying entity lists match matrix
- Test config flow by checking confirmation content

**Validation:**
- Run existing test suite: `python3 -m pytest tests/`
- Run specific tests: `python3 tests/test_phase4_integration.py`
- Manual testing of config flow matrix operations

This improved plan provides clear, actionable steps with better organization and testing focus.
