/**
 * Top Section Template
 * Contains timer, corner values, airflow diagram, and center section
 */

/**
 * Render the card's top section.
 *
 * @param {Object} data Precomputed template data for rendering.
 * @param {Function} [t] Optional translation function.
 * @returns {string} HTML string.
 */
export function createTopSection(data, t) {
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

  const {
    outdoorTemp, outdoorHumidity, outdoorAbsHumidity,
    indoorTemp, indoorHumidity, indoorAbsHumidity, comfortTemp, dehumMode, dehumActive,
    dehumEntitiesAvailable,
    supplyTemp, exhaustTemp,
    exhaustFanSpeed, supplyFanSpeed, fanMode,
    co2Level, supplyFlowRate, exhaustFlowRate, efficiency,
    timerMinutes, airflowSvg, filterDaysRemaining
  } = data;

  // Helper function to format humidity values
  const formatHumidity = (value, unit) => {
    if (value === 'unavailable' || value === '?' || value === null || value === undefined) {
      return `<span class="r-xtrs-hvac-fan-value-unavailable">${tr('sensor.unavailable', 'unavailable')}</span>`;
    }
    return `${value}${unit}`;
  };

  return `
    <div class="r-xtrs-hvac-fan-ventilation-card">
      <!-- Top Section with airflow -->
      <div class="r-xtrs-hvac-fan-top-section">
        <!-- Timer -->
        <div class="r-xtrs-hvac-fan-timer-display">
          <svg class="r-xtrs-hvac-fan-timer-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="12" cy="12" r="10"></circle>
            <path d="M12 6v6l4 2"></path>
          </svg>
          <span id="timer">${timerMinutes} ${tr('time.minutes', 'min')}</span>
        </div>

        <div class="r-xtrs-hvac-fan-settings-container">
          <button class="r-xtrs-hvac-fan-settings-icon" title="${tr('card.edit_parameters', 'Edit Parameters')}">
            ⚙️
          </button>
        </div>

        <!-- Corner Values -->
        <div class="r-xtrs-hvac-fan-corner-value top-left">
          <div class="r-xtrs-hvac-fan-corner-row">
            <div class="r-xtrs-hvac-fan-temp-value outside-edge">
              <span id="outdoorTemp">${outdoorTemp} °C</span>
              <span>🌡️</span>
            </div>
            <div class="r-xtrs-hvac-fan-icon-circle blue">☁️</div>
          </div>
          <div class="r-xtrs-hvac-fan-humidity-row">
            <span id="outdoorHumidity">${outdoorHumidity}%</span>
            <span class="r-xtrs-hvac-fan-arrow">→</span>
            <span id="outdoorAbsHumidity">${formatHumidity(outdoorAbsHumidity, ' g/m³')}</span>
            <span>💧</span>
          </div>
          <div class="r-xtrs-hvac-fan-info-stack">
            <div>📊 ${efficiency}%</div>
            <div>🫧 ${co2Level} ppm</div>
            <div>📅 ${filterDaysRemaining}d</div>
          </div>
        </div>

        <div class="r-xtrs-hvac-fan-corner-value top-right">
          <div class="r-xtrs-hvac-fan-corner-row">
            <div class="r-xtrs-hvac-fan-icon-circle red">🏠</div>
            <div class="r-xtrs-hvac-fan-temp-value outside-edge">
              <span>🌡️</span>
              <span id="indoorTemp">${indoorTemp} °C</span>
            </div>
          </div>
          <div class="r-xtrs-hvac-fan-humidity-row">
            <span>💧</span>
            <span id="indoorHumidity">${indoorHumidity}%</span>
            <span class="r-xtrs-hvac-fan-arrow">→</span>
            <span id="indoorAbsHumidity">${formatHumidity(indoorAbsHumidity, ' g/m³')}</span>
          </div>
          <div class="r-xtrs-hvac-fan-info-stack">
            <div>🌡️ ${tr('parameters.comfort_temp', 'Comfort Temperature')}: ${comfortTemp} °C</div>
            ${dehumEntitiesAvailable ? `
            <div class="r-xtrs-hvac-fan-dehum-row">
              <span id="dehumMode">${dehumMode}</span>
              <span>⚡</span>
              <span class="r-xtrs-hvac-fan-arrow">→</span>
              <span id="dehumActive">${dehumActive}</span>
            </div>
            <div>
              <span>&nbsp;</span>
            </div>
            ` : ''}
          </div>
        </div>

        <div class="r-xtrs-hvac-fan-corner-value bottom-right">
          <div class="r-xtrs-hvac-fan-temp-value">
            <span>🌡️</span>
            <span id="supplyTemp">${supplyTemp} °C</span>
          </div>
        </div>

        <div class="r-xtrs-hvac-fan-corner-value bottom-left">
          <div class="r-xtrs-hvac-fan-temp-value">
            <span>🌡️</span>
            <span id="exhaustTemp">${exhaustTemp} °C</span>
          </div>
        </div>

        <!-- SVG Flow Direction Arrows -->
        <div class="r-xtrs-hvac-fan-airflow-diagram">
          ${airflowSvg}
        </div>

        <!-- Bottom Stats -->
        <div class="r-xtrs-hvac-fan-bottom-stats">
          <div class="r-xtrs-hvac-fan-stats-top">
            <div class="r-xtrs-hvac-fan-fanmode" id="fanMode">${fanMode}</div>
          </div>
          <div class="r-xtrs-hvac-fan-stats-bottom">
            <div class="r-xtrs-hvac-fan-stat-item left">
              <div class="r-xtrs-hvac-fan-speed-display" id="exhaustFanSpeed">${exhaustFanSpeed}</div>
              <span id="exhaustFlowRate">${exhaustFlowRate} L/s</span>
            </div>
            <div class="r-xtrs-hvac-fan-stat-item right">
              <div class="r-xtrs-hvac-fan-speed-display" id="supplyFanSpeed">${supplyFanSpeed}</div>
              <span id="supplyFlowRate">${supplyFlowRate} L/s</span>
            </div>
          </div>
        </div>
      </div>
  `;
}
