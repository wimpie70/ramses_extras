# Legacy Files Audit - Ramses Extras Cleanup

## Overview

This document provides a complete audit of all legacy files and directories that will be removed during the cleanup process. Each entry includes line counts, functionality, and migration destination.

---

## 📁 Directories to Remove

### 1. automations/ Directory (5 files, ~605+ lines)

**Status:** Legacy - functionality moved to features/humidity_control/

| File                                | Lines | Status | New Location                              |
| ----------------------------------- | ----- | ------ | ----------------------------------------- |
| `humidity_automation.py`            | 620   | MOVED  | `features/humidity_control/automation.py` |
| `humidity_automation_design.md`     | N/A   | REMOVE | Documentation only                        |
| `humidity_automation_template.yaml` | N/A   | REMOVE | No longer needed                          |
| `humidity_decision_flow.md`         | N/A   | REMOVE | Documentation only                        |
| `README.md`                         | N/A   | REMOVE | Documentation only                        |

**Total:** ~620 lines of code moved, 4 documentation files removed

---

### 2. services/ Directory (2 files, ~237 lines)

**Status:** Legacy - functionality moved to feature-specific services

| File                     | Lines | Status | New Location                            |
| ------------------------ | ----- | ------ | --------------------------------------- |
| `fan_services.py`        | 190   | MOVED  | `features/humidity_control/services.py` |
| `dehumidify_services.py` | 47    | MOVED  | `features/humidity_control/services.py` |

**Total:** ~237 lines of code consolidated

---

### 3. helpers/ Directory (7+ files, ~1076+ lines)

**Status:** Legacy - functionality consolidated to framework/helpers/ and services/

| File                     | Lines | Status | New Location                                       |
| ------------------------ | ----- | ------ | -------------------------------------------------- |
| `automation.py`          | 560   | MOVED  | `framework/helpers/automation/base.py`             |
| `broker.py`              | 162   | MOVED  | `services/broker_service.py`                       |
| `device.py`              | 162   | MOVED  | `framework/helpers/device/core.py`                 |
| `entities.py`            | N/A   | REMOVE | Functionality moved to `framework/helpers/entity/` |
| `entity.py`              | 354   | MOVED  | `framework/helpers/entity/core.py`                 |
| `platform.py`            | N/A   | REMOVE | Consolidated to platform/                          |
| `automation/__init__.py` | N/A   | REMOVE | Empty file                                         |
| `automation/base.py`     | N/A   | MOVED  | `framework/helpers/automation/base.py`             |

**Total:** ~1238+ lines of code consolidated, 3 files removed

---

### 4. managers/ Directory (5 files, ~450+ lines)

**Status:** Legacy - functionality consolidated to framework/managers/ and services/

| File                    | Lines | Status | New Location                               |
| ----------------------- | ----- | ------ | ------------------------------------------ |
| `automation_manager.py` | 307   | MOVED  | `framework/managers/automation_service.py` |
| `card_manager.py`       | N/A   | MOVED  | `services/notification_service.py`         |
| `device_monitor.py`     | 143   | MOVED  | `framework/managers/device_manager.py`     |
| `entity_manager.py`     | N/A   | MOVED  | `framework/managers/entity_manager.py`     |
| `platform_reloader.py`  | N/A   | REMOVE | Consolidated to platform/                  |

**Total:** ~450+ lines of code consolidated

---

### 5. framework/features/ Directory (5 files)

**Status:** DUPLICATE - real implementations in main features/ directory

| File                   | Status | Real Implementation           |
| ---------------------- | ------ | ----------------------------- |
| `__init__.py`          | REMOVE | `features/__init__.py`        |
| `fan_control.py`       | REMOVE | `features/fan_control/`       |
| `humidity_control.py`  | REMOVE | `features/humidity_control/`  |
| `sensor_management.py` | REMOVE | `features/sensor_management/` |
| `websocket_handler.py` | REMOVE | `features/websocket_handler/` |

**Total:** 5 duplicate files removed

---

## 📄 Individual Files to Remove

### Root Level Files

| File               | Status | Reason                                   |
| ------------------ | ------ | ---------------------------------------- |
| `websocket_api.py` | REMOVE | Handled by `features/websocket_handler/` |

### Platform Files (Legacy Location)

| File               | New Location                | Status       |
| ------------------ | --------------------------- | ------------ |
| `binary_sensor.py` | `platform/binary_sensor.py` | CONSOLIDATED |
| `number.py`        | `platform/number.py`        | CONSOLIDATED |
| `sensor.py`        | `platform/sensor.py`        | CONSOLIDATED |
| `switch.py`        | `platform/switch.py`        | CONSOLIDATED |

---

## 📊 Summary Statistics

### Files to Remove

- **Directories:** 4 (`automations/`, `services/`, `helpers/`, `managers/`, `framework/features/`)
- **Individual Files:** 10+ (`websocket_api.py`, 4 platform files, etc.)
- **Total Files:** 25+ files and directories

### Code to Consolidate

- **Lines of Code Moved:** ~2,500+ lines
- **New Architecture Lines:** ~2,800+ lines (already implemented)

### Files to Keep

- **New Feature-Centric Architecture:** `features/`, `framework/`, `services/`, `platform/`
- **HA Required Files:** `manifest.json`, `__init__.py`, `config_flow.py`, `const.py`
- **Web Assets:** `www/`
- **Scripts:** `scripts/`
- **Documentation:** `.md` files about new architecture

---

## 🔄 Migration Verification

### Key Migrations to Verify

1. **Humidity Automation:** `automations/humidity_automation.py` → `features/humidity_control/automation.py`
2. **Fan Services:** `services/fan_services.py` → `features/humidity_control/services.py`
3. **Dehumidify Services:** `services/dehumidify_services.py` → `features/humidity_control/services.py`
4. **Entity Helpers:** `helpers/entity.py` → `framework/helpers/entity/core.py`
5. **Device Helpers:** `helpers/device.py` → `framework/helpers/device/core.py`
6. **Automation Base:** `helpers/automation.py` → `framework/helpers/automation/base.py`
7. **Broker Service:** `helpers/broker.py` → `services/broker_service.py`
8. **Device Monitor:** `managers/device_monitor.py` → `framework/managers/device_manager.py`
9. **Automation Manager:** `managers/automation_manager.py` → `framework/managers/automation_service.py`

### Testing Points

- [ ] All imports work from new locations
- [ ] Humidity automation functions correctly
- [ ] Fan control services work
- [ ] Entity parsing and generation works
- [ ] Device management functions
- [ ] Framework manager functionality
- [ ] WebSocket features work
- [ ] Platform entities function

---

## 🚨 Critical Dependencies

### Files with Complex Dependencies

1. **humidity_automation.py** - Used by multiple components
2. **fan_services.py** - Referenced by humidity automation
3. **entity.py** - Base class for multiple entities
4. **automation.py** - Base class for automations

### Import Chains to Verify

```python
# Old imports (to be removed)
from ..helpers.entity import EntityHelpers
from ..helpers.automation import ExtrasBaseAutomation
from ..managers.automation_manager import AutomationManager
from ..services.fan_services import async_set_fan_speed_mode

# New imports (to be used)
from ....framework.helpers.entity import EntityHelpers
from ....framework.helpers.automation import ExtrasBaseAutomation
from ....framework.managers import AutomationManager
from ...humidity_control.services import async_set_fan_speed_mode
```

---

## 📝 Cleanup Notes

### Files with Historical Value

- `humidity_decision_flow.md` - Keep in backup, document logic elsewhere
- `humidity_automation_design.md` - Keep in backup, integrate into new docs
- Various README files - Archive for reference

### Files Safe to Remove Immediately

- Empty `__init__.py` files
- Duplicate implementation files
- Legacy template files
- Development/debug files

### Risk Assessment

- **Low Risk:** Removing duplicate framework/features/, documentation files
- **Medium Risk:** Removing helpers/, services/ (verify functionality)
- **High Risk:** Removing managers/ (verify all functionality moved)

---

## ✅ Pre-Cleanup Checklist

- [ ] Full backup created
- [ ] Current functionality tested and documented
- [ ] All new architecture implementations verified
- [ ] Import chains mapped and tested
- [ ] Test suite ready for validation
- [ ] Rollback plan prepared
- [ ] Documentation updated

---

**Generated:** 2025-11-10T10:43:46Z
**Backup Location:** /home/willem/backup/ramses*extras_legacy*[timestamp].tar.gz
**Next Action:** Begin Stage 2 - Remove Duplicate Framework Features Directory
