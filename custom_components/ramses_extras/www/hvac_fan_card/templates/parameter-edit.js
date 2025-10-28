/**
 * Parameter Edit Template
 * Provides UI for editing 2411 device parameters
 */

export function createParameterEditSection(params) {
  const deviceId = params.device_id;
  const availableParams = params.availableParams || {};
  const hass = params.hass; // Pass hass instance

  return `
    <div class="parameter-edit-section">
      <!-- Navigation Header -->
      <div class="param-nav">
        <div class="nav-left">
          <span class="settings-icon" onclick="toggleParameterMode()">⚙️</span>
          <span class="device-title">Device: ${deviceId.replace(/_/g, ':')}</span>
        </div>
        <div class="nav-right">
          <span class="back-icon" onclick="toggleParameterMode()">↩️</span>
        </div>
      </div>

      <!-- Parameter List -->
      <div class="param-list">
        ${Object.entries(availableParams).map(([key, param]) =>
          createParameterItem(key, param, deviceId, hass)
        ).join('')}
      </div>
    </div>
  `;
}

function createParameterItem(paramKey, paramInfo, deviceId, hass) {
  const entityId = `number.${deviceId.replace(/:/g, '_')}_param_${paramKey}`;
  const currentValue = hass.states[entityId]?.state || paramInfo.current_value || paramInfo.default_value || paramInfo.min_value || 0;
  console.log(`🔧 Creating parameter item for ${paramKey}: entity=${entityId}, currentValue=${currentValue}, paramInfo=`, paramInfo);

  return `
    <div class="param-item" data-param="${paramKey}">
      <div class="param-info">
        <label class="param-label">${paramInfo.description}</label>
        <span class="param-unit">${paramInfo.unit || paramInfo.data_unit || ''}</span>
      </div>
      <div class="param-input-container">
        <input type="number"
               class="param-input"
               min="${paramInfo.min_value}"
               max="${paramInfo.max_value}"
               step="${paramInfo.precision}"
               value="${currentValue}"
               onchange="updateParameter('${paramKey}', this.value)"
               data-entity="${entityId}">
        <span class="param-status"></span>
      </div>
    </div>
  `;
}
