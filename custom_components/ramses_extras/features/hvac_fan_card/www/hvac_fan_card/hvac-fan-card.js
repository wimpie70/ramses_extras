/* global customElements */
/* global setTimeout */
/* global clearTimeout */
/* global clearInterval */

import * as logger from '../../helpers/logger.js';

// Import the base card class
import { RamsesBaseCard } from '../../helpers/ramses-base-card.js';

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

import { HvacFanCardHandlers } from './message-handlers.js';
import {
  callWebSocket,
  sendFanCommand,
  setFanParameter,
  refreshFanParameters,
} from '../../helpers/card-services.js';
import {
  // validateCoreEntities,
  validateDehumidifyEntities,
  getEntityValidationReport,
} from '../../helpers/card-validation.js';

class HvacFanCard extends RamsesBaseCard {
  constructor() {
    super();

    // HVAC-specific state
    this.parameterEditMode = false;
    this._cachedEntities = null; // Cache for getRequiredEntities
    this._entityMappings = null;
    this._entityMappingsLoading = false;
    this._sensorSources = null; // Store sensor source information
    this._rawInternalMappings = null; // Store raw internal mappings
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
  static getConfigElement() {
    try {
      if (typeof window.HvacFanCardEditor === 'undefined') {
        logger.error('HvacFanCardEditor is not defined on window');
        return null;
      }
      return document.createElement('hvac-fan-card-editor');
    } catch (error) {
      logger.error('Error creating config element:', error);
      return null;
    }
  }

  static getStubConfig() {
    return {
      type: `custom:${this.getTagName()}`,
      ...this.prototype.getDefaultConfig(),
    };
  }

  getConfigElement() {
    try {
      // Ensure the editor is available before creating it
      if (typeof window.HvacFanCardEditor === 'undefined') {
        logger.error('HvacFanCardEditor is not defined on window');
        return null;
      }
      return document.createElement('hvac-fan-card-editor');
    } catch (error) {
      logger.error('Error creating config element:', error);
      return null;
    }
  }

  /**
   * Card-specific rendering implementation
   */
  _renderContent() {
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
   * Set card configuration
   * @param {Object} config - Card configuration
   */
  setConfig(config) {
    super.setConfig(config);
  }

  /**
   * Load initial state including entity mappings
   */
  async _loadInitialState() {
    if (!this._hass || !this._config?.device_id) {
      return;
    }

    try {
      await this._loadEntityMappings();
      this.render();
    } catch (error) {
      logger.warn('HvacFanCard: Failed to load initial state:', error);
      this.render();
    } finally {
      this.clearUpdateThrottle();
    }
  }

  async _loadEntityMappings() {
    if (!this._hass || !this._config?.device_id) {
      return;
    }

    if (this._entityMappingsLoading) {
      return;
    }

    this._entityMappingsLoading = true;

    try {
      const result = await this._sendWebSocketCommand({
        type: 'ramses_extras/get_entity_mappings',
        device_id: this._config.device_id,
        feature_id: 'hvac_fan_card',
      }, `hvac_fan_mappings_${this._config.device_id}`);

      if (result.mappings) {
        // Cache mappings for base getRequiredEntities()
        this._cachedEntities = result.mappings;

        // Store sensor control sources if available
        if (result.sources) {
          this._sensorSources = result.sources;
        }

        // Store raw internal mappings if available
        if (result.raw_internal) {
          this._rawInternalMappings = result.raw_internal;
        }

        // Merge entity mappings into config, but keep any explicit overrides
        const updatedConfig = { ...this._config };
        Object.entries(result.mappings).forEach(([key, value]) => {
          if (
            updatedConfig[key] === undefined ||
            updatedConfig[key] === null ||
            updatedConfig[key] === ''
          ) {
            updatedConfig[key] = value;
          }
        });

        this._config = updatedConfig;
        this._entityMappings = { ...(this._entityMappings || {}), ...result.mappings };
      }
    } catch (error) {
      logger.warn('HvacFanCard: Failed to load entity mappings:', error);
    } finally {
      this._entityMappingsLoading = false;
    }
  }

  /**
   * Create sensor source indicator HTML for a given metric
   * @param {string} metric - The metric name (e.g., 'indoor_temperature')
   * @returns {string} HTML string for the sensor source indicator
   */
  _createSensorSourceIndicator(metric) {
    if (!this._sensorSources || !this._sensorSources[metric]) {
      return '';
    }

    const source = this._sensorSources[metric];
    const { kind, entity_id, valid = true } = source;

    // Don't show indicators for internal sensors (default behavior)
    if (kind === 'internal') {
      return '';
    }

    // Define display configuration for different metrics
    const metricConfig = {
      indoor_temperature: { icon: '🌡️', label: 'Indoor Temp' },
      indoor_humidity: { icon: '💧', label: 'Indoor Humidity' },
      outdoor_temperature: { icon: '🌡️', label: 'Outdoor Temp' },
      outdoor_humidity: { icon: '💧', label: 'Outdoor Humidity' },
      co2: { icon: '🫧', label: 'CO₂' },
      indoor_abs_humidity: { icon: '💨', label: 'Indoor Abs Humidity' },
      outdoor_abs_humidity: { icon: '💨', label: 'Outdoor Abs Humidity' },
    };

    const config = metricConfig[metric] || { icon: '📊', label: metric };

    // Determine status and styling
    let statusClass = 'sensor-source-external';
    let statusText = '';
    let displayEntity = '';

    if (kind === 'external_entity' || kind === 'external') {
      if (valid && entity_id) {
        statusClass = 'sensor-source-external valid';
        statusText = `External: ${entity_id}`;
        displayEntity = entity_id;
      } else {
        statusClass = 'sensor-source-external invalid';
        statusText = 'External: Invalid Entity';
        displayEntity = entity_id || 'Invalid';
      }
    } else if (kind === 'derived') {
      statusClass = 'sensor-source-derived';
      // For derived sensors, show the actual entity being used from mappings
      const actualEntity = this._entityMappings?.[metric];
      if (actualEntity) {
        statusText = `Derived: ${actualEntity}`;
        displayEntity = actualEntity;
      } else {
        statusText = 'Derived Sensor';
        displayEntity = 'Calculated';
      }
    } else if (kind === 'none') {
      statusClass = 'sensor-source-disabled';
      statusText = 'Disabled';
      displayEntity = 'Disabled';
    }

    return `
      <div class="sensor-source-indicator ${statusClass}" title="${statusText}">
        <span class="sensor-source-icon">${config.icon}</span>
        <span class="sensor-source-label">${config.label}</span>
        <span class="sensor-source-kind">${kind}</span>
        <span class="sensor-source-entity">${displayEntity}</span>
      </div>
    `;
  }

  /**
   * Create a comprehensive sensor sources panel for the card
   * @returns {string} HTML string for the sensor sources panel
   */
  _createSensorSourcesPanel() {
    if (!this._sensorSources) {
      return '';
    }

    const metrics = [
      'indoor_temperature',
      'indoor_humidity',
      'co2',
      'outdoor_temperature',
      'outdoor_humidity',
      'indoor_abs_humidity',
      'outdoor_abs_humidity',
    ];

    const indicators = metrics
      .map(metric => this._createSensorSourceIndicator(metric))
      .filter(html => html.trim() !== '');

    if (indicators.length === 0) {
      return '';
    }

    return `
      <div class="sensor-sources-panel">
        <div class="sensor-sources-title">Sensor Sources</div>
        <div class="sensor-sources-grid">
          ${indicators.join('')}
        </div>
      </div>
    `;
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
      this._createSensorSourcesPanel(), // Add sensor sources panel in settings
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
    if (!this._entityMappings && !this._entityMappingsLoading) {
      this._loadEntityMappings();
    }

    // Validate entities are available
    this.validateEntities();

    const config = this.config || {};

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
    const indoorAbsHumidity = this.getEntityStateAsNumber(
      config.indoor_abs_humid_entity,
      null
    );
    const outdoorAbsHumidity = this.getEntityStateAsNumber(
      config.outdoor_abs_humid_entity,
      null
    );

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
      exhaustFanSpeed: this._formatSpeed(da31Data.exhaust_fan_speed),
      supplyFanSpeed: this._formatSpeed(da31Data.supply_fan_speed),
      fanMode: this._getFanMode(da31Data),
      // Flow data
      supplyFlowRate: da31Data.supply_flow !== undefined ? da31Data.supply_flow : null,
      exhaustFlowRate: da31Data.exhaust_flow !== undefined ? da31Data.exhaust_flow : null,
      // Other data - raw values only
      // Prefer sensor_control-resolved CO2 mapping (config.co2) when available,
      // fall back to the original co2_entity from feature constants.
      co2Level: this.getEntityStateAsNumber(config.co2 || config.co2_entity, null),
      // Dehumidifier entities (only if available)
      dehumMode: dehumEntitiesAvailable
        ? this.getEntityState(config.dehum_mode_entity)?.state || 'off'
        : null,
      dehumActive: dehumEntitiesAvailable
        ? this.getEntityState(config.dehum_active_entity)?.state || 'off'
        : null,
      // Comfort temperature entity (will be available when created)
      comfortTemp: this.getEntityStateAsNumber(config.comfort_temp_entity, null),
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
      logger.error('Failed to fetch parameter schema:', error);
      return {};
    }
  }

  // Get available parameters based on entity existence
  getAvailableParameters() {
    // Check all possible number entities for this device
    const available = {};

    const deviceId = this.config?.device_id;
    if (!deviceId) return available;

    // Get all states and filter for this device's number entities
    const devicePrefix = `number.${deviceId.replace(/:/g, '_')}_`;

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
            logger.debug(
              `📋 No schema found for ${paramKey}, using fallback: ${description}`
            );
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
      logger.error(`❌ Failed to update parameter ${paramKey}:`, error);
      if (paramItem) {
        paramItem.classList.remove('loading');
        paramItem.classList.add('error');
      }
    }
  }

  // Refresh all parameters (2411 sequence)
  async refreshParameters() {
    const refreshBtn = this.shadowRoot?.querySelector('.refresh-params-btn');
    if (refreshBtn) {
      refreshBtn.classList.add('loading');
    }

    try {
      await refreshFanParameters(this._hass, this.config.device_id);
      // Success feedback
      if (refreshBtn) {
        refreshBtn.classList.remove('loading');
        refreshBtn.classList.add('success');
        setTimeout(() => refreshBtn.classList.remove('success'), 2000);
      }
    } catch (error) {
      logger.error('❌ Failed to refresh parameters:', error);
      if (refreshBtn) {
        refreshBtn.classList.remove('loading');
        refreshBtn.classList.add('error');
        setTimeout(() => refreshBtn.classList.remove('error'), 2000);
      }
    }
  }

  _onConnected() {
    if (this._config?.device_id) {
      this.requestInitialData();
    }
  }

  _onDisconnected() {
    if (this._eventCheckTimer) {
      clearTimeout(this._eventCheckTimer);
      this._eventCheckTimer = null;
    }

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
      logger.warn('Cannot request initial data: missing hass or device_id');
      return;
    }

    try {
      const tempButton = this;
      window.send_command('fan_request31DA', this._config.device_id, tempButton);

      window.send_command('fan_request10D0', this._config.device_id, tempButton);
    } catch (error) {
      logger.error('❌ Failed to request initial data:', error);
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

  // Format speed value consistently
  _formatSpeed(speed) {
    if (speed === undefined || speed === null) {
      return null;
    }
    return `${Math.round(speed * 100)}%`;
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
                `try { ${onclick} } catch(e) { window.ramsesExtrasLogger?.error('Error in button handler:', e); }`
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
            logger.error('❌ Missing paramKey or newValue:', { paramKey, newValue });
          }
        });
      });
      // console.log(`✅ ${deviceParamButtons.length} device parameter update button listeners attached`);
    }

    // Refresh button
    const refreshBtn = this.shadowRoot?.querySelector('.refresh-params-btn');
    if (refreshBtn) {
      refreshBtn.addEventListener('click', (e) => {
        e.preventDefault();
        e.stopPropagation();
        this.refreshParameters();
      });
    }
  }
}

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
        logger.error(`❌ Failed to update humidity control ${entityId}:`, error);
      });
  } else {
    logger.error(`❌ Cannot update humidity control - missing card or hass:`, {
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
        logger.error(`❌ Failed to toggle dehumidify ${entityId}:`, error);
      });
  } else {
    logger.error(`❌ Cannot toggle dehumidify - missing card or hass:`, {
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
        logger.error('Error sending command:', error);
      }
    })();
  } else {
    logger.error('Could not find HASS instance in host element');
    logger.debug('Element found:', element);
    logger.debug('Element _hass:', element?._hass);
  }
};


// Register the card using the base class registration
HvacFanCard.register();
