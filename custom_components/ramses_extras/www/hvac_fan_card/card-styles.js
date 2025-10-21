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
  top: 50%;
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
  font-size: 14px;
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
  color: #333;
  font-size: 14px;
  white-space: nowrap;
  padding: 8px 16px;
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
  color: #333;
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
  color: #333;
}


.side-value.mid-left {
  position: absolute;
  width: 100px;
  height: 100px;
  top: 50%;
  left: 20px;
}

.refresh-button {
  background: #2a2a2a;
  border: 1px solid #555;
  border-radius: 8px;
  padding: 12px;
  width: 60px;
  height: 60px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  color: #ffffff;
  transition: all 0.2s ease;
}

.refresh-button:hover {
  background: #3a3a3a;
  transform: scale(1.05);
}

.refresh-button:active {
  transform: scale(0.95);
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
  font-size: 20px;
  color: #ff9800;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  min-height: 28px;
  font-weight: 500;
}

.humidity-value {
  font-size: 16px;
  font-weight: 500;
  display: flex;
  align-items: center;
  gap: 4px;
}

.humidity-abs {
  font-size: 16px;
  font-weight: 500;
  display: flex;
  align-items: center;
  gap: 4px;
}

.comfort-temp {
  font-size: 16px;
  font-weight: 500;
  display: flex;
  align-items: center;
  gap: 4px;
  color: #ff9800;
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

.control-button:hover {
  background: #353535;
  border-color: #4a90e2;
}

.control-button.active {
  background: #3a3a3a;
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
`;