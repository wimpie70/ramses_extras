/* eslint-disable no-console */
// Hello World Card Editor - Configuration editor for the card
// Part of the Ramses Extra integration
// See https://github.com/wimpie70/ramses_extras for more information

/* eslint-disable no-undef */

// Import reusable helpers using environment-aware path constants
import {
  getAvailableDevices,
  normalizeDeviceDescriptor,
} from '../../helpers/card-services.js';

/**
 * Hello World Card Editor using HTMLElement pattern (like hvac_fan_card)
 * to avoid external dependencies like 'lit'
 */
class HelloworldEditor extends HTMLElement {
  constructor() {
    super();
    this._config = {};
    this._hass = null;
    this._initialized = false;
    this._devicesFetched = false; // Track if we've already fetched devices

    console.log('HelloworldEditor: Constructor called');
  }

  connectedCallback() {
    this._initialized = true;
    console.log('HelloworldEditor connected');
  }

  disconnectedCallback() {
    console.log('🧹 HelloworldEditor: Cleaning up editor component');
    this._devicesFetched = false; // Reset for next connection
  }

  setConfig(config) {
    console.log('HelloworldEditor setConfig called with:', config);
    this._config = config ? JSON.parse(JSON.stringify(config)) : {};
    this._updateContent();
  }

  set hass(hass) {
    console.log('HelloworldEditor hass set');
    this._hass = hass;
    if (this._config && this._initialized) {
      this._updateContent();
    }
  }

  _updateContent() {
    console.log('=== HelloworldEditor _updateContent Debug ===');
    console.log('HASS available:', !!this._hass);
    console.log('Config available:', !!this._config);

    if (!this._hass || !this._config) {
      console.log('Missing hass or config, showing loading message');
      this.innerHTML = '<div style="padding: 16px;">Loading Hello World Card Editor...</div>';
      return;
    }

    console.log('✅ Both hass and config available, proceeding with render');

    // Only fetch devices once per component instance
    if (!this._devicesFetched) {
      console.log('🔄 HelloworldEditor: Fetching devices for first time');
      this._devicesFetched = true;

      // Get available Ramses RF devices using WebSocket command
      this._getRamsesDevices().then(ramsesDevices => {
        console.log('Found Ramses RF devices:', ramsesDevices);

        // Show the complete editor interface
        this._renderEditor(ramsesDevices);
      }).catch(error => {
        console.error('❌ Error getting Ramses devices:', error);
        // Render editor with empty device list - no fallback
        this._renderEditor([]);
      });
    } else {
      console.log('📦 HelloworldEditor: Using cached devices (no new fetch needed)');
      // If devices were already fetched, re-render with the same devices
      // The cached devices will be reused from the card-services.js cache
      this._getRamsesDevices().then(ramsesDevices => {
        this._renderEditor(ramsesDevices);
      }).catch(error => {
        console.error('❌ Error getting cached Ramses devices:', error);
        this._renderEditor([]);
      });
    }
  }

  _renderEditor(ramsesDevices) {
    const deviceOptions = ramsesDevices.length
      ? ramsesDevices
        .map((device) => {
          const selectedAttr = this._config.device_id === device.id ? 'selected' : '';
          return `<option value="${device.id}" ${selectedAttr}>${device.label}</option>`;
        })
        .join('')
      : '<option disabled>No Ramses RF devices found</option>';

    // Show the complete editor interface
    this.innerHTML = `
      <div class="card-config">
        <div class="form-group">
          <label for="device_id">Device ID *</label>
          <select id="device_id" class="config-input" required>
            <option value="">Select a device...</option>
            ${deviceOptions}
          </select>
          <small class="form-help">Select the Ramses RF device for the Hello World switch</small>
          <div class="form-note">You may need to enable the device in the Ramses Extras configuration.</div>
        </div>

        <div class="form-group">
          <label for="name">Card Name</label>
          <input type="text" id="name" class="config-input" value="${this._config.name || 'Hello World Switch'}" placeholder="Enter card name">
          <small class="form-help">Custom name for the card display</small>
        </div>

        <div class="form-group">
          <label>Display Options</label>
          <div class="checkbox-group">
            <label>
              <input type="checkbox" id="show_status" ${this._config.show_status !== false ? 'checked' : ''}>
              Show status text
            </label>
            <label>
              <input type="checkbox" id="compact_view" ${this._config.compact_view ? 'checked' : ''}>
              Compact view
            </label>
            <label>
              <input type="checkbox" id="show_device_id_only" ${this._config.show_device_id_only ? 'checked' : ''}>
              Show device ID only
            </label>
            <label>
              <input type="checkbox" id="show_name_only" ${this._config.show_name_only ? 'checked' : ''}>
              Show name only
            </label>
          </div>
        </div>

        <div class="device-info">
          <small><strong>Current device:</strong> ${this._config.device_id || 'None selected'}</small>
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

        .checkbox-group {
          display: flex;
          flex-direction: column;
          gap: 8px;
        }

        .checkbox-group label {
          display: flex;
          align-items: center;
          margin-bottom: 0;
          font-weight: normal;
        }

        .checkbox-group input[type="checkbox"] {
          margin-right: 8px;
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

        .device-info {
          margin-top: 12px;
          padding: 8px;
          background: var(--divider-color, #f0f0f0);
          border-radius: 4px;
          font-size: 12px;
        }
      </style>
    `;

    console.log('✅ Card editor HTML generated successfully');

    // Add event listeners after content is set (with setTimeout like hvac_fan_card)
    setTimeout(() => {
      this._attachEventListeners();
    }, 0);
  }

  async _getRamsesDevices() {
    console.log('=== Finding Ramses RF devices via WebSocket ===');

    if (!this._hass) {
      console.log('❌ No Home Assistant data available');
      return [];
    }

    console.log('🔌 Getting available devices using standardized helper');

    // Use the standardized helper function
    const devices = await getAvailableDevices(this._hass);

    console.log('✅ Available devices retrieved:', devices);

    if (devices && Array.isArray(devices)) {
      const ramsesDevices = devices.map((device) => normalizeDeviceDescriptor({
        device_id: device.device_id,
        slugs: device.slugs,
        slug_label: device.slug_label,
        device_type: device.device_type,
        model: device.model,
        type: device.type,
      }));

      console.log('🎯 Found', ramsesDevices.length, 'Ramses devices via WebSocket');
      return ramsesDevices;
    } else {
      console.warn('⚠️ Invalid response format from WebSocket command');
      return [];
    }
  }

  _attachEventListeners() {
    // Add event listeners after content is set
    const deviceIdSelect = this.querySelector('#device_id');
    const nameInput = this.querySelector('#name');
    const showStatusCheckbox = this.querySelector('#show_status');
    const compactViewCheckbox = this.querySelector('#compact_view');
    const showDeviceIdOnlyCheckbox = this.querySelector('#show_device_id_only');
    const showNameOnlyCheckbox = this.querySelector('#show_name_only');

    if (deviceIdSelect) {
      deviceIdSelect.addEventListener('change', (e) => {
        this._config.device_id = e.target.value;
        this._dispatchConfigChange();
      });
    }

    if (nameInput) {
      nameInput.addEventListener('input', (e) => {
        this._config.name = e.target.value;
        this._dispatchConfigChange();
      });
    }

    if (showStatusCheckbox) {
      showStatusCheckbox.addEventListener('change', (e) => {
        this._config.show_status = e.target.checked;
        this._dispatchConfigChange();
      });
    }

    if (compactViewCheckbox) {
      compactViewCheckbox.addEventListener('change', (e) => {
        this._config.compact_view = e.target.checked;
        this._dispatchConfigChange();
      });
    }

    if (showDeviceIdOnlyCheckbox) {
      showDeviceIdOnlyCheckbox.addEventListener('change', (e) => {
        this._config.show_device_id_only = e.target.checked;
        // Uncheck show_name_only if this is checked
        if (e.target.checked && showNameOnlyCheckbox) {
          showNameOnlyCheckbox.checked = false;
          this._config.show_name_only = false;
        }
        this._dispatchConfigChange();
      });
    }

    if (showNameOnlyCheckbox) {
      showNameOnlyCheckbox.addEventListener('change', (e) => {
        this._config.show_name_only = e.target.checked;
        // Uncheck show_device_id_only if this is checked
        if (e.target.checked && showDeviceIdOnlyCheckbox) {
          showDeviceIdOnlyCheckbox.checked = false;
          this._config.show_device_id_only = false;
        }
        this._dispatchConfigChange();
      });
    }
  }

  _dispatchConfigChange() {
    const event = new CustomEvent('config-changed', {
      detail: { config: this._config }
    });
    this.dispatchEvent(event);
  }
}

// Register the editor immediately
console.log('HelloworldEditor: Starting registration process');

try {
  customElements.define('hello-world-editor', HelloworldEditor);
  console.log('HelloworldEditor: ✅ Custom element registered successfully');
} catch (error) {
  console.error('HelloworldEditor: ❌ Failed to register custom element:', error);
}

// Make editor globally available for Home Assistant
window.HelloworldEditor = HelloworldEditor;
console.log('HelloworldEditor: Made globally available');

// Export for module systems
if (typeof module !== 'undefined' && module.exports) {
  module.exports = HelloworldEditor;
}
