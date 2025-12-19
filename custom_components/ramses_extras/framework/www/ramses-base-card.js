/* eslint-disable no-console */
/* global customElements */
/* global HTMLElement */
/* global setTimeout */
/* global clearTimeout */

// Import framework utilities
import { SimpleCardTranslator } from './card-translations.js';
import { callWebSocket, entityExists, getEntityState, buildEntityId } from './card-services.js';
import { getRamsesMessageBroker } from './ramses-message-broker.js';
import { getFeatureTranslationPath } from './paths.js';

/**
 * RamsesBaseCard - Base class for Ramses Extras custom cards
 *
 * This class provides common functionality for all Ramses Extras cards.
 * Subclasses must extend this class and implement the required methods.
 *
 * Provides:
 * - Shadow DOM setup and lifecycle management
 * - Translation support with SimpleCardTranslator
 * - Configuration validation and normalization
 * - Home Assistant integration (hass/config management)
 * - WebSocket communication utilities
 * - Message broker integration for real-time updates
 * - Common entity validation and state management
 * - Automatic custom element and HA card registration
 *
 * Subclasses should implement:
 * - getCardSize() - Return card size for HA
 * - getConfigElement() - Return editor element (optional)
 * - render() - Main rendering logic (or renderNormalMode/renderEditMode)
 * - validateConfig(config) - Validate subclass-specific config (optional)
 * - getDefaultConfig() - Return default config (optional)
 * - getRequiredEntities() - Return required entity configuration (optional)
 * - handle_<MessageCode>(messageData) - Message handlers (optional)
 */
export class RamsesBaseCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: 'open' });

    // Core state management
    this._hass = null;
    this._config = null;
    this._initialStateLoaded = false;
    this._rendered = false;

    // Translation support
    this.translator = null;
    this._translationsLoaded = false;

    // WebSocket and communication
    this._pendingRequests = new Map();
    this._commandInProgress = false;

    // Message broker integration
    this._messageBroker = null;
    this._messageCodes = [];

    // Previous states for change detection
    this._previousStates = {};

    // Update control to prevent excessive updates on restart
    this._lastUpdateTime = 0;
    this._updateThrottleTime = 1000; // 1 second throttle
    this._hassLoaded = false; // Track if HASS is fully loaded
    this._hassLoadTimeout = null; // Timeout for HASS load detection (2 minute fallback)
    this._hassReadyListener = null; // Listener for HASS ready event

    this._featureReady = false;
    this._featureReadyUnsub = null;

    this._featureConfigLoadAttached = false;

    // Initialize translations
    this.initTranslations();
  }

  // ========== REQUIRED METHODS (Must be implemented by subclasses) ==========

  /**
   * Get card size for Home Assistant layout
   * @returns {number} Card size (1-6, typically 1-4)
   */
  getCardSize() {
    // This method must be implemented by subclasses
    throw new Error('getCardSize() must be implemented by subclass');
  }

  /**
   * Get configuration element for HA editor
   * @returns {HTMLElement|null} Configuration element or null
   */
  getConfigElement() {
    // This method must be implemented by subclasses
    throw new Error('getConfigElement() must be implemented by subclass');
  }

  /**
   * Main rendering method
   * Override this method for simple cards, or implement
   *  renderNormalMode/renderEditMode for complex cards
   */
  render() {
    // This method must be implemented by subclasses
    throw new Error('render() must be implemented by subclass');
  }

  // ========== OPTIONAL METHODS (Can be overridden by subclasses) ==========

  /**
   * Validate card-specific configuration
   * Default implementation checks for required device_id
   * Subclasses can override for additional validation
   * @param {Object} config - Configuration object
   * @returns {Object} Validation result {valid: boolean, errors: string[]}
   */
  validateConfig(config) {
    const errors = [];

    // Check for required device_id
    if (!config.device_id) {
      errors.push('Device ID is required');
    }

    return {
      valid: errors.length === 0,
      errors
    };
  }

  /**
   * Get default configuration for this card
   * @returns {Object} Default configuration
   */
  getDefaultConfig() {
    return {};
  }

  /**
   * Get required entity configuration for this card
   * @returns {Object} Required entities mapping
   */
  getRequiredEntities() {
    return {};
  }

  /**
   * Get message codes this card should listen for
   * @returns {Array<string>} Array of message codes (e.g., ['31DA', '10D0'])
   */
  getMessageCodes() {
    return [];
  }

  /**
   * Render in normal mode (for cards with edit modes)
   */
  renderNormalMode() {
    // Default implementation calls main render method
    this.render();
  }

  /**
   * Render in edit mode (for cards with edit modes)
   */
  renderEditMode() {
    // Default implementation calls main render method
    this.render();
  }

  /**
   * Handle specific message codes from message broker
   * Handlers should be named: handle_<MessageCode>(messageData)
   * e.g., handle_31DA(messageData), handle_10D0(messageData)
   */

  // ========== TRANSLATION MANAGEMENT ==========

  /**
   * Initialize translations for this card
   */
  async initTranslations() {
    try {
      this.translator = new SimpleCardTranslator(this.constructor.name);
      const translationPath = getFeatureTranslationPath(this.getFeatureName(), 'en');
      await this.translator.init(translationPath.replace('/translations/en.json', ''));
      this._translationsLoaded = true;

      // Force re-render if we have config and hass ready
      if (this._config && this._hass) {
        if (!this._isHomeAssistantRunning()) {
          this.renderHassInitializing();
        } else {
          this._ensureFeatureReadyLoaded();
          this.render();
        }
      }
    } catch (error) {
      console.warn(`⚠️ Failed to initialize translations for ${this.constructor.name}:`, error);
      this._translationsLoaded = true; // Continue without translations
    }
  }

  _isHomeAssistantRunning() {
    return this._hass?.config?.state === 'RUNNING';
  }

  /**
   * Get feature name from card name
   * Override this if your feature name differs from card name
   * @returns {string} Feature name
   */
  getFeatureName() {
    // Convert class name to feature name (e.g., Helloworld -> hello_world)
    const className = this.constructor.name.replace('Card', '');
    return className.replace(/([A-Z])/g, '_$1').toLowerCase().replace(/^_/, '');
  }

  /**
   * Check if the feature associated with this card is enabled
   * @returns {boolean} True if feature is enabled
   */
  isFeatureEnabled() {
    const featureName = this.getFeatureName();

    if (!window.ramsesExtras?.features) {
      this._ensureFeatureConfigLoaded();
      console.log(`Feature ${featureName} is enabled: unknown (loading)`);
      return null;
    }

    const isEnabled = window.ramsesExtras.features[featureName] === true;
    console.log(`Feature ${featureName} is enabled: ${isEnabled}`);
    return isEnabled;
  }

  _ensureFeatureConfigLoaded() {
    window.ramsesExtras = window.ramsesExtras || {};

    if (window.ramsesExtras.features) {
      return Promise.resolve();
    }

    if (!window.ramsesExtras._featuresLoadPromise) {
      if (!this._hass) {
        window.ramsesExtras._featuresLoadPromise = Promise.resolve();
      } else {
        window.ramsesExtras._featuresLoadPromise = callWebSocket(this._hass, {
          type: 'ramses_extras/default/get_enabled_features',
        })
          .then((result) => {
            window.ramsesExtras.features = result?.enabled_features || {};
          })
          .catch((error) => {
            console.warn('⚠️ Failed to load Ramses Extras feature configuration via WebSocket:', error);
          });
      }
    }

    if (!this._featureConfigLoadAttached) {
      this._featureConfigLoadAttached = true;
      window.ramsesExtras._featuresLoadPromise.then(() => {
        try {
          if (this._hass && this._config) {
            this.render();
          }
        } catch (error) {
          console.warn('⚠️ Failed to re-render after feature config load:', error);
        }
      });
    }

    return window.ramsesExtras._featuresLoadPromise;
  }

  /**
   * Get translated string
   * @param {string} key - Translation key
   * @param {Object} params - Parameters for string interpolation
   * @returns {string} Translated string
   */
  t(key, params = {}) {
    if (!this.translator || !this._translationsLoaded) {
      return key; // Fallback if translator not ready
    }
    return this.translator.t(key, params);
  }

  /**
   * Check if translation exists
   * @param {string} key - Translation key
   * @returns {boolean} True if translation exists
   */
  hasTranslation(key) {
    if (!this.translator || !this._translationsLoaded) {
      return false;
    }
    return this.translator.has(key);
  }

  // ========== CONFIGURATION MANAGEMENT ==========

  /**
   * Set card configuration
   * @param {Object} config - Card configuration
   */
  setConfig(config) {
    try {
      // Flexible validation: only validate if config is not empty (during actual configuration)
      // This allows the card to be created without configuration first
      if (config && Object.keys(config).length > 0) {
        // Validate configuration using subclass validation
        const validation = this.validateConfig(config);
        if (!validation.valid) {
          throw new Error(`Configuration validation failed: ${validation.errors.join(', ')}`);
        }
      }

      // If no config or empty config, just store it and return early
      if (!config || Object.keys(config).length === 0) {
        this._config = {};
        return;
      }

      // Normalize device ID to colon format for consistency
      const deviceId = config.device_id ? config.device_id.replace(/_/g, ':') : null;

      // Process configuration
      this._config = {
        device_id: deviceId,
        ...this.getDefaultConfig(),
        ...config
      };

      // Reset state
      this._rendered = false;
      this._initialStateLoaded = false;
      this._previousStates = {};
      this.clearUpdateThrottle(); // Clear throttle on config change

      // Load initial state if hass is available
      if (this._hass) {
        if (!this._isHomeAssistantRunning()) {
          this.renderHassInitializing();
          return;
        }

        this._ensureFeatureReadyLoaded();
        if (!this._featureReady) {
          this.renderFeatureInitializing();
          return;
        }
        this._checkAndLoadInitialState();
        this.render();
      }
    } catch (error) {
      console.error(`❌ ${this.constructor.name}: Configuration error:`, error);
      throw error;
    }
  }

  /**
   * Get current configuration
   * @returns {Object} Current configuration
   */
  get config() {
    return this._config;
  }

  /**
   * Set configuration
   * @param {Object} config - Configuration to set
   */
  set config(config) {
    this._config = config;
  }

  // ========== HOME ASSISTANT INTEGRATION ==========

  /**
   * Set Home Assistant instance
   * @param {Object} hass - Home Assistant instance
   */
  set hass(hass) {
    const previousConnection = this._hass?.connection;
    this._hass = hass;

    if (this._config) {
      const connectionChanged = previousConnection !== hass?.connection;

      if (!this._isHomeAssistantRunning()) {
        this._hassLoaded = false;
        this.clearUpdateThrottle();
        this.renderHassInitializing();
        return;
      }

      this._ensureFeatureReadyLoaded();
      if (!this._featureReady) {
        this._hassLoaded = false;
        this.clearUpdateThrottle();
        this.renderFeatureInitializing();
        return;
      }

      if (!this._hassLoaded) {
        this._hassLoaded = true;
        this.clearUpdateThrottle();
        this._checkAndLoadInitialState();
        this.render();
        return;
      }

      // Mark that HASS is being set (may be during initial load)
      if (connectionChanged) {
        this._hassLoaded = false;
      }

      // Clear any existing timeout
      if (connectionChanged && this._hassLoadTimeout) {
        clearTimeout(this._hassLoadTimeout);
      }

      // Clear any existing ready listener
      if (connectionChanged && this._hassReadyListener) {
        this._hassReadyListener();
        this._hassReadyListener = null;
      }

      // Listen for the HASS ready event to mark when HASS is fully loaded
      // This is the proper way to detect when HASS has finished its initial state sync
      if (connectionChanged && hass && hass.connection) {
        this._hassReadyListener = hass.connection.addEventListener('ready', () => {
          this._hassLoaded = true;
          console.log(`✅ ${this.constructor.name}: HASS ready event received, allowing updates and rendering`);
          this._hassReadyListener = null;

          // After HASS is ready, load initial state and render
          this._loadInitialState();
          this.render();
        });
      }

      // Fallback timeout in case ready event doesn't fire
      if (connectionChanged) {
        this._hassLoadTimeout = setTimeout(() => {
          if (!this._hassLoaded) {
            this._hassLoaded = true;
            console.log(`⚠️ ${this.constructor.name}: HASS ready timeout reached after 2 minutes, assuming HASS is loaded`);

            // After timeout, load initial state and render
            this._loadInitialState();
            this.render();
          }
        }, 120000); // Wait 2 minutes for ready event
      }

      // Clear throttle when hass is set to allow initial updates
      this.clearUpdateThrottle();

      // Check if we should update based on entity changes
      if (this.shouldUpdate()) {
        this.render();
      }
    }
  }

  /**
   * Check if card should update based on entity state changes
   * @returns {boolean} True if card should update
   */
  shouldUpdate() {
    if (!this._hass || !this.config) {
      console.log(`🔍 ${this.constructor.name}: shouldUpdate - missing hass or config`);
      return false;
    }

    // Wait until HASS is fully loaded to prevent excessive updates on restart
    if (!this._hassLoaded) {
      return false;
    }

    // Throttle updates to prevent excessive calls
    const now = Date.now();
    if (now - this._lastUpdateTime < this._updateThrottleTime) {
      console.log(`🔍 ${this.constructor.name}: shouldUpdate - throttled, skipping update check`);
      return false;
    }

    const requiredEntities = this.getRequiredEntities();

    if (Object.keys(requiredEntities).length === 0) {
      // No specific entities to monitor, always update
      console.log(`🔍 ${this.constructor.name}: shouldUpdate - no required entities, always update`);
      return true;
    }

    // Check if any monitored entities have changed
    const hasChanges = Object.entries(requiredEntities).some(([key, entityId]) => {
      if (!entityId) {
        console.log(`🔍 ${this.constructor.name}: shouldUpdate - entity ${key} is null/undefined`);
        return false;
      }

      const oldState = this._previousStates[entityId];
      const newState = this._hass.states[entityId];
      this._previousStates[entityId] = newState;

      const changed = oldState !== newState;
      console.log(`🔍 ${this.constructor.name}: shouldUpdate - entity ${entityId}:`, {
        oldState: oldState?.state,
        newState: newState?.state,
        changed
      });

      return changed;
    });

    console.log(`🔍 ${this.constructor.name}: shouldUpdate result:`, hasChanges);

    // Update the last update time if there are changes
    if (hasChanges) {
      this._lastUpdateTime = now;
    }

    return hasChanges;
  }

  // ========== INITIAL STATE LOADING ==========

  /**
   * Check and load initial state
   */
  _checkAndLoadInitialState() {
    if (this._hass && this._config && !this._initialStateLoaded) {
      this._loadInitialState();
      this._initialStateLoaded = true;
    }
  }

  /**
   * Load initial state from backend
   * Override this method if you need custom initial state loading
   */
  async _loadInitialState() {
    if (!this._hass || !this._config?.device_id) return;

    try {
      // Default implementation - subclasses can override
      console.log(`🔄 ${this.constructor.name}: Loading initial state for device:`, this._config.device_id);
    } catch (error) {
      console.warn(`⚠️ ${this.constructor.name}: Failed to load initial state:`, error);
    } finally {
      // Clear throttle after initial state loading to allow updates
      this.clearUpdateThrottle();
    }
  }

  // ========== WEBSOCKET COMMUNICATION ==========

  /**
   * Send WebSocket command with request tracking
   * @param {Object} message - WebSocket message
   * @param {string} requestKey - Unique key for request tracking
   * @returns {Promise<Object>} Response
   */
  async _sendWebSocketCommand(message, requestKey = null) {
    const key = requestKey || `request_${Date.now()}`;

    // Return existing pending request if one is already in progress
    if (this._pendingRequests.has(key)) {
      return this._pendingRequests.get(key);
    }

    // Create new request and track it
    const requestPromise = this._performWebSocketCommand(message);
    this._pendingRequests.set(key, requestPromise);

    try {
      return await requestPromise;
    } finally {
      // Clean up the pending request when done
      this._pendingRequests.delete(key);
    }
  }

  /**
   * Perform WebSocket command
   * @param {Object} message - WebSocket message
   * @returns {Promise<Object>} Response
   */
  async _performWebSocketCommand(message) {
    try {
      return await callWebSocket(this._hass, message);
    } catch (error) {
      console.error(`❌ ${this.constructor.name}: WebSocket command failed:`, error);
      throw error;
    }
  }

  /**
   * Set command in progress flag (for preventing multiple simultaneous commands)
   * @param {boolean} inProgress - Command in progress flag
   */
  _setCommandInProgress(inProgress) {
    this._commandInProgress = inProgress;
  }

  /**
   * Check if command is in progress
   * @returns {boolean} True if command is in progress
   */
  isCommandInProgress() {
    return this._commandInProgress;
  }

  /**
   * Clear update throttle to allow immediate updates
   * Useful after manual state changes or when forcing a re-render
   */
  clearUpdateThrottle() {
    this._lastUpdateTime = 0;
  }

  /**
   * Clear previous states to force update detection on next check
   * Similar to hvac_fan_card's approach
   */
  clearPreviousStates() {
    this._previousStates = {};
  }

  // ========== ENTITY UTILITIES ==========

  /**
   * Check if entity exists
   * @param {string} entityId - Entity ID
   * @returns {boolean} True if entity exists
   */
  entityExists(entityId) {
    return entityExists(this._hass, entityId);
  }

  /**
   * Get entity state
   * @param {string} entityId - Entity ID
   * @returns {Object|null} Entity state or null if not found
   */
  getEntityState(entityId) {
    return getEntityState(this._hass, entityId);
  }

  /**
   * Build entity ID from device ID and entity type
   * @param {string} domain - Entity domain (e.g., "switch", "sensor")
   * @param {string} entitySuffix - Entity suffix
   * @returns {string} Complete entity ID
   */
  buildEntityId(domain, entitySuffix) {
    return buildEntityId(this._config.device_id, domain, entitySuffix);
  }

  /**
   * Get entity state value as boolean
   * @param {string} entityId - Entity ID
   * @param {boolean} defaultValue - Default value if entity not found
   * @returns {boolean} Entity state as boolean
   */
  getEntityStateAsBoolean(entityId, defaultValue = false) {
    const state = this.getEntityState(entityId);
    return state ? state.state === 'on' : defaultValue;
  }

  /**
   * Get entity state value as number
   * @param {string} entityId - Entity ID
   * @param {number} defaultValue - Default value if entity not found or invalid
   * @returns {number} Entity state as number
   */
  getEntityStateAsNumber(entityId, defaultValue = 0) {
    const state = this.getEntityState(entityId);
    if (!state) return defaultValue;

    const value = parseFloat(state.state);
    return isNaN(value) ? defaultValue : value;
  }

  // ========== MESSAGE BROKER INTEGRATION ==========

  /**
   * Connected callback - setup message broker and lifecycle
   */
  connectedCallback() {
    console.log(`🔗 ${this.constructor.name}: Component connected to DOM`);

    // Setup message broker integration
    this._setupMessageBroker();
  }

  /**
   * Disconnected callback - cleanup
   */
  disconnectedCallback() {
    console.log(`🧹 ${this.constructor.name}: Cleaning up component`);

    // Clean up message broker
    this._cleanupMessageBroker();

    // Clean up pending requests
    this._pendingRequests.clear();

    // Clean up HASS load timeout
    if (this._hassLoadTimeout) {
      clearTimeout(this._hassLoadTimeout);
      this._hassLoadTimeout = null;
    }

    // Clean up HASS ready listener
    if (this._hassReadyListener) {
      this._hassReadyListener();
      this._hassReadyListener = null;
    }

    if (this._featureReadyUnsub) {
      this._featureReadyUnsub();
      this._featureReadyUnsub = null;
    }

    // Reset state
    this._initialStateLoaded = false;
    this._rendered = false;
    this._commandInProgress = false;
    this._previousStates = {};
    this._hassLoaded = false;
  }

  _ensureFeatureReadyLoaded() {
    if (!this._hass?.connection) {
      return;
    }

    const featureId = this.getFeatureName();
    window.ramsesExtras = window.ramsesExtras || {};
    window.ramsesExtras.featureReady = window.ramsesExtras.featureReady || {};
    window.ramsesExtras._featureReadyPromises = window.ramsesExtras._featureReadyPromises || {};

    if (window.ramsesExtras.featureReady[featureId] === true) {
      this._featureReady = true;
      return;
    }

    if (!window.ramsesExtras._featureReadyPromises[featureId]) {
      window.ramsesExtras._featureReadyPromises[featureId] = callWebSocket(this._hass, {
        type: 'ramses_extras/default/get_feature_ready',
        feature_id: featureId,
      })
        .then((result) => {
          const ready = result?.ready === true;
          window.ramsesExtras.featureReady[featureId] = ready;
          if (ready) {
            this._featureReady = true;
            this.clearUpdateThrottle();
            this._checkAndLoadInitialState();
            this.render();
          } else {
            this._subscribeFeatureReady();
          }
        })
        .catch((error) => {
          console.warn('⚠️ Failed to query feature readiness:', error);
          this._subscribeFeatureReady();
        });
    }

    this._subscribeFeatureReady();
  }

  _subscribeFeatureReady() {
    if (this._featureReadyUnsub || !this._hass?.connection) {
      return;
    }

    const featureId = this.getFeatureName();
    try {
      this._featureReadyUnsub = this._hass.connection.subscribeEvents((event) => {
        const readyFeatureId = event?.data?.feature_id;
        if (readyFeatureId !== featureId) {
          return;
        }

        window.ramsesExtras = window.ramsesExtras || {};
        window.ramsesExtras.featureReady = window.ramsesExtras.featureReady || {};
        window.ramsesExtras.featureReady[featureId] = true;

        this._featureReady = true;
        this.clearUpdateThrottle();
        this._checkAndLoadInitialState();
        this.render();

        if (this._featureReadyUnsub) {
          this._featureReadyUnsub();
          this._featureReadyUnsub = null;
        }
      }, 'ramses_extras_feature_ready');
    } catch (error) {
      console.warn('⚠️ Failed to subscribe to feature ready events:', error);
    }
  }

  /**
   * Setup message broker integration
   */
  _setupMessageBroker() {
    if (!this._config?.device_id) return;

    this._messageCodes = this.getMessageCodes();
    if (this._messageCodes.length === 0) return;

    try {
      this._messageBroker = getRamsesMessageBroker();
      this._messageBroker.addListener(this, this._config.device_id, this._messageCodes);
      console.log(`📡 ${this.constructor.name}: Registered for message codes:`, this._messageCodes);
    } catch (error) {
      console.warn(`⚠️ ${this.constructor.name}: Failed to setup message broker:`, error);
    }
  }

  /**
   * Cleanup message broker integration
   */
  _cleanupMessageBroker() {
    if (this._messageBroker && this._config?.device_id) {
      try {
        this._messageBroker.removeListener(this, this._config.device_id);
        console.log(`🧹 ${this.constructor.name}: Removed from message broker`);
      } catch (error) {
        console.warn(`⚠️ ${this.constructor.name}: Error cleaning up message broker:`, error);
      }
    }
    this._messageBroker = null;
    this._messageCodes = [];
  }

  // ========== REGISTRATION HELPERS ==========

  /**
   * Register custom element
   */
  static registerElement() {
    const tagName = this.getTagName();

    if (!customElements.get(tagName)) {
      customElements.define(tagName, this);
      console.log(`✅ ${this.name}: Custom element '${tagName}' defined successfully`);
    } else {
      console.log(`⚠️ ${this.name}: Custom element '${tagName}' already exists`);
    }
  }

  /**
   * Register with Home Assistant custom cards
   */
  static registerCustomCard() {
    window.customCards = window.customCards || [];

    const cardInfo = this.getCardInfo();

    // Register with clean type name (no custom: prefix for internal registration)
    // The custom: prefix is only used in Lovelace YAML configuration
    const customCardInfo = {
      ...cardInfo,
      type: cardInfo.type  // No custom: prefix here - HA adds it in YAML usage
    };

    const existingCard = window.customCards.find(card => card.type === customCardInfo.type);

    if (!existingCard) {
      window.customCards.push(customCardInfo);
      console.log(`✅ ${this.name}: Registered with HA custom cards:`, customCardInfo.type);
    } else {
      console.log(`⚠️ ${this.name}: Custom card '${customCardInfo.type}' already registered`);
    }
  }

  /**
   * Get tag name for this card
   * @returns {string} Tag name (kebab-case)
   */
  static getTagName() {
    // Convert class name to kebab-case
    return this.name.replace(/([A-Z])/g, '-$1').toLowerCase().replace(/^-/, '');
  }

  /**
   * Get card info for HA registration
   * Override this method to customize card registration info
   * @returns {Object} Card registration info
   */
  static getCardInfo() {
    return {
      type: this.getTagName(),
      name: this.name,
      description: `${this.name} for Ramses Extras`,
      preview: true,
      documentationURL: 'https://github.com/wimpie70/ramses_extras',
    };
  }

  /**
   * Complete registration (custom element + HA custom card)
   */
  static register() {
    this.registerElement();
    this.registerCustomCard();

    // Ensure the card is properly registered with additional verification
    this.ensureRegistration();
  }

  /**
   * Ensure card registration with additional verification (no duplicate registration)
   */
  static ensureRegistration() {
    try {
      // Get card info
      const cardInfo = this.getCardInfo();

      // Ensure customCards array exists
      if (!window.customCards) {
        window.customCards = [];
      }

      // Final verification - only check, don't register again
      const verifiedCard = window.customCards.find(card => card.type === cardInfo.type);
      if (verifiedCard) {
        console.log(`✅ ${this.name}: Registration verified successfully for type: ${cardInfo.type}`);
      } else {
        console.error(`❌ ${this.name}: Failed to verify registration for type: ${cardInfo.type}`);
      }

    } catch (error) {
      console.error(`❌ ${this.name}: Error during registration verification:`, error);
    }
  }

  // ========== CONVENIENCE METHODS ==========

  /**
   * Get configuration element
   * @returns {HTMLElement|null} Configuration element
   */
  static getConfigElement() {
    // Default implementation returns null - override in subclasses
    return null;
  }

  /**
   * Get stub configuration for editor
   * @returns {Object} Stub configuration
   */
  static getStubConfig() {
    return {
      type: `custom:${this.getTagName()}`,
      device_id: '',
      name: this.name.replace('Card', '')
    };
  }

  /**
   * Check if translations are loaded
   * @returns {boolean} True if translations are loaded
   */
  hasTranslations() {
    return this._translationsLoaded;
  }

  /**
   * Get device display name
   * @returns {string} Device display name
   */
  getDeviceDisplayName() {
    const deviceId = this._config?.device_id || 'Unknown Device';
    const deviceName = this._config?.name || this.constructor.name;

    return `${deviceName} (${deviceId})`;
  }

  /**
   * Check if the card has a valid configuration for rendering
   * This method can be called in render() to check if the card is ready to be displayed
   * @returns {boolean} True if card has valid configuration
   */
  hasValidConfig() {
    // Check for required device_id - cards that need device_id should override this method
    // to add their specific validation logic
    return true;
  }

  /**
   * Get configuration error message for display
   * Override this method in subclasses to provide specific error messages
   * @returns {string} Error message to display when configuration is invalid
   */
  getConfigErrorMessage() {
    return 'Configuration is required. Please configure this card to use it.';
  }

  /**
   * Render configuration error message
   * This method can be called in render() when hasValidConfig() returns false
   */
  renderConfigError() {
    this.shadowRoot.innerHTML = `
      <ha-card>
        <div style="padding: 16px; text-align: center; color: #666;">
          <ha-icon icon="mdi:alert-outline"></ha-icon>
          <div style="margin-top: 8px;">
            Configuration Required
          </div>
          <div style="font-size: 12px; margin-top: 4px; opacity: 0.8;">
            ${this.getConfigErrorMessage()}
          </div>
        </div>
      </ha-card>
    `;
  }

  renderHassInitializing() {
    this.shadowRoot.innerHTML = `
      <ha-card>
        <div style="padding: 16px; text-align: center; color: #666;">
          <ha-icon icon="mdi:progress-clock"></ha-icon>
          <div style="margin-top: 8px;">
            Home Assistant is initializing
          </div>
          <div style="font-size: 12px; margin-top: 4px; opacity: 0.8;">
            Please wait until startup completes
          </div>
        </div>
      </ha-card>
    `;
  }

  renderFeatureInitializing() {
    this.shadowRoot.innerHTML = `
      <ha-card>
        <div style="padding: 16px; text-align: center; color: #666;">
          <ha-icon icon="mdi:progress-clock"></ha-icon>
          <div style="margin-top: 8px;">
            Ramses Extras is initializing
          </div>
          <div style="font-size: 12px; margin-top: 4px; opacity: 0.8;">
            Waiting for feature startup to complete
          </div>
        </div>
      </ha-card>
    `;
  }
}
