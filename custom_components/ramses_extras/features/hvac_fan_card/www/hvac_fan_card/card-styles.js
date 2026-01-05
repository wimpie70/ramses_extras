export const CARD_STYLE = `

/* ====== ROOT CONTAINER ====== */
.ventilation-card {
  background: #1c1c1c;
  border-radius: 12px;
  padding: 16px;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  color: #ffffff;
  width: 100%;
  height: auto;
  min-height: 440px;
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
  padding: 12px;
  margin-bottom: 16px;
  position: relative;
  min-height: 380px;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  font-size: 13px;
  color: #333;
  font-weight: 500;
  transition: all 0.3s ease;
  overflow: hidden;
}

.parameter-edit-section {
  background: linear-gradient(135deg, #e8f4fd 0%, #d1ecf1 100%);
}

/* ====== LAYOUT HELPERS ====== */
.timer-display, .bottom-stats, .settings-container, .corner-value {
  position: absolute;
  display: flex;
}

.timer-display, .settings-container {
  top: 2%;
  left: 50%;
  width: 15%;
  transform: translateX(-50%);
  align-items: center;
  gap: 4px;
  padding: 3px;
  z-index: 20;
  background: rgba(255, 255, 255, 0.95);
  border: 1px solid rgba(0, 0, 0, 0.1);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
  border-radius: 10px;
}
.timer-icon {
  width: 24px;
  height: 24px;
}
.settings-container {
  top: 12%;
}
.settings-icon {
  margin: 5px auto 5px auto;
  font-size: 30px;
  background-color: transparent;
  border-color: transparent;
}
.settings-icon:hover {
  cursor: pointer;
}

.bottom-stats {
  bottom: 2%;
  left: 50%;
  transform: translateX(-50%);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  z-index: 20;
  background: rgba(255, 255, 255, 0.95);
  border: 1px solid rgba(0, 0, 0, 0.1);
  padding: 6px 16px;
  border-radius: 15px;
  min-width: 180px;
}

.stats-top {
  width: 100%;
  display: flex;
  justify-content: center;
  border-bottom: 1px solid rgba(0, 0, 0, 0.05);
  padding-bottom: 2px;
}

.stats-bottom {
  width: 100%;
  display: flex;
  justify-content: space-between;
  gap: 20px;
}

.stat-item {
  display: flex;
  flex-direction: column;
  align-items: center;
}

.stat-item.left { align-items: flex-start; }
.stat-item.right { align-items: flex-end; }

.corner-value {
  flex-direction: column;
  gap: 6px;
  z-index: 15;
  background: rgba(255, 255, 255, 0.92);
  padding: 3px;
  border-radius: 14px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
  border: 1px solid rgba(0, 0, 0, 0.05);
  width: 33%;
}

.corner-row, .humidity-row, .dehum-row {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
}

.top-left :is(.corner-row, .humidity-row, .dehum-row) { justify-content: flex-start; }
.top-right :is(.corner-row, .humidity-row, .dehum-row) { justify-content: flex-end; }

.outside-edge {
  font-weight: 800;
  color: #333;
}

.info-stack {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 11px;
  color: #666;
  padding-top: 6px;
  border-top: 1px solid rgba(0, 0, 0, 0.08);
}

.corner-value.top-left { top: 15px; left: 10px; text-align: left; }
.corner-value.top-right { top: 15px; right: 10px; text-align: right; }
.corner-value.bottom-left { bottom: 15px; left: 15px; background: none; box-shadow: none; border: none; padding: 0; width: auto; }
.corner-value.bottom-right { bottom: 15px; right: 15px; background: none; box-shadow: none; border: none; padding: 0; width: auto; }

/* ====== TEXT AND DATA ELEMENTS ====== */
.temp-value {
  display: flex;
  align-items: center;
  gap: 4px;
  font-weight: 600;
  font-size: 16px;
  white-space: nowrap;
}

.arrow {
  color: #888;
  font-weight: bold;
  margin: 0 4px;
}

.fanmode { font-size: 13px; text-transform: uppercase; font-weight: 700; color: #333; }
.speed-display { font-size: 13px; font-weight: 900; color: #4a90e2; }

/* ====== ICONS ====== */
.icon-circle {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  display: flex;
  justify-content: center;
  align-items: center;
  font-size: 20px;
  flex-shrink: 0;
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.15);
  background-color: #4a90e2;
  color: white;
}
.icon-circle.red {
  margin-left: 0;
  margin-right: auto;
  background-color: #e57373;
}
.icon-circle.blue {
  margin-left: auto;
  margin-right: auto0;
}
/* ====== DIAGRAMS ====== */
.airflow-diagram {
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
  padding: 1px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 1px;
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

.param-section-header .header-content {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.refresh-params-btn {
  background: #4a90e2;
  color: white;
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
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
}

.refresh-params-btn:hover {
  background: #357abd;
  transform: translateY(-1px);
  box-shadow: 0 4px 8px rgba(0, 0, 0, 0.15);
}

.refresh-params-btn:active {
  transform: translateY(0);
}

.refresh-params-btn.loading .refresh-icon {
  animation: spin 1s linear infinite;
}

.refresh-params-btn.success {
  background: #28a745;
}

.refresh-params-btn.error {
  background: #dc3545;
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

.param-update-btn {
  background: #4a90e2;
  color: white;
  border: none;
  border-radius: 6px;
  padding: 8px 12px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s ease;
}

.param-update-btn:hover {
  background: #357abd;
}

.param-item.loading .param-update-btn {
  background: #ffc107;
}

.param-item.success .param-update-btn {
  background: #28a745;
}

.param-item.error .param-update-btn {
  background: #dc3545;
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
