# Files No Longer Needed with New Feature-Centric Architecture

## Overview

With the new feature-centric architecture in place, the following files are obsolete and can be safely removed:

## 🔴 Legacy Helper Files (Consolidated into Framework)

- ❌ `helpers/entity.py` → Replaced by `framework/helpers/entity/core.py`
- ❌ `helpers/entities.py` → Replaced by `framework/helpers/entity/state.py`
- ❌ `helpers/device.py` → Replaced by `framework/helpers/device/core.py`
- ❌ `helpers/automation.py` → Replaced by `framework/helpers/automation/core.py`
- ❌ `helpers/broker.py` → Replaced by `services/broker_service.py`
- ❌ `helpers/platform.py` → Replaced by platform consolidation

## 🔴 Legacy Manager Files (Consolidated into Framework)

- ❌ `managers/automation_manager.py` → Replaced by `framework/managers/automation_service.py`
- ❌ `managers/card_manager.py` → Replaced by `services/notification_service.py`
- ❌ `managers/device_monitor.py` → Replaced by `framework/managers/device_manager.py`
- ❌ `managers/entity_manager.py` → Replaced by `framework/managers/entity_manager.py`
- ❌ `managers/platform_reloader.py` → Replaced by platform consolidation

## 🔴 Legacy Service Files (Migrated to Features)

- ❌ `services/fan_services.py` → Replaced by `features/fan_control/services.py`
- ❌ `services/dehumidify_services.py` → Replaced by `features/humidity_control/services.py`

## 🔴 Legacy Platform Files (Consolidated)

- ❌ `binary_sensor.py` → Consolidated into `platform/binary_sensor.py`
- ❌ `number.py` → Consolidated into `platform/number.py`
- ❌ `sensor.py` → Consolidated into `platform/sensor.py`
- ❌ `switch.py` → Consolidated into `platform/switch.py`

## 🔴 Legacy Automation Files (Migrated to Features)

- ❌ `automations/humidity_automation.py` → Replaced by `features/humidity_control/automation.py`
- ❌ `automations/humidity_automation_design.md` → Design documentation no longer needed
- ❌ `automations/humidity_decision_flow.md` → No longer needed
- ❌ `automations/humidity_control_template.yaml` → No longer needed
- ❌ `automations/README.md` → No longer needed

## 🔴 Other Legacy Files

- ❌ `websocket_api.py` → Replaced by `features/websocket_handler/`
- ❌ Various unused automation template files

## 🟡 Files to Review (Possibly Redundant)

- `translations/en.json` → Check if feature-specific translations are sufficient
- `translations/nl.json` → Check if feature-specific translations are sufficient
- `py.typed` → Check if this is still relevant for the new structure
- `manifest.json` → Verify if redundant with HA requirements

## ✅ Files to Keep

- ✅ All `framework/` files (foundation layer)
- ✅ All `features/` files (feature implementations)
- ✅ All `services/` files (cross-feature services)
- ✅ Core integration files (`__init__.py`, `config_flow.py`, `const.py`)
- ✅ Platform files (HA integration layer)
- ✅ Frontend assets (`www/` directory)

## 📊 Impact Summary

- **Remove**: ~15-20 obsolete files
- **Keep**: 50+ organized framework and feature files
- **Net Result**: Significantly cleaner, more maintainable codebase

## ⚠️ Note on base.py

The `framework/helpers/automation/base.py` file has circular import issues that need to be resolved before removal of the old automation files. The imports are currently:

- `from ....const import AVAILABLE_FEATURES`
- `from ....helpers.entity import EntityHelpers, get_feature_entity_mappings`

This needs to be fixed using proper relative imports for the new structure.

## Next Steps

1. Fix circular import issues in `framework/helpers/automation/base.py`
2. Remove obsolete legacy files
3. Update any remaining references to removed files
4. Run comprehensive tests to ensure nothing is broken
