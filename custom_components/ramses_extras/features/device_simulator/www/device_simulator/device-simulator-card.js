/**
 * Device Simulator Card for Ramses Extras
 * Phase 8: UI Cards - Main simulator interface
 */

import { RamsesBaseCard } from '../../helpers/ramses-base-card.js';

const SCENARIO_MANUAL_DEVICE = "autonomous_emissions";
const SCENARIO_PROFILE_EMISSIONS = "profile_emissions";
const SCENARIO_LOAD_PROFILE = "load_profile_yaml";
const LOADER_DRAFT_KEY = "ramsesExtras.deviceSimulator.loaderDraft";

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
  .device-controls { margin-bottom: 16px; }
  .device-list-empty { color: var(--secondary-text-color); padding: 8px 0; }
  .profile-missing { margin-top: 12px; padding: 8px 12px; border-radius: 8px; background: var(--secondary-background-color); display: flex; flex-direction: column; gap: 8px; }
  .profile-missing strong { font-size: 0.85em; color: var(--secondary-text-color); }
  .profile-missing-entry { display: flex; gap: 8px; align-items: center; justify-content: space-between; flex-wrap: wrap; font-size: 0.8em; }
  .speed-card { display:flex; flex-direction:column; gap:10px; }
  .speed-card .speed-controls { display:flex; flex-wrap:wrap; gap:8px; align-items:center; }
  .speed-card input[type='range'] { width:200px; }
  .speed-card input[type='number'] { width:90px; padding:4px; border:1px solid var(--divider-color); border-radius:4px; background:var(--card-background-color); color:var(--primary-text-color); }
  .speed-card button { font-size:0.8em; }
  .chip { display: inline-flex; align-items: center; padding: 2px 8px; border-radius: 999px; font-size: 0.7em; font-weight: 600; text-transform: uppercase; }
  .chip.profile { background: var(--primary-color); color: white; }
  .chip.manual { background: var(--info-color, #0288d1); color: white; }
  .chip.known { background: var(--success-color, #388e3c); color: white; }
  .chip.sensor { background: var(--warning-color, #ffa000); color: #000; }
  .chip.muted { background: var(--divider-color); color: var(--secondary-text-color); }
  .chip.source { background: var(--secondary-background-color); color: var(--secondary-text-color); }
  .btn[disabled] { opacity: 0.6; cursor: not-allowed; }
  .scenario-form { margin-top: 8px; display: flex; flex-direction: column; gap: 8px; }
  .scenario-field { display: flex; flex-direction: column; gap: 4px; font-size: 0.8em; }
  .scenario-field label { color: var(--secondary-text-color); font-weight: 600; display: flex; align-items: center; justify-content: space-between; gap: 8px; }
  .scenario-field input[type="text"],
  .scenario-field input[type="search"],
  .scenario-field input[type="number"] { padding: 4px 8px; border: 1px solid var(--divider-color); border-radius: 4px; background: var(--card-background-color); color: var(--primary-text-color); font-size: 0.9em; }
  .scenario-field select { padding: 4px 8px; border: 1px solid var(--divider-color); border-radius: 4px; background: var(--card-background-color); color: var(--primary-text-color); font-size: 0.9em; }
  .scenario-field textarea { padding: 8px; border: 1px solid var(--divider-color); border-radius: 6px; min-height: 140px; font-family: var(--code-font-family, 'Fira Code', monospace); font-size: 0.85em; background: var(--card-background-color); color: var(--primary-text-color); resize: vertical; line-height: 1.35; }
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
    this._deviceSubscription = null;
    this._activeProfile = null;
    this._activeProfileYaml = null;
    this._activeProfileTimeoutScale = null;
    this._loaderActiveProfileSnapshot = null;
    this._activeProfileKnownList = null;
    this._activeProfileSchema = null;
    this._activeProfileZones = [];
    this._runningMetadata = {};
    this._profileDeviceSummary = [];
    this._profileDeviceCounts = null;
    this._autonomousSpeed = 1.0;
    this._pendingSpeed = 1.0;
    this._speedSaving = false;

    this._loadLoaderDraft();
  }

  _buildProfileDevicesStatus() {
    const engineActive = this._emissionsActive && !!this._activeProfile;
    if (!engineActive) {
      return "";
    }

    const runningMeta = (this._runningMetadata || {})["profile_emissions"] || {};
    const deviceCount = runningMeta.devices?.length
      || (this._devices || []).filter((d) => d.owned_by_profile).length;
    const label = deviceCount ? `${deviceCount} devices emitting` : "Profile devices active";
    return `
      <div style="margin-top:8px; padding:8px 12px; border-radius:8px; background:var(--primary-color, #3f51b5); color:var(--text-primary-color,#fff); display:flex; align-items:center; gap:8px; flex-wrap:wrap;">
        <span>🔥 ${label}</span>
        <button class="btn btn-secondary" data-action="stop-profile-devices">Stop all profile devices</button>
      </div>`;
  }

  _getScenarioFieldMeta(scenarioId, key) {
    const schema = this._scenarioSchemas[scenarioId] || [];
    return schema.find((field) => field.key === key) || null;
  }

  _getDynamicOptions(source) {
    if (!source) {
      return [];
    }

    if (source === "zones") {
      return (this._activeProfileZones || []).map((zone) => ({
        value: zone.id,
        label: `${zone.label || zone.zone_id}${zone.sensor ? ` · sensor ${zone.sensor}` : ""}`,
      }));
    }

    return [];
  }

  _renderDeviceZones(device) {
    const zones = device?.zones || [];
    if (!zones.length) {
      return "";
    }

    const items = zones.map((zone) => {
      const label = zone.label || `Zone ${zone.zone_id || "?"}`;
      const controller = zone.controller ? `CTL ${zone.controller}` : null;
      const roleLabel = (zone.roles || [])
        .map((role) => (role === "devices" ? "device" : role))
        .join(", ");
      const badge = roleLabel ? `<span class="chip muted">${roleLabel}</span>` : "";
      const sensor = zone.sensor ? `<span class="chip sensor">sensor ${zone.sensor}</span>` : "";

      let members = "";
      if ((zone.roles || []).includes("controller") && Array.isArray(zone.members)) {
        const formattedMembers = zone.members
          .map((member) => {
            const memberRoles = member.roles?.includes("sensor")
              ? "(sensor)"
              : member.roles?.includes("actuator")
                ? "(actuator)"
                : "";
            return `${member.id}${memberRoles ? ` ${memberRoles}` : ""}`;
          })
          .join(", ");
        if (formattedMembers) {
          members = `<div class="device-zone-members">Members: ${formattedMembers}</div>`;
        }
      }

      return `
        <div class="device-zone-row">
          <div>
            <strong>${label}</strong>${controller ? ` · ${controller}` : ""}
          </div>
          <div style="display:flex; gap:4px; flex-wrap:wrap; font-size:0.75em;">${badge}${sensor}</div>
          ${members}
        </div>`;
    }).join("");

    return `
      <div class="device-zones" style="margin-top:12px;">
        <div style="font-size:0.8em; color:var(--secondary-text-color); margin-bottom:4px;">Zone relationships</div>
        <div class="device-zone-list" style="display:flex; flex-direction:column; gap:6px;">${items}</div>
      </div>`;
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
    this._subscribeToDevices();
  }

  _onDisconnected() {
    if (this._deviceSubscription) {
      try {
        this._deviceSubscription();
      } catch (err) {
        // eslint-disable-next-line no-console
        console.warn("Device Simulator: failed to unsubscribe", err);
      }
      this._deviceSubscription = null;
    }
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
      this._runningMetadata = result.running_metadata || {};
      this._autoAnswer = result.auto_answer !== false;
      this._emissionsActive = result.autonomous_emissions_active === true;
      this._stats = result.stats || this._stats;
      const previousActive = this._activeProfile;
      this._activeProfile = result.active_profile || null;
      this._activeProfileYaml = result.active_profile_yaml || null;
      this._activeProfileTimeoutScale = result.active_profile_timeout_scale ?? null;
      this._activeProfileKnownList = result.active_profile_known_list || null;
      this._activeProfileSchema = result.active_profile_schema || null;
      this._activeProfileZones = result.active_profile_zones || [];
      this._profileDeviceSummary = result.profile_device_summary || [];
      this._profileDeviceCounts = result.profile_device_counts || null;
      if (typeof result.autonomous_speed === "number") {
        this._autonomousSpeed = result.autonomous_speed;
        if (!this._speedSaving) {
          this._pendingSpeed = result.autonomous_speed;
        }
      }
      this._scheduleRender();
      if (
        this._activeProfile &&
        this._activeProfileYaml &&
        this._activeProfile !== this._loaderActiveProfileSnapshot
      ) {
        const current = this._scenarioParams[SCENARIO_LOAD_PROFILE] || {};
        this._scenarioParams = {
          ...this._scenarioParams,
          [SCENARIO_LOAD_PROFILE]: {
            ...current,
            profile_name: this._activeProfile,
            profile_yaml: this._activeProfileYaml,
            speed:
              current.speed ?? this._activeProfileTimeoutScale ?? current.speed ?? 1.0,
          },
        };
        this._loaderActiveProfileSnapshot = this._activeProfile;
        this._persistLoaderDraft();
      } else if (!this._activeProfile && previousActive) {
        this._loaderActiveProfileSnapshot = null;
      }
    } catch {
      // Silently handle fetch errors
    }
  }

  async _subscribeToDevices() {
    if (!this._hass || this._deviceSubscription) return;
    if (!this._hass.connection) return;

    try {
      // Subscribe to real-time device updates
      this._deviceSubscription = await this._hass.connection.subscribeMessage(
        (event) => {
          if (event?.event_type === "devices_changed") {
            const data = event.data || {};
            const action = data.action || "updated";
            const deviceId = data.device_id;
            const count = data.count;

            // eslint-disable-next-line no-console
            console.log(`Device Simulator: ${action} ${deviceId || 'all devices'} (total: ${count})`);

            this._fetchData();
          }
        },
        { type: "ramses_extras/device_simulator/subscribe_devices" },
      );

      // eslint-disable-next-line no-console
      console.log("Device Simulator: subscribed to device updates");
    } catch (err) {
      // eslint-disable-next-line no-console
      console.error("Device Simulator: failed to subscribe to device updates", err);
    }
  }

  // ========== INTERACTIONS ==========

  _setTab(tab) {
    this._tab = tab;
    this._scheduleRender();
    void this._fetchData();
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

  async _stopProfileDevices() {
    await this._stopScenario("profile_emissions");
    await this._fetchData();
  }

  async _activateProfileDevice(deviceId) {
    if (!deviceId || !this._hass) {
      return;
    }
    try {
      await this._hass.callWS({
        type: "ramses_extras/device_simulator/activate_profile_device",
        device_id: deviceId,
      });
    } catch (error) {
      // eslint-disable-next-line no-console
      console.error("DeviceSimulatorCard: failed to activate profile device", error);
    }
    await new Promise((resolve) => setTimeout(resolve, 300));
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

  async _confirmDeleteProfile(profileName) {
    if (!profileName || !this._hass) {
      return;
    }

    const profile = this._profiles.find((p) => p.name === profileName);
    if (profile?.is_builtin) {
      this._profileNotice = "Built-in profiles cannot be deleted.";
      this._scheduleRender();
      return;
    }

    const confirmed = window.confirm(`Delete profile "${profileName}"? This cannot be undone.`);
    if (!confirmed) {
      return;
    }

    try {
      await this._hass.callWS({
        type: "ramses_extras/device_simulator/delete_profile",
        profile: profileName,
      });

      if (this._activeProfile === profileName) {
        this._activeProfile = null;
        this._activeProfileYaml = null;
        this._activeProfileTimeoutScale = null;
        this._loaderActiveProfileSnapshot = null;
        this._scenarioParams = {
          ...this._scenarioParams,
          [SCENARIO_LOAD_PROFILE]: {},
        };
        this._persistLoaderDraft();
      }

      await new Promise((resolve) => setTimeout(resolve, 300));
      await this._fetchData();
    } catch (error) {
      // eslint-disable-next-line no-console
      console.error("DeviceSimulatorCard: failed to delete profile", error);
    }
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

  async _setAutonomousSpeed(value) {
    if (!this._hass) {
      return;
    }

    const numeric = Number(value);
    if (!Number.isFinite(numeric)) {
      return;
    }

    const clamped = Math.min(100, Math.max(0.01, numeric));
    this._pendingSpeed = clamped;
    this._speedSaving = true;
    this._scheduleRender();

    try {
      await this._hass.callWS({
        type: "ramses_extras/device_simulator/set_autonomous_speed",
        speed: clamped,
      });
      this._autonomousSpeed = clamped;
    } catch (error) {
      // eslint-disable-next-line no-console
      console.error("DeviceSimulatorCard: failed to set autonomous speed", error);
    } finally {
      this._speedSaving = false;
      this._scheduleRender();
      await new Promise((resolve) => setTimeout(resolve, 300));
      await this._fetchData();
    }
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

    root.querySelectorAll("[data-action='stop-profile-devices']").forEach((btn) => {
      btn.addEventListener("click", () => this._stopProfileDevices());
    });

    root.querySelectorAll("[data-action='activate-profile-device']").forEach((btn) => {
      btn.addEventListener("click", () => this._activateProfileDevice(btn.dataset.deviceId));
    });

    const speedSlider = root.querySelector("[data-action='speed-slider']");
    if (speedSlider) {
      speedSlider.addEventListener("input", (e) => {
        this._pendingSpeed = Number(e.target.value);
        this._scheduleRender();
      });
      speedSlider.addEventListener("change", (e) => this._setAutonomousSpeed(e.target.value));
    }

    const speedInput = root.querySelector("[data-action='speed-input']");
    if (speedInput) {
      speedInput.addEventListener("input", (e) => {
        this._pendingSpeed = Number(e.target.value);
        this._scheduleRender();
      });
      speedInput.addEventListener("change", (e) => this._setAutonomousSpeed(e.target.value));
    }

    const speedPresets = root.querySelectorAll("[data-action='speed-preset']");
    speedPresets.forEach((btn) => {
      btn.addEventListener("click", () => this._setAutonomousSpeed(btn.dataset.speed));
    });

    root.querySelectorAll("[data-action='delete-profile']").forEach(btn => {
      btn.addEventListener("click", () => this._confirmDeleteProfile(btn.dataset.profile));
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

    const manualTemplate = root.querySelector("[data-action='manual-template']");
    if (manualTemplate) {
      manualTemplate.addEventListener("change", (event) => {
        const select = event.target;
        const option = select.selectedOptions?.[0];
        if (option && option.value) {
          this._applyManualTemplate(option);
          select.value = "";
        }
      });
    }

    const resetLoader = root.querySelector("[data-action='reset-loader']");
    if (resetLoader) {
      resetLoader.addEventListener("click", () => {
        this._scenarioParams = { ...this._scenarioParams, [SCENARIO_LOAD_PROFILE]: {} };
        this._scheduleRender();
        this._persistLoaderDraft();
      });
    }

    this._updateLoaderStatusUI();
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

  _knownList(includeHgi = false) {
    const profile = this._profiles.find((p) => p.name === this._activeProfile);
    const knownList = profile?.known_list || {};
    if (includeHgi) {
      return knownList;
    }
    return Object.fromEntries(
      Object.entries(knownList).filter(([, meta]) => (meta?.class || "").toUpperCase() !== "HGI"),
    );
  }

  _manualDeviceCount() {
    return this._devices.filter((d) => !d.owned_by_profile).length;
  }

  _profileDeviceCount() {
    return this._devices.filter((d) => d.owned_by_profile).length;
  }

  _activeScenarioIds() {
    const ids = new Set(this._runningScenarios || []);
    if (this._manualDeviceCount() > 0) {
      ids.add(SCENARIO_MANUAL_DEVICE);
    }
    return ids;
  }

  _scenarioConflicts(scenarioId) {
    const registry = this._scenarioRegistry || {};
    const meta = registry[scenarioId] || {};
    const newCompat = meta.can_run_with || [];
    if (newCompat.includes("*")) {
      return [];
    }
    const conflicts = [];
    const activeIds = this._activeScenarioIds();
    activeIds.forEach((runningId) => {
      if (runningId === scenarioId) {
        return;
      }
      const runningMeta = registry[runningId] || {};
      const runningCompat = runningMeta.can_run_with || [];
      if (
        runningCompat.includes("*") ||
        runningCompat.includes(scenarioId) ||
        newCompat.includes(runningId)
      ) {
        return;
      }
      conflicts.push(runningId);
    });
    return conflicts;
  }

  _applyManualTemplate(option) {
    if (!option || !option.value) return;
    const deviceId = option.value;
    const slug = (option.dataset.slug || "FAN").toUpperCase();
    const variant = option.dataset.variant || "default";
    const current = this._scenarioParams[SCENARIO_MANUAL_DEVICE] || {};
    this._scenarioParams = {
      ...this._scenarioParams,
      [SCENARIO_MANUAL_DEVICE]: {
        ...current,
        device_id: deviceId,
        device_type: slug,
        variant_id: variant,
      },
    };
    this._scheduleRender();
  }

  // ========== HTML BUILDERS ==========

  _buildProfiles() {
    const loaderCard = this._buildProfileLoaderCard();
    const profileCards = this._profiles.length === 0
      ? "<div>No profiles available</div>"
      : this._profiles.map((p) => {
          const speedOptions = (p.speed_options || [1.0, 0.1, 0.01]).map((s) => {
            const label = s === 1.0 ? "1× (normal)" : s === 0.1 ? "10× faster" : s === 0.01 ? "100× faster" : `${s}×`;
            const sel = (this._profileSpeed[p.name] ?? 1.0) === s ? " selected" : "";
            return `<option value="${s}"${sel}>${label}</option>`;
          }).join("");
          const reloadChecked = (this._profileReload[p.name] ?? true) ? " checked" : "";
          const deleteButton = p.can_delete
            ? `<button class="btn btn-secondary" data-action="delete-profile" data-profile="${p.name}" style="margin-left:auto;">Delete</button>`
            : "";
          const badges = `
            <div style="display:flex; gap:4px; align-items:center; font-size:0.75em; color:var(--secondary-text-color);">
              ${p.is_active ? "<span class=\"chip profile\">Active</span>" : ""}
              ${p.is_builtin ? "<span class=\"chip source\">Built-in</span>" : ""}
            </div>`;
          return `
            <div class="card ${this._activeProfile === p.name ? "active" : ""}">
              <div style="display:flex; align-items:center; gap:8px; flex-wrap:wrap;">
                <strong>${p.name}</strong>
                ${badges}
                ${deleteButton}
              </div>
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

    return `${loaderCard}<div class="grid">${profileCards}</div>${notice}`;
  }

  _buildProfileLoaderCard() {
    const conflicts = this._scenarioConflicts(SCENARIO_LOAD_PROFILE).filter((id) => ![SCENARIO_LOAD_PROFILE, SCENARIO_PROFILE_EMISSIONS].includes(id));
    const conflictWarn = conflicts.length
      ? `<div style="font-size: 0.75em; color: var(--warning-color, #ff9800); margin-top: 4px;">⚠️ Conflicts with: ${conflicts.join(", ")}</div>`
      : "";
    const params = this._scenarioParams[SCENARIO_LOAD_PROFILE] || {};
    const nameField = this._getScenarioFieldMeta(SCENARIO_LOAD_PROFILE, "profile_name");
    const yamlField = this._getScenarioFieldMeta(SCENARIO_LOAD_PROFILE, "profile_yaml");
    const speedField = this._getScenarioFieldMeta(SCENARIO_LOAD_PROFILE, "speed");
    const reloadField = this._getScenarioFieldMeta(SCENARIO_LOAD_PROFILE, "reload_ramses");

    const profileName = (params.profile_name ?? this._activeProfile ?? nameField?.default ?? "").trim();
    const yamlValue = params.profile_yaml ?? this._activeProfileYaml ?? "";
    const hasYaml = Boolean((yamlValue || "").trim());
    const speedValue = params.speed ?? this._activeProfileTimeoutScale ?? speedField?.default ?? 1.0;
    const reloadValue = params.reload_ramses ?? reloadField?.default ?? true;

    const speedOptions = (speedField?.options || []).map((opt) => {
      const optValue = opt.value ?? opt;
      const optLabel = opt.label ?? optValue;
      const selected = Number(speedValue) === Number(optValue) ? " selected" : "";
      return `<option value="${optValue}"${selected}>${optLabel}</option>`;
    }).join("");

    const profileNameInput = `
      <div class="scenario-field">
        <label for="loader-profile-name">${nameField?.label || "Profile name"}</label>
        <input id="loader-profile-name" type="text" data-action="scenario-param" data-scenario-id="${SCENARIO_LOAD_PROFILE}" data-field="profile_name" value="${profileName}" placeholder="${nameField?.placeholder || "imported_profile"}" />
      </div>`;

    const yamlInput = `
      <div class="scenario-field">
        <label for="loader-profile-yaml">${yamlField?.label || "Profile YAML"} <span style="color:var(--error-color);">*</span></label>
        <textarea id="loader-profile-yaml" data-action="scenario-param" data-scenario-id="${SCENARIO_LOAD_PROFILE}" data-field="profile_yaml" placeholder="${yamlField?.placeholder || "known_list:\n  32:150000:\n    class: FAN"}">${yamlValue}</textarea>
      </div>`;

    const speedSelector = speedOptions
      ? `<label style="font-size: 0.8em; display:flex; flex-direction:column; gap:4px;">
          <span>${speedField?.label || "Profile speed"}</span>
          <select data-action="scenario-param" data-scenario-id="${SCENARIO_LOAD_PROFILE}" data-field="speed" data-type="number" style="font-size:0.85em; padding:4px; border:1px solid var(--divider-color); border-radius:4px; background:var(--card-background-color); color:var(--primary-text-color);">
            ${speedOptions}
          </select>
        </label>`
      : "";

    const reloadToggle = `
      <label style="font-size: 0.8em; display:flex; align-items:center; gap:4px; cursor:pointer;">
        <input type="checkbox" data-action="scenario-param" data-scenario-id="${SCENARIO_LOAD_PROFILE}" data-field="reload_ramses" data-type="checkbox" ${reloadValue ? "checked" : ""} />
        ${reloadField?.label || "Reload RF"}
      </label>`;

    return `
      <div class="card" style="margin-bottom: 16px;" data-card="profile-loader">
        <div style="display:flex; justify-content: space-between; align-items:center; gap:8px; flex-wrap:wrap;">
          <strong>Load Ramses RF profile (YAML)</strong>
          <span class="chip ${hasYaml ? "profile" : "muted"}" data-loader-chip>${hasYaml ? "Ready" : "Awaiting YAML"}</span>
        </div>
        <div style="font-size:0.85em; color: var(--secondary-text-color); margin-top:4px;">
          Paste a known_devices YAML snippet to import a simulator profile and activate its devices.
        </div>
        ${this._activeProfile ? `<div style="font-size:0.8em; color: var(--secondary-text-color); margin-top:6px;">Active profile: <strong>${this._activeProfile}</strong>${this._activeProfileZones?.length ? ` · ${this._activeProfileZones.length} zones detected` : ""}</div>` : ""}
        ${conflictWarn}
        ${this._buildProfileDevicesStatus()}
        ${profileNameInput}
        ${yamlInput}
        <div style="display:flex; gap:12px; align-items:center; flex-wrap:wrap;">
          ${speedSelector}
          ${reloadToggle}
        </div>
        <div style="margin-top: 8px; display:flex; gap:8px; flex-wrap:wrap;">
          <button class="btn btn-primary" data-action="start-scenario" data-scenario-id="${SCENARIO_LOAD_PROFILE}" ${!hasYaml || conflicts.length ? "disabled" : ""}>Load</button>
          <button class="btn btn-secondary" data-action="reset-loader" ${hasYaml ? "" : "disabled"}>Clear form</button>
        </div>
      </div>`;
  }

  _buildDevices() {
    const controls = `
      <div class="grid device-controls">
        ${this._buildManualInjectionCard()}
        ${this._buildProfileEmissionsCard()}
        ${this._buildAutonomousSpeedCard()}
      </div>`;

    if (this._devices.length === 0) {
      return `${controls}<div class="device-list-empty">No active devices. Use Manual Device Injection or Start all profile devices above to start emitters.</div>`;
    }

    const knownList = this._knownList();
    const deviceCards = this._devices.map((d) => {
      const ownershipChip = d.owned_by_profile
        ? `<span class="chip profile" title="Defined by the active profile">Profile</span>`
        : `<span class="chip manual" title="Manually injected device">Manual</span>`;
      const knownBadge = knownList[d.id]
        ? `<span class="chip known" title="Device appears in profile known list">Known</span>`
        : "";
      const extraSource = d.source && !["manual", "profile"].includes(d.source)
        ? `<span class="chip source" title="Origin scenario">${d.source}</span>`
        : "";
      const chipsMarkup = (d.excluded_codes || []).map((code) =>
        `<span class="code-chip">${code}<button data-action="remove-code" data-device-id="${d.id}" data-code="${code}" title="Remove">✕</button></span>`
      ).join("");
      const checkedAttr = d.enabled ? " checked" : "";
      const zoneMarkup = this._renderDeviceZones(d);
      return `
        <div class="card">
          <div style="display: flex; justify-content: space-between; align-items: center; gap: 8px; flex-wrap: wrap;">
            <div><strong>${d.id}</strong> <span style="color: var(--secondary-text-color); font-size: 0.85em;">${d.type}</span></div>
            <div style="display:flex; gap:4px; flex-wrap: wrap;">${ownershipChip}${knownBadge}${extraSource}</div>
          </div>
          <div class="device-actions">
            <label class="toggle">
              <ha-switch data-action="toggle-device" data-device-id="${d.id}"${checkedAttr}></ha-switch>
              <span>${d.enabled ? "Enabled" : "Disabled"}</span>
            </label>
          </div>
          <div style="font-size: 0.8em; color: var(--secondary-text-color); margin-top: 8px;">Excluded codes:</div>
          <div class="codes-row">${chipsMarkup || `<span class="chip muted">none</span>`}</div>
          <div class="add-code">
            <input type="text" maxlength="4" placeholder="1FC9"
              data-action="code-input" data-device-id="${d.id}"
              value="${this._newCodeInput[d.id] || ""}" />
            <button class="btn btn-primary" data-action="add-code" data-device-id="${d.id}">+ Exclude</button>
          </div>
          ${zoneMarkup}
        </div>`;
    }).join("");

    return `${controls}<div class="grid">${deviceCards}</div>`;
  }

  _buildManualInjectionCard() {
    const manualCount = this._manualDeviceCount();
    const conflicts = this._scenarioConflicts(SCENARIO_MANUAL_DEVICE);
    const conflictWarn = conflicts.length
      ? `<div style="font-size: 0.75em; color: var(--warning-color, #ff9800); margin-top: 4px;">⚠️ Conflicts with: ${conflicts.join(", ")}</div>`
      : "";
    const statusChip = manualCount
      ? `<span class="chip manual">${manualCount} active</span>`
      : `<span class="chip muted">Idle</span>`;
    const knownList = this._knownList();
    const templateOptions = Object.entries(knownList).map(([deviceId, meta]) => {
      const slug = (meta?.class || "FAN").toUpperCase();
      const variant = meta?.variant || meta?.variant_id || "default";
      return `<option value="${deviceId}" data-slug="${slug}" data-variant="${variant}">${deviceId} • ${slug}</option>`;
    }).join("");
    const templateSelect = templateOptions
      ? `<label style="font-size: 0.8em; display:flex; flex-direction:column; gap:4px;">
            <span>Preset from profile</span>
            <select data-action="manual-template" style="font-size:0.85em; padding:4px; border:1px solid var(--divider-color); border-radius:4px; background:var(--card-background-color); color:var(--primary-text-color);">
              <option value="">Select device...</option>
              ${templateOptions}
            </select>
         </label>`
      : "";

    return `
      <div class="card">
        <div style="display:flex; justify-content: space-between; align-items:center; flex-wrap: wrap; gap:8px;">
          <strong>Manual Device Injection</strong>
          ${statusChip}
        </div>
        <div style="font-size:0.85em; color:var(--secondary-text-color); margin-top:4px;">Inject an ad-hoc device that emits its periodic frames. Use profile presets to auto-fill slug/device id.</div>
        ${templateSelect}
        ${this._buildScenarioParamsById(SCENARIO_MANUAL_DEVICE)}
        ${conflictWarn}
        <div style="margin-top:8px; display:flex; gap:8px; flex-wrap:wrap;">
          <button class="btn btn-primary" data-action="start-scenario" data-scenario-id="${SCENARIO_MANUAL_DEVICE}" ${conflicts.length ? "disabled" : ""}>Inject Device</button>
          <button class="btn btn-secondary" data-action="stop-scenario" data-scenario-id="${SCENARIO_MANUAL_DEVICE}" ${manualCount ? "" : "disabled"}>Stop manual devices</button>
        </div>
      </div>`;
  }

  _buildProfileEmissionsCard() {
    const running = (this._runningScenarios || []).includes(SCENARIO_PROFILE_EMISSIONS);
    const conflicts = this._scenarioConflicts(SCENARIO_PROFILE_EMISSIONS);
    const conflictWarn = conflicts.length
      ? `<div style="font-size: 0.75em; color: var(--warning-color, #ff9800); margin-top: 4px;">⚠️ Conflicts with: ${conflicts.join(", ")}</div>`
      : "";
    const knownList = this._knownList();
    const summary = this._profileDeviceSummary || [];
    const counts = this._profileDeviceCounts || null;
    const knownCount = counts?.known ?? (summary.length || Object.keys(knownList).length);
    const profileCount = counts?.active ?? this._profileDeviceCount();
    const statusChip = running
      ? `<span class="chip profile">${profileCount || knownCount} active</span>`
      : `<span class="chip muted">Idle</span>`;
    const disableStart = !this._activeProfile || !knownCount || conflicts.length;
    const startDisabled = disableStart || running;
    const stopDisabled = profileCount === 0;
    const summaryText = !this._activeProfile
      ? "Load a profile to enable bulk emissions."
      : knownCount === 0
        ? "Active profile has no known devices configured."
        : running
          ? `Emitting ${profileCount || knownCount} profile device(s).`
          : `Ready to emit ${knownCount} device(s) from the active profile.`;

    const startButton = `<button class="btn btn-primary" data-action="start-scenario" data-scenario-id="${SCENARIO_PROFILE_EMISSIONS}" ${startDisabled ? "disabled" : ""}>Start all profile devices</button>`;
    const stopButton = `<button class="btn btn-secondary" data-action="stop-profile-devices" ${stopDisabled ? "disabled" : ""}>Stop all profile devices</button>`;
    const buttonRow = `${startButton}${stopButton}`;

    const missingDevices = summary.filter((entry) => !entry.active);
    const missingMarkup = missingDevices.length
      ? `
        <div class="profile-missing">
          <strong>${missingDevices.length === 1 ? "1 device" : `${missingDevices.length} devices`} not emitting</strong>
          ${missingDevices
            .map(
              (entry) => `
                <div class="profile-missing-entry">
                  <span>${entry.id}${entry.class ? ` • ${entry.class}` : ""}</span>
                  <button class="btn btn-secondary" data-action="activate-profile-device" data-device-id="${entry.id}">
                    Activate
                  </button>
                </div>`,
            )
            .join("")}
        </div>`
      : "";

    return `
      <div class="card">
        <div style="display:flex; justify-content: space-between; align-items:center; flex-wrap:wrap; gap:8px;">
          <strong>Start all profile devices</strong>
          ${statusChip}
        </div>
        <div style="font-size:0.85em; color:var(--secondary-text-color); margin-top:4px;">${summaryText}</div>
        ${conflictWarn}
        <div style="margin-top:8px; display:flex; gap:8px; flex-wrap:wrap;">${buttonRow}</div>
        ${missingMarkup}
      </div>`;
  }

  _formatAutonomousSpeedLabel(speed) {
    const value = Number(speed) || 1;
    if (Math.abs(value - 1) < 0.01) {
      return "1× normal";
    }
    if (value > 1) {
      const magnitude = value >= 10 ? value.toFixed(0) : value.toFixed(1);
      return `${magnitude}× faster`;
    }
    const slower = 1 / value;
    const text = slower >= 10 ? slower.toFixed(0) : slower.toFixed(1);
    return `${text}× slower`;
  }

  _buildAutonomousSpeedCard() {
    const current = Number(this._autonomousSpeed) || 1;
    const pending = Number.isFinite(this._pendingSpeed) ? this._pendingSpeed : current;
    const sliderValue = Math.min(1, Math.max(0.01, pending || 1));
    const presetValues = [2, 1, 0.5, 0.25, 0.1, 0.05, 0.02];

    const badge = this._speedSaving
      ? '<span class="chip muted">Saving…</span>'
      : `<span class="chip profile">${this._formatAutonomousSpeedLabel(current)}</span>`;

    const presetButtons = presetValues
      .map((value) => {
        const active = Math.abs(current - value) < 0.001 ? "btn-primary" : "btn-secondary";
        return `<button class="btn ${active}" data-action="speed-preset" data-speed="${value}">${this._formatAutonomousSpeedLabel(value)}</button>`;
      })
      .join("");

    return `
      <div class="card speed-card">
        <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px;">
          <strong>Autonomous Emission Speed</strong>
          ${badge}
        </div>
        <div style="font-size:0.85em; color:var(--secondary-text-color);">
          Lower than 1× slows emitters down, higher than 1× speeds them up. The slider covers 0.01–1×; use the number field or presets for faster modes.
        </div>
        <div class="speed-controls">
          <label style="display:flex; flex-direction:column; gap:4px; font-size:0.75em;">
            <span>Slowdown (0.01–1×)</span>
            <input type="range" min="0.01" max="1" step="0.01" value="${sliderValue}" data-action="speed-slider" />
          </label>
          <label style="display:flex; flex-direction:column; gap:4px; font-size:0.75em;">
            <span>Exact multiplier</span>
            <input type="number" min="0.01" max="100" step="0.01" value="${pending}" data-action="speed-input" />
          </label>
        </div>
        <div style="display:flex; flex-wrap:wrap; gap:6px;">
          ${presetButtons}
        </div>
      </div>`;
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

    if (scenarioId === SCENARIO_LOAD_PROFILE) {
      this._updateLoaderStatusUI();
      this._persistLoaderDraft();
    }
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

    const optionSource = this._getDynamicOptions(field.options_source);
    if ((Array.isArray(field.options) && field.options.length) || optionSource.length) {
      const optionList = optionSource.length ? optionSource : field.options;
      const optionsMarkup = optionList.map((opt) => {
        const optValue = opt.value ?? opt;
        const optLabel = opt.label ?? optValue;
        const selected = String(value ?? field.default ?? "") === String(optValue) ? " selected" : "";
        return `<option value="${optValue}"${selected}>${optLabel}</option>`;
      }).join("");
      return `
        <div class="scenario-field">
          <label for="${inputId}">${field.label || field.key} ${requiredMark}</label>
          <select id="${inputId}" ${commonAttrs}>${optionsMarkup}</select>
        </div>`;
    }

    if (field.type === "textarea") {
      const rowsAttr = field.rows ? ` rows="${field.rows}"` : " rows=\"8\"";
      const placeholder = field.placeholder || "known_list:\n  32:150000:\n    class: FAN";
      return `
        <div class="scenario-field">
          <label for="${inputId}">${field.label || field.key} ${requiredMark}</label>
          <textarea id="${inputId}" ${commonAttrs}${rowsAttr} placeholder="${placeholder}">${value}</textarea>
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

  _updateLoaderStatusUI() {
    if (!this.shadowRoot) return;
    const card = this.shadowRoot.querySelector('[data-card="profile-loader"]');
    if (!card) return;
    const params = this._scenarioParams[SCENARIO_LOAD_PROFILE] || {};
    const hasYaml = Boolean((params.profile_yaml || "").trim());
    const conflicts = this._scenarioConflicts(SCENARIO_LOAD_PROFILE);

    const importBtn = card.querySelector(`[data-action='start-scenario'][data-scenario-id='${SCENARIO_LOAD_PROFILE}']`);
    if (importBtn) {
      importBtn.disabled = !hasYaml || conflicts.length > 0;
    }

    const resetBtn = card.querySelector("[data-action='reset-loader']");
    if (resetBtn) {
      resetBtn.disabled = !hasYaml;
    }

    const chip = card.querySelector("[data-loader-chip]");
    if (chip) {
      chip.textContent = hasYaml ? "Ready" : "Awaiting YAML";
      chip.classList.remove("profile", "muted");
      chip.classList.add(hasYaml ? "profile" : "muted");
    }
  }

  _loadLoaderDraft() {
    if (typeof window === "undefined" || !window.localStorage) {
      return;
    }
    try {
      const raw = window.localStorage.getItem(LOADER_DRAFT_KEY);
      if (!raw) {
        return;
      }
      const parsed = JSON.parse(raw);
      if (parsed && typeof parsed === "object") {
        this._scenarioParams[SCENARIO_LOAD_PROFILE] = parsed;
      }
    } catch (error) {
      // eslint-disable-next-line no-console
      console.warn("Device Simulator: failed to load loader draft", error);
    }
  }

  _persistLoaderDraft() {
    if (typeof window === "undefined" || !window.localStorage) {
      return;
    }
    const params = this._scenarioParams[SCENARIO_LOAD_PROFILE];
    if (!params || Object.keys(params).length === 0) {
      window.localStorage.removeItem(LOADER_DRAFT_KEY);
      return;
    }
    try {
      window.localStorage.setItem(LOADER_DRAFT_KEY, JSON.stringify(params));
    } catch (error) {
      // eslint-disable-next-line no-console
      console.warn("Device Simulator: failed to persist loader draft", error);
    }
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
      .filter(id => id !== "auto_answer" && id !== SCENARIO_MANUAL_DEVICE && id !== SCENARIO_LOAD_PROFILE && id !== SCENARIO_PROFILE_EMISSIONS)
      .map((id) => {
        const meta = registry[id];
        const isRunning = (this._runningScenarios || []).includes(id);
        const conflicts = this._scenarioConflicts(id);
        const conflictWarn = conflicts.length
          ? `<div style="font-size: 0.75em; color: var(--warning-color, #ff9800); margin-top: 4px;">&#9888; Conflicts with: ${conflicts.join(", ")}</div>`
          : "";
        const disabledAttr = conflicts.length ? " disabled" : "";
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
