export const CARD_STYLE = `

/* ====== ROOT CONTAINER ====== */
.r-xtrs-hvac-fan-ventilation-card {
  background: var(--ha-card-background, var(--card-background-color, var(--primary-background-color)));
  border-radius: var(--ha-card-border-radius, 12px);
  padding: 16px;
  font-family: var(
    --primary-font-family,
    -apple-system,
    BlinkMacSystemFont,
    'Segoe UI',
    Roboto,
    sans-serif
  );
  color: var(--primary-text-color);
  width: 100%;
  height: auto;
  min-height: 440px;
  margin: 0 auto;
  box-sizing: border-box;
  transition: all 0.3s ease;
}

/* ====== SENSOR SOURCES PANEL ====== */
.r-xtrs-hvac-fan-sensor-sources-panel {
  background: var(--secondary-background-color);
  border-radius: 8px;
  padding: 12px;
  margin-bottom: 16px;
  border: 1px solid var(--divider-color);
}

.r-xtrs-hvac-fan-sensor-sources-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--primary-text-color);
  margin-bottom: 8px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  opacity: 0.8;
}

.r-xtrs-hvac-fan-sensor-sources-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: 8px;
}

.r-xtrs-hvac-fan-sensor-source-indicator {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 8px;
  border-radius: 6px;
  font-size: 11px;
  font-weight: 500;
  transition: all 0.2s ease;
  cursor: default;
  position: relative;
}

.r-xtrs-hvac-fan-sensor-source-indicator:hover {
  transform: translateY(-1px);
  box-shadow: var(--ha-card-box-shadow, 0 2px 8px rgba(0, 0, 0, 0.2));
}

/* Sensor source status styles */
.r-xtrs-hvac-fan-sensor-source-external.valid {
  background: var(--secondary-background-color);
  border: 1px solid var(--success-color, #4caf50);
  color: var(--success-color, #4caf50);
}

.r-xtrs-hvac-fan-sensor-source-external.invalid {
  background: var(--secondary-background-color);
  border: 1px solid var(--error-color, #f44336);
  color: var(--error-color, #f44336);
}

.r-xtrs-hvac-fan-sensor-source-derived {
  background: var(--secondary-background-color);
  border: 1px solid var(--info-color, var(--primary-color));
  color: var(--info-color, var(--primary-color));
}

.r-xtrs-hvac-fan-sensor-source-disabled {
  background: var(--secondary-background-color);
  border: 1px solid var(--divider-color);
  color: var(--secondary-text-color);
}

.r-xtrs-hvac-fan-sensor-source-icon {
  font-size: 14px;
  line-height: 1;
}

.r-xtrs-hvac-fan-sensor-source-label {
  flex: 1;
  font-weight: 500;
}

.r-xtrs-hvac-fan-sensor-source-kind {
  font-size: 9px;
  text-transform: uppercase;
  opacity: 0.7;
  font-weight: 600;
  letter-spacing: 0.3px;
}

.r-xtrs-hvac-fan-sensor-source-entity {
  font-size: 10px;
  opacity: 0.8;
  font-weight: 400;
  max-width: 120px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  margin-left: 4px;
}

.r-xtrs-hvac-fan-value-unavailable {
  color: var(--secondary-text-color);
  font-style: italic;
}

/* ====== MAIN CONTENT SECTIONS ====== */
.r-xtrs-hvac-fan-top-section, .parameter-edit-section {
  background: var(--secondary-background-color);
  border-radius: var(--ha-card-border-radius, 12px);
  padding: 12px;
  margin-bottom: 16px;
  position: relative;
  min-height: 380px;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  font-size: 13px;
  color: var(--primary-text-color);
  font-weight: 500;
  transition: all 0.3s ease;
  overflow: hidden;
}

.r-xtrs-hvac-fan-parameter-edit-section {
  background: var(--secondary-background-color);
}

/* ====== LAYOUT HELPERS ====== */
.r-xtrs-hvac-fan-timer-display, .r-xtrs-hvac-fan-bottom-stats, .r-xtrs-hvac-fan-settings-container, .r-xtrs-hvac-fan-corner-value {
  position: absolute;
  display: flex;
}

.r-xtrs-hvac-fan-timer-display, .r-xtrs-hvac-fan-settings-container {
  top: 2%;
  left: 50%;
  width: 15%;
  transform: translateX(-50%);
  align-items: center;
  gap: 4px;
  padding: 3px;
  z-index: 20;
  background: var(--ha-card-background, var(--card-background-color));
  border: 1px solid var(--divider-color);
  box-shadow: var(--ha-card-box-shadow, 0 4px 12px rgba(0, 0, 0, 0.1));
  border-radius: 10px;
}
.r-xtrs-hvac-fan-timer-icon {
  width: 24px;
  height: 24px;
}
.r-xtrs-hvac-fan-settings-container {
  top: 12%;
}
.r-xtrs-hvac-fan-settings-icon {
  margin: 5px auto 5px auto;
  font-size: 30px;
  background-color: transparent;
  border-color: transparent;
}
.r-xtrs-hvac-fan-settings-icon:hover {
  cursor: pointer;
}

.r-xtrs-hvac-fan-bottom-stats {
  bottom: 2%;
  left: 50%;
  transform: translateX(-50%);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  z-index: 20;
  background: var(--ha-card-background, var(--card-background-color));
  border: 1px solid var(--divider-color);
  padding: 6px 16px;
  border-radius: 15px;
  min-width: 180px;
}

.r-xtrs-hvac-fan-stats-top {
  width: 100%;
  display: flex;
  justify-content: center;
  border-bottom: 1px solid var(--divider-color);
  padding-bottom: 2px;
}

.r-xtrs-hvac-fan-stats-bottom {
  width: 100%;
  display: flex;
  justify-content: space-between;
  gap: 20px;
}

.r-xtrs-hvac-fan-stat-item {
  display: flex;
  flex-direction: column;
  align-items: center;
}

.r-xtrs-hvac-fan-stat-item.left { align-items: flex-start; }
.r-xtrs-hvac-fan-stat-item.right { align-items: flex-end; }

.r-xtrs-hvac-fan-corner-value {
  flex-direction: column;
  gap: 6px;
  z-index: 15;
  background: var(--ha-card-background, var(--card-background-color));
  padding: 3px;
  border-radius: 14px;
  box-shadow: var(--ha-card-box-shadow, 0 4px 12px rgba(0, 0, 0, 0.1));
  border: 1px solid var(--divider-color);
  width: 33%;
}

.r-xtrs-hvac-fan-corner-row, .r-xtrs-hvac-fan-humidity-row, .r-xtrs-hvac-fan-dehum-row {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
}

.top-left :is(.r-xtrs-hvac-fan-corner-row, .r-xtrs-hvac-fan-humidity-row, .r-xtrs-hvac-fan-dehum-row) { justify-content: flex-start; }
.top-right :is(.r-xtrs-hvac-fan-corner-row, .r-xtrs-hvac-fan-humidity-row, .r-xtrs-hvac-fan-dehum-row) { justify-content: flex-end; }

.r-xtrs-hvac-fan-outside-edge {
  font-weight: 800;
  color: var(--primary-text-color);
}

.r-xtrs-hvac-fan-info-stack {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 11px;
  color: var(--secondary-text-color);
  padding-top: 6px;
  border-top: 1px solid var(--divider-color);
}

.r-xtrs-hvac-fan-corner-value.top-left { top: 15px; left: 10px; text-align: left; }
.r-xtrs-hvac-fan-corner-value.top-right { top: 15px; right: 10px; text-align: right; }
.r-xtrs-hvac-fan-corner-value.bottom-left { bottom: 15px; left: 15px; background: none; box-shadow: none; border: none; padding: 0; width: auto; }
.r-xtrs-hvac-fan-corner-value.bottom-right { bottom: 15px; right: 15px; background: none; box-shadow: none; border: none; padding: 0; width: auto; }

/* ====== TEXT AND DATA ELEMENTS ====== */
.r-xtrs-hvac-fan-temp-value {
  display: flex;
  align-items: center;
  gap: 4px;
  font-weight: 600;
  font-size: 16px;
  white-space: nowrap;
}

.r-xtrs-hvac-fan-arrow {
  color: var(--secondary-text-color);
  font-weight: bold;
  margin: 0 4px;
}

.r-xtrs-hvac-fan-fanmode { font-size: 13px; text-transform: uppercase; font-weight: 700; color: var(--primary-text-color); }
.r-xtrs-hvac-fan-speed-display { font-size: 13px; font-weight: 900; color: var(--primary-color); }

/* ====== ICONS ====== */
.r-xtrs-hvac-fan-icon-circle {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  display: flex;
  justify-content: center;
  align-items: center;
  font-size: 20px;
  flex-shrink: 0;
  box-shadow: var(--ha-card-box-shadow, 0 2px 6px rgba(0, 0, 0, 0.15));
  background-color: var(--primary-color);
  color: var(--text-primary-color, #fff);
}
.r-xtrs-hvac-fan-icon-circle.red {
  margin-left: 0;
  margin-right: auto;
  background-color: var(--error-color, #e57373);
}
.r-xtrs-hvac-fan-icon-circle.blue {
  margin-left: auto;
  margin-right: auto0;
}
/* ====== DIAGRAMS ====== */
.r-xtrs-hvac-fan-airflow-diagram {
  position: absolute;
  width: 40%;
  height: auto;
  top: 60%;
  left: 50%;
  transform: translate(-50%, -50%);
  z-index: 1;
  opacity: 0.85;
}

/* ====== CONTROLS ====== */
.r-xtrs-hvac-fan-controls-container {
  display: flex;
  flex-direction: column;
  gap: 12px;
  width: 100%;
}

.r-xtrs-hvac-fan-control-row {
  display: flex;
  gap: 12px;
  justify-content: space-around;
}

.r-xtrs-hvac-fan-control-button {
  background: var(--secondary-background-color);
  border: 1px solid var(--divider-color);
  border-radius: 12px;
  padding: 1px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 1px;
  cursor: pointer;
  transition: all 0.3s ease;
  flex: 1;
}

.r-xtrs-hvac-fan-control-button:hover, .control-button.active {
  border-color: var(--primary-color);
}

.r-xtrs-hvac-fan-control-icon {
  font-size: 32px;
  color: var(--primary-color);
}

.r-xtrs-hvac-fan-control-label {
  color: var(--primary-text-color);
  font-size: 13px;
  text-align: center;
}

/* ====== PARAMETER EDIT NAVIGATION ====== */
.r-xtrs-hvac-fan-param-nav {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
  padding-bottom: 15px;
  border-bottom: 1px solid var(--divider-color);
}

.r-xtrs-hvac-fan-nav-left, .r-xtrs-hvac-fan-nav-right {
  display: flex;
  align-items: center;
  gap: 12px;
}

.r-xtrs-hvac-fan-device-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--primary-text-color);
}

/* ====== PARAMETER SECTIONS ====== */
.r-xtrs-hvac-fan-param-section-header {
  margin: 16px 0 12px 0;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--divider-color);
}

.r-xtrs-hvac-fan-param-section-header .r-xtrs-hvac-fan-header-content {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.r-xtrs-hvac-fan-refresh-params-btn {
  background: var(--primary-color);
  color: var(--text-primary-color, #fff);
  border: none;
  border-radius: 6px;
  padding: 6px 12px;
  margin-right: 20px;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 6px;
  transition: all 0.3s ease;
  box-shadow: var(--ha-card-box-shadow, 0 2px 4px rgba(0, 0, 0, 0.1));
}

.r-xtrs-hvac-fan-refresh-params-btn:hover {
  filter: brightness(0.9);
  transform: translateY(-1px);
  box-shadow: var(--ha-card-box-shadow, 0 4px 8px rgba(0, 0, 0, 0.15));
}

.r-xtrs-hvac-fan-refresh-params-btn:active {
  transform: translateY(0);
}

.r-xtrs-hvac-fan-refresh-params-btn.loading .r-xtrs-hvac-fan-refresh-icon {
  animation: spin 1s linear infinite;
}

.r-xtrs-hvac-fan-refresh-params-btn.success {
  background: var(--success-color, #28a745);
}

.r-xtrs-hvac-fan-refresh-params-btn.error {
  background: var(--error-color, #dc3545);
}

.r-xtrs-hvac-fan-param-section-header h3 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: var(--primary-text-color);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

/* ====== PARAMETER LIST ====== */
.r-xtrs-hvac-fan-param-list {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 16px;
  max-height: 400px;
  overflow-y: auto;
  padding-right: 8px;
  margin-bottom: 20px;
}

.r-xtrs-hvac-fan-param-list::-webkit-scrollbar { width: 6px; }
.r-xtrs-hvac-fan-param-list::-webkit-scrollbar-track { background: var(--secondary-background-color); border-radius: 3px; }
.r-xtrs-hvac-fan-param-list::-webkit-scrollbar-thumb { background: var(--divider-color); border-radius: 3px; }

/* ====== PARAMETER ITEMS ====== */
.r-xtrs-hvac-fan-param-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px;
  background: var(--ha-card-background, var(--card-background-color));
  border-radius: 8px;
  border: 1px solid var(--divider-color);
  transition: all 0.3s ease;
}

.r-xtrs-hvac-fan-param-item:hover {
  box-shadow: var(--ha-card-box-shadow, 0 2px 8px rgba(0, 0, 0, 0.1));
}

.r-xtrs-hvac-fan-param-item.loading { border-color: var(--warning-color, #ffc107); }
.r-xtrs-hvac-fan-param-item.success { border-color: var(--success-color, #28a745); }
.r-xtrs-hvac-fan-param-item.error { border-color: var(--error-color, #dc3545); }

.r-xtrs-hvac-fan-param-info {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.r-xtrs-hvac-fan-param-label {
  font-weight: 500;
  color: var(--primary-text-color);
  line-height: 1.3;
}

.r-xtrs-hvac-fan-param-unit {
  font-size: 12px;
  color: var(--secondary-text-color);
  font-weight: 400;
}

.r-xtrs-hvac-fan-param-input-container {
  display: flex;
  align-items: center;
  gap: 12px;
}

.r-xtrs-hvac-fan-param-input {
  width: 80px;
  padding: 8px 12px;
  border: 1px solid var(--divider-color);
  border-radius: 6px;
  text-align: center;
  background: var(--ha-card-background, var(--card-background-color));
  color: var(--primary-text-color);
  font-weight: 500;
  transition: all 0.3s ease;
}

.r-xtrs-hvac-fan-param-input:focus {
  outline: none;
  border-color: var(--primary-color);
  box-shadow: 0 0 0 3px rgba(0, 0, 0, 0.12);
}

.r-xtrs-hvac-fan-param-input:disabled {
  background: var(--secondary-background-color);
  color: var(--secondary-text-color);
  cursor: not-allowed;
}

.r-xtrs-hvac-fan-param-update-btn {
  background: var(--primary-color);
  color: var(--text-primary-color, #fff);
  border: none;
  border-radius: 6px;
  padding: 8px 12px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s ease;
}

.r-xtrs-hvac-fan-param-update-btn:hover {
  filter: brightness(0.9);
}

.r-xtrs-hvac-fan-param-item.loading .param-update-btn {
  background: var(--warning-color, #ffc107);
}

.r-xtrs-hvac-fan-param-item.success .param-update-btn {
  background: var(--success-color, #28a745);
}

.r-xtrs-hvac-fan-param-item.error .param-update-btn {
  background: var(--error-color, #dc3545);
}

.r-xtrs-hvac-fan-param-status {
  font-size: 16px;
  min-width: 20px;
  text-align: center;
}

.r-xtrs-hvac-fan-param-status.loading::after { content: "⏳"; animation: spin 1s linear infinite; }
.r-xtrs-hvac-fan-param-status.success::after { content: "✅"; color: var(--success-color, #28a745); }
.r-xtrs-hvac-fan-param-status.error::after { content: "❌"; color: var(--error-color, #dc3545); }

@keyframes spin {
  0% { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
}

/* ====== RESPONSIVE ====== */
@media (max-width: 480px) {
  .param-item {
    flex-direction: column;
    align-items: flex-start;
    gap: 12px;
  }
  .param-input-container {
    width: 100%;
    justify-content: space-between;
  }
  .param-input { flex: 1; }
}
`;
