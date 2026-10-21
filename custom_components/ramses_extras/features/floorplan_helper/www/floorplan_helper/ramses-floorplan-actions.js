/**
 * Ramses Floorplan Actions card
 *
 * Companion bar for floorplan-studio: full-width card meant to sit
 * below (or above) the studio card on the same view.
 *
 * Studio stores its projects in this origin's IndexedDB
 * (db 'floorplan-studio', store 'projects', meta 'lastProjectId') and
 * autosaves ~600ms after every change — so this card can pull the live
 * project and push seeded/stored projects with no export/download
 * round-trip. The workflow row reads left→right:
 *
 *   1. "Open studio" — navigate to the studio view (editor_url option)
 *   2. project picker — studio's own projects in this browser
 *   3. "⟵ Store ← studio" — store the selected project server-side
 *      (latest.json + backup) and sync HA areas
 *   4. "Export ⇒" — snapshot the live project, run floorplan_export,
 *      copy the card yaml
 *
 * Tools row:
 *   - "＋ Add devices" — seed/merge new device markers into the
 *     selected project (or the stored one), written back into studio
 *   - "⇒ Push → studio" — write the stored latest.json back into
 *     studio's project list (restores a project this browser lost)
 *   - "Sync areas" — re-run marker-in-room → entity area_id sync
 *   - Drop zone: fallback for JSON files from another machine/backup
 *
 * Config (all optional):
 *   floors: {begane grond: plattegrond-bg.svg, ...}  floor name → SVG ref
 *   marker_size: 20
 *   sync_on_pull: true   (also sync HA areas after pull/store)
 *   studio_url: /floorplan-studio   (fallback: floorplan options)
 *   device_view_url: /lovelace/hvac  (optional — adds a '⤢ dashboard'
 *   button to the device popup opened by double-clicking a marker)
 */

const DOMAIN = 'ramses_extras';
const FP_DB = 'floorplan-studio';

const STYLE = `
  :host { display: block; }
  ha-card { padding: 12px 16px; }
  .title { font-size: 15px; font-weight: 600;
           color: var(--primary-text-color); }
  .hint { font-size: 12px; color: var(--secondary-text-color);
          margin: 4px 0 8px; }
  .row { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
  .lbl { font-size: 13px; color: var(--secondary-text-color); }
  button {
    background: var(--primary-color); color: var(--text-primary-color, #fff);
    border: none; border-radius: 6px; padding: 7px 14px; cursor: pointer;
    font-size: 13px; font-family: inherit;
  }
  button.secondary { background: var(--secondary-background-color, #eee);
                     color: var(--primary-text-color); }
  button:disabled { opacity: 0.5; cursor: default; }
  select {
    font-size: 13px; padding: 5px; border-radius: 6px;
    border: 1px solid var(--divider-color, #ccc);
    background: var(--card-background-color, #fff);
    color: var(--primary-text-color); max-width: 220px;
  }
  .drop {
    margin-top: 10px; border: 2px dashed var(--divider-color, #ccc);
    border-radius: 8px; padding: 10px; text-align: center;
    color: var(--secondary-text-color); font-size: 13px; cursor: pointer;
  }
  .drop.over { border-color: var(--primary-color);
               color: var(--primary-color); }
  .status { margin-top: 8px; font-size: 12px;
            color: var(--secondary-text-color); white-space: pre-wrap; }
  textarea.log {
    width: 100%; box-sizing: border-box; margin-top: 8px; padding: 6px;
    font-size: 12px; font-family: inherit; resize: vertical;
    color: var(--secondary-text-color); background: transparent;
    border: 1px solid var(--divider-color, #ccc); border-radius: 6px;
    min-height: 2.4em; user-select: text; cursor: text;
  }
  .tweaks { margin-top: 10px; padding: 10px; border-radius: 8px;
            background: var(--secondary-background-color, #f5f5f5);
            font-size: 13px; }
  .tweaks .row { margin-bottom: 6px; }
  .tweaks label { color: var(--secondary-text-color); min-width: 150px;
                  display: inline-block; }
  .tweaks input[type=number], .tweaks input[type=text] {
    width: 140px; padding: 4px 6px; border-radius: 5px;
    border: 1px solid var(--divider-color, #ccc); font-size: 13px;
  }
  .devoverlay {
    position: fixed; inset: 0; z-index: 999;
    display: flex; align-items: center; justify-content: center;
    background: rgba(0,0,0,0.5);
  }
  .devdialog {
    background: var(--card-background-color, #fff);
    color: var(--primary-text-color);
    border-radius: 12px; box-shadow: 0 8px 30px rgba(0,0,0,0.4);
    width: min(440px, 92vw); max-height: 85vh; overflow-y: auto;
    padding: 10px 14px 14px;
  }
  .devdialog .lbl { font-size: 14px; font-weight: 600;
                    color: var(--primary-text-color); }
  input[type=file] { display: none; }
`;

const TWEAKS_KEY = 'ramses-floorplan-actions-tweaks';

const DBG = '[fp-actions]';
/* eslint-disable no-console -- temporary diagnostics while the studio bridge settles */
const dlog = (...a) => console.debug(DBG, ...a);
const dwarn = (...a) => console.warn(DBG, ...a);
/* eslint-enable no-console */

// Lovelace renders cards inside nested shadow roots (hui-card etc.), so
// a plain document.querySelector can't reach sibling cards — walk the
// shadow tree instead.
function deepFind(selector, root = document) {
  const direct = root.querySelector(selector);
  if (direct) return direct;
  for (const el of root.querySelectorAll('*')) {
    if (el.shadowRoot) {
      const hit = deepFind(selector, el.shadowRoot);
      if (hit) return hit;
    }
  }
  return null;
}

// --- minimal IndexedDB helpers (studio's 'floorplan-studio' db) -----------

function openFpDb() {
  return new Promise((resolve, reject) => {
    const req = window.indexedDB.open(FP_DB);
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error || new Error('IndexedDB open failed'));
  });
}

function idbReq(req) {
  return new Promise((resolve, reject) => {
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error || new Error('IndexedDB request failed'));
  });
}

// Piercing selector — lovelace nests cards inside several shadow roots.
function _deepQuery(selector, root = document) {
  if (!root || !root.querySelectorAll) return null;
  for (const el of root.querySelectorAll('*')) {
    if (el.matches && el.matches(selector)) return el;
    if (el.shadowRoot) {
      const hit = _deepQuery(selector, el.shadowRoot);
      if (hit) return hit;
    }
  }
  return null;
}

class RamsesFloorplanActions extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: 'open' });
    this._config = {};
    this._hass = null;
    this._fpConfig = null;
    this._topology = null;
    this._entityDevice = {}; // entity_id -> topology device record
    this._projects = [];   // studio projects [{id, name, updatedAt}]
    this._busy = false;
    this._tweaks = {};
    this._hiDevice = null; // device_id whose zone is highlighted
    this._hiPatched = [];  // [el, {attr: original}] pairs to restore
    this._roomsCache = null;
    this._devCard = null;
    try {
      this._tweaks =
        JSON.parse(window.localStorage.getItem(TWEAKS_KEY) || '{}') || {};
    } catch {
      this._tweaks = {};
    }
  }

  _tweak(key) {
    // card tweaks (localStorage) override the YAML config
    const v = this._tweaks[key];
    if (v !== undefined && v !== '' && v !== null) return v;
    return this._config[key];
  }

  _saveTweak(key, value) {
    this._tweaks[key] = value;
    window.localStorage.setItem(TWEAKS_KEY, JSON.stringify(this._tweaks));
  }

  setConfig(config) {
    this._config = config || {};
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    if (this._devCard) this._devCard.hass = hass;
    if (!this._fpConfig && hass) {
      this._fetchConfig();
      this._refreshProjects();
    }
  }

  connectedCallback() {
    if (!this._watch) {
      this._watch = setInterval(() => this._pollSelection(), 700);
    }
    // ll-custom is handled by the module-level popup below — it works on
    // every view, not only ones containing this card.
  }

  disconnectedCallback() {
    clearInterval(this._watch);
    this._watch = null;
    this._clearZoneHighlight();
  }

  getCardSize() {
    return 3;
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
    try {
      this._topology = await this._hass.callWS({
        type: 'ramses_extras/floorplan_helper/get_topology',
      });
      this._entityDevice = {};
      for (const d of (this._topology && this._topology.devices) || []) {
        for (const e of d.entities || []) {
          if (e.entity_id) this._entityDevice[e.entity_id] = d;
        }
      }
    } catch {
      this._topology = null;
      this._entityDevice = {};
    }
    this._fillZoneDevices();
  }

  async _refreshProjects() {
    try {
      const db = await openFpDb();
      const all = await idbReq(
        db.transaction('projects').objectStore('projects').getAll()
      );
      const lastId = await idbReq(
        db.transaction('meta').objectStore('meta').get('lastProjectId')
      );
      db.close();
      this._projects = (all || [])
        .map((p) => ({ id: p.id, name: p.name || p.id, last: p.id === lastId }))
        .sort((a, b) => (b.last ? 1 : 0) - (a.last ? 1 : 0));
    } catch {
      this._projects = [];
    }
    this._fillProjectSelect();
  }

  _fillProjectSelect() {
    const sel = this.shadowRoot.getElementById('project');
    if (!sel) return;
    sel.innerHTML = '';
    if (!this._projects.length) {
      const o = document.createElement('option');
      o.textContent = '(no studio project found)';
      o.value = '';
      sel.appendChild(o);
      return;
    }
    for (const p of this._projects) {
      const o = document.createElement('option');
      o.value = p.id;
      o.textContent = p.name + (p.last ? ' (current)' : '');
      sel.appendChild(o);
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

  async _run(fn) {
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
    if (el) {
      el.value = text;
      // grow to fit content
      el.style.height = 'auto';
      el.style.height = `${Math.max(2.4, (text.split('\n').length + 0.4) * 1.4)}em`;
    }
  }

  // --- reach into the studio card: selection + in-memory marker state ----

  _studioRoot() {
    const el = deepFind('floorplan-studio-card');
    dlog('studio card element:', el, 'shadowRoot:', el && el.shadowRoot);
    return el && el.shadowRoot ? el.shadowRoot : null;
  }

  _studioSelectedMarkers(quiet) {
    // Selected markers render a dashed #38bdf8 ring as first child of
    // their <g translate(x y)> inside the entities layer (edit mode only).
    const root = this._studioRoot();
    if (!root) return [];
    const gs = [...root.querySelectorAll('g[data-layer="entities"] > g')];
    if (!quiet) dlog(`entities layer: ${gs.length} marker <g> elements`);
    const out = gs
      .map((g) => {
        const ring = g.querySelector(':scope > circle');
        const sel =
          ring &&
          ring.getAttribute('stroke') === '#38bdf8' &&
          ring.getAttribute('stroke-dasharray');
        const m = /translate\(\s*([-\d.e]+)[ ,]+([-\d.e]+)\s*\)/.exec(
          g.getAttribute('transform') || ''
        );
        if (ring && !quiet) dlog('first circle attrs:', ring.getAttribute('stroke'), ring.getAttribute('stroke-dasharray'), '| transform:', g.getAttribute('transform'));
        return sel && m ? { x: parseFloat(m[1]), y: parseFloat(m[2]), el: g } : null;
      })
      .filter(Boolean);
    if (!quiet) dlog('selected markers found:', out.length);
    return out;
  }

  _studioSelectedRoomIds() {
    // Selected rooms render stroke:#38bdf8 + dasharray on their fill
    // path; the wrapping <g> carries data-room="<id>" — no fiber needed.
    const root = this._studioRoot();
    const ids = new Set();
    if (!root) return ids;
    for (const g of root.querySelectorAll('g[data-layer="rooms"] g[data-room]')) {
      const path = g.querySelector(':scope > path');
      if (
        path &&
        path.getAttribute('stroke') === '#38bdf8' &&
        path.getAttribute('stroke-dasharray')
      ) {
        ids.add(g.getAttribute('data-room'));
      }
    }
    dlog('selected rooms found:', ids.size);
    return ids;
  }

  _fiberOf(el) {
    const keys = Object.keys(el).filter((k) => k.startsWith('__react'));
    const key = keys.find((k) => k.startsWith('__reactFiber$'));
    if (!key) dwarn('no react fiber key on element; react keys present:', keys);
    return key ? el[key] : null;
  }

  _fiberMarker(g) {
    // Walk the fiber for the host <g> up to MarkerNode — its props carry
    // the marker object (and its id) from studio's store.
    let f = this._fiberOf(g);
    while (f) {
      if (f.memoizedProps && f.memoizedProps.marker) return f.memoizedProps.marker;
      f = f.return;
    }
    return null;
  }

  _selectedProjectId() {
    const sel = this.shadowRoot.getElementById('project');
    return sel && sel.value ? sel.value : null;
  }

  // --- device zones: marker click → highlight served rooms ---------------

  _slug(name) {
    return String(name || '')
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, '_')
      .replace(/^_+|_+$/g, '');
  }

  async _projectRooms() {
    // roomId -> {name, areaId, floor} from the selected studio project
    const now = Date.now();
    if (this._roomsCache && now - this._roomsCache.t < 3000) {
      return this._roomsCache.m;
    }
    const m = new Map();
    try {
      const db = await openFpDb();
      const id = this._selectedProjectId();
      const p = id && (await idbReq(
        db.transaction('projects').objectStore('projects').get(id)
      ));
      db.close();
      for (const f of (p && p.floors) || []) {
        for (const r of f.rooms || []) {
          m.set(r.id, {
            name: r.name,
            areaId: r.areaId || this._slug(r.name),
            floor: f.name,
          });
        }
      }
    } catch { /* no project reachable — zone matching degrades to none */ }
    this._roomsCache = { t: now, m };
    return m;
  }

  _deviceOfMarkerEl(g) {
    const marker = this._fiberMarker(g);
    const ents =
      marker && (marker.entities || (marker.entity ? [marker.entity] : []));
    for (const e of ents || []) {
      if (this._entityDevice[e]) return this._entityDevice[e];
    }
    return null;
  }

  _pollSelection() {
    if (this._busy || document.hidden || this._tweak('zone_watch') === false) {
      return;
    }
    const root = this._studioRoot();
    if (!root) return;

    // (Re)hook dblclick on the entities layer — studio may re-render it.
    const layer = root.querySelector('g[data-layer="entities"]');
    if (layer && !layer.__fpDbl) {
      layer.__fpDbl = true;
      layer.addEventListener('dblclick', (ev) => this._markerDblClick(ev, layer));
    }

    const sel = this._studioSelectedMarkers(true);
    let dev = null;
    for (const m of sel) {
      dev = this._deviceOfMarkerEl(m.el);
      if (dev) break;
    }
    const devId = dev && dev.device_id;
    if (devId !== this._hiDevice) {
      this._hiDevice = devId;
      this._hiDev = dev;
      this._applyZoneHighlight(devId, dev);
    } else if (
      this._hiDevice &&
      this._hiPatched.length &&
      !this._hiPatched[0][0].isConnected
    ) {
      // Studio re-rendered the rooms layer — re-apply the highlight.
      this._hiPatched = [];
      this._applyZoneHighlight(this._hiDevice, this._hiDev);
    }
  }

  _clearZoneHighlight() {
    for (const [el, attrs] of this._hiPatched) {
      for (const [k, v] of Object.entries(attrs)) {
        if (v === null) el.removeAttribute(k);
        else el.setAttribute(k, v);
      }
    }
    this._hiPatched = [];
  }

  async _applyZoneHighlight(devId, dev) {
    this._clearZoneHighlight();
    if (!devId) return;
    const zone = ((this._fpConfig || {}).device_zones || {})[devId];
    if (!zone) return;
    const areas = new Set(zone.areas || []);
    if (!areas.size) return;
    const color = zone.color || '#f59e0b';
    const rooms = await this._projectRooms();
    const root = this._studioRoot();
    if (!root) return;

    const names = [];
    for (const g of root.querySelectorAll('g[data-layer="rooms"] g[data-room]')) {
      const room = rooms.get(g.getAttribute('data-room'));
      if (!room || !areas.has(room.areaId)) continue;
      const path = g.querySelector(':scope > path');
      if (!path) continue;
      this._hiPatched.push([
        path,
        {
          stroke: path.getAttribute('stroke'),
          'stroke-width': path.getAttribute('stroke-width'),
          'stroke-dasharray': path.getAttribute('stroke-dasharray'),
        },
      ]);
      path.setAttribute('stroke', color);
      path.setAttribute('stroke-width', '3');
      path.setAttribute('stroke-dasharray', '6 3');
      names.push(room.name);
    }

    // bound devices: schema parent links (remotes/sensors of a FAN) +
    // the zone's devices list — the latter may hold non-ramses entity
    // ids (DIY valves, zigbee sensors); HGI gateways never highlight.
    const bound = new Set([devId]);
    for (const d of (this._topology || {}).devices || []) {
      if (d.parent === devId && d.device_class !== 'HGI') bound.add(d.device_id);
    }
    for (const b of zone.devices || []) bound.add(String(b));
    const entsLayer = root.querySelector('g[data-layer="entities"]');
    if (entsLayer) {
      let nDev = 0;
      for (const g of entsLayer.querySelectorAll('g')) {
        const marker = this._fiberMarker(g);
        if (!marker) continue;
        const ents = marker.entities || (marker.entity ? [marker.entity] : []);
        const hit = ents.some(
          (e) => bound.has(e) ||
            (this._entityDevice[e] && bound.has(this._entityDevice[e].device_id)),
        );
        if (!hit) continue;
        this._hiPatched.push([g, { style: g.getAttribute('style') }]);
        g.style.filter = `drop-shadow(0 0 5px ${color})`;
        nDev++;
      }
      if (nDev) names.push(`${nDev} bound device(s)`);
    }
    if (names.length) {
      this._status(
        `${dev.display_name || devId} zone → ${names.join(', ')}`
      );
    }
  }

  _markerDblClick(ev, layer) {
    // ev.target may be the ring/path/text — walk up to the marker <g>
    // (direct child of the entities layer).
    let g = ev.target;
    while (g && g.parentElement !== layer) g = g.parentElement;
    if (!g) return;
    const dev = this._deviceOfMarkerEl(g);
    if (dev) this._run(() => this._openDeviceCard(dev));
  }

  async _openDeviceCard(dev) {
    const panel = this.shadowRoot.getElementById('devpanel');
    const host = this.shadowRoot.getElementById('devhost');
    const title = this.shadowRoot.getElementById('devtitle');
    if (!panel || !host) return;

    // The FAN gets its own card; other devices use the native more-info.
    if (dev.device_class === 'FAN' || dev.device_class === 'HVAC') {
      if (!customElements.get('hvac-fan-card')) {
        try {
          await import('/local/ramses_extras/features/hvac_fan_card/hvac-fan-card.js');
        } catch (e) {
          dwarn('hvac-fan-card module failed to load:', e);
        }
      }
      if (customElements.get('hvac-fan-card')) {
        host.innerHTML = '';
        const card = document.createElement('hvac-fan-card');
        card.setConfig({
          type: 'custom:hvac-fan-card',
          device_id: dev.device_id,
        });
        card.hass = this._hass;
        host.appendChild(card);
        this._devCard = card;
        title.textContent =
          `${dev.display_name || dev.device_id} (${dev.device_id})`;
        const view =
          this._tweak('device_view_url') ||
          ((this._fpConfig || {}).device_view_url || '');
        const full = this.shadowRoot.getElementById('devfull');
        if (full) full.style.display = view ? '' : 'none';
        panel.style.display = 'flex';
        return;
      }
    }
    if (dev.primary_entity) {
      this.dispatchEvent(
        new CustomEvent('hass-more-info', {
          detail: { entityId: dev.primary_entity },
          bubbles: true,
          composed: true,
        })
      );
    } else {
      this._status(`No card for ${dev.device_id} (${dev.device_class})`);
    }
  }

  _fillZoneDevices() {
    const sel = this.shadowRoot.getElementById('zone-dev');
    if (!sel) return;
    const zones = ((this._fpConfig || {}).device_zones) || {};
    sel.innerHTML = '<option value="">(device)</option>';
    for (const d of (this._topology && this._topology.devices) || []) {
      const o = document.createElement('option');
      o.value = d.device_id;
      const z = zones[d.device_id];
      o.textContent =
        `${d.device_id} ${d.device_class}` +
        (z ? ` ▸ ${(z.areas || []).join(',')}` : '');
      sel.appendChild(o);
    }
    this._fillZoneColor();
  }

  _fillZoneColor() {
    const sel = this.shadowRoot.getElementById('zone-dev');
    const inp = this.shadowRoot.getElementById('zone-color');
    if (!sel || !inp) return;
    const z = (((this._fpConfig || {}).device_zones || {})[sel.value]) || {};
    inp.value = z.color || '#22c55e';
    inp.disabled = !sel.value;
  }

  async _setZoneColor(color) {
    const devSel = this.shadowRoot.getElementById('zone-dev');
    const devId = devSel && devSel.value;
    if (!devId) return;
    const zone = (((this._fpConfig || {}).device_zones || {})[devId]) || {};
    await this._call('floorplan_set_device_zone', {
      device_id: devId,
      areas: zone.areas || [],
      devices: zone.devices || [],
      color,
    });
    await this._fetchConfig();
    this._status(`Zone ${devId}: colour ${color} — click its marker in studio to preview`);
  }

  async _assignZone() {
    const devSel = this.shadowRoot.getElementById('zone-dev');
    const devId = devSel && devSel.value;
    if (!devId) {
      this._status('Pick a device in the zone row first');
      return;
    }
    const ids = this._studioSelectedRoomIds();
    if (!ids.size) {
      this._status(
        'No rooms selected in studio — shift-click the rooms this device serves first'
      );
      return;
    }
    const rooms = await this._projectRooms();
    const areas = [
      ...new Set(
        [...ids]
          .map((id) => rooms.get(id))
          .filter(Boolean)
          .map((r) => r.areaId)
      ),
    ];
    if (!areas.length) {
      this._status('Selected rooms resolve to no HA areas');
      return;
    }
    const colorInput = this.shadowRoot.getElementById('zone-color');
    const color = (colorInput && colorInput.value) || undefined;
    const existing =
      (((this._fpConfig || {}).device_zones || {})[devId]) || {};
    await this._call('floorplan_set_device_zone', {
      device_id: devId,
      areas,
      devices: existing.devices || [],
      ...(color ? { color } : {}),
    });
    await this._fetchConfig();
    this._status(
      `Zone stored for ${devId}: ${areas.join(', ')}` +
        (color ? ` (${color})` : '') +
        ' — click its marker in studio to highlight'
    );
  }

  async _assignZoneDevices() {
    const devSel = this.shadowRoot.getElementById('zone-dev');
    const devId = devSel && devSel.value;
    if (!devId) {
      this._status('Pick a device in the zone row first');
      return;
    }
    const sel = this._studioSelectedMarkers(true);
    if (!sel.length) {
      this._status('Select marker(s) in studio first (shift-click)');
      return;
    }
    const zones = ((this._fpConfig || {}).device_zones) || {};
    const zone = zones[devId] || {};
    const ids = new Set(zone.devices || []);
    const added = [];
    for (const m of sel) {
      const marker = this._fiberMarker(m.el);
      const ents =
        marker && (marker.entities || (marker.entity ? [marker.entity] : []));
      for (const e of ents || []) {
        // ramses devices bind by device_id; anything else (DIY/zigbee)
        // binds by entity id — a one-way link, so the same member can
        // serve several zones
        const d = this._entityDevice[e];
        const id = d ? d.device_id : e;
        if (id !== devId && !ids.has(id)) {
          ids.add(id);
          added.push(id);
        }
      }
    }
    const colorInput = this.shadowRoot.getElementById('zone-color');
    await this._call('floorplan_set_device_zone', {
      device_id: devId,
      areas: zone.areas || [],
      devices: [...ids],
      color: zone.color || (colorInput && colorInput.value) || undefined,
    });
    await this._fetchConfig();
    this._status(
      `Zone ${devId}: bound devices ${added.length ? `+${added.join(', ')}` : 'unchanged'} ` +
        `(total ${ids.size})`
    );
  }

  async _pull() {
    const project = await this._readStudioProject();
    if (!project) return; // _readStudioProject already reported
    const resized = this._normalizeSizes(project);
    if (resized) {
      // write the normalized sizes back so studio shows them too
      project.updatedAt = Date.now();
      const dbw = await openFpDb();
      await idbReq(
        dbw.transaction('projects', 'readwrite').objectStore('projects').put(project)
      );
      dbw.close();
    }
    await this._storeAndSync(
      JSON.stringify(project),
      `pulled '${project.name || project.id}'` +
        (resized ? `, ${resized} markers resized` : '')
    );
  }

  async _readStudioProject(quiet) {
    const id = this._selectedProjectId();
    if (!id) {
      if (!quiet) this._status('No studio project selected');
      return null;
    }
    const db = await openFpDb();
    const project = await idbReq(
      db.transaction('projects').objectStore('projects').get(id)
    );
    db.close();
    if (!project && !quiet) {
      this._status('Project not found in studio storage');
    }
    return project;
  }

  _normalizeSizes(project) {
    if (this._tweak('normalize_sizes') === false) return 0;
    const size = Number(this._tweak('marker_size'));
    if (!size) return 0;
    let n = 0;
    for (const floor of project.floors || []) {
      for (const m of floor.markers || []) {
        if (m.style && m.style.size !== size) {
          m.style.size = size;
          n += 1;
        }
      }
    }
    return n;
  }

  async _pushToStudio(projectJson) {
    const project = JSON.parse(projectJson);
    project.id = project.id || `seed-${Date.now()}`;
    project.updatedAt = Date.now();
    const db = await openFpDb();
    const tx = db.transaction(['projects', 'meta'], 'readwrite');
    await idbReq(tx.objectStore('projects').put(project));
    // studio reloads `meta:lastProjectId` on mount — point it at the
    // project we just wrote so a remount lands on it
    await idbReq(tx.objectStore('meta').put(project.id, 'lastProjectId'));
    db.close();
    return project;
  }

  // After an IndexedDB write, an open studio still shows its stale
  // in-memory copy — and its autosave would clobber our write on the
  // next edit. Remount the card so it reloads the pushed project.
  _reloadStudioCard() {
    const el = _deepQuery('floorplan-studio-card');
    if (el && el.mounted) {
      el.disconnectedCallback();
      el.connectedCallback();
      return true;
    }
    return false;
  }

  async _seed() {
    const data = {};
    if (this._config.floors) data.floors = this._config.floors;
    const size = this._tweak('marker_size');
    if (size) data.marker_size = size;
    const seedName = this._tweak('seed_name');
    if (seedName) data.name = seedName;
    // Merge into the selected studio project when one is open — keeps
    // walls, background and existing placement, only *new* devices get
    // centroid markers. Without a selection the service falls back to
    // the stored latest.json; with neither it emits a fresh project.
    const selected = await this._readStudioProject(true);
    if (selected) data.project_json = JSON.stringify(selected);
    const r = await this._call('floorplan_seed_studio', data);
    const placed = Object.keys(r.placed || {}).length;
    const unplaced = (r.unplaced || []).length;
    if (r.project_json) {
      try {
        const p = await this._pushToStudio(r.project_json);
        const reloaded = this._reloadStudioCard();
        this._status(
          `Seeded: ${placed} placed, ${unplaced} parked — merged into studio project '${p.name}'` +
            (reloaded
              ? ' (studio reloaded).'
              : ' (select it via Projects if it isn\'t open).'),
        );
      } catch {
        this._copy(r.project_json, 'Project JSON');
        this._status(`Seeded: ${placed} placed, ${unplaced} parked — could not write to studio storage; JSON copied to clipboard instead.`);
      }
      this._refreshProjects();
    } else {
      this._status(`Seeded: ${placed} placed, ${unplaced} parked`);
    }
  }

  async _pushStored() {
    const r = await this._hass.callWS({
      type: 'ramses_extras/floorplan_helper/get_project',
    }).catch((err) => ({ __err: (err && err.message) || String(err) }));
    if (r.__err) {
      this._status(`Push → studio: ${r.__err}`);
      return;
    }
    const p = await this._pushToStudio(r.project_json);
    const reloaded = this._reloadStudioCard();
    this._status(
      `Pushed stored project '${p.name || p.id}' into studio` +
        (reloaded
          ? ' — studio reloaded.'
          : ' — open it via Projects (studio autosaves to this browser).')
    );
    this._refreshProjects();
  }

  async _export() {
    // Snapshot live studio state first — the merged-SVG export reads
    // latest.json, so unsaved drags/recolours must be stored or they
    // silently don't make it into the output.
    const project = await this._readStudioProject();
    let stored = '';
    if (project) {
      const resized = this._normalizeSizes(project);
      const s = await this._call('floorplan_store_project', {
        project_json: JSON.stringify(project),
      });
      stored = ` (project snapshot: ${s.latest_path}` +
        (resized ? `, ${resized} markers resized` : '') + ')';
      if (this._tweak('sync_on_pull') !== false) {
        await this._call('floorplan_sync_areas', {});
      }
    }
    // the service applies the generated card to matching storage
    // dashboards itself (apply:false / apply_dashboard / apply_match
    // are passed through from this card's config)
    const data = {};
    if (this._config.apply === false) data.apply = false;
    if (this._config.apply_dashboard) data.apply_dashboard = this._config.apply_dashboard;
    if (this._config.apply_match) data.apply_match = this._config.apply_match;
    const r = await this._call('floorplan_export', data);
    const yamls = r.card_yamls || (r.card_yaml ? { default: r.card_yaml } : {});
    const floors = Object.keys(yamls);
    this._renderYamlButtons(yamls);
    const applied =
      r.applied && r.applied.cards
        ? ` — applied to ${r.applied.cards} card(s) on ${r.applied.dashboards} dashboard(s)`
        : data.apply !== false
          ? ' — no matching floorplan card found (nothing applied)'
          : '';
    if (floors.length) {
      this._copy(yamls[floors[0]], `card yaml (${floors[0]})`);
      this._status(
        `Exported ${(r.rules || []).length} rules${stored} — ` +
          `card yaml for '${floors[0]}' copied` +
          (floors.length > 1
            ? `; ${floors.length} floors — use the copy buttons below for the other card(s).`
            : '.') +
          applied,
      );
    } else {
      this._status(`Export finished${stored} (no card_yaml in response)${applied}`);
    }
  }

  // Dashboard apply lives server-side in floorplan_export — every
  // export path (this button, the in-SVG toolbar, automations)
  // replaces cards whose image.location matches a generated map.

  _renderYamlButtons(yamls) {
    const row = this.shadowRoot.getElementById('yaml-copies');
    if (!row) return;
    row.innerHTML = '';
    const floors = Object.keys(yamls || {});
    if (!floors.length) {
      row.style.display = 'none';
      return;
    }
    const lbl = document.createElement('span');
    lbl.className = 'lbl';
    lbl.textContent = 'card yaml →';
    row.appendChild(lbl);
    for (const floor of floors) {
      const b = document.createElement('button');
      b.className = 'secondary';
      b.textContent = `⧉ ${floor}`;
      b.title = `Copy the floorplan card yaml for '${floor}' — paste as a separate card (e.g. one per floor)`;
      b.onclick = () => this._copy(yamls[floor], `card yaml (${floor})`);
      row.appendChild(b);
    }
    row.style.display = 'flex';
  }

  async _sync() {
    const r = await this._call('floorplan_sync_areas', {});
    this._status(this._syncSummary(r));
  }

  _syncSummary(r) {
    const a = Object.keys(r.assignments || {}).length;
    const d = (r.assigned_via_device || []).length;
    const c = (r.areas_created || []).length;
    const o = (r.entities_without_area_room || []).length;
    return `Sync: ${a} entities assigned` +
      (d ? ` (${d} via device)` : '') +
      `, ${c} areas created` +
      (o ? `, ${o} outside rooms` : '') +
      (r.backup_path ? `\nbackup: ${r.backup_path}` : '');
  }

  async _storeAndSync(text, via) {
    const r = await this._call('floorplan_store_project', { project_json: text });
    let msg = `Project ${via || 'stored'}: ${r.latest_path}`;
    if (this._tweak('sync_on_pull') !== false) {
      const s = await this._call('floorplan_sync_areas', {});
      msg += `\n${this._syncSummary(s)}`;
    }
    this._status(msg);
  }

  _readFile(file) {
    const reader = new window.FileReader();
    reader.onload = () =>
      this._run(() => this._storeAndSync(String(reader.result || ''), `file '${file.name}'`));
    reader.readAsText(file);
  }

  _render() {
    this.shadowRoot.innerHTML = `
      <style>${STYLE}</style>
      <ha-card>
        <div class="title">Floorplan</div>
        <div class="hint">
          Edit markers in studio, store the project, export — the studio
          project is the source of truth; export compiles it into the
          floorplan bundle (rules + CSS + card YAML).
        </div>
        <div class="row">
          <button id="b-studio"
            title="Open the floorplan-studio editor (editor_url from your floorplan settings)">Open studio</button>
          <span class="lbl">studio project:</span>
          <select id="project"
            title="Projects stored in floorplan-studio (this browser). The one studio is currently editing is marked (current)."></select>
          <button id="b-pull" class="secondary"
            title="Read the selected project straight from studio (it autosaves ~0.6s after each change), store it as latest.json + backup, and sync marker positions into HA areas">⟵ Store ← studio</button>
          <button id="b-export" class="secondary"
            title="Snapshot the selected studio project, regenerate the ha-floorplan bundle (SVG + rules + CSS) and copy the dashboard card YAML to your clipboard">Export ⇒</button>
        </div>
        <div class="row">
          <button id="b-seed" class="secondary"
            title="Add markers for devices not yet in the selected project — merged into it (existing placement kept; new devices at their room's centre or parked below the canvas), written back into studio">＋ Add devices</button>
          <button id="b-push" class="secondary"
            title="Write the stored latest.json back into this browser's studio project list — restores the project after a browser/profile switch">⇒ Push → studio</button>
          <button id="b-sync" class="secondary"
            title="Re-run area sync on the stored project: marker-in-room → entity area_id, missing areas created">Sync areas</button>
          <button id="b-tweaks" class="secondary"
            title="Card tweaks — saved in this browser">⚙ Tweaks</button>
        </div>
        <div class="tweaks" id="tweaks" style="display:none">
          <div class="row">
            <label for="tw-sync" title="After Pull (or a dropped file), also run area sync automatically">Sync areas on pull</label>
            <input id="tw-sync" type="checkbox">
          </div>
          <div class="row">
            <label for="tw-norm" title="On Pull, set every marker's icon size in the project to marker_size (yaml config, default 20) — also writes it back to studio so manually placed markers (studio default 40) get fixed">Normalize icon sizes on pull</label>
            <input id="tw-norm" type="checkbox">
          </div>
          <div class="row">
            <label for="zone-dev" title="A zone = the rooms a device serves + the extra markers bound to it. Tap the device's marker in studio → its rooms and bound markers light up in the zone colour.">Zone →</label>
            <select id="zone-dev" style="max-width:220px"
              title="Device whose zone you are editing — its current zone areas are shown after ▸"></select>
            <input id="zone-color" type="color" style="width:36px;padding:0;height:24px"
              title="This zone's highlight colour — stored on the zone itself, applies on change">
            <button id="b-zone" class="secondary"
              title="1) pick the device, 2) shift-click its rooms in studio, 3) click — stores the selected rooms as the zone">◧ rooms → zone</button>
            <button id="b-zonedev" class="secondary"
              title="1) pick the device, 2) shift-click markers in studio, 3) click — binds them to the zone (they highlight on tap too). Works for non-ramses entities (DIY valves, zigbee sensors); ramses devices in the schema need no entry">◉ markers → zone</button>
          </div>
          <div class="row">
            <label for="tw-zonewatch" title="When a marker is selected in studio, outline the rooms its device serves (device_zones config); double-click a marker to open the device card">Highlight zones on select</label>
            <input id="tw-zonewatch" type="checkbox">
          </div>
          <div class="row">
            <label for="tw-devview" title="Optional dashboard path for device details (e.g. /lovelace/hvac) — a '⤢ dashboard' button appears in the device popup">Device dashboard URL</label>
            <input id="tw-devview" type="text" placeholder="/lovelace/hvac" style="width:200px">
          </div>
        </div>
        <div class="drop" id="drop"
          title="For project files from another machine or a backup — this browser's studio is already reachable via Pull">
          Drop a studio project JSON here (or click to browse) — fallback
          for files from another machine or backup
          <input id="file" type="file" accept=".json,application/json">
        </div>
        <textarea class="log" id="status" readonly
          title="Result log — selectable, copy with Ctrl+C"></textarea>
        <div class="row" id="yaml-copies" style="display:none"></div>
        <div class="devoverlay" id="devpanel" style="display:none">
          <div class="devdialog">
            <div class="row" style="justify-content:space-between">
              <span class="lbl" id="devtitle"></span>
              <span>
                <button id="devfull" class="secondary" style="display:none"
                  title="Open the dashboard view configured for this device">⤢ dashboard</button>
                <button id="devclose" class="secondary" title="Close">✕</button>
              </span>
            </div>
            <div id="devhost"></div>
          </div>
        </div>
      </ha-card>`;

    const $ = (id) => this.shadowRoot.getElementById(id);
    $('b-studio').onclick = () =>
      this._navigate(this._config.studio_url || (this._fpConfig || {}).editor_url || '/floorplan-studio');
    $('b-pull').onclick = () => this._run(() => this._pull());
    $('b-seed').onclick = () => this._run(() => this._seed());
    $('b-push').onclick = () => this._run(() => this._pushStored());
    $('b-export').onclick = () => this._run(() => this._export());
    $('b-sync').onclick = () => this._run(() => this._sync());
    $('b-tweaks').onclick = () => {
      const t = $('tweaks');
      t.style.display = t.style.display === 'none' ? 'block' : 'none';
    };

    // tweaks panel — values persist in localStorage, override YAML config
    const twSync = $('tw-sync');
    const twNorm = $('tw-norm');
    twSync.checked = this._tweak('sync_on_pull') !== false;
    twNorm.checked = this._tweak('normalize_sizes') !== false;
    twSync.onchange = () => this._saveTweak('sync_on_pull', twSync.checked);
    twNorm.onchange = () => this._saveTweak('normalize_sizes', twNorm.checked);

    // zone row: colour is stored on the zone itself (SSOT), shown and
    // edited for the device picked in the dropdown
    $('zone-dev').onchange = () => this._fillZoneColor();
    $('zone-color').onchange = (e) => this._run(() => this._setZoneColor(e.target.value));
    $('b-zone').onclick = () => this._run(() => this._assignZone());
    $('b-zonedev').onclick = () => this._run(() => this._assignZoneDevices());
    const twWatch = $('tw-zonewatch');
    twWatch.checked = this._tweak('zone_watch') !== false;
    twWatch.onchange = () => {
      this._saveTweak('zone_watch', twWatch.checked);
      if (!twWatch.checked) {
        this._hiDevice = null;
        this._clearZoneHighlight();
      }
    };
    this._fillZoneDevices();
    const closePanel = () => {
      $('devpanel').style.display = 'none';
      this._devCard = null;
    };
    $('devclose').onclick = closePanel;
    $('devpanel').onclick = (e) => {
      if (e.target.id === 'devpanel') closePanel();
    };
    $('devfull').onclick = () => {
      const url = this._tweak('device_view_url');
      if (url) {
        closePanel();
        this._navigate(url);
      }
    };
    const twDevView = $('tw-devview');
    twDevView.value = this._tweak('device_view_url') || '';
    twDevView.onchange = () =>
      this._saveTweak('device_view_url', twDevView.value || undefined);

    this._fillProjectSelect();

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
}

customElements.define('ramses-floorplan-actions', RamsesFloorplanActions);

// ---------------------------------------------------------------------------
// Global device popup
// ---------------------------------------------------------------------------
// ha-floorplan rules fire 'll-custom' (composed + bubbles) with
// {ramses_device_id, ramses_entity, ramses_card} on a zoned marker's
// double_tap. This listener lives at module level — once the file is
// loaded as a Lovelace resource it works on ANY view; the actions card
// itself does not have to be rendered.

const FP_POPUP_ID = 'ramses-fp-device-popup';
let _fpPopCard = null;   // the embedded device card element
let _fpPopHassTimer = null; // keeps card.hass fresh while open
let _fpPopView; // undefined = not fetched yet

function _fpHass() {
  const ha = document.querySelector('home-assistant');
  return ha ? ha.hass : null;
}

function _fpPopClose() {
  const el = document.getElementById(FP_POPUP_ID);
  if (el) el.remove();
  _fpPopCard = null;
  if (_fpPopHassTimer) {
    clearInterval(_fpPopHassTimer);
    _fpPopHassTimer = null;
  }
}

async function _fpDeviceViewUrl(hass) {
  if (_fpPopView !== undefined) return _fpPopView;
  try {
    const cfg = await hass.callWS({
      type: 'ramses_extras/floorplan_helper/get_config',
    });
    _fpPopView = cfg.device_view_url || '';
  } catch {
    _fpPopView = '';
  }
  return _fpPopView;
}

// Create-or-reuse the shared overlay shell; returns the .host element
// ready for content. Hides the "⤢ dashboard" button by default.
function _fpPopupShell() {
  let pop = document.getElementById(FP_POPUP_ID);
  if (!pop) {
    pop = document.createElement('div');
    pop.id = FP_POPUP_ID;
    pop.innerHTML = `
      <style>
        #${FP_POPUP_ID} {
          position: fixed; inset: 0; z-index: 999;
          display: flex; align-items: center; justify-content: center;
          background: rgba(0,0,0,0.5);
        }
        #${FP_POPUP_ID} .dlg {
          background: var(--card-background-color, #fff);
          color: var(--primary-text-color);
          border-radius: 12px; box-shadow: 0 8px 30px rgba(0,0,0,0.4);
          width: min(440px, 92vw); max-height: 85vh; overflow-y: auto;
          padding: 10px 14px 14px;
        }
        #${FP_POPUP_ID} .head {
          display: flex; align-items: center;
          justify-content: space-between; margin-bottom: 6px;
        }
        #${FP_POPUP_ID} .lbl { font-size: 14px; font-weight: 600; }
        #${FP_POPUP_ID} button {
          background: none; border: 1px solid var(--divider-color, #ccc);
          border-radius: 6px; color: inherit; cursor: pointer;
          padding: 3px 8px; font-size: 12px;
        }
        #${FP_POPUP_ID} textarea {
          width: 100%; box-sizing: border-box; min-height: 140px;
          background: var(--secondary-background-color, transparent);
          color: inherit; border: 1px solid var(--divider-color, #ccc);
          border-radius: 6px; font-family: monospace; font-size: 11px;
          padding: 6px; margin-bottom: 6px;
        }
        #${FP_POPUP_ID} input[type='text'], #${FP_POPUP_ID} input[type='file'] {
          width: 100%; box-sizing: border-box; color: inherit;
          border: 1px solid var(--divider-color, #ccc); border-radius: 6px;
          padding: 4px 6px; margin-bottom: 6px; background: transparent;
        }
        #${FP_POPUP_ID} .msg { font-size: 12px; margin: 4px 0; }
        #${FP_POPUP_ID} .err { font-size: 12px; margin: 4px 0; color: #e53935; }
        #${FP_POPUP_ID} .warn { font-size: 11px; margin: 2px 0; opacity: 0.75; }
        #${FP_POPUP_ID} .ybtn { margin: 2px 6px 2px 0; }
      </style>
      <div class="dlg">
        <div class="head">
          <span class="lbl"></span>
          <span>
            <button class="view" style="display:none">⤢ dashboard</button>
            <button class="x">✕</button>
          </span>
        </div>
        <div class="host"></div>
      </div>`;
    pop.addEventListener('click', (e) => {
      if (e.target === pop) _fpPopClose();
    });
    pop.querySelector('.x').addEventListener('click', _fpPopClose);
    pop.querySelector('.view').addEventListener('click', () => {
      if (_fpPopView) {
        _fpPopClose();
        window.history.pushState(null, '', _fpPopView);
        window.dispatchEvent(new window.Event('location-changed'));
      }
    });
    document.body.appendChild(pop);
  }
  pop.querySelector('.view').style.display = 'none';
  const host = pop.querySelector('.host');
  host.innerHTML = '';
  _fpPopCard = null;
  if (_fpPopHassTimer) {
    clearInterval(_fpPopHassTimer);
    _fpPopHassTimer = null;
  }
  return pop;
}

async function _fpCallService(service, data) {
  const hass = _fpHass();
  if (!hass) throw new Error('hass not ready');
  const r = await hass.callWS({
    type: 'call_service',
    domain: DOMAIN,
    service,
    service_data: data || {},
    return_response: true,
  });
  return (r && r.response) || {};
}

// Dialogs for the in-SVG toolbar buttons — export/import/upload need a
// response or user input, so they run through ll-custom rather than a
// plain call-service/navigate rule.
async function _openFpActionDialog(action) {
  const titles = {
    export: 'Export floorplan bundle',
    import: 'Import floorplan YAML',
    upload: 'Upload SVG',
  };
  const pop = _fpPopupShell();
  pop.querySelector('.lbl').textContent = titles[action] || action;
  const host = pop.querySelector('.host');
  if (action === 'export') _fpExportDialog(host);
  else if (action === 'import') _fpImportDialog(host);
  else if (action === 'upload') _fpUploadDialog(host);
}

function _fpMsg(host, text, cls) {
  const div = document.createElement('div');
  div.className = cls || 'msg';
  div.textContent = text;
  host.appendChild(div);
  return div;
}

async function _fpExportDialog(host) {
  _fpMsg(host, 'Exporting…');
  try {
    const r = await _fpCallService('floorplan_export', {});
    host.innerHTML = '';
    const files = r.files_written || {};
    _fpMsg(
      host,
      `Wrote ${Object.keys(files).length} file(s) to /local/ramses_extras/floorplan/generated/` +
        (r.applied && r.applied.cards
          ? ` — applied to ${r.applied.cards} card(s) on ${r.applied.dashboards} dashboard(s)`
          : '')
    );
    for (const w of r.warnings || []) _fpMsg(host, w, 'warn');
    const yamls =
      r.card_yamls || (r.card_yaml ? { default: r.card_yaml } : {});
    for (const [stem, yml] of Object.entries(yamls)) {
      const b = document.createElement('button');
      b.className = 'ybtn';
      b.textContent = `⧉ ${stem}`;
      b.addEventListener('click', () => {
        navigator.clipboard.writeText(yml).then(
          () => {
            b.textContent = `✓ ${stem}`;
          },
          () => {
            b.textContent = `⧉ ${stem} — copy failed`;
          }
        );
      });
      host.appendChild(b);
    }
  } catch (e) {
    host.innerHTML = '';
    _fpMsg(host, `Export failed: ${(e && e.message) || e}`, 'err');
  }
}

function _fpImportDialog(host) {
  const ta = document.createElement('textarea');
  ta.placeholder = 'Paste floorplan YAML (element bindings / extra rules)…';
  host.appendChild(ta);
  const b = document.createElement('button');
  b.textContent = 'Import';
  host.appendChild(b);
  const out = _fpMsg(host, '', 'msg');
  b.addEventListener('click', async () => {
    out.textContent = 'Importing…';
    try {
      const r = await _fpCallService('floorplan_import', {
        yaml_text: ta.value,
      });
      out.textContent =
        `Imported ${r.bindings_imported || 0} binding(s), ` +
        `${r.rules_kept || 0} rule(s) kept`;
      for (const w of r.warnings || []) _fpMsg(host, w, 'warn');
    } catch (e) {
      out.className = 'err';
      out.textContent = `Import failed: ${(e && e.message) || e}`;
    }
  });
}

function _fpUploadDialog(host) {
  const name = document.createElement('input');
  name.type = 'text';
  name.placeholder = 'filename.svg (optional — defaults to the file name)';
  host.appendChild(name);
  const file = document.createElement('input');
  file.type = 'file';
  file.accept = '.svg,image/svg+xml';
  host.appendChild(file);
  const b = document.createElement('button');
  b.textContent = 'Upload';
  host.appendChild(b);
  const out = _fpMsg(host, '', 'msg');
  b.addEventListener('click', () => {
    const f = file.files && file.files[0];
    if (!f) {
      out.className = 'err';
      out.textContent = 'Pick an SVG file first';
      return;
    }
    const reader = new FileReader();
    reader.onload = async () => {
      out.className = 'msg';
      out.textContent = 'Uploading…';
      try {
        const r = await _fpCallService('floorplan_upload_svg', {
          filename: name.value || f.name,
          svg_text: String(reader.result || ''),
        });
        out.textContent = `Written: ${r.path || r.filename || 'ok'}`;
      } catch (e) {
        out.className = 'err';
        out.textContent = `Upload failed: ${(e && e.message) || e}`;
      }
    };
    reader.readAsText(f);
  });
}

async function _openGlobalDevicePopup(detail) {
  const hass = _fpHass();
  if (!hass) return;
  const deviceId = detail.ramses_device_id;

  const pop = _fpPopupShell();
  pop.querySelector('.lbl').textContent = deviceId;
  const viewUrl = await _fpDeviceViewUrl(hass);
  pop.querySelector('.view').style.display = viewUrl ? '' : 'none';

  const host = pop.querySelector('.host');

  if (detail.ramses_card === 'hvac-fan') {
    if (!customElements.get('hvac-fan-card')) {
      try {
        await import(
          '/local/ramses_extras/features/hvac_fan_card/hvac-fan-card.js'
        );
      } catch (e) {
        dwarn('hvac-fan-card module failed to load:', e);
      }
    }
    if (customElements.get('hvac-fan-card')) {
      const card = document.createElement('hvac-fan-card');
      card.setConfig({
        type: 'custom:hvac-fan-card',
        device_id: deviceId,
      });
      card.hass = hass;
      host.appendChild(card);
      _fpPopCard = card;
    }
  }
  if (!_fpPopCard) {
    // fallback: native entity dialog
    _fpPopClose();
    if (detail.ramses_entity) {
      document.querySelector('home-assistant').dispatchEvent(
        new CustomEvent('hass-more-info', {
          detail: { entityId: detail.ramses_entity },
          bubbles: true,
          composed: true,
        })
      );
    }
    return;
  }

  // Keep the embedded card's hass fresh while the popup is open —
  // it has no card parent pushing updates to it.
  if (_fpPopHassTimer) clearInterval(_fpPopHassTimer);
  _fpPopHassTimer = setInterval(() => {
    const h = _fpHass();
    if (h && _fpPopCard) _fpPopCard.hass = h;
  }, 1000);
}

// Zone tap rules call ramses_extras.floorplan_zone_toggle — a real HA
// service (studio-expressible, unlike fire-dom-event lists) that fires
// an event we subscribe to here. The handler applies the class
// toggles to EVERY floorplan card, so a FAN's served rooms + bound
// devices light up on all floors (and all open browsers) at once.
// The legacy ll-custom path stays for previously exported yaml.
function _fpFloorplanCards() {
  const cards = [];
  const walk = (root) => {
    for (const el of root.querySelectorAll('*')) {
      if (el.tagName === 'FLOORPLAN-CARD') cards.push(el);
      if (el.shadowRoot) walk(el.shadowRoot);
    }
  };
  walk(document);
  return cards;
}

function _fpZoneApply(toggles, clear, skipCard) {
  for (const card of _fpFloorplanCards()) {
    if (skipCard && card === skipCard) continue;
    if (clear && !(toggles || []).length) {
      // blanket clear: strip every rx-zone-* class on this card —
      // used by the device-view bridge before the popup opens
      const strip = (root) => {
        for (const el of root.querySelectorAll('[class]')) {
          for (const c of [...(el.classList || [])]) {
            if (c.startsWith('rx-zone-')) el.classList.remove(c);
          }
        }
      };
      strip(card.shadowRoot || card);
      continue;
    }
    for (const t of toggles || []) {
      for (const id of t.elements || []) {
        const node =
          _fpDeepById(card.shadowRoot, id) || _fpDeepById(card, id);
        if (node) {
          if (clear) node.classList.remove(t.class);
          else node.classList.toggle(t.class);
        }
      }
    }
  }
}

// legacy ll-custom broadcast: origin card already class_toggle'd
// itself, so it is skipped (clear must include it — the highlight came
// from an earlier tap)
function _fpZoneSync(ev, toggles, clear) {
  const path = ev.composedPath ? ev.composedPath() : [];
  _fpZoneApply(
    toggles,
    clear,
    clear ? null : _fpFloorplanCards().find((c) => path.includes(c))
  );
}

function _fpDeepById(root, id) {
  if (!root) return null;
  const node = root.getElementById ? root.getElementById(id) : null;
  if (node) return node;
  for (const el of root.querySelectorAll('*')) {
    if (el.id === id) return el;
    if (el.shadowRoot) {
      const hit = _fpDeepById(el.shadowRoot, id);
      if (hit) return hit;
    }
  }
  return null;
}

window.addEventListener('ll-custom', (ev) => {
  const d = ev && ev.detail;
  if (d && d.ramses_device_id) _openGlobalDevicePopup(d);
  if (d && d.ramses_zone_sync) _fpZoneSync(ev, d.ramses_zone_sync);
  if (d && d.ramses_zone_clear) _fpZoneSync(ev, d.ramses_zone_clear, true);
  if (d && d.ramses_fp_action) _openFpActionDialog(d.ramses_fp_action);
});

// --- Backend event bridges ---------------------------------------------
// Marker gestures call real HA services (ramses_extras.floorplan_*),
// which is the only shape studio's action editor can express — the
// service fires one of these events and every open dashboard reacts.
// Subscribe as soon as a hass connection exists.
let _fpEventsBound = false;
function _fpBindEvents() {
  if (_fpEventsBound) return;
  const hass = _fpHass();
  if (!hass || !hass.connection || !hass.connection.subscribeEvents) return;
  _fpEventsBound = true;
  hass.connection.subscribeEvents(
    (e) => {
      const d = (e && e.data) || {};
      _fpZoneApply(d.toggles, !!d.clear);
    },
    'ramses_extras_floorplan_zone_toggle'
  );
  hass.connection.subscribeEvents(
    (e) => {
      const d = (e && e.data) || {};
      // clear every zone highlight first — a fast second tap is eaten
      // as a double tap, so a deterministic clear keeps "tap again to
      // deselect" from leaving a lit zone behind the popup
      _fpZoneApply(null, true);
      _openGlobalDevicePopup({
        ramses_device_id: d.device_id,
        ramses_entity: d.entity,
        ramses_card: d.card,
      });
    },
    'ramses_extras_floorplan_device_view'
  );
}
_fpBindEvents();
if (!_fpEventsBound) {
  const _fpEvtTimer = setInterval(() => {
    _fpBindEvents();
    if (_fpEventsBound) clearInterval(_fpEvtTimer);
  }, 1500);
}

// --- Pan/zoom on floorplan card SVGs ----------------------------------
// ha-floorplan has no zoom support — we pan/zoom by rewriting the svg's
// viewBox, so element ids, taps and generated rules all keep working.
// Deliberately non-intrusive on a scrolling dashboard:
//   wheel            zooms only with Ctrl/Cmd held (plain wheel = page
//                    scroll, unless already zoomed in — then it keeps
//                    zooming)
//   pinch (2-finger) zooms always — distinct from one-finger scroll
//   drag             pans only while zoomed in
//   dblclick on the  zooms in 2x; when zoomed, resets to full view
//   background
const _FP_PZ_MIN = 0.05; // deepest zoom-in factor vs. base viewBox

function _fpPzSvgPoint(svg, clientX, clientY) {
  const ctm = svg.getScreenCTM && svg.getScreenCTM();
  if (!ctm) return null;
  const pt = svg.createSVGPoint();
  pt.x = clientX;
  pt.y = clientY;
  return pt.matrixTransform(ctm.inverse());
}

function _fpPzBase(svg) {
  // Full-drawing viewBox, captured once — reset target.
  if (!svg._rxPzBase) {
    const vb = svg.viewBox.baseVal;
    svg._rxPzBase = { x: vb.x, y: vb.y, w: vb.width, h: vb.height };
  }
  return svg._rxPzBase;
}

function _fpPzScale(svg) {
  const base = _fpPzBase(svg);
  return base.w / svg.viewBox.baseVal.width;
}

function _fpPzZoomAt(svg, loc, factor) {
  const vb = svg.viewBox.baseVal;
  const base = _fpPzBase(svg);
  const minW = base.w * _FP_PZ_MIN;
  const newW = Math.max(minW, Math.min(base.w, vb.width / factor));
  const clamped = vb.width / newW; // effective factor after min/max clamp
  vb.x = loc.x - (loc.x - vb.x) / clamped;
  vb.y = loc.y - (loc.y - vb.y) / clamped;
  vb.width = newW;
  vb.height = vb.width / (base.w / base.h); // keep aspect
}

function _fpPzReset(svg) {
  const base = _fpPzBase(svg);
  const vb = svg.viewBox.baseVal;
  vb.x = base.x;
  vb.y = base.y;
  vb.width = base.w;
  vb.height = base.h;
}

function _fpPzInit(svg) {
  if (svg._rxPz) return;
  svg._rxPz = { pointers: new Map(), drag: null, pinch: null };
  const st = svg._rxPz;

  svg.addEventListener(
    'wheel',
    (ev) => {
      // plain wheel stays page scroll — except while zoomed in, where
      // zooming is the expected gesture
      if (!(ev.ctrlKey || ev.metaKey) && _fpPzScale(svg) <= 1.001) return;
      const loc = _fpPzSvgPoint(svg, ev.clientX, ev.clientY);
      ev.preventDefault();
      if (!loc) return;
      _fpPzZoomAt(svg, loc, ev.deltaY < 0 ? 1.25 : 0.8);
    },
    { passive: false },
  );

  svg.addEventListener('pointerdown', (ev) => {
    st.pointers.set(ev.pointerId, { x: ev.clientX, y: ev.clientY });
    if (st.pointers.size === 1 && _fpPzScale(svg) > 1.001) {
      st.drag = { x: ev.clientX, y: ev.clientY };
    } else if (st.pointers.size === 2) {
      const [a, b] = [...st.pointers.values()];
      st.pinch = {
        dist: Math.hypot(a.x - b.x, a.y - b.y),
        cx: (a.x + b.x) / 2,
        cy: (a.y + b.y) / 2,
      };
      st.drag = null;
    }
  });

  svg.addEventListener('pointermove', (ev) => {
    if (!st.pointers.has(ev.pointerId)) return;
    st.pointers.set(ev.pointerId, { x: ev.clientX, y: ev.clientY });
    if (st.pinch && st.pointers.size === 2) {
      const [a, b] = [...st.pointers.values()];
      const dist = Math.hypot(a.x - b.x, a.y - b.y);
      const loc = _fpPzSvgPoint(svg, st.pinch.cx, st.pinch.cy);
      if (loc && st.pinch.dist > 0) {
        _fpPzZoomAt(svg, loc, dist / st.pinch.dist);
      }
      st.pinch = { dist, cx: (a.x + b.x) / 2, cy: (a.y + b.y) / 2 };
      ev.preventDefault();
    } else if (st.drag) {
      const ctm = svg.getScreenCTM && svg.getScreenCTM();
      if (!ctm || !ctm.a) return;
      const vb = svg.viewBox.baseVal;
      const dx = (st.drag.x - ev.clientX) / ctm.a;
      const dy = (st.drag.y - ev.clientY) / ctm.a;
      if (Math.abs(dx) + Math.abs(dy) < 0.01) return;
      const base = _fpPzBase(svg);
      // keep the visible window inside the drawing
      vb.x = Math.min(base.x + base.w - vb.width, Math.max(base.x, vb.x + dx));
      vb.y = Math.min(base.y + base.h - vb.height, Math.max(base.y, vb.y + dy));
      st.drag = { x: ev.clientX, y: ev.clientY };
      ev.preventDefault();
    }
  });

  const _end = (ev) => {
    st.pointers.delete(ev.pointerId);
    if (st.pointers.size < 2) st.pinch = null;
    if (st.pointers.size === 0) st.drag = null;
  };
  svg.addEventListener('pointerup', _end);
  svg.addEventListener('pointercancel', _end);
  svg.addEventListener('pointerleave', _end);

  svg.addEventListener('dblclick', (ev) => {
    // a dblclick on a generated marker/toolbar is ha-floorplan's
    // double-tap action, not a zoom gesture — everything else zooms
    // in when at rest and resets while zoomed
    for (let n = ev.target; n && n !== svg; n = n.parentNode) {
      if (n.id === 'floorplan.markers' || n.id === 'floorplan.toolbar') return;
    }
    if (_fpPzScale(svg) > 1.001) {
      _fpPzReset(svg);
      return;
    }
    const loc = _fpPzSvgPoint(svg, ev.clientX, ev.clientY);
    if (loc) _fpPzZoomAt(svg, loc, 2);
  });
}

// Attach to every floorplan-card svg. A document-level observer can't
// see inside shadow DOM, so each discovered card's shadowRoot gets its
// own observer (the svg appears late and is replaced on re-render);
// a slow rescan is the backstop for anything else.
function _fpPzScan() {
  const walk = (root) => {
    for (const el of root.querySelectorAll('*')) {
      if (el.tagName === 'FLOORPLAN-CARD' && el.shadowRoot) {
        const svg = el.shadowRoot.querySelector('svg');
        if (svg) _fpPzInit(svg);
        if (!el._rxPzObserved) {
          el._rxPzObserved = true;
          new window.MutationObserver(() => {
            const s = el.shadowRoot && el.shadowRoot.querySelector('svg');
            if (s) _fpPzInit(s);
          }).observe(el.shadowRoot, { childList: true, subtree: true });
        }
      }
      if (el.shadowRoot) walk(el.shadowRoot);
    }
  };
  walk(document);
}
_fpPzScan();
new window.MutationObserver(_fpPzScan).observe(document.body, {
  childList: true,
  subtree: true,
});
setInterval(_fpPzScan, 2500);

window.customCards = window.customCards || [];
window.customCards.push({
  type: 'ramses-floorplan-actions',
  name: 'Ramses Floorplan Actions',
  description: 'Action bar + studio project bridge for floorplan-studio workflows',
});
