/* global HTMLElement */
/* global customElements */

class RamsesLogExplorerCard extends HTMLElement {
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

    const title = this._config?.title || 'Ramses Log Explorer';
    this._root.innerHTML = `
      <ha-card header="${title}">
        <div style="padding: 16px;">
          <div>Ramses Debugger: Log Explorer scaffold.</div>
        </div>
      </ha-card>
    `;
  }
}

const tag = 'ramses-log-explorer';
if (!customElements.get(tag)) {
  customElements.define(tag, RamsesLogExplorerCard);
}

window.customCards = window.customCards || [];
window.customCards.push({
  type: 'ramses-log-explorer',
  name: 'Ramses Log Explorer',
  description: 'Filter and extract context from the HA log file',
  preview: true,
});
