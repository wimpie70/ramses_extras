/* global customElements */
/* global HTMLElement */
/* global setTimeout */
/* global fetch */
/* global navigator */

// Debug: Check if this file is being loaded
console.log('🚀 hvac-fan-card.js is being loaded!');

// Translation path configuration
const TRANSLATION_BASE_PATH = '/local/ramses_extras/hvac_fan_card';

import { NORMAL_SVG, BYPASS_OPEN_SVG } from './airflow-diagrams.js';
import { CARD_STYLE } from './card-styles.js';
import { createCardHeader, createTopSection, createParameterEditSection, createControlsSection, createCardFooter } from './templates/card-templates.js';
import { createTemplateData } from './templates/template-helpers.js';
import './hvac-fan-card-editor.js';

// Import reusable helpers
import { SimpleCardTranslator } from '../../../helpers/card-translations.js';
import { FAN_COMMANDS } from '../../../helpers/card-commands.js';
import { sendPacket, getBoundRemDevice, callService, entityExists, getEntityState, callWebSocket, setFanParameter } from '../../../helpers/card-services.js';
import { validateCoreEntities, validateDehumidifyEntities, logValidationResults, getEntityValidationReport } from '../../../helpers/card-validation.js';

// Debug: Check if imports work
console.log('✅ ES6 imports loaded suRFessfully');

class HvacFanCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: 'open' });
    this.parameterEditMode = false;
    this.parameterSchema = null;
    this.availableParams = {};
    this.translator = null;

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

      // // 2411 commands (sorted by payload)
      // 'req_2411_supply_away': {
      //   code: '2411',
      //   payload: '00003D'  // Request supply away
      // },
      // 'req_2411_exhaust_away': {
      //   code: '2411',
      //   payload: '00003E'  // Request exhaust away
      // },
      // 'req_2411_filtertime': {
      //   code: '2411',
      //   payload: '000031'  // Request filter time
      // },
      // 'req_2411_moist_pos': {
      //   code: '2411',
      //   payload: '00004E'  // Request moisture position
      // },
      // 'req_2411_moist_sens': {
      //   code: '2411',
      //   payload: '000052'  // Request moisture sensitivity
      // },
      // 'req_2411_moist_overrun': {
      //   code: '2411',
      //   payload: '000058'  // Request moisture overrun
      // },
      // 'req_2411_comfort': {
      //   code: '2411',
      //   payload: '000075'  // Request comfort
      // },


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
    const entities = [
      // ramses_extras provided sensors
      this.config.indoor_abs_humid_entity,
      this.config.outdoor_abs_humid_entity,
      // ramses_cc provided sensors
      this.config.indoor_temp_entity,
      this.config.outdoor_temp_entity,
      this.config.indoor_humidity_entity,
      this.config.outdoor_humidity_entity,
      this.config.supply_temp_entity,
      this.config.exhaust_temp_entity,
      this.config.fan_speed_entity,
      this.config.fan_mode_entity,
      this.config.co2_entity,
      this.config.flow_entity,
      this.config.bypass_entity,
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

  // Use service methods from shared helper
  async getBoundRem(deviceId) {
    return await getBoundRemDevice(this._hass, deviceId);
  }

  async sendPacket(deviceId, fromId, verb, code, payload) {
    return await sendPacket(this._hass, deviceId, fromId, verb, code, payload);
  }

  async sendFanCommand(commandKey) {
    if (!this._hass || !this.config?.device_id) {
      console.error('Missing Home Assistant instance or device_id');
      return false;
    }

    const command = HvacFanCard.FAN_COMMANDS[commandKey];
    if (!command) {
      console.error(`No command defined for: ${commandKey}`);
      return false;
    }

    try {
      // Use the configured device ID
      const deviceId = this.config.device_id;

      console.log(`Using configured device ID for commands: ${deviceId}`);

      // Find the actual dehumidify switch entity
      const switchEntity = 'switch.dehumidify_' + deviceId.replace(/:/g, '_');

      if (commandKey === 'active') {
        // Toggle dehumidify mode by calling the switch service
        console.log(`Toggling dehumidify switch: ${switchEntity}`);
        await callService(this._hass, 'switch', 'turn_on', {
          entity_id: switchEntity
        });
        return true;
      }

      // Get the bound REM device first
      let remId;
      try {
        remId = await this.getBoundRem(deviceId);
        if (remId) {
          console.log(`Using bound REM as from_id: ${remId}`);
        } else {
          console.log('No bound REM found, using device_id as from_id');
          remId = deviceId;
        }
      } catch (error) {
        console.warn(`WebSocket error getting bound REM: ${error.message}. Falling back to device_id.`);
        remId = null;
      }

      // Send the packet
      await this.sendPacket(deviceId, remId, command.verb, command.code, command.payload);

      console.log(`SuRFessfully sent ${commandKey} command`);

      // Update UI based on command type
      if (commandKey.startsWith('bypass_')) {
        const mode = commandKey.replace('bypass_', '');
        this.updateBypassUI(mode);
        this.render(); // Force re-render to update SVG
      } else {
        // Update fan mode display
        const fanModeElement = this.shadowRoot?.querySelector('#fanMode');
        if (fanModeElement) {
          fanModeElement.textContent = commandKey;
        }
      }

      return true;
    } catch (error) {
      console.error(`Error sending ${commandKey} command:`, error);
      return false;
    }
  }

  setConfig(config) {
    // console.log('=== hvacFanCard setConfig Debug ===');
    // console.log('Config received:', config);
    // console.log('Config type:', typeof config);
    // console.log('Config keys:', config ? Object.keys(config) : 'null');

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
      fan_speed_entity: config.fan_speed_entity || 'sensor.' + deviceId.replace(/:/g, '_') + '_fan_info',
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
    console.log('🎯 RENDER CALLED - checking config and hass...');
    console.log('🎯 this._config:', this._config);
    console.log('🎯 this._hass:', this._hass);
    console.log('🎯 this.config:', this.config);
    console.log('🎯 parameterEditMode:', this.parameterEditMode);

    if (!this._hass || !this.config) {
      console.error('❌ Missing hass or config:', {
        hass: !!this._hass,
        _config: !!this._config,
        config: !!this.config
      });
      return;
    }

    console.log('✅ Hass and config available, proceeding with render');

    // Check if we're in parameter edit mode
    if (this.parameterEditMode) {
      this.renderParameterEditMode();
      return;
    }

    // Normal card rendering
    this.renderNormalMode();
  }

  async renderParameterEditMode() {
    console.log('🔧 Rendering parameter edit mode');

    // Save scroll position before re-rendering
    const scrollContainer = this.shadowRoot?.querySelector('.param-list');
    const scrollTop = scrollContainer?.scrollTop || 0;

    // Ensure we have the parameter schema
    if (!this.parameterSchema) {
      console.log('📡 Fetching parameter schema in render...');
      this.parameterSchema = await this.fetchParameterSchema();
      console.log('✅ Schema fetched:', Object.keys(this.parameterSchema));
    }

    // Get available parameters based on entity existence
    this.availableParams = this.getAvailableParameters();
    console.log('📋 Available parameters:', Object.keys(this.availableParams));

    const templateData = {
      device_id: this.config.device_id,
      availableParams: this.availableParams,
      hass: this._hass
    };

    console.log('🔧 Generating parameter edit HTML...');

    // Generate HTML for parameter edit mode
    const cardHtml = [
      createCardHeader(CARD_STYLE),
      createParameterEditSection(templateData),
      createCardFooter()
    ].join('');

    this.shadowRoot.innerHTML = cardHtml;
    console.log('✅ Parameter edit HTML generated successfully');

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
    // Debug: Validate entities are available
    this.validateEntities();

    const config = this.config;  // Use config consistently
    const hass = this._hass;

    // Check dehumidify entity availability
    const dehumEntitiesAvailable = this.checkDehumidifyEntities();

    const indoorTemp = hass.states[config.indoor_temp_entity]?.state || '?';
    const outdoorTemp = hass.states[config.outdoor_temp_entity]?.state || '?';
    const indoorHumidity = hass.states[config.indoor_humidity_entity]?.state || '?';
    const outdoorHumidity = hass.states[config.outdoor_humidity_entity]?.state || '?';

    // Use ramses_extras absolute humidity sensors
    const indoorAbsHumidity = hass.states[config.indoor_abs_humid_entity]?.state || '?';
    const outdoorAbsHumidity = hass.states[config.outdoor_abs_humid_entity]?.state || '?';

    const supplyTemp = hass.states[config.supply_temp_entity]?.state || '?';
    const exhaustTemp = hass.states[config.exhaust_temp_entity]?.state || '?';
    const fanSpeed = hass.states[config.fan_speed_entity]?.state || 'speed ?';
    const fanMode = hass.states[config.fan_mode_entity]?.state || 'auto';
    const co2Level = hass.states[config.co2_entity]?.state || '?';
    const flowRate = hass.states[config.flow_entity]?.state || '?';

    // Dehumidifier entities (only if available)
    const dehumMode = dehumEntitiesAvailable ? (hass.states[config.dehum_mode_entity]?.state || 'off') : null;
    const dehumActive = dehumEntitiesAvailable ? (hass.states[config.dehum_active_entity]?.state || 'off') : null;

    // Comfort temperature entity (will be available when created)
    const comfortTemp = hass.states[config.comfort_temp_entity]?.state || '?';

    // Determine which SVG to use based on bypass position
    const isBypassOpen = hass.states[config.bypass_entity]?.state === 'on';
    const selectedSvg = isBypassOpen ? BYPASS_OPEN_SVG : NORMAL_SVG;

    // Create template data object with integration-provided absolute humidity
    const rawData = {
      indoorTemp, outdoorTemp, indoorHumidity, outdoorHumidity,
      indoorAbsHumidity, outdoorAbsHumidity,  // From integration sensors
      supplyTemp, exhaustTemp, fanSpeed, fanMode, co2Level, flowRate,
      dehumMode, dehumActive, comfortTemp,
      dehumEntitiesAvailable,  // Add availability flag
      timerMinutes: 0, // This would come from timer state
      // efficiency: 75   // Remove hardcoded value - let template calculate it
    };

    console.log('🔍 DEBUG - Raw temperature values:', {
      supplyTemp, exhaustTemp, outdoorTemp,
      indoorTemp
    });

    console.log('🔍 DEBUG - Humidity values:', {
      indoorHumidity, outdoorHumidity,
      indoorAbsHumidity, outdoorAbsHumidity,
      indoorAbsFromIntegration: !!hass.states[config.indoor_abs_humid_entity]?.state,
      outdoorAbsFromIntegration: !!hass.states[config.outdoor_abs_humid_entity]?.state,
      indoorAbsEntity: config.indoor_abs_humid_entity,
      outdoorAbsEntity: config.outdoor_abs_humid_entity
    });

    // Enhanced dehumidify debugging
    console.log('🔍 DEBUG - Dehumidify entities:', {
      dehumModeEntity: config.dehum_mode_entity,
      dehumActiveEntity: config.dehum_active_entity,
      dehumEntitiesAvailable,
      dehumMode: dehumMode,
      dehumActive: dehumActive,
      dehumModeState: dehumEntitiesAvailable ? hass.states[config.dehum_mode_entity]?.state : 'N/A',
      dehumActiveState: dehumEntitiesAvailable ? hass.states[config.dehum_active_entity]?.state : 'N/A'
    });

    const templateData = createTemplateData(rawData);
    // Add airflow SVG to template data
    templateData.airflowSvg = selectedSvg;

    console.log('🔍 DEBUG - Calculated efficiency:', templateData.efficiency);

    console.log('🔧 Generating card HTML using templates...');

    // Generate HTML using template functions
    const cardHtml = [
      createCardHeader(CARD_STYLE),
      createTopSection(templateData),
      createControlsSection(dehumEntitiesAvailable),  // Pass availability flag
      createCardFooter()
    ].join('');

    this.shadowRoot.innerHTML = cardHtml;

    console.log('✅ Card HTML generated suRFessfully');

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
    return 3;
  }

  // Validate all required entities are available
  validateEntities() {
    console.log('🎯 VALIDATE ENTITIES CALLED!');
    console.log('🎯 this._config exists:', !!this._config);
    console.log('🎯 this._hass exists:', !!this._hass);
    console.log('🎯 this.config exists:', !!this.config);

    // Note: config and hass are already validated in render() before this is called
    const config = this.config;
    const hass = this._hass;

    console.log('🔍 DEBUG - Config object:', {
      hasConfig: !!config,
      configKeys: config ? Object.keys(config) : 'NO CONFIG',
      indoor_temp_entity: config?.indoor_temp_entity,
      outdoor_temp_entity: config?.outdoor_temp_entity,
      dehum_mode_entity: config?.dehum_mode_entity,
      dehum_active_entity: config?.dehum_active_entity,
      device_id: config?.device_id,
      fullConfig: config
    });

    // Use the shared validation helper
    const validationReport = getEntityValidationReport(hass, config);
    logValidationResults(validationReport);
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

  // Handle bypass button clicks
  async sendBypassCommand(mode) {
    console.log('Setting bypass to:', mode);

    try {
      // Send the actual bypass command via FAN_COMMANDS
      const commandKey = 'bypass_' + mode;
      await this.sendFanCommand(commandKey);

      // Update UI immediately to reflect the change
      this.updateBypassUI(mode);

      console.log(`✅ Bypass mode set to ${mode} successfully`);
      console.log('📋 Note: SVG will update automatically when entity state changes');
    } catch (error) {
      console.error(`❌ Failed to set bypass mode to ${mode}:`, error);
    }
  }

  // Handle timer button clicks
  async setTimer(minutes) {
    console.log('Setting timer for:', minutes, 'minutes');

    try {
      // Send the actual timer command via FAN_COMMANDS
      // Convert minutes to command key (e.g., '15' -> 'high_15')
      const commandKey = `high_${minutes}`;
      await this.sendFanCommand(commandKey);

      // Update UI immediately to reflect the change
      this.updateTimerUI(minutes);

      console.log(`✅ Timer set to ${minutes} minutes successfully`);
    } catch (error) {
      console.error(`❌ Failed to set timer to ${minutes} minutes:`, error);
    }
  }

  // Handle fan mode changes
  async setFanMode(mode) {
    console.log('Setting fan mode to:', mode);

    if (mode === 'active') {
      // Find the actual dehumidify switch entity
      const deviceId = this.config.device_id;
      const switchEntity = 'switch.dehumidify_' + deviceId.replace(/:/g, '_');

      if (entityExists(this._hass, switchEntity)) {
        // Toggle dehumidify mode by calling the switch service
        console.log(`Toggling dehumidify switch: ${switchEntity}`);
        await callService(this._hass, 'switch', 'toggle', {
          entity_id: switchEntity
        });
      } else {
        console.error(`Dehumidify switch not found: ${switchEntity}`);
      }
    } else {
      // Handle other fan modes (if any)
      console.log('Other fan mode:', mode);
      await this.sendFanCommand(mode);
    }
  }

  // Toggle between normal and parameter edit modes
  async toggleParameterMode() {
    console.log('🎛️ Toggling parameter edit mode, current:', this.parameterEditMode);
    this.parameterEditMode = !this.parameterEditMode;

    if (this.parameterEditMode) {
      console.log('🔧 Entering parameter edit mode - fetching schema...');
      // Entering parameter edit mode - fetch schema if needed
      if (!this.parameterSchema) {
        console.log('📡 Fetching parameter schema...');
        this.parameterSchema = await this.fetchParameterSchema();
        console.log('✅ Parameter schema received:', Object.keys(this.parameterSchema));
      }
    } else {
      console.log('🏠 Returning to normal mode');
    }

    this.render();
  }

  // Fetch parameter schema from WebSocket
  async fetchParameterSchema() {
    try {
      console.log('Fetching 2411 parameter schema via WebSocket...');
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
    console.log('🔍 Getting available parameters for device:', this.config.device_id);

    // Check all possible number entities for this device
    const available = {};

    // Get all states and filter for this device's number entities
    const devicePrefix = `number.${this.config.device_id.replace(/:/g, '_')}_`;

    Object.keys(this._hass.states).forEach(entityId => {
      if (entityId.startsWith(devicePrefix) && entityId.startsWith('number.')) {
        const entity = this._hass.states[entityId];
        const entityName = entityId.replace(devicePrefix, '');

        console.log(`🔍 Found entity: ${entityId}, state: ${entity?.state}`);

        // Try to get description from 2411 schema if it's a param_ entity
        let description = entity.attributes?.friendly_name || entityName.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());

        if (entityName.startsWith('param_')) {
          const paramKey = entityName.replace('param_', '').toUpperCase();
          if (this.parameterSchema && this.parameterSchema[paramKey]) {
            description = this.parameterSchema[paramKey].description || this.parameterSchema[paramKey].name;
            console.log(`📋 Using schema description for ${paramKey}: ${description}`);
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
        console.log(`✅ Added parameter ${entityName} with description "${description}" and value ${entity.state}`);
      }
    });

    console.log('📋 Final available parameters:', Object.keys(available));
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

  updateTimerUI(minutes) {
    console.log('Updating timer UI to:', minutes, 'minutes');
    const timerElement = this.shadowRoot?.querySelector('#timer');
    if (timerElement) {
      timerElement.textContent = minutes + ' min';
    }

    // Update active state
    const buttons = this.shadowRoot?.querySelectorAll('.control-button');
    if (buttons) {
      buttons.forEach(btn => {
        const label = btn.querySelector('.control-label')?.textContent;
        if (label === minutes + 'm') {
          btn.classList.add('active');
        } else if (['15m', '30m', '60m'].includes(label)) {
          btn.classList.remove('active');
        }
      });
    }
  }

  updateBypassUI(mode) {
    console.log('Updating bypass UI to:', mode);

    // Update active state
    const buttons = this.shadowRoot?.querySelectorAll('.control-button');
    if (buttons) {
      buttons.forEach(btn => {
        const label = btn.querySelector('.control-label')?.textContent;
        if ((mode === 'auto' && label === 'Bypass Auto') ||
            (mode === 'close' && label === 'Bypass Close') ||
            (mode === 'open' && label === 'Bypass Open')) {
          btn.classList.add('active');
        } else if (label?.startsWith('Bypass')) {
          btn.classList.remove('active');
        }
      });
    }
  }

  // Add event listeners after the component is connected to the DOM
  connectedCallback() {
    console.log('=== hvacFanCard connectedCallback Debug ===');
    console.log('Card connected to DOM');
    console.log('Card instance:', this);
    console.log('Card shadowRoot:', this.shadowRoot);
    console.log('Card config at connect:', this._config);
    console.log('Card hass at connect:', this._hass);

    // No need to call super.connectedCallback() as HTMLElement doesn't have it

    console.log('✅ Event listeners will be attached during render');
  }

  // Attach event listeners for normal mode
  attachNormalModeListeners() {
    console.log('🔧 Attaching normal mode event listeners');

    // Settings icon in top section
    const settingsIcon = this.shadowRoot?.querySelector('.settings-icon');
    if (settingsIcon) {
      settingsIcon.addEventListener('click', (e) => {
        console.log('⚙️ Settings icon clicked');
        e.preventDefault();
        e.stopPropagation();
        this.toggleParameterMode();
      });
      console.log('✅ Settings icon listener attached');
    } else {
      console.log('⚠️ Settings icon not found in DOM');
    }

    // Control buttons
    const controlButtons = this.shadowRoot?.querySelectorAll('.control-button');
    if (controlButtons) {
      controlButtons.forEach(button => {
        button.addEventListener('click', (e) => {
          console.log('🔘 Control button clicked:', button);
          e.preventDefault();
          e.stopPropagation();

          const onclick = button.getAttribute('onclick');
          if (onclick) {
            console.log('Executing onclick handler:', onclick);
            const fn = new Function('event', `try { ${onclick} } catch(e) { console.error('Error in button handler:', e); }`);
            fn.call(button, e);
          } else if (button.dataset.mode) {
            console.log('Calling setFanMode with mode:', button.dataset.mode);
            this.setFanMode(button.dataset.mode);
          } else if (button.dataset.timer) {
            console.log('Calling setTimer with minutes:', button.dataset.timer);
            this.setTimer(button.dataset.timer);
          }
        });
      });
      console.log(`✅ ${controlButtons.length} control button listeners attached`);
    }
  }

  // Attach event listeners for parameter edit mode
  attachParameterEditListeners() {
    console.log('🔧 Attaching parameter edit mode event listeners');

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

window.setBypassMode = function(mode) {
  const card = document.querySelector('hvac-fan-card');
  if (card) {
    card.sendBypassCommand(mode);
  }
};

window.setTimer = function(minutes) {
  const card = document.querySelector('hvac-fan-card');
  if (card) {
    card.setTimer(minutes);
  }
};

window.setFanMode = function(mode) {
  const card = document.querySelector('hvac-fan-card');
  if (card) {
    card.setFanMode(mode);
  }
};

// Register it with HA for automatic discovery
window.customCards = window.customCards || [];
console.log('🔍 Current window.customCards before registration:', window.customCards.length);

window.customCards.push({
  type: "hvac-fan-card",
  name: "Hvac Fan Control Card",
  description: "Advanced control card for Orcon or other ventilation systems with multi-language support",
  preview: true, // Shows in card picker
  documentationURL: "https://github.com/wimpie70/ramses_extras"
});

console.log('✅ hvac-fan-card registered in window.customCards:', {
  type: "hvac-fan-card",
  name: "Hvac Fan Control Card",
  length: window.customCards.length
});
console.log('📋 All registered cards:', window.customCards);
