

// Debug: Check if this file is being loaded
console.log('🚀 hvac-fan-card.js is being loaded!');

import { NORMAL_SVG, BYPASS_OPEN_SVG } from './airflow-diagrams.js';
import { CARD_STYLE } from './card-styles.js';
import { createCardHeader, createTopSection, createControlsSection, createCardFooter } from './templates/card-templates.js';
import { createTemplateData } from './templates/template-helpers.js';
import './hvac-fan-card-editor.js';

// Debug: Check if imports work
console.log('✅ ES6 imports loaded suRFessfully');

class HvacFanCard extends HTMLElement {
  // All fan commands in one simple object
  static get FAN_COMMANDS() {
    return {
      'request10D0': {
        code: '10D0',
        verb: 'RQ',
        payload: '00'  // Request 10D0
      },

      'away': {
        code: '22F1',
        verb: ' I',
        payload: '000007'  // Away mode
      },
      'low': {
        code: '22F1',
        verb: ' I',
        payload: '000107'  // Low speed
      },
      'medium': {
        code: '22F1',
        verb: ' I',
        payload: '000207'  // Medium speed
      },
      'high': {
        code: '22F1',
        verb: ' I',
        payload: '000307'  // High speed
      },
      'active': {
        code: '22F1',
        verb: ' I',
        payload: '000807'  // Active mode
      },
      'auto2': {
        code: '22F1',
        verb: ' I',
        payload: '000507'  // Auto mode
      },
      'boost': {
        code: '22F1',
        verb: ' I',
        payload: '000607'  // Boost mode
      },
      'disable': {
        code: '22F1',
        verb: ' I',
        payload: '000707'  // Disable mode
      },

      'filter_reset': {
        code: '10D0',
        verb: ' W',
        payload: '00FF'  // Filter reset
      },

      'high_15': {
        code: '22F3',
        verb: ' I',
        payload: '00120F03040404'  // 15 minutes timer
      },
      'high_30': {
        code: '22F3',
        verb: ' I',
        payload: '00121E03040404'  // 30 minutes timer
      },
      'high_60': {
        code: '22F3',
        verb: ' I',
        payload: '00123C03040404'  // 60 minutes timer
      },

      'bypass_close': {
        code: '22F7',
        verb: ' W',
        payload: '0000EF'  // Bypass close
      },
      'bypass_open': {
        code: '22F7',
        verb: ' W',
        payload: '00C8EF'  // Bypass open
      },
      'bypass_auto': {
        code: '22F7',
        verb: ' W',
        payload: '00FFEF'  // Bypass auto
      },

      'request31DA': {
        code: '31DA',
        verb: 'RQ',
        payload: '00'
      },
    };
  }

      // // 2411 commands (sorted by payload)
      // 'req_2411_supply_away': {
      //   code: '2411',
      //   payload: '00003D'  // Request supply away
      // },
      // 'req_2411_exhaust_away': {
      //   code: '2411',
      //   payload: '00003E'  // Request exhaust away
      // },
      // 'req_2411_filtertime': {
      //   code: '2411',
      //   payload: '000031'  // Request filter time
      // },
      // 'req_2411_moist_pos': {
      //   code: '2411',
      //   payload: '00004E'  // Request moisture position
      // },
      // 'req_2411_moist_sens': {
      //   code: '2411',
      //   payload: '000052'  // Request moisture sensitivity
      // },
      // 'req_2411_moist_overrun': {
      //   code: '2411',
      //   payload: '000058'  // Request moisture overrun
      // },
      // 'req_2411_comfort': {
      //   code: '2411',
      //   payload: '000075'  // Request comfort
      // },


  static get properties() {
    return {
      config: {},
      _hass: {},
    };
  }

  set hass(hass) {
    this._hass = hass;
    if (this.config && this.shouldUpdate()) {
      this.render();
    }
  }

  shouldUpdate() {
    if (!this._hass || !this.config) return false;

    // Check if any of our monitored entities have changed
    const entities = [
      // ramses_extras provided sensors
      this.config.indoor_abs_humid_entity,
      this.config.outdoor_abs_humid_entity,
      // ramses_cc provided sensors
      this.config.indoor_temp_entity,
      this.config.outdoor_temp_entity,
      this.config.indoor_humidity_entity,
      this.config.outdoor_humidity_entity,
      this.config.supply_temp_entity,
      this.config.exhaust_temp_entity,
      this.config.fan_speed_entity,
      this.config.fan_mode_entity,
      this.config.co2_entity,
      this.config.flow_entity,
      this.config.bypass_entity,
      this.config.dehum_mode_entity,
      this.config.dehum_active_entity,
      this.config.comfort_temp_entity,
    ].filter(Boolean);

    return entities.some(entity => {
      const oldState = this._prevStates ? this._prevStates[entity] : null;
      const newState = this._hass.states[entity];
      this._prevStates = this._prevStates || {};
      this._prevStates[entity] = newState;
      return oldState !== newState;
    });
  }

  // Method to get bound REM device via WebSocket
  async getBoundRem(deviceId) {
    if (!this._hass) {
      throw new Error('Home Assistant instance not available');
    }

    let sensor_id = 'climate.' + deviceId.replace(/:/g, '_');
    try {
      console.log('bound_rem: ', this._hass.states[sensor_id].attributes.bound_rem);
      let bound_rem = this._hass.states[sensor_id].attributes.bound_rem;
      if (bound_rem) {
        return bound_rem;
      }
    } catch (error) {
      console.error('Error getting bound REM device:', error);
      throw error;
    }

    // try {
    //   const result = await this._hass.connection.sendMessagePromise({
    //     type: 'ramses_RF/get_bound_rem',
    //     device_id: deviceId
    //   });

    //   return result.rem_id;
    // } catch (error) {
    //   console.error('Error getting bound REM device:', error);
    //   throw error;
    // }
  }

  // Method to send packet via ramses_RF service
  async sendPacket(deviceId, fromId, verb, code, payload) {
    if (!this._hass) {
      throw new Error('Home Assistant instance not available');
    }

    try {
      await this._hass.callService('ramses_RF', 'send_packet', {
        device_id: deviceId,
        from_id: fromId,
        verb: verb,
        code: code,
        payload: payload
      });
      console.log(`SuRFessfully sent packet: ${verb} ${code} ${payload}`);
    } catch (error) {
      console.error('Error sending packet:', error);
      throw error;
    }
  }

  async sendFanCommand(commandKey) {
    if (!this._hass || !this.config?.device_id) {
      console.error('Missing Home Assistant instance or device_id');
      return false;
    }

    const command = hvacFanCard.FAN_COMMANDS[commandKey];
    if (!command) {
      console.error(`No command defined for: ${commandKey}`);
      return false;
    }

    try {
      // Use the configured device ID
      const deviceId = this.config.device_id;

      console.log(`Using configured device ID for commands: ${deviceId}`);

      // Find the actual dehumidify switch entity
      const switchEntity = 'switch.dehumidify_' + deviceId.replace(/:/g, '_');

      if (commandKey === 'active') {
        // Toggle dehumidify mode by calling the switch service
        console.log(`Toggling dehumidify switch: ${switchEntity}`);
        await this._hass.callService('switch', 'turn_on', {
          entity_id: switchEntity
        });
        return true;
      }

      // Get the bound REM device first
      let remId;
      try {
        remId = await this.getBoundRem(deviceId);
        if (remId) {
          console.log(`Using bound REM as from_id: ${remId}`);
        } else {
          console.log('No bound REM found, using device_id as from_id');
          remId = deviceId;
        }
      } catch (error) {
//        console.warn(`WebSocket error getting bound REM: ${error.message}. Falling back to device_id.`);
        remId = null;
      }

      // Send the packet
      await this.sendPacket(deviceId, remId, command.verb, command.code, command.payload);

      console.log(`SuRFessfully set fan mode to ${commandKey}`);
      // Update UI
      const fanModeElement = this.shadowRoot?.querySelector('#fanMode');
      if (fanModeElement) {
        fanModeElement.textContent = commandKey;
      }

      return true;
    } catch (error) {
      console.error(`Error sending ${commandKey} command:`, error);
      return false;
    }
  }

  setConfig(config) {
    // console.log('=== hvacFanCard setConfig Debug ===');
    // console.log('Config received:', config);
    // console.log('Config type:', typeof config);
    // console.log('Config keys:', config ? Object.keys(config) : 'null');

    if (!config.fan_entity && !config.device_id) {
      console.error('Missing required config: need fan_entity or device_id');
      throw new Error('You need to define either fan_entity or device_id');
    }

    if (!config.device_id) {
      console.warn('No device_id provided, will extract from fan_entity');
      throw new Error('You need to define device_id');
    }

    // Normalize device ID to colon format for consistency
    let deviceId = config.device_id;
    deviceId = deviceId.replace(/_/g, ':');

    // Store the processed config for internal use
    this._config = {
      device_id: deviceId,
      // Auto-generate absolute humidity sensor entities (created by integration)
      indoor_abs_humid_entity: 'sensor.indoor_absolute_humidity_' + deviceId.replace(/:/g, '_'),
      outdoor_abs_humid_entity: 'sensor.outdoor_absolute_humidity_' + deviceId.replace(/:/g, '_'),
      // Fallback to calculated humidity if absolute humidity sensors don't exist
      indoor_temp_entity: config.indoor_temp_entity || 'sensor.' + deviceId.replace(/:/g, '_') + '_indoor_temp',
      outdoor_temp_entity: config.outdoor_temp_entity || 'sensor.' + deviceId.replace(/:/g, '_') + '_outdoor_temp',
      indoor_humidity_entity: config.indoor_humidity_entity || 'sensor.' + deviceId.replace(/:/g, '_') + '_indoor_humidity',
      outdoor_humidity_entity: config.outdoor_humidity_entity || 'sensor.' + deviceId.replace(/:/g, '_') + '_outdoor_humidity',
      supply_temp_entity: config.supply_temp_entity || 'sensor.' + deviceId.replace(/:/g, '_') + '_supply_temp',
      exhaust_temp_entity: config.exhaust_temp_entity || 'sensor.' + deviceId.replace(/:/g, '_') + '_exhaust_temp',
      fan_speed_entity: config.fan_speed_entity || 'sensor.' + deviceId.replace(/:/g, '_') + '_fan_info',
      fan_mode_entity: config.fan_mode_entity || 'sensor.' + deviceId.replace(/:/g, '_') + '_fan_mode',
      co2_entity: config.co2_entity || 'sensor.' + deviceId.replace(/:/g, '_') + '_co2_level',
      flow_entity: config.flow_entity || 'sensor.' + deviceId.replace(/:/g, '_') + '_supply_flow',
      bypass_entity: config.bypass_entity || 'binary_sensor.' + deviceId.replace(/:/g, '_') + '_bypass_position',
      // Use configured entities if provided, otherwise auto-generate
      dehum_mode_entity: config.dehum_mode_entity || 'switch.dehumidify_' + deviceId.replace(/:/g, '_'),
      dehum_active_entity: config.dehum_active_entity || 'binary_sensor.dehumidifying_active_' + deviceId.replace(/:/g, '_'),
      comfort_temp_entity: config.comfort_temp_entity || 'number.' + deviceId.replace(/:/g, '_') + '_param_75',
      ...config
    };

    // Set the config property for Home Assistant's card framework
    // This ensures this.config is available and matches this._config
    this.config = this._config;
  }

  render() {
    console.log('🎯 RENDER CALLED - checking config and hass...');
    console.log('🎯 this._config:', this._config);
    console.log('🎯 this._hass:', this._hass);
    console.log('🎯 this.config:', this.config);

    if (!this._hass || !this.config) {
      console.error('❌ Missing hass or config:', {
        hass: !!this._hass,
        _config: !!this._config,
        config: !!this.config
      });
      return;
    }

    console.log('✅ Hass and config available, proceeding with render');

    // Debug: Validate entities are available
    this.validateEntities();

    const config = this.config;  // Use config consistently
    const hass = this._hass;

    // Check dehumidify entity availability
    const dehumEntitiesAvailable = this.checkDehumidifyEntities();

    const indoorTemp = hass.states[config.indoor_temp_entity]?.state || '?';
    const outdoorTemp = hass.states[config.outdoor_temp_entity]?.state || '?';
    const indoorHumidity = hass.states[config.indoor_humidity_entity]?.state || '?';
    const outdoorHumidity = hass.states[config.outdoor_humidity_entity]?.state || '?';

    // Use ramses_extras absolute humidity sensors
    const indoorAbsHumidity = hass.states[config.indoor_abs_humid_entity]?.state || '?';
    const outdoorAbsHumidity = hass.states[config.outdoor_abs_humid_entity]?.state || '?';

    const supplyTemp = hass.states[config.supply_temp_entity]?.state || '?';
    const exhaustTemp = hass.states[config.exhaust_temp_entity]?.state || '?';
    const fanSpeed = hass.states[config.fan_speed_entity]?.state || 'speed ?';
    const fanMode = hass.states[config.fan_mode_entity]?.state || 'auto';
    const co2Level = hass.states[config.co2_entity]?.state || '?';
    const flowRate = hass.states[config.flow_entity]?.state || '?';

    // Dehumidifier entities (only if available)
    const dehumMode = dehumEntitiesAvailable ? (hass.states[config.dehum_mode_entity]?.state || 'off') : null;
    const dehumActive = dehumEntitiesAvailable ? (hass.states[config.dehum_active_entity]?.state || 'off') : null;

    // Comfort temperature entity (will be available when created)
    const comfortTemp = hass.states[config.comfort_temp_entity]?.state || '?';

    // Determine which SVG to use based on bypass position
    const isBypassOpen = hass.states[config.bypass_entity]?.state === 'on';
    const selectedSvg = isBypassOpen ? BYPASS_OPEN_SVG : NORMAL_SVG;

    // Create template data object with integration-provided absolute humidity
    const rawData = {
      indoorTemp, outdoorTemp, indoorHumidity, outdoorHumidity,
      indoorAbsHumidity, outdoorAbsHumidity,  // From integration sensors
      supplyTemp, exhaustTemp, fanSpeed, fanMode, co2Level, flowRate,
      dehumMode, dehumActive, comfortTemp,
      dehumEntitiesAvailable,  // Add availability flag
      timerMinutes: 0, // This would come from timer state
      // efficiency: 75   // Remove hardcoded value - let template calculate it
    };

    console.log('🔍 DEBUG - Raw temperature values:', {
      supplyTemp, exhaustTemp, outdoorTemp,
      indoorTemp, outdoorTemp
    });

    console.log('🔍 DEBUG - Humidity values:', {
      indoorHumidity, outdoorHumidity,
      indoorAbsHumidity, outdoorAbsHumidity,
      indoorAbsFromIntegration: !!hass.states[config.indoor_abs_humid_entity]?.state,
      outdoorAbsFromIntegration: !!hass.states[config.outdoor_abs_humid_entity]?.state,
      indoorAbsEntity: config.indoor_abs_humid_entity,
      outdoorAbsEntity: config.outdoor_abs_humid_entity
    });

    // Enhanced dehumidify debugging
    console.log('🔍 DEBUG - Dehumidify entities:', {
      dehumModeEntity: config.dehum_mode_entity,
      dehumActiveEntity: config.dehum_active_entity,
      dehumEntitiesAvailable,
      dehumMode: dehumMode,
      dehumActive: dehumActive,
      dehumModeState: dehumEntitiesAvailable ? hass.states[config.dehum_mode_entity]?.state : 'N/A',
      dehumActiveState: dehumEntitiesAvailable ? hass.states[config.dehum_active_entity]?.state : 'N/A'
    });

    const templateData = createTemplateData(rawData);
    // Add airflow SVG to template data
    templateData.airflowSvg = selectedSvg;

    console.log('🔍 DEBUG - Calculated efficiency:', templateData.efficiency);

    console.log('🔧 Generating card HTML using templates...');

    // Generate HTML using template functions
    const cardHtml = [
      createCardHeader(CARD_STYLE),
      createTopSection(templateData),
      createControlsSection(dehumEntitiesAvailable),  // Pass availability flag
      createCardFooter()
    ].join('');

    this.innerHTML = cardHtml;

    console.log('✅ Card HTML generated suRFessfully');
  }

  // Configuration schema for visual editor
  static getConfigElement() {
    try {
      // Ensure the editor is available before creating it
      if (typeof window.HvacFanCardEditor === 'undefined') {
        console.error('HvacFanCardEditor is not defined on window');
        return null;
      }
      return document.createElement("hvac-fan-card-editor");
    } catch (error) {
      console.error('Error creating config element:', error);
      return null;
    }
  }

  // Card size for Home Assistant
  getCardSize() {
    return 3;
  }

  // Validate all required entities are available
  validateEntities() {
    console.log('🎯 VALIDATE ENTITIES CALLED!');
    console.log('🎯 this._config exists:', !!this._config);
    console.log('🎯 this._hass exists:', !!this._hass);
    console.log('🎯 this.config exists:', !!this.config);

    // Note: config and hass are already validated in render() before this is called
    const config = this.config;
    const hass = this._hass;

    console.log('🔍 DEBUG - Config object:', {
      hasConfig: !!config,
      configKeys: config ? Object.keys(config) : 'NO CONFIG',
      indoor_temp_entity: config?.indoor_temp_entity,
      outdoor_temp_entity: config?.outdoor_temp_entity,
      dehum_mode_entity: config?.dehum_mode_entity,
      dehum_active_entity: config?.dehum_active_entity,
      device_id: config?.device_id,
      fullConfig: config
    });
    // Check core entities
    const coreEntities = {
      'Indoor Temperature': config.indoor_temp_entity,
      'Outdoor Temperature': config.outdoor_temp_entity,
      'Indoor Humidity': config.indoor_humidity_entity,
      'Outdoor Humidity': config.outdoor_humidity_entity,
      'Supply Temperature': config.supply_temp_entity,
      'Exhaust Temperature': config.exhaust_temp_entity,
      'Fan Speed': config.fan_speed_entity,
      'Fan Mode': config.fan_mode_entity,
      'Bypass': config.bypass_entity,
    };

    const missingCoreEntities = [];
    const availableCoreEntities = [];

    Object.entries(coreEntities).forEach(([name, entityId]) => {
      const exists = !!hass.states[entityId];
      if (exists) {
        availableCoreEntities.push(name);
      } else {
        missingCoreEntities.push(name);
      }
    });

    if (availableCoreEntities.length > 0) {
      console.log('✅ Available entities:', availableCoreEntities.join(', '));
    }

    if (missingCoreEntities.length > 0) {
      console.warn('⚠️ Missing entities:', missingCoreEntities.join(', '));
    }

    // Check dehumidify entities specifically
    const dehumEntities = {
      'Dehumidify Mode': config.dehum_mode_entity,
      'Dehumidify Active': config.dehum_active_entity,
    };

    const missingDehumEntities = [];
    const availableDehumEntities = [];

    Object.entries(dehumEntities).forEach(([name, entityId]) => {
      const exists = !!hass.states[entityId];
      if (exists) {
        availableDehumEntities.push(name);
      } else {
        missingDehumEntities.push(name);
      }
    });

    if (availableDehumEntities.length > 0) {
      console.log('💧 Dehumidify entities available:', availableDehumEntities.join(', '));
    }

    if (missingDehumEntities.length > 0) {
      console.log('💧 Dehumidify entities missing:', missingDehumEntities.join(', '));
    }

    // Check absolute humidity entities
    const absHumidEntities = {
      'Indoor Absolute Humidity': config.indoor_abs_humid_entity,
      'Outdoor Absolute Humidity': config.outdoor_abs_humid_entity,
    };

    const missingAbsEntities = [];
    const availableAbsEntities = [];

    Object.entries(absHumidEntities).forEach(([name, entityId]) => {
      const exists = !!hass.states[entityId];
      if (exists) {
        availableAbsEntities.push(name);
      } else {
        missingAbsEntities.push(name);
      }
    });

    if (availableAbsEntities.length > 0) {
      console.log('🌫️ Absolute humidity entities available:', availableAbsEntities.join(', '));
    }

    if (missingAbsEntities.length > 0) {
      console.log('🌫️ Absolute humidity entities missing:', missingAbsEntities.join(', '));
    }

    console.log('🔍 Entity validation complete');
  }

  // Check if dehumidify entities are available
  checkDehumidifyEntities() {
    // Note: config and hass are already validated in render() before this is called
    const config = this.config;
    const hass = this._hass;

    // Check if both dehumidify entities exist with correct format
    const dehumModeExists = !!hass.states[config.dehum_mode_entity];
    const dehumActiveExists = !!hass.states[config.dehum_active_entity];

    const entitiesAvailable = dehumModeExists && dehumActiveExists;

    console.log('💧 Dehumidify entity check:', {
      dehumModeEntity: config.dehum_mode_entity,
      dehumActiveEntity: config.dehum_active_entity,
      dehumModeExists,
      dehumActiveExists,
      entitiesAvailable
    });

    return entitiesAvailable;
  }

  // Handle bypass button clicks
  async sendBypassCommand(mode) {
    console.log('Setting bypass to:', mode);
    // Use the new sendFanCommand function
    await this.sendFanCommand('bypass_' + mode);
  }

  // Handle timer button clicks
  async setTimer(minutes) {
    console.log('Setting timer for:', minutes, 'minutes');
    // Use the new sendFanCommand function
    await this.sendFanCommand(minutes);
  }

  // Handle fan mode changes
  async setFanMode(mode) {
    console.log('Setting fan mode to:', mode);

    if (mode === 'active') {
      // Find the actual dehumidify switch entity
      const deviceId = this.config.device_id;
      const switchEntity = 'switch.dehumidify_' + deviceId.replace(/:/g, '_');

      if (this._hass.states[switchEntity]) {
        // Toggle dehumidify mode by calling the switch service
        console.log(`Toggling dehumidify switch: ${switchEntity}`);
        await this._hass.callService('switch', 'toggle', {
          entity_id: switchEntity
        });
      } else {
        console.error(`Dehumidify switch not found: ${switchEntity}`);
      }
    } else {
      // Handle other fan modes (if any)
      console.log('Other fan mode:', mode);
      await this.sendFanCommand(mode);
    }
  }

  updateTimerUI(minutes) {
    console.log('Updating timer UI to:', minutes, 'minutes');
    const timerElement = this.shadowRoot?.querySelector('#timer');
    if (timerElement) {
      timerElement.textContent = minutes + ' min';
    }

    // Update active state
    const buttons = this.shadowRoot?.querySelectorAll('.control-button');
    if (buttons) {
      buttons.forEach(btn => {
        const label = btn.querySelector('.control-label')?.textContent;
        if (label === minutes + 'm') {
          btn.classList.add('active');
        } else if (['15m', '30m', '60m'].includes(label)) {
          btn.classList.remove('active');
        }
      });
    }
  }

  updateBypassUI(mode) {
    console.log('Updating bypass UI to:', mode);

    // Update active state
    const buttons = this.shadowRoot?.querySelectorAll('.control-button');
    if (buttons) {
      buttons.forEach(btn => {
        const label = btn.querySelector('.control-label')?.textContent;
        if ((mode === 'auto' && label === 'Bypass Auto') ||
            (mode === 'close' && label === 'Bypass Close') ||
            (mode === 'open' && label === 'Bypass Open')) {
          btn.classList.add('active');
        } else if (label?.startsWith('Bypass')) {
          btn.classList.remove('active');
        }
      });
    }
  }

  // Add event listeners after the component is connected to the DOM
  connectedCallback() {
    console.log('=== hvacFanCard connectedCallback Debug ===');
    console.log('Card connected to DOM');
    console.log('Card instance:', this);
    console.log('Card shadowRoot:', this.shadowRoot);
    console.log('Card config at connect:', this._config);
    console.log('Card hass at connect:', this._hass);

    // No need to call super.connectedCallback() as HTMLElement doesn't have it

    // Set up a single click handler for the entire card
    this.addEventListener('click', (event) => {
      const button = event.target.closest('.control-button');
      if (!button) return;

      event.preventDefault();
      event.stopPropagation();

      console.log('🔘 Button clicked:', button);
      console.log('Button dataset:', button.dataset);
      console.log('Button onclick:', button.getAttribute('onclick'));

      // Handle different button types
      if (button.hasAttribute('onclick')) {
        // For buttons with inline onclick handlers
        const onclick = button.getAttribute('onclick');
        if (onclick) {
          console.log('Executing onclick handler:', onclick);
          // Create a function in the global scope to execute the onclick
          const fn = new Function('event', `
            try {
              ${onclick}
            } catch(e) {
              console.error('Error in button handler:', e);
            }`);
          fn.call(button, event);
        }
      } else if (button.dataset.mode) {
        console.log('Calling setFanMode with mode:', button.dataset.mode);
        this.setFanMode(button.dataset.mode);
      } else if (button.dataset.timer) {
        console.log('Calling setTimer with minutes:', button.dataset.timer);
        this.setTimer(button.dataset.timer);
      }
    });

    console.log('✅ Event listeners attached');

    // Store the card instance globally
    window.hvacFanCardInstance = this;

    // Make functions globally available for onclick handlers
    window.updateTimerUI = this.updateTimerUI;
    window.updateBypassUI = this.updateBypassUI;
    window.setBypassMode = (mode) => this.sendBypassCommand(mode);
  }
}

// Include the editor component
// This ensures the editor is loaded when the card is used

// Register the web component
if (!customElements.get('hvac-fan-card')) {
  console.log('Registering hvac-fan-card web component');
  customElements.define('hvac-fan-card', HvacFanCard);
}

// Register it with HA for automatic discovery
window.customCards = window.customCards || [];
console.log('🔍 Current window.customCards before registration:', window.customCards.length);

window.customCards.push({
  type: "hvac-fan-card",
  name: "Hvac Fan Control Card",
  description: "Advanced control card for Orcon or other ventilation systems",
  preview: true, // Shows in card picker
  documentationURL: "https://github.com/wimpie70/ramses_extras"
});

console.log('✅ hvac-fan-card registered in window.customCards:', {
  type: "hvac-fan-card",
  name: "Hvac Fan Control Card",
  length: window.customCards.length
});
console.log('📋 All registered cards:', window.customCards);
