/**
 * Top Section Template
 * Contains timer, corner values, airflow diagram, and center section
 */

export function createTopSection(data) {
  const {
    outdoorTemp, outdoorHumidity, outdoorAbsHumidity,
    indoorTemp, indoorHumidity, indoorAbsHumidity, comfortTemp, dehumMode, dehumActive,
    supplyTemp, exhaustTemp,
    fanSpeed, fanMode,
    co2Level, flowRate, efficiency,
    timerMinutes, bypassState, airflowSvg
  } = data;

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
            <span id="outdoorAbsHumidity">${outdoorAbsHumidity} g/m³</span>
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
            <span id="indoorAbsHumidity">${indoorAbsHumidity} g/m³</span>
            <span>💨</span>
          </div>
          <div class="comfort-temp">
            <span id="comfortTemp">${comfortTemp} °C</span>
            <span>🌡️</span>
          </div>
          <!-- Dehumidifier Mode - Auto Moisture Sensing -->
          <div class="dehum-mode">
            <span id="dehumMode">${dehumMode}</span>
            <span>🖐️</span>
          </div>
          <div class="dehum-active">
            <span id="dehumActive">${dehumActive}</span>
            <span>💨</span>
          </div>
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
          <!-- Refresh Button -->
          <button class="refresh-button" onclick="triggerRefresh()" title="Refresh all values">
            <svg width="40" height="40" viewBox="0 0 42 42" fill="none" xmlns="http://www.w3.org/2000/svg">
              <path d="M36.75 21C36.75 29.69848 29.69848 36.75 21 36.75C16.966145 36.75 13.2864725 35.23345 10.5 32.739525L5.25 28M5.25 21C5.25 12.30152 12.30152 5.25 21 5.25C25.033925 5.25 28.713475 6.76648 31.5 9.26044L36.75 14M5.25 36.75V28M5.25 28H14M36.75 5.25V14M36.75 14H28" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
          </button>
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
            <span id="co2Level">${co2Level}%</span>
          </div>
          <div>
            <span id="flowRate">${flowRate} L/s</span>
          </div>
        </div>
      </div>
  `;
}
