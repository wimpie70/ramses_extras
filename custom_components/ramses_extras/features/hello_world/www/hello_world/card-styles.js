export const CARD_STYLE = `
/* ====== ROOT CONTAINER ====== */
ha-card {
  padding: 16px;
  background: var(--ha-card-background, var(--card-background-color, var(--primary-background-color)));
  border-radius: var(--ha-card-border-radius, 12px);
}

/* ====== HEADER ====== */
.r-xtrs-hello-card-header {
  margin-bottom: 16px;
  font-weight: 500;
}

.r-xtrs-hello-device-info {
  font-size: 1.1em;
  color: var(--primary-text-color);
}

/* ====== CONTENT ====== */
.r-xtrs-hello-card-content {
  display: flex;
  flex-direction: column;
  gap: 12px;
  text-align: center;
  justify-content: center;
}

.r-xtrs-hello-button-instruction {
  font-size: 0.9em;
  color: var(--secondary-text-color);
  margin-bottom: 12px;
}

.r-xtrs-hello-button-container {
  display: flex;
  justify-content: center;
  align-items: center;
  gap: 12px;
  margin-bottom: 8px;
}

/* ====== TOGGLE BUTTON ====== */
.r-xtrs-hello-toggle-button {
  --mdc-theme-primary: var(--primary-color);
  --mdc-theme-on-primary: var(--text-primary-color, #fff);
  min-width: 120px;
  height: 40px;
  font-weight: 500;
  border-radius: 8px;
  transition: all 0.3s ease;
  cursor: pointer;
  border: none;
  outline: none;
  display: flex;
  align-items: center;
  justify-content: center;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.r-xtrs-hello-toggle-button.on {
  background-color: var(--primary-color);
  color: var(--text-primary-color, #fff);
  box-shadow: var(--ha-card-box-shadow, 0 2px 4px rgba(0, 0, 0, 0.2));
}

.r-xtrs-hello-toggle-button.off {
  background-color: var(--secondary-background-color);
  color: var(--primary-text-color);
  border: 2px solid var(--divider-color);
}

.r-xtrs-hello-toggle-button:hover {
  transform: translateY(-1px);
  box-shadow: var(--ha-card-box-shadow, 0 4px 8px rgba(0, 0, 0, 0.3));
}

.r-xtrs-hello-toggle-button:active {
  transform: translateY(0);
  box-shadow: var(--ha-card-box-shadow, 0 2px 4px rgba(0, 0, 0, 0.2));
}

/* ====== STATUS ELEMENTS ====== */
.r-xtrs-hello-status {
  font-size: 0.9em;
  color: var(--secondary-text-color);
  font-weight: 500;
}

.r-xtrs-hello-binary-sensor-status {
  font-size: 0.8em;
  color: var(--secondary-text-color);
  margin-top: 8px;
  padding: 8px;
  background-color: var(--ha-card-background, var(--card-background-color));
  border-radius: 6px;
}

/* ====== RESPONSIVE ====== */
@media (max-width: 480px) {
  .r-xtrs-hello-button-container {
    flex-direction: column;
    gap: 8px;
  }

  .toggle-button {
    width: 100%;
    min-width: unset;
  }

  .r-xtrs-hello-device-info {
    font-size: 1em;
  }
}

/* ====== ANIMATIONS ====== */
@keyframes pulse {
  0% { transform: scale(1); }
  50% { transform: scale(1.05); }
  100% { transform: scale(1); }
}

.r-xtrs-hello-toggle-button:active {
  animation: pulse 0.2s ease-in-out;
}
`;
