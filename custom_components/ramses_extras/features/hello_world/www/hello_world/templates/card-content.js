/**
 * Card Content Template
 * Creates the main content structure for Hello World Card
 */

export function createCardContent(data) {
  const {
    deviceDisplay,
    switchState,
    sensorState,
    switchAvailable,
    sensorAvailable,
    showStatus,
    translator,
    instructionKey = 'ui.card.hello_world.click_button_activate_automation',
    sensorKey = 'ui.card.hello_world.binary_sensor_changed_by_automation'
  } = data;

  // Handle unavailable states
  const buttonText = switchAvailable ? (switchState ? 'TURN OFF' : 'TURN ON') : 'UNAVAILABLE';
  const buttonClass = switchAvailable ? (switchState ? 'on' : 'off') : 'unavailable';
  const statusText = switchAvailable ? (switchState ? 'ON' : 'OFF') : 'UNAVAILABLE';
  const sensorText = sensorAvailable ? (sensorState ? 'ON' : 'OFF') : 'UNAVAILABLE';

  return `
    <ha-card>
      <div class="r-xtrs-hello-card-header">
        <div class="r-xtrs-hello-device-info">${deviceDisplay}</div>
      </div>
      <div class="r-xtrs-hello-card-content">
        <div class="r-xtrs-hello-button-instruction">
          ${translator ? translator.t(instructionKey) : instructionKey}
        </div>
        <div class="r-xtrs-hello-button-container">
          <ha-button
            id="helloWorldButton"
            class="r-xtrs-hello-toggle-button ${buttonClass}">
            ${buttonText}
          </ha-button>
          ${showStatus ? `
            <div class="r-xtrs-hello-status">
              Status: ${statusText}
            </div>
          ` : ''}
        </div>
        ${showStatus ? `
          <div class="r-xtrs-hello-binary-sensor-status">
            ${translator ? translator.t(sensorKey) : sensorKey} ${sensorText}
          </div>
        ` : ''}
      </div>
    </ha-card>
  `;
}
