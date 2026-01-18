/* global HTMLElement */
/* global customElements */

class RamsesTrafficAnalyserCard extends HTMLElement {
  setConfig(config) {
    this._config = config;
    if (!this._root) {
      this._root = this.attachShadow({ mode: 'open' });
    }
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  getCardSize() {
    return 2;
  }

  _render() {
    if (!this._root) {
      return;
    }

    const title = this._config?.title || 'Ramses Traffic Analyser';
    this._root.innerHTML = `
      <ha-card header="${title}">
        <div style="padding: 16px;">
          <div>Ramses Debugger: Traffic Analyser scaffold.</div>
        </div>
      </ha-card>
    `;
  }
}

const tag = 'ramses-traffic-analyser';
if (!customElements.get(tag)) {
  customElements.define(tag, RamsesTrafficAnalyserCard);
}

window.customCards = window.customCards || [];
window.customCards.push({
  type: 'ramses-traffic-analyser',
  name: 'Ramses Traffic Analyser',
  description: 'Spreadsheet-like comms matrix for ramses_cc traffic',
  preview: true,
});
