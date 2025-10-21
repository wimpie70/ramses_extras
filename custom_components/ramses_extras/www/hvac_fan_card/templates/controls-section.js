/**
 * Controls Section Template
 * Contains the 4 rows of control buttons (fan modes, speeds, timer, bypass)
 */

export function createControlsSection() {
  return `
    <!-- Control Buttons - 4 rows -->
    <div class="controls-container">
      <!-- Row 1: Fan Modes -->
      <div class="control-row">
        <div class="control-button" data-mode="away">
          <div class="control-icon">🏠</div>
          <div class="control-label">Away</div>
        </div>
        <div class="control-button" data-mode="auto">
          <div class="control-icon">🌀</div>
          <div class="control-label">Auto</div>
        </div>
        <div class="control-button" data-mode="active">
          <div class="control-icon">⚡</div>
          <div class="control-label">Dehumidify</div>
        </div>
      </div>

      <!-- Row 2: Fan Speeds -->
      <div class="control-row">
        <div class="control-button" data-mode="low">
          <div class="control-icon">🌀</div>
          <div class="control-label">Low</div>
        </div>
        <div class="control-button" data-mode="medium">
          <div class="control-icon">🌀</div>
          <div class="control-label">Medium</div>
        </div>
        <div class="control-button" data-mode="high">
          <div class="control-icon">🌀</div>
          <div class="control-label">High</div>
        </div>
      </div>

      <!-- Row 3: Timer -->
      <div class="control-row">
        <div class="control-button" data-timer="15">
          <div class="control-icon">⏱️</div>
          <div class="control-label">15m</div>
        </div>
        <div class="control-button" data-timer="30">
          <div class="control-icon">⏰</div>
          <div class="control-label">30m</div>
        </div>
        <div class="control-button" data-timer="60">
          <div class="control-icon">⏳</div>
          <div class="control-label">60m</div>
        </div>
      </div>

      <!-- Row 4: Bypass -->
      <div class="control-row">
        <div class="control-button" onclick="setBypassMode('auto')">
          <div class="control-icon">🔄</div>
          <div class="control-label">Bypass Auto</div>
        </div>
        <div class="control-button" onclick="setBypassMode('close')">
          <div class="control-icon">⊞</div>
          <div class="control-label">Bypass Close</div>
        </div>
        <div class="control-button" onclick="setBypassMode('open')">
          <div class="control-icon">⊟</div>
          <div class="control-label">Bypass Open</div>
        </div>
      </div>
    </div>
  `;
}
