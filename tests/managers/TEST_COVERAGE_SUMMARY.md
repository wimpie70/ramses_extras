# Entity Management Test Coverage Summary

## Overview

Comprehensive test suite for the EntityManager and feature registry system, covering all aspects of entity lifecycle management during feature enable/disable operations.

## Test Statistics

- **Total Tests**: 80 passing
- **Skipped Tests**: 5 (humidity automation specific tests)
- **Test Files**: 5
- **Coverage Areas**: 6 major categories

## Test Files

### 1. `test_startup_flow.py` (12 tests)

Tests the startup flow with EntityManager post-creation validation.

**Key Areas:**

- ✅ Startup flow completion
- ✅ EntityManager validation after startup
- ✅ Discrepancy detection and fixing
- ✅ Graceful failure handling
- ✅ Feature configuration validation
- ✅ Startup sequence ordering
- ✅ Separation of concerns (creation vs validation)

**Test Classes:**

- `TestStartupFlow` (10 tests)
- `TestStartupEntityCreationVsValidation` (2 tests)

### 2. `test_broker_retrieval.py` (11 tests)

Tests broker retrieval with backwards compatibility for different ramses_cc versions.

**Key Areas:**

- ✅ Method 1: `hass.data["ramses_cc"][entry.entry_id]` (newest)
- ✅ Method 2: `hass.data["ramses_cc"]` directly (older)
- ✅ Method 3: `entry.broker` (older versions)
- ✅ Method 4: `hass.data["ramses_cc"][DOMAIN]` (very old)
- ✅ Fallback order verification
- ✅ Error handling for missing brokers
- ✅ Exception handling

**Test Classes:**

- `TestBrokerRetrieval` (11 tests)

### 3. `test_entity_manager.py` (22 tests)

Core EntityManager functionality tests.

**Key Areas:**

- ✅ EntityInfo TypedDict structure
- ✅ EntityManager initialization
- ✅ Entity catalog building
- ✅ Feature target updates
- ✅ Existing entity retrieval
- ✅ Feature entity scanning (cards, automations, devices)
- ✅ Entity removal/creation lists
- ✅ Entity summary generation
- ✅ Entity change application
- ✅ Error handling
- ✅ Automation pattern matching
- ✅ Device discovery

**Test Classes:**

- `TestEntityManager` (19 tests)
- `TestEntityManagerIntegration` (3 tests)

### 4. `test_entity_manager_integration.py` (17 tests)

Integration tests for EntityManager in config flow context.

**Key Areas:**

- ✅ EntityManager creation on feature changes
- ✅ Config flow integration
- ✅ Confirmation step handling
- ✅ Entity change application in save_config
- ✅ Fallback when EntityManager unavailable
- ✅ Error handling in config flow
- ✅ State persistence across steps
- ✅ Entity summary in UI
- ✅ Backwards compatibility
- ✅ Broker retrieval methods (all 4 methods)

**Test Classes:**

- `TestEntityManagerIntegration` (9 tests)
- `TestConfigFlowBackwardsCompatibility` (8 tests)

### 5. `test_feature_registry.py` (15 tests) ⭐ NEW

Comprehensive feature registry and entity lifecycle tests.

**Key Areas:**

- ✅ Enable feature from scratch
- ✅ Disable feature with existing entities
- ✅ Keep enabled feature entities
- ✅ Multiple features enable/disable
- ✅ Catalog with all features disabled
- ✅ Catalog with all features enabled
- ✅ Default feature exclusion
- ✅ Entity state transitions (4 states)
- ✅ Entity summary reporting
- ✅ Cards and automations exclusion
- ✅ Feature conflict resolution
- ✅ Feature priority ordering

**Test Classes:**

- `TestFeatureEnableDisableWorkflow` (4 tests)
- `TestFeatureEntityCatalog` (3 tests)
- `TestEntityStateTransitions` (4 tests)
- `TestEntitySummaryReporting` (2 tests)
- `TestFeatureConflictResolution` (2 tests)

### 6. `test_humidity_automation.py` (3 tests + 2 skipped)

Humidity automation specific tests.

**Key Areas:**

- ✅ Entity validation
- ✅ Humidity decision logic
- ✅ Problem reproduction
- ⏭️ Entity name transformation (skipped)
- ⏭️ State mappings generation (skipped)

## Entity State Coverage

The test suite covers all 4 possible entity states:

1. **Exists + Should Exist** ✅
   - Entity exists and feature is enabled
   - Should be kept (not in remove or create lists)

2. **Exists + Should NOT Exist** ✅
   - Entity exists but feature is disabled
   - Should be removed (in remove list)

3. **Does NOT Exist + Should Exist** ✅
   - Entity doesn't exist but feature is enabled
   - Should be created (in create list)

4. **Does NOT Exist + Should NOT Exist** ✅
   - Entity doesn't exist and feature is disabled
   - No action needed (not in any list)

## Feature Workflow Coverage

### Enable Feature Workflow ✅

1. Feature starts disabled
2. No entities exist
3. User enables feature
4. EntityManager detects entities to create
5. Entities are created during platform setup
6. EntityManager validates creation

### Disable Feature Workflow ✅

1. Feature starts enabled
2. Entities exist
3. User disables feature
4. EntityManager detects entities to remove
5. Entities are removed
6. EntityManager validates removal

### Keep Feature Workflow ✅

1. Feature stays enabled
2. Entities exist
3. No changes needed
4. EntityManager confirms no action required

### Multiple Features Workflow ✅

1. Enable feature A, disable feature B
2. EntityManager handles both operations
3. Correct entities removed and created

## Broker Access Methods Coverage

All 4 broker access methods are tested for backwards compatibility:

1. **Method 1** (newest): `hass.data["ramses_cc"][entry.entry_id]` ✅
2. **Method 2** (older): `hass.data["ramses_cc"]` directly ✅
3. **Method 3** (older): `entry.broker` attribute ✅
4. **Method 4** (very old): `hass.data["ramses_cc"][DOMAIN]` ✅

## Error Handling Coverage

- ✅ Entity registry access failures
- ✅ Broker retrieval failures
- ✅ Device discovery failures
- ✅ Entity removal failures
- ✅ Automation pattern matching failures
- ✅ Config flow errors
- ✅ Startup validation failures (graceful degradation)

## Edge Cases Covered

- ✅ Empty entity registry
- ✅ No devices discovered
- ✅ No broker found
- ✅ All features disabled
- ✅ All features enabled
- ✅ Default feature exclusion from management
- ✅ Cards and automations exclusion from summaries
- ✅ Mixed entity states
- ✅ Feature priority conflicts

## Test Quality Metrics

- **Isolation**: Each test is independent with proper setup/teardown
- **Mocking**: Comprehensive mocking of Home Assistant APIs
- **Coverage**: All major code paths tested
- **Documentation**: Clear test names and docstrings
- **Assertions**: Specific, meaningful assertions
- **Error Cases**: Both success and failure paths tested

## Running Tests

```bash
# Run all entity management tests
cd ramses_extras
source ~/venvs/extras/bin/activate
python3 -m pytest tests/startup/ tests/managers/ -v

# Run specific test file
python3 -m pytest tests/managers/test_feature_registry.py -v

# Run with coverage
python3 -m pytest tests/startup/ tests/managers/ --cov=custom_components.ramses_extras.framework.helpers.entity --cov-report=html
```

## Future Test Additions

Potential areas for additional testing:

1. **Performance Tests**
   - Large entity catalogs (1000+ entities)
   - Multiple rapid feature toggles
   - Memory usage during catalog building

2. **Integration Tests**
   - Real Home Assistant instance tests
   - Actual device discovery
   - Real entity registry operations

3. **Stress Tests**
   - Concurrent feature changes
   - Race condition handling
   - Network failures during broker access

4. **UI Tests**
   - Config flow UI rendering
   - Confirmation dialog display
   - Error message presentation

## Conclusion

The entity management test suite provides comprehensive coverage of:

- ✅ All entity lifecycle states
- ✅ All feature enable/disable workflows
- ✅ All broker access methods
- ✅ Error handling and edge cases
- ✅ Backwards compatibility
- ✅ Integration with config flow
- ✅ Startup validation

**Total Coverage: 80 passing tests across 6 major categories**

This ensures the EntityManager system is robust, reliable, and maintainable.
