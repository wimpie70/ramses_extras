/* global customElements */
/* global HTMLElement */
/* global setTimeout */
/* global clearTimeout */
/* global setInterval */
/* global clearInterval */
/* global fetch */
/* global navigator */

// Translation path configuration
const TRANSLATION_BASE_PATH = '/local/ramses_extras/hvac_fan_card';

import { NORMAL_SVG, BYPASS_OPEN_SVG } from './airflow-diagrams.js';
import { CARD_STYLE } from './card-styles.js';
import { createCardHeader, createTopSection, createParameterEditSection, createControlsSection, createCardFooter } from './templates/card-templates.js';
import { createTemplateData } from './templates/template-helpers.js';
import './hvac-fan-card-editor.js';

// Import reusable helpers from shared location
import { SimpleCardTranslator } from '/local/ramses_extras/helpers/card-translations.js';
import { FAN_COMMANDS } from '/local/ramses_extras/helpers/card-commands.js';
import { getRamsesMessageBroker } from '/local/ramses_extras/helpers/ramses-message-broker.js';
import { HvacFanCardHandlers } from './message-handlers.js';
import { sendPacket, getBoundRemDevice, callService, entityExists, getEntityState, callWebSocket, setFanParameter } from '/local/ramses_extras/helpers/card-services.js';
import { validateCoreEntities, validateDehumidifyEntities, getEntityValidationReport } from '/local/ramses_extras/helpers/card-validation.js';

// Make FAN_COMMANDS globally available
window.FAN_COMMANDS = FAN_COMMANDS;

class HvacFanCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: 'open' });
    this.parameterEditMode = false;
    this.parameterSchema = null;
    this.availableParams = {};
    this.translator = null;
    this._eventCheckTimer = null; // Timer for event checks
    this._stateCheckInterval = null; // Interval for state monitoring
    this._pollInterval = null; // Interval for polling

    // Initialize translations
    this.initTranslations();
  }

  // Initialize translations for this card
  async initTranslations() {
    this.translator = new SimpleCardTranslator('hvac-fan-card');
    await this.translator.init('/local/ramses_extras/hvac_fan_card');
  }

  // Helper method to get translated strings
  t(key, params = {}) {
    if (!this.translator) {
      return key; // Fallback if translator not ready
    }
    return this.translator.t(key, params);
  }

  // Helper method to check if translation exists
  hasTranslation(key) {
    if (!this.translator) {
      return false;
    }
    return this.translator.has(key);
  }

  // Get current language
  getCurrentLanguage() {
    if (!this.translator) {
      return 'en';
    }
    return this.translator.getCurrentLanguage();
  }

  // Use commands from the shared helper
  static get FAN_COMMANDS() {
    return FAN_COMMANDS;
  }


  static get properties() {
    return {
      config: {},
      _hass: {},
    };
  }


  set hass(hass) {
    this._hass = hass;

    if (this.config && this.shouldUpdate()) {
      this.render();
    }
  }

  shouldUpdate() {
    if (!this._hass || !this.config) return false;

    // Check if any of our monitored entities have changed
    // Only monitor entities that are NOT provided by 31DA messages
    const entities = [
      // ramses_extras provided sensors (not from 31DA)
      this.config.indoor_abs_humid_entity,
      this.config.outdoor_abs_humid_entity,
      // Other sensors not provided by 31DA
      this.config.co2_entity,
      this.config.dehum_mode_entity,
      this.config.dehum_active_entity,
      this.config.comfort_temp_entity,
    ].filter(Boolean);

    return entities.some(entity => {
      const oldState = this._prevStates ? this._prevStates[entity] : null;
      const newState = this._hass.states[entity];
      this._prevStates = this._prevStates || {};
      this._prevStates[entity] = newState;
      return oldState !== newState;
    });
  }



  setConfig(config) {
    if (!config.fan_entity && !config.device_id) {
      console.error('Missing required config: need fan_entity or device_id');
      throw new Error('You need to define either fan_entity or device_id');
    }

    if (!config.device_id) {
      console.warn('No device_id provided, will extract from fan_entity');
      throw new Error('You need to define device_id');
    }

    // Normalize device ID to colon format for consistency
    let deviceId = config.device_id;
    deviceId = deviceId.replace(/_/g, ':');

    // Store the processed config for internal use
    this._config = {
      device_id: deviceId,
      // Auto-generate absolute humidity sensor entities (created by integration)
      indoor_abs_humid_entity: 'sensor.indoor_absolute_humidity_' + deviceId.replace(/:/g, '_'),
      outdoor_abs_humid_entity: 'sensor.outdoor_absolute_humidity_' + deviceId.replace(/:/g, '_'),
      // Fallback to calculated humidity if absolute humidity sensors don't exist
      indoor_temp_entity: config.indoor_temp_entity || 'sensor.' + deviceId.replace(/:/g, '_') + '_indoor_temp',
      outdoor_temp_entity: config.outdoor_temp_entity || 'sensor.' + deviceId.replace(/:/g, '_') + '_outdoor_temp',
      indoor_humidity_entity: config.indoor_humidity_entity || 'sensor.' + deviceId.replace(/:/g, '_') + '_indoor_humidity',
      outdoor_humidity_entity: config.outdoor_humidity_entity || 'sensor.' + deviceId.replace(/:/g, '_') + '_outdoor_humidity',
      supply_temp_entity: config.supply_temp_entity || 'sensor.' + deviceId.replace(/:/g, '_') + '_supply_temp',
      exhaust_temp_entity: config.exhaust_temp_entity || 'sensor.' + deviceId.replace(/:/g, '_') + '_exhaust_temp',
      fan_speed_entity: config.fan_speed_entity || 'sensor.' + deviceId.replace(/:/g, '_') + '_fan_rate',
      fan_mode_entity: config.fan_mode_entity || 'sensor.' + deviceId.replace(/:/g, '_') + '_fan_mode',
      co2_entity: config.co2_entity || 'sensor.' + deviceId.replace(/:/g, '_') + '_co2_level',
      flow_entity: config.flow_entity || 'sensor.' + deviceId.replace(/:/g, '_') + '_supply_flow',
      bypass_entity: config.bypass_entity || 'binary_sensor.' + deviceId.replace(/:/g, '_') + '_bypass_position',
      // Use configured entities if provided, otherwise auto-generate
      dehum_mode_entity: config.dehum_mode_entity || 'switch.dehumidify_' + deviceId.replace(/:/g, '_'),
      dehum_active_entity: config.dehum_active_entity || 'binary_sensor.dehumidifying_active_' + deviceId.replace(/:/g, '_'),
      comfort_temp_entity: config.comfort_temp_entity || 'number.' + deviceId.replace(/:/g, '_') + '_param_75',
      ...config
    };

    // Set the config property for Home Assistant's card framework
    // This ensures this.config is available and matches this._config
    this.config = this._config;
  }

  render() {
    if (!this._hass || !this.config) {
      console.error('❌ Missing hass or config:', {
        hass: !!this._hass,
        _config: !!this._config,
        config: !!this.config
      });
      return;
    }

    // Check if we're in parameter edit mode
    if (this.parameterEditMode) {
      this.renderParameterEditMode();
      return;
    }

    // Normal card rendering
    this.renderNormalMode();
  }

  async renderParameterEditMode() {
    // Save scroll position before re-rendering
    const scrollContainer = this.shadowRoot?.querySelector('.param-list');
    const scrollTop = scrollContainer?.scrollTop || 0;

    // Ensure we have the parameter schema
    if (!this.parameterSchema) {
      this.parameterSchema = await this.fetchParameterSchema();
    }

    // Get available parameters based on entity existence
    this.availableParams = this.getAvailableParameters();

    const templateData = {
      device_id: this.config.device_id,
      availableParams: this.availableParams,
      hass: this._hass
    };


    // Generate HTML for parameter edit mode
    const cardHtml = [
      createCardHeader(CARD_STYLE),
      createParameterEditSection(templateData),
      createCardFooter()
    ].join('');

    this.shadowRoot.innerHTML = cardHtml;

    // Restore scroll position after DOM update
    const newScrollContainer = this.shadowRoot?.querySelector('.param-list');
    if (newScrollContainer) {
      newScrollContainer.scrollTop = scrollTop;
    }

    // Attach event listeners for parameter edit mode
    this.attachParameterEditListeners();

    // Re-attach event listeners after DOM update
    // Note: onchange removed from input, now using update button
  }

  renderNormalMode() {
    // Validate entities are available
    this.validateEntities();

    const config = this.config;  // Use config consistently
    const hass = this._hass;

    // Check dehumidify entity availability
    const dehumEntitiesAvailable = this.checkDehumidifyEntities();

    // Get data from 31DA messages (primary source) or fall back to entities
    const da31Data = this.get31DAData();

    // Temperature data - depend solely on 31DA
    const indoorTemp = da31Data.indoor_temp !== undefined ?
      da31Data.indoor_temp : null;

    const outdoorTemp = da31Data.outdoor_temp !== undefined ?
      da31Data.outdoor_temp : null;

    const supplyTemp = da31Data.supply_temp !== undefined ?
      da31Data.supply_temp : null;

    const exhaustTemp = da31Data.exhaust_temp !== undefined ?
      da31Data.exhaust_temp : null;

    // Humidity data - depend solely on 31DA
    const indoorHumidity = da31Data.indoor_humidity !== undefined ?
      da31Data.indoor_humidity : null;

    const outdoorHumidity = da31Data.outdoor_humidity !== undefined ?
      da31Data.outdoor_humidity : null;

    // Use ramses_extras absolute humidity sensors (if available) - raw values only
    const indoorAbsHumidity = hass.states[config.indoor_abs_humid_entity]?.state ?
      (isNaN(parseFloat(hass.states[config.indoor_abs_humid_entity].state)) ? null : parseFloat(hass.states[config.indoor_abs_humid_entity].state)) : null;
    const outdoorAbsHumidity = hass.states[config.outdoor_abs_humid_entity]?.state ?
      (isNaN(parseFloat(hass.states[config.outdoor_abs_humid_entity].state)) ? null : parseFloat(hass.states[config.outdoor_abs_humid_entity].state)) : null;

    // Fan data - 31DA as primary, entity as fallback
    const rawData = {
      indoorTemp, outdoorTemp, indoorHumidity, outdoorHumidity,
      indoorAbsHumidity, outdoorAbsHumidity,  // From integration sensors
      supplyTemp, exhaustTemp,
      // Fan data - depend solely on da31Data, move into if-then-else
      fanSpeed: this._getFanSpeed(da31Data),
      fanMode: this._getFanMode(da31Data),
      // Flow data - depend solely on da31Data
      flowRate: da31Data.supply_flow !== undefined ?
        da31Data.supply_flow : null,
      exhaustFlowRate: da31Data.exhaust_flow !== undefined ?
        da31Data.exhaust_flow : null,
      // Other data - raw values only
      co2Level: hass.states[config.co2_entity]?.state ?
        (isNaN(parseFloat(hass.states[config.co2_entity].state)) ? null : parseFloat(hass.states[config.co2_entity].state)) : null,
      // Dehumidifier entities (only if available)
      dehumMode: dehumEntitiesAvailable ? (hass.states[config.dehum_mode_entity]?.state || 'off') : null,
      dehumActive: dehumEntitiesAvailable ? (hass.states[config.dehum_active_entity]?.state || 'off') : null,
      // Comfort temperature entity (will be available when created)
      comfortTemp: hass.states[config.comfort_temp_entity]?.state ?
        (isNaN(parseFloat(hass.states[config.comfort_temp_entity].state)) ? null : parseFloat(hass.states[config.comfort_temp_entity].state)) : null,
      // Bypass position - depend solely on da31Data
      bypassPosition: da31Data.bypass_position !== undefined ?
        da31Data.bypass_position : null,
      dehumEntitiesAvailable,  // Add availability flag
      dataSource31DA: da31Data.source === '31DA_message',  // Flag for UI
      timerMinutes: da31Data.remaining_mins !== undefined ? da31Data.remaining_mins : 0,
      // efficiency: 75   // Remove hardcoded value - let template calculate it
    };

    const selectedSvg = rawData.bypassPosition !== null && rawData.bypassPosition > 0 ? BYPASS_OPEN_SVG : NORMAL_SVG;

    const templateData = createTemplateData(rawData);
    // Add airflow SVG to template data
    templateData.airflowSvg = selectedSvg;

    // Generate HTML using template functions
    const cardHtml = [
      createCardHeader(CARD_STYLE),
      createTopSection(templateData),
      createControlsSection(dehumEntitiesAvailable, config),  // Pass availability flag and config
      createCardFooter()
    ].join('');

    this.shadowRoot.innerHTML = cardHtml;

    // Attach event listeners for normal mode
    this.attachNormalModeListeners();
  }

  // Configuration schema for visual editor
  static getConfigElement() {
    try {
      // Ensure the editor is available before creating it
      if (typeof window.HvacFanCardEditor === 'undefined') {
        console.error('HvacFanCardEditor is not defined on window');
        return null;
      }
      return document.createElement("hvac-fan-card-editor");
    } catch (error) {
      console.error('Error creating config element:', error);
      return null;
    }
  }

  // Card size for Home Assistant
  getCardSize() {
    return 4;
  }

  // Validate all required entities are available
  validateEntities() {

    // Note: config and hass are already validated in render() before this is called
    const config = this.config;
    const hass = this._hass;

    // Use the shared validation helper
    const validationReport = getEntityValidationReport(hass, config);
  }

  // Check if dehumidify entities are available
  checkDehumidifyEntities() {
    // Note: config and hass are already validated in render() before this is called
    const config = this.config;
    const hass = this._hass;

    // Use the shared validation helper
    const dehumValidation = validateDehumidifyEntities(hass, config);
    return dehumValidation.available;
  }


  // Toggle between normal and parameter edit modes
  async toggleParameterMode() {
    this.parameterEditMode = !this.parameterEditMode;

    if (this.parameterEditMode) {
      // Entering parameter edit mode - fetch schema if needed
      if (!this.parameterSchema) {
        this.parameterSchema = await this.fetchParameterSchema();
      }
    }

    this.render();
  }

  // Fetch parameter schema from WebSocket
  async fetchParameterSchema() {
    try {
      const result = await callWebSocket(this._hass, {
        type: "ramses_extras/get_2411_schema"
      });
      console.log('Parameter schema received:', Object.keys(result));
      return result;
    } catch (error) {
      console.error('Failed to fetch parameter schema:', error);
      return {};
    }
  }

  // Get available parameters based on entity existence
  getAvailableParameters() {
    // Check all possible number entities for this device
    const available = {};

    // Get all states and filter for this device's number entities
    const devicePrefix = `number.${this.config.device_id.replace(/:/g, '_')}_`;

    Object.keys(this._hass.states).forEach(entityId => {
      if (entityId.startsWith(devicePrefix) && entityId.startsWith('number.')) {
        const entity = this._hass.states[entityId];
        const entityName = entityId.replace(devicePrefix, '');

        // Try to get description from 2411 schema if it's a param_ entity
        let description = entity.attributes?.friendly_name || entityName.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());

        if (entityName.startsWith('param_')) {
          const paramKey = entityName.replace('param_', '').toUpperCase();
          if (this.parameterSchema && this.parameterSchema[paramKey]) {
            description = this.parameterSchema[paramKey].description || this.parameterSchema[paramKey].name;
          } else {
            // Fallback: try to create a readable description from the parameter key
            description = paramKey.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
            console.log(`📋 No schema found for ${paramKey}, using fallback: ${description}`);
          }
        }

        // Create parameter info based on entity attributes or schema
        const paramInfo = {
          description: description,
          unit: entity.attributes?.unit_of_measurement || '',
          min_value: entity.attributes?.min || 0,
          max_value: entity.attributes?.max || 100,
          default_value: entity.attributes?.min || 0,
          current_value: entity.state,
          data_type: '01', // Generic number
          precision: entity.attributes?.step || 1
        };

        // Override with schema data if available
        if (entityName.startsWith('param_')) {
          const paramKey = entityName.replace('param_', '');
          if (this.parameterSchema && this.parameterSchema[paramKey]) {
            const schemaInfo = this.parameterSchema[paramKey];
            paramInfo.unit = schemaInfo.unit || schemaInfo.data_unit || paramInfo.unit;
            paramInfo.min_value = schemaInfo.min_value || paramInfo.min_value;
            paramInfo.max_value = schemaInfo.max_value || paramInfo.max_value;
            paramInfo.default_value = schemaInfo.default_value || paramInfo.default_value;
            paramInfo.precision = schemaInfo.precision || paramInfo.precision;
            paramInfo.data_type = schemaInfo.data_type || paramInfo.data_type;
          }
        }

        available[entityName] = paramInfo;
      }
    });

    return available;
  }

  // Update a parameter value
  async updateParameter(paramKey, newValue) {
    console.log(`🔄 Updating parameter ${paramKey} to ${newValue}`);

    const paramItem = this.shadowRoot?.querySelector(`[data-param="${paramKey}"]`);
    if (paramItem) {
      paramItem.classList.add('loading');
      paramItem.classList.remove('success', 'error');
    }

    try {
      console.log(`📡 Calling ramses_cc.set_fan_param service for ${paramKey}...`);
      // Extract the parameter ID from the entity name (e.g., "param_31" -> "31")
      const paramId = paramKey.startsWith('param_') ? paramKey.replace('param_', '') : paramKey;
      await setFanParameter(this._hass, this.config.device_id, paramId, newValue);
      console.log(`✅ Parameter ${paramKey} update sent successfully (fire and forget)`);
      // Don't wait for confirmation - service handles it asynchronously
      if (paramItem) {
        paramItem.classList.remove('loading');
        paramItem.classList.add('success');
        setTimeout(() => paramItem.classList.remove('success'), 2000);
      }
    } catch (error) {
      console.error(`❌ Failed to update parameter ${paramKey}:`, error);
      if (paramItem) {
        paramItem.classList.remove('loading');
        paramItem.classList.add('error');
      }
    }
  }


  // REMOVED: Cards no longer subscribe directly - RamsesMessageHelper handles all subscriptions

  // REMOVED: Cards no longer handle messages directly - RamsesMessageHelper manages all subscriptions

  // Add event listeners after the component is connected to the DOM
  connectedCallback() {
    // Register for real-time message updates if we have a device ID
    if (this._config?.device_id) {
      const messageHelper = getRamsesMessageBroker();
      messageHelper.addListener(this, this._config.device_id, ["31DA", "10D0"]);
    }
  }

  disconnectedCallback() {
    // Clean up message listener when card is removed
    if (this._config?.device_id) {
      const messageHelper = getRamsesMessageBroker();
      messageHelper.removeListener(this, this._config.device_id);

      // Clear any event reception check timers
      if (this._eventCheckTimer) {
        clearTimeout(this._eventCheckTimer);
        this._eventCheckTimer = null;
      }
    }

    // REMOVED: No direct subscriptions to clean up - RamsesMessageHelper handles all subscriptions

    // Clear other intervals
    if (this._stateCheckInterval) {
      clearInterval(this._stateCheckInterval);
      this._stateCheckInterval = null;
    }

    if (this._pollInterval) {
      clearInterval(this._pollInterval);
      this._pollInterval = null;
    }
  }


  // Message handler methods - called automatically by RamsesMessageHelper
  handle_31DA(messageData) {
    // Use the handlers class to process the message
    HvacFanCardHandlers.handle_31DA(this, messageData);
  }

  handle_10D0(messageData) {
    // Use the handlers class to process the message
    HvacFanCardHandlers.handle_10D0(this, messageData);
  }

  // Update the card with 31DA data
  updateFrom31DA(hvacData) {
    // Store the data for rendering
    this._31daData = hvacData;

    // Force a re-render to show updated data
    if (this._hass && this.config) {
      this.render();
    }
  }

  // Update the card with 10D0 data
  updateFrom10D0(filterData) {
    // Store the filter data for rendering
    this._10d0Data = filterData;

    // Force a re-render to show updated data
    if (this._hass && this.config) {
      this.render();
    }
  }

  // Get 31DA data (if available) for template rendering
  get31DAData() {
    return this._31daData || {};
  }

  // Get 10D0 data (if available) for template rendering
  get10D0Data() {
    return this._10d0Data || {};
  }

  // Get fan speed from 31DA data - always show percentage
  _getFanSpeed(da31Data) {
    if (!da31Data.fan_info) return null;

    // Try to get speed from supply/exhaust fan speed first
    const supplySpeed = da31Data.supply_fan_speed;
    const exhaustSpeed = da31Data.exhaust_fan_speed;

    // Use supply speed if available, otherwise exhaust speed
    const actualSpeed = supplySpeed !== undefined ? supplySpeed : exhaustSpeed;

    // Always return percentage if we have speed data (multiply by 100, no decimals)
    if (actualSpeed !== undefined) {
      return `${Math.round(actualSpeed * 100)}%`;
    }

    return null;
  }

  // Get fan mode from 31DA data - always show fan_info as-is
  _getFanMode(da31Data) {
    return da31Data.fan_info || null;
  }


  // Attach event listeners for normal mode
  attachNormalModeListeners() {
    // Settings icon in top section
    const settingsIcon = this.shadowRoot?.querySelector('.settings-icon');
    if (settingsIcon) {
      settingsIcon.addEventListener('click', (e) => {
        e.preventDefault();
        e.stopPropagation();
        this.toggleParameterMode();
      });
    }

    // Control buttons
    const controlButtons = this.shadowRoot?.querySelectorAll('.control-button');
    if (controlButtons) {
      controlButtons.forEach(button => {
        button.addEventListener('click', (e) => {
          e.preventDefault();
          e.stopPropagation();

          const onclick = button.getAttribute('onclick');
          if (onclick) {
            const fn = new Function('event', `try { ${onclick} } catch(e) { console.error('Error in button handler:', e); }`);
            fn.call(button, e);
          }
        });
      });
    }
  }

  // Attach event listeners for parameter edit mode
  attachParameterEditListeners() {
    // Back/settings icons in parameter edit mode
    const settingsIcon = this.shadowRoot?.querySelector('.settings-icon');
    const backIcon = this.shadowRoot?.querySelector('.back-icon');

    if (settingsIcon) {
      settingsIcon.addEventListener('click', (e) => {
        console.log('🔙 Back icon clicked');
        e.preventDefault();
        e.stopPropagation();
        this.toggleParameterMode();
      });
    }

    if (backIcon) {
      backIcon.addEventListener('click', (e) => {
        console.log('🔙 Back icon clicked');
        e.preventDefault();
        e.stopPropagation();
        this.toggleParameterMode();
      });
    }

    // Parameter update buttons
    const paramButtons = this.shadowRoot?.querySelectorAll('.param-update-btn');
    if (paramButtons) {
      paramButtons.forEach(button => {
        button.addEventListener('click', (e) => {
          const paramKey = button.getAttribute('data-param');
          const input = button.previousElementSibling;
          const newValue = input?.value;
          console.log(`📝 Parameter ${paramKey} update button clicked with value ${newValue}`);
          if (paramKey && newValue !== undefined) {
            this.updateParameter(paramKey, newValue);
          } else {
            console.error('❌ Missing paramKey or newValue:', { paramKey, newValue });
          }
        });
      });
      console.log(`✅ ${paramButtons.length} parameter update button listeners attached`);
    }
  }
}

// Include the editor component
// This ensures the editor is loaded when the card is used

// Register the web component
if (!customElements.get('hvac-fan-card')) {
  console.log('Registering hvac-fan-card web component');
  customElements.define('hvac-fan-card', HvacFanCard);
}

// Make functions globally available for onclick handlers
window.toggleParameterMode = function() {
  const card = document.querySelector('hvac-fan-card');
  if (card) {
    card.toggleParameterMode();
  }
};

window.updateParameter = function(paramKey, newValue) {
  const card = document.querySelector('hvac-fan-card');
  if (card) {
    card.updateParameter(paramKey, newValue);
  }
};

// Note: window.send_command is defined below

window.send_command = function(commandKey, deviceId, buttonElement) {
  console.log(`window.send_command called with: ${commandKey}, deviceId: ${deviceId}, buttonElement:`, buttonElement);

  // Get the command definition
  const command = window.FAN_COMMANDS[commandKey];
  if (!command) {
    console.error(`No command defined for: ${commandKey}`);
    return;
  }

  // Use the button element to find the host element
  let element = buttonElement;
  while (element && element.tagName !== 'HVAC-FAN-CARD') {
    element = element.parentElement || element.getRootNode()?.host;
  }

  if (element && element._hass) {
//    console.log('Found HASS instance in host element, using proper from_id');

    // Use the imported helper functions directly with the element's hass instance
    (async () => {
      try {
        // Get the bound REM device first for proper from_id
        let remId;
        try {
          remId = await getBoundRemDevice(element._hass, deviceId);
          if (!remId) {
            console.log('No bound REM found, add a "bound" REM device to Ramses RF Known Devices Config.');
          }
        } catch (error) {
          console.warn(`WebSocket error getting bound REM: ${error.message}.`);
          remId = deviceId;
        }

        // Send the packet with proper from_id
        await sendPacket(element._hass, deviceId, remId, command.verb, command.code, command.payload);
        console.log(`Successfully sent ${commandKey} command`);

        // After sending command, wait a bit then request status update and refresh entity states
        setTimeout(async () => {
          try {
            console.log(`🔄 Requesting status updates after ${commandKey} command...`);

            // Send 31DA request to get updated status (speed, flow, etc.)
            await sendPacket(element._hass, deviceId, remId, 'RQ', '31DA', '00');

            // // For speed commands, also request 10D0 to get fan mode information
            // const speedCommands = ['low', 'medium', 'high', 'away', 'boost', 'disable'];
            // if (speedCommands.includes(commandKey)) {
            //   console.log('📡 Also requesting 10D0 for fan mode update...');
            //   await sendPacket(element._hass, deviceId, remId, 'RQ', '10D0', '00');
            //   console.log('✅ 10D0 fan mode request sent');
            // }

            // Wait a bit more for the status responses, then refresh UI
            setTimeout(() => {
              console.log(`🔄 Refreshing entity states after ${commandKey} command...`);
              if (element && element._hass) {
                // Clear previous states to force update detection
                element._prevStates = null;
                // Trigger hass setter to re-render if states changed
                element.hass = element._hass;
              }
            }, 1000); // Additional 1 second delay for status responses
          } catch (error) {
            console.warn('Error requesting status update:', error);
          }
        }, 1000); // 1 second delay to allow device to respond
      } catch (error) {
        console.error('Error sending command:', error);
      }
    })();
  } else {
    console.error('Could not find HASS instance in host element');
    console.log('Element found:', element);
    console.log('Element _hass:', element?._hass);
  }
};

// Register it with HA for automatic discovery
window.customCards = window.customCards || [];

window.customCards.push({
  type: "hvac-fan-card",
  name: "Hvac Fan Control Card",
  description: "Advanced control card for Orcon or other ventilation systems with multi-language support",
  preview: true, // Shows in card picker
  documentationURL: "https://github.com/wimpie70/ramses_extras"
});
