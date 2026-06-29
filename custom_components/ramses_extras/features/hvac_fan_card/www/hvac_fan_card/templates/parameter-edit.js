
/**
 * Parameter Edit Template
 * Provides UI for editing 2411 device parameters
 */

/**
 * Render the parameter edit/settings view.
 *
 * @param {Object} params Template parameters.
 * @param {string} params.device_id Device id (`32:123456` or `32_123456`).
 * @param {Array<Object>} [params.humidityControlEntities] Humidity control view-model.
 * @param {Array<Object>} [params.parameterItems] 2411 parameter view-model.
 * @param {Function} [params.t] Optional translation function.
 * @returns {string} HTML string.
 */
export function createParameterEditSection(params) {
  const deviceId = params.device_id;
  const humidityControlEntities = params.humidityControlEntities || [];
  const parameterItems = params.parameterItems || [];
  const t = params.t;

  const tr = (key, fallback, options = {}) => {
    try {
      if (typeof t === 'function') {
        const result = t(key, options);
        // t() returns '' for missing keys, so also check for non-empty
        if (typeof result === 'string' && result !== key && result !== '') {
          return result;
        }
      }
    } catch {
      // ignore and fall back
    }
    return fallback;
  };

  const settingsText = tr('card.settings', 'Settings');

  const humidityEntities = getHumidityControlEntities(humidityControlEntities);
  const deviceParameters = getDeviceParameters(parameterItems);

  return `
    <div class="r-xtrs-hvac-fan-parameter-edit-section">
      <!-- Navigation Header -->
      <div class="r-xtrs-hvac-fan-param-nav">
        <div class="r-xtrs-hvac-fan-nav-left">
          <span class="r-xtrs-hvac-fan-settings-icon">⚙️</span>
          <span class="r-xtrs-hvac-fan-device-title">${settingsText}: ${deviceId.replace(/_/g, ':')}</span>
        </div>
        <div class="r-xtrs-hvac-fan-nav-right">
          <span class="r-xtrs-hvac-fan-back-icon">↩️</span>
        </div>
      </div>

      ${humidityEntities.length > 0 ? `
      <!-- Humidity Control Settings Section -->
      <div class="r-xtrs-hvac-fan-param-section-header">
        <h3>${tr('parameters.humidity_control_settings', 'Humidity Control Settings')}</h3>
      </div>
      <div class="r-xtrs-hvac-fan-param-list" style="max-height: 200px; overflow-y: auto;">
        ${humidityEntities.map(entity =>
          createHumidityControlItem(entity, tr)
        ).join('')}
      </div>
      ` : ''}

      ${(params.tempControlEntities && params.tempControlEntities.length > 0) || params.tempControlSettings ? `
      <!-- Temp Control Settings Section -->
      <div class="r-xtrs-hvac-fan-param-section-header">
        <h3>${tr('parameters.temp_control_settings', 'Temperature Control Settings')}</h3>
      </div>
      <div class="r-xtrs-hvac-fan-param-list" style="max-height: 300px; overflow-y: auto;">
        ${params.tempControlEntities ? params.tempControlEntities.map(entity =>
          createTempControlItem(entity, tr)
        ).join('') : ''}
        ${params.comfortTempValue ? createComfortTempItem(params.comfortTempValue, tr) : ''}
        ${params.tempControlSettings ? createTempControlSettingItems(params.tempControlSettings, tr) : ''}
      </div>
      ` : ''}

      ${deviceParameters.length > 0 ? `
      <!-- Device Parameters Section -->
      <div class="r-xtrs-hvac-fan-param-section-header">
        <div class="r-xtrs-hvac-fan-header-content">
          <h3>${tr('parameters.device_parameters_title', 'Device Parameters (2411)')}</h3>
          <button class="r-xtrs-hvac-fan-refresh-params-btn" title="${tr('parameters.refresh_title', 'Refresh all parameters from device')}">
            <span class="r-xtrs-hvac-fan-refresh-icon">🔄</span> ${tr('parameters.refresh', 'Refresh')}
          </button>
        </div>
      </div>
      <div class="r-xtrs-hvac-fan-param-list" style="max-height: 400px; overflow-y: auto;">
        ${deviceParameters.map((param) =>
          createParameterItem(param, tr)
        ).join('')}
      </div>
      ` : ''}
    </div>
  `;
}

/**
 * Normalize humidity control list input.
 * @param {Array<Object>} humidityControlEntities
 * @returns {Array<Object>}
 */
function getHumidityControlEntities(humidityControlEntities) {
  return Array.isArray(humidityControlEntities) ? humidityControlEntities : [];
}

/**
 * Normalize device parameter list input.
 * @param {Array<Object>} parameterItems
 * @returns {Array<Object>}
 */
function getDeviceParameters(parameterItems) {
  return Array.isArray(parameterItems) ? parameterItems : [];
}

/**
 * Render a humidity control number entity row.
 * @param {Object} entity View-model item.
 * @param {Function} tr Translation helper.
 * @returns {string}
 */
function createHumidityControlItem(entity, tr) {
  const entityId = entity.entity_id;
  const currentValue = entity.state;
  const friendlyName = entity.attributes?.friendly_name || entityId.split('_').pop().replace(/([A-Z])/g, ' $1').toLowerCase();
  const unit = entity.attributes?.unit_of_measurement || '%';

  // Create a readable name from the entity ID
  let displayName = friendlyName;
  if (entity.name_key) {
    displayName = tr(entity.name_key, entity.name_fallback || friendlyName);
  }

  return `
    <div class="r-xtrs-hvac-fan-param-item" data-humidity-control="${entityId}">
      <div class="r-xtrs-hvac-fan-param-info">
        <label class="r-xtrs-hvac-fan-param-label">${displayName}</label>
        <span class="r-xtrs-hvac-fan-param-unit">${unit}</span>
      </div>
      <div class="r-xtrs-hvac-fan-param-input-container">
        <input type="number"
                class="r-xtrs-hvac-fan-param-input"
                min="${entity.attributes?.min || 0}"
                max="${entity.attributes?.max || 100}"
                step="${entity.attributes?.step || 1}"
                value="${currentValue}"
                data-entity="${entityId}">
        <button class="r-xtrs-hvac-fan-param-update-btn" data-action="update-humidity" data-entity-id="${entityId}">${tr('parameters.update', 'Update')}</button>
        <span class="r-xtrs-hvac-fan-param-status"></span>
      </div>
    </div>
  `;
}

/**
 * Render a Temp control entity row.
 * @param {Object} entity View-model item.
 * @param {Function} tr Translation helper.
 * @returns {string}
 */
function createTempControlItem(entity, tr) {
  const entityId = entity.entity_id;
  const currentValue = entity.state;
  const friendlyName = entity.attributes?.friendly_name || entityId.split('_').pop().replace(/([A-Z])/g, ' $1').toLowerCase();

  let displayName = friendlyName;
  if (entity.name_key) {
    displayName = tr(entity.name_key, entity.name_fallback || friendlyName);
  }

  if (entityId.startsWith('select.')) {
    const options = entity.attributes?.options || [];
    return `
      <div class="r-xtrs-hvac-fan-param-item" data-temp-control="${entityId}">
        <div class="r-xtrs-hvac-fan-param-info">
          <label class="r-xtrs-hvac-fan-param-label">${displayName}</label>
        </div>
        <div class="r-xtrs-hvac-fan-param-input-container">
          <select class="r-xtrs-hvac-fan-param-input" data-entity="${entityId}">
            ${options.map(opt => `<option value="${opt}" ${opt === currentValue ? 'selected' : ''}>${tr(`status.${opt}`, opt)}</option>`).join('')}
          </select>
          <button class="r-xtrs-hvac-fan-param-update-btn" data-action="update-select" data-entity-id="${entityId}">${tr('parameters.update', 'Update')}</button>
          <span class="r-xtrs-hvac-fan-param-status"></span>
        </div>
      </div>
    `;
  } else if (entityId.startsWith('switch.')) {
    return `
      <div class="r-xtrs-hvac-fan-param-item" data-temp-control="${entityId}">
        <div class="r-xtrs-hvac-fan-param-info">
          <label class="r-xtrs-hvac-fan-param-label">${displayName}</label>
        </div>
        <div class="r-xtrs-hvac-fan-param-input-container">
          <select class="r-xtrs-hvac-fan-param-input" data-entity="${entityId}">
            <option value="on" ${currentValue === 'on' ? 'selected' : ''}>On</option>
            <option value="off" ${currentValue === 'off' ? 'selected' : ''}>Off</option>
          </select>
          <button class="r-xtrs-hvac-fan-param-update-btn" data-action="update-switch" data-entity-id="${entityId}">${tr('parameters.update', 'Update')}</button>
          <span class="r-xtrs-hvac-fan-param-status"></span>
        </div>
      </div>
    `;
  }

  return `
    <div class="r-xtrs-hvac-fan-param-item">
      <div class="r-xtrs-hvac-fan-param-info">
        <label class="r-xtrs-hvac-fan-param-label">${displayName}</label>
        <span class="r-xtrs-hvac-fan-param-unit">${currentValue}</span>
      </div>
    </div>
  `;
}

/**
 * Render the comfort temp row.
 *
 * - If an external comfort_temp_entity is configured, show a number
 *   input to edit that entity's value directly (via set_value service).
 * - If no external entity is configured (using default param_75), show
 *   the current param_75 value as read-only info.
 *
 * @param {Object} comfortTemp { entity, value, isExternal }
 * @param {Function} tr Translation helper.
 * @returns {string} HTML string.
 */
function createComfortTempItem(comfortTemp, tr) {
  const label = tr('parameters.comfort_temp', 'Comfort Temp');
  const currentEntity = comfortTemp.entity || '';

  if (comfortTemp.isExternal) {
    // Entity is configured — edit its value directly
    const numMatch = comfortTemp.value.match(/^([\d.]+)/);
    const numVal = numMatch ? numMatch[1] : '';
    return `
      <div class="r-xtrs-hvac-fan-param-item" data-comfort-temp="value">
        <div class="r-xtrs-hvac-fan-param-info">
          <label class="r-xtrs-hvac-fan-param-label">${label}</label>
          <span class="r-xtrs-hvac-fan-param-unit">${currentEntity}</span>
        </div>
        <div class="r-xtrs-hvac-fan-param-input-container">
          <input type="number" class="r-xtrs-hvac-fan-param-input" data-comfort-temp-value="${numVal}" step="0.1" value="${numVal}" />
          <button class="r-xtrs-hvac-fan-param-update-btn" data-action="set-comfort-temp-value" data-entity-id="${currentEntity}">${tr('parameters.update', 'Update')}</button>
          <span class="r-xtrs-hvac-fan-param-status"></span>
        </div>
      </div>
    `;
  }

  // No external entity — show param_75 value as read-only info
  return `
    <div class="r-xtrs-hvac-fan-param-item" data-comfort-temp="info">
      <div class="r-xtrs-hvac-fan-param-info">
        <label class="r-xtrs-hvac-fan-param-label">${label}</label>
        <span class="r-xtrs-hvac-fan-param-unit">${comfortTemp.value} <small>(param_75)</small></span>
      </div>
    </div>
  `;
}

/**
 * Render temp_control numeric settings as editable input rows.
 * Each field has an input, an Update button, and a status span.
 * @param {Object} settings Temp control settings from WebSocket.
 * @param {Function} tr Translation helper.
 * @returns {string} HTML string.
 */
function createTempControlSettingItems(settings, tr) {
  const fields = [
    { key: 'comfort_delta_activate', label: 'Comfort Delta (Activate)', unit: '°C', step: '0.1' },
    { key: 'comfort_delta_deactivate', label: 'Comfort Delta (Deactivate)', unit: '°C', step: '0.1' },
    { key: 'cooling_delta_activate', label: 'Cooling Delta (Activate)', unit: '°C', step: '0.1' },
    { key: 'cooling_delta_deactivate', label: 'Cooling Delta (Deactivate)', unit: '°C', step: '0.1' },
    { key: 'min_outdoor_temp', label: 'Min Outdoor Temp', unit: '°C', step: '0.5' },
    { key: 'dewpoint_margin_c', label: 'Dewpoint Margin', unit: '°C', step: '0.1' },
    { key: 'supply_cooler_delta_activate', label: 'Supply Cooler Delta (Activate)', unit: '°C', step: '0.1' },
    { key: 'supply_cooler_delta_deactivate', label: 'Supply Cooler Delta (Deactivate)', unit: '°C', step: '0.1' },
    { key: 'min_supply_temp', label: 'Min Supply Temp', unit: '°C', step: '0.5' },
  ];

  return fields.map(f => {
    const raw = settings[f.key];
    if (raw === undefined || raw === null) return '';
    const val = typeof raw === 'number' ? raw : parseFloat(raw) || 0;
    return `
      <div class="r-xtrs-hvac-fan-param-item" data-temp-setting="${f.key}">
        <div class="r-xtrs-hvac-fan-param-info">
          <label class="r-xtrs-hvac-fan-param-label">${f.label}</label>
          <span class="r-xtrs-hvac-fan-param-unit">${f.unit}</span>
        </div>
        <div class="r-xtrs-hvac-fan-param-input-container">
          <input type="number" class="r-xtrs-hvac-fan-param-input" data-setting-key="${f.key}" step="${f.step}" value="${val}" />
          <button class="r-xtrs-hvac-fan-param-update-btn" data-action="save-temp-setting" data-setting-key="${f.key}">${tr('parameters.update', 'Update')}</button>
          <span class="r-xtrs-hvac-fan-param-status"></span>
        </div>
      </div>
    `;
  }).join('');
}

/**
 * Render a single 2411 parameter item.
 * @param {Object} param View-model item.
 * @param {Function} tr Translation helper.
 * @returns {string}
 */
function createParameterItem(param, tr) {
  const paramKey = param.paramKey;
  const displayMin = param.min;
  const displayMax = param.max;
  const displayStep = param.step;
  const displayValue = param.value;

  return `
    <div class="r-xtrs-hvac-fan-param-item" data-param="${paramKey}">
      <div class="r-xtrs-hvac-fan-param-info">
        <label class="r-xtrs-hvac-fan-param-label">${param.description}</label>
        <span class="r-xtrs-hvac-fan-param-unit">${param.unit}</span>
      </div>
      <div class="r-xtrs-hvac-fan-param-input-container">
        <input type="number"
                class="r-xtrs-hvac-fan-param-input"
                min="${displayMin}"
                max="${displayMax}"
                step="${displayStep}"
                value="${displayValue}"
                data-entity="${param.entity_id}">
        <button class="r-xtrs-hvac-fan-param-update-btn" data-param="${paramKey}">${tr('parameters.update', 'Update')}</button>
        <span class="r-xtrs-hvac-fan-param-status"></span>
      </div>
    </div>
  `;
}
