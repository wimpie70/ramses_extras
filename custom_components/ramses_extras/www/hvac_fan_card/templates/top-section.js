/**
 * Top Section Template
 * Contains timer, corner values, airflow diagram, and center section
 */

export function createTopSection(data) {
  const {
    outdoorTemp, outdoorHumidity, outdoorAbsHumidity,
    indoorTemp, indoorHumidity, indoorAbsHumidity, comfortTemp, dehumMode, dehumActive,
    dehumEntitiesAvailable,
    supplyTemp, exhaustTemp,
    fanSpeed, fanMode,
    co2Level, flowRate, efficiency,
    timerMinutes, bypassState, airflowSvg
  } = data;

  // Helper function to format humidity values
  const formatHumidity = (value, unit) => {
    if (value === 'unavailable' || value === '?' || value === null || value === undefined) {
      return '<span style="color: #999; font-style: italic;">unavailable</span>';
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
          <span id="timer">${timerMinutes} min</span>
        </div>

        <!-- Corner Values -->
        <div class="corner-value top-left">
          <div class="icon-circle blue">☁️</div>
          <div class="temp-value">
            <span id="outdoorTemp">${outdoorTemp} °C</span>
            <span>🌡️</span>
          </div>
          <div class="humidity-value">
            <span id="outdoorHumidity">${outdoorHumidity}%</span>
            <span>💧</span>
          </div>
          <div class="humidity-abs">
            <span id="outdoorAbsHumidity">${formatHumidity(outdoorAbsHumidity, ' g/m³')}</span>
            <span>💨</span>
          </div>
        </div>

        <div class="corner-value top-right">
          <div class="icon-circle red">🏠</div>
          <div class="temp-value">
            <span id="indoorTemp">${indoorTemp} °C</span>
            <span>🌡️</span>
          </div>
          <div class="humidity-value">
            <span id="indoorHumidity">${indoorHumidity}%</span>
            <span>💧</span>
          </div>
          <div class="humidity-abs">
            <span id="indoorAbsHumidity">${formatHumidity(indoorAbsHumidity, ' g/m³')}</span>
            <span>💨</span>
          </div>
          <!-- Comfort temperature - always show -->
          <div class="comfort-temp">
            <span id="comfortTemp">${comfortTemp} °C</span>
            <span>🌡️</span>
          </div>
          ${dehumEntitiesAvailable ? `
          <!-- Dehumidifier Mode - Auto Moisture Sensing -->
          <div class="dehum-mode">
            <span id="dehumMode">${dehumMode}</span>
            <span>🖐️</span>
          </div>
          <div class="dehum-active">
            <span id="dehumActive">${dehumActive}</span>
            <span>💨</span>
          </div>
          ` : ''}
        </div>

        <div class="corner-value bottom-right">
          <div class="temp-value">
            <span id="supplyTemp">${supplyTemp} °C</span>
            <span>🌡️</span>
          </div>
        </div>

        <div class="corner-value bottom-left">
          <div class="temp-value">
            <span id="exhaustTemp">${exhaustTemp} °C</span>
            <span>🌡️</span>
          </div>
        </div>

        <div class="side-value mid-left">
          <!-- Refresh button removed -->
        </div>

        <!-- SVG Flow Direction Arrows -->
        <div class="airflow-diagram">
          ${airflowSvg}
        </div>

        <!-- centre -->
        <div class="centre-container">
          <div class="centre">
            <div class="centre-inner">
              <div class="speed-display" id="fanSpeed">${fanSpeed}</div>
              <div class="fanmode" id="fanMode">${fanMode}</div>
            </div>
          </div>
        </div>

        <!-- Bottom Stats -->
        <div style="position: absolute; bottom: 10px; left: 50%; transform: translateX(-50%); display: flex; gap: 20px; font-size: 13px; color: #333; z-index: 2;">
          <div style="display: flex; align-items: center; gap: 4px;">
            <span>📊</span>
            <span id="efficiency">${efficiency}%</span>
          </div>
          <div>
            <span id="co2Level">${co2Level} ppm</span>
          </div>
          <div>
            <span id="flowRate">${flowRate} L/s</span>
          </div>
        </div>
      </div>
  `;
}
