/**
 * Device Simulator Card for Ramses Extras
 * Phase 8: UI Cards - Main simulator interface
 */

import {
  LitElement,
  html,
  css,
} from "https://unpkg.com/lit-element@2.4.0/lit-element.js?module";

class DeviceSimulatorCard extends LitElement {
  static get properties() {
    return {
      hass: { type: Object },
      config: { type: Object },
      _profiles: { type: Array },
      _activeProfile: { type: String },
      _devices: { type: Array },
      _scenarios: { type: Array },
      _scenarioState: { type: String },
      _events: { type: Array },
      _stats: { type: Object },
      _tab: { type: String },
    };
  }

  static get styles() {
    return css`
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
    `;
  }

  constructor() {
    super();
    this._profiles = [];
    this._devices = [];
    this._scenarios = [];
    this._events = [];
    this._stats = { rx: 0, tx: 0, devices: 0, active: 0 };
    this._tab = "profiles";
    this._scenarioState = "idle";
    this._activeScenario = null;
    this._newCodeInput = {};
    this._profileSpeed = {};
    this._profileReload = {};
    this._profileNotice = null;
    this._scenarioParams = {};
  }

  setConfig(config) {
    this.config = config;
  }

  getCardSize() {
    return 6;
  }

  connectedCallback() {
    super.connectedCallback();
    this._fetchData();
  }

  async _fetchData() {
    if (!this.hass) return;
    try {
      const result = await this.hass.callWS({
        type: "ramses_extras/device_simulator/get_status",
      });
      this._profiles = result.profiles || [];
      this._devices = result.devices || [];
      this._scenarios = result.scenarios || [];
      this._stats = result.stats || this._stats;
      this._activeProfile = result.active_profile;
    } catch {
      // Silently handle fetch errors
    }
  }

  _setTab(tab) {
    this._tab = tab;
  }

  async _loadProfile(name) {
    const speed = this._profileSpeed[name] ?? 1.0;
    const reloadRf = this._profileReload[name] ?? true;
    const result = await this.hass.callWS({
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
      setTimeout(() => { this._profileNotice = null; this.requestUpdate(); }, 5000);
    } else {
      this._profileNotice = null;
    }
    await new Promise((r) => setTimeout(r, 300));
    await this._fetchData();
  }

  async _startScenario(scenario) {
    const overrides = this._scenarioParams[scenario.id] || {};
    const params = { ...(scenario.params || {}), ...overrides };
    await this.hass.callService(
      "ramses_extras",
      "device_simulator_run_scenario",
      { scenario_type: scenario.scenario_type, params }
    );
    this._scenarioState = "running";
    this._activeScenario = scenario.id;
    await new Promise((r) => setTimeout(r, 500));
    await this._fetchData();
  }

  async _stopScenario(scenario) {
    await this.hass.callService(
      "ramses_extras",
      "device_simulator_stop_scenario",
      {
        scenario_id: scenario ? scenario.scenario_type : "autonomous_emissions",
        ...(scenario?.params?.device_id ? { device_id: scenario.params.device_id } : {}),
      }
    );
    this._scenarioState = "idle";
    this._activeScenario = null;
    await new Promise((r) => setTimeout(r, 300));
    await this._fetchData();
  }

  render() {
    if (!this.hass) {
      return html`<div>Loading...</div>`;
    }

    return html`
      <ha-card>
        <div class="header">
          <div style="display: flex; flex-direction: column; gap: 2px;">
            <div class="title">🔌 ${this.config?.title || "Device Simulator"}</div>
            ${this._activeProfile ? html`<div style="font-size: 0.8em; color: var(--secondary-text-color);">Profile: <strong>${this._activeProfile}</strong></div>` : ""}
          </div>
          <div class="badge ${this._scenarioState === "running" ? "running" : this._devices.length > 0 ? "active" : ""}" title="${this._scenarioState === "running" ? "Scenario running" : this._devices.length > 0 ? "Devices emitting" : "No active devices"}">
            ${this._scenarioState === "running" ? "Running" : this._devices.length > 0 ? `${this._devices.filter(d=>d.enabled).length} active` : "Idle"}
          </div>
        </div>

        <div class="tabs">
          <div class="tab ${this._tab === "profiles" ? "active" : ""}" @click="${() => this._setTab("profiles")}">Profiles</div>
          <div class="tab ${this._tab === "devices" ? "active" : ""}" @click="${() => this._setTab("devices")}">Devices</div>
          <div class="tab ${this._tab === "scenarios" ? "active" : ""}" @click="${() => this._setTab("scenarios")}">Scenarios</div>
          <div class="tab ${this._tab === "events" ? "active" : ""}" @click="${() => this._setTab("events")}">Events</div>
        </div>

        <div class="content ${this._tab === "profiles" ? "active" : ""}">
          ${this._renderProfiles()}
        </div>
        <div class="content ${this._tab === "devices" ? "active" : ""}">
          ${this._renderDevices()}
        </div>
        <div class="content ${this._tab === "scenarios" ? "active" : ""}">
          ${this._renderScenarios()}
        </div>
        <div class="content ${this._tab === "events" ? "active" : ""}">
          ${this._renderEvents()}
        </div>
      </ha-card>
    `;
  }

  async _clearCache({ clearSchema = true, clearPackets = false } = {}) {
    const result = await this.hass.callWS({
      type: "ramses_extras/device_simulator/clear_ramses_cache",
      clear_schema: clearSchema,
      clear_packets: clearPackets,
    });
    return result;
  }

  _renderProfiles() {
    return html`
      <div class="grid">
        ${this._profiles.length === 0
          ? html`<div>No profiles available</div>`
          : this._profiles.map(
              (p) => html`
                <div class="card ${this._activeProfile === p.name ? "active" : ""}">
                  <div><strong>${p.name}</strong></div>
                  <div style="font-size: 0.85em; color: var(--secondary-text-color); margin-bottom: 8px;">${p.description || "No description"}</div>
                  <div style="display: flex; gap: 8px; align-items: center; flex-wrap: wrap;">
                    <label style="font-size: 0.8em;">Speed:</label>
                    <select
                      style="font-size: 0.8em; padding: 2px 4px; border: 1px solid var(--divider-color); border-radius: 4px; background: var(--card-background-color); color: var(--primary-text-color);"
                      .value="${String(this._profileSpeed[p.name] ?? 1.0)}"
                      @change="${(e) => { this._profileSpeed = { ...this._profileSpeed, [p.name]: parseFloat(e.target.value) }; }}"
                    >
                      ${(p.speed_options || [1.0, 0.1, 0.01]).map((s) => html`
                        <option value="${s}" ?selected="${(this._profileSpeed[p.name] ?? 1.0) === s}">
                          ${s === 1.0 ? "1× (normal)" : s === 0.1 ? "10× faster" : s === 0.01 ? "100× faster" : s + "×"}
                        </option>
                      `)}
                    </select>
                    <label style="font-size: 0.8em; display: flex; align-items: center; gap: 4px; cursor: pointer;">
                      <input
                        type="checkbox"
                        .checked="${this._profileReload[p.name] ?? true}"
                        @change="${(e) => { this._profileReload = { ...this._profileReload, [p.name]: e.target.checked }; }}"
                      />
                      Reload RF
                    </label>
                    <button class="btn btn-primary" @click="${() => this._loadProfile(p.name)}">Load</button>
                  </div>
                </div>
              `
            )}
      </div>
      ${this._profileNotice ? html`
        <div style="margin-top: 12px; padding: 8px 12px; background: var(--warning-color, #ff9800); color: white; border-radius: 6px; font-size: 0.85em; display: flex; justify-content: space-between; align-items: center; gap: 8px;">
          <span>⚠️ ${this._profileNotice}</span>
          <button @click="${() => { this._profileNotice = null; }}" style="background: none; border: none; color: white; cursor: pointer; font-size: 1.1em; line-height: 1; padding: 0 2px;">✕</button>
        </div>
      ` : ""}
    `;
  }

  async _toggleDeviceEnabled(deviceId, current) {
    try {
      await this.hass.callWS({
        type: "ramses_extras/device_simulator/set_device_enabled",
        device_id: deviceId,
        enabled: !current,
      });
      this._devices = this._devices.map((d) =>
        d.id === deviceId ? { ...d, enabled: !current } : d
      );
    } catch {
      this._fetchData();
    }
  }

  async _removeExcludedCode(deviceId, code) {
    const device = this._devices.find((d) => d.id === deviceId);
    if (!device) return;
    const updated = device.excluded_codes.filter((c) => c !== code);
    try {
      await this.hass.callWS({
        type: "ramses_extras/device_simulator/set_device_excluded_codes",
        device_id: deviceId,
        excluded_codes: updated,
      });
      this._devices = this._devices.map((d) =>
        d.id === deviceId ? { ...d, excluded_codes: updated } : d
      );
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
      await this.hass.callWS({
        type: "ramses_extras/device_simulator/set_device_excluded_codes",
        device_id: deviceId,
        excluded_codes: updated,
      });
      this._devices = this._devices.map((d) =>
        d.id === deviceId ? { ...d, excluded_codes: updated } : d
      );
      this._newCodeInput = { ...this._newCodeInput, [deviceId]: "" };
    } catch {
      this._fetchData();
    }
  }

  _knownList() {
    const profile = this._profiles.find((p) => p.name === this._activeProfile);
    return profile?.known_list || {};
  }

  _renderDevices() {
    if (this._devices.length === 0) {
      return html`<div style="color: var(--secondary-text-color); padding: 8px 0;">No active devices. Start an autonomous emissions scenario first.</div>`;
    }
    const knownList = this._knownList();
    return html`
      <div class="grid">
        ${this._devices.map(
          (d) => html`
            <div class="card">
              <div style="display: flex; justify-content: space-between; align-items: center;">
                <div><strong>${d.id}</strong> <span style="color: var(--secondary-text-color); font-size: 0.85em;">${d.type}</span></div>
                ${knownList[d.id] ? html`<span style="padding: 1px 6px; border-radius: 10px; font-size: 0.7em; font-weight: 600; background: var(--primary-color); color: white;">known</span>` : ""}
              </div>
              <div class="device-actions">
                <label class="toggle">
                  <ha-switch
                    ?checked="${d.enabled}"
                    @change="${() => this._toggleDeviceEnabled(d.id, d.enabled)}"
                  ></ha-switch>
                  <span>${d.enabled ? "Enabled" : "Disabled"}</span>
                </label>
              </div>
              <div style="font-size: 0.8em; color: var(--secondary-text-color); margin-top: 8px;">Excluded codes:</div>
              <div class="codes-row">
                ${(d.excluded_codes || []).map(
                  (code) => html`
                    <span class="code-chip">
                      ${code}
                      <button @click="${() => this._removeExcludedCode(d.id, code)}" title="Remove">✕</button>
                    </span>
                  `
                )}
              </div>
              <div class="add-code">
                <input
                  type="text"
                  maxlength="4"
                  placeholder="1FC9"
                  .value="${this._newCodeInput[d.id] || ""}"
                  @input="${(e) => { this._newCodeInput = { ...this._newCodeInput, [d.id]: e.target.value }; }}"
                  @keydown="${(e) => e.key === "Enter" && this._addExcludedCode(d.id)}"
                />
                <button class="btn btn-primary" @click="${() => this._addExcludedCode(d.id)}">+ Exclude</button>
              </div>
            </div>
          `
        )}
      </div>
    `;
  }

  _renderScenarioParams(s) {
    const timedParams = {
      device_unavailability: ["silence_after", "resume_after"],
      hvac_device_loss: ["device_id", "loss_after", "restore_after"],
    };
    const fields = timedParams[s.id];
    if (!fields) return "";
    const overrides = this._scenarioParams[s.id] || {};
    return html`
      <div style="margin-top: 8px; display: grid; grid-template-columns: auto 1fr; gap: 4px 8px; align-items: center; font-size: 0.8em;">
        ${fields.map((f) => html`
          <label style="color: var(--secondary-text-color);">${f}:</label>
          <input
            type="text"
            style="padding: 2px 6px; border: 1px solid var(--divider-color); border-radius: 4px; background: var(--card-background-color); color: var(--primary-text-color); font-size: 0.95em;"
            .value="${String(overrides[f] ?? (s.params?.[f] ?? ""))}"
            @change="${(e) => {
              this._scenarioParams = {
                ...this._scenarioParams,
                [s.id]: { ...(this._scenarioParams[s.id] || {}), [f]: e.target.value },
              };
            }}"
          />
        `)}
      </div>
    `;
  }

  _renderScenarios() {
    return html`
      <div class="grid">
        ${this._scenarios.map(
          (s) => html`
            <div class="card ${this._activeScenario === s.id ? "active" : ""}">
              <div><strong>${s.name}</strong></div>
              <div style="font-size: 0.85em; color: var(--secondary-text-color);">${s.description || ""}</div>
              ${this._renderScenarioParams(s)}
              <div style="margin-top: 8px; display: flex; gap: 8px;">
                <button
                  class="btn btn-primary"
                  @click="${() => this._startScenario(s)}"
                  ?disabled="${this._scenarioState === "running" && this._activeScenario !== s.id}"
                >Start</button>
                ${this._activeScenario === s.id
                  ? html`<button class="btn btn-danger" @click="${() => this._stopScenario(s)}">Stop</button>`
                  : ""}
              </div>
            </div>
          `
        )}
      </div>
    `;
  }

  _renderEvents() {
    return html`
      <div class="stats">
        <div class="stat"><div class="stat-value">${this._stats.rx}</div><div>RX</div></div>
        <div class="stat"><div class="stat-value">${this._stats.tx}</div><div>TX</div></div>
        <div class="stat"><div class="stat-value">${this._stats.devices}</div><div>Devices</div></div>
        <div class="stat"><div class="stat-value">${this._stats.active}</div><div>Active</div></div>
      </div>
      <div class="event-log">
        ${this._events.length === 0
          ? html`<div style="padding: 16px; text-align: center; color: var(--secondary-text-color);">No events</div>`
          : this._events.map(
              (e) => html`
                <div class="event ${e.type === "unavailable" ? "unavailable" : ""}">
                  <span class="event-type ${e.type}">${e.type}</span>
                  <span>${e.message}</span>
                </div>
              `
            )}
      </div>
    `;
  }
}

customElements.define("device-simulator-card", DeviceSimulatorCard);

// Card editor
class DeviceSimulatorCardEditor extends LitElement {
  static get properties() {
    return {
      hass: { type: Object },
      config: { type: Object },
    };
  }

  setConfig(config) {
    this.config = config;
  }

  configChanged(newConfig) {
    const event = new CustomEvent("config-changed", {
      bubbles: true,
      composed: true,
      detail: { config: newConfig }
    });
    this.dispatchEvent(event);
  }

  render() {
    return html`
      <div class="card-config">
        <paper-input
          label="Card Title"
          .value="${this.config?.title || ""}"
          @value-changed="${(e) => this.configChanged({ ...this.config, title: e.detail.value })}"
        ></paper-input>
      </div>
    `;
  }
}

customElements.define("device-simulator-card-editor", DeviceSimulatorCardEditor);

window.customCards = window.customCards || [];
window.customCards.push({
  type: "device-simulator-card",
  name: "Device Simulator",
  description: "Control and monitor the Ramses device simulator",
  preview: true,
  documentationURL: "https://github.com/wimpie70/ramses_extras",
});

// Device Simulator Card v1.0.0 loaded
