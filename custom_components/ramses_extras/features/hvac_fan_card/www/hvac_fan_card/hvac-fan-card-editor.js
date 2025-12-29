/* eslint-disable no-console */
// hvac-fan-card-editor.js

/* global customElements */
/* global setTimeout */
/* global CustomEvent */
/* global HTMLElement */

import {
  getAvailableDevices,
  normalizeDeviceDescriptor,
  filterDevicesBySlugs,
} from '../../helpers/card-services.js';

class HvacFanCardEditor extends HTMLElement {
  constructor() {
    super();
    this._config = {};
    this._hass = null;
    this._initialized = false;
    this._devicesFetched = false;
  }

  connectedCallback() {
    this._initialized = true;

    if (this._config && this._hass) {
      this._updateContent();
    }
  }

  setConfig(config) {
    this._config = config ? JSON.parse(JSON.stringify(config)) : {};
    this._updateContent();
  }

  set hass(hass) {
    this._hass = hass;
    if (this._config && this._initialized) {
      this._updateContent();
    }
  }

  _updateContent() {
    if (!this._hass || !this._config) {
      this.innerHTML = '<div>Loading configuration...</div>';
      return;
    }

    if (!this._devicesFetched) {
      this._devicesFetched = true;
      this._loadDevices();
    } else {
      this._loadDevices(true);
    }
  }

  async _loadDevices(fromCache = false) {
    try {
      if (!fromCache) {
        this.innerHTML = '<div>Loading HVAC Fan configuration...</div>';
      }

      const devices = await getAvailableDevices(this._hass);
      const filtered = filterDevicesBySlugs(devices, ['FAN']);
      const normalized = filtered.map((device) => normalizeDeviceDescriptor(device));

      this._renderEditor(normalized);
    } catch (error) {
      console.error('HvacFanCardEditor: Failed to load devices', error);
      this._renderEditor([]);
    }
  }

  _renderEditor(devices) {
    const deviceOptions = devices.length
      ? devices
        .map((device) => {
          const selectedAttr = this._config.device_id === device.id ? 'selected' : '';
          return `<option value="${device.id}" ${selectedAttr}>${device.label}</option>`;
        })
        .join('')
      : '<option disabled>No compatible devices found</option>';

    this.innerHTML = `
      <div class="card-config">
        <div class="form-group">
          <label for="device_id">FAN Device ID *</label>
          <select id="device_id" class="config-input" required>
            <option value="">Select a Ramses RF FAN...</option>
            ${deviceOptions}
          </select>
          <small class="form-help">Select the Ramses RF FAN device ID</small>
          <div class="form-note">You may need to enable the device in the Ramses Extras configuration. Check the Hello World settings.</div>
        </div>
      </div>

      <style>
        .card-config {
          padding: 16px;
          background: var(--card-background-color, #fff);
          border-radius: 8px;
        }

        .form-group {
          margin-bottom: 16px;
        }

        label {
          display: block;
          margin-bottom: 8px;
          font-weight: 500;
          color: var(--primary-text-color);
        }

        .config-input {
          width: 100%;
          padding: 8px 12px;
          border: 1px solid var(--divider-color);
          border-radius: 4px;
          color: var(--primary-text-color);
          font-size: 14px;
          box-sizing: border-box;
        }

        .config-input option {
          color: inherit;
        }

        .form-help {
          display: block;
          margin-top: 4px;
          font-size: 12px;
          color: var(--secondary-text-color);
        }

        .form-note {
          margin-top: 4px;
          font-size: 12px;
          color: var(--primary-text-color, #333);
        }
      </style>
    `;

    setTimeout(() => {
      const deviceIdSelect = this.querySelector('#device_id');

      if (deviceIdSelect) {
        deviceIdSelect.addEventListener('change', (e) => {
          this._config.device_id = e.target.value;
          this._dispatchConfigChange();
        });
      }
    }, 0);
  }

  _dispatchConfigChange() {
    const event = new CustomEvent('config-changed', {
      detail: { config: this._config }
    });
    this.dispatchEvent(event);
  }
}

if (!customElements.get('hvac-fan-card-editor')) {
  customElements.define('hvac-fan-card-editor', HvacFanCardEditor);
}

// Make editor globally available for Home Assistant
window.HvacFanCardEditor = HvacFanCardEditor;
