
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
        if (typeof result === 'string' && result !== key) {
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
