/* global customElements */

import * as logger from '../../helpers/logger.js';

import { RamsesBaseCard } from '../../helpers/ramses-base-card.js';
import { callService } from '../../helpers/card-services.js';

import './ramses-fan-map-editor.js';

class RamsesFanMap extends RamsesBaseCard {
  constructor() {
    super();
    this._domInitialized = false;
    this._loading = false;
    this._error = null;
    this._topology = null;
    this._remoteBindings = null;
    this._zoneCoordinatorState = null;
    this._sensorControl = null;
    this._requiredEntitiesDynamic = {};
    this._testBenchArmed = false;
    this._testBenchLastAction = null;
    this._unsubTestBenchEvents = null;
  }

  async _refreshCoordinatorState() {
    const deviceId = this._config?.device_id;
    if (!this._hass || !deviceId) {
      return;
    }

    try {
      const state = await this._sendWebSocketCommand(
        {
          type: 'ramses_extras/get_zone_coordinator_state',
          fan_id: deviceId,
        },
        `fan_map_zone_coordinator_${deviceId}`
      );
      this._zoneCoordinatorState = state;
    } catch (err) {
      logger.warn('RamsesFanMap: Failed to refresh zone coordinator state', err);
    }

    this.clearUpdateThrottle();
    this._scheduleRender(true);
  }

  _onConnected() {
    const deviceIdRaw = String(this._config?.device_id || '').trim();
    if (!this._hass || !deviceIdRaw) {
      return;
    }

    const normalized = deviceIdRaw.replace(/_/g, ':');

    if (this._unsubTestBenchEvents) {
      return;
    }

    this._hass.connection.subscribeEvents((event) => {
      const evt = event?.event_type;
      const data = event?.data || {};

      if (
        evt !== 'ramses_extras_zone_demand_changed'
        && evt !== 'ramses_extras_zone_actuation_completed'
        && evt !== 'ramses_extras_zone_ventilation_forced'
      ) {
        return;
      }

      const fanId = String(data?.fan_id || '').replace(/_/g, ':');
      if (!fanId || fanId !== normalized) {
        return;
      }

      this._refreshCoordinatorState();
    }).then((unsub) => {
      this._unsubTestBenchEvents = unsub;
    }).catch((err) => {
      logger.warn('RamsesFanMap: Failed to subscribe to test bench events', err);
    });
  }

  _onDisconnected() {
    if (this._unsubTestBenchEvents) {
      try {
        this._unsubTestBenchEvents();
      } catch (err) {
        logger.warn('RamsesFanMap: Failed to unsubscribe test bench events', err);
      }
      this._unsubTestBenchEvents = null;
    }
  }

  _captureOpenDetailsKeys() {
    const openKeys = new Set();
    const details = this.shadowRoot?.querySelectorAll('details[data-key][open]');
    details?.forEach((el) => {
      const key = el.getAttribute('data-key');
      if (key) {
        openKeys.add(key);
      }
    });
    return openKeys;
  }

  _restoreOpenDetailsKeys(openKeys) {
    if (!openKeys || !openKeys.size) {
      return;
    }

    const details = this.shadowRoot?.querySelectorAll('details[data-key]');
    details?.forEach((el) => {
      const key = el.getAttribute('data-key');
      if (key && openKeys.has(key)) {
        el.open = true;
      }
    });
  }

  _getFanIdCandidates() {
    const raw = String(this._config?.device_id || '').trim();
    if (!raw) {
      return [];
    }
    const colon = raw.replace(/_/g, ':');
    return raw === colon ? [raw] : [raw, colon];
  }

  _getZoneDemandDiagnostics(zoneIdRaw) {
    const zoneId = String(zoneIdRaw || '').trim();
    if (!zoneId) {
      return null;
    }

    const diag = this._zoneCoordinatorState?.diagnostics;
    const registry = diag?.demand_registry;
    const demands = registry?.demands;
    if (!demands || typeof demands !== 'object') {
      return null;
    }

    const fanIds = this._getFanIdCandidates();
    for (const fanId of fanIds) {
      const key = `${fanId}:${zoneId}`;
      const entry = demands[key];
      if (entry) {
        const sources = Object.entries(entry)
          .filter(([, v]) => v && typeof v === 'object')
          .map(([k, v]) => ({
            source: k,
            has_demand: Boolean(v?.has_demand),
          }));

        const anyDemand = sources.some((s) => s.has_demand === true);
        const manual = sources.find((s) => s.source === 'MANUAL');

        return {
          anyDemand,
          manualPresent: Boolean(manual),
          manualDemand: manual ? manual.has_demand : null,
          sources,
        };
      }
    }

    return null;
  }

  getFeatureName() {
    return 'sensor_control';
  }

  getRequiredEntities() {
    return this._requiredEntitiesDynamic || {};
  }

  getCardSize() {
    return 4;
  }

  static getConfigElement() {
    try {
      if (typeof window.RamsesFanMapEditor === 'undefined') {
        logger.error('RamsesFanMapEditor is not defined on window');
        return null;
      }
      return document.createElement('ramses-fan-map-editor');
    } catch (error) {
      logger.error('Error creating config element:', error);
      return null;
    }
  }

  getConfigElement() {
    try {
      if (typeof window.RamsesFanMapEditor === 'undefined') {
        logger.error('RamsesFanMapEditor is not defined on window');
        return null;
      }
      return document.createElement('ramses-fan-map-editor');
    } catch (error) {
      logger.error('Error creating config element:', error);
      return null;
    }
  }

  static getCardInfo() {
    return {
      type: this.getTagName(),
      name: 'FAN Map',
      description: 'Observability and test bench for FAN configuration (zones/areas/REMs/valves/sensors)',
      preview: true,
    };
  }

  setConfig(config) {
    const previousDeviceId = this._config?.device_id;
    super.setConfig(config);

    if (this._config?.device_id !== previousDeviceId) {
      this._loading = false;
      this._error = null;
      this._topology = null;
      this._remoteBindings = null;
      this._zoneCoordinatorState = null;
      this._sensorControl = null;
      this._requiredEntitiesDynamic = {};
      this.clearPreviousStates();

      if (this._hass && this._config?.device_id) {
        this._loadInitialState();
      }
    }
  }

  _buildRequiredEntitiesFromTopology(topology) {
    const result = {};
    const zones = this._asList(topology?.zones);

    for (const zone of zones) {
      const zoneId = String(zone?.zone_id || '').trim();
      if (!zoneId) {
        continue;
      }

      const sensors = this._asObject(zone?.sensors);
      const actuator = this._asObject(zone?.actuator);

      const temperature = sensors?.temperature_entity;
      const humidity = sensors?.humidity_entity;
      const co2 = sensors?.co2_entity;
      const actuatorEntity = actuator?.entity_id;

      const inletValve = zone?.inlet_valve_entity;
      const outletValve = zone?.outlet_valve_entity;

      if (typeof temperature === 'string' && temperature) {
        result[`zone_${zoneId}_temperature`] = temperature;
      }
      if (typeof humidity === 'string' && humidity) {
        result[`zone_${zoneId}_humidity`] = humidity;
      }
      if (typeof co2 === 'string' && co2) {
        result[`zone_${zoneId}_co2`] = co2;
      }
      if (typeof actuatorEntity === 'string' && actuatorEntity) {
        result[`zone_${zoneId}_actuator`] = actuatorEntity;
      }

      if (typeof inletValve === 'string' && inletValve) {
        result[`zone_${zoneId}_inlet_valve`] = inletValve;
      }
      if (typeof outletValve === 'string' && outletValve) {
        result[`zone_${zoneId}_outlet_valve`] = outletValve;
      }
    }

    return result;
  }

  _buildRequiredEntitiesFromSensorControl(sensorControl) {
    const result = {};
    const sensors = this._asList(sensorControl?.area_sensors);

    for (const s of sensors) {
      const zoneId = String(s?.zone_id || '').trim();
      const areaId = String(s?.area_id || '').trim();
      const keyBase = [zoneId, areaId].filter((v) => v).join('_') || String(Math.random());

      for (const k of ['temperature_entity', 'humidity_entity', 'co2_entity', 'co2_threshold_entity']) {
        const entityId = s?.[k];
        if (typeof entityId === 'string' && entityId) {
          result[`area_sensor_${keyBase}_${k}`] = entityId;
        }
      }
    }

    return result;
  }

  async _loadInitialState() {
    if (!this._hass || !this._config?.device_id) {
      return;
    }

    const deviceId = this._config.device_id;
    this._loading = true;
    this._error = null;
    this._scheduleRender(true);

    try {
      const topology = await this._sendWebSocketCommand(
        {
          type: 'ramses_extras/get_fan_config_associations',
          device_id: deviceId,
        },
        `fan_map_topology_${deviceId}`
      );

      const remoteBindings = await this._sendWebSocketCommand(
        {
          type: 'ramses_extras/get_remote_bindings',
          device_id: deviceId,
        },
        `fan_map_remote_bindings_${deviceId}`
      );

      const zoneCoordinatorState = await this._sendWebSocketCommand(
        {
          type: 'ramses_extras/get_zone_coordinator_state',
          fan_id: deviceId,
        },
        `fan_map_zone_coordinator_${deviceId}`
      );

      let sensorControl = null;
      try {
        sensorControl = await this._sendWebSocketCommand(
          {
            type: 'ramses_extras/sensor_control/get_device_config',
            device_id: deviceId,
          },
          `fan_map_sensor_control_${deviceId}`
        );
      } catch (error) {
        logger.warn('RamsesFanMap: Failed to load sensor_control device config', error);
        sensorControl = null;
      }

      this._topology = topology;
      this._remoteBindings = remoteBindings;
      this._zoneCoordinatorState = zoneCoordinatorState;
      this._sensorControl = sensorControl;

      this._requiredEntitiesDynamic = {
        ...this._buildRequiredEntitiesFromTopology(topology),
        ...this._buildRequiredEntitiesFromSensorControl(sensorControl),
      };
      this.clearPreviousStates();
    } catch (error) {
      this._error = error;
      logger.error('RamsesFanMap: Failed to load initial state', error);
    } finally {
      this._loading = false;
      this.clearUpdateThrottle();
      this._scheduleRender(true);
    }
  }

  _escapeHtml(value) {
    const text = value == null ? '' : String(value);
    return text
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  _asList(value) {
    if (Array.isArray(value)) {
      return value;
    }
    return [];
  }

  _asObject(value) {
    if (value && typeof value === 'object' && !Array.isArray(value)) {
      return value;
    }
    return {};
  }

  _getEntitySummary(entityId) {
    if (!entityId || typeof entityId !== 'string') {
      return { text: '—', stateClass: 'muted', tooltip: '' };
    }

    const st = this._hass?.states?.[entityId];
    if (!st) {
      return { text: 'missing', stateClass: 'muted', tooltip: entityId };
    }

    const raw = st.state;
    const unavailable = raw === 'unknown' || raw === 'unavailable';
    if (unavailable) {
      return { text: raw, stateClass: 'muted', tooltip: entityId };
    }

    const unit = st.attributes?.unit_of_measurement;
    const valueText = unit ? `${raw} ${unit}` : String(raw);
    const lastChanged = st.last_changed ? `last_changed: ${st.last_changed}` : '';

    return {
      text: valueText,
      stateClass: 'ok',
      tooltip: [entityId, lastChanged].filter((v) => v).join('\n'),
    };
  }

  _getCoverSummary(entityId) {
    if (!entityId || typeof entityId !== 'string') {
      return { text: '—', stateClass: 'muted', tooltip: '' };
    }

    const st = this._hass?.states?.[entityId];
    if (!st) {
      return { text: 'missing', stateClass: 'muted', tooltip: entityId };
    }

    const raw = st.state;
    const unavailable = raw === 'unknown' || raw === 'unavailable';
    if (unavailable) {
      return { text: raw, stateClass: 'muted', tooltip: entityId };
    }

    const pos = st.attributes?.current_position;
    const valueText = typeof pos === 'number' ? `${pos} %` : String(raw);
    const lastChanged = st.last_changed ? `last_changed: ${st.last_changed}` : '';

    return {
      text: valueText,
      stateClass: 'ok',
      tooltip: [entityId, lastChanged].filter((v) => v).join('\n'),
    };
  }

  _renderCoverLine(label, entityId) {
    if (!entityId || typeof entityId !== 'string') {
      return '';
    }
    const summary = this._getCoverSummary(entityId);
    const labelEsc = this._escapeHtml(label);
    const entityEsc = this._escapeHtml(entityId);
    const valueEsc = this._escapeHtml(summary.text);
    const tooltipEsc = this._escapeHtml(summary.tooltip);

    return `
      <div class="sensor-line" title="${tooltipEsc}">
        <span class="sensor-k">${labelEsc}</span>
        <span class="sensor-v ${summary.stateClass}">${valueEsc}</span>
        <span class="sensor-e"><code>${entityEsc}</code></span>
      </div>
    `;
  }

  _renderEntityLine(label, entityId) {
    if (!entityId || typeof entityId !== 'string') {
      return '';
    }
    const summary = this._getEntitySummary(entityId);
    const labelEsc = this._escapeHtml(label);
    const entityEsc = this._escapeHtml(entityId);
    const valueEsc = this._escapeHtml(summary.text);
    const tooltipEsc = this._escapeHtml(summary.tooltip);

    return `
      <div class="sensor-line" title="${tooltipEsc}">
        <span class="sensor-k">${labelEsc}</span>
        <span class="sensor-v ${summary.stateClass}">${valueEsc}</span>
        <span class="sensor-e"><code>${entityEsc}</code></span>
      </div>
    `;
  }

  _renderAreaSensorsForZone(zone) {
    const zoneId = String(zone?.zone_id || '').trim();
    const areas = Array.isArray(zone?.areas) ? zone.areas : null;
    const sensors = this._asList(this._sensorControl?.area_sensors);

    const filtered = sensors.filter((s) => {
      if (!s || typeof s !== 'object') {
        return false;
      }
      if (areas && areas.length) {
        return areas.includes(s.area_id);
      }
      return String(s.zone_id || '').trim() === zoneId;
    });

    if (!filtered.length) {
      return '<span class="muted">—</span>';
    }

    const rows = filtered.map((s) => {
      const areaId = this._escapeHtml(s?.area_id || '');
      const enabled = s?.enabled === false ? 'no' : 'yes';

      const tempEntity = s?.temperature_entity;
      const humEntity = s?.humidity_entity;
      const co2Entity = s?.co2_entity;

      const lines = [
        this._renderEntityLine('T', tempEntity),
        this._renderEntityLine('H', humEntity),
        this._renderEntityLine('CO₂', co2Entity),
      ].filter((v) => v).join('');

      return `
        <div class="area-sensor-block">
          <div class="area-sensor-meta">
            <span><b>${areaId || 'area'}</b></span>
            <span class="muted">en: ${this._escapeHtml(enabled)}</span>
          </div>
          ${lines || '<span class="muted">—</span>'}
        </div>
      `;
    }).join('');

    return `<div class="area-sensors">${rows}</div>`;
  }

  _renderAreaSensorsAll() {
    const sensors = this._asList(this._sensorControl?.area_sensors);
    if (!sensors.length) {
      return '<div class="placeholder">No area sensors configured</div>';
    }

    const sorted = [...sensors].sort((a, b) => {
      const az = String(a?.zone_id || '');
      const bz = String(b?.zone_id || '');
      if (az !== bz) return az.localeCompare(bz);
      const aa = String(a?.area_id || '');
      const ba = String(b?.area_id || '');
      if (aa !== ba) return aa.localeCompare(ba);
      return 0;
    });

    return `
      <table class="table">
        <thead>
          <tr>
            <th>Zone</th>
            <th>Area</th>
            <th>Enabled</th>
            <th>Temperature</th>
            <th>Humidity</th>
            <th>CO₂</th>
          </tr>
        </thead>
        <tbody>
          ${sorted.map((s) => {
            const zoneId = this._escapeHtml(s?.zone_id || '');
            const areaId = this._escapeHtml(s?.area_id || '');
            const enabled = s?.enabled === false ? 'no' : 'yes';

            const t = this._getEntitySummary(s?.temperature_entity)?.text;
            const h = this._getEntitySummary(s?.humidity_entity)?.text;
            const c = this._getEntitySummary(s?.co2_entity)?.text;

            return `
              <tr>
                <td><code>${zoneId}</code></td>
                <td>${areaId}</td>
                <td>${this._escapeHtml(enabled)}</td>
                <td>${this._escapeHtml(t || '—')}</td>
                <td>${this._escapeHtml(h || '—')}</td>
                <td>${this._escapeHtml(c || '—')}</td>
              </tr>
            `;
          }).join('')}
        </tbody>
      </table>
    `;
  }

  _renderTopology() {
    const zones = this._asList(this._topology?.zones);
    const remoteBindings = this._asList(this._topology?.remote_bindings);
    const remoteBindingIds = this._asList(this._topology?.remote_binding_ids);

    const runtimeRemId = this._remoteBindings?.rem_id;
    const runtimeRemIdText = runtimeRemId ? this._escapeHtml(runtimeRemId) : '';

    const zonesHtml = zones.length
      ? `
          <table class="table">
            <thead>
              <tr>
                <th>Zone</th>
                <th>Type</th>
                <th>Valves</th>
                <th>Areas / Area sensors</th>
              </tr>
            </thead>
            <tbody>
              ${zones.map((zone) => {
                const zoneId = this._escapeHtml(zone?.zone_id || '');
                const type = this._escapeHtml(zone?.type || zone?.source_type || '');
                const inlet = zone?.inlet_valve_entity;
                const outlet = zone?.outlet_valve_entity;

                const valvesText = [
                  this._renderCoverLine('in', inlet),
                  this._renderCoverLine('out', outlet),
                ].filter((v) => v).join('') || '<span class="muted">—</span>';

                const areaSensorsText = this._renderAreaSensorsForZone(zone);

                return `
                  <tr>
                    <td><code>${zoneId}</code></td>
                    <td class="small">${type || '—'}</td>
                    <td>${valvesText}</td>
                    <td>${areaSensorsText}</td>
                  </tr>
                `;
              }).join('')}
            </tbody>
          </table>
        `
      : '<div class="placeholder">No configured zones</div>';

    const configuredRemsText = remoteBindingIds.length
      ? remoteBindingIds.map((remId) => `<code>${this._escapeHtml(remId)}</code>`).join(' ')
      : '—';

    const remDetails = remoteBindings.length
      ? `<details class="details" data-key="configured_rems"><summary>Configured REM entries</summary><pre class="json">${this._escapeHtml(JSON.stringify(remoteBindings, null, 2))}</pre></details>`
      : '';

    const runtimeRemText = runtimeRemIdText
      ? `<code>${runtimeRemIdText}</code>`
      : '—';

    return `
      <div class="kv">
        <div class="kv-row"><div class="kv-k">Configured REM(s)</div><div class="kv-v">${configuredRemsText}</div></div>
        <div class="kv-row"><div class="kv-k">Runtime bound REM</div><div class="kv-v">${runtimeRemText}</div></div>
        <div class="kv-row"><div class="kv-k">Area sensors</div><div class="kv-v">${this._escapeHtml(String(this._asList(this._sensorControl?.area_sensors).length))}</div></div>
      </div>
      ${remDetails}
      ${zonesHtml}
      <details class="details" data-key="all_area_sensors">
        <summary>All area sensors</summary>
        ${this._renderAreaSensorsAll()}
      </details>
    `;
  }

  _renderObservability() {
    const coordinatorEnabled = this._zoneCoordinatorState?.enabled;
    const states = this._asObject(this._zoneCoordinatorState?.states);
    const zones = this._asList(this._topology?.zone_ids);

    const enabledText = typeof coordinatorEnabled === 'boolean'
      ? (coordinatorEnabled ? 'yes' : 'no')
      : '—';

    const zonesHtml = zones.length
      ? `
        <table class="table">
          <thead>
            <tr>
              <th>Zone</th>
              <th>Position</th>
              <th>Available</th>
              <th>Source</th>
              <th>Reason</th>
            </tr>
          </thead>
          <tbody>
            ${zones.map((zoneIdRaw) => {
              const zoneId = String(zoneIdRaw || '');
              const state = states?.[zoneId] || {};
              const position = state?.position;
              const available = state?.available;
              const source = state?.source;
              const reason = state?.reason;
              const positionText = (typeof position === 'number') ? String(position) : '—';
              const availableText = (typeof available === 'boolean') ? (available ? 'yes' : 'no') : '—';

              return `
                <tr>
                  <td><code>${this._escapeHtml(zoneId)}</code></td>
                  <td>${this._escapeHtml(positionText)}</td>
                  <td>${this._escapeHtml(availableText)}</td>
                  <td class="small">${this._escapeHtml(source || '—')}</td>
                  <td class="small">${this._escapeHtml(reason || '—')}</td>
                </tr>
              `;
            }).join('')}
          </tbody>
        </table>
      `
      : '<div class="placeholder">No zones to observe</div>';

    const rawStateDetails = this._zoneCoordinatorState
      ? `<details class="details" data-key="raw_coordinator_state"><summary>Raw coordinator state</summary><pre class="json">${this._escapeHtml(JSON.stringify(this._zoneCoordinatorState, null, 2))}</pre></details>`
      : '';

    return `
      <div class="kv">
        <div class="kv-row"><div class="kv-k">Coordinator enabled</div><div class="kv-v">${this._escapeHtml(enabledText)}</div></div>
      </div>
      ${zonesHtml}
      ${rawStateDetails}
    `;
  }

  _renderTestBench() {
    const zones = this._asList(this._topology?.zones);
    const armed = this._testBenchArmed === true;
    const last = this._testBenchLastAction
      ? `<div class="small muted">last: ${this._escapeHtml(this._testBenchLastAction)}</div>`
      : '';

    const zonesHtml = zones.length
      ? `
        <table class="table">
          <thead>
            <tr>
              <th>Zone</th>
              <th>Status</th>
              <th>(simulate) Demand</th>
              <th>Valves manual</th>
            </tr>
          </thead>
          <tbody>
            ${zones.map((zone) => {
              const zoneId = this._escapeHtml(zone?.zone_id || '');
              const demandDiag = this._getZoneDemandDiagnostics(zone?.zone_id);
              const statusText = demandDiag
                ? (demandDiag.anyDemand ? 'ON' : 'off')
                : '—';
              const statusClass = demandDiag
                ? (demandDiag.anyDemand ? 'pill pill-on' : 'pill pill-off')
                : 'pill pill-unknown';
              const manualText = demandDiag?.manualPresent
                ? ` <span class="small muted">(manual: ${demandDiag.manualDemand ? 'yes' : 'no'})</span>`
                : '';
              return `
                <tr>
                  <td><code>${zoneId}</code></td>
                  <td><span class="${statusClass}">${statusText}</span>${manualText}</td>
                  <td>
                    <button class="btn danger-btn" data-tb="set_zone_demand" data-zone-id="${zoneId}" data-has-demand="true" ${armed ? '' : 'disabled'}>Yes</button>
                    <button class="btn danger-btn" data-tb="set_zone_demand" data-zone-id="${zoneId}" data-has-demand="false" ${armed ? '' : 'disabled'}>No</button>
                    <button class="btn danger-btn" data-tb="clear_zone_demand" data-zone-id="${zoneId}" ${armed ? '' : 'disabled'}>Auto</button>
                  </td>
                  <td>
                    <button class="btn danger-btn" data-tb="force_zone_ventilation" data-zone-id="${zoneId}" data-state="open" ${armed ? '' : 'disabled'}>Open</button>
                    <button class="btn danger-btn" data-tb="force_zone_ventilation" data-zone-id="${zoneId}" data-state="min" ${armed ? '' : 'disabled'}>Close</button>
                    <div class="small muted">set valves manual</div>
                  </td>
                </tr>
              `;
            }).join('')}
          </tbody>
        </table>
      `
      : '<div class="placeholder">No zones available</div>';

    return `
      <div class="kv">
        <div class="kv-row">
          <div class="kv-k">Arm test bench</div>
          <div class="kv-v">
            <label class="arm">
              <input id="armTestBench" type="checkbox" ${armed ? 'checked' : ''} />
              <span>Enable dangerous actions</span>
            </label>
            ${last}
          </div>
        </div>
      </div>

      <div class="actions">
        <button id="tbCalibrateValves" class="btn danger-btn" ${armed ? '' : 'disabled'}>Calibrate all valves</button>
      </div>

      ${zonesHtml}
    `;
  }

  _attachTestBenchHandlers() {
    const arm = this.shadowRoot?.getElementById('armTestBench');
    if (arm) {
      arm.onchange = (e) => {
        const checked = Boolean(e?.target?.checked);
        this._testBenchArmed = checked;
        this.clearUpdateThrottle();
        this._scheduleRender(true);
      };
    }

    const deviceIdRaw = this._config?.device_id;
    if (!deviceIdRaw) {
      return;
    }

    const deviceId = String(deviceIdRaw).replace(/_/g, ':').trim();
    if (!deviceId) {
      return;
    }

    const calibrate = this.shadowRoot?.getElementById('tbCalibrateValves');
    if (calibrate) {
      calibrate.onclick = async (e) => {
        e.preventDefault();
        e.stopPropagation();
        if (!this._testBenchArmed) {
          return;
        }
        const msg = `Calibrate all valves for ${deviceId}?\n\nThis may take several minutes and will move valves.`;
        if (!window.confirm(msg)) {
          return;
        }
        this._testBenchLastAction = `calibrate_all_valves @ ${new Date().toISOString()}`;
        await this._withElementFeedback(calibrate, async () => {
          await callService(this._hass, 'ramses_extras', 'calibrate_all_valves', { device_id: deviceId });
        }, 4000);

        await this._refreshCoordinatorState();
      };
    }

    const zoneButtons = this.shadowRoot?.querySelectorAll('button[data-tb]');
    zoneButtons?.forEach((btn) => {
      btn.onclick = async (e) => {
        e.preventDefault();
        e.stopPropagation();
        if (!this._testBenchArmed) {
          return;
        }

        const action = btn.getAttribute('data-tb');
        const zoneId = btn.getAttribute('data-zone-id');
        if (!action || !zoneId) {
          return;
        }

        let service = null;
        const data = { device_id: deviceId, zone_id: zoneId };

        if (action === 'set_zone_demand') {
          service = 'set_zone_demand';
          data.has_demand = btn.getAttribute('data-has-demand') === 'true';
        } else if (action === 'clear_zone_demand') {
          service = 'clear_zone_demand';
        } else if (action === 'force_zone_ventilation') {
          service = 'force_zone_ventilation';
          data.state = btn.getAttribute('data-state') || 'off';
        } else {
          return;
        }

        if (!window.confirm(`Run ${service} for ${deviceId} zone ${zoneId}?`)) {
          return;
        }

        this._testBenchLastAction = `${service}(${zoneId}) @ ${new Date().toISOString()}`;
        await this._withElementFeedback(btn, async () => {
          await callService(this._hass, 'ramses_extras', service, data);
          if (service === 'set_zone_demand' || service === 'clear_zone_demand') {
            await callService(this._hass, 'ramses_extras', 'run_zone_actuation', { device_id: deviceId });
          }
        });

        await this._refreshCoordinatorState();
      };
    });
  }

  _renderContent() {
    const openKeys = this._captureOpenDetailsKeys();

    if (!this._domInitialized) {
      this._initializeDOM();
      this._domInitialized = true;
    }

    const container = this.shadowRoot?.getElementById('cardContent');
    if (!container) {
      return;
    }

    const topologyHtml = this._topology ? this._renderTopology() : '<div class="placeholder">No data yet</div>';
    const observabilityHtml = this._zoneCoordinatorState
      ? this._renderObservability()
      : '<div class="placeholder">No data yet</div>';

    const errorText = this._error
      ? this._escapeHtml(this._error?.message || this._error?.toString?.() || String(this._error))
      : '';

    container.innerHTML = `
      <div class="section">
        <div class="title">FAN Map</div>
        <div class="subtitle">device_id: <code>${this.config?.device_id || ''}</code></div>
        <div class="actions">
          <button id="refresh" class="btn" ${this._loading ? 'disabled' : ''}>Refresh</button>
          ${this._loading ? '<span class="status">Loading…</span>' : ''}
        </div>
        ${errorText ? `<div class="error">${errorText}</div>` : ''}
      </div>

      <div class="section">
        <div class="section-header">Topology</div>
        ${topologyHtml}
        ${this._topology ? `<details class="details" data-key="raw_topology"><summary>Raw topology</summary><pre class="json">${this._escapeHtml(JSON.stringify(this._topology, null, 2))}</pre></details>` : ''}
      </div>

      <div class="section">
        <div class="section-header">Observability</div>
        ${observabilityHtml}
      </div>

      <div class="section danger">
        <div class="section-header">Test bench</div>
        ${this._renderTestBench()}
      </div>
    `;

    const refreshButton = this.shadowRoot?.getElementById('refresh');
    if (refreshButton) {
      refreshButton.onclick = () => this._loadInitialState();
    }

    this._attachTestBenchHandlers();
    this._restoreOpenDetailsKeys(openKeys);
  }

  _initializeDOM() {
    this.shadowRoot.innerHTML = `
      <style>
        ha-card {
          padding: 16px;
        }

        .title {
          font-size: 18px;
          font-weight: 600;
          margin-bottom: 4px;
        }

        .subtitle {
          color: var(--secondary-text-color);
          font-size: 12px;
          margin-bottom: 12px;
        }

        .actions {
          display: flex;
          align-items: center;
          gap: 10px;
          margin-bottom: 8px;
        }

        .btn {
          background: var(--primary-color);
          color: var(--text-primary-color, #fff);
          border: none;
          border-radius: 4px;
          padding: 6px 10px;
          cursor: pointer;
          font-size: 12px;
        }

        .btn[disabled] {
          opacity: 0.6;
          cursor: not-allowed;
        }

        .status {
          color: var(--secondary-text-color);
          font-size: 12px;
        }

        .error {
          color: var(--error-color);
          font-size: 12px;
          margin-top: 8px;
          white-space: pre-wrap;
        }

        .section {
          border-top: 1px solid var(--divider-color);
          padding-top: 12px;
          margin-top: 12px;
        }

        .section:first-child {
          border-top: none;
          padding-top: 0;
          margin-top: 0;
        }

        .section-header {
          font-weight: 600;
          margin-bottom: 6px;
        }

        .placeholder {
          color: var(--secondary-text-color);
          font-size: 13px;
        }

        .kv {
          display: grid;
          grid-template-columns: 1fr;
          gap: 6px;
          margin-bottom: 10px;
        }

        .kv-row {
          display: grid;
          grid-template-columns: 160px 1fr;
          gap: 10px;
        }

        .kv-k {
          color: var(--secondary-text-color);
          font-size: 12px;
        }

        .kv-v {
          font-size: 12px;
        }

        .table {
          width: 100%;
          border-collapse: collapse;
          font-size: 12px;
        }

        .table th,
        .table td {
          border-bottom: 1px solid var(--divider-color);
          padding: 6px 8px;
          text-align: left;
          vertical-align: top;
        }

        .table thead th {
          font-weight: 600;
          color: var(--primary-text-color);
        }

        .small {
          font-size: 11px;
          color: var(--secondary-text-color);
        }

        .muted {
          color: var(--secondary-text-color);
        }

        .sensor-line {
          display: grid;
          grid-template-columns: 18px 90px 1fr;
          gap: 8px;
          align-items: baseline;
          line-height: 1.3;
        }

        .sensor-k {
          font-weight: 600;
          color: var(--secondary-text-color);
        }

        .sensor-v.ok {
          color: var(--primary-text-color);
        }

        .sensor-v.muted {
          color: var(--secondary-text-color);
        }

        .sensor-e {
          justify-self: start;
          overflow: hidden;
          text-overflow: ellipsis;
        }

        .area-sensors {
          display: grid;
          grid-template-columns: 1fr;
          gap: 10px;
        }

        .area-sensor-block {
          border: 1px solid var(--divider-color);
          border-radius: 6px;
          padding: 8px;
        }

        .area-sensor-meta {
          display: flex;
          flex-wrap: wrap;
          gap: 10px;
          font-size: 12px;
          margin-bottom: 6px;
        }

        .details {
          margin: 8px 0;
        }

        details > summary {
          cursor: pointer;
          font-size: 12px;
          color: var(--secondary-text-color);
          margin-bottom: 6px;
        }

        details > summary.section-header {
          font-size: 14px;
          color: inherit;
          margin-bottom: 8px;
        }

        .test-bench {
          margin: 0;
        }

        .danger .section-header {
          color: var(--error-color);
        }

        .danger-btn {
          background: var(--error-color);
        }

        .arm {
          display: inline-flex;
          gap: 8px;
          align-items: center;
          font-size: 12px;
        }

        .btn.loading {
          opacity: 0.7;
        }

        .btn.success {
          outline: 2px solid rgba(0, 128, 0, 0.4);
        }

        .btn.error {
          outline: 2px solid rgba(255, 0, 0, 0.4);
        }

        .pill {
          display: inline-block;
          padding: 2px 8px;
          border-radius: 999px;
          font-size: 11px;
          font-weight: 600;
          border: 1px solid var(--divider-color);
          line-height: 1.3;
        }

        .pill-on {
          background: rgba(0, 128, 0, 0.15);
          color: var(--primary-text-color);
        }

        .pill-off {
          background: rgba(128, 128, 128, 0.10);
          color: var(--secondary-text-color);
        }

        .pill-unknown {
          background: rgba(128, 128, 128, 0.05);
          color: var(--secondary-text-color);
        }

        .json {
          font-family: var(--code-font-family, monospace);
          font-size: 12px;
          margin: 0;
          padding: 8px;
          border: 1px solid var(--divider-color);
          border-radius: 6px;
          background: rgba(0, 0, 0, 0.04);
          overflow: auto;
          max-height: 280px;
        }

        code {
          font-family: var(--code-font-family, monospace);
          font-size: 12px;
        }
      </style>

      <ha-card>
        <div id="cardContent"></div>
      </ha-card>
    `;
  }
}

const ExistingRamsesFanMap = customElements.get('ramses-fan-map');
if (!ExistingRamsesFanMap) {
  customElements.define('ramses-fan-map', RamsesFanMap);
}

RamsesFanMap.register();
