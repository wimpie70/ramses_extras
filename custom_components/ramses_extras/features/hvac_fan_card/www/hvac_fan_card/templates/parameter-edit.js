
/**
 * Parameter Edit Template
 * Provides UI for editing 2411 device parameters
 */

export function createParameterEditSection(params) {
  const deviceId = params.device_id;
  const availableParams = params.availableParams || {};
  const hass = params.hass; // Pass hass instance
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

  // Check for humidity control entities
  const humidityControlEntities = getHumidityControlEntities(deviceId, hass);

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

      ${humidityControlEntities.length > 0 ? `
      <!-- Humidity Control Settings Section -->
      <div class="param-section-header">
        <h3>${tr('parameters.humidity_control_settings', 'Humidity Control Settings')}</h3>
      </div>
      <div class="param-list" style="max-height: 200px; overflow-y: auto;">
        ${humidityControlEntities.map(entity =>
          createHumidityControlItem(entity, hass, tr)
        ).join('')}
      </div>
      ` : ''}

      ${Object.keys(availableParams).length > 0 ? `
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
        ${Object.entries(availableParams).map(([key, param]) =>
          createParameterItem(key, param, deviceId, hass, tr)
        ).join('')}
      </div>
      ` : ''}
    </div>
  `;
}

function getHumidityControlEntities(deviceId, hass) {
  const humidityControlEntities = [];
  const deviceIdUnderscore = deviceId.replace(/:/g, '_');

  // Check for humidity control entities with full descriptive names
  // Integration converts friendly names: "Relative Humidity Minimum" → "relative_humidity_minimum"
  const humidityEntities = [
    `number.relative_humidity_minimum_${deviceIdUnderscore}`,
    `number.relative_humidity_maximum_${deviceIdUnderscore}`,
    `number.absolute_humidity_offset_${deviceIdUnderscore}`
  ];

  // console.log('🔍 Looking for humidity control entities:', humidityEntities);

  humidityEntities.forEach(entityId => {
    if (hass.states[entityId]) {
      // console.log('✅ Found humidity entity:', entityId);
      humidityControlEntities.push({
        entity_id: entityId,
        state: hass.states[entityId].state,
        attributes: hass.states[entityId].attributes || {}
      });
    } else {
      // console.log('❌ Missing humidity entity:', entityId);
    }
  });

  // console.log('🎯 Final humidity entities:', humidityControlEntities);
  return humidityControlEntities;
}

function createHumidityControlItem(entity, hass, tr) {
  const entityId = entity.entity_id;
  const currentValue = entity.state;
  const friendlyName = entity.attributes.friendly_name || entityId.split('_').pop().replace(/([A-Z])/g, ' $1').toLowerCase();
  const unit = entity.attributes.unit_of_measurement || '%';

  // Create a readable name from the entity ID
  let displayName = friendlyName;
  if (entityId.includes('minimum')) {
    displayName = tr('parameters.humidity_minimum_relative', 'Minimum Relative Humidity');
  } else if (entityId.includes('maximum')) {
    displayName = tr('parameters.humidity_maximum_relative', 'Maximum Relative Humidity');
  } else if (entityId.includes('absolute_humidity_offset')) {
    displayName = tr('parameters.humidity_absolute_offset', 'Absolute Humidity Offset');
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
                min="${entity.attributes.min || 0}"
                max="${entity.attributes.max || 100}"
                step="${entity.attributes.step || 1}"
                value="${currentValue}"
                data-entity="${entityId}">
        <button class="param-update-btn" onclick="updateHumidityControl('${entityId}', this.previousElementSibling.value, this)">${tr('parameters.update', 'Update')}</button>
        <span class="param-status"></span>
      </div>
    </div>
  `;
}

function createParameterItem(paramKey, paramInfo, deviceId, hass, tr) {
  const entityId = `number.${deviceId.replace(/:/g, '_')}_param_${paramKey}`;
  const currentValue = hass.states[entityId]?.state || paramInfo.current_value || paramInfo.default_value || paramInfo.min_value || 0;
  // console.log(`🔧 Creating parameter item for ${paramKey}: entity=${entityId}, currentValue=${currentValue}, paramInfo=`, paramInfo);

  // The schema already comes pre-scaled from the backend, so we just use the values directly
  // No additional scaling needed in the frontend
  const displayMin = paramInfo.min_value;
  const displayMax = paramInfo.max_value;
  const displayStep = paramInfo.precision;
  let displayValue = currentValue;

  // Round the display value if precision is a whole number (integer parameters)
  if (Number.isInteger(paramInfo.precision)) {
    displayValue = Math.round(parseFloat(displayValue));
  }

  return `
    <div class="param-item" data-param="${paramKey}">
      <div class="param-info">
        <label class="param-label">${paramInfo.description}</label>
        <span class="param-unit">${paramInfo.unit || paramInfo.data_unit || ''}</span>
      </div>
      <div class="param-input-container">
        <input type="number"
                class="param-input"
                min="${displayMin}"
                max="${displayMax}"
                step="${displayStep}"
                value="${displayValue}"
                data-entity="${entityId}">
        <button class="param-update-btn" data-param="${paramKey}" onclick="updateParameter('${paramKey}', this.previousElementSibling.value)">${tr('parameters.update', 'Update')}</button>
        <span class="param-status"></span>
      </div>
    </div>
  `;
}
