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

      this._topology = topology;
      this._remoteBindings = remoteBindings;
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

  _renderContent() {
    if (!this._domInitialized) {
      this._initializeDOM();
      this._domInitialized = true;
    }

    const container = this.shadowRoot?.getElementById('cardContent');
    if (!container) {
      return;
    }

    const topologyJson = this._topology ? this._escapeHtml(JSON.stringify(this._topology, null, 2)) : '';
    const remoteBindingsJson = this._remoteBindings
      ? this._escapeHtml(JSON.stringify(this._remoteBindings, null, 2))
      : '';

    const errorText = this._error
      ? this._escapeHtml(this._error?.message || this._error?.toString?.() || String(this._error))
      : '';

    container.innerHTML = `
      <div class="section">
        <div class="title">FAN Map</div>
        <div class="subtitle">device_id: <code>${this.config?.device_id || ''}</code></div>
        <div class="actions">
          <button id="refresh" class="btn" ?disabled=${this._loading}>Refresh</button>
          ${this._loading ? '<span class="status">Loading…</span>' : ''}
        </div>
        ${errorText ? `<div class="error">${errorText}</div>` : ''}
      </div>

      <div class="section">
        <div class="section-header">Topology</div>
        ${topologyJson ? `<pre class="json">${topologyJson}</pre>` : '<div class="placeholder">No data yet</div>'}
      </div>

      <div class="section">
        <div class="section-header">Observability</div>
        ${remoteBindingsJson ? `<pre class="json">${remoteBindingsJson}</pre>` : '<div class="placeholder">No data yet</div>'}
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
