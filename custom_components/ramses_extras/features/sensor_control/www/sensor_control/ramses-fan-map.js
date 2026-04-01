/* global customElements */

import * as logger from '../../helpers/logger.js';

import { RamsesBaseCard } from '../../helpers/ramses-base-card.js';

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
  }

  getFeatureName() {
    return 'sensor_control';
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

      if (this._hass && this._config?.device_id) {
        this._loadInitialState();
      }
    }
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

      this._topology = topology;
      this._remoteBindings = remoteBindings;
      this._zoneCoordinatorState = zoneCoordinatorState;
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
                <th>Label</th>
                <th>Source</th>
                <th>Sensors</th>
                <th>Actuator</th>
              </tr>
            </thead>
            <tbody>
              ${zones.map((zone) => {
                const zoneId = this._escapeHtml(zone?.zone_id || '');
                const label = this._escapeHtml(zone?.label || '');
                const source = this._escapeHtml(zone?.source_type || '');

                const sensors = this._asObject(zone?.sensors);
                const temp = this._escapeHtml(sensors?.temperature_entity || '');
                const hum = this._escapeHtml(sensors?.humidity_entity || '');
                const co2 = this._escapeHtml(sensors?.co2_entity || '');
                const sensorsText = [
                  temp ? `T:${temp}` : '',
                  hum ? `H:${hum}` : '',
                  co2 ? `CO₂:${co2}` : '',
                ].filter((v) => v).join('<br>');

                const actuator = this._asObject(zone?.actuator);
                const actuatorEntity = this._escapeHtml(actuator?.entity_id || '');

                return `
                  <tr>
                    <td><code>${zoneId}</code></td>
                    <td>${label}</td>
                    <td>${source}</td>
                    <td class="small">${sensorsText || '—'}</td>
                    <td class="small">${actuatorEntity || '—'}</td>
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
      ? `<details class="details"><summary>Configured REM entries</summary><pre class="json">${this._escapeHtml(JSON.stringify(remoteBindings, null, 2))}</pre></details>`
      : '';

    const runtimeRemText = runtimeRemIdText
      ? `<code>${runtimeRemIdText}</code>`
      : '—';

    return `
      <div class="kv">
        <div class="kv-row"><div class="kv-k">Configured REM(s)</div><div class="kv-v">${configuredRemsText}</div></div>
        <div class="kv-row"><div class="kv-k">Runtime bound REM</div><div class="kv-v">${runtimeRemText}</div></div>
      </div>
      ${remDetails}
      ${zonesHtml}
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
      ? `<details class="details"><summary>Raw coordinator state</summary><pre class="json">${this._escapeHtml(JSON.stringify(this._zoneCoordinatorState, null, 2))}</pre></details>`
      : '';

    return `
      <div class="kv">
        <div class="kv-row"><div class="kv-k">Coordinator enabled</div><div class="kv-v">${this._escapeHtml(enabledText)}</div></div>
      </div>
      ${zonesHtml}
      ${rawStateDetails}
    `;
  }

  _renderContent() {
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
        ${this._topology ? `<details class="details"><summary>Raw topology</summary><pre class="json">${this._escapeHtml(JSON.stringify(this._topology, null, 2))}</pre></details>` : ''}
      </div>

      <div class="section">
        <div class="section-header">Observability</div>
        ${observabilityHtml}
      </div>

      <div class="section danger">
        <div class="section-header">Test bench</div>
        <div class="placeholder">(coming next) guarded actions (actuation / demand / calibrate)</div>
      </div>
    `;

    const refreshButton = this.shadowRoot?.getElementById('refresh');
    if (refreshButton) {
      refreshButton.onclick = () => this._loadInitialState();
    }
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

        .details {
          margin: 8px 0;
        }

        details > summary {
          cursor: pointer;
          font-size: 12px;
          color: var(--secondary-text-color);
          margin-bottom: 6px;
        }

        .danger .section-header {
          color: var(--error-color);
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
