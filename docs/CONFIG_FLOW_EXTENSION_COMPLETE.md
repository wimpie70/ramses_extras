# Ramses Extras Config Flow Extension - Complete Final Plan

## Updated Requirements with All Considerations

### Key Updates Based on Feedback

1. **Complete DeviceFeatureMatrix** with all requested methods:
   - `get_enabled_devices_for_feature(feature_id)`
   - `enable_device_for_feature(feature_id, device_id)`
   - `is_device_enabled_for_feature(feature_id, device_id)` ← NEW: For entity checking
   - Plus all standard methods

2. **Additional considerations**:
   - **Translations**: May need to add translations for UI texts
   - **ramses_cc reference**: Check how they created menus in config flow
   - **Entity registry**: Review architecture.md for entity registry work
   - **Phase 3 complexity**: Entity management may have hidden complexities

3. **Simplified approach**:
   - No backward compatibility needed
   - No caching needed
   - Frequent commits after each phase
   - Focused testing on core functionality

## 1. Complete DeviceFeatureMatrix

```python
class DeviceFeatureMatrix:
    """Track which features are enabled for which devices."""

    def __init__(self):
        self.matrix = {}  # {device_id: {feature_id: enabled}}

    def enable_feature_for_device(self, device_id, feature_id):
        """Enable a feature for a specific device."""
        if device_id not in self.matrix:
            self.matrix[device_id] = {}
        self.matrix[device_id][feature_id] = True

    def enable_device_for_feature(self, feature_id, device_id):
        """Enable a device for a specific feature (convenience method)."""
        self.enable_feature_for_device(device_id, feature_id)

    def get_enabled_features_for_device(self, device_id):
        """Get all enabled features for a device."""
        return self.matrix.get(device_id, {})

    def get_enabled_devices_for_feature(self, feature_id):
        """Get all devices that have this feature enabled."""
        devices = []
        for device_id, features in self.matrix.items():
            if feature_id in features and features[feature_id]:
                devices.append(device_id)
        return devices

    def is_feature_enabled_for_device(self, feature_id, device_id):
        """Check if feature is enabled for specific device."""
        return self.matrix.get(device_id, {}).get(feature_id, False)

    def is_device_enabled_for_feature(self, device_id, feature_id):
        """Check if device is enabled for specific feature (readable alias)."""
        return self.is_feature_enabled_for_device(feature_id, device_id)

    def get_all_enabled_combinations(self):
        """Get all enabled feature/device combinations."""
        combinations = []
        for device_id, features in self.matrix.items():
            for feature_id, enabled in features.items():
                if enabled:
                    combinations.append((device_id, feature_id))
        return combinations
```

## 2. Implementation Plan with Considerations

### Phase 1: Foundation (1-2 days)

**Goal**: Basic device filtering and config flow structure

**Tasks**:
```bash
# Day 1: Device filtering implementation
- Update AVAILABLE_FEATURES with device filtering fields
- Implement DeviceFilter class with slug filtering
- Create basic device discovery utilities
- Update EntityManager with device filtering support
- Write tests for device filtering
```

**Considerations**:
- **Check ramses_cc config flow**: Look at how they created menus
- **Review translations**: May need to add translation support

**Files**:
- `const.py` - Add device filtering fields
- `framework/helpers/device/filter.py` - Device filtering logic
- `framework/helpers/entity/manager.py` - Basic device filtering

**Testing**:
```bash
cd /home/willem/dev/ramses_extras && bash -c "source ~/venvs/extras/bin/activate && pre-commit run -a"
```

**Commit**:
```bash
git add const.py framework/helpers/device/filter.py framework/helpers/entity/manager.py
git commit -m "feat(config): Add device filtering foundation"
```

### Phase 2: Config Flow Extension (2-3 days)

**Goal**: Flat menu structure with feature configurations

**Tasks**:
```bash
# Day 2: Basic config flow extension
- Extend config flow with feature-specific step handlers
- Implement flat menu structure with dynamic feature configs
- Create basic device selection UI components
- Write tests for config flow navigation
```

```bash
# Day 3: Complete config flow
- Implement individual feature configuration steps
- Add device selection for each feature
- Update EntityManager with per-device tracking
- Write integration tests
```

**Considerations**:
- **Translations**: Add translation support for UI texts
- **ramses_cc reference**: Study their menu implementation patterns
- **UI validation**: Ensure texts are visible with translations

**Files**:
- `config_flow.py` - Flat menu and feature config handlers
- `framework/helpers/config_flow.py` - Config flow utilities
- `translations/` - Translation files (if needed)

**Testing**:
```bash
cd /home/willem/dev/ramses_extras && bash -c "source ~/venvs/extras/bin/activate && pre-commit run -a"
```

**Commits**:
```bash
git add config_flow.py framework/helpers/config_flow.py
git commit -m "feat(config): Implement flat menu structure"

git add tests/config_flow/
git commit -m "test: Add config flow navigation tests"
```

### Phase 3: Entity Management (1-2 days) ⚠️ COMPLEX

**Goal**: Per-device feature tracking and entity lifecycle

**Tasks**:
```bash
# Day 4: Per-device tracking
- Implement DeviceFeatureMatrix class with all methods
- Update entity creation/removal logic for per-device control
- Enhance EntityManager with per-device tracking
- Write tests for device/feature matrix
```

```bash
# Day 5: Entity lifecycle (may take longer)
- Review architecture.md for entity registry patterns
- Create migration path for testing (no backward compatibility needed)
- Add entity dependency management
- Write comprehensive entity management tests
```

**Considerations**:
- **Entity registry complexity**: Review architecture.md thoroughly
- **Hidden complexities**: Entity management may have unexpected details
- **Testing focus**: Comprehensive testing for entity lifecycle

**Files**:
- `framework/helpers/entity/device_mapping.py` - Device/feature matrix
- `framework/helpers/entity/manager.py` - Enhanced entity lifecycle
- `RAMSES_EXTRAS_ARCHITECTURE.md` - Review for entity patterns

**Testing**:
```bash
cd /home/willem/dev/ramses_extras && bash -c "source ~/venvs/extras/bin/activate && pre-commit run -a"
```

**Commits**:
```bash
git add framework/helpers/entity/device_mapping.py
git commit -m "feat(entity): Add DeviceFeatureMatrix with all methods"

git add framework/helpers/entity/manager.py
git commit -m "feat(entity): Enhance entity lifecycle with per-device tracking"

git add tests/helpers/test_device_feature_mapping.py
git commit -m "test: Add DeviceFeatureMatrix tests"
```

### Phase 4: Integration (1 day)

**Goal**: Full system integration and final testing

**Tasks**:
```bash
# Day 6: Final integration
- Integrate all components
- End-to-end testing
- Performance optimization (basic)
- Documentation updates
- Final validation
```

**Considerations**:
- **Translation validation**: Ensure all UI texts are properly translated
- **ramses_cc patterns**: Verify we're following their best practices
- **Entity registry**: Double-check entity patterns from architecture.md

**Files**:
- All modified files
- `RAMSES_EXTRAS_ARCHITECTURE.md` - Update documentation
- `translations/` - Final translation updates

**Testing**:
```bash
cd /home/willem/dev/ramses_extras && bash -c "source ~/venvs/extras/bin/activate && pre-commit run -a"
```

**Commits**:
```bash
git add .
git commit -m "feat: Complete config flow extension integration"

git add docs/
git commit -m "docs: Update architecture documentation"
```

## 3. Important Considerations

### Translations

```python
# Translation considerations
TRANSLATION_DOMAIN = "ramses_extras"

# Example translation structure
translations = {
    "en": {
        "config_flow": {
            "enable_features": "Enable Features",
            "device_selection": "Select Devices for {feature}",
            "apply_changes": "Apply Changes"
        }
    },
    "nl": {
        "config_flow": {
            "enable_features": "Functies Inschakelen",
            "device_selection": "Selecteer Apparaten voor {feature}",
            "apply_changes": "Wijzigingen Toepassen"
        }
    }
}
```

### ramses_cc Reference

**Key areas to check**:
- How they structure config flow menus
- Their pattern for dynamic menu options
- Translation handling in config flow
- Error handling approaches

```bash
# Reference command
grep -r "async_show_menu" ramses_cc/custom_components/ramses_cc/config_flow.py
grep -r "translation" ramses_cc/custom_components/ramses_cc/
```

### Entity Registry Considerations

**From architecture.md review**:
- Entity registry patterns
- Entity lifecycle management
- Entity creation/removal strategies
- Performance considerations

```bash
# Review commands
grep -A 10 -B 5 "entity.*registry" ramses_extras/docs/RAMSES_EXTRAS_ARCHITECTURE.md
grep -A 10 -B 5 "lifecycle" ramses_extras/docs/RAMSES_EXTRAS_ARCHITECTURE.md
```

## 4. Phase 3 Complexity Warning

### Potential Hidden Complexities

1. **Entity Dependencies**: Features may have complex entity dependencies
2. **Lifecycle Management**: Entity creation/removal timing
3. **Performance**: Many devices × many features combinations
4. **Error Recovery**: Handling partial failures gracefully
5. **State Management**: Tracking complex feature/device states

### Mitigation Strategies

1. **Thorough architecture review**: Study existing patterns
2. **Incremental implementation**: Build step by step
3. **Comprehensive testing**: Test edge cases thoroughly
4. **Performance monitoring**: Watch for bottlenecks
5. **Error handling**: Robust recovery mechanisms

## 5. Simplified Commit Strategy

### Commit Structure

```bash
# After each phase (not 30 files at once)
git add <phase_files>
git commit -m "feat(<component>): <phase_description>"

# Run pre-commit after each commit
cd /home/willem/dev/ramses_extras && bash -c "source ~/venvs/extras/bin/activate && pre-commit run -a"
```

### Example Commit Sequence

```bash
# Phase 1: Foundation
git add const.py framework/helpers/device/filter.py
git commit -m "feat(config): Add device filtering foundation"
pre-commit run -a  # Passes

# Phase 2: Config Flow
git add config_flow.py framework/helpers/config_flow.py
git commit -m "feat(config): Implement flat menu structure"
pre-commit run -a  # Passes

# Phase 3: Entity Management (may need multiple commits)
git add framework/helpers/entity/device_mapping.py
git commit -m "feat(entity): Add DeviceFeatureMatrix with all methods"
pre-commit run -a  # Passes

git add framework/helpers/entity/manager.py
git commit -m "feat(entity): Enhance entity lifecycle with per-device tracking"
pre-commit run -a  # Passes

# Phase 4: Integration
git add .
git commit -m "feat: Complete config flow extension integration"
pre-commit run -a  # Passes
```

## 6. Summary of Changes

### What's Updated

1. **Complete DeviceFeatureMatrix** with all requested methods including `is_device_enabled_for_feature`
2. **Added considerations** - Translations, ramses_cc reference, entity complexity
3. **Simplified approach** - No backward compatibility, no caching
4. **Frequent commits** - After each phase, not 30 files at once
5. **Focused testing** - Core functionality validation

### What's Maintained

1. **Flat menu structure** - Feature configs in main menu
2. **Device filtering** - Features specify allowed slugs
3. **Per-device enablement** - Users enable features for specific devices
4. **Comprehensive testing** - Good coverage with simplified approach
5. **Clear implementation** - 4-phase roadmap with frequent commits

This final plan includes all requested functionality with the helpful `is_device_enabled_for_feature` method for entity checking, plus proper consideration of translations, ramses_cc patterns, entity complexity, and simplified implementation approach.
