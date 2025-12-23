export const CARD_STYLE = `

/* ====== ROOT CONTAINER ====== */
.ventilation-card {
  background: #1c1c1c;
  border-radius: 12px;
  padding: 16px;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  color: #ffffff;
  max-width: 500px;
  width: 100%;
  height: auto;
  min-height: 400px;
  margin: 0 auto;
  box-sizing: border-box;
  transition: all 0.3s ease;
}

/* ====== SENSOR SOURCES PANEL ====== */
.sensor-sources-panel {
  background: rgba(255, 255, 255, 0.05);
  border-radius: 8px;
  padding: 12px;
  margin-bottom: 16px;
  border: 1px solid rgba(255, 255, 255, 0.1);
}

.sensor-sources-title {
  font-size: 12px;
  font-weight: 600;
  color: #ffffff;
  margin-bottom: 8px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  opacity: 0.8;
}

.sensor-sources-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: 8px;
}

.sensor-source-indicator {
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

.sensor-source-indicator:hover {
  transform: translateY(-1px);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.2);
}

/* Sensor source status styles */
.sensor-source-external.valid {
  background: rgba(76, 175, 80, 0.2);
  border: 1px solid rgba(76, 175, 80, 0.3);
  color: #a5d6a7;
}

.sensor-source-external.invalid {
  background: rgba(244, 67, 54, 0.2);
  border: 1px solid rgba(244, 67, 54, 0.3);
  color: #ef9a9a;
}

.sensor-source-derived {
  background: rgba(33, 150, 243, 0.2);
  border: 1px solid rgba(33, 150, 243, 0.3);
  color: #90caf9;
}

.sensor-source-disabled {
  background: rgba(158, 158, 158, 0.2);
  border: 1px solid rgba(158, 158, 158, 0.3);
  color: #e0e0e0;
}

.sensor-source-icon {
  font-size: 14px;
  line-height: 1;
}

.sensor-source-label {
  flex: 1;
  font-weight: 500;
}

.sensor-source-kind {
  font-size: 9px;
  text-transform: uppercase;
  opacity: 0.7;
  font-weight: 600;
  letter-spacing: 0.3px;
}

.sensor-source-entity {
  font-size: 10px;
  opacity: 0.8;
  font-weight: 400;
  max-width: 120px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  margin-left: 4px;
}

/* ====== MAIN CONTENT SECTIONS ====== */
.top-section, .parameter-edit-section {
  background: #f5f5f5;
  border-radius: 12px;
  padding: 20px;
  margin-bottom: 16px;
  position: relative;
  min-height: 280px;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  font-size: 14px;
  color: #333;
  font-weight: 500;
  transition: all 0.3s ease;
}

.parameter-edit-section {
  background: linear-gradient(135deg, #e8f4fd 0%, #d1ecf1 100%);
}

/* ====== LAYOUT HELPERS ====== */
.centre {
  width: 100px;
  height: 100px;
  position: absolute;
  top: 35%;
  left: 50%;
  transform: translate(-50%, -50%);
  border-radius: 8px;
  display: flex;
  flex-direction: column;
}

.timer-display, .bottom-stats, .settings-container, .corner-value, .side-value {
  position: absolute;
  display: flex;
}

.timer-display {
  top: 15px;
  left: 50%;
  transform: translateX(-50%);
  align-items: center;
  gap: 12px;
  white-space: nowrap;
  padding: 8px 16px;
  min-width: 80px;
  z-index: 2;
}

.bottom-stats {
  bottom: 10px;
  left: 50%;
  transform: translateX(-50%);
  gap: 20px;
  z-index: 2;
}

.settings-container {
  bottom: 45px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 2;
}

.corner-value {
  flex-direction: column;
  gap: 4px;
}

.side-value {
  flex-direction: column;
  gap: 4px;
  color: #333;
}

.corner-value.top-left { top: 20px; left: 20px; align-items: flex-start; text-align: left; }
.corner-value.top-right { top: 20px; right: 20px; align-items: flex-end; text-align: right; }
.corner-value.bottom-left { bottom: 20px; left: 20px; align-items: flex-start; text-align: left; }
.corner-value.bottom-right { bottom: 20px; right: 20px; align-items: flex-end; text-align: right; }

/* ====== TEXT AND DATA ELEMENTS ====== */
.timer-icon {
  width: 20px;
  height: 20px;
  flex-shrink: 0;
}

.temp-value, .humidity-value, .humidity-abs, .comfort-temp, .side-value-item, .dehum-mode, .dehum-active {
  display: flex;
  align-items: center;
  gap: 4px;
  font-weight: 500;
}

.temp-value, .humidity-value, .humidity-abs, .comfort-temp, .side-value-item {
  font-size: 16px;
}

.dehum-mode, .dehum-active {
  font-size: 20px;
  color: #4a90e2;
  justify-content: center;
  min-height: 28px;
}

.comfort-temp { color: #4a90e2; }

.centre-inner {
  text-align: center;
  color: black;
  font-weight: 600;
}

/* ====== ICONS ====== */
.icon-circle {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  display: flex;
  justify-content: center;
  font-size: 20px;
}
.icon-circle.blue {
  background-color:blue;
}
.icon-circle.blue, .icon-circle.red {
  color: white;
}

/* ====== BUTTONS AND INTERACTIVE ELEMENTS ====== */
.settings-icon, .back-icon, .refresh-button, .param-update-btn {
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.3s ease;
}

.settings-icon, .back-icon, .refresh-button {
  font-size: 32px;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.1);
  border: none;
  opacity: 0.7;
  width: 40px;
  height: 40px;
}

.settings-icon:hover, .back-icon:hover {
  background: rgba(255, 255, 255, 0.2);
  opacity: 1;
  transform: scale(1.1);
}

.refresh-button {
  border-radius: 8px;
  background: #2a2a2a;
  border: 1px solid #555;
}

.refresh-button:hover { background: #3a3a3a; transform: scale(1.05); }
.refresh-button:active { transform: scale(0.95); }

.param-update-btn {
  border-radius: 6px;
  padding: 8px 16px;
  background: #4a90e2;
  color: white;
  border: none;
  font-size: 14px;
  font-weight: 500;
  width: auto;
  height: auto;
}

.param-update-btn:hover { background: #357abd; transform: translateY(-1px); }
.param-update-btn:active { transform: translateY(0); }

/* ====== DIAGRAMS ====== */
.airflow-diagram {
  position: absolute;
  width: 200px;
  height: 160px;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  z-index: 0;
}

/* ====== CONTROLS ====== */
.controls-container {
  display: flex;
  flex-direction: column;
  gap: 12px;
  width: 100%;
}

.control-row {
  display: flex;
  gap: 12px;
  justify-content: space-around;
}

.control-button {
  background: #2a2a2a;
  border: 2px solid #3a3a3a;
  border-radius: 12px;
  padding: 16px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  transition: all 0.3s ease;
  flex: 1;
}

.control-button:hover, .control-button.active {
  background: #353535;
  border-color: #4a90e2;
}

.control-icon {
  font-size: 32px;
  color: #4a90e2;
}

.control-label {
  color: #ffffff;
  font-size: 13px;
  text-align: center;
}

/* ====== PARAMETER EDIT NAVIGATION ====== */
.param-nav {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
  padding-bottom: 15px;
  border-bottom: 2px solid #b8daff;
}

.nav-left, .nav-right {
  display: flex;
  align-items: center;
  gap: 12px;
}

.device-title {
  font-size: 16px;
  font-weight: 600;
  color: #1e3a8a;
}

/* ====== PARAMETER SECTIONS ====== */
.param-section-header {
  margin: 16px 0 12px 0;
  padding-bottom: 8px;
  border-bottom: 1px solid rgba(30, 58, 138, 0.2);
}

.param-section-header h3 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: #1e3a8a;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

/* ====== PARAMETER LIST ====== */
.param-list {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 16px;
  max-height: 400px;
  overflow-y: auto;
  padding-right: 8px;
  margin-bottom: 20px;
}

.param-list::-webkit-scrollbar { width: 6px; }
.param-list::-webkit-scrollbar-track { background: rgba(255, 255, 255, 0.1); border-radius: 3px; }
.param-list::-webkit-scrollbar-thumb { background: rgba(30, 58, 138, 0.3); border-radius: 3px; }

/* ====== PARAMETER ITEMS ====== */
.param-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px;
  background: rgba(255, 255, 255, 0.8);
  border-radius: 8px;
  border: 1px solid #b8daff;
  transition: all 0.3s ease;
}

.param-item:hover {
  background: rgba(255, 255, 255, 0.9);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}

.param-item.loading { border-color: #ffc107; background: #fff3cd; }
.param-item.success { border-color: #28a745; background: #d4edda; }
.param-item.error { border-color: #dc3545; background: #f8d7da; }

.param-info {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.param-label {
  font-weight: 500;
  color: #333;
  line-height: 1.3;
}

.param-unit {
  font-size: 12px;
  color: #666;
  font-weight: 400;
}

.param-input-container {
  display: flex;
  align-items: center;
  gap: 12px;
}

.param-input {
  width: 80px;
  padding: 8px 12px;
  border: 2px solid #b8daff;
  border-radius: 6px;
  text-align: center;
  background: white;
  color: #333;
  font-weight: 500;
  transition: all 0.3s ease;
}

.param-input:focus {
  outline: none;
  border-color: #4a90e2;
  box-shadow: 0 0 0 3px rgba(74, 144, 226, 0.1);
}

.param-input:disabled {
  background: #f8f9fa;
  color: #6c757d;
  cursor: not-allowed;
}

.param-status {
  font-size: 16px;
  min-width: 20px;
  text-align: center;
}

.param-status.loading::after { content: "⏳"; animation: spin 1s linear infinite; }
.param-status.success::after { content: "✅"; color: #28a745; }
.param-status.error::after { content: "❌"; color: #dc3545; }

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
