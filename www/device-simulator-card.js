// Part of the Ramses Extra integration
// Device Simulator UI Card for Home Assistant Lovelace

import { LitElement, html, css } from 'https://unpkg.com/lit@2.8.0/index.js?module';

class DeviceSimulatorCard extends LitElement {
  static get styles() {
    return css`
      :host {
        display: block;
        padding: 16px;
        background: var(--card-background, #fff);
        border-radius: var(--ha-card-border-radius, 12px);
        box-shadow: var(--ha-card-box-shadow, 0 2px 4px rgba(0, 0, 0, 0.1));
      }
      .tabs {
        display: flex;
        gap: 8px;
        margin-bottom: 16px;
      }
      .tab {
        padding: 8px 16px;
        background: var(--primary-color);
        color: white;
        border: none;
        border-radius: 4px;
        cursor: pointer;
      }
      .tab.active {
        background: var(--primary-color);
      }
      .content {
        min-height: 200px;
      }
      .status {
        padding: 16px;
        background: var(--secondary-background-color);
        border-radius: 8px;
      }
      button {
        padding: 8px 16px;
        background: var(--primary-color);
        color: white;
        border: none;
        border-radius: 4px;
        cursor: pointer;
        margin: 4px;
      }
      button:disabled {
        opacity: 0.5;
        cursor: not-allowed;
      }
    `;
  }

  static get properties() {
    return {
      hass: { type: Object },
      config: { type: Object },
      activeTab: { type: String },
      status: { type: Object },
      devices: { type: Array },
      scenarios: { type: Array },
    };
  }

  constructor() {
    super();
    this.activeTab = 'profiles';
    this.status = {};
    this.devices = [];
    this.scenarios = [];
  }

  connectedCallback() {
    super.connectedCallback();
    this._loadStatus();
  }

  _loadStatus() {
    if (!this.hass) return;

    this.hass
      .callWS({
        type: 'ramses_extras/device_simulator/get_status',
      })
      .then((response) => {
        this.status = response;
        this.devices = response.devices || [];
        this.scenarios = response.scenarios || [];
      })
      .catch((error) => {
        console.error('Error loading simulator status:', error);
      });
  }

  _activateDevice(deviceId, slug) {
    this.hass
      .callService('device_simulator', 'activate_device', {
        device_id: deviceId,
        slug: slug,
      })
      .then(() => {
        this._loadStatus();
      });
  }

  _deactivateDevice(deviceId) {
    this.hass
      .callService('device_simulator', 'deactivate_device', {
        device_id: deviceId,
      })
      .then(() => {
        this._loadStatus();
      });
  }

  _renderProfilesTab() {
    return html`
      <div class="content">
        <h3>Configuration Profiles</h3>
        <button @click=${() => this._loadProfile('default')}>Load Default</button>
        <button @click=${() => this._loadProfile('minimal')}>Load Minimal</button>
        <button @click=${() => this._loadProfile('full')}>Load Full</button>
        <div class="status">
          <p>Current profile: ${this.status.current_profile || 'None'}</p>
          <p>Active devices: ${this.devices.length}</p>
        </div>
      </div>
    `;
  }

  _renderDevicesTab() {
    return html`
      <div class="content">
        <h3>Active Devices</h3>
        ${this.devices.map(
          (device) => html`
            <div class="status" style="margin: 8px 0;">
              <strong>${device.device_id}</strong> - ${device.slug}
              <button
                @click=${() =>
                  device.active
                    ? this._deactivateDevice(device.device_id)
                    : this._activateDevice(device.device_id, device.slug)}
              >
                ${device.active ? 'Deactivate' : 'Activate'}
              </button>
            </div>
          `
        )}
        ${this.devices.length === 0
          ? html` <p>No active devices. Activate a device to start simulation.</p> `
          : ''}
      </div>
    `;
  }

  _renderScenariosTab() {
    return html`
      <div class="content">
        <h3>Scenarios</h3>
        <button @click=${() => this._runScenario('test')}>Run Test Scenario</button>
        <button @click=${() => this._runScenario('load_test')}>Run Load Test</button>
        <div class="status">
          <p>Running scenario: ${this.status.running_scenario || 'None'}</p>
        </div>
      </div>
    `;
  }

  _renderEventsTab() {
    return html`
      <div class="content">
        <h3>Event Log</h3>
        <div class="status">
          <p>Messages sent: ${this.status.messages_sent || 0}</p>
          <p>Messages received: ${this.status.messages_received || 0}</p>
          <p>Last activity: ${this.status.last_activity || 'Never'}</p>
        </div>
      </div>
    `;
  }

  render() {
    if (!this.hass || !this.config) {
      return html`<div>Loading...</div>`;
    }

    return html`
      <div class="tabs">
        <button
          class="tab ${this.activeTab === 'profiles' ? 'active' : ''}"
          @click=${() => (this.activeTab = 'profiles')}
        >
          Profiles
        </button>
        <button
          class="tab ${this.activeTab === 'devices' ? 'active' : ''}"
          @click=${() => (this.activeTab = 'devices')}
        >
          Devices
        </button>
        <button
          class="tab ${this.activeTab === 'scenarios' ? 'active' : ''}"
          @click=${() => (this.activeTab = 'scenarios')}
        >
          Scenarios
        </button>
        <button
          class="tab ${this.activeTab === 'events' ? 'active' : ''}"
          @click=${() => (this.activeTab = 'events')}
        >
          Events
        </button>
      </div>

      ${this.activeTab === 'profiles' ? this._renderProfilesTab() : ''}
      ${this.activeTab === 'devices' ? this._renderDevicesTab() : ''}
      ${this.activeTab === 'scenarios' ? this._renderScenariosTab() : ''}
      ${this.activeTab === 'events' ? this._renderEventsTab() : ''}
    `;
  }
}

customElements.define('device-simulator-card', DeviceSimulatorCard);

// Register card with Home Assistant
window.customCards = window.customCards || [];
window.customCards.push({
  type: 'device-simulator-card',
  name: 'Device Simulator',
  description: 'Control the RAMSES device simulator',
  preview: false,
});
