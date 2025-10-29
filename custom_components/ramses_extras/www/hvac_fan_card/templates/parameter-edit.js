/**
 * Parameter Edit Template
 * Provides UI for editing 2411 device parameters
 */

export function createParameterEditSection(params) {
  const deviceId = params.device_id;
  const availableParams = params.availableParams || {};
  const hass = params.hass; // Pass hass instance

  // Get localized text for "Settings for Device:"
  const settingsText = hass.localize('component.ramses_extras.exceptions.card_translations.parameter_edit.settings_for_device') || 'Settings for Device:';

  return `
    <div class="parameter-edit-section">
      <!-- Navigation Header -->
      <div class="param-nav">
        <div class="nav-left">
          <span class="settings-icon" onclick="toggleParameterMode()">⚙️</span>
          <span class="device-title">${settingsText} ${deviceId.replace(/_/g, ':')}</span>
        </div>
        <div class="nav-right">
          <span class="back-icon" onclick="toggleParameterMode()">↩️</span>
        </div>
      </div>

      <!-- Parameter List -->
      <div class="param-list" style="max-height: 400px; overflow-y: auto;">
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
        <button class="param-update-btn" data-param="${paramKey}" onclick="updateParameter('${paramKey}', this.previousElementSibling.value)">Update</button>
        <span class="param-status"></span>
      </div>
    </div>
  `;
}
