
/**
 * Parameter Edit Template
 * Provides UI for editing 2411 device parameters
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
    <div class="parameter-edit-section">
      <!-- Navigation Header -->
      <div class="param-nav">
        <div class="nav-left">
          <span class="settings-icon" onclick="toggleParameterMode()">⚙️</span>
          <span class="device-title">${settingsText}: ${deviceId.replace(/_/g, ':')}</span>
        </div>
        <div class="nav-right">
          <span class="back-icon" onclick="toggleParameterMode()">↩️</span>
        </div>
      </div>

      ${humidityEntities.length > 0 ? `
      <!-- Humidity Control Settings Section -->
      <div class="param-section-header">
        <h3>${tr('parameters.humidity_control_settings', 'Humidity Control Settings')}</h3>
      </div>
      <div class="param-list" style="max-height: 200px; overflow-y: auto;">
        ${humidityEntities.map(entity =>
          createHumidityControlItem(entity, tr)
        ).join('')}
      </div>
      ` : ''}

      ${deviceParameters.length > 0 ? `
      <!-- Device Parameters Section -->
      <div class="param-section-header">
        <div class="header-content">
          <h3>${tr('parameters.device_parameters_title', 'Device Parameters (2411)')}</h3>
          <button class="refresh-params-btn" title="${tr('parameters.refresh_title', 'Refresh all parameters from device')}">
            <span class="refresh-icon">🔄</span> ${tr('parameters.refresh', 'Refresh')}
          </button>
        </div>
      </div>
      <div class="param-list" style="max-height: 400px; overflow-y: auto;">
        ${deviceParameters.map((param) =>
          createParameterItem(param, tr)
        ).join('')}
      </div>
      ` : ''}
    </div>
  `;
}

function getHumidityControlEntities(humidityControlEntities) {
  return Array.isArray(humidityControlEntities) ? humidityControlEntities : [];
}

function getDeviceParameters(parameterItems) {
  return Array.isArray(parameterItems) ? parameterItems : [];
}

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
    <div class="param-item" data-humidity-control="${entityId}">
      <div class="param-info">
        <label class="param-label">${displayName}</label>
        <span class="param-unit">${unit}</span>
      </div>
      <div class="param-input-container">
        <input type="number"
                class="param-input"
                min="${entity.attributes?.min || 0}"
                max="${entity.attributes?.max || 100}"
                step="${entity.attributes?.step || 1}"
                value="${currentValue}"
                data-entity="${entityId}">
        <button class="param-update-btn" onclick="updateHumidityControl('${entityId}', this.previousElementSibling.value, this)">${tr('parameters.update', 'Update')}</button>
        <span class="param-status"></span>
      </div>
    </div>
  `;
}

function createParameterItem(param, tr) {
  const paramKey = param.paramKey;
  const displayMin = param.min;
  const displayMax = param.max;
  const displayStep = param.step;
  const displayValue = param.value;

  return `
    <div class="param-item" data-param="${paramKey}">
      <div class="param-info">
        <label class="param-label">${param.description}</label>
        <span class="param-unit">${param.unit}</span>
      </div>
      <div class="param-input-container">
        <input type="number"
                class="param-input"
                min="${displayMin}"
                max="${displayMax}"
                step="${displayStep}"
                value="${displayValue}"
                data-entity="${param.entity_id}">
        <button class="param-update-btn" data-param="${paramKey}">${tr('parameters.update', 'Update')}</button>
        <span class="param-status"></span>
      </div>
    </div>
  `;
}
