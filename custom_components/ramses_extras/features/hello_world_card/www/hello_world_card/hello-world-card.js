/* eslint-disable no-console */
/* global customElements */
/* global HTMLElement */

// Hello World Card - Main card component
// Part of the Ramses Extra integration
// See https://github.com/wimpie70/ramses_extras for more information

// Import the editor component
import './hello-world-card-editor.js';

// Import reusable helpers using environment-aware path constants
import { callWebSocket } from '/local/ramses_extras/helpers/card-services.js';
import { getFeatureTranslationPath } from '/local/ramses_extras/helpers/paths.js';

// Import translation helper
import { SimpleCardTranslator } from '/local/ramses_extras/helpers/card-translations.js';

/**
 * Hello World Card using HTMLElement pattern (like hvac_fan_card)
 * to avoid external dependencies like 'lit'
 */
class HelloWorldCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: 'open' });
    this._hass = null;
    this._config = null;
    this._initialStateLoaded = false;
    this._pendingRequests = new Map(); // Track pending WebSocket requests
    this._previousSwitchState = null;
    this._previousSensorState = null;
    this._rendered = false;
    this._commandInProgress = false; // Prevent multiple simultaneous commands
    this.translator = null; // Translation support
    this._translationsLoaded = false; // Track if translations are loaded

    // Initialize translations
    this.initTranslations();
    // No event subscriptions needed - HA handles re-rendering automatically
  }

  // Initialize translations for this card
  async initTranslations() {
    this.translator = new SimpleCardTranslator('hello-world-card');
    // Use environment-aware path resolution like hvac_fan_card
    const translationPath = getFeatureTranslationPath('hello_world_card', 'en');
    await this.translator.init(translationPath.replace('/translations/en.json', ''));
    this._translationsLoaded = true;

    // Force re-render if we have config and hass ready
    if (this._config && this._hass) {
      this.render();
    }
  }

  // Helper method to get translated strings
  t(key, params = {}) {
    if (!this.translator || !this._translationsLoaded) {
      return key; // Fallback if translator not ready
    }
    return this.translator.t(key, params);
  }

  // Helper method to check if translation exists
  hasTranslation(key) {
    if (!this.translator || !this._translationsLoaded) {
      return false;
    }
    return this.translator.has(key);
  }

  static get properties() {
    return {
      config: {},
      _hass: {},
    };
  }

  set hass(hass) {
    this._hass = hass;
    this._checkAndLoadInitialState();

    // Re-render when hass changes (HA handles entity state updates automatically)
    if (this._config) {
      this.render();
    }
  }

  setConfig(config) {
    if (!config.device_id) {
      throw new Error('Device ID is required');
    }
    this._config = config;
    this._rendered = false; // Force re-render when config changes
    this._checkAndLoadInitialState();

    // Re-render when config changes
    if (this._hass) {
      this.render();
    }
  }

  _checkAndLoadInitialState() {
    // Only load initial state once when both hass and config are available
    if (this._hass && this._config && !this._initialStateLoaded) {
      console.log('🔄 HelloWorldCard: Both hass and config ready, loading initial state');
      this._loadInitialState();
      this._initialStateLoaded = true;
    }
  }

  get config() {
    return this._config;
  }

  getCardSize() {
    return this._config.compact_view ? 1 : 2;
  }

  static getConfigElement() {
    console.log('HelloWorldCard: Creating config element');

    // The editor should now be available due to the import statement
    const EditorClass = customElements.get('hello-world-card-editor');

    if (EditorClass) {
      console.log('HelloWorldCard: Using custom element class');
      const element = new EditorClass();
      console.log('HelloWorldCard: Config element created with custom class:', element);
      return element;
    }

    // Fallback: create basic element if custom element is not available
    console.warn('HelloWorldCard: Editor not available, creating basic element');
    return document.createElement('hello-world-card-editor');
  }

  // Static cache to avoid duplicate editor instances during development
  static _cachedEditor = null;

  static getCachedEditor() {
    if (!this._cachedEditor || !document.contains(this._cachedEditor)) {
      console.log('🔄 HelloWorldCard: Creating new editor instance');
      this._cachedEditor = this.getConfigElement();
    } else {
      console.log('📦 HelloWorldCard: Reusing cached editor instance');
    }
    return this._cachedEditor;
  }

  static getStubConfig() {
    return {
      type: 'custom:hello-world-card',
      device_id: '',
      name: 'Hello World Switch',
      show_device_id_only: false,
      show_name_only: false,
      show_both: true,
      show_status: true,
      compact_view: false
    };
  }

  connectedCallback() {
    console.log('🔗 HelloWorldCard: Component connected to DOM');
  }

  disconnectedCallback() {
    console.log('🧹 HelloWorldCard: Cleaning up component');

    // Clean up pending requests
    this._pendingRequests.clear();
    // Reset state for next connection
    this._initialStateLoaded = false;
    this._rendered = false;
  }


  async _loadInitialState() {
    if (!this._hass || !this._config?.device_id) return;

    const deviceId = this._config.device_id;
    const requestKey = `initial_state_${deviceId}`;

    // Return existing pending request if one is already in progress
    if (this._pendingRequests.has(requestKey)) {
      console.log('📋 HelloWorldCard: Reusing existing request for device:', deviceId);
      return this._pendingRequests.get(requestKey);
    }

    console.log('🔄 HelloWorldCard: Loading initial state for device:', deviceId);

    // Create new request and track it
    const requestPromise = this._performInitialStateLoad(deviceId);
    this._pendingRequests.set(requestKey, requestPromise);

    try {
      await requestPromise;
    } finally {
      // Clean up the pending request when done
      this._pendingRequests.delete(requestKey);
    }
  }

  async _performInitialStateLoad(deviceId) {
    try {
      // Get initial state from WebSocket using framework helper
      const result = await callWebSocket(this._hass, {
        type: 'ramses_extras/hello_world/get_switch_state',
        device_id: deviceId
      });

      console.log('✅ HelloWorldCard: Initial state loaded:', { switch: result.switch_state, sensor: result.binary_sensor_state });
      // HA will automatically re-render when entity states are updated by the backend
    } catch (error) {
      console.warn('⚠️ HelloWorldCard: Failed to load initial state:', error);
    }
  }

  // eslint-disable-next-line no-unused-vars
  _handleButtonClick(event) {
    // Prevent multiple simultaneous commands
    if (this._commandInProgress) {
      console.log('HelloWorldCard: Command already in progress, ignoring duplicate click');
      return;
    }

    // Get current state and toggle it
    const deviceId = this._config.device_id;
    const switchEntityId = `switch.hello_world_switch_${deviceId.replace(':', '_')}`;
    const currentState = this._hass.states[switchEntityId]?.state === 'on';
    const newState = !currentState; // Toggle the current state

    console.log('HelloWorldCard: Button click detected, toggling from', currentState, 'to', newState);

    // Send WebSocket command to toggle the switch state
    this._sendSwitchCommand(newState);
  }

  async _sendSwitchCommand(state) {
    // Set flag to prevent multiple simultaneous commands
    this._commandInProgress = true;

    try {
      console.log('HelloWorldCard: Sending WebSocket command for state:', state);
      console.log('HelloWorldCard: Device ID:', this._config.device_id);
      console.log('HelloWorldCard: hass available:', !!this._hass);

      const result = await callWebSocket(this._hass, {
        type: 'ramses_extras/hello_world/toggle_switch',
        device_id: this._config.device_id,
        state: state
      });

      if (!result.success) {
        console.error('HelloWorldCard: Command failed:', result);
        // If the command failed, revert the switch state to match the actual entity state
        this._revertSwitchToActualState();
      } else {
        console.log('HelloWorldCard: Switch command successful, framework handles coordination');
        // Command was successful, but we still need to ensure our UI stays in sync
        // The backend will update the entity state, which will trigger a re-render
      }
    } catch (error) {
      console.error('HelloWorldCard: WebSocket command error:', error);
      // If there was an error, revert the switch state to match the actual entity state
      this._revertSwitchToActualState();
    } finally {
      // Always clear the flag when command completes (success or failure)
      this._commandInProgress = false;
    }
  }

  _revertSwitchToActualState() {
    // Get the current actual state from Home Assistant
    const deviceId = this._config.device_id;
    const switchEntityId = `switch.hello_world_switch_${deviceId.replace(':', '_')}`;

    // Get the actual state from HA
    const actualState = this._hass.states[switchEntityId]?.state === 'on';

    // Find the switch element and update it to match the actual state
    const switchElement = this.shadowRoot?.getElementById('helloWorldSwitch');
    if (switchElement) {
      console.log('HelloWorldCard: Reverting switch to actual state:', actualState);
      switchElement.checked = actualState;
    }
  }

  _getDeviceDisplayName() {
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

    // Don't render until translations are loaded
    if (!this._translationsLoaded) {
      return;
    }

    const deviceId = this._config.device_id;
    const switchEntityId = `switch.hello_world_switch_${deviceId.replace(':', '_')}`;
    const sensorEntityId = `binary_sensor.hello_world_status_${deviceId.replace(':', '_')}`;

    // Get current states from HA
    const switchState = this._hass.states[switchEntityId]?.state === 'on';
    const sensorState = this._hass.states[sensorEntityId]?.state === 'on';

    // Only re-render if states have changed or first render
    if (switchState === this._previousSwitchState && sensorState === this._previousSensorState && this._rendered) {
      return;
    }

    this._previousSwitchState = switchState;
    this._previousSensorState = sensorState;

    const deviceDisplay = this._getDeviceDisplayName();

    this.shadowRoot.innerHTML = `
      <ha-card>
        <div class="card-header">
          <div class="device-info">${deviceDisplay}</div>
        </div>
        <div class="card-content">
          <div class="button-instruction">
            ${this.t('ui.card.hello_world.click_button_activate_automation')}
          </div>
          <div class="button-container">
            <ha-button
              id="helloWorldButton"
              class="toggle-button ${switchState ? 'on' : 'off'}">
              ${switchState ? 'TURN OFF' : 'TURN ON'}
            </ha-button>
            ${this._config.show_status ? `
              <div class="status">
                Status: ${switchState ? 'ON' : 'OFF'}
              </div>
            ` : ''}
          </div>
          ${this._config.show_status ? `
            <div class="binary-sensor-status">
              ${this.t('ui.card.hello_world.binary_sensor_changed_by_automation')} ${sensorState ? 'ON' : 'OFF'}
            </div>
          ` : ''}
        </div>
        <style>
          ha-card {
            padding: 16px;
          }

          .card-header {
            margin-bottom: 16px;
            font-weight: 500;
          }

          .device-info {
            font-size: 1.1em;
            color: var(--primary-text-color);
          }

          .button-instruction {
            font-size: 0.9em;
            color: var(--secondary-text-color);
            margin-bottom: 12px;
            text-align: left;
          }

          .button-container {
            display: flex;
            justify-content: center;
            align-items: center;
            gap: 12px;
            margin-bottom: 8px;
          }

          .toggle-button {
            --mdc-theme-primary: var(--primary-color);
            --mdc-theme-on-primary: white;
            min-width: 120px;
            height: 40px;
            font-weight: 500;
          }

          .toggle-button.on {
            background-color: var(--primary-color);
            color: white;
          }

          .toggle-button.off {
            background-color: var(--secondary-background-color);
            color: var(--primary-text-color);
          }

          .status {
            font-size: 0.9em;
            color: var(--secondary-text-color);
          }

          .binary-sensor-status {
            font-size: 0.8em;
            color: var(--secondary-text-color);
            margin-top: 8px;
          }
        </style>
      </ha-card>
    `;

    this._rendered = true;

    // Attach event listeners after DOM update (like hvac_fan_card)
    this._attachEventListeners();
  }

  _attachEventListeners() {
    console.log('HelloWorldCard: Attaching event listeners');

    // Find the ha-button element by ID
    const buttonElement = this.shadowRoot?.getElementById('helloWorldButton');
    if (buttonElement) {
      console.log('HelloWorldCard: Found ha-button element, attaching listener');

      // Listen for click events - this is our main event handler
      buttonElement.addEventListener('click', (event) => {
        console.log('HelloWorldCard: Button click event fired', event);
        this._handleButtonClick(event);
      });
    } else {
      console.error('HelloWorldCard: Could not find ha-button element');
    }
  }
}

// Register the web component
console.log('HelloWorldCard: Starting card registration...');
console.log('HelloWorldCard: Custom element exists?', !!customElements.get('hello-world-card'));

if (!customElements.get('hello-world-card')) {
  console.log('HelloWorldCard: Defining custom element...');
  customElements.define('hello-world-card', HelloWorldCard);
  console.log('HelloWorldCard: ✅ Custom element defined successfully');
} else {
  console.log('HelloWorldCard: ⚠️ Custom element already exists');
}

// Register it with HA for automatic discovery
console.log('HelloWorldCard: Registering with HA custom cards...');
window.customCards = window.customCards || [];
window.customCards.push({
  type: 'hello-world-card',
  name: 'Hello World Card',
  description: 'A simple demonstration card for Ramses Extras Hello World feature',
  preview: true,
  documentationURL: 'https://github.com/wimpie70/ramses_extras',
});

console.log('HelloWorldCard: ✅ Card and editor loading complete');
console.log('HelloWorldCard: Custom cards count:', window.customCards.length);
