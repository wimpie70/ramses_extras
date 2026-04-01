/* global customElements */

import * as logger from '../../helpers/logger.js';

import { RamsesBaseCard } from '../../helpers/ramses-base-card.js';

import './ramses-fan-map-editor.js';

class RamsesFanMap extends RamsesBaseCard {
  constructor() {
    super();
    this._domInitialized = false;
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

  _renderContent() {
    if (!this._domInitialized) {
      this._initializeDOM();
      this._domInitialized = true;
    }

    const container = this.shadowRoot?.getElementById('cardContent');
    if (!container) {
      return;
    }

    container.innerHTML = `
      <div class="section">
        <div class="title">FAN Map</div>
        <div class="subtitle">device_id: <code>${this.config?.device_id || ''}</code></div>
      </div>

      <div class="section">
        <div class="section-header">Topology</div>
        <div class="placeholder">(coming next) zones / areas / REM bindings</div>
      </div>

      <div class="section">
        <div class="section-header">Observability</div>
        <div class="placeholder">(coming next) valve positions / sensors / diagnostics</div>
      </div>

      <div class="section danger">
        <div class="section-header">Test bench</div>
        <div class="placeholder">(coming next) guarded actions (actuation / demand / calibrate)</div>
      </div>
    `;
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
