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

/**
 * HVAC ventilation control card.
 *
 * Renders live ventilation data and exposes controls via service/WebSocket
 * helpers. Also provides a settings mode for editing 2411 parameters.
 * Interacts with:
 * - Humid Control feature (enable/disable), Edit settings
 * - Default feature (absolute humidity)
 * - Sensor Control (resolve mapped entities)
 */
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
    this._domInitialized = false;
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

  /**
   * Create the card editor element (instance method for HA UI).
   * @returns {HTMLElement|null} The editor element.
   */
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
    if (!this._domInitialized) {
      this._initializeDOM();
      this._domInitialized = true;
    }
    this._updateDOM();
  }

  _initializeDOM() {
    // Create a basic static structure that can be updated for both modes
    this.shadowRoot.innerHTML = `
      <style>
        ${CARD_STYLE}
      </style>
      <ha-card>
        <div id="cardContent">
          <!-- Content will be dynamically updated -->
        </div>
      </ha-card>
    `;

    this._attachEventListeners();
  }

  _attachEventListeners() {
    return;
  }

  _updateDOM() {
    const cardContent = this.shadowRoot.getElementById('cardContent');
    if (!cardContent) return;

    // Check if we're in parameter edit mode
    if (this.parameterEditMode) {
      this._updateParameterEditMode(cardContent);
    } else {
      this._updateNormalMode(cardContent);
    }
  }

  async _updateParameterEditMode(container) {
    // Save scroll position before re-rendering
    const scrollContainer = this.shadowRoot?.querySelector('.param-list');
    const scrollTop = scrollContainer?.scrollTop || 0;

    // Ensure we have the parameter schema
    if (!this.parameterSchema) {
      this.parameterSchema = await this.fetchParameterSchema();
    }

    // Get available parameters based on entity existence
    this.availableParams = this.getAvailableParameters();

    const humidityControlEntities = this._getHumidityControlEntities();
    const parameterItems = this._createParameterItems(this.availableParams);

    const templateData = {
      device_id: this.config.device_id,
      humidityControlEntities,
      parameterItems,
      t: this.t?.bind(this),
    };

    // Generate HTML for parameter edit mode
    const cardHtml = [
      createCardHeader(CARD_STYLE),
      this._createSensorSourcesPanel(), // Add sensor sources panel in settings
      createParameterEditSection(templateData),
      createCardFooter(),
    ].join('');

    container.innerHTML = cardHtml;

    // Restore scroll position after DOM update
    const newScrollContainer = this.shadowRoot?.querySelector('.param-list');
    if (newScrollContainer) {
      newScrollContainer.scrollTop = scrollTop;
    }

    // Attach event listeners for parameter edit mode
    this.attachParameterEditListeners();
  }

  _updateNormalMode(container) {
    if (!this._entityMappings && !this._entityMappingsLoading) {
      this._loadEntityMappings();
    }

    const config = this.config;
    const hass = this._hass;

    // Collect live data
    const { da31Data, da10D0Data } = this._collectLiveData();
    const dehumEntitiesAvailable = validateDehumidifyEntities(hass, config)?.available === true;

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

    const rawData = {
      indoorTemp,
      outdoorTemp,
      indoorHumidity,
      outdoorHumidity,
      indoorAbsHumidity,
      outdoorAbsHumidity,
      supplyTemp,
      exhaustTemp,
      exhaustFanSpeed: this._formatSpeed(da31Data.exhaust_fan_speed),
      supplyFanSpeed: this._formatSpeed(da31Data.supply_fan_speed),
      fanMode: this._getFanMode(da31Data),
      supplyFlowRate: da31Data.supply_flow !== undefined ? da31Data.supply_flow : null,
      exhaustFlowRate: da31Data.exhaust_flow !== undefined ? da31Data.exhaust_flow : null,
      co2Level: this.getEntityStateAsNumber(config.co2 || config.co2_entity, null),
      dehumMode: dehumEntitiesAvailable
        ? this.getEntityState(config.dehum_mode_entity)?.state || 'off'
        : null,
      dehumActive: dehumEntitiesAvailable
        ? this.getEntityState(config.dehum_active_entity)?.state || 'off'
        : null,
      comfortTemp: this.getEntityStateAsNumber(config.comfort_temp_entity, null),
      bypassPosition: da31Data.bypass_position !== undefined ? da31Data.bypass_position : null,
      dehumEntitiesAvailable,
      dataSource31DA: da31Data.source === '31DA_message',
      timerMinutes: da31Data.remaining_mins !== undefined ? da31Data.remaining_mins : 0,
      filterDaysRemaining:
        da10D0Data.days_remaining !== undefined ? da10D0Data.days_remaining : null,
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
      createTopSection(templateData, this.t?.bind(this)),
      createControlsSection(
        dehumEntitiesAvailable,
        config,
        this.t?.bind(this)
      ), // Pass availability flag and config
      createCardFooter(),
    ].join('');

    container.innerHTML = cardHtml;

    // Attach event listeners for normal mode
    this.attachNormalModeListeners();
  }

  _collectLiveData() {
    const da31Data = typeof this.get31DAData === 'function' ? this.get31DAData() : {};
    const da10D0Data = typeof this.get10D0Data === 'function' ? this.get10D0Data() : {};
    return { da31Data, da10D0Data };
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

  /**
   * Load entity mappings and sensor sources for this device via WebSocket.
   *
   * Populates `_cachedEntities` for the base class required-entities logic and
   * merges returned entity IDs into the config when not explicitly overridden.
   *
   * @returns {Promise<void>}
   */
  async _loadEntityMappings() {
    if (!this._hass || !this._config?.device_id) {
      return;
    }

    if (this._entityMappingsLoading) {
      return;
    }

    // Check for version mismatch - don't retry if there's a mismatch
    if (window.ramsesExtras?._versionMismatch) {
      this._entityMappingsLoadFailed = true;
      return;
    }

    // Don't retry if we already failed due to version mismatch
    if (this._entityMappingsLoadFailed) {
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
      // If it's a version mismatch error, stop retrying
      if (error?.version_mismatch || error?.code === 'version_mismatch') {
        this._entityMappingsLoadFailed = true;
        logger.warn('HvacFanCard: Version mismatch detected - stopping entity mapping retries');
      } else {
        logger.warn('HvacFanCard: Failed to load entity mappings:', error);
      }
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

    const panelTitle = this.t?.('sensor.sources') || 'Sensor Sources';

    return `
      <div class="sensor-sources-panel">
        <div class="sensor-sources-title">${panelTitle}</div>
        <div class="sensor-sources-grid">
          ${indicators.join('')}
        </div>
      </div>
    `;
  }


  /**
   * Render normal mode (live dashboard).
   *
   * Collects state, builds template data, and wires normal-mode listeners.
   * @returns {void}
   */
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
      createTopSection(templateData, this.t?.bind(this)),
      createControlsSection(
        dehumEntitiesAvailable,
        config,
        this.t?.bind(this)
      ), // Pass availability flag and config
      createCardFooter(),
    ].join('');

    this.shadowRoot.innerHTML = cardHtml;

    // Attach event listeners for normal mode
    this.attachNormalModeListeners();
  }


  // Validate all required entities are available
  /**
   * Validate configured entities exist.
   * Uses framework validation helpers; the report is currently informational.
   * @returns {void}
   */
  validateEntities() {
    // Note: config and hass are already validated in render() before this is called
    const config = this.config;
    const hass = this._hass;

    // Use the shared validation helper
    // eslint-disable-next-line no-unused-vars
    const validationReport = getEntityValidationReport(hass, config);
  }

  // Check if dehumidify entities are available
  /**
   * Check whether the dehumidify related entities exist.
   * @returns {boolean} True if dehumidify entities are available.
   */
  checkDehumidifyEntities() {
    // Note: config and hass are already validated in render() before this is called
    const config = this.config;
    const hass = this._hass;

    // Use the shared validation helper
    const dehumValidation = validateDehumidifyEntities(hass, config);
    return dehumValidation.available;
  }

  // Toggle between normal and parameter edit modes
  /**
   * Toggle between normal mode and parameter edit mode.
   * @returns {Promise<void>}
   */
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
  /**
   * Fetch the 2411 parameter schema via WebSocket.
   * @returns {Promise<Object>} Schema mapping.
   */
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
  /**
   * Build a map of available number entities for this device.
   * Uses entity attributes and (if available) the 2411 schema.
   * @returns {Object} Map of entityName -> paramInfo.
   */
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

  /**
   * Build view-model items for humidity control number entities.
   * @returns {Array<Object>} Items for the settings template.
   */
  _getHumidityControlEntities() {
    const deviceId = this.config?.device_id;
    if (!deviceId) return [];

    const hass = this._hass;
    if (!hass) return [];

    const humidityControlEntities = [];
    const deviceIdUnderscore = deviceId.replace(/:/g, '_');

    const humidityEntities = [
      `number.relative_humidity_minimum_${deviceIdUnderscore}`,
      `number.relative_humidity_maximum_${deviceIdUnderscore}`,
      `number.absolute_humidity_offset_${deviceIdUnderscore}`,
    ];

    humidityEntities.forEach((entityId) => {
      const stateObj = hass.states?.[entityId];
      if (!stateObj) return;

      const attributes = stateObj.attributes || {};

      let nameKey = null;
      let nameFallback = null;

      if (entityId.includes('minimum')) {
        nameKey = 'parameters.humidity_minimum_relative';
        nameFallback = 'Minimum Relative Humidity';
      } else if (entityId.includes('maximum')) {
        nameKey = 'parameters.humidity_maximum_relative';
        nameFallback = 'Maximum Relative Humidity';
      } else if (entityId.includes('absolute_humidity_offset')) {
        nameKey = 'parameters.humidity_absolute_offset';
        nameFallback = 'Absolute Humidity Offset';
      }

      humidityControlEntities.push({
        entity_id: entityId,
        state: stateObj.state,
        attributes,
        name_key: nameKey,
        name_fallback: nameFallback,
      });
    });

    return humidityControlEntities;
  }

  /**
   * Build view-model items for 2411 `param_*` entities.
   * @param {Object} availableParams Map from `getAvailableParameters()`.
   * @returns {Array<Object>} Items for the settings template.
   */
  _createParameterItems(availableParams) {
    const deviceId = this.config?.device_id;
    if (!deviceId) return [];

    const deviceIdUnderscore = deviceId.replace(/:/g, '_');

    return Object.entries(availableParams || {})
      .filter(([paramKey]) => paramKey.startsWith('param_'))
      .map(([paramKey, paramInfo]) => {
      const entityId = `number.${deviceIdUnderscore}_${paramKey}`;

      const rawValue =
        paramInfo?.current_value ??
        paramInfo?.default_value ??
        paramInfo?.min_value ??
        0;

      let value = rawValue;
      if (Number.isInteger(paramInfo?.precision)) {
        const parsed = parseFloat(String(rawValue));
        value = Number.isNaN(parsed) ? rawValue : Math.round(parsed);
      }

      return {
        paramKey,
        entity_id: entityId,
        description: paramInfo?.description,
        unit: paramInfo?.unit || paramInfo?.data_unit || '',
        min: paramInfo?.min_value,
        max: paramInfo?.max_value,
        step: paramInfo?.precision,
        value,
      };
    });
  }

  // Update a parameter value
  /**
   * Update a 2411 parameter using the card WebSocket helper.
   * @param {string} paramKey Parameter key (e.g. `param_31`).
   * @param {string|number} newValue New value.
   * @returns {Promise<void>}
   */
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
  /**
   * Request a full parameter refresh sequence.
   * @returns {Promise<void>}
   */
  async refreshParameters() {
    const refreshBtn = this.shadowRoot?.querySelector('.r-xtrs-hvac-fan-refresh-params-btn');
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

  /**
   * Connection lifecycle hook (called by base card).
   * @returns {void}
   */
  _onConnected() {
    if (this._config?.device_id) {
      this.requestInitialData();
    }
  }

  /**
   * Connection lifecycle hook (called by base card).
   * Clears timers/intervals.
   * @returns {void}
   */
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
  /**
   * Request initial 31DA/10D0 data from the device.
   * @returns {Promise<void>}
   */
  async requestInitialData() {
    if (!this._hass || !this._config?.device_id) {
      logger.warn('Cannot request initial data: missing hass or device_id');
      return;
    }

    try {
      await sendFanCommand(this._hass, this._config.device_id, 'fan_request31DA');
      await sendFanCommand(this._hass, this._config.device_id, 'fan_request10D0');
    } catch (error) {
      logger.error('❌ Failed to request initial data:', error);
    }
  }

  // Update the card with 31DA data
  /**
   * Update internal state from a 31DA message and re-render.
   * @param {Object} hvacData Parsed 31DA data.
   * @returns {void}
   */
  updateFrom31DA(hvacData) {
    // Store the data for rendering
    this._31daData = hvacData;

    // Force a re-render to show updated data
    if (this._hass && this.config) {
      this.render();
    }
  }

  // Update the card with 10D0 data
  /**
   * Update internal state from a 10D0 message and re-render.
   * @param {Object} filterData Parsed 10D0 data.
   * @returns {void}
   */
  updateFrom10D0(filterData) {
    // Store the filter data for rendering
    this._10d0Data = filterData;

    // Force a re-render to show updated data
    if (this._hass && this.config) {
      this.render();
    }
  }

  // Get 31DA data (if available) for template rendering
  /**
   * Get last received 31DA data.
   * @returns {Object}
   */
  get31DAData() {
    return this._31daData || {};
  }

  // Get 10D0 data (if available) for template rendering
  /**
   * Get last received 10D0 data.
   * @returns {Object}
   */
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
  /**
   * Attach click handlers for the normal mode UI.
   * @returns {void}
   */
  attachNormalModeListeners() {
    // Settings icon in top section
    const settingsIcon = this.shadowRoot?.querySelector('.r-xtrs-hvac-fan-settings-icon');
    if (settingsIcon) {
      settingsIcon.addEventListener('click', (e) => {
        e.preventDefault();
        e.stopPropagation();
        this.toggleParameterMode();
      });
    }

    // Control buttons - handle via data attributes
    const controlButtons = this.shadowRoot?.querySelectorAll('.r-xtrs-hvac-fan-control-button');
    if (controlButtons) {
      controlButtons.forEach((button) => {
        button.addEventListener('click', async (e) => {
          e.preventDefault();
          e.stopPropagation();

          const command = button.getAttribute('data-command');
          const deviceId = button.getAttribute('data-device-id');
          const action = button.getAttribute('data-action');
          const entityId = button.getAttribute('data-entity-id');

          if (command && deviceId) {
            // Fan command button
            try {
              await sendFanCommand(this._hass, deviceId, command);
            } catch (error) {
              logger.error('Error sending command:', error);
            }
          } else if (action === 'toggle-dehumidify' && entityId) {
            // Dehumidify toggle button
            try {
              await this._hass.callService('switch', 'toggle', { entity_id: entityId });
              this._prevStates = null;
              setTimeout(() => {
                if (this._hass && this.config) {
                  this.render();
                }
              }, 100);
            } catch (error) {
              logger.error(`Failed to toggle dehumidify ${entityId}:`, error);
            }
          }
        });
      });
    }
  }

  // Attach event listeners for parameter edit mode
  /**
   * Attach click handlers for the parameter edit UI.
   * @returns {void}
   */
  attachParameterEditListeners() {
    // Back/settings icons in parameter edit mode
    const settingsIcon = this.shadowRoot?.querySelector('.r-xtrs-hvac-fan-settings-icon');
    const backIcon = this.shadowRoot?.querySelector('.r-xtrs-hvac-fan-back-icon');

    if (settingsIcon) {
      settingsIcon.addEventListener('click', (e) => {
        e.preventDefault();
        e.stopPropagation();
        this.toggleParameterMode();
      });
    }

    if (backIcon) {
      backIcon.addEventListener('click', (e) => {
        e.preventDefault();
        e.stopPropagation();
        this.toggleParameterMode();
      });
    }

    // Parameter update buttons - handle both device parameters and humidity control
    const allUpdateButtons = this.shadowRoot?.querySelectorAll('.r-xtrs-hvac-fan-param-update-btn');

    if (allUpdateButtons) {
      allUpdateButtons.forEach((button) => {
        button.addEventListener('click', async () => {
          const paramKey = button.getAttribute('data-param');
          const action = button.getAttribute('data-action');
          const entityId = button.getAttribute('data-entity-id');
          const input = button.previousElementSibling;
          const newValue = input?.value;

          if (paramKey && newValue !== undefined) {
            // Device parameter update (2411)
            this.updateParameter(paramKey, newValue);
          } else if (action === 'update-humidity' && entityId && newValue !== undefined) {
            // Humidity control update
            try {
              await this._hass.callService('number', 'set_value', {
                entity_id: entityId,
                value: parseFloat(newValue),
              });
              this._prevStates = null;
              this.render();
            } catch (error) {
              logger.error(`Failed to update humidity control ${entityId}:`, error);
            }
          }
        });
      });
      // console.log(`✅ ${deviceParamButtons.length} device parameter update button listeners attached`);
    }

    // Refresh button
    const refreshBtn = this.shadowRoot?.querySelector('.r-xtrs-hvac-fan-refresh-params-btn');
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
const ExistingHvacFanCard = customElements.get('hvac-fan-card');
if (!ExistingHvacFanCard) {
  // console.log('Registering hvac-fan-card web component');
  customElements.define('hvac-fan-card', HvacFanCard);
} else if (ExistingHvacFanCard?.prototype) {
  const patchableMethods = ['_collectLiveData', '_attachEventListeners'];
  for (const methodName of patchableMethods) {
    if (
      typeof ExistingHvacFanCard.prototype[methodName] !== 'function'
      && typeof HvacFanCard.prototype[methodName] === 'function'
    ) {
      ExistingHvacFanCard.prototype[methodName] = HvacFanCard.prototype[methodName];
    }
  }
}

// Register the card using the base class registration
HvacFanCard.register();
