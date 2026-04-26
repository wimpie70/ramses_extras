/**
 * Device Simulator Card for Ramses Extras
 * Phase 8: UI Cards - Main simulator interface
 */

import { RamsesBaseCard } from '../../helpers/ramses-base-card.js';
import {
  SCENARIO_MANUAL_DEVICE,
  SCENARIO_PROFILE_EMISSIONS,
  SCENARIO_LOAD_PROFILE,
  SCENARIO_DEVICE_PLAYBACK,
  LOADER_DRAFT_KEY,
  MESSAGE_HISTORY_LIMIT,
} from './card/constants.js';
import { CARD_STYLE } from './card/styles.js';
import { buildProfiles } from './card/tabs/profiles-tab.js';
import { buildScenarios } from './card/tabs/scenarios-tab.js';
import { buildDevices } from './card/tabs/devices-tab.js';
import { buildEvents } from './card/tabs/events-tab.js';


class DeviceSimulatorCard extends RamsesBaseCard {
  constructor() {
    super();
    this._profiles = [];
    this._devices = [];
    this._scenarioRegistry = {};
    this._scenarioSchemas = {};
    this._runningScenarios = [];
    this._autoAnswer = true;
    this._answerUnknownDevices = false;
    this._preserveState = true;
    this._rfEnforceKnownList = false;
    this._rfKnownListEnabled = false;
    this._emissionsActive = false;
    this._events = [];
    this._stats = { rx: 0, tx: 0, devices: 0, active: 0 };
    this._profileReload = {};
    this._profilePreloadSchema = {};
    this._profileResetCache = {};
    this._profileEavesdrop = {};
    this._profileSkipHydrate = {};
    this._profileClearLog = {};
    this._tab = "profiles";
    this._newCodeInput = {};
    this._profileReload = {};
    this._profilePreloadSchema = {};
    this._profileResetCache = {};
    this._profileEavesdrop = {};
    this._profileSkipHydrate = {};
    this._profileClearLog = {};
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
    this._deviceMsgPreviews = {};
    this._profileZoneMembership = {};
    this._msgSubscription = null;
    this._savedPlaybacks = [];
    this._playbackSelection = null;
    this._playbackImportDraft = { log_content: "", name: "" };
    this._playbackSaving = false;
    this._playbackInterMsgDelay = "";
    this._playbackSkipAnswers = false;
    this._scenarioSubscription = null;
    this._playbackSearchQuery = "";

    this._loadLoaderDraft();
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

  _onConnected() {
    this._fetchData();
    this._subscribeToDevices();
    this._subscribeToScenarios();
    if (this._tab === "devices") {
      void this._subscribeToMessageEvents();
    }
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

    if (this._msgSubscription) {
      try {
        this._msgSubscription();
      } catch (err) {
        // eslint-disable-next-line no-console
        console.warn("Device Simulator: failed to unsubscribe from message events", err);
      }
      this._msgSubscription = null;
    }

    if (this._scenarioSubscription) {
      try {
        this._scenarioSubscription();
      } catch (err) {
        // eslint-disable-next-line no-console
        console.warn("Device Simulator: failed to unsubscribe from scenario events", err);
      }
      this._scenarioSubscription = null;
    }
  }

  // ========== DATA FETCHING ==========

  async _fetchData() {
    if (!this._hass) return;
    try {
      const result = await this._hass.callWS({
        type: "ramses_extras/device_simulator/get_status",
      });
      await this._fetchRfConfig();
      const profileSummary = Array.isArray(result.profile_device_summary)
        ? result.profile_device_summary
        : [];
      const zoneMembership = result.profile_zone_membership || {};
      const devices = Array.isArray(result.devices) ? result.devices : [];
      const mergedDevices = [...devices];
      const existingIds = new Set(mergedDevices.map((d) => d.id));
      if (profileSummary.length) {
        for (const entry of profileSummary) {
          if (!entry?.id || existingIds.has(entry.id)) {
            continue;
          }
          const stub = this._buildProfileDeviceStub(entry);
          if (stub) {
            mergedDevices.push(stub);
            existingIds.add(entry.id);
          }
        }
      }

      this._profiles = result.profiles || [];
      this._profileZoneMembership = zoneMembership;
      this._devices = mergedDevices;
      this._scenarioRegistry = result.scenario_registry || {};
      this._scenarioSchemas = result.scenario_param_schemas || {};
      // eslint-disable-next-line no-console
      console.debug(
        "DeviceSimulatorCard: scenario schemas",
        Object.keys(this._scenarioSchemas),
        this._scenarioSchemas
      );
      this._runningScenarios = result.running_scenarios || [];
      this._runningMetadata = result.running_metadata || {};
      this._autoAnswer = result.auto_answer !== false;
      this._answerUnknownDevices = result.answer_unknown_devices === true;
      this._preserveState = result.preserve_state === true;
      this._emissionsActive = result.autonomous_emissions_active === true;
      this._stats = result.stats || this._stats;
      const previousActive = this._activeProfile;
      this._activeProfile = result.active_profile || null;
      this._activeProfileYaml = result.active_profile_yaml || null;
      this._activeProfileTimeoutScale = result.active_profile_timeout_scale ?? null;
      this._activeProfileKnownList = result.active_profile_known_list || null;
      this._activeProfileSchema = result.active_profile_schema || null;
      this._activeProfileZones = result.active_profile_zones || [];
      this._profileDeviceSummary = profileSummary;
      this._profileDeviceCounts = result.profile_device_counts || null;
      this._deviceMsgPreviews = result.device_message_previews || {};
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

    // Fetch saved playbacks separately (non-fatal on failure)
    try {
      const pb = await this._hass.callWS({
        type: "ramses_extras/device_simulator/list_saved_playbacks",
      });
      this._savedPlaybacks = pb?.playbacks || [];
      this._scheduleRender();
    } catch {
      // leave previous list intact
    }
  }

  async _deleteSavedPlayback(identifier) {
    if (!this._hass || !identifier) return;
    try {
      await this._hass.callWS({
        type: "ramses_extras/device_simulator/delete_saved_playback",
        identifier,
      });
      this._savedPlaybacks = this._savedPlaybacks.filter(
        (p) => p.id !== identifier && p.file !== identifier,
      );
      this._scheduleRender();
    } catch (err) {
      // eslint-disable-next-line no-console
      console.error("DeviceSimulatorCard: delete_saved_playback failed", err);
    }
  }

  async _pauseScenario(scenarioId) {
    if (!this._hass) return;
    try {
      await this._hass.callWS({
        type: "ramses_extras/device_simulator/pause_scenario",
        scenario: scenarioId,
      });
      await this._fetchData();
    } catch (err) {
      // eslint-disable-next-line no-console
      console.error("DeviceSimulatorCard: pause_scenario failed", err);
    }
  }

  async _resumeScenario(scenarioId) {
    if (!this._hass) return;
    try {
      await this._hass.callWS({
        type: "ramses_extras/device_simulator/resume_scenario",
        scenario: scenarioId,
      });
      await this._fetchData();
    } catch (err) {
      // eslint-disable-next-line no-console
      console.error("DeviceSimulatorCard: resume_scenario failed", err);
    }
  }

  async _startSavedPlayback(identifier) {
    if (!this._hass || !identifier) return;
    const params = this._scenarioParams?.[SCENARIO_DEVICE_PLAYBACK] || {};
    const loops = Number(params.loops) || 1;
    const payload = {
      type: "ramses_extras/device_simulator/start_scenario",
      scenario: SCENARIO_DEVICE_PLAYBACK,
      params: {
        conversation: identifier,
        loops,
      },
    };
    if (this._playbackInterMsgDelay !== "" && this._playbackInterMsgDelay !== null) {
      const parsed = Number(this._playbackInterMsgDelay);
      if (!Number.isNaN(parsed)) {
        payload.params.inter_message_delay = parsed;
      }
    }
    if (this._playbackSkipAnswers) {
      payload.params.skip_answers = true;
    }
    try {
      await this._hass.callWS(payload);
      await this._fetchData();
    } catch (err) {
      // eslint-disable-next-line no-console
      console.error("DeviceSimulatorCard: start_saved_playback failed", err);
    }
  }

  async _savePlaybackImport() {
    if (!this._hass) return;
    const draft = this._playbackImportDraft || {};
    const content = (draft.log_content || "").trim();
    if (!content) return;
    this._playbackSaving = true;
    this._scheduleRender();
    try {
      const result = await this._hass.callWS({
        type: "ramses_extras/device_simulator/import_user_log",
        content,
        name: draft.name || undefined,
        save_yaml: true,
      });
      // Reset draft, refresh list
      this._playbackImportDraft = { log_content: "", name: "" };
      // Pre-select the new one so it appears as the default in the Devices tab
      if (result?.conversation_name) {
        this._playbackSelection = result.conversation_name;
      }
    } catch (err) {
      // eslint-disable-next-line no-console
      console.error("DeviceSimulatorCard: save playback import failed", err);
    } finally {
      this._playbackSaving = false;
      await this._fetchData();
    }
  }

  _clearPlaybackImport() {
    this._playbackImportDraft = { log_content: "", name: "" };
    this._scheduleRender();
  }

  async _loadPlaybackIntoEditor(identifier) {
    if (!this._hass || !identifier) return;
    try {
      const res = await this._hass.callWS({
        type: "ramses_extras/device_simulator/get_playback_text",
        identifier,
      });
      this._playbackImportDraft = {
        log_content: res?.text || "",
        // Pre-fill a new name so saving doesn't silently overwrite the original.
        name: `${identifier}_edited`,
      };
      // Jump to Scenarios tab where the editor lives.
      if (this._tab !== "scenarios") {
        this._setTab("scenarios");
      } else {
        this._scheduleRender();
      }
    } catch (err) {
      // eslint-disable-next-line no-console
      console.error("DeviceSimulatorCard: load playback failed", err);
    }
  }

  async _toggleScenario(scenarioId, enable) {
    if (!this._hass) return;
    const type = enable
      ? "ramses_extras/device_simulator/start_scenario"
      : "ramses_extras/device_simulator/stop_scenario";
    const payload = { type, scenario: scenarioId };
    if (enable) {
      const params = this._scenarioParams?.[scenarioId];
      if (params && Object.keys(params).length) {
        payload.params = this._prepareScenarioParams(scenarioId);
        // Extract clear_message_log from params and send as top-level parameter
        if (payload.params.clear_message_log !== undefined) {
          payload.clear_message_log = payload.params.clear_message_log;
          delete payload.params.clear_message_log;
        }
      }
    }
    try {
      await this._hass.callWS(payload);
      await this._fetchData();
    } catch (err) {
      // eslint-disable-next-line no-console
      console.error(`DeviceSimulatorCard: toggle_scenario ${scenarioId} failed`, err);
      await this._fetchData();
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

  async _subscribeToMessageEvents() {
    if (!this._hass || this._msgSubscription) return;
    if (!this._hass.connection) return;

    try {
      this._msgSubscription = await this._hass.connection.subscribeMessage(
        (event) => {
          if (!event?.event_type || event.event_type !== "device_messages") {
            return;
          }
          const payload = event?.data;
          if (!payload || !Array.isArray(payload.messages)) {
            return;
          }
          this._mergeDeviceMessages(payload.messages);
        },
        { type: "ramses_extras/device_simulator/subscribe_messages" },
      );
    } catch (err) {
      // eslint-disable-next-line no-console
      console.error("DeviceSimulatorCard: failed to subscribe to message events", err);
      this._msgSubscription = null;
    }
  }

  async _subscribeToScenarios() {
    if (!this._hass || this._scenarioSubscription) return;
    if (!this._hass.connection) return;

    try {
      this._scenarioSubscription = await this._hass.connection.subscribeMessage(
        (event) => {
          if (event?.event_type === "scenarios_changed") {
            void this._fetchData();
          }
        },
        { type: "ramses_extras/device_simulator/subscribe_scenarios" },
      );
    } catch (err) {
      // eslint-disable-next-line no-console
      console.error("Device Simulator: failed to subscribe to scenario updates", err);
      this._scenarioSubscription = null;
    }
  }

  // ========== INTERACTIONS ==========

  _setTab(tab) {
    this._tab = tab;
    this._scheduleRender();
    void this._fetchData();
    if (tab === "devices") {
      void this._subscribeToMessageEvents();
    }
  }

  async _loadProfile(name) {
    const reloadRf = this._profileReload[name] ?? true;
    const preloadSchema = this._profilePreloadSchema[name] ?? true;
    const resetCache = this._profileResetCache[name] ?? false;
    const eavesdrop = this._profileEavesdrop[name] ?? false;
    const skipHydrate = this._profileSkipHydrate[name] ?? false;
    const clearLog = this._profileClearLog[name] ?? false;
    // Get checkbox value from DOM
    const checkbox = this.shadowRoot.querySelector(`[data-action='auto-answer-check'][data-profile='${name}']`);
    const autoAnswer = checkbox ? checkbox.checked : true;
    const result = await this._hass.callWS({
      type: "ramses_extras/device_simulator/load_profile",
      profile: name,
      reload_ramses_cc: reloadRf,
      preload_schema: preloadSchema,
      reset_rf_cache: resetCache,
      enable_eavesdrop: eavesdrop,
      remove_database: skipHydrate,
      clear_message_log: clearLog,
      enable_auto_answer: autoAnswer,
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

  async _resumeAllDevices() {
    await this._resumeDevices();
  }

  async _resumeDevice(deviceId) {
    if (!deviceId) {
      return;
    }
    await this._resumeDevices([deviceId]);
  }

  async _resumeDevices(deviceIds) {
    if (!this._hass) {
      return;
    }
    const payload = {
      type: "ramses_extras/device_simulator/resume_devices",
    };
    if (Array.isArray(deviceIds) && deviceIds.length) {
      payload.device_ids = deviceIds;
    }
    try {
      await this._hass.callWS(payload);
    } catch (error) {
      // eslint-disable-next-line no-console
      console.error("DeviceSimulatorCard: resume_devices failed", error);
    }
    await this._fetchData();
  }

  async _silenceAllDevices() {
    await this._silenceDevices();
  }

  async _silenceDevices(deviceIds) {
    if (!this._hass) {
      return;
    }
    const payload = {
      type: "ramses_extras/device_simulator/silence_devices",
    };
    if (Array.isArray(deviceIds) && deviceIds.length) {
      payload.device_ids = deviceIds;
    }
    try {
      await this._hass.callWS(payload);
    } catch (error) {
      // eslint-disable-next-line no-console
      console.error("DeviceSimulatorCard: silence_devices failed", error);
    }
    await this._fetchData();
  }

  async _discoverCapabilities(deviceIds) {
    if (!this._hass) {
      return;
    }
    const payload = {
      type: "ramses_extras/device_simulator/discover_capabilities",
    };
    if (Array.isArray(deviceIds) && deviceIds.length) {
      payload.device_ids = deviceIds;
    }
    try {
      const result = await this._hass.callWS(payload);
      // eslint-disable-next-line no-console
      console.log("DeviceSimulatorCard: discover_capabilities result", result);
      if (result.errors && result.errors.length) {
        // eslint-disable-next-line no-console
        console.warn("DeviceSimulatorCard: discovery errors", result.errors);
      }
    } catch (error) {
      // eslint-disable-next-line no-console
      console.error("DeviceSimulatorCard: discover_capabilities failed", error);
    }
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
    const payload = {
      type: "ramses_extras/device_simulator/start_scenario",
      scenario: scenarioId,
      params,
    };
    // Extract clear_message_log from params and send as top-level parameter
    if (params.clear_message_log !== undefined) {
      payload.clear_message_log = params.clear_message_log;
      delete params.clear_message_log;
    }
    try {
      await this._hass.callWS(payload);
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

  async _setPreserveState(enabled) {
    await this._hass.callWS({
      type: "ramses_extras/device_simulator/set_preserve_state",
      enabled,
    });
    this._preserveState = enabled;
    this._scheduleRender();
    await new Promise((r) => setTimeout(r, 300));
    await this._fetchData();
  }

  async _fetchRfConfig() {
    if (!this._hass) return;
    try {
      const result = await this._hass.callWS({
        type: "ramses_extras/device_simulator/get_rf_config",
      });
      this._rfEnforceKnownList = result.enforce_known_list === true;
      this._rfKnownListEnabled = result.known_list_enabled === true;
    } catch (err) {
      // eslint-disable-next-line no-console
      console.error("DeviceSimulatorCard: failed to fetch RF config", err);
    }
  }

  async _setAnswerUnknownDevices(enabled) {
    await this._hass.callWS({
      type: "ramses_extras/device_simulator/set_answer_unknown_devices",
      enabled,
    });
    this._answerUnknownDevices = enabled;
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
          <div class="tab ${this._tab === "scenarios" ? "active" : ""}" data-tab="scenarios">Scenarios</div>
          <div class="tab ${this._tab === "devices" ? "active" : ""}" data-tab="devices">Devices</div>
          <div class="tab ${this._tab === "events" ? "active" : ""}" data-tab="events">Events</div>
        </div>

        <div class="content ${this._tab === "profiles" ? "active" : ""}" data-content="profiles">
          ${buildProfiles(this)}
        </div>
        <div class="content ${this._tab === "scenarios" ? "active" : ""}" data-content="scenarios">
          ${buildScenarios(this)}
        </div>
        <div class="content ${this._tab === "devices" ? "active" : ""}" data-content="devices">
          ${buildDevices(this)}
        </div>
        <div class="content ${this._tab === "events" ? "active" : ""}" data-content="events">
          ${buildEvents(this)}
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

    root.querySelectorAll("[data-action='resume-device']").forEach((btn) => {
      btn.addEventListener("click", () => this._resumeDevice(btn.dataset.deviceId));
    });

    root.querySelectorAll("[data-action='silence-device']").forEach((btn) => {
      btn.addEventListener("click", () => this._silenceDevices([btn.dataset.deviceId]));
    });

    root.querySelectorAll("[data-action='discover-device']").forEach((btn) => {
      btn.addEventListener("click", () => this._discoverCapabilities([btn.dataset.deviceId]));
    });

    const resumeAll = root.querySelector("[data-action='resume-all-devices']");
    if (resumeAll) {
      resumeAll.addEventListener("click", () => this._resumeAllDevices());
    }

    const silenceAll = root.querySelector("[data-action='silence-all-devices']");
    if (silenceAll) {
      silenceAll.addEventListener("click", () => this._silenceAllDevices());
    }

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

    root.querySelectorAll("[data-action='pause-scenario']").forEach(btn => {
      btn.addEventListener("click", () => this._pauseScenario(btn.dataset.scenarioId));
    });

    root.querySelectorAll("[data-action='resume-scenario']").forEach(btn => {
      btn.addEventListener("click", () => this._resumeScenario(btn.dataset.scenarioId));
    });

    root.querySelectorAll("[data-action='delete-saved-playback']").forEach(btn => {
      btn.addEventListener("click", () => this._deleteSavedPlayback(btn.dataset.identifier));
    });

    root.querySelectorAll("[data-action='load-playback-editor']").forEach(btn => {
      btn.addEventListener("click", () => this._loadPlaybackIntoEditor(btn.dataset.identifier));
    });

    root.querySelectorAll("[data-action='start-saved-playback']").forEach(btn => {
      btn.addEventListener("click", () => this._startSavedPlayback(btn.dataset.identifier));
    });

    const playbackSelect = root.querySelector("[data-action='playback-select']");
    if (playbackSelect) {
      playbackSelect.addEventListener("change", (e) => {
        this._playbackSelection = e.target.value;
        this._scheduleRender();
      });
    }

    root.querySelectorAll("[data-action='playback-import-field']").forEach((input) => {
      input.addEventListener("input", (e) => {
        const field = e.target.dataset.field;
        this._playbackImportDraft = {
          ...(this._playbackImportDraft || {}),
          [field]: e.target.value,
        };
        // Toggle Save disabled live without re-rendering the textarea (lose focus)
        const saveBtn = root.querySelector("[data-action='save-playback-import']");
        if (saveBtn) {
          saveBtn.disabled = !(this._playbackImportDraft.log_content || "").trim();
        }
        const clearBtn = root.querySelector("[data-action='clear-playback-import']");
        if (clearBtn) {
          clearBtn.disabled = !(
            (this._playbackImportDraft.log_content || "").trim()
            || (this._playbackImportDraft.name || "").trim()
          );
        }
      });
    });

    const saveBtn = root.querySelector("[data-action='save-playback-import']");
    if (saveBtn) {
      saveBtn.addEventListener("click", () => this._savePlaybackImport());
    }
    const clearImportBtn = root.querySelector("[data-action='clear-playback-import']");
    if (clearImportBtn) {
      clearImportBtn.addEventListener("click", () => this._clearPlaybackImport());
    }

    root.querySelectorAll("[data-action='toggle-scenario']").forEach((el) => {
      el.addEventListener("change", (e) => {
        this._toggleScenario(el.dataset.scenarioId, Boolean(e.target.checked));
      });
    });

    const imdInput = root.querySelector("[data-action='playback-inter-msg-delay']");
    if (imdInput) {
      imdInput.addEventListener("input", (e) => {
        this._playbackInterMsgDelay = e.target.value;
      });
    }

    const skipAnswers = root.querySelector("[data-action='playback-skip-answers']");
    if (skipAnswers) {
      skipAnswers.addEventListener("change", (e) => {
        this._playbackSkipAnswers = Boolean(e.target.checked);
      });
    }

    const searchInput = root.querySelector("[data-action='playback-search']");
    if (searchInput) {
      searchInput.addEventListener("input", (e) => {
        this._playbackSearchQuery = e.target.value;
        this._scheduleRender();
      });
    }

    const aaToggle = root.querySelector("[data-action='toggle-auto-answer']");
    if (aaToggle) aaToggle.addEventListener("change", (e) => this._setAutoAnswer(e.target.checked));

    const auToggle = root.querySelector("[data-action='toggle-answer-unknown']");
    if (auToggle) auToggle.addEventListener("change", (e) => this._setAnswerUnknownDevices(e.target.checked));

    const psToggle = root.querySelector("[data-action='toggle-preserve-state']");
    if (psToggle) psToggle.addEventListener("change", (e) => this._setPreserveState(e.target.checked));

    root.querySelectorAll("[data-action='toggle-device']").forEach(el => {
      el.addEventListener("change", () => {
        const d = this._devices.find(d => d.id === el.dataset.deviceId);
        if (d) this._toggleDeviceEnabled(d.id, d.enabled);
      });
    });

    root.querySelectorAll("[data-action='clear-device-log']").forEach((btn) => {
      btn.addEventListener("click", () => {
        const deviceId = btn.dataset.deviceId;
        void this._clearDeviceMessages(deviceId || null);
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

    root.querySelectorAll("[data-action='reload-check']").forEach(chk => {
      chk.addEventListener("change", (e) => {
        this._profileReload = { ...this._profileReload, [chk.dataset.profile]: e.target.checked };
      });
    });

    root.querySelectorAll("[data-action='preload-check']").forEach(chk => {
      chk.addEventListener("change", (e) => {
        this._profilePreloadSchema = { ...this._profilePreloadSchema, [chk.dataset.profile]: e.target.checked };
      });
    });

    root.querySelectorAll("[data-action='reset-cache-check']").forEach(chk => {
      chk.addEventListener("change", (e) => {
        this._profileResetCache = { ...this._profileResetCache, [chk.dataset.profile]: e.target.checked };
      });
    });

    root.querySelectorAll("[data-action='eavesdrop-check']").forEach(chk => {
      chk.addEventListener("change", (e) => {
        this._profileEavesdrop = { ...this._profileEavesdrop, [chk.dataset.profile]: e.target.checked };
      });
    });

    root.querySelectorAll("[data-action='skip-hydrate-check']").forEach(chk => {
      chk.addEventListener("change", (e) => {
        this._profileSkipHydrate = { ...this._profileSkipHydrate, [chk.dataset.profile]: e.target.checked };
      });
    });

    root.querySelectorAll("[data-action='clear-log-check']").forEach(chk => {
      chk.addEventListener("change", (e) => {
        this._profileClearLog = { ...this._profileClearLog, [chk.dataset.profile]: e.target.checked };
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

  _profileDeviceStateMeta(profileCountOverride, knownCountOverride) {
    const knownListCount = Object.keys(this._knownList()).length;
    const counts = this._profileDeviceCounts || {};
    const profileCount =
      profileCountOverride ?? counts.active ?? this._profileDeviceCount();
    const knownCount =
      knownCountOverride ?? counts.known ?? knownListCount ?? 0;
    const running = (this._runningScenarios || []).includes(
      SCENARIO_PROFILE_EMISSIONS,
    );

    const pluralize = (value, noun) =>
      `${value} ${noun}${value === 1 ? "" : "s"}`;

    if (running && profileCount > 0) {
      return {
        state: "active",
        label: "Active (autonomous)",
        description: `${pluralize(
          profileCount,
          "device",
        )} emitting autonomously until you stop them.`,
        chipClass: "chip profile",
        profileCount,
        knownCount,
      };
    }

    if (profileCount > 0) {
      return {
        state: "reply",
        label: "Registered (reply-only)",
        description: `${pluralize(
          profileCount,
          "device",
        )} answering discovery/RQ traffic. Emitters stay idle until you press Start.`,
        chipClass: "chip reply",
        profileCount,
        knownCount,
      };
    }

    if (knownCount > 0) {
      return {
        state: "disabled",
        label: "Disabled",
        description: `${pluralize(
          knownCount,
          "device",
        )} defined in the profile. Start them to register again.`,
        chipClass: "chip disabled",
        profileCount,
        knownCount,
      };
    }

    return {
      state: "disabled",
      label: "No profile devices",
      description: "Load a profile to register simulator devices.",
      chipClass: "chip muted",
      profileCount,
      knownCount,
    };
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

  _mergeDeviceMessages(batch) {
    if (!Array.isArray(batch) || batch.length === 0) {
      return;
    }
    const nextPreviews = { ...this._deviceMsgPreviews };
    batch.forEach((message) => {
      if (!message) {
        return;
      }
      const ids = Array.isArray(message.device_ids) && message.device_ids.length
        ? message.device_ids
        : message.device_id
          ? [message.device_id]
          : [];
      if (!ids.length) {
        return;
      }
      ids.forEach((deviceId) => {
        if (!deviceId) {
          return;
        }
        const existing = nextPreviews[deviceId] ? [...nextPreviews[deviceId]] : [];
        const last = existing[existing.length - 1];
        const lastKey = last ? `${last.ts}-${last.direction}-${last.code}-${last.verb}` : null;
        const nextKey = `${message.ts}-${message.direction}-${message.code}-${message.verb}`;
        if (lastKey === nextKey) {
          return;
        }
        existing.push(message);
        if (existing.length > MESSAGE_HISTORY_LIMIT) {
          existing.splice(0, existing.length - MESSAGE_HISTORY_LIMIT);
        }
        nextPreviews[deviceId] = existing;
      });
    });
    this._deviceMsgPreviews = nextPreviews;
    this._scheduleRender();
  }

  async _clearDeviceMessages(deviceId) {
    if (!this._hass) {
      return;
    }
    try {
      await this._hass.callWS({
        type: "ramses_extras/device_simulator/clear_messages",
        ...(deviceId ? { device_ids: [deviceId] } : {}),
      });
      if (deviceId) {
        const next = { ...this._deviceMsgPreviews };
        delete next[deviceId];
        this._deviceMsgPreviews = next;
      } else {
        this._deviceMsgPreviews = {};
      }
      this._scheduleRender();
    } catch (err) {
      // eslint-disable-next-line no-console
      console.error("DeviceSimulatorCard: failed to clear messages", err);
    }
  }

  _buildProfileDeviceStub(summary) {
    if (!summary?.id) {
      return null;
    }
    const deviceId = summary.id;
    const zones = this._profileZoneMembership?.[deviceId] || [];
    return {
      id: deviceId,
      type: (summary.class || "profile").toLowerCase(),
      enabled: Boolean(summary.active),
      suppress_autonomous: false,
      suppress_responses: false,
      excluded_codes: [],
      source: "profile",
      owned_by_profile: true,
      zones,
    };
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
}

DeviceSimulatorCard.register();
