/**
 * Device Simulator Card for Ramses Extras
 * Phase 8: UI Cards - Main simulator interface
 */

import { RamsesBaseCard } from '../../helpers/ramses-base-card.js';

const CARD_STYLE = `
  :host { display: block; padding: 16px; }
  .header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 16px; }
  .title { font-size: 1.2em; font-weight: 500; }
  .badge { padding: 4px 12px; border-radius: 12px; font-size: 0.75em; text-transform: uppercase; }
  .badge.active { background: var(--success-color, #4caf50); color: white; }
  .badge.running { background: var(--primary-color, #03a9f4); color: white; animation: pulse 1.5s infinite; }
  @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.6; } }
  .tabs { display: flex; gap: 8px; margin-bottom: 16px; border-bottom: 1px solid var(--divider-color); }
  .tab { padding: 12px 16px; cursor: pointer; border-bottom: 2px solid transparent; font-size: 0.9em; }
  .tab.active { color: var(--primary-color); border-bottom-color: var(--primary-color); }
  .content { display: none; }
  .content.active { display: block; }
  .btn { padding: 8px 16px; border: none; border-radius: 4px; cursor: pointer; font-size: 0.85em; }
  .btn-primary { background: var(--primary-color); color: var(--text-primary-color); }
  .btn-secondary { background: var(--secondary-background-color); color: var(--primary-text-color); border: 1px solid var(--divider-color); }
  .btn-danger { background: var(--error-color); color: white; }
  .grid { display: grid; gap: 12px; }
  .card { border: 1px solid var(--divider-color); border-radius: 8px; padding: 16px; }
  .card:hover { border-color: var(--primary-color); }
  .card.active { border-color: var(--success-color); background: var(--success-color-light); }
  .stats { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 16px; }
  .stat { background: var(--secondary-background-color); padding: 16px; border-radius: 8px; text-align: center; }
  .stat-value { font-size: 1.5em; font-weight: 600; color: var(--primary-color); }
  .event-log { max-height: 300px; overflow-y: auto; border: 1px solid var(--divider-color); border-radius: 8px; }
  .event { display: flex; gap: 12px; padding: 8px; border-bottom: 1px solid var(--divider-color); font-size: 0.85em; }
  .event.unavailable { background: var(--error-color-light); border-left: 3px solid var(--error-color); }
  .event-type { padding: 2px 6px; border-radius: 4px; font-size: 0.75em; text-transform: uppercase; }
  .event-type.rx { background: var(--success-color-light); color: var(--success-color); }
  .event-type.tx { background: var(--info-color-light); color: var(--info-color); }
  .event-type.unavailable { background: var(--error-color-light); color: var(--error-color); }
  .device-actions { display: flex; gap: 8px; margin-top: 8px; align-items: center; flex-wrap: wrap; }
  .toggle { display: flex; align-items: center; gap: 6px; cursor: pointer; font-size: 0.85em; }
  .codes-row { display: flex; gap: 6px; flex-wrap: wrap; margin-top: 6px; align-items: center; }
  .code-chip { display: flex; align-items: center; gap: 4px; padding: 2px 8px; border-radius: 12px; font-size: 0.75em; background: var(--secondary-background-color); border: 1px solid var(--divider-color); }
  .code-chip button { background: none; border: none; cursor: pointer; padding: 0; font-size: 0.9em; color: var(--secondary-text-color); line-height: 1; }
  .add-code { display: flex; gap: 4px; margin-top: 4px; }
  .add-code input { padding: 3px 6px; border: 1px solid var(--divider-color); border-radius: 4px; font-size: 0.8em; width: 80px; background: var(--card-background-color); color: var(--primary-text-color); }
  .scenario-form { margin-top: 8px; display: flex; flex-direction: column; gap: 8px; }
  .scenario-field { display: flex; flex-direction: column; gap: 4px; font-size: 0.8em; }
  .scenario-field label { color: var(--secondary-text-color); font-weight: 600; display: flex; align-items: center; justify-content: space-between; gap: 8px; }
  .scenario-field input[type="text"],
  .scenario-field input[type="search"],
  .scenario-field input[type="number"] { padding: 4px 8px; border: 1px solid var(--divider-color); border-radius: 4px; background: var(--card-background-color); color: var(--primary-text-color); font-size: 0.9em; }
  .scenario-field--checkbox { flex-direction: row; align-items: center; gap: 8px; }
  .scenario-field--checkbox label { font-weight: 500; margin: 0; }
  .scenario-description { margin-top: 6px; font-size: 0.8em; color: var(--secondary-text-color); }
`;

class DeviceSimulatorCard extends RamsesBaseCard {
  constructor() {
    super();
    this._profiles = [];
    this._devices = [];
    this._scenarioRegistry = {};
    this._scenarioSchemas = {};
    this._runningScenarios = [];
    this._autoAnswer = true;
    this._emissionsActive = false;
    this._events = [];
    this._stats = { rx: 0, tx: 0, devices: 0, active: 0 };
    this._tab = "profiles";
    this._newCodeInput = {};
    this._profileSpeed = {};
    this._profileReload = {};
    this._profileNotice = null;
    this._scenarioParams = {};
  }

  // ========== REQUIRED BASE CLASS OVERRIDES ==========

  getCardSize() {
    return 6;
  }

  getFeatureName() {
    return "device_simulator";
  }

  hasValidConfig() {
    return true;
  }

  static getCardInfo() {
    return {
      type: "device-simulator-card",
      name: "Device Simulator",
      description: "Control and monitor the Ramses device simulator",
      preview: true,
      documentationURL: "https://github.com/wimpie70/ramses_extras",
    };
  }

  async _loadInitialState() {
    await this._fetchData();
  }

  _onConnected() {
    this._fetchData();
  }

  // ========== DATA FETCHING ==========

  async _fetchData() {
    if (!this._hass) return;
    try {
      const result = await this._hass.callWS({
        type: "ramses_extras/device_simulator/get_status",
      });
      this._profiles = result.profiles || [];
      this._devices = result.devices || [];
      this._scenarioRegistry = result.scenario_registry || {};
      this._scenarioSchemas = result.scenario_param_schemas || {};
      this._runningScenarios = result.running_scenarios || [];
      this._autoAnswer = result.auto_answer !== false;
      this._emissionsActive = result.autonomous_emissions_active === true;
      this._stats = result.stats || this._stats;
      this._activeProfile = result.active_profile;
      this._scheduleRender();
    } catch {
      // Silently handle fetch errors
    }
  }

  // ========== INTERACTIONS ==========

  _setTab(tab) {
    this._tab = tab;
    this._scheduleRender();
  }

  async _loadProfile(name) {
    const speed = this._profileSpeed[name] ?? 1.0;
    const reloadRf = this._profileReload[name] ?? true;
    const result = await this._hass.callWS({
      type: "ramses_extras/device_simulator/load_profile",
      profile: name,
      speed,
      reload_ramses_cc: reloadRf,
    });
    this._activeProfile = name;
    this._scenarioState = "idle";
    this._activeScenario = null;
    if (result?.actions?.includes("reloading_ramses_cc")) {
      this._profileNotice = "ramses_cc is reloading — wait a few seconds before starting scenarios.";
      setTimeout(() => { this._profileNotice = null; this._scheduleRender(); }, 5000);
    } else {
      this._profileNotice = null;
    }
    await new Promise((r) => setTimeout(r, 300));
    await this._fetchData();
  }

  async _startScenario(scenarioId) {
    const params = this._prepareScenarioParams(scenarioId);
    try {
      await this._hass.callWS({
        type: "ramses_extras/device_simulator/start_scenario",
        scenario: scenarioId,
        params,
      });
    } catch (error) {
      // eslint-disable-next-line no-console
      console.error("DeviceSimulatorCard: failed to start scenario", error);
    }
    await new Promise((r) => setTimeout(r, 500));
    await this._fetchData();
  }

  async _stopScenario(scenarioId) {
    try {
      await this._hass.callWS({
        type: "ramses_extras/device_simulator/stop_scenario",
        scenario: scenarioId,
      });
    } catch (error) {
      // eslint-disable-next-line no-console
      console.error("DeviceSimulatorCard: failed to stop scenario", error);
    }
    await new Promise((r) => setTimeout(r, 300));
    await this._fetchData();
  }

  async _setAutoAnswer(enabled) {
    await this._hass.callWS({
      type: "ramses_extras/device_simulator/set_auto_answer",
      enabled,
    });
    this._autoAnswer = enabled;
    this._scheduleRender();
    await new Promise((r) => setTimeout(r, 300));
    await this._fetchData();
  }

  // ========== RENDERING ==========

  _renderContent() {
    const hasRunning = this._runningScenarios.length > 0;
    const emittingNow = this._emissionsActive && this._autoAnswer;
    const badgeClass = hasRunning ? "running" : emittingNow ? "active" : this._devices.length > 0 ? "" : "";
    const enabledCount = this._devices.filter(d => d.enabled).length;
    const badgeTitle = hasRunning
      ? `Running: ${this._runningScenarios.join(", ")}`
      : emittingNow ? `${enabledCount} device(s) emitting`
      : this._emissionsActive && !this._autoAnswer ? "Devices loaded but auto-answer is off — silent"
      : this._devices.length > 0 ? "Devices loaded, emissions idle"
      : "No active devices";
    const badgeText = hasRunning ? "Running"
      : emittingNow ? `${enabledCount} emitting`
      : this._devices.length > 0 ? `${enabledCount} silent`
      : "Idle";

    this.shadowRoot.innerHTML = `
      <style>${CARD_STYLE}</style>
      <ha-card>
        <div class="header">
          <div style="display: flex; flex-direction: column; gap: 2px;">
            <div class="title">🔌 ${this._config?.title || "Device Simulator"}</div>
            ${this._activeProfile ? `<div style="font-size: 0.8em; color: var(--secondary-text-color);">Profile: <strong>${this._activeProfile}</strong></div>` : ""}
          </div>
          <div class="badge ${badgeClass}" title="${badgeTitle}">${badgeText}</div>
        </div>

        <div class="tabs">
          <div class="tab ${this._tab === "profiles" ? "active" : ""}" data-tab="profiles">Profiles</div>
          <div class="tab ${this._tab === "devices" ? "active" : ""}" data-tab="devices">Devices</div>
          <div class="tab ${this._tab === "scenarios" ? "active" : ""}" data-tab="scenarios">Scenarios</div>
          <div class="tab ${this._tab === "events" ? "active" : ""}" data-tab="events">Events</div>
        </div>

        <div class="content ${this._tab === "profiles" ? "active" : ""}" data-content="profiles">
          ${this._buildProfiles()}
        </div>
        <div class="content ${this._tab === "devices" ? "active" : ""}" data-content="devices">
          ${this._buildDevices()}
        </div>
        <div class="content ${this._tab === "scenarios" ? "active" : ""}" data-content="scenarios">
          ${this._buildScenarios()}
        </div>
        <div class="content ${this._tab === "events" ? "active" : ""}" data-content="events">
          ${this._buildEvents()}
        </div>
      </ha-card>
    `;
    this._attachListeners();
  }

  _attachListeners() {
    const root = this.shadowRoot;

    root.querySelectorAll(".tab").forEach(tab => {
      tab.addEventListener("click", () => this._setTab(tab.dataset.tab));
    });

    root.querySelectorAll("[data-action='load-profile']").forEach(btn => {
      btn.addEventListener("click", () => this._loadProfile(btn.dataset.profile));
    });

    root.querySelectorAll("[data-action='start-scenario']").forEach(btn => {
      btn.addEventListener("click", () => this._startScenario(btn.dataset.scenarioId));
    });

    root.querySelectorAll("[data-action='stop-scenario']").forEach(btn => {
      btn.addEventListener("click", () => this._stopScenario(btn.dataset.scenarioId));
    });

    const aaToggle = root.querySelector("[data-action='toggle-auto-answer']");
    if (aaToggle) aaToggle.addEventListener("change", (e) => this._setAutoAnswer(e.target.checked));

    root.querySelectorAll("[data-action='toggle-device']").forEach(el => {
      el.addEventListener("change", () => {
        const d = this._devices.find(d => d.id === el.dataset.deviceId);
        if (d) this._toggleDeviceEnabled(d.id, d.enabled);
      });
    });

    root.querySelectorAll("[data-action='remove-code']").forEach(btn => {
      btn.addEventListener("click", () => this._removeExcludedCode(btn.dataset.deviceId, btn.dataset.code));
    });

    root.querySelectorAll("[data-action='add-code']").forEach(btn => {
      btn.addEventListener("click", () => this._addExcludedCode(btn.dataset.deviceId));
    });

    root.querySelectorAll("[data-action='code-input']").forEach(input => {
      input.addEventListener("input", (e) => {
        this._newCodeInput = { ...this._newCodeInput, [input.dataset.deviceId]: e.target.value };
      });
      input.addEventListener("keydown", (e) => {
        if (e.key === "Enter") this._addExcludedCode(input.dataset.deviceId);
      });
    });

    root.querySelectorAll("[data-action='speed-select']").forEach(sel => {
      sel.addEventListener("change", (e) => {
        this._profileSpeed = { ...this._profileSpeed, [sel.dataset.profile]: parseFloat(e.target.value) };
      });
    });

    root.querySelectorAll("[data-action='reload-check']").forEach(chk => {
      chk.addEventListener("change", (e) => {
        this._profileReload = { ...this._profileReload, [chk.dataset.profile]: e.target.checked };
      });
    });

    root.querySelectorAll("[data-action='scenario-param']").forEach((input) => {
      const handler = () => this._handleScenarioParamInput(input);
      const dataType = (input.dataset.type || input.type || "text").toLowerCase();
      if (dataType === "checkbox") {
        input.addEventListener("change", handler);
      } else {
        input.addEventListener("input", handler);
        input.addEventListener("change", handler);
      }
    });

    const dismissNotice = root.querySelector("[data-action='dismiss-notice']");
    if (dismissNotice) {
      dismissNotice.addEventListener("click", () => { this._profileNotice = null; this._scheduleRender(); });
    }
  }

  async _clearCache({ clearSchema = true, clearPackets = false } = {}) {
    const result = await this._hass.callWS({
      type: "ramses_extras/device_simulator/clear_ramses_cache",
      clear_schema: clearSchema,
      clear_packets: clearPackets,
    });
    return result;
  }

  async _toggleDeviceEnabled(deviceId, current) {
    try {
      await this._hass.callWS({
        type: "ramses_extras/device_simulator/set_device_enabled",
        device_id: deviceId,
        enabled: !current,
      });
      this._devices = this._devices.map((d) =>
        d.id === deviceId ? { ...d, enabled: !current } : d
      );
      this._scheduleRender();
    } catch {
      this._fetchData();
    }
  }

  async _removeExcludedCode(deviceId, code) {
    const device = this._devices.find((d) => d.id === deviceId);
    if (!device) return;
    const updated = device.excluded_codes.filter((c) => c !== code);
    try {
      await this._hass.callWS({
        type: "ramses_extras/device_simulator/set_device_excluded_codes",
        device_id: deviceId,
        excluded_codes: updated,
      });
      this._devices = this._devices.map((d) =>
        d.id === deviceId ? { ...d, excluded_codes: updated } : d
      );
      this._scheduleRender();
    } catch {
      this._fetchData();
    }
  }

  async _addExcludedCode(deviceId) {
    const code = (this._newCodeInput[deviceId] || "").trim().toUpperCase();
    if (!code) return;
    const device = this._devices.find((d) => d.id === deviceId);
    if (!device || device.excluded_codes.includes(code)) return;
    const updated = [...device.excluded_codes, code];
    try {
      await this._hass.callWS({
        type: "ramses_extras/device_simulator/set_device_excluded_codes",
        device_id: deviceId,
        excluded_codes: updated,
      });
      this._devices = this._devices.map((d) =>
        d.id === deviceId ? { ...d, excluded_codes: updated } : d
      );
      this._newCodeInput = { ...this._newCodeInput, [deviceId]: "" };
      this._scheduleRender();
    } catch {
      this._fetchData();
    }
  }

  _knownList() {
    const profile = this._profiles.find((p) => p.name === this._activeProfile);
    return profile?.known_list || {};
  }

  // ========== HTML BUILDERS ==========

  _buildProfiles() {
    const profileCards = this._profiles.length === 0
      ? "<div>No profiles available</div>"
      : this._profiles.map((p) => {
          const speedOptions = (p.speed_options || [1.0, 0.1, 0.01]).map((s) => {
            const label = s === 1.0 ? "1× (normal)" : s === 0.1 ? "10× faster" : s === 0.01 ? "100× faster" : `${s}×`;
            const sel = (this._profileSpeed[p.name] ?? 1.0) === s ? " selected" : "";
            return `<option value="${s}"${sel}>${label}</option>`;
          }).join("");
          const reloadChecked = (this._profileReload[p.name] ?? true) ? " checked" : "";
          return `
            <div class="card ${this._activeProfile === p.name ? "active" : ""}">
              <div><strong>${p.name}</strong></div>
              <div style="font-size: 0.85em; color: var(--secondary-text-color); margin-bottom: 8px;">${p.description || "No description"}</div>
              <div style="display: flex; gap: 8px; align-items: center; flex-wrap: wrap;">
                <label style="font-size: 0.8em;">Speed:</label>
                <select data-action="speed-select" data-profile="${p.name}"
                  style="font-size: 0.8em; padding: 2px 4px; border: 1px solid var(--divider-color); border-radius: 4px; background: var(--card-background-color); color: var(--primary-text-color);">
                  ${speedOptions}
                </select>
                <label style="font-size: 0.8em; display: flex; align-items: center; gap: 4px; cursor: pointer;">
                  <input type="checkbox" data-action="reload-check" data-profile="${p.name}"${reloadChecked} />
                  Reload RF
                </label>
                <button class="btn btn-primary" data-action="load-profile" data-profile="${p.name}">Load</button>
              </div>
            </div>`;
        }).join("");

    const notice = this._profileNotice
      ? `<div style="margin-top: 12px; padding: 8px 12px; background: var(--warning-color, #ff9800); color: white; border-radius: 6px; font-size: 0.85em; display: flex; justify-content: space-between; align-items: center; gap: 8px;">
           <span>⚠️ ${this._profileNotice}</span>
           <button data-action="dismiss-notice" style="background: none; border: none; color: white; cursor: pointer; font-size: 1.1em; line-height: 1; padding: 0 2px;">✕</button>
         </div>`
      : "";

    return `<div class="grid">${profileCards}</div>${notice}`;
  }

  _buildDevices() {
    if (this._devices.length === 0) {
      return `<div style="color: var(--secondary-text-color); padding: 8px 0;">No active devices. Start an autonomous emissions scenario first.</div>`;
    }
    const knownList = this._knownList();
    return `<div class="grid">${this._devices.map((d) => {
      const knownBadge = knownList[d.id]
        ? `<span style="padding: 1px 6px; border-radius: 10px; font-size: 0.7em; font-weight: 600; background: var(--primary-color); color: white;">known</span>`
        : "";
      const chips = (d.excluded_codes || []).map((code) =>
        `<span class="code-chip">${code}<button data-action="remove-code" data-device-id="${d.id}" data-code="${code}" title="Remove">✕</button></span>`
      ).join("");
      const checkedAttr = d.enabled ? " checked" : "";
      return `
        <div class="card">
          <div style="display: flex; justify-content: space-between; align-items: center;">
            <div><strong>${d.id}</strong> <span style="color: var(--secondary-text-color); font-size: 0.85em;">${d.type}</span></div>
            ${knownBadge}
          </div>
          <div class="device-actions">
            <label class="toggle">
              <ha-switch data-action="toggle-device" data-device-id="${d.id}"${checkedAttr}></ha-switch>
              <span>${d.enabled ? "Enabled" : "Disabled"}</span>
            </label>
          </div>
          <div style="font-size: 0.8em; color: var(--secondary-text-color); margin-top: 8px;">Excluded codes:</div>
          <div class="codes-row">${chips}</div>
          <div class="add-code">
            <input type="text" maxlength="4" placeholder="1FC9"
              data-action="code-input" data-device-id="${d.id}"
              value="${this._newCodeInput[d.id] || ""}" />
            <button class="btn btn-primary" data-action="add-code" data-device-id="${d.id}">+ Exclude</button>
          </div>
        </div>`;
    }).join("")}</div>`;
  }

  _handleScenarioParamInput(input) {
    const { scenarioId, field, type } = input.dataset;
    let value;
    if (input.type === "checkbox") {
      value = input.checked;
    } else if (type === "number") {
      const parsed = input.value === "" ? null : Number(input.value);
      value = Number.isNaN(parsed) ? null : parsed;
    } else {
      value = input.value;
    }
    this._scenarioParams = {
      ...this._scenarioParams,
      [scenarioId]: { ...(this._scenarioParams[scenarioId] || {}), [field]: value },
    };
  }

  _prepareScenarioParams(scenarioId) {
    const schema = this._scenarioSchemas[scenarioId] || [];
    const overrides = this._scenarioParams[scenarioId] || {};
    const result = {};
    schema.forEach((field) => {
      const key = field.key;
      let value = overrides[key];
      if (value === undefined || value === null || value === "") {
        if (field.default !== undefined) {
          value = field.default;
        } else {
          return;
        }
      }
      if (field.type === "number") {
        const parsed = Number(value);
        if (!Number.isNaN(parsed)) {
          result[key] = parsed;
        }
        return;
      }
      if (field.type === "csv") {
        const list = String(value)
          .split(/[,\s]/)
          .map((item) => item.trim())
          .filter(Boolean);
        if (list.length) {
          result[key] = list;
        }
        return;
      }
      if (field.type === "checkbox") {
        result[key] = Boolean(value);
        return;
      }
      result[key] = value;
    });
    return result;
  }

  _buildScenarioParamsById(scenarioId) {
    const schema = this._scenarioSchemas[scenarioId];
    if (!schema || schema.length === 0) {
      return "";
    }
    const overrides = this._scenarioParams[scenarioId] || {};
    const fields = schema
      .map((field) => this._renderScenarioField(scenarioId, field, overrides[field.key]))
      .join("");
    return `<div class="scenario-form">${fields}</div>`;
  }

  _renderScenarioField(scenarioId, field, rawValue) {
    const value = rawValue ?? field.default ?? "";
    const inputId = `${scenarioId}-${field.key}`;
    const requiredMark = field.required ? "<span style=\"color:var(--error-color);\">*</span>" : "";
    const commonAttrs = `data-action="scenario-param" data-scenario-id="${scenarioId}" data-field="${field.key}" data-type="${field.type || 'text'}"`;

    if (field.type === "checkbox") {
      const checked = value === true ? " checked" : "";
      return `
        <div class="scenario-field scenario-field--checkbox">
          <label for="${inputId}">${field.label || field.key} ${requiredMark}</label>
          <ha-switch id="${inputId}" ${commonAttrs} type="checkbox"${checked}></ha-switch>
        </div>`;
    }

    const inputType = field.type === "number" ? "number" : "text";
    const stepAttr = field.step ? ` step="${field.step}"` : "";
    const minAttr = field.min !== undefined ? ` min="${field.min}"` : "";
    const maxAttr = field.max !== undefined ? ` max="${field.max}"` : "";
    const placeholder = field.placeholder || "";
    return `
      <div class="scenario-field">
        <label for="${inputId}">${field.label || field.key} ${requiredMark}</label>
        <input id="${inputId}" ${commonAttrs} type="${inputType}"${stepAttr}${minAttr}${maxAttr} placeholder="${placeholder}" value="${value}" />
      </div>`;
  }

  _buildScenarios() {
    const registry = this._scenarioRegistry;
    const ids = Object.keys(registry);
    if (!ids.length) return `<div style="color: var(--secondary-text-color); padding: 8px 0;">No scenarios available.</div>`;

    const aaChecked = this._autoAnswer ? " checked" : "";
    const aaCard = `
      <div class="card ${this._autoAnswer ? "active" : ""}">
        <div style="display: flex; justify-content: space-between; align-items: center;">
          <div><strong>Auto Answer (RQ&#8594;RP)</strong></div>
          <label class="toggle">
            <ha-switch data-action="toggle-auto-answer"${aaChecked}></ha-switch>
          </label>
        </div>
        <div style="font-size: 0.85em; color: var(--secondary-text-color); margin-top: 4px;">When off: simulator receives RQ frames but never replies &#8212; simulates broken ESP or powered-off device.</div>
      </div>`;

    const scenarioCards = ids
      .filter(id => id !== "auto_answer")
      .map((id) => {
        const meta = registry[id];
        const isRunning = this._runningScenarios.includes(id);
        const conflicts = this._runningScenarios
          .filter(r => r !== id)
          .filter(r => {
            const rm = registry[r] || {};
            const rc = rm.can_run_with || [];
            const nc = meta.can_run_with || [];
            return !(rc.includes("*") || nc.includes("*") || rc.includes(id) || nc.includes(r));
          });
        const conflictWarn = conflicts.length
          ? `<div style="font-size: 0.75em; color: var(--warning-color, #ff9800); margin-top: 4px;">&#9888; Conflicts with: ${conflicts.join(", ")}</div>`
          : "";
        const disabledAttr = conflicts.length ? ' style="opacity:0.7"' : "";
        const actionBtns = meta.toggleable
          ? (isRunning
            ? `<button class="btn btn-danger" data-action="stop-scenario" data-scenario-id="${id}">Stop</button>`
            : `<button class="btn btn-primary" data-action="start-scenario" data-scenario-id="${id}"${disabledAttr}>Start</button>`)
          : `<button class="btn btn-primary" data-action="start-scenario" data-scenario-id="${id}"${disabledAttr}>Run</button>`;
        return `
          <div class="card ${isRunning ? "active" : ""}">
            <div style="display: flex; justify-content: space-between; align-items: center;">
              <strong>${meta.label || id}</strong>
              ${isRunning ? `<span style="font-size:0.75em; padding:2px 8px; border-radius:10px; background:var(--success-color,#4caf50); color:white;">running</span>` : ""}
            </div>
            <div class="scenario-description">${meta.description || "No description"}</div>
            ${conflictWarn}
            ${this._buildScenarioParamsById(id)}
            <div style="margin-top: 8px; display: flex; gap: 8px;">${actionBtns}</div>
          </div>`;
      }).join("");

    return `<div class="grid">${aaCard}${scenarioCards}</div>`;
  }

  _buildEvents() {
    const events = this._events.length === 0
      ? `<div style="padding: 16px; text-align: center; color: var(--secondary-text-color);">No events</div>`
      : this._events.map((e) =>
          `<div class="event ${e.type === "unavailable" ? "unavailable" : ""}">
             <span class="event-type ${e.type}">${e.type}</span>
             <span>${e.message}</span>
           </div>`
        ).join("");
    return `
      <div class="stats">
        <div class="stat"><div class="stat-value">${this._stats.rx}</div><div>RX</div></div>
        <div class="stat"><div class="stat-value">${this._stats.tx}</div><div>TX</div></div>
        <div class="stat"><div class="stat-value">${this._stats.devices}</div><div>Devices</div></div>
        <div class="stat"><div class="stat-value">${this._stats.active}</div><div>Active</div></div>
      </div>
      <div class="event-log">${events}</div>`;
  }
}

DeviceSimulatorCard.register();
