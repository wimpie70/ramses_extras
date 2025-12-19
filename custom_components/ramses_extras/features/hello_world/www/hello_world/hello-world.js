/* eslint-disable no-console */

// Import the base card class (matching working hvac_fan_card pattern)
import { RamsesBaseCard } from '/local/ramses_extras/helpers/ramses-base-card.js';

// Import the editor component
import './hello-world-editor.js';

// Import card styles and templates following hvac_fan_card pattern
import { CARD_STYLE } from './card-styles.js';
import { createCardContent } from './templates/card-templates.js';

/**
 * Helloworld - Simple demonstration card for Ramses Extras
 *
 * This card demonstrates the capabilities of the RamsesBaseCard framework.
 * It shows how to create a simple card with:
 * - Basic configuration (device_id, display options)
 * - Entity mapping via WebSocket
 * - State management and rendering
 * - Interactive controls
 */
class HelloWorld extends RamsesBaseCard {
  constructor() {
    super();

    // Helloworld-specific state
    this._previousSwitchState = null;
    this._previousSensorState = null;
    this._entityMappings = null;
    this._cachedEntities = null; // Cache for getRequiredEntities
    this._clickHandler = null; // Store click handler for proper cleanup
  }

  // ========== IMPLEMENT REQUIRED ABSTRACT METHODS ==========

  /**
   * Get card size for Home Assistant layout
   * @returns {number} Card size
   */
  getCardSize() {
    return this._config?.compact_view ? 1 : 2;
  }

  static getConfigElement() {
    try {
      if (typeof window.HelloworldEditor === 'undefined') {
        console.error('HelloworldEditor is not defined on window');
        return null;
      }
      return document.createElement('hello-world-editor');
    } catch (error) {
      console.error('Error creating config element:', error);
      return null;
    }
  }

  static getStubConfig() {
    return {
      type: `custom:${this.getTagName()}`,
      ...this.prototype.getDefaultConfig(),
    };
  }

  /**
   * Get configuration element for HA editor
   * @returns {HTMLElement|null} Configuration element
   */
  getConfigElement() {
    try {
      // Ensure the editor is available before creating it (similar to hvac_fan_card)
      if (typeof window.HelloworldEditor === 'undefined') {
        console.error('HelloworldEditor is not defined on window');
        return null;
      }
      return document.createElement('hello-world-editor');
    } catch (error) {
      console.error('Error creating config element:', error);
      return null;
    }
  }

  /**
   * Main rendering method
   */
  render() {
    if (!this._config || !this._hass) {
      if (!this._rendered) {
        this.shadowRoot.innerHTML = `
          <ha-card>Card not configured</ha-card>
        `;
        this._rendered = true;
      }
      return;
    }

    // Check if the hello_world feature is enabled
    // If not enabled, show a disabled message instead of loading entities
    const featureEnabled = this.isFeatureEnabled();

    // Feature state may be loading (null) while the base card fetches flags via WebSocket
    if (featureEnabled === null) {
      return;
    }

    if (featureEnabled === false) {
      if (!this._rendered) {
        this.shadowRoot.innerHTML = `
          <ha-card>
            <div style="padding: 16px; text-align: center; color: #666;">
              <ha-icon icon="mdi:information-outline"></ha-icon>
              <div style="margin-top: 8px;">
                Hello World feature is disabled
              </div>
              <div style="font-size: 12px; margin-top: 4px; opacity: 0.8;">
                Enable the feature in Ramses Extras configuration to use this card
              </div>
            </div>
          </ha-card>
        `;
        this._rendered = true;
      }
      return;
    }

    // Don't render until translations are loaded
    if (!this.hasTranslations()) {
      return;
    }

    // Use base class validation check
    if (!this.hasValidConfig()) {
      this.renderConfigError();
      return;
    }

    // Use feature-centric design to get entity IDs (same as getRequiredEntities)
    const deviceId = this._config?.device_id;
    let switchEntityId = this._config?.switchEntityId;
    let sensorEntityId = this._config?.sensorEntityId;

    // If entity IDs not in config, build them using the same logic as getRequiredEntities
    if (!switchEntityId || !sensorEntityId) {
      if (deviceId) {
        switchEntityId = this.buildEntityId('switch', 'hello_world_switch');
        sensorEntityId = this.buildEntityId('binary_sensor', 'hello_world_status');
      }
    }

    // Get current states from HA - always use HA as source of truth
    const switchStateObj = this.getEntityState(switchEntityId);
    const sensorStateObj = this.getEntityState(sensorEntityId);

    // Only use the state if entities exist and are available
    const switchState = switchStateObj ? switchStateObj.state === 'on' : null;
    const sensorState = sensorStateObj ? sensorStateObj.state === 'on' : null;

    this._previousSwitchState = switchState;
    this._previousSensorState = sensorState;

    const deviceDisplay = this.getDeviceDisplayName();

    // Use template following hvac_fan_card pattern
    const templateData = {
      deviceDisplay,
      switchState,
      sensorState,
      switchAvailable: switchState !== null,
      sensorAvailable: sensorState !== null,
      showStatus: this._config.show_status,
      translator: this
    };

    const cardHtml = createCardContent(templateData);

    // Optimize: Only re-render if not already rendered or if we need to rebuild the entire structure
    if (!this._rendered) {
      this.shadowRoot.innerHTML = `
        <!DOCTYPE html>
        <html>
        <head>
          <style>${CARD_STYLE}</style>
        </head>
        <body>
          ${cardHtml}
        </body>
        </html>
      `;
      this._rendered = true;

      // Attach event listeners after initial DOM update
      this._attachEventListeners();
    } else {
      // Optimized re-render: Only update the button text and class, and sensor status
      // This avoids rebuilding the entire DOM structure
      const buttonElement = this.shadowRoot?.querySelector('#helloWorldButton');
      const statusDiv = this.shadowRoot?.querySelector('.status');
      const sensorStatusDiv = this.shadowRoot?.querySelector('.binary-sensor-status');

      if (buttonElement) {
        buttonElement.textContent = switchState ? 'TURN OFF' : 'TURN ON';
        buttonElement.className = `toggle-button ${switchState ? 'on' : 'off'}`;
      }

      if (statusDiv) {
        const statusText = switchState ? 'ON' : 'OFF';
        statusDiv.innerHTML = `Status: ${statusText}`;
      }

      if (sensorStatusDiv) {
        const sensorText = sensorState ? 'ON' : 'OFF';
        const sensorPrefix = this.t('ui.card.hello_world.binary_sensor_changed_by_automation');
        sensorStatusDiv.textContent = `${sensorPrefix} ${sensorText}`;
      }
    }
  }

  // ========== OVERRIDE OPTIONAL METHODS ==========

  /**
   * Check if the card has a valid configuration for rendering
   * @returns {boolean} True if card has valid configuration
   */
  hasValidConfig() {
    return this._config && this._config.device_id;
  }

  validateConfig(config) {
    return {
      valid: true,
      errors: [],
    };
  }

  /**
   * Get configuration error message for display
   * @returns {string} Error message to display when configuration is invalid
   */
  getConfigErrorMessage() {
    return 'Device ID is required. Please configure the card with a device_id to use this card.';
  }

  /**
   * Get default configuration
   * @returns {Object} Default configuration
   */
  getDefaultConfig() {
    return {
      name: 'Hello World Switch',
      show_device_id_only: false,
      show_name_only: false,
      show_both: true,
      show_status: true,
      compact_view: false
    };
  }

  /**
   * Get required entity configuration
   * @returns {Object} Required entities mapping
   */
  getRequiredEntities() {
    // Use cached entities if available to avoid unnecessary recalculation
    if (this._cachedEntities) {
      return this._cachedEntities;
    }

    // Use feature-centric design to construct entity IDs
    // This ensures we always have valid entity IDs to monitor
    const deviceId = this._config?.device_id;

    if (!deviceId) {
      console.warn('HelloWorld: getRequiredEntities - no device_id available');
      return {
        switch: undefined,
        sensor: undefined
      };
    }

    // Build entity IDs using the framework's buildEntityId method
    // This follows the feature-centric design pattern
    const switchEntityId = this.buildEntityId('switch', 'hello_world_switch');
    const sensorEntityId = this.buildEntityId('binary_sensor', 'hello_world_status');

    const entities = {
      switch: switchEntityId,
      sensor: sensorEntityId
    };

    // Cache the entities for future calls
    this._cachedEntities = entities;

    return entities;
  }

  /**
   * Get feature name for translation path resolution
   * Override the default to return the correct feature directory name
   * @returns {string} Feature name
   */
  getFeatureName() {
    return 'hello_world';
  }

  /**
   * Get card info for HA registration with proper display name
   * @returns {Object} Card registration info
   */
  static getCardInfo() {
    return {
      type: this.getTagName(),
      name: 'Hello World Card',
      description: 'A simple demonstration card for Ramses Extras Hello World feature',
      preview: true,
      documentationURL: 'https://github.com/wimpie70/ramses_extras',
    };
  }

  /**
   * Load initial state from backend
   */
  async _loadInitialState() {
    if (!this._hass || !this._config?.device_id) {
      return;
    }

    try {
      // Load entity mappings first
      await this._loadEntityMappings();

      // Force a render after entity mappings are loaded to ensure
      // getRequiredEntities() has the correct entity IDs
      this.render();

      // Then load initial state
      const result = await this._sendWebSocketCommand({
        type: 'ramses_extras/hello_world/get_switch_state',
        device_id: this._config.device_id
      }, `initial_state_${this._config.device_id}`);

      // Update previous states from WebSocket response (boolean values)
      this._previousSwitchState = result.switch_state;
      this._previousSensorState = result.binary_sensor_state;

      // Force another render with loaded state
      this.render();
    } catch (error) {
      console.warn('HelloWorld: Failed to load initial state:', error);
      this.render();
    }
  }

  // ========== HELLOWORLD CARD SPECIFIC METHODS ==========

  /**
   * Load entity mappings from backend
   */
  async _loadEntityMappings() {
    if (!this._hass || !this._config?.device_id) {
      return;
    }

    try {
      const result = await this._sendWebSocketCommand({
        type: 'ramses_extras/get_entity_mappings',
        device_id: this._config.device_id,
        feature_id: 'hello_world'
      }, `mappings_${this._config.device_id}`);

      if (result.mappings) {
        // Update config with retrieved entity mappings
        this._config.switchEntityId = result.mappings.switch_state;
        this._config.sensorEntityId = result.mappings.sensor_state;
        this._entityMappings = result.mappings;
      }
    } catch (error) {
      console.warn('HelloWorld: Failed to load entity mappings:', error);
    }
  }

  /**
   * Handle button click events
   * @param {Event} event - Click event
   */
  // eslint-disable-next-line no-unused-vars
  async _handleButtonClick(event) {
    // Prevent multiple simultaneous commands
    if (this.isCommandInProgress()) {
      return;
    }

    try {
      // Get current state from backend to ensure accuracy
      const currentStateResult = await this._sendWebSocketCommand({
        type: 'ramses_extras/hello_world/get_switch_state',
        device_id: this._config.device_id
      });

      const currentState = currentStateResult.switch_state || false;
      const newState = !currentState;

      // Send WebSocket command to toggle the switch state
      await this._sendSwitchCommand(newState);
    } catch (error) {
      console.error('HelloWorld: Failed to handle button click:', error);
      // Re-throw to let the framework handle it
      throw error;
    }
  }

  /**
   * Send WebSocket command to toggle switch
   * @param {boolean} state - New switch state
   */
  async _sendSwitchCommand(state) {
    this._setCommandInProgress(true);

    try {
      const result = await this._sendWebSocketCommand({
        type: 'ramses_extras/hello_world/toggle_switch',
        device_id: this._config.device_id,
        state: state
      });

      if (!result.success) {
        console.error('HelloWorld: Command failed:', result);
        this._revertSwitchToActualState();
      } else {
        // Clear update throttle and previous states to allow immediate updates when entity states change
        this.clearUpdateThrottle();
        this.clearPreviousStates();

        // Force a render to update the UI with current Home Assistant states
        // This ensures we show the actual state, not cached values
        this.render();

        // The base card's entity change detection will also handle updates
        // when Home Assistant propagates the state change
      }
    } catch (error) {
      console.error('HelloWorld: WebSocket command error:', error);
      this._revertSwitchToActualState();
    } finally {
      this._setCommandInProgress(false);
    }
  }

  /**
   * Revert switch to actual state from HA
   */
  _revertSwitchToActualState() {
    const switchEntityId = this._config.switchEntityId;
    const actualState = this.getEntityStateAsBoolean(switchEntityId, false);

    // Find the switch element and update it
    const switchElement = this.shadowRoot?.getElementById('helloWorldSwitch');
    if (switchElement) {
      switchElement.checked = actualState;
    }
  }

  /**
   * Get device display name based on configuration
   * @returns {string} Device display name
   */
  getDeviceDisplayName() {
    const deviceId = this._config.device_id;
    const deviceName = this._config.name || 'Hello World Switch';

    if (this._config.show_device_id_only) {
      return deviceId;
    }

    if (this._config.show_name_only) {
      return deviceName;
    }

    // Default: show both
    return `${deviceName} (${deviceId})`;
  }

  /**
   * Attach event listeners after DOM update
   */
  _attachEventListeners() {
    // Remove any existing listeners to prevent duplicates
    this._removeEventListeners();

    const buttonElement = this.shadowRoot?.getElementById('helloWorldButton');

    if (buttonElement) {
      // Store the click handler for potential cleanup
      this._clickHandler = (event) => {
        this._handleButtonClick(event);
      };

      buttonElement.addEventListener('click', this._clickHandler);
    }
  }

  /**
   * Remove event listeners to prevent duplicates
   */
  _removeEventListeners() {
    const buttonElement = this.shadowRoot?.getElementById('helloWorldButton');
    if (buttonElement && this._clickHandler) {
      buttonElement.removeEventListener('click', this._clickHandler);
    }
    this._clickHandler = null;
  }
}

// Register the card using the base class registration
HelloWorld.register();

// Export for testing purposes
export { HelloWorld };
