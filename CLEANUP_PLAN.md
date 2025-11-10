# Ramses Extras Legacy Files Cleanup Plan

## Overview

This plan provides a safe, staged approach to removing obsolete files and directories from the legacy mixed helper/manager structure, leaving only the clean feature-centric architecture.

## Safety First Approach

- **Each stage is independently testable and commit-able**
- **Full backup before starting**
- **Rollback plan for each stage**
- **Test validation after each stage**

---

## 🗂️ Stage 1: Backup and Document Current State

### Actions

1. Create full backup of current codebase
2. Document current file structure
3. Create archive of legacy directories for reference

### Files to Create

- `backup/legacy_structure_[timestamp].tar.gz` - Full backup
- `docs/LEGACY_FILES_AUDIT.md` - Complete audit of files being removed
- `CLEANUP_PROGRESS.md` - Stage tracking document

### Testing

- [ ] Verify backup integrity
- [ ] Confirm all files are backed up
- [ ] Document current state with tree structure

### Commit Message

```
Stage 1: Backup and document current state

- Create full codebase backup
- Document legacy files audit
- Create stage tracking infrastructure
```

### Rollback

- Restore from backup if any issues

---

## 🗂️ Stage 2: Remove Duplicate Framework Features Directory

### Actions

1. Remove `framework/features/` directory (contains duplicate implementations)
2. Verify main `features/` directory remains intact
3. Test that new architecture still works

### Files to Remove

```
framework/features/
├── __init__.py
├── fan_control.py
├── humidity_control.py
├── sensor_management.py
└── websocket_handler.py
```

### Testing

- [ ] New humidity control feature still works
- [ ] Framework imports still function
- [ ] No import errors in codebase
- [ ] Run humidity automation tests

### Commit Message

```
Stage 2: Remove duplicate framework/features directory

- Remove framework/features/ (5 files)
- Verify new features/ directory intact
- Test humidity control functionality
```

### Rollback

- Restore framework/features/ directory from backup

---

## 🗂️ Stage 3: Remove Legacy Automations Directory

### Actions

1. Remove `automations/` directory
2. Verify humidity automation still works from new location
3. Test automation functionality

### Files to Remove

```
automations/
├── humidity_automation.py (605 lines - now in features/humidity_control/automation.py)
├── humidity_automation_design.md
├── humidity_automation_template.yaml
├── humidity_decision_flow.md
└── README.md
```

### Testing

- [ ] Humidity automation still functional
- [ ] No import errors for humidity features
- [ ] Test humidity automation manually
- [ ] Run humidity-related tests

### Commit Message

```
Stage 3: Remove legacy automations directory

- Remove automations/ directory (5 files)
- Humidity automation now in features/humidity_control/
- Test automation functionality
```

### Rollback

- Restore automations/ directory from backup

---

## 🗂️ Stage 4: Remove Legacy Services Directory

### Actions

1. Remove `services/` directory
2. Verify fan services still work from new location
3. Test service functionality

### Files to Remove

```
services/
├── fan_services.py (190 lines - now in features/humidity_control/services.py)
└── dehumidify_services.py (47 lines - now in features/humidity_control/services.py)
```

### Testing

- [ ] Fan control services still work
- [ ] Humidity control services functional
- [ ] Test fan speed mode changes
- [ ] Test dehumidify services

### Commit Message

```
Stage 4: Remove legacy services directory

- Remove services/ directory (2 files)
- Services now in features/humidity_control/
- Test service functionality
```

### Rollback

- Restore services/ directory from backup

---

## 🗂️ Stage 5: Remove Legacy Helpers Directory

### Actions

1. Remove `helpers/` directory
2. Verify framework helpers still work
3. Test entity and device helper functionality

### Files to Remove

```
helpers/
├── automation.py (560 lines - now in framework/helpers/automation/)
├── broker162 lines - now in services/broker_service.py)
├── device.py (162 lines - now in framework/helpers/device/)
├── entities.py (obsolete - functionality moved)
├── entity.py (354 lines - now in framework/helpers/entity/)
├── platform.py (obsolete - consolidated to platform/)
└── automation/
    ├── __init__.py
    └── base.py (moved to framework/helpers/automation/)
```

### Testing

- [ ] Entity helpers function correctly
- [ ] Device helpers work properly
- [ ] Entity parsing and generation works
- [ ] No import errors in framework
- [ ] Run helper-related tests

### Commit Message

```
Stage 5: Remove legacy helpers directory

- Remove helpers/ directory (7+ files)
- Functionality moved to framework/helpers/ and services/
- Test helper functionality
```

### Rollback

- Restore helpers/ directory from backup

---

## 🗂️ Stage 6: Remove Legacy Managers Directory

### Actions

1. Remove `managers/` directory
2. Verify framework managers still work
3. Test feature management functionality

### Files to Remove

```
managers/
├── automation_manager.py (307 lines - now in framework/managers/)
├── card_manager.py (obsolete - moved to services/)
├── device_monitor.py (143 lines - now in framework/managers/)
├── entity_manager.py (obsolete - now in framework/managers/)
└── platform_reloader.py (obsolete - consolidated to platform/)
```

### Testing

- [ ] Feature management works
- [ ] Device monitoring functional
- [ ] Entity management works
- [ ] No import errors in managers
- [ ] Run manager-related tests

### Commit Message

```
Stage 6: Remove legacy managers directory

- Remove managers/ directory (5 files)
- Functionality moved to framework/managers/ and services/
- Test management functionality
```

### Rollback

- Restore managers/ directory from backup

---

## 🗂️ Stage 7: Remove Legacy Platform Files

### Actions

1. Remove legacy platform files from root
2. Verify platform consolidation works
3. Test platform functionality

### Files to Remove

```
custom_components/ramses_extras/
├── binary_sensor.py (moved to platform/)
├── number.py (moved to platform/)
├── sensor.py (moved to platform/)
└── switch.py (moved to platform/)
```

### Testing

- [ ] Platform entities still work
- [ ] Sensor functionality intact
- [ ] Switch functionality intact
- [ ] Binary sensor functionality intact
- [ ] Number entity functionality intact
- [ ] Run platform tests

### Commit Message

```
Stage 7: Remove legacy platform files

- Remove 4 platform files from root
- Files now consolidated in platform/ directory
- Test platform functionality
```

### Rollback

- Restore platform files from backup

---

## 🗂️ Stage 8: Remove Legacy WebSocket API File

### Actions

1. Remove `websocket_api.py`
2. Verify WebSocket functionality in new location
3. Test WebSocket features

### Files to Remove

```
websocket_api.py (handled by features/websocket_handler/)
```

### Testing

- [ ] WebSocket functionality works
- [ ] Real-time updates work
- [ ] No WebSocket import errors
- [ ] Test WebSocket handler

### Commit Message

```
Stage 8: Remove legacy WebSocket API file

- Remove websocket_api.py
- WebSocket now handled by features/websocket_handler/
- Test WebSocket functionality
```

### Rollback

- Restore websocket_api.py from backup

---

## 🗂️ Stage 9: Final Validation and Testing

### Actions

1. Run comprehensive test suite
2. Verify all functionality works
3. Check for any remaining import errors
4. Performance validation

### Testing Checklist

- [ ] All humidity control tests pass
- [ ] All framework tests pass
- [ ] All service tests pass
- [ ] All manager tests pass
- [ ] All entity tests pass
- [ ] All platform tests pass
- [ ] No import errors
- [ ] Documentation accurate
- [ ] Performance maintained

### Commit Message

```
Stage 9: Final validation and testing

- Comprehensive test suite validation
- Performance verification
- Documentation updates
- Cleanup validation complete
```

### Rollback

- Restore from previous stage backup if needed

---

## 🗂️ Stage 10: Cleanup Complete - Archive Documentation

### Actions

1. Create final archive of legacy structure
2. Update documentation to reflect new clean structure
3. Create migration summary
4. Mark cleanup as complete

### Files to Create

- `docs/CLEANUP_SUMMARY.md` - Final summary
- `docs/ARCHITECTURE_FINAL.md` - New clean architecture documentation
- `backup/legacy_removed_[timestamp].tar.gz` - Final archive

### Commit Message

```
Stage 10: Cleanup complete - Archive documentation

- Final cleanup validation
- Archive legacy structure
- Update final documentation
- Mark cleanup complete
```

### Rollback

- Full restore from initial backup if needed

---

## 🚨 Risk Mitigation

### Before Each Stage

1. **Create stage-specific backup**
2. **Run existing tests to establish baseline**
3. **Document current state**

### After Each Stage

1. **Run affected tests**
2. **Verify functionality**
3. **Check for import errors**
4. **Test critical user flows**

### Rollback Strategy

1. **Immediate rollback from stage backup**
2. **Restore from initial backup if needed**
3. **Re-run tests to verify rollback**
4. **Document rollback reason**

---

## 📊 Success Metrics

- ✅ All tests pass after each stage
- ✅ No functionality regression
- ✅ No import errors
- ✅ Clean file structure
- ✅ Documentation accuracy
- ✅ Performance maintained

---

## 🏁 Final Result

After completing all 10 stages:

- **Clean feature-centric architecture only**
- **Legacy mixed structure completely removed**
- **Full functionality preserved**
- **Better maintainability achieved**
- **Clear separation of concerns**

This staged approach ensures safe, testable progress with full rollback capability at each step.
