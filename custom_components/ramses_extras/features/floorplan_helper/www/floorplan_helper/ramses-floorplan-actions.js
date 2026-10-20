/**
 * Ramses Floorplan Actions card
 *
 * Companion bar for floorplan-studio: full-width card meant to sit
 * below (or above) the studio card on the same view.
 *
 * Studio stores its projects in this origin's IndexedDB
 * (db 'floorplan-studio', store 'projects', meta 'lastProjectId') and
 * autosaves ~600ms after every change — so this card can pull the live
 * project and push seeded projects with no export/download round-trip:
 *
 *   - Project picker lists studio's own projects; "Pull" stores it
 *     server-side (latest.json + backup) and syncs HA areas
 *   - "Seed markers" runs floorplan_seed_studio and writes the result
 *     back into studio's project list (open it via Projects)
 *   - "Open studio" / "Open editor" navigate to the configured tool URLs
 *   - "Export bundle" runs floorplan_export and copies card_yaml
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

  _fiberCommit(f, label) {
    // Scan a fiber's hook list for the first function-valued hook — in
    // studio's panels that is useStore((s) => s.commit).
    let h = f.memoizedState;
    let hi = 0;
    while (h) {
      const v = h.memoizedState;
      dlog(`  ${label} hook[${hi}] type=${typeof v}`,
        v && typeof v === 'object' ? Object.keys(v) : v);
      const cand =
        typeof v === 'function' ? v
        : v && typeof v.value === 'function' ? v.value
        : null;
      if (cand) {
        dlog(`commit candidate at ${label} hook[${hi}]`);
        return cand;
      }
      h = h.next;
      hi += 1;
    }
    return null;
  }

  _studioCommit() {
    // Studio persists edits via store.commit(recipe) (immer produce →
    // set → re-render + autosave + undo history). Two ways to lift the
    // function: LayerPanel (.fp-layers — always mounted, its hooks are
    // [project, commit]), then MarkerEditor (single-selection only).
    const root = this._studioRoot();
    if (!root) return null;

    const layers = root.querySelector('.fp-layers');
    if (layers) {
      let f = this._fiberOf(layers);
      let hops = 0;
      while (f && hops++ < 15) {
        if (f.memoizedState) {
          const cand = this._fiberCommit(f, 'layers');
          if (cand) return cand;
        }
        f = f.return;
      }
    } else {
      dwarn('.fp-layers anchor not found');
    }

    for (const el of root.querySelectorAll('input, select, button, div')) {
      let f = this._fiberOf(el);
      let hops = 0;
      while (f && hops++ < 40) {
        const p = f.memoizedProps;
        if (p && p.marker && p.floor && !p.screenToDoc) {
          dlog('MarkerEditor fiber found, scanning hooks…');
          const cand = this._fiberCommit(f, 'editor');
          if (cand) return cand;
        }
        f = f.return;
      }
    }
    dwarn('no commit found');
    return null;
  }

  _patchMarkerDom(g, size) {
    for (const child of g.children) {
      const tag = child.tagName.toLowerCase();
      if (tag === 'circle') {
        if (child.getAttribute('stroke-dasharray')) child.setAttribute('r', size * 0.72);
        else if (child.getAttribute('fill') === 'rgba(20,24,33,0.55)') child.setAttribute('r', size * 0.5);
        else if (child.getAttribute('stroke') === '#fff') child.setAttribute('r', size * 0.4);
      } else if (tag === 'path') {
        child.setAttribute('transform', `translate(${-size * 0.35} ${-size * 0.35}) scale(${(size * 0.7) / 24})`);
      } else if (tag === 'image') {
        child.setAttribute('x', -size / 2);
        child.setAttribute('y', -size / 2);
        child.setAttribute('width', size);
        child.setAttribute('height', size);
      } else if (tag === 'g') {
        child.setAttribute('transform', `scale(${size / 24})`);
      } else if (tag === 'text') {
        child.setAttribute('y', size * 0.5 + 14);
      }
    }
  }

  async _resizeSelected() {
    const size = Number(this._tweak('marker_size') || 20);
    const sel = this._studioSelectedMarkers();
    if (!this._studioRoot()) {
      this._status('Studio card not found on this view');
      return;
    }
    if (!sel.length) {
      const layer = this._studioRoot().querySelector('g[data-layer="entities"]');
      const total = layer ? layer.children.length : 0;
      this._status(
        `No selected markers found (${total} marker(s) on canvas). ` +
          'In studio: pick the select tool in edit mode and click a marker — a dashed blue ring appears around the selection.'
      );
      return;
    }

    // Collect the marker ids behind the selected <g> elements.
    const ids = new Set();
    for (const m of sel) {
      const marker = this._fiberMarker(m.el);
      dlog('fiber marker for selected g:', marker && { id: marker.id, size: marker.style && marker.style.size });
      if (marker && marker.id) ids.add(marker.id);
    }

    // Preferred path: studio's own commit() (immer produce -> re-render
    // -> autosave -> undo history). Available while a single marker is
    // selected (MarkerEditor mounted in the inspector).
    const commit = this._studioCommit();
    dlog('commit:', typeof commit, '| ids:', [...ids]);
    if (commit && ids.size) {
      try {
        commit((p) => {
          for (const floor of p.floors || []) {
            for (const mk of floor.markers || []) {
              if (ids.has(mk.id)) mk.style.size = size;
            }
          }
        });
        this._status(
          `Resized ${ids.size} selected marker(s) to ${size}px via studio's own commit — re-rendered, autosaved, undo-able`
        );
        return;
      } catch (e) {
        dwarn('commit threw:', e);
        this._status(`commit failed (${e.message || e}), falling back to DOM+IDB patch…`);
      }
    }

    // Fallback: write sizes into the IndexedDB project + live DOM patch
    // (studio's in-memory copy may overwrite on its next autosave).
    for (const m of sel) this._patchMarkerDom(m.el, size);
    const id = this._selectedProjectId();
    if (id) {
      try {
        const db = await openFpDb();
        const project = await idbReq(db.transaction('projects').objectStore('projects').get(id));
        if (project) {
          for (const floor of project.floors || []) {
            for (const mk of floor.markers || []) {
              if (ids.has(mk.id) || sel.some((s) => Math.abs(mk.x - s.x) < 0.5 && Math.abs(mk.y - s.y) < 0.5)) {
                mk.style.size = size;
              }
            }
          }
          await idbReq(db.transaction('projects', 'readwrite').objectStore('projects').put(project));
          db.close();
          this._status(
            `Resized ${sel.length} selected marker(s) to ${size}px — patched DOM + project storage` +
              ` (select a single marker to also drive studio's own commit for live persistence)`
          );
          return;
        }
        db.close();
      } catch { /* fall through */ }
    }
    this._status(`Resized ${sel.length} selected marker(s) to ${size}px (DOM only)`);
  }

  async _recolorSelectedRooms() {
    const fill = this._tweak('room_fill') || '#22c55e';
    const opRaw = this._tweak('room_opacity');
    const opacity = opRaw === undefined || opRaw === '' ? null : Number(opRaw);
    const root = this._studioRoot();
    if (!root) {
      this._status('Studio card not found on this view');
      return;
    }
    const ids = this._studioSelectedRoomIds();
    if (!ids.size) {
      const total = root.querySelectorAll('g[data-layer="rooms"] g[data-room]').length;
      this._status(
        `No selected rooms found (${total} rooms on canvas). In studio edit mode: ` +
          'select tool, click a room (shift-click for several) — a dashed blue outline marks the selection.'
      );
      return;
    }
    const label = `${fill}${opacity !== null ? ` @ ${opacity}` : ''}`;

    const commit = this._studioCommit();
    if (commit) {
      try {
        commit((p) => {
          for (const floor of p.floors || []) {
            for (const room of floor.rooms || []) {
              if (ids.has(room.id)) {
                room.fill = fill;
                if (opacity !== null) room.opacity = opacity;
              }
            }
          }
        });
        this._status(
          `Recolored ${ids.size} selected room(s) → ${label} via studio's own commit — re-rendered, autosaved, undo-able`
        );
        return;
      } catch (e) {
        dwarn('commit threw:', e);
        this._status(`commit failed (${e.message || e}), falling back to DOM+IDB patch…`);
      }
    }

    // Fallback: patch the fill path live + write the stored project.
    for (const g of root.querySelectorAll('g[data-layer="rooms"] g[data-room]')) {
      if (!ids.has(g.getAttribute('data-room'))) continue;
      const path = g.querySelector(':scope > path');
      if (path) {
        path.setAttribute('fill', fill);
        if (opacity !== null) path.setAttribute('fill-opacity', String(opacity));
      }
    }
    const pid = this._selectedProjectId();
    if (pid) {
      try {
        const db = await openFpDb();
        const project = await idbReq(db.transaction('projects').objectStore('projects').get(pid));
        if (project) {
          for (const floor of project.floors || []) {
            for (const room of floor.rooms || []) {
              if (ids.has(room.id)) {
                room.fill = fill;
                if (opacity !== null) room.opacity = opacity;
              }
            }
          }
          await idbReq(db.transaction('projects', 'readwrite').objectStore('projects').put(project));
        }
        db.close();
      } catch { /* fall through */ }
    }
    this._status(
      `Recolored ${ids.size} selected room(s) → ${label} (DOM + stored project; studio commit unavailable)`
    );
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
    const color = this._tweak('room_fill') || undefined;
    await this._call('floorplan_set_device_zone', {
      device_id: devId,
      areas,
      ...(color ? { color } : {}),
    });
    await this._fetchConfig();
    this._status(
      `Zone stored for ${devId}: ${areas.join(', ')}` +
        (color ? ` (${color})` : '') +
        ' — click its marker in studio to highlight'
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

  async _readStudioProject() {
    const id = this._selectedProjectId();
    if (!id) { this._status('No studio project selected'); return null; }
    const db = await openFpDb();
    const project = await idbReq(
      db.transaction('projects').objectStore('projects').get(id)
    );
    db.close();
    if (!project) {
      this._status('Project not found in studio storage');
      return null;
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
    await idbReq(
      db.transaction('projects', 'readwrite').objectStore('projects').put(project)
    );
    db.close();
    return project;
  }

  async _seed() {
    const data = {};
    if (this._config.floors) data.floors = this._config.floors;
    const size = this._tweak('marker_size');
    if (size) data.marker_size = size;
    const seedName = this._tweak('seed_name');
    if (seedName) data.name = seedName;
    const r = await this._call('floorplan_seed_studio', data);
    const placed = Object.keys(r.placed || {}).length;
    const unplaced = (r.unplaced || []).length;
    if (r.project_json) {
      try {
        const p = await this._pushToStudio(r.project_json);
        this._status(`Seeded: ${placed} placed, ${unplaced} parked — written to studio as '${p.name}'. Open it via Projects.`);
      } catch {
        this._copy(r.project_json, 'Project JSON');
        this._status(`Seeded: ${placed} placed, ${unplaced} parked — could not write to studio storage; JSON copied to clipboard instead.`);
      }
      this._refreshProjects();
    } else {
      this._status(`Seeded: ${placed} placed, ${unplaced} parked`);
    }
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
    const r = await this._call('floorplan_export', {});
    const yamls = r.card_yamls || (r.card_yaml ? { default: r.card_yaml } : {});
    const floors = Object.keys(yamls);
    this._renderYamlButtons(yamls);
    if (floors.length) {
      this._copy(yamls[floors[0]], `card yaml (${floors[0]})`);
      this._status(
        `Exported ${(r.rules || []).length} rules${stored} — ` +
          `card yaml for '${floors[0]}' copied` +
          (floors.length > 1
            ? `; ${floors.length} floors — use the copy buttons below for the other card(s).`
            : '.'),
      );
    } else {
      this._status(`Export finished${stored} (no card_yaml in response)`);
    }
  }

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
          Bridge between floorplan-studio and Home Assistant — pull the
          drawing into HA areas, or seed device markers back into studio.
        </div>
        <div class="row">
          <button id="b-studio"
            title="Open the floorplan-studio editor (planner_url from your floorplan settings)">Open studio</button>
          <span class="lbl">studio project:</span>
          <select id="project"
            title="Projects stored in floorplan-studio (this browser). The one studio is currently editing is marked (current)."></select>
          <button id="b-pull" class="secondary"
            title="Read the selected project straight from studio (it autosaves ~0.6s after each change), store it as latest.json + backup, and sync marker positions into HA areas">Pull ← studio</button>
          <button id="b-seed" class="secondary"
            title="Pre-place a marker for every device whose HA area matches a room (at the room's centre), park unassigned devices below the canvas, and write the result into studio's project list">Seed → studio</button>
          <button id="b-export" class="secondary"
            title="Regenerate the ha-floorplan bundle (SVG + rules + CSS) and copy the dashboard card YAML to your clipboard">Export bundle</button>
          <button id="b-sync" class="secondary"
            title="Re-run area sync on the stored project: marker-in-room → entity area_id, missing areas created">Sync areas</button>
          <button id="b-resize" class="secondary"
            title="Apply the tweak icon size to the markers currently selected inside studio (edit mode). Patches the studio canvas live and persists via studio's own autosave">Resize ◉ selected</button>
          <button id="b-recolor" class="secondary"
            title="Apply the tweak room colour to the rooms currently selected inside studio (edit mode, shift-click for several) — e.g. colour every room a device serves">Recolor ◧ rooms</button>
          <button id="b-tweaks" class="secondary"
            title="Card tweaks — saved in this browser">⚙ Tweaks</button>
        </div>
        <div class="tweaks" id="tweaks" style="display:none">
          <div class="row">
            <label for="tw-size" title="Icon size in px — applies immediately to markers selected in studio, and to markers Seed generates">Marker icon size</label>
            <input id="tw-size" type="number" min="8" max="80" placeholder="20">
          </div>
          <div class="row">
            <label for="tw-name" title="Name given to the project Seed writes into studio">Seed project name</label>
            <input id="tw-name" type="text" placeholder="Floorplan">
          </div>
          <div class="row">
            <label for="tw-sync" title="After Pull (or a dropped file), also run area sync automatically">Sync areas on pull</label>
            <input id="tw-sync" type="checkbox">
          </div>
          <div class="row">
            <label for="tw-norm" title="On Pull, set every marker's icon size in the project to the size above — also writes it back to studio so manually placed markers (studio default 40) get fixed">Normalize icon sizes on pull</label>
            <input id="tw-norm" type="checkbox">
          </div>
          <div class="row">
            <label for="tw-fill" title="Fill colour applied to rooms selected in studio via 'Recolor ◧ rooms' — e.g. mark every room a WTW ventilates">Room fill</label>
            <input id="tw-fill" type="color" style="width:44px;padding:0;height:24px">
            <label for="tw-op" title="Fill opacity 0–1; leave empty to keep each room's current opacity">opacity</label>
            <input id="tw-op" type="number" min="0" max="1" step="0.05" style="width:64px" placeholder="keep">
          </div>
          <div class="row">
            <label for="zone-dev" title="Device whose 'zone' (rooms it serves) you are editing — existing zones shown after ▸">Zone device</label>
            <select id="zone-dev" style="max-width:260px"></select>
            <button id="b-zone" class="secondary"
              title="Store the rooms currently selected in studio (shift-click) as this device's zone — clicking its marker then highlights them">◧ rooms → zone</button>
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
      this._navigate(this._config.studio_url || (this._fpConfig || {}).planner_url || '/floorplan-studio');
    $('b-pull').onclick = () => this._run(() => this._pull());
    $('b-seed').onclick = () => this._run(() => this._seed());
    $('b-export').onclick = () => this._run(() => this._export());
    $('b-sync').onclick = () => this._run(() => this._sync());
    $('b-resize').onclick = () => this._run(() => this._resizeSelected());
    $('b-recolor').onclick = () => this._run(() => this._recolorSelectedRooms());
    $('b-tweaks').onclick = () => {
      const t = $('tweaks');
      t.style.display = t.style.display === 'none' ? 'block' : 'none';
    };

    // tweaks panel — values persist in localStorage, override YAML config
    const twSize = $('tw-size');
    const twName = $('tw-name');
    const twSync = $('tw-sync');
    const twNorm = $('tw-norm');
    twSize.value = this._tweak('marker_size') ?? '';
    twName.value = this._tweak('seed_name') ?? '';
    twSync.checked = this._tweak('sync_on_pull') !== false;
    twNorm.checked = this._tweak('normalize_sizes') !== false;
    twSize.onchange = () => {
      this._saveTweak('marker_size', twSize.value ? Number(twSize.value) : undefined);
      // Live-apply: if markers are selected in studio right now, resize
      // them immediately so the field acts like studio's own size input.
      if (twSize.value && this._studioSelectedMarkers().length) {
        this._run(() => this._resizeSelected());
      } else if (twSize.value) {
        this._status(
          `Icon size set to ${twSize.value}px — applied to seeded markers and to 'Resize ◉ selected'. ` +
            'Select markers in studio to resize them now.'
        );
      }
    };
    twName.onchange = () => this._saveTweak('seed_name', twName.value || undefined);
    twSync.onchange = () => this._saveTweak('sync_on_pull', twSync.checked);
    twNorm.onchange = () => this._saveTweak('normalize_sizes', twNorm.checked);

    const twFill = $('tw-fill');
    const twOp = $('tw-op');
    twFill.value = this._tweak('room_fill') || '#22c55e';
    twOp.value = this._tweak('room_opacity') ?? '';
    twFill.onchange = () => {
      this._saveTweak('room_fill', twFill.value);
      if (this._studioSelectedRoomIds().size) {
        this._run(() => this._recolorSelectedRooms());
      }
    };
    twOp.onchange = () =>
      this._saveTweak('room_opacity', twOp.value === '' ? undefined : Number(twOp.value));

    // device zones: "◧ rooms → zone" + watch toggle + device panel close
    $('b-zone').onclick = () => this._run(() => this._assignZone());
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

async function _openGlobalDevicePopup(detail) {
  const hass = _fpHass();
  if (!hass) return;
  const deviceId = detail.ramses_device_id;

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

  pop.querySelector('.lbl').textContent = deviceId;
  const viewUrl = await _fpDeviceViewUrl(hass);
  pop.querySelector('.view').style.display = viewUrl ? '' : 'none';

  const host = pop.querySelector('.host');
  host.innerHTML = '';
  _fpPopCard = null;

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

window.addEventListener('ll-custom', (ev) => {
  const d = ev && ev.detail;
  if (d && d.ramses_device_id) _openGlobalDevicePopup(d);
});

window.customCards = window.customCards || [];
window.customCards.push({
  type: 'ramses-floorplan-actions',
  name: 'Ramses Floorplan Actions',
  description: 'Action bar + studio project bridge for floorplan-studio workflows',
});
