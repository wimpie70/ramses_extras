# Environment-Aware Path Resolution System

**Date**: 2025-11-22
**Status**: Design Draft
**Purpose**: Handle different file locations for testing, linting, development, and production environments

## Problem Statement

The current path system uses hardcoded production paths (`/local/ramses_extras`) which don't work in:

- Development environment (source files in different locations)
- Testing environment (mock files in different paths)
- Linting environment (different working directories)

## Solution Design

### Environment Detection Strategy

```javascript
/**
 * Detect the current environment based on multiple indicators
 */
export function detectEnvironment() {
  const indicators = {
    // Check for testing indicators
    isTest:
      typeof jest !== 'undefined' ||
      typeof vitest !== 'undefined' ||
      (window.location?.hostname === 'localhost' && document?.title?.includes('test')),

    // Check for development indicators
    isDevelopment:
      window.location?.hostname === 'localhost' ||
      window.location?.hostname === '127.0.0.1' ||
      (typeof process !== 'undefined' && process.env?.NODE_ENV === 'development'),

    // Check for linting indicators
    isLint:
      typeof ESLINT !== 'undefined' || (typeof require !== 'undefined' && require.main === module),

    // Check for production indicators
    isProduction:
      (typeof process !== 'undefined' && process.env?.NODE_ENV === 'production') ||
      window.location?.hostname !== 'localhost',
  };

  // Determine primary environment (priority: test > lint > development > production)
  if (indicators.isTest) return 'test';
  if (indicators.isLint) return 'lint';
  if (indicators.isDevelopment) return 'development';
  return 'production';
}
```

### Context-Aware Path Resolution

```javascript
/**
 * Environment-specific base paths
 */
const ENVIRONMENTS = {
  production: {
    RAMSES_EXTRAS_BASE: '/local/ramses_extras',
    HELPERS_BASE: '/local/ramses_extras/helpers',
    FEATURES_BASE: '/local/ramses_extras',
  },

  development: {
    // For development, files are in source structure
    RAMSES_EXTRAS_BASE: '/local/ramses_extras',
    HELPERS_BASE: '/local/ramses_extras/www/helpers',
    FEATURES_BASE: '/local/ramses_extras',
  },

  test: {
    // For testing, use relative paths from test location
    RAMSES_EXTRAS_BASE: '../..',
    HELPERS_BASE: '../www/helpers',
    FEATURES_BASE: '../..',
  },

  lint: {
    // For linting, use project-relative paths
    RAMSES_EXTRAS_BASE: './custom_components/ramses_extras',
    HELPERS_BASE: './custom_components/ramses_extras/www/helpers',
    FEATURES_BASE: './custom_components/ramses_extras',
  },
};

/**
 * Resolve paths based on current environment
 */
export function resolveBasePaths(environment = detectEnvironment()) {
  return ENVIRONMENTS[environment] || ENVIRONMENTS.production;
}

/**
 * Environment-aware helper path resolver
 */
export function getHelperPath(fileName, customEnvironment = null) {
  const env = customEnvironment || detectEnvironment();
  const basePaths = resolveBasePaths(env);

  return `${basePaths.HELPERS_BASE}/${fileName}`;
}

/**
 * Environment-aware feature path resolver
 */
export function getFeaturePath(featureName, assetPath = '', customEnvironment = null) {
  const env = customEnvironment || detectEnvironment();
  const basePaths = resolveBasePaths(env);

  const basePath = `${basePaths.FEATURES_BASE}/${featureName}`;
  return assetPath ? `${basePath}/${assetPath}` : basePath;
}
```

### Usage Examples

#### In Feature Files

```javascript
// Instead of ugly relative paths:
import { FAN_COMMANDS } from '../../../../../www/helpers/card-commands.js';

// Use environment-aware paths:
import { getHelperPath } from '../../../../../www/helpers/paths.js';
import { FAN_COMMANDS } from getHelperPath('card-commands.js');

// Or with direct environment specification for testing:
import { getHelperPath } from '/path/to/paths.js';
import { FAN_COMMANDS } from getHelperPath('card-commands.js', 'test');
```

#### For Testing Environments

```javascript
// In test files, specify test environment explicitly:
import { getHelperPath } from '../../../www/helpers/paths.js';

// Mock the environment for specific tests:
import { getHelperPath } from '../../../www/helpers/paths.js';

// Override for specific test cases:
const testPath = getHelperPath('card-commands.js', 'test');
```

### Implementation Benefits

1. **Automatic Environment Detection**: No manual configuration needed
2. **Contextual Path Resolution**: Paths adapt to current environment
3. **Testing Support**: Test files can specify their context
4. **Backward Compatibility**: Existing code continues to work
5. **Debugging Support**: Easy to see what environment is detected

### Configuration Override

```javascript
/**
 * Override environment detection for specific cases
 */
export function setEnvironment(environment) {
  if (ENVIRONMENTS[environment]) {
    window.RAMSES_EXTRAS_ENV = environment;
    return true;
  }
  return false;
}

/**
 * Get current environment (with override support)
 */
export function getCurrentEnvironment() {
  return window.RAMSES_EXTRAS_ENV || detectEnvironment();
}
```

### Migration Strategy

1. **Phase 1**: Add environment detection to existing paths.js
2. **Phase 2**: Update feature files to use new path resolvers
3. **Phase 3**: Add environment override support for special cases
4. **Phase 4**: Test across all environments

This approach eliminates the need for manual path configuration while maintaining flexibility for different development contexts.
