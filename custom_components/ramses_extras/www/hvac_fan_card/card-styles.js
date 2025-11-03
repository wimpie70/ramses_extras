export const CARD_STYLE = `
/* ====== UTILITY CLASSES ====== */
.flex { display: flex; }
.flex-center { display: flex; align-items: center; justify-content: center; }
.flex-column { display: flex; flex-direction: column; }
.flex-center-column { display: flex; flex-direction: column; align-items: center; justify-content: center; }

.gap-4 { gap: 4px; } .gap-6 { gap: 6px; } .gap-8 { gap: 8px; }
.gap-12 { gap: 12px; } .gap-16 { gap: 16px; } .gap-20 { gap: 20px; }

.transition { transition: all 0.3s ease; }
.hover-scale:hover { transform: scale(1.1); }
.hover-opacity:hover { opacity: 1; }

.rounded-sm { border-radius: 6px; } .rounded-md { border-radius: 8px; }
.rounded-lg { border-radius: 12px; } .rounded-xl { border-radius: 20px; }

.p-6 { padding: 6px; } .p-8 { padding: 8px; } .p-12 { padding: 12px; }
.p-16 { padding: 16px; } .p-20 { padding: 20px; }

.text-sm { font-size: 12px; } .text-md { font-size: 14px; } .text-lg { font-size: 16px; }
.text-xl { font-size: 20px; } .text-2xl { font-size: 32px; }

.color-orange { color: #ff9800; } .color-blue { color: #4a90e2; } .color-green { color: #28a745; }
.color-gray { color: #333; } .color-white { color: #ffffff; } .color-dark { color: #1e3a8a; }

.bg-dark { background: #2a2a2a; } .bg-hover { background: #353535; }
.bg-light { background: white; } .bg-disabled { background: #f8f9fa; }

.border-blue { border-color: #4a90e2; } .border-warning { border-color: #ffc107; }
.border-success { border-color: #28a745; } .border-error { border-color: #dc3545; } .border-light { border-color: #b8daff; }

.shadow-focus { box-shadow: 0 0 0 3px rgba(74, 144, 226, 0.1); }
.shadow-hover { box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1); }

/* ====== BASE CARD STYLES ====== */
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
  display: block;
}

.top-section {
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
}

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

.centre-inner {
  text-align: center;
  color: black;
  font-weight: 600;
}

/* ====== TEXT DISPLAYS ====== */
.speed-display {
  margin-bottom: 4px;
}

.fanmode {
  font-size: 12px;
  font-weight: 500;
}

.timer-display {
  position: absolute;
  top: 15px;
  left: 50%;
  transform: translateX(-50%);
  display: flex;
  align-items: center;
  gap: 12px;
  white-space: nowrap;
  padding: 8px 16px;
  background: rgba(255, 255, 255, 0.1);
  border-radius: 20px;
  min-width: 80px;
}

.timer-icon {
  width: 20px;
  height: 20px;
  flex-shrink: 0;
}

/* ====== LAYOUT COMPONENTS ====== */
.corner-value {
  position: absolute;
  display: flex;
  flex-direction: column;
  gap: 4px;
  color: #333;
}

.corner-value.top-left { top: 20px; left: 20px; align-items: flex-start; text-align: left; }
.corner-value.top-right { top: 20px; right: 20px; align-items: flex-end; text-align: right; }
.corner-value.bottom-left { bottom: 20px; left: 20px; align-items: flex-start; text-align: left; }
.corner-value.bottom-right { bottom: 20px; right: 20px; align-items: flex-end; text-align: right; }

.side-value {
  position: absolute;
  display: flex;
  flex-direction: column;
  gap: 4px;
  color: #333;
}

.side-value.mid-left {
  position: absolute;
  width: 100px;
  height: 100px;
  top: 50%;
  left: 20px;
}

.side-value-item {
  display: flex;
  align-items: center;
  gap: 4px;
}

.bottom-stats {
  position: absolute;
  bottom: 10px;
  left: 50%;
  transform: translateX(-50%);
  display: flex;
  gap: 20px;
  z-index: 2;
}

/* ====== ICONS AND BUTTONS ====== */
.settings-icon, .back-icon, .refresh-button {
  font-size: 32px;
  cursor: pointer;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.1);
  border: none;
  opacity: 0.7;
  width: 40px;
  height: 40px;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.3s ease;
}

.refresh-button {
  border-radius: 8px;
  background: #2a2a2a;
  border: 1px solid #555;
}

.settings-icon:hover, .back-icon:hover {
  background: rgba(255, 255, 255, 0.2);
  opacity: 1;
  transform: scale(1.1);
}

.refresh-button:hover {
  background: #3a3a3a;
  transform: scale(1.05);
}

.refresh-button:active {
  transform: scale(0.95);
}

/* ====== DATA DISPLAYS ====== */
.temp-value, .humidity-value, .humidity-abs, .comfort-temp {
  font-size: 16px;
  font-weight: 500;
  display: flex;
  align-items: center;
  gap: 4px;
}

.dehum-mode, .dehum-active {
  font-size: 20px;
  color: #ff9800;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  min-height: 28px;
  font-weight: 500;
}

.comfort-temp { color: #4a90e2; }

/* ====== ICON CIRCLES ====== */
.icon-circle {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  display: flex;
  justify-content: center;
  font-size: 20px;
}

.icon-circle.blue { background: #4a90e2; color: white; }
.icon-circle.red { background: #e74c3c; color: white; }

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

/* ====== PARAMETER EDIT MODE ====== */
.parameter-edit-section {
  background: linear-gradient(135deg, #e8f4fd 0%, #d1ecf1 100%);
  border-radius: 12px;
  padding: 20px;
  margin-bottom: 16px;
  min-height: 280px;
  display: flex;
  flex-direction: column;
}

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

.param-list {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 16px;
  max-height: 400px;
  overflow-y: auto;
  padding-right: 8px;
}

.param-list::-webkit-scrollbar { width: 6px; }
.param-list::-webkit-scrollbar-track { background: rgba(255, 255, 255, 0.1); border-radius: 3px; }
.param-list::-webkit-scrollbar-thumb { background: rgba(30, 58, 138, 0.3); border-radius: 3px; }

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
  padding: 8px 16px;
  background: #4a90e2;
  color: white;
  border: none;
  border-radius: 6px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.3s ease;
}

.param-update-btn:hover {
  background: #357abd;
  transform: translateY(-1px);
}

.param-update-btn:active {
  transform: translateY(0);
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
