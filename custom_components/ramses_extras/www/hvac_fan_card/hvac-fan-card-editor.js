// hvac-fan-card-editor.js
class HvacFanCardEditor extends HTMLElement {
  constructor() {
    super();
    this._config = {};
    this._hass = null;
    this._initialized = false;
  }

  connectedCallback() {
    this._initialized = true;
    console.log('HvacFanCardEditor connected');
  }

  setConfig(config) {
    console.log('HvacFanCardEditor setConfig called with:', config);
    this._config = config ? JSON.parse(JSON.stringify(config)) : {};
    this._updateContent();
  }

  set hass(hass) {
    console.log('HvacFanCardEditor hass set');
    this._hass = hass;
    if (this._config && this._initialized) {
      this._updateContent();
    }
  }

  _updateContent() {
    console.log('=== HvacFanCardEditor _updateContent Debug ===');
    console.log('HASS available:', !!this._hass);
    console.log('Config available:', !!this._config);

    if (!this._hass || !this._config) {
      console.log('Missing hass or config, showing loading message');
      this.innerHTML = '<div>Loading configuration...</div>';
      return;
    }

    console.log('✅ Both hass and config available, proceeding with render');

    // Get available Ramses RF FAN devices only
    const ramsesDevices = this._getRamsesDevices();
    console.log('Found Ramses RF FAN devices:', ramsesDevices);

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
          <label for="device_id">FAN Device ID *</label>
          <select id="device_id" class="config-input" required>
            <option value="">Select a Ramses RF FAN...</option>
            ${ramsesDevices.map(device => `<option value="${device.id}" ${this._config.device_id === device.id ? 'selected' : ''}>${device.id} (${device.name})</option>`).join('')}
            ${ramsesDevices.length === 0 ? '<option disabled>No Ramses RF FAN devices found</option>' : ''}
          </select>
          <small class="form-help">Select the Ramses RF FAN device ID</small>
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

    console.log('✅ Card editor HTML generated suRFessfully');
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
    console.log('=== Finding Ramses RF FAN devices ===');

    if (!this._hass) {
      console.log('❌ No Home Assistant data available');
      return [];
    }

    const fanDevices = [];

    // Check device registry for FAN devices
    if (this._hass.devices) {
      Object.values(this._hass.devices).forEach(device => {
        // Look for devices with fan in name or model
        if (device.name?.toLowerCase().includes('fan') ||
            device.model?.toLowerCase().includes('fan') ||
            device.name?.toLowerCase().includes('ventilation')) {

          // Verify device has fan-related entities
          const allEntities = Object.keys(this._hass.states);
          const fanEntities = allEntities.filter(entityId => {
            const entityName = entityId.toLowerCase();
            const deviceNameLower = (device.name || '').toLowerCase();
            const deviceModelLower = (device.model || '').toLowerCase();

            return entityName.includes('fan') ||
                   entityName.includes('ventilator') ||
                   entityName.includes(deviceModelLower.replace(/[^a-z0-9]/g, '')) ||
                   entityName.includes(deviceNameLower.replace(/[^a-z0-9]/g, ''));
          });

          const hasFanCapabilities = fanEntities.some(entity =>
            entity.includes('_fan_info') ||
            entity.includes('_fan_mode') ||
            entity.includes('_fan_speed') ||
            (entity.includes('_fan_') && entity.includes('_temp'))
          );

          if (hasFanCapabilities) {
            // Extract clean device ID from device name
            let deviceId = device.id;
            if (device.name && device.name.includes(':')) {
              const nameParts = device.name.split(' ');
              const idMatch = nameParts.find(part => part.includes(':'));
              if (idMatch) {
                deviceId = idMatch;
              }
            }

            fanDevices.push({
              id: deviceId,
              name: `FAN: ${deviceId}`
            });

            console.log('✅ Found FAN device:', device.name, '→', deviceId);
          }
        }
      });
    }

    console.log('🎯 Found', fanDevices.length, 'FAN devices');
    return fanDevices;
  }

  _dispatchConfigChange() {
    const event = new CustomEvent('config-changed', {
      detail: { config: this._config }
    });
    this.dispatchEvent(event);
  }
}

// Register the editor
customElements.define('hvac-fan-card-editor', HvacFanCardEditor);

// Make editor globally available for Home Assistant
window.HvacFanCardEditor = HvacFanCardEditor;
