# JavaScript Feature Reorganization Plan

**Date**: 2025-11-22
**Status**: Approved - Ready for Implementation
**Scope**: HVAC Fan Card JavaScript files reorganization

## Overview

This document clarifies the distinction between the **integration structure** (development repo organization) and the **deployment structure** (how files are copied to Home Assistant config/www when features are enabled).

## Architecture Context

**Reference Documents:**

- `docs/RAMSES_EXTRAS_ARCHITECTURE.md` - Feature-centric architecture principles
- `.kilocode/rules/kilo rules.txt` - Development guidelines

**Key Clarification:** The integration structure (development files) remains unchanged. Only the deployment structure (what gets copied to hass/config/www) is being reorganized.

## Integration Structure (Current - Updated)

```
ramses_extras/custom_components/ramses_extras/
├── features/
│   ├── hvac_fan_card/
│   │   ├── __init__.py
│   │   ├── const.py
│   │   └── www/                   # Feature-specific web assets
│   │       └── hvac_fan_card/
│   │           ├── hvac-fan-card.js
│   │           ├── hvac-fan-card-editor.js
│   │           ├── airflow-diagrams.js
│   │           ├── card-styles.js
│   │           ├── message-handlers.js
│   │           ├── templates/
│   │           └── translations/
│   └── [other_features]/
├── framework/                      # Framework foundation
│   ├── helpers/                   # Python helpers
│   │   ├── [python_helpers]/
│   │   └── paths.py
│   └── www/                       # JavaScript framework utilities
│       ├── paths.js               # Environment-aware path constants
│       ├── card-commands.js
│       ├── card-services.js
│       ├── card-translations.js
│       ├── card-validation.js
│       └── ramses-message-broker.js
└── translations/                   # Integration-level translations
    ├── en.json
    └── nl.json
```

**Note:** This structure remains unchanged - it's how we organize our development files.

## Current Deployment Structure (Before Changes)

When features are enabled, files are copied to:

```
hass/config/www/community/ramses_extras/
├── helpers/                       # Current: mixed structure
│   ├── paths.js
│   ├── card-commands.js
│   └── [other_helpers]/
└── hvac_fan_card/                 # Current: copied from features/hvac_fan_card/www/hvac_fan_card/
    ├── hvac-fan-card.js
    ├── hvac-fan-card-editor.js
    └── [other_files]/
```

**Problem:** Mixed structure - helpers and features are at the same level.

## Target Deployment Structure (After Changes)

When features are enabled, files should be copied to:

```
hass/config/www/ramses_extras/
├── helpers/                       # Shared utilities (copied from framework/www/)
│   ├── paths.js
│   ├── card-commands.js
│   ├── card-services.js
│   ├── card-translations.js
│   ├── card-validation.js
│   └── ramses-message-broker.js
└── features/                      # Feature-specific cards (copied from features/*/www/*/)
    └── hvac_fan_card/             # Each feature gets its own folder
        ├── hvac-fan-card.js
        ├── hvac-fan-card-editor.js
        ├── airflow-diagrams.js
        ├── card-styles.js
        ├── message-handlers.js
        ├── templates/
        └── translations/
```

**Benefits:**

- Clear separation between helpers and features
- Each feature gets its own folder within features/
- Consistent structure for multiple features
- Easier URL management: `/local/ramses_extras/features/hvac_fan_card/hvac-fan-card.js`

## Implementation Steps

### Step 1: Update Deployment Logic

**Files to modify:**

- `__init__.py` - Main deployment logic (around line 428)
- `features/hvac_fan_card/__init__.py` - Card path discovery
- `features/hvac_fan_card/const.py` - Feature constants

**Current deployment logic:**

```python
# OLD: Mixed structure
for feature_id, card_info in cards.items():
    source_path = INTEGRATION_DIR / "features" / feature_id / "www" / feature_id
    destination_path = HASS_CONFIG_DIR / "www" / "community" / "ramses_extras" / feature_id
```

**Updated deployment logic:**

```python
# NEW: Clean structure
# 1. Copy helpers from framework/www (when any card is enabled)
if any_card_enabled:
    helpers_source = INTEGRATION_DIR / "framework" / "www"
    helpers_dest = HASS_CONFIG_DIR / "www" / "ramses_extras" / "helpers"
    await asyncio.to_thread(shutil.copytree, helpers_source, helpers_dest)

# 2. Copy feature cards to features/ directory
for feature_id, card_info in cards.items():
    feature_card_path = INTEGRATION_DIR / "features" / feature_id / "www" / feature_id
    destination_path = HASS_CONFIG_DIR / "www" / "ramses_extras" / "features" / feature_id

    # Create features directory if it doesn't exist
    destination_path.parent.mkdir(parents=True, exist_ok=True)

    await asyncio.to_thread(shutil.copytree, feature_card_path, destination_path)
```

### Step 2: Update Path Constants

**Python paths (framework/helpers/paths.py):**

```python
# Deployment paths
WWW_BASE = "/local/ramses_extras"
HELPERS_BASE = f"{WWW_BASE}/helpers"
FEATURES_BASE = f"{WWW_BASE}/features"

# Feature-specific paths
def get_feature_path(feature_name):
    return f"{FEATURES_BASE}/{feature_name}"

def get_feature_file_path(feature_name, file_name):
    return f"{get_feature_path(feature_name)}/{file_name}"
```

**JavaScript paths (framework/www/paths.js):**

```javascript
export const PATHS = {
  WWW_BASE: '/local/ramses_extras',
  HELPERS_BASE: '/local/ramses_extras/helpers',
  FEATURES_BASE: '/local/ramses_extras/features',

  getFeaturePath(featureName) {
    return `${this.FEATURES_BASE}/${featureName}`;
  },

  getFeatureFilePath(featureName, fileName) {
    return `${this.getFeaturePath(featureName)}/${fileName}`;
  },
};
```

### Step 3: Update Feature Constants

**features/hvac_fan_card/const.py:**

```python
# Feature deployment configuration
FEATURE_CARD_CONFIG = {
    "hvac_fan_card": {
        "card_path": "features/hvac_fan_card",  # Updated path
        "main_js": "hvac-fan-card.js",
        "editor_js": "hvac-fan-card-editor.js",
        "templates_path": "templates/",
        "translations_path": "translations/",
    }
}
```

### Step 4: Update JavaScript Imports

**Card files should use:**

```javascript
import { PATHS } from '/local/ramses_extras/helpers/paths.js';

// Access feature files
const mainCardPath = PATHS.getFeatureFilePath('hvac_fan_card', 'hvac-fan-card.js');
const templatesPath = PATHS.getFeaturePath('hvac_fan_card') + '/templates/';
```

### Step 5: Update Home Assistant Card Configuration

**Card configuration in Lovelace:**

```yaml
type: custom:hvac-fan-card
hass_config: !include ../../../configuration.yaml
entity: climate.living_room
card_path: '/local/ramses_extras/features/hvac_fan_card/hvac-fan-card.js'
```

## Technical Decisions

### 1. Integration Structure Unchanged

**Decision:** Keep current development file organization
**Rationale:** No need to reorganize development files - only deployment structure needs improvement

### 2. Feature Folders in Deployment

**Decision:** Each feature gets its own folder in `features/`
**Rationale:** Maintains file organization, supports multiple files per feature, enables templates and translations

### 3. Consistent URL Structure

**Decision:** All feature URLs use `features/{feature_name}/` pattern
**Rationale:** Predictable, scalable, consistent with helpers structure

### 4. Path Management

**Decision:** Use shared path constants for both Python and JavaScript
**Rationale:** Centralized path management, prevents hardcoded paths, enables easy configuration

## Expected Benefits

1. **Clear Separation:** Helpers vs features have distinct locations
2. **Scalable Structure:** Easy to add new features without conflicts
3. **Predictable URLs:** Consistent pattern for all feature assets
4. **Maintainable:** Clear organization for development and deployment
5. **Template-Friendly:** Supports templates and translations per feature

## Testing Strategy

1. **Deployment Testing:** Verify files are copied to correct locations
2. **URL Accessibility:** Ensure all feature files are accessible via new URLs
3. **Card Functionality:** Verify cards load correctly from new paths
4. **Helper Access:** Confirm helpers work from new location
5. **Multiple Features:** Test with multiple enabled features

## Migration Strategy

### Phase 1: Path Updates

- Update deployment logic and path constants
- Test in development environment

### Phase 2: URL Updates

- Update card configurations to use new URLs
- Update JavaScript imports

### Phase 3: Validation

- Test deployment in container environment
- Verify all functionality works

### Phase 4: Cleanup

- Remove old deployment paths
- Update documentation references

## Rollback Plan

If issues arise:

1. **Git revert:** Simple rollback to previous deployment logic
2. **Configuration fallback:** Keep old paths as fallback options
3. **No data loss:** Only deployment path changes, no file changes

---

**Next Steps:** Ready for implementation - proceed with Step 1 (Update Deployment Logic)
