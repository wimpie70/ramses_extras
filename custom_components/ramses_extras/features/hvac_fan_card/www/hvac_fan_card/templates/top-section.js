/**
 * Top Section Template
 * Contains timer, corner values, airflow diagram, and center section
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
      return `<span style="color: #999; font-style: italic;">${tr('sensor.unavailable', 'unavailable')}</span>`;
    }
    return `${value}${unit}`;
  };

  return `
    <div class="ventilation-card">
      <!-- Top Section with airflow -->
      <div class="top-section">
        <!-- Timer -->
        <div class="timer-display">
          <svg class="timer-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="12" cy="12" r="10"></circle>
            <path d="M12 6v6l4 2"></path>
          </svg>
          <span id="timer">${timerMinutes} ${tr('time.minutes', 'min')}</span>
        </div>

        <div class="settings-container">
          <button class="settings-icon" title="${tr('card.edit_parameters', 'Edit Parameters')}">
            ⚙️
          </button>
        </div>

        <!-- Corner Values -->
        <div class="corner-value top-left">
          <div class="corner-row">
            <div class="temp-value outside-edge">
              <span id="outdoorTemp">${outdoorTemp} °C</span>
              <span>🌡️</span>
            </div>
            <div class="icon-circle blue">☁️</div>
          </div>
          <div class="humidity-row">
            <span id="outdoorHumidity">${outdoorHumidity}%</span>
            <span class="arrow">→</span>
            <span id="outdoorAbsHumidity">${formatHumidity(outdoorAbsHumidity, ' g/m³')}</span>
            <span>💧</span>
          </div>
          <div class="info-stack">
            <div>📊 ${efficiency}%</div>
            <div>🫧 ${co2Level} ppm</div>
            <div>📅 ${filterDaysRemaining}d</div>
          </div>
        </div>

        <div class="corner-value top-right">
          <div class="corner-row">
            <div class="icon-circle red">🏠</div>
            <div class="temp-value outside-edge">
              <span>🌡️</span>
              <span id="indoorTemp">${indoorTemp} °C</span>
            </div>
          </div>
          <div class="humidity-row">
            <span>💧</span>
            <span id="indoorHumidity">${indoorHumidity}%</span>
            <span class="arrow">→</span>
            <span id="indoorAbsHumidity">${formatHumidity(indoorAbsHumidity, ' g/m³')}</span>
          </div>
          <div class="info-stack">
            <div>🌡️ ${tr('parameters.comfort_temp', 'Comfort Temperature')}: ${comfortTemp} °C</div>
            ${dehumEntitiesAvailable ? `
            <div class="dehum-row">
              <span id="dehumMode">${dehumMode}</span>
              <span>⚡</span>
              <span class="arrow">→</span>
              <span id="dehumActive">${dehumActive}</span>
            </div>
            <div>
              <span>&nbsp;</span>
            </div>
            ` : ''}
          </div>
        </div>

        <div class="corner-value bottom-right">
          <div class="temp-value">
            <span>🌡️</span>
            <span id="supplyTemp">${supplyTemp} °C</span>
          </div>
        </div>

        <div class="corner-value bottom-left">
          <div class="temp-value">
            <span>🌡️</span>
            <span id="exhaustTemp">${exhaustTemp} °C</span>
          </div>
        </div>

        <!-- SVG Flow Direction Arrows -->
        <div class="airflow-diagram">
          ${airflowSvg}
        </div>

        <!-- Bottom Stats -->
        <div class="bottom-stats">
          <div class="stats-top">
            <div class="fanmode" id="fanMode">${fanMode}</div>
          </div>
          <div class="stats-bottom">
            <div class="stat-item left">
              <div class="speed-display" id="exhaustFanSpeed">${exhaustFanSpeed}</div>
              <span id="exhaustFlowRate">${exhaustFlowRate} L/s</span>
            </div>
            <div class="stat-item right">
              <div class="speed-display" id="supplyFanSpeed">${supplyFanSpeed}</div>
              <span id="supplyFlowRate">${supplyFlowRate} L/s</span>
            </div>
          </div>
        </div>
      </div>
  `;
}
