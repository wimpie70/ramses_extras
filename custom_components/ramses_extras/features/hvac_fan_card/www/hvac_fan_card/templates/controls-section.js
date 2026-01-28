/**
 * Controls Section Template
 * Contains the 4 rows of control buttons (fan modes, speeds, timer, bypass)
 */

/**
 * Render the card's controls section.
 *
 * @param {boolean} [dehumEntitiesAvailable=false] Whether dehumidify controls should be shown.
 * @param {Object} [config={}] Card configuration.
 * @param {Function} [t] Optional translation function.
 * @returns {string} HTML string.
 */
export function createControlsSection(dehumEntitiesAvailable = false, config = {}, t) {
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

  return `
    <!-- Control Buttons - 4 rows -->
    <div class="r-xtrs-hvac-fan-controls-container">
      <!-- Row 1: Fan Modes -->
      <div class="r-xtrs-hvac-fan-control-row">
        <div class="r-xtrs-hvac-fan-control-button" data-command="fan_away" data-device-id="${config.device_id}">
          <div class="r-xtrs-hvac-fan-control-icon">🏠</div>
          <div class="r-xtrs-hvac-fan-control-label">${tr('status.away', 'Away')}</div>
        </div>
        <div class="r-xtrs-hvac-fan-control-button" data-command="fan_auto" data-device-id="${config.device_id}">
          <div class="r-xtrs-hvac-fan-control-icon">🌀</div>
          <div class="r-xtrs-hvac-fan-control-label">${tr('status.auto2', 'Auto')}</div>
        </div>
        ${dehumEntitiesAvailable ? `
        <div class="r-xtrs-hvac-fan-control-button" data-action="toggle-dehumidify" data-entity-id="${config.dehum_mode_entity || 'switch.dehumidify_' + config.device_id.replace(/:/g, '_')}">
          <div class="r-xtrs-hvac-fan-control-icon">⚡</div>
          <div class="r-xtrs-hvac-fan-control-label">${tr('controls.dehumidify', 'Dehumidify')}</div>
        </div>
        ` : ''}
      </div>

      <!-- Row 2: Fan Speeds -->
      <div class="r-xtrs-hvac-fan-control-row">
        <div class="r-xtrs-hvac-fan-control-button" data-command="fan_low" data-device-id="${config.device_id}">
          <div class="r-xtrs-hvac-fan-control-icon">🌀</div>
          <div class="r-xtrs-hvac-fan-control-label">${tr('status.low', 'Low')}</div>
        </div>
        <div class="r-xtrs-hvac-fan-control-button" data-command="fan_medium" data-device-id="${config.device_id}">
          <div class="r-xtrs-hvac-fan-control-icon">🌀</div>
          <div class="r-xtrs-hvac-fan-control-label">${tr('status.medium', 'Medium')}</div>
        </div>
        <div class="r-xtrs-hvac-fan-control-button" data-command="fan_high" data-device-id="${config.device_id}">
          <div class="r-xtrs-hvac-fan-control-icon">🌀</div>
          <div class="r-xtrs-hvac-fan-control-label">${tr('status.high', 'High')}</div>
        </div>
      </div>

      <!-- Row 3: Timer -->
      <div class="r-xtrs-hvac-fan-control-row">
        <div class="r-xtrs-hvac-fan-control-button" data-command="fan_timer_15min" data-device-id="${config.device_id}">
          <div class="r-xtrs-hvac-fan-control-icon">⏱️</div>
          <div class="r-xtrs-hvac-fan-control-label">${tr('controls.timer_15', '15m')}</div>
        </div>
        <div class="r-xtrs-hvac-fan-control-button" data-command="fan_timer_30min" data-device-id="${config.device_id}">
          <div class="r-xtrs-hvac-fan-control-icon">⏰</div>
          <div class="r-xtrs-hvac-fan-control-label">${tr('controls.timer_30', '30m')}</div>
        </div>
        <div class="r-xtrs-hvac-fan-control-button" data-command="fan_timer_60min" data-device-id="${config.device_id}">
          <div class="r-xtrs-hvac-fan-control-icon">⏳</div>
          <div class="r-xtrs-hvac-fan-control-label">${tr('controls.timer_60', '60m')}</div>
        </div>
      </div>

      <!-- Row 4: Bypass -->
      <div class="r-xtrs-hvac-fan-control-row">
        <div class="r-xtrs-hvac-fan-control-button" data-command="fan_bypass_auto" data-device-id="${config.device_id}">
          <div class="r-xtrs-hvac-fan-control-icon">🔄</div>
          <div class="r-xtrs-hvac-fan-control-label">${tr('controls.bypass_auto', 'Bypass Auto')}</div>
        </div>
        <div class="r-xtrs-hvac-fan-control-button" data-command="fan_bypass_close" data-device-id="${config.device_id}">
          <div class="r-xtrs-hvac-fan-control-icon">⊞</div>
          <div class="r-xtrs-hvac-fan-control-label">${tr('controls.bypass_close', 'Bypass Close')}</div>
        </div>
        <div class="r-xtrs-hvac-fan-control-button" data-command="fan_bypass_open" data-device-id="${config.device_id}">
          <div class="r-xtrs-hvac-fan-control-icon">⊟</div>
          <div class="r-xtrs-hvac-fan-control-label">${tr('controls.bypass_open', 'Bypass Open')}</div>
        </div>
      </div>
    </div>
  `;
}
