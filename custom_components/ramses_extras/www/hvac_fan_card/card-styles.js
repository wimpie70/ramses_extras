export const CARD_STYLE = `
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
  background: linear-gradient(135deg, #f5f5f5 0%, #e0e0e0 100%);
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

.centre-container {
  position: absolute;
  width: 150px;
  height: 150px;
  bottom: 70px;
  left: 50%;
  transform: translateX(-50%);
  flex-shrink: 0;
  z-index: 1;
}

.centre {
  width: 100px;
  height: 100px;
  position: absolute;
  top: 10%;
  left: 50%;
  transform: translate(-50%, -50%);
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-direction: column;
}

.centre-inner {
  text-align: center;
  color: black;
  font-weight: 600;
}

.speed-display {
  margin-bottom: 4px;
}

.fanmode {
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
  padding: 6px 14px;
  background: rgba(255, 255, 255, 0.1);
  border-radius: 20px;
  min-width: 80px;
}

.timer-icon {
  width: 20px; /* 0.7 * 24px (24px is the viewBox size) */
  height: 20px; /* 0.7 * 24px (24px is the viewBox size) */
  flex-shrink: 0;
}

.corner-value {
  position: absolute;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.corner-value.top-left {
  top: 20px;
  left: 20px;
  align-items: flex-start;
  text-align: left;
}

.corner-value.top-right {
  top: 20px;
  right: 20px;
  align-items: flex-end;
  text-align: right;
}

.corner-value.bottom-left {
  bottom: 20px;
  left: 20px;
  align-items: flex-start;
  text-align: left;
}

.corner-value.bottom-right {
  bottom: 20px;
  right: 20px;
  align-items: flex-end;
  text-align: right;
}

.side-value {
  position: absolute;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.side-value.mid-left {
  position: absolute;
  width: 100px;
  top: 50%;
  left: 20px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.side-value-item {
  display: flex;
  align-items: center;
  gap: 4px;
}

.settings-container {
  margin-top: 8px;
  display: flex;
  justify-content: center;
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

.settings-icon, .back-icon {
  font-size: 32px;
  cursor: pointer;
  // padding: 8px;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.1);
  border: none;
  transition: all 0.3s ease;
  opacity: 0.7;
  width: 40px;
  height: 40px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.settings-icon:hover {
  background: rgba(255, 255, 255, 0.2);
  opacity: 1;
  transform: scale(1.1);
}

.temp-value {
  font-size: 20px;
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: 4px;
}

.dehum-mode,
.dehum-active {
  color: #ff9800;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  min-height: 28px;
}

.humidity-value,
.humidity-abs {
  display: flex;
  align-items: center;
  gap: 4px;
}

.comfort-temp {
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: 4px;
  color: #2d5aa0;
  background: rgba(74, 144, 226, 0.1);
  padding: 4px 8px;
  border-radius: 6px;
  border: 1px solid rgba(74, 144, 226, 0.2);
}

.icon-circle {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  display: flex;
  justify-content: center;
  font-size: 20px;
}

.icon-circle.blue {
  background: #4a90e2;
  color: white;
}

.icon-circle.red {
  background: #e74c3c;
  color: white;
}

.airflow-diagram {
  position: absolute;
  width: 200px;
  height: 160px;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  z-index: 0;
}

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

.control-button:hover,
.control-button.active {
  background: #353535;
  border-color: #4a90e2;
}

.control-icon {
  font-size: 32px;
  color: #4a90e2;
}

.control-label {
  color: #ffffff;
  text-align: center;
}

/* Parameter Edit Mode Styles */
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

.settings-icon, .back-icon {
  cursor: pointer;
  padding: 2px;
  border-radius: 8px;
  transition: all 0.3s ease;
  background: rgba(255, 255, 255, 0.2);
}

.settings-icon:hover, .back-icon:hover {
  background: rgba(255, 255, 255, 0.4);
  transform: scale(1.1);
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

.param-list::-webkit-scrollbar {
  width: 6px;
}

.param-list::-webkit-scrollbar-track {
  background: rgba(255, 255, 255, 0.1);
  border-radius: 3px;
}

.param-list::-webkit-scrollbar-thumb {
  background: rgba(30, 58, 138, 0.3);
  border-radius: 3px;
}

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

.param-item.loading {
  border-color: #ffc107;
  background: #fff3cd;
}

.param-item.success {
  border-color: #28a745;
  background: #d4edda;
}

.param-item.error {
  border-color: #dc3545;
  background: #f8d7da;
}

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
  transition: all 0.3s ease;
  color: #333;
  font-weight: 500;
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

.param-status.loading::after {
  content: "⏳";
  animation: spin 1s linear infinite;
}

.param-status.success::after {
  content: "✅";
  color: #28a745;
}

.param-status.error::after {
  content: "❌";
  color: #dc3545;
}

@keyframes spin {
  0% { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
}

/* Responsive adjustments */
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

  .param-input {
    flex: 1;
  }
}
`;
