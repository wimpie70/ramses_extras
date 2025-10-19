// orcon-fan-card-editor.js
class OrconFanCardEditor extends HTMLElement {
  constructor() {
    super();
    this._config = {};
    this._hass = null;
    this._initialized = false;
  }

  connectedCallback() {
    this._initialized = true;
    console.log('OrconFanCardEditor connected');
  }

  setConfig(config) {
    console.log('OrconFanCardEditor setConfig called with:', config);
    this._config = config || {};
    this._updateContent();
  }

  set hass(hass) {
    console.log('OrconFanCardEditor hass set');
    this._hass = hass;
    if (this._config && this._initialized) {
      this._updateContent();
    }
  }

  _updateContent() {
    console.log('=== OrconFanCardEditor _updateContent Debug ===');
    console.log('HASS available:', !!this._hass);
    console.log('Config available:', !!this._config);

    if (!this._hass || !this._config) {
      console.log('Missing hass or config, showing loading message');
      this.innerHTML = '<div>Loading configuration...</div>';
      return;
    }

    console.log('✅ Both hass and config available, proceeding with render');

    // Get available Ramses CC devices
    const ramsesDevices = this._getRamsesDevices();
    console.log('Found Ramses devices:', ramsesDevices);

    // Debug entity detection (only for entities we need)
    const inputBooleanEntities = Object.keys(this._hass.states).filter(entity =>
      entity.startsWith('input_boolean.')
    );
    console.log('Found input_boolean entities:', inputBooleanEntities);

    console.log('🔧 Generating card editor HTML...');
    console.log('🔧 Generating card editor HTML...');

    this.innerHTML = `
      <div class="card-config">
        <div class="form-group">
          <label for="device_id">Device ID *</label>
          <select id="device_id" class="config-input" required>
            <option value="">Select a Ramses CC device...</option>
            ${ramsesDevices.map(device => `<option value="${device.id}" ${this._config.device_id === device.id ? 'selected' : ''}>${device.id} (${device.name || 'Unknown'})</option>`).join('')}
            ${ramsesDevices.length === 0 ? '<option disabled>No Ramses CC devices found</option>' : ''}
          </select>
          <small class="form-help">Select the Ramses CC device ID that corresponds to your fan</small>
        </div>

        <div class="form-group">
          <label for="dehum_mode_entity">Dehumidifier Mode Entity</label>
          <select id="dehum_mode_entity" class="config-input">
            <option value="">Auto-detect (recommended)</option>
            ${Object.keys(this._hass ? this._hass.states : {})
              .filter(entity => entity.startsWith('input_boolean.'))
              .sort()
              .map(entity => `<option value="${entity}" ${this._config.dehum_mode_entity === entity ? 'selected' : ''}>${entity}</option>`)
              .join('')}
            ${!this._hass || Object.keys(this._hass.states).filter(entity => entity.startsWith('input_boolean.')).length === 0 ? '<option disabled>No input_boolean entities found - create them first</option>' : ''}
          </select>
          <small class="form-help">Input boolean entity for dehumidifier mode control</small>
        </div>

        <div class="form-group">
          <label for="dehum_active_entity">Dehumidifier Active Entity</label>
          <select id="dehum_active_entity" class="config-input">
            <option value="">Auto-detect (recommended)</option>
            ${Object.keys(this._hass ? this._hass.states : {})
              .filter(entity => entity.startsWith('input_boolean.'))
              .sort()
              .map(entity => `<option value="${entity}" ${this._config.dehum_active_entity === entity ? 'selected' : ''}>${entity}</option>`)
              .join('')}
            ${!this._hass || Object.keys(this._hass.states).filter(entity => entity.startsWith('input_boolean.')).length === 0 ? '<option disabled>No input_boolean entities found - create them first</option>' : ''}
          </select>
          <small class="form-help">Input boolean entity for dehumidifier active status</small>
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
          // background: #f0f0f0 !important;
          color: var(--primary-text-color);
          font-size: 14px;
        }

        .form-help {
          display: block;
          margin-top: 4px;
          font-size: 12px;
          color: var(--secondary-text-color);
        }
      </style>
    `;

    console.log('✅ Card editor HTML generated successfully');
    console.log('📏 Editor dimensions:', this.offsetWidth, 'x', this.offsetHeight);

    // Add event listeners after content is set
    setTimeout(() => {
      const deviceIdSelect = this.querySelector('#device_id');
      const dehumModeSelect = this.querySelector('#dehum_mode_entity');
      const dehumActiveSelect = this.querySelector('#dehum_active_entity');

      if (deviceIdSelect) {
        deviceIdSelect.addEventListener('change', (e) => {
          this._config.device_id = e.target.value;
          this._dispatchConfigChange();
        });
      }

      if (dehumModeSelect) {
        dehumModeSelect.addEventListener('change', (e) => {
          this._config.dehum_mode_entity = e.target.value;
          this._dispatchConfigChange();
        });
      }

      if (dehumActiveSelect) {
        dehumActiveSelect.addEventListener('change', (e) => {
          this._config.dehum_active_entity = e.target.value;
          this._dispatchConfigChange();
        });
      }
    }, 0);
  }

  _getRamsesDevices() {
    console.log('=== _getRamsesDevices Debug ===');
    console.log('HASS available in _getRamsesDevices:', !!this._hass);

    if (!this._hass) {
      console.log('No HASS available, returning empty array');
      return [];
    }

    // Get all Ramses CC entities and extract device IDs
    const ramsesEntities = Object.keys(this._hass.states).filter(entity =>
      entity.startsWith('sensor.') && entity.includes('_fan')
    );
    console.log('Found Ramses entities:', ramsesEntities);

    const deviceIds = new Set();

    ramsesEntities.forEach(entity => {
      const entityBase = entity.replace('sensor.', '');
      let deviceId = '';

      if (entityBase.includes('_fan_info')) {
        deviceId = entityBase.replace('_fan_info', '');
      } else if (entityBase.includes('_fan_')) {
        deviceId = entityBase.split('_fan_')[0];
      } else if (entityBase.includes('_')) {
        const parts = entityBase.split('_');
        if (parts.length === 2 && parts.every(part => /^\d+$/.test(part))) {
          deviceId = entityBase;
        } else {
          deviceId = parts.slice(0, -1).join('_');
        }
      } else {
        deviceId = entityBase;
      }

      if (deviceId) {
        deviceIds.add(deviceId);
      }
    });

    const devices = Array.from(deviceIds).map(id => ({
      id: id.replace(/_/g, ':'), // Normalize to colon format
      name: `Device ${id.replace(/_/g, ':')}`
    }));

    console.log('Extracted devices:', devices);
    return devices;
  }

  _dispatchConfigChange() {
    const event = new CustomEvent('config-changed', {
      detail: { config: this._config }
    });
    this.dispatchEvent(event);
  }
}

// Register the editor
customElements.define('orcon-fan-card-editor', OrconFanCardEditor);

// Make editor globally available for Home Assistant
window.OrconFanCardEditor = OrconFanCardEditor;
