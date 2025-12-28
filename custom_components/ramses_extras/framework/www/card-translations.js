/* eslint-disable no-console */
/* global navigator */
/* global fetch */

/**
 * Simple Localization Support
 * Embedded translation system to avoid module import issues
 */

// Helper to rewrite paths to versioned base if needed
function rewritePathToVersioned(path) {
  if (typeof window === 'undefined' || !window.ramsesExtras || !window.ramsesExtras.assetBase) {
    return path;
  }

  // Only rewrite /local/ramses_extras/features/... paths
  if (path.startsWith('/local/ramses_extras/features/')) {
    const relativePath = path.replace('/local/ramses_extras/features/', '');
    return `${window.ramsesExtras.assetBase}/features/${relativePath}`;
  }

  return path;
}

// Simple translation system embedded directly in the card
export class SimpleCardTranslator {
  constructor(cardName) {
    this.cardName = cardName;
    this.translations = {};
    this.currentLanguage = 'en';
    this.initialized = false;
  }

  async init(cardPath) {
    try {
      this.currentLanguage = this.detectLanguage();
      await this.loadTranslations(cardPath);
      this.initialized = true;
    } catch (error) {
      console.warn(`⚠️ Failed to load translations for ${this.cardName}:`, error);
      this.initialized = true; // Continue without translations
    }
  }

  detectLanguage() {
    if (window.hass && window.hass.language) {
      return window.hass.language.split('-')[0];
    }
    if (navigator.language) {
      return navigator.language.split('-')[0];
    }
    return 'en';
  }

  async loadTranslations(cardPath) {
    const versionedCardPath = rewritePathToVersioned(cardPath);
    const translationPath = `${versionedCardPath}/translations/${this.currentLanguage}.json`;
    try {
      const response = await fetch(translationPath);
      if (response.ok) {
        try {
          const responseText = await response.text();
          this.translations = JSON.parse(responseText);
        } catch (jsonError) {
          console.warn(`⚠️ Invalid JSON in translation file ${translationPath}:`, jsonError);
          await this.loadFallbackTranslations(cardPath);
        }
      } else {
        console.warn(`⚠️ Translation file not found (${response.status}): ${translationPath}`);
        await this.loadFallbackTranslations(cardPath);
      }
    } catch (error) {
      console.warn(`⚠️ Could not load translations:`, error);
      await this.loadFallbackTranslations(cardPath);
    }
  }

  async loadFallbackTranslations(cardPath) {
    const versionedCardPath = rewritePathToVersioned(cardPath);
    const fallbackPath = `${versionedCardPath}/translations/en.json`;
    try {
      const fallbackResponse = await fetch(fallbackPath);

      if (fallbackResponse.ok) {
        try {
          const responseText = await fallbackResponse.text();
          this.translations = JSON.parse(responseText);
        } catch (jsonError) {
          console.warn(`⚠️ Invalid JSON in fallback translation file:`, jsonError);
          this.translations = {};
        }
      } else {
        console.warn(`⚠️ Fallback translation file not found: ${fallbackPath}`);
        this.translations = {};
      }
    } catch (error) {
      console.warn(`⚠️ Could not load fallback translations:`, error);
      this.translations = {};
    }
  }

  t(key, params = {}) {
    if (!this.initialized) return key;

    const keys = key.split('.');
    let value = this.translations;

    for (const k of keys) {
      if (value && typeof value === 'object' && k in value) {
        value = value[k];
      } else {
        return key; // Return key if translation not found
      }
    }

    if (typeof value !== 'string') return key;

    // Simple string interpolation
    return value.replace(/\{(\w+)\}/g, (match, paramKey) => {
      return params[paramKey] !== undefined ? params[paramKey] : match;
    });
  }

  has(key) {
    if (!this.translations || !this.initialized) return false;

    const keys = key.split('.');
    let value = this.translations;

    for (const k of keys) {
      if (value && typeof value === 'object' && k in value) {
        value = value[k];
      } else {
        return false;
      }
    }

    return typeof value === 'string';
  }

  getCurrentLanguage() {
    return this.currentLanguage;
  }
}

/**
 * Translation Manager for Home Assistant Custom Cards
 * Provides flexible localization support following HA conventions
 */

export class CardTranslations {
  constructor(cardName) {
    this.cardName = cardName;
    this.currentLanguage = 'en';
    this.translations = {};
    this.fallbackLanguage = 'en';
    this.initialized = false;
  }

  /**
   * Initialize translations for the card
   * @param {string} cardPath - Path to the card directory
   * @param {string} defaultLanguage - Default language code (default: 'en')
   */
  async init(cardPath, defaultLanguage = 'en') {
    this.fallbackLanguage = defaultLanguage;
    this.currentLanguage = this.detectLanguage();

    try {
      await this.loadTranslations(cardPath);
      this.initialized = true;
    } catch (error) {
      console.error(`❌ Failed to load translations for ${this.cardName}:`, error);
      // Fallback to default language
      this.currentLanguage = this.fallbackLanguage;
      try {
        await this.loadTranslations(cardPath, this.fallbackLanguage);
        this.initialized = true;
      } catch (fallbackError) {
        console.error(`❌ Failed to load fallback translations:`, fallbackError);
      }
    }
  }

  /**
   * Detect user's preferred language from HA or browser
   */
  detectLanguage() {
    // Try to get language from Home Assistant
    if (typeof window !== 'undefined' && window.hass && window.hass.language) {
      return window.hass.language.split('-')[0]; // Get 'en' from 'en-US'
    }

    // Fallback to browser language
    if (typeof navigator !== 'undefined' && navigator.language) {
      return navigator.language.split('-')[0];
    }

    // Final fallback
    return 'en';
  }

  /**
   * Load translation files for the card
   * @param {string} cardPath - Path to card directory
   * @param {string} language - Language code
   */
  async loadTranslations(cardPath, language = this.currentLanguage) {
    const versionedCardPath = rewritePathToVersioned(cardPath);
    const translationPath = `${versionedCardPath}/translations/${language}.json`;

    try {
      const response = await fetch(translationPath);
      if (!response.ok) {
        throw new Error(`Translation file not found: ${translationPath}`);
      }

      const translations = await response.json();
      this.translations[language] = translations;
    } catch (error) {
      // If current language fails, try fallback
      if (language !== this.fallbackLanguage) {
        console.warn(`⚠️ ${language} translations not found, trying fallback: ${this.fallbackLanguage}`);
        await this.loadTranslations(cardPath, this.fallbackLanguage);
      } else {
        throw error;
      }
    }
  }

  /**
   * Get translated string with fallback support
   * @param {string} key - Translation key (supports dot notation: 'card.title')
   * @param {Object} params - Parameters for string interpolation
   * @returns {string} Translated string
   */
  t(key, params = {}) {
    if (!this.initialized) {
      console.warn(`⚠️ Translations not initialized for ${this.cardName}`);
      return key;
    }

    const keys = key.split('.');
    let value = this.translations[this.currentLanguage];

    // Navigate through nested keys
    for (const k of keys) {
      if (value && typeof value === 'object' && k in value) {
        value = value[k];
      } else {
        // Try fallback language
        value = this.translations[this.fallbackLanguage];
        for (const k of keys) {
          if (value && typeof value === 'object' && k in value) {
            value = value[k];
          } else {
            console.warn(`⚠️ Missing translation: ${key} for ${this.cardName}`);
            return key; // Return key if translation not found
          }
        }
        break;
      }
    }

    if (typeof value !== 'string') {
      console.warn(`⚠️ Translation value is not a string: ${key}`);
      return key;
    }

    // String interpolation for parameters like {minutes}
    return value.replace(/\{(\w+)\}/g, (match, paramKey) => {
      return params[paramKey] !== undefined ? params[paramKey] : match;
    });
  }

  /**
   * Check if a translation key exists
   * @param {string} key - Translation key
   * @returns {boolean} True if key exists
   */
  has(key) {
    if (!this.initialized) return false;

    try {
      const test = this.t(key);
      return test !== key; // If different from key, translation exists
    } catch {
      return false;
    }
  }

  /**
   * Get all available languages for this card
   * @returns {Array<string>} Array of language codes
   */
  getAvailableLanguages() {
    return Object.keys(this.translations);
  }

  /**
   * Switch to a different language
   * @param {string} language - Language code
   * @param {string} cardPath - Card path for loading new translations
   */
  async switchLanguage(language, cardPath) {
    if (this.translations[language]) {
      this.currentLanguage = language;
      return;
    }

    // Load new language
    try {
      await this.loadTranslations(cardPath, language);
      this.currentLanguage = language;
    } catch (error) {
      console.error(`❌ Failed to switch to language ${language}:`, error);
    }
  }

  /**
   * Get current language
   * @returns {string} Current language code
   */
  getCurrentLanguage() {
    return this.currentLanguage;
  }
}

/**
 * Helper function to create a translation manager for a card
 * @param {string} cardName - Name of the card
 * @param {string} cardPath - Path to card directory
 * @param {string} defaultLanguage - Default language
 * @returns {Promise<CardTranslations>} Initialized translation manager
 */
export async function createCardTranslator(cardName, cardPath, defaultLanguage = 'en') {
  const translator = new CardTranslations(cardName);
  await translator.init(cardPath, defaultLanguage);
  return translator;
}

/**
 * Get user's preferred language for cards
 * @returns {string} Language code
 */
export function getUserLanguage() {
  // Try to get from Home Assistant
  if (typeof window !== 'undefined' && window.hass && window.hass.language) {
    return window.hass.language.split('-')[0];
  }

  // Fallback to browser
  if (typeof navigator !== 'undefined' && navigator.language) {
    return navigator.language.split('-')[0];
  }

  return 'en';
}

/**
 * Check if a language is RTL (Right-to-Left)
 * @param {string} language - Language code
 * @returns {boolean} True if RTL language
 */
export function isRTL(language) {
  const rtlLanguages = ['ar', 'he', 'fa', 'ur'];
  return rtlLanguages.includes(language);
}

// Global translation cache to avoid duplicate loading
const translationCache = new Map();

/**
 * Get cached or create new translator instance
 * @param {string} cardName - Name of the card
 * @param {string} cardPath - Path to card directory
 * @returns {Promise<CardTranslations>} Translation manager
 */
export async function getTranslator(cardName, cardPath) {
  const cacheKey = `${cardName}:${cardPath}`;

  if (translationCache.has(cacheKey)) {
    return translationCache.get(cacheKey);
  }

  const translator = await createCardTranslator(cardName, cardPath);
  translationCache.set(cacheKey, translator);
  return translator;
}

/**
 * Clear translation cache (useful for testing)
 */
export function clearTranslationCache() {
  translationCache.clear();
}
