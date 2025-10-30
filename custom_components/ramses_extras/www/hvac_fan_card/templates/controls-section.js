/**
 * Controls Section Template
 * Contains the 4 rows of control buttons (fan modes, speeds, timer, bypass)
 */

export function createControlsSection(dehumEntitiesAvailable = false, config = {}) {
  return `
    <!-- Control Buttons - 4 rows -->
    <div class="controls-container">
      <!-- Row 1: Fan Modes -->
      <div class="control-row">
        <div class="control-button" onclick="send_command('away', '${config.device_id}', this)">
          <div class="control-icon">🏠</div>
          <div class="control-label">Away</div>
        </div>
        <div class="control-button" onclick="send_command('auto', '${config.device_id}', this)">
          <div class="control-icon">🌀</div>
          <div class="control-label">Auto</div>
        </div>
        ${dehumEntitiesAvailable ? `
        <div class="control-button" onclick="send_command('active', '${config.device_id}', this)">
          <div class="control-icon">⚡</div>
          <div class="control-label">Dehumidify</div>
        </div>
        ` : ''}
      </div>

      <!-- Row 2: Fan Speeds -->
      <div class="control-row">
        <div class="control-button" onclick="send_command('low', '${config.device_id}', this)">
          <div class="control-icon">🌀</div>
          <div class="control-label">Low</div>
        </div>
        <div class="control-button" onclick="send_command('medium', '${config.device_id}', this)">
          <div class="control-icon">🌀</div>
          <div class="control-label">Medium</div>
        </div>
        <div class="control-button" onclick="send_command('high', '${config.device_id}', this)">
          <div class="control-icon">🌀</div>
          <div class="control-label">High</div>
        </div>
      </div>

      <!-- Row 3: Timer -->
      <div class="control-row">
        <div class="control-button" onclick="send_command('high_15', '${config.device_id}', this)">
          <div class="control-icon">⏱️</div>
          <div class="control-label">15m</div>
        </div>
        <div class="control-button" onclick="send_command('high_30', '${config.device_id}', this)">
          <div class="control-icon">⏰</div>
          <div class="control-label">30m</div>
        </div>
        <div class="control-button" onclick="send_command('high_60', '${config.device_id}', this)">
          <div class="control-icon">⏳</div>
          <div class="control-label">60m</div>
        </div>
      </div>

      <!-- Row 4: Bypass -->
      <div class="control-row">
        <div class="control-button" onclick="send_command('bypass_auto', '${config.device_id}', this)">
          <div class="control-icon">🔄</div>
          <div class="control-label">Bypass Auto</div>
        </div>
        <div class="control-button" onclick="send_command('bypass_close', '${config.device_id}', this)">
          <div class="control-icon">⊞</div>
          <div class="control-label">Bypass Close</div>
        </div>
        <div class="control-button" onclick="send_command('bypass_open', '${config.device_id}', this)">
          <div class="control-icon">⊟</div>
          <div class="control-label">Bypass Open</div>
        </div>
      </div>
    </div>
  `;
}
