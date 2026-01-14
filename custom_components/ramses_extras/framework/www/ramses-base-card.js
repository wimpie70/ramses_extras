/* global customElements */
/* global HTMLElement */
/* global setTimeout */
/* global clearTimeout */

// Import framework utilities
import * as logger from './logger.js';
import { SimpleCardTranslator } from './card-translations.js';
import { callWebSocket, entityExists, getEntityState, buildEntityId } from './card-services.js';
import { getRamsesMessageBroker } from './ramses-message-broker.js';
import { getFeatureTranslationPath } from './paths.js';
/**
 * window.ramsesExtras = window.ramsesExtras || {};
 * window.ramsesExtras.debug = true;
 */
const debugLog = (...args) => logger.debug(...args);

const _ensureOptionsUpdatesSubscribed = (hass) => {
  if (!hass?.connection) {
    return;
  }

  window.ramsesExtras = window.ramsesExtras || {};

  if (typeof window.ramsesExtras._optionsUpdatesUnsub === 'function') {
    return;
  }

  try {
    window.ramsesExtras._optionsUpdatesUnsub = hass.connection.subscribeEvents((event) => {
      const payload = event?.data || {};

      window.ramsesExtras = window.ramsesExtras || {};
      if (payload.enabled_features) {
        window.ramsesExtras.features = payload.enabled_features;
      }
      if (payload.device_feature_matrix) {
        window.ramsesExtras.deviceFeatureMatrix = payload.device_feature_matrix;
      }
      if (typeof payload.frontend_log_level === 'string' && payload.frontend_log_level) {
        window.ramsesExtras.frontendLogLevel = payload.frontend_log_level;
        window.ramsesExtras.debug = payload.frontend_log_level === 'debug';
      } else if (typeof payload.debug_mode === 'boolean') {
        window.ramsesExtras.debug = payload.debug_mode;
        if (payload.debug_mode === true) {
          window.ramsesExtras.frontendLogLevel = 'debug';
        }
      }
      if (typeof payload.log_level === 'string' && payload.log_level) {
        window.ramsesExtras.logLevel = payload.log_level;
      }
      if (typeof payload.cards_enabled === 'boolean') {
        window.ramsesExtras.cardsEnabled = payload.cards_enabled;
      }

      try {
        const event = document.createEvent('Event');
        event.initEvent('ramses_extras_options_updated', false, false);
        event.detail = payload;
        window.dispatchEvent(event);
      } catch (error) {
        logger.warn('⚠️ Failed to dispatch ramses_extras_options_updated event:', error);
      }
    }, 'ramses_extras_options_updated');
  } catch (error) {
    logger.warn('⚠️ Failed to subscribe to options updated events:', error);
  }
};

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
    this._translations = null;

    this._initialStateLoaded = false;
    this._rendered = false;

    // Translation support
    this.translator = null;
    this._translationsLoaded = false;

    // WebSocket and communication
    this._pendingRequests = new Map();
    this._commandInProgress = false;

    this._onceKeys = new Set();

    this._backendReadyPromise = null;

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

    this._cardsEnabled = false;
    this._cardsEnabledUnsub = null;

    this._featureConfigLoadAttached = false;
    this._cachedEntities = null; // Cache for getRequiredEntities
    this._requiredEntitiesPromise = null;

    this._optionsUpdatedListenerAttached = false;
    this._optionsUpdatedListener = null;

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
    return null;
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
   * Get required entity configuration with caching
   * Default implementation loads entity mappings from feature constants
   * Override this method for custom entity logic
   * @returns {Object} Required entities mapping
   */
  getRequiredEntities() {
    if (this._cachedEntities) {
      return this._cachedEntities;
    }
    this._ensureRequiredEntitiesLoaded();
    return {};
  }

  _ensureRequiredEntitiesLoaded() {
    if (this._cachedEntities) {
      return;
    }
    if (this._requiredEntitiesPromise) {
      return;
    }
    if (!this._hass || !this._config?.device_id) {
      return;
    }

    this._requiredEntitiesPromise = this._loadRequiredEntities()
      .catch(() => {})
      .finally(() => {
        this._requiredEntitiesPromise = null;
      });
  }

  async _loadRequiredEntities() {
    const deviceId = this._config?.device_id;
    if (!deviceId) {
      return;
    }

    try {
      const result = await this._sendWebSocketCommand({
        type: 'ramses_extras/get_entity_mappings',
        device_id: deviceId,
        feature_id: this.getFeatureName()
      }, `entity_mappings_${deviceId}`);

      if (result.mappings) {
        this._cachedEntities = result.mappings;

        // Now that we have entity IDs, reset state tracking and re-render.
        // This ensures shouldUpdate() will start using entity-based change detection.
        this.clearPreviousStates();
        this.clearUpdateThrottle();
        if (this.isConnected) {
          this.render();
        }
      }
    } catch (error) {
      logger.warn(
        `${this.constructor.name}: Failed to load entity mappings:`,
        error
      );
    }
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
   * Called when card is disconnected from DOM
   * Override this method for card-specific cleanup
   */
  _onDisconnected() {
    // Default implementation - override for card-specific cleanup
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
          this._ensureCardsEnabledLoaded();
          this.render();
        }
      }
    } catch (error) {
      logger.warn(
        `⚠️ Failed to initialize translations for ${this.constructor.name}:`,
        error
      );
      this._translationsLoaded = true; // Continue without translations
    }
  }

  _attachOptionsUpdatedListener() {
    if (this._optionsUpdatedListenerAttached) {
      return;
    }

    this._optionsUpdatedListener = () => {
      try {
        if (window.ramsesExtras?.cardsEnabled === true) {
          this._cardsEnabled = true;
        }

        this.clearUpdateThrottle();
        this.render();
      } catch (error) {
        logger.warn('⚠️ Failed to update after options change:', error);
      }
    };

    window.addEventListener('ramses_extras_options_updated', this._optionsUpdatedListener);
    this._optionsUpdatedListenerAttached = true;
  }

  _isHomeAssistantRunning() {
    return this._hass?.connected && this._hass?.config?.state === 'RUNNING';
  }

  _confirmBackendReady() {
    if (this._hassLoaded) {
      return;
    }
    if (!this._isHomeAssistantRunning()) {
      return;
    }
    if (!this._hass?.connection) {
      return;
    }
    if (this._backendReadyPromise) {
      return;
    }

    this._backendReadyPromise = callWebSocket(this._hass, {
      type: 'ramses_extras/default/get_cards_enabled',
    })
      .then(() => {
        this._hassLoaded = true;
        this._backendReadyPromise = null;
        this.render();
      })
      .catch(() => {
        this._backendReadyPromise = null;
        setTimeout(() => this._confirmBackendReady(), 1000);
      });
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
      debugLog(`Feature ${featureName} is enabled: unknown (loading)`);
      return null;
    }

    const isEnabled = window.ramsesExtras.features[featureName] === true;
    debugLog(`Feature ${featureName} is enabled: ${isEnabled}`);
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
            logger.warn(
              '⚠️ Failed to load Ramses Extras feature configuration via WebSocket:',
              error
            );
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
          logger.warn('⚠️ Failed to re-render after feature config load:', error);
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
    // Basic validation of the config object itself
    if (!config) {
      this._config = {};
      return;
    }

    try {
      const oldDeviceId = this._config?.device_id;
      const deviceId = config.device_id ? config.device_id.replace(/_/g, ':') : null;

      // Process configuration
      this._config = {
        ...this.getDefaultConfig(),
        ...config,
        device_id: deviceId, // Ensure normalized ID wins
      };

      // Reset state if device changed
      if (deviceId !== oldDeviceId) {
        this._rendered = false;
        this._initialStateLoaded = false;
        this._previousStates = {};
        this._onceKeys = new Set();
        this._cachedEntities = null;
        this.clearUpdateThrottle();
      }

      // Load initial state if hass is available
      if (this._hass) {
        if (!this._isHomeAssistantRunning()) {
          this.renderHassInitializing();
        } else {
          this._checkAndLoadInitialState();
          this.render();
        }
      }
    } catch (error) {
      logger.error(`❌ ${this.constructor.name}: Configuration error:`, error);
      // We don't throw here to allow the card to stay in a predictable state
      // and let render() show the config error if needed.
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

      // During restart/reconnect the websocket connection object changes.
      // Keep the card in an initializing state until the HA connection is ready.
      if (connectionChanged) {
        this._hassLoaded = false;
        this.clearUpdateThrottle();
        this.render();
      }

      if (!this._isHomeAssistantRunning()) {
        this._hassLoaded = false;
        this.clearUpdateThrottle();
        this.renderHassInitializing();
        return;
      }

      _ensureOptionsUpdatesSubscribed(hass);

      // Ensure we latch startup until HA websocket finishes initial sync.
      // Some restarts keep the same connection object, so don't rely solely on
      // connectionChanged to attach the ready listener.
      const needsReadyLatch = !this._hassLoaded;

      // Temporarily disable cards_enabled check to get HVAC card working
      // TODO: Debug cards_enabled latch timing issue
      // if (!this._cardsEnabled) {
      //   this._ensureCardsEnabledLoaded();
      //   if (!this._cardsEnabled) {
      //     this._hassLoaded = false;
      //     this.clearUpdateThrottle();
      //     this.renderFeatureInitializing();
      //     return;
      //   }
      // }

      // Note: do not set _hassLoaded = true here.
      // We wait for the websocket 'ready' event (or timeout) to avoid
      // cards becoming interactive while HA is still initializing.

      // Clear any existing timeout
      if (connectionChanged && this._hassLoadTimeout) {
        clearTimeout(this._hassLoadTimeout);
        this._hassLoadTimeout = null;
      }

      // Clear any existing ready listener
      if (connectionChanged && typeof this._hassReadyListener === 'function') {
        this._hassReadyListener();
        this._hassReadyListener = null;
      }

      // Listen for the HASS ready event to mark when HASS is fully loaded.
      // Do this whenever we need the latch, not only on connectionChanged.
      if (needsReadyLatch && hass && hass.connection && !this._hassReadyListener) {
        this._hassReadyListener = hass.connection.addEventListener('ready', () => {
          this._hassLoaded = true;
          debugLog(
            `✅ ${this.constructor.name}: HASS ready event received, allowing updates and rendering`
          );

          if (typeof this._hassReadyListener === 'function') {
            this._hassReadyListener();
          }
          this._hassReadyListener = null;

          // After HASS is ready, load initial state and render
          this._loadInitialState();
          this.render();
        });
      }

      // If we missed the 'ready' event (e.g. after a hard refresh), confirm readiness
      // by probing a lightweight backend websocket command.
      if (!this._hassLoaded) {
        this._confirmBackendReady();
      }

      // Fallback timeout in case ready event doesn't fire
      if (needsReadyLatch && !this._hassLoadTimeout) {
        this._hassLoadTimeout = setTimeout(() => {
          if (!this._hassLoaded) {
            this._hassLoaded = true;
            debugLog(
              `⚠️ ${this.constructor.name}: HASS ready timeout reached after 2 minutes, assuming HASS is loaded`
            );

            this._hassLoadTimeout = null;

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
      debugLog(`🔍 ${this.constructor.name}: shouldUpdate - missing hass or config`);
      return false;
    }

    // Wait until HASS is fully loaded to prevent excessive updates on restart
    if (!this._hassLoaded) {
      return false;
    }

    // Throttle updates to prevent excessive calls
    const now = Date.now();
    if (now - this._lastUpdateTime < this._updateThrottleTime) {
      debugLog(`🔍 ${this.constructor.name}: shouldUpdate - throttled, skipping update check`);
      return false;
    }

    const requiredEntities = this.getRequiredEntities();

    if (Object.keys(requiredEntities).length === 0) {
      // If we're using the base implementation and entities haven't loaded yet,
      // avoid treating this as "no entities" (which would cause render thrash).
      if (
        this.getRequiredEntities === RamsesBaseCard.prototype.getRequiredEntities &&
        !this._cachedEntities
      ) {
        return false;
      }

      // No specific entities to monitor, always update
      debugLog(`🔍 ${this.constructor.name}: shouldUpdate - no required entities, always update`);
      return true;
    }

    // Check if any monitored entities have changed
    const hasChanges = Object.entries(requiredEntities).some(([key, entityId]) => {
      if (!entityId) {
        debugLog(`🔍 ${this.constructor.name}: shouldUpdate - entity ${key} is null/undefined`);
        return false;
      }

      const oldState = this._previousStates[entityId];
      const newState = this._hass.states[entityId];
      this._previousStates[entityId] = newState;

      const changed = oldState !== newState;
      debugLog(`🔍 ${this.constructor.name}: shouldUpdate - entity ${entityId}:`, {
        oldState: oldState?.state,
        newState: newState?.state,
        changed
      });

      return changed;
    });

    debugLog(`🔍 ${this.constructor.name}: shouldUpdate result:`, hasChanges);

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
      this._ensureRequiredEntitiesLoaded();
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
      debugLog(`🔄 ${this.constructor.name}: Loading initial state for device:`, this._config.device_id);
    } catch (error) {
      logger.warn(`⚠️ ${this.constructor.name}: Failed to load initial state:`, error);
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
      logger.error(`❌ ${this.constructor.name}: WebSocket command failed:`, error);
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

  _runOnce(key, fn) {
    if (this._onceKeys.has(key)) {
      return;
    }

    this._onceKeys.add(key);
    return fn();
  }

  _maybeRunOnceWhenReady(key, fn) {
    if (!this._hass || !this._config) {
      return;
    }
    if (!this._isHomeAssistantRunning()) {
      return;
    }
    if (!this._cardsEnabled) {
      return;
    }
    if (!this.isConnected) {
      return;
    }

    return this._runOnce(key, fn);
  }

  async _withElementFeedback(element, fn, successMs = 2000) {
    if (element) {
      element.classList.add('loading');
      element.classList.remove('success', 'error');
    }

    try {
      const result = await fn();
      if (element) {
        element.classList.remove('loading');
        element.classList.add('success');
        setTimeout(() => element.classList.remove('success'), successMs);
      }
      return result;
    } catch (error) {
      if (element) {
        element.classList.remove('loading');
        element.classList.add('error');
      }
      throw error;
    }
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
    if (!this._config?.device_id) return '';
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
    debugLog(`🔗 ${this.constructor.name}: Component connected to DOM`);

    // Setup message broker integration
    this._setupMessageBroker();

    try {
      this._onConnected();
    } catch (error) {
      logger.warn(`⚠️ ${this.constructor.name}: Error in _onConnected():`, error);
    }

    this._attachOptionsUpdatedListener();
  }

  _onConnected() {}

  /**
   * Disconnected callback - cleanup
   */
  disconnectedCallback() {
    debugLog(`🧹 ${this.constructor.name}: Cleaning up component`);

    try {
      this._onDisconnected();
    } catch (error) {
      logger.warn(`⚠️ ${this.constructor.name}: Error in _onDisconnected():`, error);
    }

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

    if (typeof this._cardsEnabledUnsub === 'function') {
      this._cardsEnabledUnsub();
    }
    this._cardsEnabledUnsub = null;

    if (typeof this._featureReadyUnsub === 'function') {
      this._featureReadyUnsub();
    }
    this._featureReadyUnsub = null;

    if (this._optionsUpdatedListenerAttached && this._optionsUpdatedListener) {
      window.removeEventListener(
        'ramses_extras_options_updated',
        this._optionsUpdatedListener
      );
    }
    this._optionsUpdatedListenerAttached = false;
    this._optionsUpdatedListener = null;

    // Reset state
    this._initialStateLoaded = false;
    this._rendered = false;
    this._commandInProgress = false;
    this._previousStates = {};
    this._hassLoaded = false;
  }

  _ensureCardsEnabledLoaded() {
    if (!this._hass?.connection) {
      return;
    }

    window.ramsesExtras = window.ramsesExtras || {};
    window.ramsesExtras._cardsEnabledPromise = window.ramsesExtras._cardsEnabledPromise || null;

    if (window.ramsesExtras.cardsEnabled === true) {
      this._cardsEnabled = true;
      return;
    }

    if (!window.ramsesExtras._cardsEnabledPromise) {
      window.ramsesExtras._cardsEnabledPromise = callWebSocket(this._hass, {
        type: 'ramses_extras/default/get_cards_enabled',
      })
        .then((result) => {
          const enabled = result?.cards_enabled === true;
          if (enabled) {
            window.ramsesExtras.cardsEnabled = true;
          }
          if (enabled) {
            this._cardsEnabled = true;
            this.clearUpdateThrottle();
            this._checkAndLoadInitialState();
            this.render();
          } else {
            this._subscribeCardsEnabled();
          }
        })
        .catch((error) => {
          logger.warn('⚠️ Failed to query cards_enabled:', error);
          this._subscribeCardsEnabled();
        })
        .finally(() => {
          if (window.ramsesExtras) {
            window.ramsesExtras._cardsEnabledPromise = null;
          }
        });
    } else {
      // If promise exists but we're not enabled yet, ensure we're subscribed
      if (!this._cardsEnabledUnsub) {
        this._subscribeCardsEnabled();
      }
    }
  }

  _subscribeCardsEnabled() {
    if (this._cardsEnabledUnsub || !this._hass?.connection) {
      return;
    }

    try {
      this._cardsEnabledUnsub = this._hass.connection.subscribeEvents(() => {
        // Prevent multiple renders when the event fires multiple times
        if (this._cardsEnabled) {
          return;
        }

        window.ramsesExtras = window.ramsesExtras || {};
        window.ramsesExtras.cardsEnabled = true;

        this._cardsEnabled = true;
        this.clearUpdateThrottle();
        this._checkAndLoadInitialState();
        this.render();
      }, 'ramses_extras_cards_enabled');
    } catch (error) {
      logger.warn('⚠️ Failed to subscribe to cards enabled events:', error);
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
      debugLog(`📡 ${this.constructor.name}: Registered for message codes:`, this._messageCodes);
    } catch (error) {
      logger.warn(`⚠️ ${this.constructor.name}: Failed to setup message broker:`, error);
    }
  }

  /**
   * Cleanup message broker integration
   */
  _cleanupMessageBroker() {
    if (this._messageBroker && this._config?.device_id) {
      try {
        this._messageBroker.removeListener(this, this._config.device_id);
        debugLog(`🧹 ${this.constructor.name}: Removed from message broker`);
      } catch (error) {
        logger.warn(`⚠️ ${this.constructor.name}: Error cleaning up message broker:`, error);
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
      debugLog(`✅ ${this.name}: Custom element '${tagName}' defined successfully`);
    } else {
      debugLog(`⚠️ ${this.name}: Custom element '${tagName}' already exists`);
    }
  }

  /**
   * Register with Home Assistant custom cards
   */
  static registerCustomCard() {
    window.customCards = window.customCards || [];

    // Use static getCardInfo during registration (hass not available yet)
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
      debugLog(`✅ ${this.name}: Registered with HA custom cards:`, customCardInfo.type);
    } else {
      debugLog(`⚠️ ${this.name}: Custom card '${customCardInfo.type}' already registered`);
    }
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
   * Get tag name for this card
   * @returns {string} Tag name (kebab-case)
   */
  static getTagName() {
    // Convert class name to kebab-case
    return this.name.replace(/([A-Z])/g, '-$1').toLowerCase().replace(/^-/, '');
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
        debugLog(`✅ ${this.name}: Registration verified successfully for type: ${cardInfo.type}`);
      } else {
        logger.error(`❌ ${this.name}: Failed to verify registration for type: ${cardInfo.type}`);
      }

    } catch (error) {
      logger.error(`❌ ${this.name}: Error during registration verification:`, error);
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

    if (this._config?.show_device_id_only === true) {
      return deviceId;
    }

    if (this._config?.show_name_only === true) {
      return deviceName;
    }

    if (this._config?.show_both === false) {
      return deviceName;
    }

    return `${deviceName} (${deviceId})`;
  }

  /**
   * Main render method with common validation and setup
   * Subclasses should implement _renderContent() for card-specific rendering
   */
  render() {
    // Basic validation
    if (!this._hass || !this._config) {
      return;
    }

    // Prevent interaction during HA restart / reconnect.
    // - hass.connected goes false while the websocket reconnects
    // - _hassLoaded stays false until the connection 'ready' event fires
    if (!this._isHomeAssistantRunning() || !this._hassLoaded) {
      this.renderHassInitializing();
      return;
    }

    // Don't render until translations are loaded
    if (!this.hasTranslations()) {
      return;
    }

    // Use feature-centric design to check if feature is enabled
    // Allow rendering when feature status is loading (null) but config is valid
    // Only show disabled message when feature is explicitly disabled (false)
    const featureEnabled = this.isFeatureEnabled();

    if (featureEnabled === false) {
      this.renderFeatureDisabled();
      return;
    }

    // Use subclass validation check
    if (!this.hasValidConfig()) {
      this.renderConfigError();
      return;
    }

    // Call subclass-specific rendering
    this._renderContent();
  }

  /**
   * Card-specific rendering method to be implemented by subclasses
   * This method is called after all common validation passes
   */
  _renderContent() {
    throw new Error('_renderContent() must be implemented by subclass');
  }

  /**
   * Check if the card has a valid configuration for rendering
   * This method can be called in render() to check if the card is ready to be displayed
   * @returns {boolean} True if card has valid configuration
   */
  hasValidConfig() {
    // Check for required device_id - cards that need device_id should override this method
    // to add their specific validation logic
    return Boolean(this._config?.device_id);
  }

  /**
   * Get configuration error message for display
   * Override this method in subclasses to provide specific error messages
   * @returns {string} Error message to display when configuration is invalid
   */
  getConfigErrorMessage() {
    return 'Device ID is required. Please configure the card with a device_id to use this card.';
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

  renderFeatureDisabled() {
    const featureName = this.getFeatureName();
    const featureDisplayName = featureName.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());

    this.shadowRoot.innerHTML = `
      <ha-card>
        <div style="padding: 16px; text-align: center; color: #666;">
          <ha-icon icon="mdi:toggle-switch-off"></ha-icon>
          <div style="margin-top: 8px;">
            ${featureDisplayName} Feature Disabled
          </div>
          <div style="font-size: 12px; margin-top: 4px; opacity: 0.8;">
            Enable this feature in Ramses Extras configuration
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
