/**
 * Ramses Floorplan Actions card
 *
 * Companion bar for floorplan-studio: full-width card meant to sit
 * below (or above) the studio card on the same view.
 *
 *   - "Open studio" / "Open editor" navigate to the configured tool URLs
 *   - "Seed markers" runs floorplan_seed_studio and copies the emitted
 *     project JSON to the clipboard (paste into studio → Import JSON)
 *   - "Export bundle" runs floorplan_export and copies card_yaml
 *   - "Sync areas" runs floorplan_sync_areas on the stored project
 *   - Drop zone: drop a studio "Export JSON" file — it is stored
 *     server-side (latest.json + timestamped backup) and, unless
 *     sync_on_drop: false, synced into HA areas.
 *
 * Config (all optional):
 *   floors: {begane grond: plattegrond-bg.svg, ...}  floor name → SVG ref
 *   marker_size: 20
 *   sync_on_drop: true
 *   studio_url: /floorplan-studio   (fallback: floorplan options)
 */

const DOMAIN = 'ramses_extras';

const STYLE = `
  :host { display: block; }
  ha-card { padding: 12px 16px; }
  .title { font-size: 15px; font-weight: 600; margin-bottom: 8px;
           color: var(--primary-text-color); }
  .row { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
  button {
    background: var(--primary-color); color: var(--text-primary-color, #fff);
    border: none; border-radius: 6px; padding: 7px 14px; cursor: pointer;
    font-size: 13px; font-family: inherit;
  }
  button.secondary { background: var(--secondary-background-color, #eee);
                     color: var(--primary-text-color); }
  button:disabled { opacity: 0.5; cursor: default; }
  .drop {
    margin-top: 10px; border: 2px dashed var(--divider-color, #ccc);
    border-radius: 8px; padding: 10px; text-align: center;
    color: var(--secondary-text-color); font-size: 13px; cursor: pointer;
  }
  .drop.over { border-color: var(--primary-color);
               color: var(--primary-color); }
  .status { margin-top: 8px; font-size: 12px;
            color: var(--secondary-text-color); white-space: pre-wrap; }
  input[type=file] { display: none; }
`;

class RamsesFloorplanActions extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: 'open' });
    this._config = {};
    this._hass = null;
    this._fpConfig = null;
    this._busy = false;
  }

  setConfig(config) {
    this._config = config || {};
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._fpConfig && hass) {
      this._fetchConfig();
    }
  }

  getCardSize() {
    return 2;
  }

  static getConfigElement() {
    return document.createElement('div'); // no visual editor (yet)
  }

  static getStubConfig() {
    return {};
  }

  async _fetchConfig() {
    try {
      this._fpConfig = await this._hass.callWS({
        type: 'ramses_extras/floorplan_helper/get_config',
      });
    } catch {
      this._fpConfig = {};
    }
  }

  _call(service, data) {
    return this._hass.callWS({
      type: 'call_service',
      domain: DOMAIN,
      service,
      service_data: data || {},
      return_response: true,
    }).then((r) => (r && r.response) || {});
  }

  _copy(text, label) {
    const done = () => this._status(`${label} copied to clipboard`);
    if (navigator.clipboard && window.isSecureContext) {
      navigator.clipboard.writeText(text).then(done, () => this._status(`${label} — copy failed`));
    } else {
      const ta = document.createElement('textarea');
      ta.value = text;
      document.body.appendChild(ta);
      ta.select();
      try { document.execCommand('copy'); done(); }
      catch { this._status(`${label} — copy failed`); }
      document.body.removeChild(ta);
    }
  }

  _navigate(url) {
    if (!url) { this._status('No tool URL configured'); return; }
    if (/^https?:/i.test(url)) { window.open(url, '_blank'); return; }
    window.history.pushState(null, '', url);
    window.dispatchEvent(new CustomEvent('location-changed'));
  }

  async _run(btn, fn) {
    if (this._busy) return;
    this._busy = true;
    this._setDisabled(true);
    try {
      await fn();
    } catch (e) {
      this._status(`Error: ${e.message || e}`);
    } finally {
      this._busy = false;
      this._setDisabled(false);
    }
  }

  _setDisabled(off) {
    this.shadowRoot.querySelectorAll('button').forEach((b) => { b.disabled = off; });
  }

  _status(text) {
    const el = this.shadowRoot.getElementById('status');
    if (el) el.textContent = text;
  }

  async _seed() {
    const data = {};
    if (this._config.floors) data.floors = this._config.floors;
    if (this._config.marker_size) data.marker_size = this._config.marker_size;
    const r = await this._call('floorplan_seed_studio', data);
    const placed = Object.keys(r.placed || {}).length;
    const unplaced = (r.unplaced || []).length;
    if (r.project_json) {
      this._copy(r.project_json,
        `Seeded: ${placed} placed, ${unplaced} parked. Project JSON`);
      this._status(`Seeded: ${placed} placed, ${unplaced} parked — project JSON copied to clipboard. Import via Projects → Import JSON in studio.`);
    } else {
      this._status(`Seeded: ${placed} placed, ${unplaced} parked`);
    }
  }

  async _export() {
    const r = await this._call('floorplan_export', {});
    if (r.card_yaml) {
      this._copy(r.card_yaml, 'card_yaml');
      this._status(`Exported ${(r.rules || []).length} rules — card_yaml copied to clipboard.`);
    } else {
      this._status('Export finished (no card_yaml in response)');
    }
  }

  async _sync() {
    const r = await this._call('floorplan_sync_areas', {});
    const a = r.assignments || [];
    const c = r.areas_created || [];
    const o = r.entities_without_area_room || [];
    this._status(`Sync: ${a.length} entities assigned, ${c.length} areas created` +
      (o.length ? `, ${o.length} outside rooms` : '') +
      (r.backup_path ? `\nbackup: ${r.backup_path}` : ''));
  }

  async _storeAndSync(text) {
    const r = await this._call('floorplan_store_project', { project_json: text });
    let msg = `Project stored: ${r.latest_path}`;
    if (this._config.sync_on_drop !== false) {
      const s = await this._call('floorplan_sync_areas', {});
      msg += `\nSync: ${(s.assignments || []).length} entities assigned, ` +
        `${(s.areas_created || []).length} areas created`;
    }
    this._status(msg);
  }

  _render() {
    this.shadowRoot.innerHTML = `
      <style>${STYLE}</style>
      <ha-card>
        <div class="title">Floorplan</div>
        <div class="row">
          <button id="b-studio">Open studio</button>
          <button id="b-editor" class="secondary">Open editor</button>
          <button id="b-seed" class="secondary">Seed markers</button>
          <button id="b-export" class="secondary">Export bundle</button>
          <button id="b-sync" class="secondary">Sync areas</button>
        </div>
        <div class="drop" id="drop">
          Drop studio project JSON here (or click to browse)
          <input id="file" type="file" accept=".json,application/json">
        </div>
        <div class="status" id="status"></div>
      </ha-card>`;

    const $ = (id) => this.shadowRoot.getElementById(id);
    $('b-studio').onclick = () =>
      this._navigate(this._config.studio_url || (this._fpConfig || {}).planner_url || '/floorplan-studio');
    $('b-editor').onclick = () =>
      this._navigate(this._config.editor_url || (this._fpConfig || {}).editor_url);
    $('b-seed').onclick = () => this._run(null, () => this._seed());
    $('b-export').onclick = () => this._run(null, () => this._export());
    $('b-sync').onclick = () => this._run(null, () => this._sync());

    const drop = $('drop');
    const file = $('file');
    drop.onclick = () => file.click();
    file.onchange = () => {
      const f = file.files[0];
      if (f) this._readFile(f);
      file.value = '';
    };
    drop.ondragover = (e) => { e.preventDefault(); drop.classList.add('over'); };
    drop.ondragleave = () => drop.classList.remove('over');
    drop.ondrop = (e) => {
      e.preventDefault();
      drop.classList.remove('over');
      const f = e.dataTransfer.files && e.dataTransfer.files[0];
      if (f) this._readFile(f);
    };
  }

  _readFile(file) {
    const reader = new window.FileReader();
    reader.onload = () =>
      this._run(null, () => this._storeAndSync(String(reader.result || '')));
    reader.readAsText(file);
  }
}

customElements.define('ramses-floorplan-actions', RamsesFloorplanActions);

window.customCards = window.customCards || [];
window.customCards.push({
  type: 'ramses-floorplan-actions',
  name: 'Ramses Floorplan Actions',
  description: 'Action bar + project drop zone for floorplan-studio workflows',
});
