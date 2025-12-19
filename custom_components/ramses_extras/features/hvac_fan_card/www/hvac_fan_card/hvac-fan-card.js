/* eslint-disable no-console */
/* global customElements */
/* global setTimeout */
/* global clearTimeout */
/* global clearInterval */

// Import the base card class
import { RamsesBaseCard } from '/local/ramses_extras/helpers/ramses-base-card.js';

// Import shared path constants (using new JS_FEATURE_REORGANIZATION pattern)
// import {
//   // PATHS, HELPER_PATHS,
//   getFeatureTranslationPath
// } from '/local/ramses_extras/helpers/paths.js';

// Translation path configuration - using shared constants
// const TRANSLATION_BASE_PATH = getFeatureTranslationPath('hvac_fan_card', 'en').replace('/translations/en.json', '');

import { NORMAL_SVG, BYPASS_OPEN_SVG } from './airflow-diagrams.js';
import { CARD_STYLE } from './card-styles.js';
import {
  createCardHeader,
  createTopSection,
  createParameterEditSection,
  createControlsSection,
  createCardFooter,
} from './templates/card-templates.js';
import { createTemplateData } from './templates/template-helpers.js';
import './hvac-fan-card-editor.js';

// Import reusable helpers using environment-aware path constants
// import { SimpleCardTranslator } from '/local/ramses_extras/helpers/card-translations.js';
import { getRamsesMessageBroker } from '/local/ramses_extras/helpers/ramses-message-broker.js';
import { HvacFanCardHandlers } from './message-handlers.js';
import {
  callWebSocket,
  sendFanCommand,
  setFanParameter,
} from '/local/ramses_extras/helpers/card-services.js';
import {
  // validateCoreEntities,
  validateDehumidifyEntities,
  getEntityValidationReport,
} from '/local/ramses_extras/helpers/card-validation.js';


class HvacFanCard extends RamsesBaseCard {
  constructor() {
    super();

    // HVAC-specific state
    this.parameterEditMode = false;
    this.parameterSchema = null;
    this.availableParams = {};
    this._eventCheckTimer = null; // Timer for event checks
    this._stateCheckInterval = null; // Interval for state monitoring
    this._pollInterval = null; // Interval for polling
  }

  // ========== IMPLEMENT REQUIRED ABSTRACT METHODS ==========

  /**
   * Get card size for Home Assistant layout
   * @returns {number} Card size
   */
  getCardSize() {
    return 4;
  }

  /**
   * Get configuration element for HA editor
   * @returns {HTMLElement|null} Configuration element
   */
  getConfigElement() {
    try {
      // Ensure the editor is available before creating it
      if (typeof window.HvacFanCardEditor === 'undefined') {
        console.error('HvacFanCardEditor is not defined on window');
        return null;
      }
      return document.createElement('hvac-fan-card-editor');
    } catch (error) {
      console.error('Error creating config element:', error);
      return null;
    }
  }

  /**
   * Main rendering method
   */
  render() {
    if (!this._hass || !this.config) {
      console.error('❌ Missing hass or config:', {
        hass: !!this._hass,
        _config: !!this._config,
        config: !!this.config,
      });
      return;
    }

    // Check for required device_id at render time (not during initial creation)
    if (!this._config.device_id) {
      console.error('❌ Missing required device_id for HVAC fan card');
      this.shadowRoot.innerHTML = `
        <ha-card>
          <div style="padding: 16px; text-align: center; color: #666;">
            <ha-icon icon="mdi:alert-outline"></ha-icon>
            <div style="margin-top: 8px;">
              Device ID is required
            </div>
            <div style="font-size: 12px; margin-top: 4px; opacity: 0.8;">
              Please configure the card with a device_id to use this card
            </div>
          </div>
        </ha-card>
      `;
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

  // ========== OVERRIDE OPTIONAL METHODS ==========

  /**
   * Get default configuration
   * @returns {Object} Default configuration
   */
  getDefaultConfig() {
    return {
      name: 'HVAC Fan Card',
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
    if (!this._config?.device_id) {
      return {};
    }

    return {
      indoor_abs_humidity: this._config.indoor_abs_humid_entity,
      outdoor_abs_humidity: this._config.outdoor_abs_humid_entity,
      co2: this._config.co2_entity,
      dehum_mode: this._config.dehum_mode_entity,
      dehum_active: this._config.dehum_active_entity,
      comfort_temp: this._config.comfort_temp_entity,
    };
  }

  /**
   * Get message codes this card should listen for
   * @returns {Array<string>} Array of message codes
   */
  getMessageCodes() {
    return ['31DA', '10D0'];
  }

  /**
   * Get feature name for translation path resolution
   * @returns {string} Feature name
   */
  getFeatureName() {
    return 'hvac_fan_card';
  }

  /**
   * Get card info for HA registration
   * @returns {Object} Card registration info
   */
  static getCardInfo() {
    return {
      type: this.getTagName(),
      name: 'Hvac Fan Control Card',
      description: 'Advanced control card for Orcon or other ventilation systems with multi-language support',
      preview: true,
      documentationURL: 'https://github.com/wimpie70/ramses_extras',
    };
  }

  /**
   * Set card configuration with additional entity building
   * @param {Object} config - Card configuration
   */
  setConfig(config) {
    // Call parent setConfig for validation and basic processing
    super.setConfig(config);

    // If config is empty, return early
    if (!config || Object.keys(config).length === 0) {
      return;
    }

    // Additional processing: build entity IDs based on device_id
    const deviceId = this._config.device_id;

    // Add auto-generated entity IDs to config
    this._config = {
      ...this._config,
      // Auto-generate absolute humidity sensor entities (created by integration)
      indoor_abs_humid_entity: 'sensor.indoor_absolute_humidity_' + deviceId.replace(/:/g, '_'),
      outdoor_abs_humid_entity: 'sensor.outdoor_absolute_humidity_' + deviceId.replace(/:/g, '_'),
      // Fallback to calculated humidity if absolute humidity sensor don't exist
      indoor_temp_entity:
        this._config.indoor_temp_entity || 'sensor.' + deviceId.replace(/:/g, '_') + '_indoor_temp',
      outdoor_temp_entity:
        this._config.outdoor_temp_entity || 'sensor.' + deviceId.replace(/:/g, '_') + '_outdoor_temp',
      indoor_humidity_entity:
        this._config.indoor_humidity_entity ||
        'sensor.' + deviceId.replace(/:/g, '_') + '_indoor_humidity',
      outdoor_humidity_entity:
        this._config.outdoor_humidity_entity ||
        'sensor.' + deviceId.replace(/:/g, '_') + '_outdoor_humidity',
      supply_temp_entity:
        this._config.supply_temp_entity || 'sensor.' + deviceId.replace(/:/g, '_') + '_supply_temp',
      exhaust_temp_entity:
        this._config.exhaust_temp_entity || 'sensor.' + deviceId.replace(/:/g, '_') + '_exhaust_temp',
      fan_speed_entity:
        this._config.fan_speed_entity || 'sensor.' + deviceId.replace(/:/g, '_') + '_fan_rate',
      fan_mode_entity:
        this._config.fan_mode_entity || 'sensor.' + deviceId.replace(/:/g, '_') + '_fan_mode',
      co2_entity: this._config.co2_entity || 'sensor.' + deviceId.replace(/:/g, '_') + '_co2_level',
      flow_entity: this._config.flow_entity || 'sensor.' + deviceId.replace(/:/g, '_') + '_supply_flow',
      bypass_entity:
        this._config.bypass_entity || 'binary_sensor.' + deviceId.replace(/:/g, '_') + '_bypass_position',
      // Use configured entities if provided, otherwise auto-generate
      dehum_mode_entity:
        this._config.dehum_mode_entity || 'switch.dehumidify_' + deviceId.replace(/:/g, '_'),
      dehum_active_entity:
        this._config.dehum_active_entity ||
        'binary_sensor.dehumidifying_active_' + deviceId.replace(/:/g, '_'),
      comfort_temp_entity:
        this._config.comfort_temp_entity || 'number.' + deviceId.replace(/:/g, '_') + '_param_75',
    };
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
      hass: this._hass,
    };

    // Generate HTML for parameter edit mode
    const cardHtml = [
      createCardHeader(CARD_STYLE),
      createParameterEditSection(templateData),
      createCardFooter(),
    ].join('');

    this.shadowRoot.innerHTML = cardHtml;

    // Restore scroll position after DOM update
    const newScrollContainer = this.shadowRoot?.querySelector('.param-list');
    if (newScrollContainer) {
      newScrollContainer.scrollTop = scrollTop;
    }

    // Attach event listeners for parameter edit mode
    this.attachParameterEditListeners();
  }

  renderNormalMode() {
    // Validate entities are available
    this.validateEntities();

    const config = this.config; // Use config consistently
    const hass = this._hass;

    // Check dehumidify entity availability
    const dehumEntitiesAvailable = this.checkDehumidifyEntities();

    // Get data from 31DA messages
    const da31Data = this.get31DAData();

    // Temperature data
    const indoorTemp = da31Data.indoor_temp !== undefined ? da31Data.indoor_temp : null;

    const outdoorTemp = da31Data.outdoor_temp !== undefined ? da31Data.outdoor_temp : null;

    const supplyTemp = da31Data.supply_temp !== undefined ? da31Data.supply_temp : null;

    const exhaustTemp = da31Data.exhaust_temp !== undefined ? da31Data.exhaust_temp : null;

    // Humidity data
    const indoorHumidity = da31Data.indoor_humidity !== undefined ? da31Data.indoor_humidity : null;

    const outdoorHumidity =
      da31Data.outdoor_humidity !== undefined ? da31Data.outdoor_humidity : null;

    // Use ramses_extras absolute humidity sensor (if available) - raw values only
    const indoorAbsHumidity = hass.states[config.indoor_abs_humid_entity]?.state
      ? isNaN(parseFloat(hass.states[config.indoor_abs_humid_entity].state))
        ? null
        : parseFloat(hass.states[config.indoor_abs_humid_entity].state)
      : null;
    const outdoorAbsHumidity = hass.states[config.outdoor_abs_humid_entity]?.state
      ? isNaN(parseFloat(hass.states[config.outdoor_abs_humid_entity].state))
        ? null
        : parseFloat(hass.states[config.outdoor_abs_humid_entity].state)
      : null;

    // Get 10D0 data for filter information
    const da10D0Data = this.get10D0Data();

    // Fan data
    const rawData = {
      indoorTemp,
      outdoorTemp,
      indoorHumidity,
      outdoorHumidity,
      indoorAbsHumidity,
      outdoorAbsHumidity, // From integration sensor
      supplyTemp,
      exhaustTemp,
      // Fan data
      fanSpeed: this._getFanSpeed(da31Data),
      fanMode: this._getFanMode(da31Data),
      // Flow data
      flowRate: da31Data.supply_flow !== undefined ? da31Data.supply_flow : null,
      exhaustFlowRate: da31Data.exhaust_flow !== undefined ? da31Data.exhaust_flow : null,
      // Other data - raw values only
      co2Level: hass.states[config.co2_entity]?.state
        ? isNaN(parseFloat(hass.states[config.co2_entity].state))
          ? null
          : parseFloat(hass.states[config.co2_entity].state)
        : null,
      // Dehumidifier entities (only if available)
      dehumMode: dehumEntitiesAvailable
        ? hass.states[config.dehum_mode_entity]?.state || 'off'
        : null,
      dehumActive: dehumEntitiesAvailable
        ? hass.states[config.dehum_active_entity]?.state || 'off'
        : null,
      // Comfort temperature entity (will be available when created)
      comfortTemp: hass.states[config.comfort_temp_entity]?.state
        ? isNaN(parseFloat(hass.states[config.comfort_temp_entity].state))
          ? null
          : parseFloat(hass.states[config.comfort_temp_entity].state)
        : null,
      // Bypass position
      bypassPosition: da31Data.bypass_position !== undefined ? da31Data.bypass_position : null,
      dehumEntitiesAvailable, // Add availability flag
      dataSource31DA: da31Data.source === '31DA_message', // Flag for UI
      timerMinutes: da31Data.remaining_mins !== undefined ? da31Data.remaining_mins : 0,
      // Filter days remaining from 10D0 data
      filterDaysRemaining:
        da10D0Data.days_remaining !== undefined ? da10D0Data.days_remaining : null,
      // efficiency: 75   // Remove hardcoded value - let template calculate it
    };

    // create templateData for rendering
    const templateData = createTemplateData(rawData);
    // Add airflow SVG to template data
    const selectedSvg =
      rawData.bypassPosition !== null && rawData.bypassPosition > 0 ? BYPASS_OPEN_SVG : NORMAL_SVG;
    templateData.airflowSvg = selectedSvg;

    // Generate HTML using template functions
    const cardHtml = [
      createCardHeader(CARD_STYLE),
      createTopSection(templateData),
      createControlsSection(dehumEntitiesAvailable, config), // Pass availability flag and config
      createCardFooter(),
    ].join('');

    this.shadowRoot.innerHTML = cardHtml;

    // Attach event listeners for normal mode
    this.attachNormalModeListeners();
  }


  // Validate all required entities are available
  validateEntities() {
    // Note: config and hass are already validated in render() before this is called
    const config = this.config;
    const hass = this._hass;

    // Use the shared validation helper
    // eslint-disable-next-line no-unused-vars
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
        type: 'ramses_extras/get_2411_schema',
        device_id: this.config.device_id,
      });
      // console.log('Parameter schema received:', Object.keys(result));
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

    Object.keys(this._hass.states).forEach((entityId) => {
      if (entityId.startsWith(devicePrefix) && entityId.startsWith('number.')) {
        const entity = this._hass.states[entityId];
        const entityName = entityId.replace(devicePrefix, '');

        // Try to get description from 2411 schema if it's a param_ entity
        let description =
          entity.attributes?.friendly_name ||
          entityName.replace(/_/g, ' ').replace(/\b\w/g, (l) => l.toUpperCase());

        if (entityName.startsWith('param_')) {
          const paramKey = entityName.replace('param_', '').toUpperCase();
          if (this.parameterSchema && this.parameterSchema[paramKey]) {
            description =
              this.parameterSchema[paramKey].description || this.parameterSchema[paramKey].name;
          } else {
            // Fallback: try to create a readable description from the parameter key
            description = paramKey.replace(/_/g, ' ').replace(/\b\w/g, (l) => l.toUpperCase());
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
          precision: entity.attributes?.step || 1,
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
    // console.log(`🔄 Updating parameter ${paramKey} to ${newValue}`);

    const paramItem = this.shadowRoot?.querySelector(`[data-param="${paramKey}"]`);
    if (paramItem) {
      paramItem.classList.add('loading');
      paramItem.classList.remove('success', 'error');
    }

    try {
      // Extract the parameter ID from the entity name (e.g., "param_31" -> "31")
      const paramId = paramKey.startsWith('param_') ? paramKey.replace('param_', '') : paramKey;

      await setFanParameter(this._hass, this.config.device_id, paramId, newValue.toString());

      {
        // console.log(`✅ Parameter ${paramKey} update sent successfully via WebSocket`);
        if (paramItem) {
          paramItem.classList.remove('loading');
          paramItem.classList.add('success');
          setTimeout(() => paramItem.classList.remove('success'), 2000);
        }
      }
    } catch (error) {
      console.error(`❌ Failed to update parameter ${paramKey}:`, error);
      if (paramItem) {
        paramItem.classList.remove('loading');
        paramItem.classList.add('error');
      }
    }
  }

  // Add event listeners after the component is connected to the DOM
  connectedCallback() {
    // Register for real-time message updates if we have a device ID
    if (this._config?.device_id) {
      const messageHelper = getRamsesMessageBroker();
      messageHelper.addListener(this, this._config.device_id, ['31DA', '10D0']);

      // Request initial data when card is fully loaded
      this.requestInitialData();
    }
  }

  disconnectedCallback() {
    // Call parent's disconnectedCallback first to clean up cards_enabled subscription
    super.disconnectedCallback();

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

  // Message handler functions -
  // called automatically by (Global) RamsesMessageBroker
  // these were first registered in connectedCallback
  handle_31DA(messageData) {
    HvacFanCardHandlers.handle_31DA(this, messageData);
  }

  handle_10D0(messageData) {
    HvacFanCardHandlers.handle_10D0(this, messageData);
  }

  // Update functions

  // Request initial data when card is fully loaded
  async requestInitialData() {
    if (!this._hass || !this._config?.device_id) {
      console.warn('Cannot request initial data: missing hass or device_id');
      return;
    }

    try {
      const tempButton = this;
      window.send_command('fan_request31DA', this._config.device_id, tempButton);

      window.send_command('fan_request10D0', this._config.device_id, tempButton);
    } catch (error) {
      console.error('❌ Failed to request initial data:', error);
    }
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

    // Control buttons - only attach listeners to buttons without existing onclick handlers
    const controlButtons = this.shadowRoot?.querySelectorAll('.control-button');
    if (controlButtons) {
      controlButtons.forEach((button) => {
        // Skip buttons that already have onclick handlers
        if (!button.getAttribute('onclick')) {
          button.addEventListener('click', (e) => {
            e.preventDefault();
            e.stopPropagation();

            const onclick = button.getAttribute('onclick');
            if (onclick) {
              const fn = new Function(
                'event',
                `try { ${onclick} } catch(e) { console.error('Error in button handler:', e); }`
              );
              fn.call(button, e);
            }
          });
        }
      });
      // console.log(`✅ Attached event listeners to ${controlButtons.length - 1} control buttons (1 has onclick)`);
    }
  }

  // Attach event listeners for parameter edit mode
  attachParameterEditListeners() {
    // Back/settings icons in parameter edit mode
    const settingsIcon = this.shadowRoot?.querySelector('.settings-icon');
    const backIcon = this.shadowRoot?.querySelector('.back-icon');

    if (settingsIcon) {
      settingsIcon.addEventListener('click', (e) => {
        // console.log('🔙 Back icon clicked');
        e.preventDefault();
        e.stopPropagation();
        this.toggleParameterMode();
      });
    }

    if (backIcon) {
      backIcon.addEventListener('click', (e) => {
        // console.log('🔙 Back icon clicked');
        e.preventDefault();
        e.stopPropagation();
        this.toggleParameterMode();
      });
    }

    // Parameter update buttons - only attach to device parameter buttons, not humidity control buttons
    this.shadowRoot?.querySelectorAll('.param-update-btn');
    const deviceParamButtons = this.shadowRoot?.querySelectorAll('.param-update-btn[data-param]');

    if (deviceParamButtons) {
      deviceParamButtons.forEach((button) => {
        button.addEventListener('click', () => {
          const paramKey = button.getAttribute('data-param');
          const input = button.previousElementSibling;
          const newValue = input?.value;
          // console.log(`📝 Device parameter ${paramKey} update button clicked with value ${newValue}`);
          if (paramKey && newValue !== undefined) {
            this.updateParameter(paramKey, newValue);
          } else {
            console.error('❌ Missing paramKey or newValue:', { paramKey, newValue });
          }
        });
      });
      // console.log(`✅ ${deviceParamButtons.length} device parameter update button listeners attached`);
    }
  }
}

// Include the editor component
// This ensures the editor is loaded when the card is used

// Register the web component
if (!customElements.get('hvac-fan-card')) {
  // console.log('Registering hvac-fan-card web component');
  customElements.define('hvac-fan-card', HvacFanCard);
}

// Make functions globally available for onclick handlers
window.toggleParameterMode = function () {
  const card = document.querySelector('hvac-fan-card');
  if (card) {
    card.toggleParameterMode();
  }
};

window.updateParameter = function (paramKey, newValue) {
  const card = document.querySelector('hvac-fan-card');
  if (card) {
    card.updateParameter(paramKey, newValue);
  }
};

// controls min/max values
window.updateHumidityControl = function (entityId, newValue, buttonElement) {
  // console.log(`🔧 updateHumidityControl called with:`, { entityId, newValue, buttonElement });

  // Find the card element using the button element (similar to send_command)
  let element = buttonElement;
  while (element && element.tagName !== 'HVAC-FAN-CARD') {
    element = element.parentElement || element.getRootNode()?.host;
  }

  if (element && element._hass) {
    // console.log(`📡 Calling number.set_value service for ${entityId} = ${newValue}`);

    // Call Home Assistant service to update the entity
    element._hass
      .callService('number', 'set_value', {
        entity_id: entityId,
        value: parseFloat(newValue),
      })
      .then(() => {
        // console.log(`✅ Humidity control updated: ${entityId} = ${newValue}`);
        // Clear previous states to force update detection
        element._prevStates = null;
        // Trigger re-render
        if (element._hass && element.config) {
          element.render();
        }
      })
      .catch((error) => {
        console.error(`❌ Failed to update humidity control ${entityId}:`, error);
      });
  } else {
    console.error(`❌ Cannot update humidity control - missing card or hass:`, {
      element: !!element,
      hass: element?._hass,
    });
  }
};

window.toggleDehumidify = function (entityId, buttonElement) {
  // console.log(`🔧 toggleDehumidify called with:`, { entityId, buttonElement });

  // Find the card element using the button element (similar to send_command)
  let element = buttonElement;
  while (element && element.tagName !== 'HVAC-FAN-CARD') {
    element = element.parentElement || element.getRootNode()?.host;
  }

  if (element && element._hass) {
    // console.log(`📡 Toggling dehumidify switch ${entityId}`);

    // Toggle the switch using Home Assistant's toggle service
    element._hass
      .callService('switch', 'toggle', {
        entity_id: entityId,
      })
      .then(() => {
        // console.log(`✅ Dehumidify toggled: ${entityId}`);

        // Clear previous states to force update detection
        element._prevStates = null;

        // Wait a brief moment for the entity state to update, then trigger re-render
        setTimeout(() => {
          // console.log(`🔄 Re-rendering card after dehumidify toggle`);
          if (element._hass && element.config) {
            element.render();
          }
        }, 100); // 100ms delay to ensure state is updated
      })
      .catch((error) => {
        console.error(`❌ Failed to toggle dehumidify ${entityId}:`, error);
      });
  } else {
    console.error(`❌ Cannot toggle dehumidify - missing card or hass:`, {
      element: !!element,
      hass: element?._hass,
    });
  }
};


window.send_command = function (commandKey, deviceId, buttonElement) {
  // console.log(`window.send_command called with: ${commandKey}, deviceId: ${deviceId}, buttonElement:`, buttonElement);

  // Use the button element to find the host element
  let element = buttonElement;
  while (element && element.tagName !== 'HVAC-FAN-CARD') {
    element = element.parentElement || element.getRootNode()?.host;
  }

  if (element && element._hass) {
    //    console.log('Found HASS instance in host element, using proper from_id');

    (async () => {
      try {
        await sendFanCommand(element._hass, deviceId, commandKey);

        // Command sent successfully - Python queue handles all timing and processing
        // UI will update automatically when device state changes via WebSocket messages
        // console.log(`✅ Command '${commandKey}' queued for device ${deviceId}`);
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

if (!window.customCards.some((card) => card.type === 'hvac-fan-card')) {
  window.customCards.push({
    type: 'hvac-fan-card',
    name: 'Hvac Fan Control Card',
    description:
      'Advanced control card for Orcon or other ventilation systems with multi-language support',
    preview: true, // Shows in card picker
    documentationURL: 'https://github.com/wimpie70/ramses_extras',
  });
}
