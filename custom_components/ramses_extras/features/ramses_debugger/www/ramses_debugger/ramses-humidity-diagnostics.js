/**
 * Ramses Humidity Diagnostics Card - detect where the reported outdoor
 * RH is measured on a FAN unit (outside flow vs supply duct).
 *
 * Flow:
 * 1. User runs the fan on HIGH with the bypass OPEN for ~15 minutes
 *    (helper buttons send the commands; manual works too).
 * 2. "Analyze" fetches recorder history for outdoor RH, outdoor temp and
 *    supply temp over the last N minutes and computes which temperature
 *    pairing yields the more stable dewpoint (issue 304).
 * 3. The result explains the recommended Sensor Control setting and can
 *    apply it via ramses_extras/sensor_control/set_abs_temperature_kind.
 *
 * @module ramses-humidity-diagnostics
 * @extends RamsesBaseCard
 */

import * as logger from '../../helpers/logger.js';
import { RamsesBaseCard } from '../../helpers/ramses-base-card.js';
import {
  callService,
  sendFanCommand,
} from '../../helpers/card-services.js';
import {
  analyzeHumidityLocation,
  parseHistorySeries,
} from './humidity-diagnostics.js';

const DEFAULT_WINDOW_MINUTES = 20;
const RUN_MINUTES = 15;
const RUN_STORAGE_KEY = 'ramses_humidity_diag_run';

/** Control-switch mapping keys suspended during a diagnostic run. */
const CONTROL_SWITCH_KEYS = [
  'temp_control_entity',
  'co2_control_entity',
  'dehum_mode_entity',
];

/**
 * Ramses Humidity Diagnostics card.
 *
 * @class RamsesHumidityDiagnosticsCard
 * @extends RamsesBaseCard
 */
class RamsesHumidityDiagnosticsCard extends RamsesBaseCard {
  constructor() {
    super();
    this._mappings = {};
    this._absInputs = null;
    this._windowMinutes = DEFAULT_WINDOW_MINUTES;
    this._busy = null;
    this._lastError = null;
    this._result = null;
    this._applied = null;
    this._disabledControls = [];
    this._run = null;
    this._runTimer = null;
    this._domInitialized = false;
  }

  getCardSize() {
    return 8;
  }

  static getTagName() {
    return 'ramses-humidity-diagnostics';
  }

  static getStubConfig() {
    return {
      type: `custom:${this.getTagName()}`,
      device_id: '',
    };
  }

  getDefaultConfig() {
    return { name: 'Humidity sensor location' };
  }

  getFeatureName() {
    return 'ramses_debugger';
  }

  getRequiredEntities() {
    return {};
  }

  hasValidConfig() {
    return Boolean(this._config?.device_id);
  }

  validateConfig() {
    const valid = Boolean(this._config?.device_id);
    return {
      valid,
      errors: valid ? [] : ['device_id is required'],
    };
  }

  setConfig(config) {
    super.setConfig(config);
    const w = Number(config?.window_minutes);
    if (Number.isFinite(w) && w >= 5) {
      this._windowMinutes = Math.round(w);
    }
  }

  _onConnected() {
    void this._loadMappings().then(() => this._resumeRun());
  }

  _onDisconnected() {
    if (this._runTimer) {
      clearInterval(this._runTimer);
      this._runTimer = null;
    }
  }

  /** localStorage key for the pending auto-run of this device. */
  _runStorageKey() {
    return `${RUN_STORAGE_KEY}_${this._config?.device_id}`;
  }

  _loadRun() {
    if (typeof window === 'undefined' || !window.localStorage) {
      return null;
    }
    try {
      const raw = window.localStorage.getItem(this._runStorageKey());
      const run = raw ? JSON.parse(raw) : null;
      return run && Number.isFinite(run.endTs) ? run : null;
    } catch {
      return null;
    }
  }

  _saveRun() {
    if (typeof window === 'undefined' || !window.localStorage) {
      return;
    }
    try {
      if (this._run) {
        window.localStorage.setItem(
          this._runStorageKey(),
          JSON.stringify(this._run)
        );
      } else {
        window.localStorage.removeItem(this._runStorageKey());
      }
    } catch {
      // localStorage unavailable — run just becomes non-persistent
    }
  }

  /**
   * Resume a persisted auto-run after reload/navigation.
   * If the run already finished, analyze its window and restore now.
   */
  _resumeRun() {
    const run = this._loadRun();
    if (!run) {
      return;
    }
    this._run = run;
    this._disabledControls = Array.isArray(run.disabledControls)
      ? run.disabledControls
      : [];
    if (Date.now() >= run.endTs) {
      void this._finalizeRun();
    } else {
      this._scheduleRunTimer();
    }
    this.render();
  }

  _scheduleRunTimer() {
    if (this._runTimer) {
      clearInterval(this._runTimer);
    }
    this._runTimer = setInterval(() => {
      if (!this._run) {
        clearInterval(this._runTimer);
        this._runTimer = null;
        return;
      }
      if (Date.now() >= this._run.endTs) {
        clearInterval(this._runTimer);
        this._runTimer = null;
        void this._finalizeRun();
      } else {
        this._updateCountdown();
      }
    }, 1000);
    this._updateCountdown();
  }

  _updateCountdown() {
    const el = this.shadowRoot?.getElementById('rhd-countdown');
    if (!el || !this._run) {
      return;
    }
    const secs = Math.max(0, Math.round((this._run.endTs - Date.now()) / 1000));
    const mm = String(Math.floor(secs / 60)).padStart(2, '0');
    const ss = String(secs % 60).padStart(2, '0');
    el.textContent = `run active — auto-analyze + restore in ${mm}:${ss}`;
  }

  async _onAutoRun() {
    if (!this._hass || this._busy || this._run) {
      return;
    }
    await this._onStartTest();
    if (this._lastError) {
      return;
    }
    const now = Date.now();
    this._run = {
      startTs: now,
      endTs: now + RUN_MINUTES * 60 * 1000,
      disabledControls: [...this._disabledControls],
    };
    this._saveRun();
    this._scheduleRunTimer();
    this.render();
  }

  async _finalizeRun() {
    const run = this._run;
    if (!run) {
      return;
    }
    await this._onAnalyze({ start: run.startTs, end: run.endTs });
    await this._onRestore();
    this._run = null;
    this._saveRun();
    this.render();
  }

  async _onCancelRun() {
    if (!this._run) {
      return;
    }
    if (this._runTimer) {
      clearInterval(this._runTimer);
      this._runTimer = null;
    }
    this._run = null;
    this._saveRun();
    await this._onRestore();
  }

  async _loadMappings() {
    if (!this._hass || !this._config?.device_id) {
      return;
    }
    try {
      const res = await this._sendWebSocketCommand(
        {
          type: 'ramses_extras/get_entity_mappings',
          device_id: this._config.device_id,
          feature_id: 'ramses_debugger',
        },
        `hum_diag_mappings_${this._config.device_id}`
      );
      this._mappings = res?.mappings || {};
      this._absInputs = res?.abs_humidity_inputs || null;
    } catch (error) {
      logger.warn('HumidityDiagnostics: failed to load mappings:', error);
      this._lastError = error;
    }
    this.render();
  }

  _entityId(key) {
    return this._mappings?.[key] || null;
  }

  _fmt(v, digits = 2) {
    return Number.isFinite(v) ? v.toFixed(digits) : '—';
  }

  async _onStartTest() {
    if (!this._hass || this._busy) {
      return;
    }
    this._busy = 'start';
    this._lastError = null;
    this.render();
    try {
      // Suspend automation controls so they cannot fight the forced run
      // (temp control steers the bypass, humidity/CO2 steer the speed).
      this._disabledControls = [];
      for (const key of CONTROL_SWITCH_KEYS) {
        const eid = this._entityId(key);
        if (eid && this._hass.states?.[eid]?.state === 'on') {
          await callService(this._hass, 'switch', 'turn_off', {
            entity_id: eid,
          });
          this._disabledControls.push(eid);
        }
      }
      await sendFanCommand(this._hass, this._config.device_id, 'fan_high');
      await sendFanCommand(
        this._hass,
        this._config.device_id,
        'fan_bypass_open'
      );
    } catch (error) {
      this._lastError = error;
    } finally {
      this._busy = null;
      this.render();
    }
  }

  async _onRestore() {
    if (!this._hass || this._busy) {
      return;
    }
    this._busy = 'restore';
    this._lastError = null;
    this.render();
    try {
      await sendFanCommand(this._hass, this._config.device_id, 'fan_auto');
      await sendFanCommand(
        this._hass,
        this._config.device_id,
        'fan_bypass_auto'
      );
      // Re-enable only the controls that were on before the run.
      for (const eid of this._disabledControls) {
        await callService(this._hass, 'switch', 'turn_on', {
          entity_id: eid,
        });
      }
      this._disabledControls = [];
    } catch (error) {
      this._lastError = error;
    } finally {
      this._busy = null;
      this.render();
    }
  }

  /**
   * Analyze recorded history, either for the last `windowMinutes` or for
   * an explicit {start, end} epoch-ms range (auto-run window).
   *
   * @param {{start: number, end: number}} [range] Explicit time range.
   */
  async _onAnalyze(range = null) {
    if (!this._hass || this._busy) {
      return;
    }
    const rhEntity = this._entityId('outdoor_humidity_entity');
    const outEntity = this._entityId('outdoor_temp_entity');
    const supEntity = this._entityId('supply_temp_entity');
    const bypassEntity = this._entityId('bypass_entity');
    const missing = [
      ['outdoor_humidity_entity', rhEntity],
      ['outdoor_temp_entity', outEntity],
      ['supply_temp_entity', supEntity],
    ]
      .filter(([, v]) => !v)
      .map(([k]) => k);
    if (missing.length) {
      this._lastError = new Error(
        `Missing entity mappings: ${missing.join(', ')}`
      );
      this.render();
      return;
    }

    this._busy = 'analyze';
    this._lastError = null;
    this._result = null;
    this._applied = null;
    this.render();

    try {
      const end = range ? new Date(range.end) : new Date();
      const start = range
        ? new Date(range.start)
        : new Date(end.getTime() - this._windowMinutes * 60 * 1000);
      const entityIds = [rhEntity, outEntity, supEntity];
      if (bypassEntity) {
        entityIds.push(bypassEntity);
      }
      const res = await this._hass.callWS({
        type: 'history/history_during_period',
        start_time: start.toISOString(),
        end_time: end.toISOString(),
        entity_ids: entityIds,
        minimal_response: true,
        no_attributes: true,
        significant_changes_only: false,
      });

      const result = analyzeHumidityLocation({
        rh: parseHistorySeries(res?.[rhEntity]),
        outdoorTemp: parseHistorySeries(res?.[outEntity]),
        supplyTemp: parseHistorySeries(res?.[supEntity]),
      });
      result.bypassOpenFraction = this._bypassOpenFraction(res?.[bypassEntity]);
      this._result = result;
    } catch (error) {
      this._lastError = error;
    } finally {
      this._busy = null;
      this.render();
    }
  }

  /**
   * Fraction of the window where the bypass binary sensor was "on".
   *
   * @param {Array<Object>} raw History rows for the bypass entity.
   * @returns {number|null} Fraction 0..1, or null when unknown.
   */
  _bypassOpenFraction(raw) {
    if (!Array.isArray(raw) || raw.length === 0) {
      return null;
    }
    let open = 0;
    for (const item of raw) {
      const s = 's' in item ? item.s : item.state;
      if (s === 'on') {
        open += 1;
      }
    }
    return open / raw.length;
  }

  async _onApply() {
    if (!this._hass || this._busy) {
      return;
    }
    this._busy = 'apply';
    this._lastError = null;
    this._applied = null;
    this.render();
    try {
      await this._hass.callWS({
        type: 'ramses_extras/sensor_control/set_abs_temperature_kind',
        device_id: this._config.device_id,
        metric: 'outdoor_abs_humidity',
        kind: 'internal_supply',
      });
      this._applied = true;
    } catch (error) {
      this._applied = false;
      this._lastError = error;
    } finally {
      this._busy = null;
      this.render();
    }
  }

  _attachEventListeners() {
    if (!this.shadowRoot) {
      return;
    }
    const bind = (id, fn) => {
      const el = this.shadowRoot.getElementById(id);
      if (el) {
        el.addEventListener('click', fn);
      }
    };
    bind('rhd-start', () => void this._onStartTest());
    bind('rhd-restore', () => void this._onRestore());
    bind('rhd-analyze', () => void this._onAnalyze());
    bind('rhd-apply', () => void this._onApply());
    bind('rhd-autorun', () => void this._onAutoRun());
    bind('rhd-cancel', () => void this._onCancelRun());
    const win = this.shadowRoot.getElementById('rhd-window');
    if (win) {
      win.addEventListener('change', (ev) => {
        const v = Number(ev?.target?.value);
        if (Number.isFinite(v) && v >= 5) {
          this._windowMinutes = Math.round(v);
        }
      });
    }
  }

  _renderContent() {
    if (!this._domInitialized) {
      this._initializeDOM();
      this._domInitialized = true;
    }
    this._updateDOM();
  }

  _renderResult() {
    const r = this._result;
    if (!r) {
      return '';
    }
    const verdicts = {
      supply: this.t('card.diagnostics.verdict_supply')
        || 'Measured in the SUPPLY duct (after heat recovery / bypass)',
      outdoor: this.t('card.diagnostics.verdict_outdoor')
        || 'Measured on the OUTDOOR (untreated) airflow',
      inconclusive: this.t('card.diagnostics.verdict_inconclusive')
        || 'Inconclusive',
    };
    const reasons = {
      not_enough_samples:
        'Not enough recorded samples — make sure recorder captured the test window.',
      supply_temp_flat:
        'Supply temperature barely moved — re-run on a colder/hotter day or check the bypass opened.',
      ambiguous:
        'Both pairings are similarly stable — no clear verdict.',
    };
    let action = '';
    if (r.verdict === 'supply') {
      action = `
        <div class="rhd-hint">
          Set Sensor Control → Internal Fan Sensors → outdoor absolute
          humidity temperature to
          <b>Internal (from FAN's supply flow)</b>.
          <button id="rhd-apply" class="rhd-btn primary">Apply now</button>
          ${this._applied === true ? '<span class="rhd-ok">Applied</span>' : ''}
          ${this._applied === false ? '<span class="rhd-err">Apply failed — set it manually in Sensor Control</span>' : ''}
        </div>`;
    } else if (r.verdict === 'outdoor') {
      action = `
        <div class="rhd-hint">
          Keep the default pairing: Sensor Control → Internal Fan Sensors →
          outdoor absolute humidity temperature =
          <b>Internal (from FAN's outside flow)</b>.
        </div>`;
    }
    return `
      <div class="rhd-result ${r.verdict}">
        <div class="rhd-verdict">${verdicts[r.verdict] || verdicts.inconclusive}</div>
        ${r.reason ? `<div class="rhd-reason">${reasons[r.reason] || r.reason}</div>` : ''}
        <table class="rhd-table">
          <tr><td>Samples</td><td>${r.samples}</td></tr>
          <tr><td>Supply temp range</td><td>${this._fmt(r.supplyRange, 1)} °C</td></tr>
          <tr><td>Dewpoint spread (supply pairing)</td>
              <td>${this._fmt(r.dewpointStdSupply)} °C</td></tr>
          <tr><td>Dewpoint spread (outdoor pairing)</td>
              <td>${this._fmt(r.dewpointStdOutdoor)} °C</td></tr>
          <tr><td>Correlation RH ↔ supply temp</td>
              <td>${this._fmt(r.corrRhSupply)}</td></tr>
          ${r.bypassOpenFraction !== null && r.bypassOpenFraction !== undefined ? `
          <tr><td>Bypass open</td>
              <td>${Math.round(r.bypassOpenFraction * 100)}% of samples</td></tr>` : ''}
        </table>
        ${action}
      </div>`;
  }

  _initializeDOM() {
    const title = this._config?.name
      || this.t('card.diagnostics.title')
      || 'Humidity sensor location';
    const deviceId = this._config?.device_id;

    this.shadowRoot.innerHTML = `
      <style>
        .rhd-card { padding: 16px; font-size: 14px; }
        .rhd-title { font-size: 18px; font-weight: 600; margin-bottom: 8px; }
        .rhd-expl { color: var(--secondary-text-color); margin-bottom: 12px;
                    line-height: 1.5; }
        .rhd-row { display: flex; gap: 8px; flex-wrap: wrap;
                   align-items: center; margin-bottom: 8px; }
        .rhd-btn { border: 1px solid var(--divider-color); border-radius: 8px;
                   background: var(--secondary-background-color);
                   color: var(--primary-text-color); padding: 6px 12px;
                   cursor: pointer; font-size: 13px; }
        .rhd-btn.primary { background: var(--primary-color); color: #fff;
                           border: none; }
        .rhd-btn:disabled { opacity: 0.5; cursor: default; }
        .rhd-input { width: 70px; }
        .rhd-live { font-size: 12px; color: var(--secondary-text-color); }
        .rhd-err { color: var(--error-color, #f44336); font-size: 12px; }
        .rhd-ok { color: var(--success-color, #4CAF50); font-size: 12px;
                  margin-left: 8px; }
        .rhd-result { margin-top: 12px; border: 1px solid var(--divider-color);
                      border-radius: 10px; padding: 10px; }
        .rhd-result.supply { border-color: var(--warning-color, #f4b400); }
        .rhd-result.outdoor { border-color: var(--success-color, #4CAF50); }
        .rhd-verdict { font-weight: 700; margin-bottom: 6px; }
        .rhd-reason { color: var(--secondary-text-color); margin-bottom: 6px; }
        .rhd-table { font-size: 12px; border-collapse: collapse; }
        .rhd-table td { padding: 2px 8px 2px 0;
                        color: var(--secondary-text-color); }
        .rhd-table td:last-child { color: var(--primary-text-color); }
        .rhd-hint { margin-top: 8px; font-size: 13px; line-height: 1.5; }
        .rhd-hint .rhd-btn { margin-left: 8px; }
        .rhd-none { color: var(--secondary-text-color); font-style: italic; }
      </style>
      <ha-card header="${title}">
        <div class="rhd-card">
        <div class="rhd-expl">
          Some units (e.g. Orcon, ClimaRad) report "outdoor" relative
          humidity measured in the supply duct, after heat recovery / bypass.
          This affects the outdoor <i>absolute</i> humidity calculation.
          <br><br>
          <b>1.</b> Run the fan on <b>High</b> with the bypass <b>open</b>
          for ~15 minutes. <b>Auto run</b> does it all: it suspends Temp,
          Balance and CO₂ control, sets HIGH + opens the bypass, waits
          15 min, analyzes, and restores everything (survives a page
          reload). Or drive it manually with the other buttons.
          <br>
          <b>2.</b> Click <b>Analyze</b> for an ad-hoc window — the tool
          compares which temperature pairing keeps the dewpoint most
          stable.
        </div>
        ${deviceId ? `
        <div class="rhd-row">
          <button id="rhd-autorun" class="rhd-btn primary">⚡ Auto run (15 min)</button>
          <button id="rhd-start" class="rhd-btn">▶ Fan HIGH + Bypass open</button>
          <button id="rhd-restore" class="rhd-btn">⏹ Restore (Auto + Bypass auto)</button>
        </div>
        <div class="rhd-row">
          <span class="rhd-live" id="rhd-countdown"></span>
          <button id="rhd-cancel" class="rhd-btn" style="display:none">Cancel run + restore</button>
          <span class="rhd-live" id="rhd-live"></span>
        </div>
        <div class="rhd-row">
          <label>Window (min):
            <input id="rhd-window" class="rhd-input" type="number" min="5"
                   value="${this._windowMinutes}"></label>
          <button id="rhd-analyze" class="rhd-btn primary">Analyze</button>
        </div>
        <div id="rhd-error" class="rhd-err" style="display:none"></div>
        <div id="rhd-result"></div>
        ` : `
        <div class="rhd-err">Configure <code>device_id</code> in the card
             YAML (e.g. <code>device_id: "32:153289"</code>).</div>
        `}
        </div>
      </ha-card>
    `;
    this._attachEventListeners();
  }

  _updateDOM() {
    if (!this.shadowRoot) {
      return;
    }
    const live = this.shadowRoot.getElementById('rhd-live');
    if (live) {
      const bypass = this._entityId('bypass_entity');
      const sup = this._entityId('supply_temp_entity');
      const parts = [];
      if (bypass && this._hass?.states?.[bypass]) {
        parts.push(`bypass: ${this._hass.states[bypass].state}`);
      }
      if (sup && this._hass?.states?.[sup]) {
        parts.push(`supply: ${this._hass.states[sup].state} °C`);
      }
      const kind = this._absInputs?.outdoor_abs_humidity?.temperature?.kind;
      if (kind) {
        parts.push(`current pairing: ${kind}`);
      }
      if (this._disabledControls.length) {
        parts.push(
          `controls paused: ${this._disabledControls.length}`
        );
      }
      live.textContent = parts.join(' · ');
    }

    const err = this.shadowRoot.getElementById('rhd-error');
    if (err) {
      if (this._lastError) {
        err.textContent = String(
          this._lastError?.message || this._lastError
        );
        err.style.display = '';
      } else {
        err.style.display = 'none';
      }
    }

    const res = this.shadowRoot.getElementById('rhd-result');
    if (res) {
      res.innerHTML = this._renderResult();
      const applyBtn = this.shadowRoot.getElementById('rhd-apply');
      if (applyBtn) {
        applyBtn.addEventListener('click', () => void this._onApply());
      }
    }

    const cancel = this.shadowRoot.getElementById('rhd-cancel');
    if (cancel) {
      cancel.style.display = this._run ? '' : 'none';
    }

    this._btnLabels = this._btnLabels || {};
    for (const [id, key] of [
      ['rhd-start', 'start'],
      ['rhd-restore', 'restore'],
      ['rhd-analyze', 'analyze'],
      ['rhd-apply', 'apply'],
      ['rhd-autorun', 'autorun'],
      ['rhd-cancel', 'cancel'],
    ]) {
      const btn = this.shadowRoot.getElementById(id);
      if (!btn) {
        continue;
      }
      if (!(id in this._btnLabels)) {
        this._btnLabels[id] = btn.textContent;
      }
      btn.disabled = this._busy !== null
        || (this._run && !['cancel', 'restore'].includes(key));
      btn.textContent =
        this._busy === key ? '…' : this._btnLabels[id];
    }
  }

  static getCardInfo() {
    return {
      type: 'ramses-humidity-diagnostics',
      name: 'Ramses Humidity Diagnostics',
      description:
        'Detect whether the reported outdoor RH is measured in the supply '
        + 'duct, and apply the correct absolute-humidity pairing.',
      preview: true,
      documentationURL:
        'https://github.com/wimpie70/ramses_extras/issues/304',
    };
  }
}

RamsesHumidityDiagnosticsCard.register();
