/* global URL */
/* global process */
/**
 * Environment-Aware Path Resolution for Ramses Extras
 *
 * Provides centralized path management that adapts to different environments:
 * - Production: Home Assistant deployment
 * - Development: Source code environment
 * - Testing: Test suites with mocks
 * - Linting: ESLint and other tools
 *
 * This file should be imported by any JavaScript file that needs to
 * reference helpers or feature-specific assets.
 */

import * as logger from './logger.js';

/**
 * File Location Detection
 * Determines the current file location to accurately detect environment
 */
function getCurrentScriptLocation() {
  try {
    // Method 1: Try to get the current script URL (browser)
    if (typeof document !== 'undefined') {
      const currentScript = document.currentScript;
      if (currentScript && currentScript.src) {
        return new URL(currentScript.src).pathname;
      }

      // Fallback: try to find this script in the document
      const scripts = document.getElementsByTagName('script');
      for (let i = scripts.length - 1; i >= 0; i--) {
        const script = scripts[i];
        if (script.src && script.src.includes('paths.js')) {
          return new URL(script.src).pathname;
        }
      }
    }

    // Method 2: Try to get the referrer or document location (browser)
    if (typeof document !== 'undefined' && document.referrer) {
      return new URL(document.referrer).pathname;
    }

    // Method 3: Try import.meta.url (ES modules in Node.js/bundlers)
    try {
      if (typeof window === 'undefined' && globalThis.import?.meta?.url) {
        return new URL(globalThis.import.meta.url).pathname;
      }
      // Alternative check for import.meta
      if (typeof window === 'undefined' && globalThis.process?.versions?.node) {
        // We're in Node.js, try to get the module path
        const modulePath = globalThis.__dirname || process.cwd();
        return `${modulePath}/paths.js`;
      }
    // eslint-disable-next-line no-unused-vars
    } catch (_) {
      // Continue to next method
    }

    // Method 4: Try to use error stack to find this file (last resort)
    if (typeof Error !== 'undefined') {
      const stack = new Error().stack;
      if (stack && stack.includes('paths.js')) {
        const lines = stack.split('\n');
        for (const line of lines) {
          if (line.includes('paths.js') && line.includes('http')) {
            try {
              return new URL(line.match(/https?:\/\/[^\s]+/)[0]).pathname;
            // eslint-disable-next-line no-unused-vars
            } catch (_) {
              // Continue to next method
            }
          }
        }
      }
    }

    // Method 5: Check if we're in a test environment by looking for common test patterns
    if (typeof window !== 'undefined' && window.location) {
      const path = window.location.pathname;
      if (path.includes('/test') || path.includes('/tests') || path.includes('/__tests__')) {
        return '/test/path/paths.js';
      }
    }

  // eslint-disable-next-line no-unused-vars
  } catch (_) {
    // Silently fail and return null
  }

  return null;
}

/**
 * Detect environment based on file location patterns
 * This is much more reliable than hostname checking
 */
function detectEnvironmentFromLocation() {
  const scriptPath = getCurrentScriptLocation();

  if (!scriptPath) {
    // If we can't determine location, fall back to other methods
    return detectEnvironmentFromContext();
  }

  // Check for test/mock environments (highest priority)
  if (scriptPath.includes('MagicMock') ||
      scriptPath.includes('/test') ||
      scriptPath.includes('/tests') ||
      scriptPath.includes('__tests__') ||
      scriptPath.includes('mock.config')) {
    return 'test';
  }

  // Check for source code structure (development)
  if (scriptPath.includes('custom_components/ramses_extras/framework/www/paths.js') ||
      scriptPath.includes('ramses_extras/custom_components/ramses_extras/framework/www/paths.js')) {
    return 'development';
  }

  // Check for linting environment patterns
  if (scriptPath.includes('/node_modules/') ||
      scriptPath.includes('.eslintrc') ||
      scriptPath.includes('eslint.config')) {
    return 'lint';
  }

  // Check for deployed production patterns
  if (scriptPath.includes('/local/ramses_extras/')) {
    return 'production';
  }

  // Check for feature-specific paths (still development)
  if (scriptPath.includes('/features/') && scriptPath.includes('/www/')) {
    return 'development';
  }

  // Default based on path structure
  if (scriptPath.includes('/custom_components/')) {
    return 'development';
  }

  return 'production';
}

/**
 * Fallback environment detection based on context indicators
 */
function detectEnvironmentFromContext() {
  // Check for testing indicators
  if (typeof jest !== 'undefined' ||
      typeof vitest !== 'undefined' ||
      (typeof window !== 'undefined' && window.location?.hostname === 'localhost' &&
       document?.title?.toLowerCase().includes('test'))) {
    return 'test';
  }

  // Check for linting indicators
  if (typeof ESLINT !== 'undefined' ||
      (typeof process !== 'undefined' && process.argv?.some(arg => arg.includes('eslint')))) {
    return 'lint';
  }

  // Check for development indicators
  if ((typeof window !== 'undefined' && (
        window.location?.hostname === 'localhost' ||
        window.location?.hostname === '127.0.0.1')) ||
      (typeof process !== 'undefined' && process.env?.NODE_ENV === 'development')) {
    return 'development';
  }

  // Default to production
  return 'production';
}

/**
 * Environment Detection
 * Main entry point - tries file location detection first, then context
 */
function detectEnvironment() {
  return detectEnvironmentFromLocation();
}

/**
 * Environment-specific base paths
 * Each environment has its own path structure
 */
const ENVIRONMENTS = {
  production: {
    // Home Assistant deployment structure
    RAMSES_EXTRAS_BASE: '/local/ramses_extras',
    HELPERS_BASE: '/local/ramses_extras/helpers',
    FEATURES_BASE: '/local/ramses_extras/features',
    DESCRIPTION: 'Home Assistant production environment'
  },

  development: {
    // Development environment (source files)
    RAMSES_EXTRAS_BASE: '/local/ramses_extras',
    HELPERS_BASE: '/local/ramses_extras/framework/www',
    FEATURES_BASE: '/local/ramses_extras/features',
    DESCRIPTION: 'Development environment with source files'
  },

  test: {
    // Test environment - use relative paths
    RAMSES_EXTRAS_BASE: '../..',
    HELPERS_BASE: '../www/ramses_extras/helpers',
    FEATURES_BASE: '../www/ramses_extras/features',
    DESCRIPTION: 'Test environment with mocks'
  },

  lint: {
    // Linting environment - project-relative paths
    RAMSES_EXTRAS_BASE: './custom_components/ramses_extras',
    HELPERS_BASE: './custom_components/ramses_extras/framework/www',
    FEATURES_BASE: './custom_components/ramses_extras/features',
    DESCRIPTION: 'ESLint and code analysis environment'
  }
};

/**
 * Global environment override support
 * Allows setting environment explicitly for special cases
 */
let GLOBAL_ENVIRONMENT_OVERRIDE = null;

/**
 * Set environment override (for testing or special cases)
 * @param {string} environment - Environment name ('production', 'development', 'test', 'lint')
 * @returns {boolean} True if environment was set successfully
 */
export function setEnvironment(environment) {
  if (ENVIRONMENTS[environment]) {
    GLOBAL_ENVIRONMENT_OVERRIDE = environment;
    if (typeof window !== 'undefined') {
      window.RAMSES_EXTRAS_ENV = environment;
    }
    return true;
  }
  logger.warn(
    `Unknown environment: ${environment}. Valid environments: ${Object.keys(ENVIRONMENTS).join(', ')}`
  );
  return false;
}

/**
 * Get current environment (with override support)
 * @returns {string} Current environment name
 */
export function getCurrentEnvironment() {
  return GLOBAL_ENVIRONMENT_OVERRIDE || detectEnvironment();
}

/**
 * Get environment configuration
 * @param {string} environment - Environment name (optional, uses current if not specified)
 * @returns {Object} Environment configuration
 */
export function getEnvironmentConfig(environment = null) {
  const env = environment || getCurrentEnvironment();
  return ENVIRONMENTS[env] || ENVIRONMENTS.production;
}

/**
 * Resolve base paths for current environment
 * @param {string} environment - Environment name (optional)
 * @returns {Object} Base paths for the environment
 */
export function resolveBasePaths(environment = null) {
  return getEnvironmentConfig(environment);
}

/**
 * Environment-aware path constants
 * These adapt based on the current environment
 */
export const PATHS = {
  // Dynamic base paths (resolved at runtime)
  get RAMSES_EXTRAS_BASE() {
    if (typeof window !== 'undefined' && window.ramsesExtras?.assetBase) {
      return window.ramsesExtras.assetBase;
    }
    return resolveBasePaths().RAMSES_EXTRAS_BASE;
  },

  get HELPERS_BASE() {
    if (typeof window !== 'undefined' && window.ramsesExtras?.assetBase) {
      return `${window.ramsesExtras.assetBase}/helpers`;
    }
    return resolveBasePaths().HELPERS_BASE;
  },

  get FEATURES_BASE() {
    if (typeof window !== 'undefined' && window.ramsesExtras?.assetBase) {
      return `${window.ramsesExtras.assetBase}/features`;
    }
    return resolveBasePaths().FEATURES_BASE;
  },

  // Environment metadata
  get CURRENT_ENVIRONMENT() {
    return getCurrentEnvironment();
  },

  get ENVIRONMENT_DESCRIPTION() {
    return resolveBasePaths().DESCRIPTION;
  }
};

/**
 * Environment-aware helper path resolver
 * @param {string} helperFileName - Name of the helper file (e.g., 'card-commands.js')
 * @param {string} customEnvironment - Override environment for this call (optional)
 * @returns {string} Full path to the helper file
 */
export function getHelperPath(helperFileName, customEnvironment = null) {
  const basePaths = resolveBasePaths(customEnvironment);
  return `${basePaths.HELPERS_BASE}/${helperFileName}`;
}

/**
 * Environment-aware feature path resolver
 * @param {string} featureName - Name of the feature (e.g., 'hvac_fan_card')
 * @param {string} assetPath - Relative path within the feature's www folder (optional)
 * @param {string} customEnvironment - Override environment for this call (optional)
 * @returns {string} Full path to the feature asset
 */
export function getFeaturePath(featureName, assetPath = '', customEnvironment = null) {
  const basePaths = resolveBasePaths(customEnvironment);
  const basePath = `${basePaths.FEATURES_BASE}/${featureName}`;
  return assetPath ? `${basePath}/${assetPath}` : basePath;
}

/**
 * Get the full path for a feature card file
 * @param {string} featureName - Name of the feature
 * @param {string} cardFileName - Name of the card file (e.g., 'hvac-fan-card.js')
 * @param {string} customEnvironment - Override environment for this call (optional)
 * @returns {string} Full path to the feature card
 */
export function getFeatureCardPath(featureName, cardFileName, customEnvironment = null) {
  return getFeaturePath(featureName, cardFileName, customEnvironment);
}

/**
 * Get the full path for a feature template
 * @param {string} featureName - Name of the feature
 * @param {string} templatePath - Relative path within templates folder
 * @param {string} customEnvironment - Override environment for this call (optional)
 * @returns {string} Full path to the feature template
 */
export function getFeatureTemplatePath(featureName, templatePath, customEnvironment = null) {
  return getFeaturePath(featureName, `templates/${templatePath}`, customEnvironment);
}

/**
 * Get the full path for feature translations
 * @param {string} featureName - Name of the feature
 * @param {string} locale - Language locale (e.g., 'en', 'nl')
 * @param {string} customEnvironment - Override environment for this call (optional)
 * @returns {string} Full path to the translation file
 */
export function getFeatureTranslationPath(featureName, locale, customEnvironment = null) {
  return getFeaturePath(featureName, `translations/${locale}.json`, customEnvironment);
}

/**
 * Environment-aware helper file paths
 * These paths adapt to the current environment
 */
export const HELPER_PATHS = {
  get CARD_COMMANDS() {
    return getHelperPath('card-commands.js');
  },
  get CARD_SERVICES() {
    return getHelperPath('card-services.js');
  },
  get CARD_TRANSLATIONS() {
    return getHelperPath('card-translations.js');
  },
  get CARD_VALIDATION() {
    return getHelperPath('card-validation.js');
  },
  get RAMSES_MESSAGE_BROKER() {
    return getHelperPath('ramses-message-broker.js');
  }
};

/**
 * Get helper path for specific environment (for testing)
 * @param {string} fileName - Helper file name
 * @param {string} environment - Target environment
 * @returns {string} Helper path for the specified environment
 */
export function getHelperPathForEnvironment(fileName, environment) {
  return getHelperPath(fileName, environment);
}

/**
 * Get detailed debug information about environment detection
 * @returns {Object} Complete debug information
 */
export function getEnvironmentDebugInfo() {
  const scriptPath = getCurrentScriptLocation();
  const environment = getCurrentEnvironment();
  const config = getEnvironmentConfig();

  return {
    detectionMethod: 'file-location-based',
    scriptPath,
    detectedEnvironment: environment,
    environmentDescription: config.DESCRIPTION,
    fallbackUsed: scriptPath === null,
    detectionMethods: {
      hasDocument: typeof document !== 'undefined',
      hasCurrentScript: typeof document !== 'undefined' && !!document.currentScript,
      hasImportMeta: typeof window === 'undefined' && !!globalThis.import?.meta,
      isNodeJS: typeof window === 'undefined' && !!globalThis.process?.versions?.node,
      hasWindow: typeof window !== 'undefined',
      windowLocation: typeof window !== 'undefined' ? window.location?.href : null
    }
  };
}

/**
 * Get all paths for debugging
 * @returns {Object} All path information for current environment
 */
export function getAllPaths() {
  const environment = getCurrentEnvironment();
  const config = getEnvironmentConfig();
  const debugInfo = getEnvironmentDebugInfo();

  return {
    environment,
    description: config.DESCRIPTION,
    debug: debugInfo,
    basePaths: config,
    helperPaths: {
      CARD_COMMANDS: HELPER_PATHS.CARD_COMMANDS,
      CARD_SERVICES: HELPER_PATHS.CARD_SERVICES,
      CARD_TRANSLATIONS: HELPER_PATHS.CARD_TRANSLATIONS,
      CARD_VALIDATION: HELPER_PATHS.CARD_VALIDATION,
      RAMSES_MESSAGE_BROKER: HELPER_PATHS.RAMSES_MESSAGE_BROKER
    },
    dynamicPaths: {
      RAMSES_EXTRAS_BASE: PATHS.RAMSES_EXTRAS_BASE,
      HELPERS_BASE: PATHS.HELPERS_BASE,
      FEATURES_BASE: PATHS.FEATURES_BASE
    }
  };
}

/**
 * Validate that a path is properly formatted
 * @param {string} path - Path to validate
 * @returns {boolean} True if path is valid
 */
export function isValidPath(path) {
  return typeof path === 'string' && path.length > 0 && (path.startsWith('/') || path.startsWith('./') || path.startsWith('../'));
}

/**
 * Debug logging for path resolution
 * @param {string} context - Context where paths are being resolved
 */
export function debugPathResolution(context = 'unknown') {
  logger.debug(`🔍 Ramses Extras Path Resolution [${context}]:`, getAllPaths());
}

/**
 * Default export with all path constants and utilities
 * This allows for easy importing: import paths from './paths.js';
 */
export default {
  // Environment management
  setEnvironment,
  getCurrentEnvironment,
  getEnvironmentConfig,
  resolveBasePaths,

  // Path constants (dynamic)
  PATHS,
  HELPER_PATHS,

  // Path builders
  getHelperPath,
  getFeaturePath,
  getFeatureCardPath,
  getFeatureTemplatePath,
  getFeatureTranslationPath,
  getHelperPathForEnvironment,

  // Debug and utilities
  isValidPath,
  getAllPaths,
  getEnvironmentDebugInfo,
  debugPathResolution,

  // File location detection
  getCurrentScriptLocation,

  // Legacy compatibility (deprecated)
  detectEnvironment,
  ENVIRONMENTS
};

// Log path resolution info in development
if (typeof window !== 'undefined' && getCurrentEnvironment() === 'development') {
  const debugInfo = getEnvironmentDebugInfo();
  logger.debug(`🔍 Ramses Extras Path Resolution [module-load]:`, debugInfo);
}
