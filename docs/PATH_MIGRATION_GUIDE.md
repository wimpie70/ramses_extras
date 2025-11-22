# Path Migration Guide

**Date**: 2025-11-22
**Purpose**: Guide for migrating from ugly relative imports to environment-aware paths

## Quick Summary

Instead of using ugly relative imports like:

```javascript
import { FAN_COMMANDS } from '../../../../../www/helpers/card-commands.js';
```

Use the new environment-aware system:

```javascript
import { HELPER_PATHS, getHelperPath } from '../../../../../www/helpers/paths.js';
import { FAN_COMMANDS } from HELPER_PATHS.CARD_COMMANDS;
```

## Migration Examples

### Before (Current - ❌ Ugly)

```javascript
// hvac-fan-card.js - Lines 29-31, 41-46
import { SimpleCardTranslator } from '../../../../../www/helpers/card-translations.js';
import { FAN_COMMANDS } from '../../../../../www/helpers/card-commands.js';
import { getRamsesMessageBroker } from '../../../../../www/helpers/ramses-message-broker.js';

import {
  sendPacket,
  getBoundRemDevice,
  callService,
  entityExists,
  getEntityState,
  callWebSocket,
  setFanParameter,
} from '../../../../../www/helpers/card-services.js';

import {
  validateCoreEntities,
  validateDehumidifyEntities,
  getEntityValidationReport,
} from '../../../../../www/helpers/card-validation.js';
```

### After (✅ Clean)

```javascript
// hvac-fan-card.js - Updated imports
import { HELPER_PATHS, getHelperPath } from '../../../../../www/helpers/paths.js';

// Import reusable helpers using environment-aware paths
import { SimpleCardTranslator } from HELPER_PATHS.CARD_TRANSLATIONS;
import { FAN_COMMANDS } from HELPER_PATHS.CARD_COMMANDS;
import { getRamsesMessageBroker } from HELPER_PATHS.RAMSES_MESSAGE_BROKER;

import {
  sendPacket,
  getBoundRemDevice,
  callService,
  entityExists,
  getEntityState,
  callWebSocket,
  setFanParameter,
} from HELPER_PATHS.CARD_SERVICES;

import {
  validateCoreEntities,
  validateDehumidifyEntities,
  getEntityValidationReport,
} from HELPER_PATHS.CARD_VALIDATION;
```

## Available Helper Paths

The `HELPER_PATHS` object provides shortcuts for all common helper files:

```javascript
HELPER_PATHS.CARD_COMMANDS; // -> 'path/to/card-commands.js'
HELPER_PATHS.CARD_SERVICES; // -> 'path/to/card-services.js'
HELPER_PATHS.CARD_TRANSLATIONS; // -> 'path/to/card-translations.js'
HELPER_PATHS.CARD_VALIDATION; // -> 'path/to/card-validation.js'
HELPER_PATHS.RAMSES_MESSAGE_BROKER; // -> 'path/to/ramses-message-broker.js'
```

## Dynamic Path Resolution

For more complex cases, use the path builder functions:

```javascript
import { getHelperPath, getFeaturePath } from '../../../../../www/helpers/paths.js';

// Get path for any helper file
const customHelperPath = getHelperPath('custom-helper.js');

// Get path for feature-specific assets
const featureCardPath = getFeaturePath('hvac_fan_card', 'hvac-fan-card.js');
const templatePath = getFeaturePath('hvac_fan_card', 'templates/card-header.js');
```

## Environment-Specific Behavior

The paths automatically adapt to the current environment:

- **Development**: Uses source file paths
- **Testing**: Uses mock/test paths
- **Production**: Uses deployed paths
- **Linting**: Uses project-relative paths

### Manual Environment Override

For testing or special cases, you can override the environment:

```javascript
import { setEnvironment, HELPER_PATHS } from '../../../../../www/helpers/paths.js';

// Force test environment
setEnvironment('test');
console.log(HELPER_PATHS.CARD_COMMANDS); // Shows test path

// Force production environment
setEnvironment('production');
console.log(HELPER_PATHS.CARD_COMMANDS); // Shows production path

// Reset to auto-detection
setEnvironment(null);
```

## Debugging Path Resolution

To see how paths are being resolved:

```javascript
import { getEnvironmentDebugInfo, getAllPaths } from '../../../../../www/helpers/paths.js';

// Get detailed debug information
console.log(getEnvironmentDebugInfo());

// Get all paths with debug info
console.log(getAllPaths());
```

This shows:

- The detected script location
- Which environment was detected
- What detection method was used
- All resolved paths

## Migration Checklist

- [ ] Replace ugly relative imports with `HELPER_PATHS` constants
- [ ] Use `getHelperPath()` for custom helper files
- [ ] Use `getFeaturePath()` for feature-specific assets
- [ ] Test imports work in different environments
- [ ] Remove any hardcoded relative path calculations

## Benefits

✅ **Cleaner Code**: No more `../../../../../` chains
✅ **Environment-Aware**: Works in dev, test, and production
✅ **Maintainable**: Centralized path management
✅ **Debuggable**: Easy to see how paths are resolved
✅ **Future-Proof**: Automatically adapts to new environments

## File Location Detection

The system detects environment based on the current file location:

- **Source files**: `custom_components/ramses_extras/www/helpers/paths.js` → `development`
- **Test files**: Files containing `MagicMock`, `/test/`, etc. → `test`
- **Production**: Files in `/local/ramses_extras/` → `production`
- **Linting**: Files in node_modules or with eslint patterns → `lint`

This is much more reliable than hostname-based detection!
