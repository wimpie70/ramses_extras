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
 *   1. project picker — studio's own projects in this browser (this
 *      card belongs on the same view as the floorplan-studio card)
 *   2. "Studio → HA" — store the selected project server-side
 *      (latest.json + backup)
 *   3. "HA → Studio" — restore the stored project into this
 *      browser's studio
 *
 * Tools row:
 *   - "＋ Add devices" — seed/merge new device markers into the
 *     selected project (or the stored one), written back into studio
 *   - "Sync areas → HA" — link rooms to HA areas and set each entity's
 *     HA area from which room its marker sits inside
 *   - "Export ⇒" — snapshot the live project, run floorplan_export,
 *     copy the card yaml (dashboard cards untouched)
 *   - "⇒ Update cards" — same export, plus every floorplan card
 *     showing a generated map is updated in place
 *   - "⚙ Zones" — zone editor: pick a device, check the rooms it
 *     serves and the extra markers bound to it; the swatch sets the
 *     selected-zone highlight colour only — room fills stay studio's
 *   - Drop zone: fallback for JSON files from another machine/backup
 *
 * Config (all optional):
 *   floors: {begane grond: plattegrond-bg.svg, ...}  floor name → SVG
 *   ref — seeds floor geometry for a new project only; the export
 *   renders the drawing straight from the stored plan itself
 *   marker_size: 20  (size for newly seeded markers — studio owns size
 *   after that; the inspector edits it per marker)
 *   device_view_url: /lovelace/hvac  (optional — adds a '⤢ dashboard'
 *   button to the device popup opened by double-clicking a marker)
 *   editor: studio | hfs  — which plan editor this card drives; absent,
 *   the backend resolves the configured default (see the floorplan
 *   helper options). Server-side editors (hfs) hide the pull/push row
 *   and show "Open editor" instead — their plan already lives in HA.
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
  .drop .droplinks a { color: var(--primary-color); }
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
  .zcols { align-items: flex-end; }
  .zcol { display: flex; flex-direction: column; gap: 3px; }
  .zlist {
    min-width: 240px; max-height: 170px; overflow-y: auto;
    border: 1px solid var(--divider-color, #ccc); border-radius: 6px;
    padding: 4px 6px; background: var(--card-background-color, #fff);
  }
  .zitem { display: flex; align-items: center; gap: 6px;
           padding: 2px 2px; font-size: 13px; cursor: pointer;
           color: var(--primary-text-color); }
  .zitem input { margin: 0; }
  .zitem.off { opacity: .55; cursor: default; }
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
    this._hiDevice = null; // device_id whose zone is highlighted
    this._hiPatched = [];  // [el, {attr: original}] pairs to restore
    this._roomsCache = null;
    this._devCard = null;
    this._studioRoomSel = new Set();   // last-seen studio room selection
    this._studioMemberSel = new Set(); // last-seen member selection (ids)
    this._lastSoleDev = null;          // marker last seen as sole selection
    this._zoneSaveT = null;            // autosave debounce timer
    this._zoneRowFor = null;           // device the zone lists are built for
    this._sawStudioSel = false;        // studio selection seen non-empty
    this._suppressMenuClear = false;   // ignore the post-remount deselect
    this._uiInteractAt = 0;            // last interaction inside this card
  }

  setConfig(config) {
    this._config = config || {};
    // yaml `editor:` pins this card to one plan editor (studio|hfs);
    // absent, the backend resolves the configured/default one
    this._editor = this._config.editor || '';
    this._editorCaps = null;
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
    if (!this._uiStamp) {
      // hfs clears the editor's st.sel when focus leaves the editor —
      // interacting with this card must not read as a canvas deselect
      this._uiStamp = () => {
        this._uiInteractAt = Date.now();
      };
      for (const ev of ['pointerdown', 'focusin', 'input', 'change']) {
        this.addEventListener(ev, this._uiStamp, true);
      }
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
        ...(this._editor ? { editor: this._editor } : {}),
      });
      this._resolvedEditor = this._fpConfig.editor || 'studio';
      this._editorCaps = this._fpConfig.editor_caps || {};
      this._applyEditorCaps();
    } catch {
      this._fpConfig = {};
      this._editorCaps = {};
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

  // Per-editor menu rows — driven by the resolved adapter's
  // capabilities (get_config reply), not by hardcoding. Server-side
  // editors (hfs) have no browser store: the studio pull/push row is
  // replaced by an "Open editor" link.
  _applyEditorCaps() {
    if (!this.shadowRoot || !this._editorCaps) return;
    const caps = this._editorCaps;
    const $ = (id) => this.shadowRoot.getElementById(id);
    const rowStudio = $('row-studio');
    if (rowStudio) rowStudio.style.display = caps.browser_side === false ? 'none' : '';
    const rowEditor = $('row-editor');
    if (rowEditor) rowEditor.style.display = caps.browser_side === false ? '' : 'none';
    const drop = $('drop');
    if (drop && caps.browser_side === false) {
      drop.title = 'Import a layout/plan file — replaces the stored plan for the resolved editor';
      drop.childNodes[0].textContent =
        'Drop a floorplan-studio layout JSON here ';
      const tail = drop.childNodes[2];
      if (tail && tail.nodeType === 3)
        tail.textContent = ' — restores a downloaded plan into HA storage';
    }
    const lbl = this.shadowRoot.querySelector('#row-studio .lbl');
    if (lbl && this._resolvedEditor) lbl.textContent = `${this._resolvedEditor} project:`;
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
      service_data: {
        ...(data || {}),
        // the card's yaml `editor:` pins which plan editor every
        // service call resolves — absent, the backend picks the
        // configured/default one
        ...(this._editor ? { editor: this._editor } : {}),
      },
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

  _editorCardEl() {
    // the card_element capability names the editable DOM element —
    // '' means the editor isn't a dashboard card (hfs edits in its own
    // panel; its card is only a live renderer)
    const tag = this._editorCaps && this._editorCaps.card_element;
    return tag ? deepFind(tag) : null;
  }

  _studioRoot() {
    const el = this._editorCardEl();
    dlog('editor card element:', el, 'shadowRoot:', el && el.shadowRoot);
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
    // path; the wrapping <g> carries data-room="<id>".
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
    return ids;
  }

  // Drive studio's own selection from the menu: a dispatched
  // pointerdown reaches React's delegated handler and runs
  // select(id, shiftKey) — additive toggles, plain selects solely.
  // setPointerCapture throws on synthetic pointerIds, so it is
  // stubbed for the dispatch; the pointerup settles marker drag state.
  _studioClick(el, additive) {
    if (!el) return false;
    const orig = window.Element.prototype.setPointerCapture;
    window.Element.prototype.setPointerCapture = function () {};
    try {
      for (const type of ['pointerdown', 'pointerup']) {
        el.dispatchEvent(
          new window.PointerEvent(type, {
            bubbles: true,
            composed: true,
            cancelable: true,
            shiftKey: additive,
            pointerId: 9999,
            isPrimary: true,
            clientX: 0,
            clientY: 0,
          })
        );
      }
      return true;
    } finally {
      window.Element.prototype.setPointerCapture = orig;
    }
  }

  _studioElForRoom(roomId) {
    const root = this._studioRoot();
    return (
      root &&
      root.querySelector(
        `g[data-layer="rooms"] g[data-room="${window.CSS.escape(roomId)}"]`
      )
    );
  }

  _studioElForMember(id) {
    const root = this._studioRoot();
    if (!root) return null;
    for (const g of root.querySelectorAll('g[data-layer="entities"] > g')) {
      const marker = this._fiberMarker(g);
      const ents =
        marker && (marker.entities || (marker.entity ? [marker.entity] : []));
      for (const e of ents || []) {
        const d = this._entityDevice[e];
        if ((d ? d.device_id : e) === id) return g;
      }
    }
    return null;
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
    if (this._resolvedEditor === 'hfs') {
      // hfs rooms come from the stored layout (the overlay shares its
      // live copy). The room key is the area/name slug — the same
      // value zone.areas stores, so _saveZone's areaId mapping and the
      // renderer card's data-r resolution are identity.
      const info =
        window.__ramsesHfsInfo && window.__ramsesHfsInfo();
      const floors = (info && info.layout && info.layout.floors) || {};
      for (const [fk, f] of Object.entries(floors)) {
        (f.rooms || []).forEach((r, i) => {
          const slug = this._slug(r.area || r.name) || `${fk}-${i}`;
          m.set(slug, {
            name: r.name || slug,
            areaId: slug,
            fill: r.color,
            floor: f.title || fk,
          });
        });
      }
      this._roomsCache = { t: now, m };
      return m;
    }
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
            fill: r.fill,
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
    if (this._busy || document.hidden) return;
    if (this._resolvedEditor === 'hfs') {
      this._pollHfsSelection();
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

    this._syncStudioSelection(sel);
  }

  // Studio → menu: resolve the fiber markers into the shared shape —
  // selected member ids (device_id, else entity), room ids, and the
  // sole-selected device — then run the common delta pass.
  _syncStudioSelection(mSel) {
    const roomIds = this._studioSelectedRoomIds();
    let soleDev = null;
    const memberIds = new Set();
    for (const m of mSel) {
      const marker = this._fiberMarker(m.el);
      const ents =
        marker && (marker.entities || (marker.entity ? [marker.entity] : []));
      for (const e of ents || []) {
        const d = this._entityDevice[e];
        memberIds.add(d ? d.device_id : e);
      }
      if (mSel.length === 1) {
        const d = this._deviceOfMarkerEl(m.el);
        if (d) soleDev = d.device_id;
      }
    }
    this._syncZoneSelection(memberIds, roomIds, soleDev);
  }

  // hfs → menu: the editor keeps its selection on the element's `st.sel`
  // — {t:'dev'|'devs'|'room', i|is} indexing the shown floor's lists.
  // Same shared shape; indices resolve through the overlay's layout.
  _pollHfsSelection() {
    const info =
      window.__ramsesHfsInfo && window.__ramsesHfsInfo();
    const ed = info && info.editor;
    const floors = (info && info.layout && info.layout.floors) || {};
    const floor = ed && floors[ed.floor];
    const sel = (ed && ed.st && ed.st.sel) || null;
    const memberIds = new Set();
    const roomIds = new Set();
    let soleDev = null;
    const devKey = (list, i) => {
      const d = (list || [])[i];
      const t = d && d.entity && this._entityDevice[d.entity];
      return t ? String(t.device_id) : (d && d.entity) || null;
    };
    let firstDev = null;
    if (floor && sel) {
      if (sel.t === 'dev' || sel.t === 'devs') {
        const idx = sel.t === 'dev' ? [sel.i] : sel.is || [];
        for (const i of idx) {
          const d = (floor.devices || [])[i];
          const t = d && this._entityDevice[d.entity];
          const id = t ? String(t.device_id) : (d && d.entity) || null;
          if (id) memberIds.add(id);
          if (t && !firstDev) firstDev = String(t.device_id);
        }
        // ownership adoption only counts topology devices — an
        // unmapped entity marker can't be a zone owner
        if (sel.t === 'dev') soleDev = firstDev;
      } else if (sel.t === 'unl') {
        const id = devKey(floor.unlinked, sel.i);
        if (id) memberIds.add(id);
      } else if (sel.t === 'room') {
        const r = (floor.rooms || [])[sel.i];
        if (r) roomIds.add(this._slug(r.area || r.name) || `${sel.i}`);
      }
    }

    // zone preview highlight follows the first selected topology
    // device — same hook the studio poll drives
    const hiDev =
      firstDev &&
      ((this._topology.devices || []).find(
        (d) => d.device_id === firstDev
      ) ||
        null);
    const hiId = hiDev ? firstDev : null;
    if (hiId !== this._hiDevice) {
      this._hiDevice = hiId;
      this._hiDev = hiDev;
      this._applyZoneHighlight(hiId, hiDev);
    } else if (
      this._hiDevice &&
      this._hiPatched.length &&
      !this._hiPatched[0][0].isConnected
    ) {
      this._hiPatched = [];
      this._applyZoneHighlight(this._hiDevice, this._hiDev);
    }

    this._syncZoneSelection(memberIds, roomIds, soleDev);
  }

  // True while the interaction lives inside this card's own UI —
  // the native colour dialog drops document focus entirely, so a
  // recent interaction timestamp backs up :focus-within. Either way
  // an empty st.sel during this is upstream's focus-out clear, not a
  // canvas deselect.
  _ownUiActive() {
    return (
      !document.hasFocus() ||
      this.matches(':focus-within') ||
      Date.now() - (this._uiInteractAt || 0) < 2500
    );
  }

  // Editor → menu: while the zone editor is open, selection changes
  // on the canvas toggle the matching listbox entries (delta-only —
  // a cleared canvas selection means "no selection", not "clear the
  // zone"), and a sole-selected marker that maps to a device adopts
  // it as the zone owner. Shared by the studio and hfs paths.
  _syncZoneSelection(memberIds, roomIds, soleDev) {
    const tweaks = this.shadowRoot.getElementById('tweaks');
    const devSel = this.shadowRoot.getElementById('zone-dev');
    const roomsSel = this.shadowRoot.getElementById('zone-rooms');
    const memSel = this.shadowRoot.getElementById('zone-members');
    const open =
      tweaks && tweaks.style.display !== 'none' && devSel && roomsSel && memSel;
    if (!open) {
      this._studioRoomSel = new Set();
      this._studioMemberSel = new Set();
      this._lastSoleDev = null;
      this._sawStudioSel = false;
      return;
    }

    // A genuinely empty canvas (user clicked a non-room/non-marker
    // spot) clears the zone picker — the menu follows the editor's
    // deselect. The empty selection a studio remount briefly shows
    // after our own project push is not a user deselect: the flag
    // _reloadStudioCard sets swallows exactly that one observation.
    if (!memberIds.size && !roomIds.size) {
      if (this._suppressMenuClear) {
        this._suppressMenuClear = false;
      } else if (this._ownUiActive()) {
        // upstream cleared st.sel on focus-out (our colour swatch,
        // listboxes…): keep the pick, and put the marker's selection
        // ring back so canvas and menu stay in sync
        if (devSel.value && this._resolvedEditor === 'hfs') {
          this._hfsSelectDevice(devSel.value);
        }
      } else if (this._sawStudioSel && devSel.value) {
        devSel.value = '';
        this._zoneRowFor = null;
        this._fillZoneRow();
      }
      this._sawStudioSel = false;
      this._studioRoomSel = roomIds;
      this._studioMemberSel = new Set();
      this._lastSoleDev = null;
      return;
    }
    this._sawStudioSel = true;

    // the owner itself is never its own member
    memberIds.delete(devSel.value);

    // no zone picked yet: a sole-selected marker adopts ownership;
    // membership deltas need an owner, so they wait
    if (!devSel.value) {
      if (soleDev && soleDev !== this._lastSoleDev) {
        devSel.value = soleDev;
        this._fillZoneRow();
      }
      this._lastSoleDev = soleDev;
      this._studioRoomSel = roomIds;
      this._studioMemberSel = memberIds;
      return;
    }

    // a newly sole-selected marker becomes the zone owner — only on
    // a *change* of sole selection so a lingering selection can't
    // fight a menu pick that the editor ignored. On a switch the
    // listboxes are rebuilt, so the delta pass is skipped until next
    // poll.
    if (
      soleDev &&
      soleDev !== devSel.value &&
      soleDev !== this._lastSoleDev
    ) {
      devSel.value = soleDev;
      this._fillZoneRow();
      memberIds.delete(soleDev);
      this._studioMemberSel = memberIds;
      this._studioRoomSel = roomIds;
      this._lastSoleDev = soleDev;
      return;
    }
    this._lastSoleDev = soleDev;

    let dirty = this._applySelDelta(roomsSel, this._studioRoomSel, roomIds, false);
    this._studioRoomSel = roomIds;
    dirty =
      this._applySelDelta(memSel, this._studioMemberSel, memberIds, true) ||
      dirty;
    this._studioMemberSel = memberIds;
    if (dirty) this._queueZoneSave();
  }

  // Flip checkboxes whose studio-selection state changed since the
  // last poll. Skipped entirely when the selection went empty —
  // clearing the canvas is not "remove everything from the zone".
  // Returns whether any checkbox changed.
  _applySelDelta(selEl, prev, cur, appendEntities) {
    if (!cur.size && prev.size) return false;
    const toggled = new Set(
      [...cur]
        .filter((x) => !prev.has(x))
        .concat([...prev].filter((x) => !cur.has(x)))
    );
    let dirty = false;
    const boxes = selEl.querySelectorAll('input[type=checkbox]');
    const have = new Set([...boxes].map((cb) => cb.value));
    for (const cb of boxes) {
      if (!toggled.has(cb.value) || cb.disabled) continue;
      const want = cur.has(cb.value);
      if (cb.checked !== want) {
        cb.checked = want;
        dirty = true;
      }
    }
    // selected markers that aren't listed yet (non-topology entity
    // markers) get a row appended so they can be unchecked
    if (appendEntities) {
      for (const id of cur) {
        if (have.has(id)) continue;
        selEl.appendChild(this._zitem(id, `${id} (entity)`, true));
        dirty = true;
      }
    }
    return dirty;
  }

  // Menu → studio: rebuild studio's selection to match the checked
  // boxes exactly, then autosave. A plain pointerdown on the canvas
  // clears the selection; shift-pointerdown adds — needed because a
  // marker's own pointerdown can only *add*, never toggle off, so
  // deselects can't be expressed per-element.
  _pushZoneSelToStudio() {
    const roomsSel = this.shadowRoot.getElementById('zone-rooms');
    const memSel = this.shadowRoot.getElementById('zone-members');
    const devSel = this.shadowRoot.getElementById('zone-dev');
    const checked = (el) =>
      [...el.querySelectorAll('input:checked:not(:disabled)')].map(
        (cb) => cb.value
      );
    if (this._resolvedEditor === 'hfs') {
      // hfs can't multi-select rooms — members + owner land as a
      // devs selection; checked rooms show through the painted
      // zone highlight instead.
      const info = window.__ramsesHfsInfo && window.__ramsesHfsInfo();
      const ed = info && info.editor;
      const floor =
        ed && ((info.layout && info.layout.floors) || {})[ed.floor];
      if (ed && ed.st && floor && roomsSel && memSel) {
        const wanted = new Set(
          [...checked(memSel), devSel && devSel.value].filter(Boolean)
        );
        const idx = [];
        (floor.devices || []).forEach((d, i) => {
          const t = d.entity && this._entityDevice[d.entity];
          const key = t ? String(t.device_id) : d.entity;
          if (wanted.has(key) || (d.entity && wanted.has(d.entity))) {
            idx.push(i);
          }
        });
        ed.st.sel =
          idx.length > 1
            ? { t: 'devs', is: idx }
            : idx.length
              ? { t: 'dev', i: idx[0] }
              : null;
        if (ed.requestUpdate) ed.requestUpdate();
        this._studioRoomSel = new Set(checked(roomsSel));
        this._studioMemberSel = new Set(checked(memSel));
      }
      this._queueZoneSave();
      return;
    }
    const root = this._studioRoot();
    if (root && roomsSel && memSel) {
      this._ensureStudioEdit();
      this._studioClick(root.querySelector('svg'), false); // clear
      const roomIds = checked(roomsSel);
      const memberIds = checked(memSel);
      for (const id of roomIds) {
        this._studioClick(this._studioElForRoom(id), true);
      }
      for (const id of memberIds) {
        this._studioClick(this._studioElForMember(id), true);
      }
      // owner marker last — keeps it selected for the zone preview
      if (devSel && devSel.value) {
        this._studioClick(this._studioElForMember(devSel.value), true);
      }
      this._studioRoomSel = new Set(roomIds);
      this._studioMemberSel = new Set(memberIds);
    }
    this._queueZoneSave();
  }

  // Studio only honours pointerdown selection in edit mode with the
  // select tool — click its own toolbar buttons when needed.
  _ensureStudioEdit() {
    const root = this._studioRoot();
    if (!root) return;
    const clickIfInactive = (sel, text) => {
      for (const b of root.querySelectorAll(sel)) {
        if (b.textContent.trim() === text) {
          if (!b.classList.contains('active')) b.click();
          return;
        }
      }
    };
    clickIfInactive('.fp-mode button', 'Edit');
    clickIfInactive('.fp-toolbar .fp-tool', 'Select');
  }

  _queueZoneSave() {
    clearTimeout(this._zoneSaveT);
    this._zoneSaveT = setTimeout(
      () => this._run(() => this._saveZone()),
      700
    );
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
    const rooms = await this._projectRooms();
    // same resolution as the export: the stored zone colour is the
    // highlight outline; a zone room's own fill is only the fallback
    // for zones that never picked one
    let color = zone.color;
    if (!color) {
      for (const room of rooms.values()) {
        if (room.fill && areas.has(room.areaId)) { color = room.fill; break; }
      }
    }
    if (!color) color = '#f59e0b';

    if (this._resolvedEditor === 'hfs') {
      this._applyZoneHighlightHfs(devId, dev, zone, areas, color);
      return;
    }

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

  // hfs editor canvas: stroke the zone's room polygons (data-r index)
  // and drop-shadow bound device markers (data-x index) — the same
  // patch/restore scheme as the studio path (_hiPatched).
  _applyZoneHighlightHfs(devId, dev, zone, areas, color) {
    const info = window.__ramsesHfsInfo && window.__ramsesHfsInfo();
    const ed = info && info.editor;
    const floors = (info && info.layout && info.layout.floors) || {};
    const floor = ed && floors[ed.floor];
    const root = ed && ed.shadowRoot;
    if (!root || !floor) return;

    const roomAreas = (floor.rooms || []).map((r) =>
      this._slug(r.area || r.name)
    );
    const want = new Set([...areas].map((a) => this._slug(a)));
    const names = [];
    for (const poly of root.querySelectorAll('polygon[data-r]')) {
      const i = Number(poly.getAttribute('data-r'));
      if (!want.has(roomAreas[i])) continue;
      this._hiPatched.push([
        poly,
        {
          stroke: poly.getAttribute('stroke'),
          'stroke-width': poly.getAttribute('stroke-width'),
          'stroke-dasharray': poly.getAttribute('stroke-dasharray'),
        },
      ]);
      poly.setAttribute('stroke', color);
      poly.setAttribute('stroke-width', '3');
      poly.setAttribute('stroke-dasharray', '6 3');
      names.push((floor.rooms[i] || {}).name || roomAreas[i]);
    }

    const bound = new Set([devId]);
    for (const d of (this._topology || {}).devices || []) {
      if (d.parent === devId && d.device_class !== 'HGI') {
        bound.add(d.device_id);
      }
    }
    for (const b of zone.devices || []) bound.add(String(b));
    let nDev = 0;
    for (const g of root.querySelectorAll('g.dev[data-x]')) {
      const d = (floor.devices || [])[Number(g.getAttribute('data-x'))];
      if (!d) continue;
      const t = d.entity && this._entityDevice[d.entity];
      const key = t ? String(t.device_id) : d.entity;
      if (!bound.has(key) && !bound.has(d.entity)) continue;
      this._hiPatched.push([g, { style: g.getAttribute('style') }]);
      g.style.filter = `drop-shadow(0 0 5px ${color})`;
      nDev++;
    }
    if (nDev) names.push(`${nDev} bound device(s)`);
    if (names.length) {
      this._status(
        `${(dev && dev.display_name) || devId} zone → ${names.join(', ')}`
      );
    }
  }

  // Menu → hfs editor: select the zone owner's marker on the shown
  // floor (no-op when it lives on another floor).
  _hfsSelectDevice(devId) {
    const info = window.__ramsesHfsInfo && window.__ramsesHfsInfo();
    const ed = info && info.editor;
    const floor =
      ed && ((info.layout && info.layout.floors) || {})[ed.floor];
    if (!ed || !ed.st || !floor) return;
    const i = (floor.devices || []).findIndex((d) => {
      const t = d.entity && this._entityDevice[d.entity];
      return t ? String(t.device_id) === devId : d.entity === devId;
    });
    ed.st.sel = i >= 0 ? { t: 'dev', i } : null;
    if (ed.requestUpdate) ed.requestUpdate();
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
          this._config.device_view_url ||
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
    const cur = sel.value;
    sel.innerHTML = '<option value="">(pick a device)</option>';
    for (const d of (this._topology && this._topology.devices) || []) {
      const o = document.createElement('option');
      o.value = d.device_id;
      const z = zones[d.device_id];
      o.textContent =
        `${d.device_id} ${d.device_class}` +
        (z ? ` ▸ ${(z.areas || []).length} room(s)` : '');
      sel.appendChild(o);
    }
    if (cur) sel.value = cur;
    this._fillZoneRow();
  }

  // The zone colour IS the studio room fill — the only colour the
  // studio inspector can edit. The swatch paints the zone's rooms
  // inside the project itself (no parallel store); `zone.color` stays
  // as the fallback for zones that have no rooms yet.
  _zitem(value, label, checked, disabled) {
    const l = document.createElement('label');
    l.className = 'zitem' + (disabled ? ' off' : '');
    const cb = document.createElement('input');
    cb.type = 'checkbox';
    cb.value = value;
    cb.checked = checked;
    cb.disabled = disabled;
    l.appendChild(cb);
    l.appendChild(document.createTextNode(label));
    return l;
  }

  async _fillZoneRow() {
    // Fill the rooms + markers checkbox lists with the selected
    // device's zone membership pre-checked, and the swatch with its
    // colour.
    const devSel = this.shadowRoot.getElementById('zone-dev');
    const roomsSel = this.shadowRoot.getElementById('zone-rooms');
    const memSel = this.shadowRoot.getElementById('zone-members');
    const inp = this.shadowRoot.getElementById('zone-color');
    if (!devSel || !roomsSel || !memSel || !inp) return;
    const devId = devSel.value;
    const zone = (((this._fpConfig || {}).device_zones || {})[devId]) || {};
    const zoneAreas = new Set((zone.areas || []).map((a) => this._slug(a)));
    const zoneDevs = new Set(zone.devices || []);
    roomsSel.innerHTML = '';
    let fill = null;
    const rooms = await this._projectRooms();
    for (const [id, r] of rooms) {
      const on = zoneAreas.has(this._slug(r.areaId));
      if (on && r.fill && !fill) fill = r.fill;
      roomsSel.appendChild(this._zitem(id, `${r.name} — ${r.floor}`, on));
    }
    memSel.innerHTML = '';
    const seen = new Set([devId]);
    for (const d of (this._topology && this._topology.devices) || []) {
      if (seen.has(d.device_id)) continue;
      // transport-layer devices (HGI/RFG/RFS) can never be zone
      // members — matches the export's zone_eligible check
      if (['HGI', 'RFG', 'RFS'].includes(d.device_class)) continue;
      seen.add(d.device_id);
      // schema children bind automatically via their parent link —
      // shown checked but not selectable, so autosave never writes
      // them into zone.devices
      const auto = d.parent === devId;
      memSel.appendChild(
        this._zitem(
          d.device_id,
          `${d.device_id} (${d.device_class})` + (auto ? ' · auto' : ''),
          auto || zoneDevs.has(d.device_id),
          auto
        )
      );
    }
    // bound ids that are not topology devices (DIY/zigbee entity ids) —
    // keep them listed so they can be unchecked
    for (const id of zoneDevs) {
      if (seen.has(id)) continue;
      memSel.appendChild(this._zitem(id, `${id} (entity)`, true));
    }
    // caption: the server resolves the current selection with the
    // same precedence the export uses — checked = what the card
    // shows. Entries outside the device entities stay listed (like
    // bound entities) so they can be unchecked
    const capSel = this.shadowRoot.getElementById('zone-caption');
    if (capSel) {
      capSel.innerHTML = '';
      const cfg = this._fpConfig || {};
      const picked = (cfg.device_captions || {})[devId] || [];
      const pickedIds = new Set(picked.map((p) => p[0]));
      const listed = new Set();
      const row = (pair, on, extra) =>
        capSel.appendChild(
          this._zitem(
            pair[0],
            `${pair[0]}${pair[1] ? ` ${pair[1]}` : ''}${extra}`,
            on
          )
        );
      for (const pair of (cfg.caption_choices || {})[devId] || []) {
        listed.add(pair[0]);
        row(pair, pickedIds.has(pair[0]), '');
      }
      for (const pair of picked) {
        if (!listed.has(pair[0])) row(pair, true, ' (entity)');
      }
    }
    inp.disabled = !devId;
    // zone.color is the highlight outline colour — an explicit pick
    // wins; a room fill is only the suggested default for new zones
    if (zone.color && /^#[0-9a-f]{6}$/i.test(zone.color)) inp.value = zone.color;
    else if (fill && /^#[0-9a-f]{6}$/i.test(fill)) inp.value = fill;
    else inp.value = '#22c55e';
    // marks the lists as populated *for this device* — _saveZone
    // refuses to snapshot while a rebuild for another device is
    // still in flight (an empty-looking list would wipe areas)
    this._zoneRowFor = devId;
  }

  async _saveZone() {
    const devSel = this.shadowRoot.getElementById('zone-dev');
    const devId = devSel && devSel.value;
    if (!devId) {
      this._status('Pick a device in the zone editor first');
      return;
    }
    if (this._zoneRowFor !== devId) {
      // the lists are still (re)building for this device — saving now
      // would snapshot an empty UI and wipe the zone; retry shortly
      this._queueZoneSave();
      return;
    }
    const roomsSel = this.shadowRoot.getElementById('zone-rooms');
    const memSel = this.shadowRoot.getElementById('zone-members');
    const inp = this.shadowRoot.getElementById('zone-color');
    const zone =
      (((this._fpConfig || {}).device_zones || {})[devId]) || {};
    const rooms = await this._projectRooms();
    // an empty list means "never populated" (no project/topology
    // loaded), not "user unchecked everything" — keep stored values
    const areas = roomsSel.children.length
      ? [
          ...new Set(
            [...roomsSel.querySelectorAll('input:checked')]
              .map((cb) => rooms.get(cb.value))
              .filter(Boolean)
              .map((r) => r.areaId)
          ),
        ]
      : zone.areas || [];
    // disabled boxes are schema children — auto-bound via their
    // parent link, never written into zone.devices
    const devices = memSel.children.length
      ? [...memSel.querySelectorAll('input:checked:not(:disabled)')]
          .map((cb) => cb.value)
          .filter(Boolean)
      : (zone.devices || []).filter(Boolean);
    const color = (inp && inp.value) || undefined;
    await this._call('floorplan_set_device_zone', {
      device_id: devId,
      areas,
      devices,
      ...(color ? { color } : {}),
    });
    // caption rides the same pick + debounce — an unpopulated list
    // (no config yet) preserves the stored caption, like the lists
    const capSel = this.shadowRoot.getElementById('zone-caption');
    if (capSel && capSel.children.length) {
      await this._call('floorplan_set_device_caption', {
        device_id: devId,
        entities: [...capSel.querySelectorAll('input:checked')].map(
          (cb) => cb.value
        ),
      });
    }
    await this._fetchConfig();
    if (typeof window.__ramsesHfsRefresh === 'function') {
      window.__ramsesHfsRefresh();
    }
    this._status(
      `Zone ${devId}: ${areas.length ? areas.join(', ') : 'no rooms'} ` +
        `+ ${devices.length} marker(s)` +
        (color ? ` — outline ${color}` : '') +
        ' — select its marker in studio to highlight'
    );
  }

  async _pull() {
    const project = await this._readStudioProject();
    if (!project) return; // _readStudioProject already reported
    await this._store(
      JSON.stringify(project),
      `pulled '${project.name || project.id}'`
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
    const tag = this._editorCaps && this._editorCaps.card_element;
    const el = tag ? _deepQuery(tag) : null;
    if (el && el.mounted) {
      // the remount briefly shows an empty selection — tell the
      // studio→menu sync that is not a user deselect
      this._suppressMenuClear = true;
      el.disconnectedCallback();
      el.connectedCallback();
      return true;
    }
    return false;
  }

  async _seed() {
    const data = {};
    if (this._config.floors) data.floors = this._config.floors;
    const size = this._config.marker_size;
    if (size) data.marker_size = size;
    const seedName = this._config.seed_name;
    if (seedName) data.name = seedName;
    // Merge into the selected studio project when one is open — keeps
    // walls, background and existing placement, only *new* devices get
    // centroid markers. Server-side editors (hfs) keep their plan in
    // HA storage already, so nothing is passed or pushed — the service
    // merges into the stored layout itself.
    const browserSide = !this._editorCaps || this._editorCaps.browser_side !== false;
    if (browserSide) {
      const selected = await this._readStudioProject(true);
      if (selected) data.project_json = JSON.stringify(selected);
    } else {
      // hfs: the seed merges into the *stored* layout — flush the open
      // editor's unsaved work first so it merges over the newest state
      // (their store rev-checks saves; a stale editor would conflict)
      const ed =
        window.__ramsesHfsInfo && window.__ramsesHfsInfo().editor;
      if (
        ed &&
        ed.st &&
        ed.st.dirty &&
        !(ed.placeRoom || ed.asideMode === 'place')
      ) {
        try {
          ed.save();
        } catch {
          /* the editor surfaces validation itself */
        }
        for (let i = 0; i < 30 && ed.st.dirty; i += 1)
          await new Promise((r2) => setTimeout(r2, 150));
      }
    }
    const r = await this._call('floorplan_seed_studio', data);
    const placed = Object.keys(r.placed || {}).length;
    const unplaced = (r.unplaced || []).length;
    if (!browserSide) {
      // Reload the open editor onto the new stored rev so the seeded
      // markers appear and its next save can't hit a stale-rev conflict
      const ed =
        window.__ramsesHfsInfo && window.__ramsesHfsInfo().editor;
      const panel = ed && ed.getRootNode && ed.getRootNode().host;
      if (panel && typeof panel.load === 'function' && !(ed.st && ed.st.dirty)) {
        try {
          await panel.load();
        } catch {
          /* panel reports its own load errors */
        }
      }
      this._status(
        `Seeded: ${placed} placed, ${unplaced} parked — written into ` +
          `${r.stored_at || 'editor storage'} (editor: ${r.editor || '?'}).`,
      );
      this._fillZoneRow();
      await this._export(true);
      return;
    }
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
      // the project write remounts studio and clears its selection —
      // reassert the stored zone membership in the editor
      this._fillZoneRow();
      this._refreshProjects();
    } else {
      this._status(`Seeded: ${placed} placed, ${unplaced} parked`);
    }
  }

  async _pushStored() {
    const r = await this._hass.callWS({
      type: 'ramses_extras/floorplan_helper/get_project',
      ...(this._editor ? { editor: this._editor } : {}),
    }).catch((err) => ({ __err: (err && err.message) || String(err) }));
    if (r.__err) {
      this._status(`HA → Studio: ${r.__err}`);
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
    this._fillZoneRow();
    this._refreshProjects();
  }

  async _export(apply) {
    // Snapshot live studio state first — the merged-SVG export reads
    // latest.json, so unsaved drags/recolours must be stored or they
    // silently don't make it into the output. Server-side editors
    // (hfs) already keep their plan in HA — nothing to snapshot.
    const browserSide = !this._editorCaps || this._editorCaps.browser_side !== false;
    let stored = '';
    if (browserSide) {
      const project = await this._readStudioProject();
      if (project) {
        const s = await this._call('floorplan_store_project', {
          project_json: JSON.stringify(project),
        });
        stored = ` (project snapshot: ${s.latest_path})`;
      }
    }
    // apply:true lets the service update every matching storage
    // dashboard itself; apply:false is generate + clipboard only
    const data = { apply: apply !== false };
    if (this._config.apply_dashboard) data.apply_dashboard = this._config.apply_dashboard;
    if (this._config.apply_match) data.apply_match = this._config.apply_match;
    const r = await this._call('floorplan_export', data);
    // stamp so the hfs overlay's save→export bridge dedupes this run
    window.__ramsesHfsLastExport = Date.now();
    const yamls = r.card_yamls || (r.card_yaml ? { default: r.card_yaml } : {});
    const floors = Object.keys(yamls);
    this._renderYamlButtons(yamls);
    const applied =
      r.applied && r.applied.cards
        ? ` — applied to ${r.applied.cards} card(s) on ${r.applied.dashboards} dashboard(s)`
        : data.apply
          ? ' — no matching floorplan card found (nothing applied)'
          : ' — dashboards untouched (⇒ Update cards applies)';
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

  async _store(text, via) {
    const r = await this._call('floorplan_store_project', { project_json: text });
    this._status(`Project ${via || 'stored'}: ${r.latest_path}`);
  }

  _readFile(file) {
    const reader = new window.FileReader();
    reader.onload = () =>
      this._run(() => this._store(String(reader.result || ''), `file '${file.name}'`));
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
        <div class="row" id="row-studio">
          <span class="lbl">studio project:</span>
          <select id="project"
            title="Projects stored in floorplan-studio (this browser). The one studio is currently editing is marked (current)."></select>
          <button id="b-pull" class="secondary"
            title="Save the selected studio project into Home Assistant (latest.json + a timestamped backup). Reads studio's live copy — it autosaves ~0.6s after each change">Studio → HA</button>
          <button id="b-push" class="secondary"
            title="Restore the stored HA project (latest.json) into this browser's studio — use after a browser/profile switch, or to roll studio back to the last saved version">HA → Studio</button>
        </div>
        <div class="row" id="row-editor" style="display:none">
          <button id="b-open-editor" class="secondary"
            title="Open the plan editor — its layout already lives in Home Assistant storage, so no pull/push is needed">Open editor</button>
        </div>
        <div class="row">
          <button id="b-seed" class="secondary"
            title="Add a studio marker for every ramses device or _extras entity (valves, zone sensors) missing from the selected project — existing markers keep position/style, new ones land at their room's centre or in the top-right dock. Nothing is removed">＋ Add devices</button>
          <button id="b-sync" class="secondary"
            title="Walk every studio room: link it to an HA area (creating the area if missing), then set the HA area of every entity whose marker sits inside that room's polygon. This makes the drawing drive real HA areas, so dashboards and automations can group by area">Sync areas → HA</button>
          <button id="b-export" class="secondary"
            title="Snapshot the selected studio project and regenerate the card files (merged SVG + state rules + captions). The card YAML is copied to your clipboard — dashboard cards are NOT updated (use ⇒ Update cards for that)">Export ⇒</button>
          <button id="b-apply" class="secondary"
            title="Same as Export ⇒, plus every floorplan card on your dashboards that shows a generated map is updated in place — no edit mode, no paste needed">⇒ Update cards</button>
          <button id="b-tweaks" class="secondary"
            title="Zone editor — which rooms and markers belong to each device's zone">⚙ Zones</button>
          <button id="b-reset" class="secondary"
            title="Reset the stored plan to the first-install (empty) state — a canonical backup is written first. hfs's own Reset only blanks the editor in memory and its validator will not save a fully blank plan; this actually clears the store">⌫ Reset</button>
        </div>
        <div class="tweaks" id="tweaks" style="display:none">
          <div class="row">
            <label for="zone-dev"
              title="A zone = the rooms a device serves + the extra markers bound to it. Select a marker in studio → its device lands here; pick one here → it gets selected in studio. Tap the device's marker → its rooms and bound markers light up in the zone colour.">Zone of</label>
            <select id="zone-dev" style="max-width:220px"
              title="Device whose zone you are editing — also follows the marker selected in studio"></select>
            <input id="zone-color" type="color" style="width:36px;padding:0;height:24px"
              title="Zone colour — the outline/highlight colour shown when this zone is selected; room fills stay whatever studio's inspector set. Autosaves">
          </div>
          <div class="row zcols">
            <div class="zcol">
              <span class="lbl">Serves rooms</span>
              <div id="zone-rooms" class="zlist"
                title="Every room in the studio project — check the rooms this device serves; they highlight when the zone marker is tapped. Synced both ways with studio's selection — click to toggle, changes autosave"></div>
            </div>
            <div class="zcol">
              <span class="lbl">Bound markers</span>
              <div id="zone-members" class="zlist"
                title="Extra markers bound to the zone — they highlight along with the rooms (e.g. DIY valve covers under a FAN zone). '· auto' entries come from the ramses schema's parent link — already bound. Synced with studio's marker selection — click to toggle, changes autosave"></div>
            </div>
            <div class="zcol">
              <span class="lbl">Caption</span>
              <div id="zone-caption" class="zlist"
                title="Entity states shown under this device's marker — untick all to hide the caption. Alternative: attach extra entities to the marker in studio and they show too. Autosaves"></div>
            </div>
          </div>
        </div>
        <div class="drop" id="drop" tabindex="0"
          title="For project files from another machine or a backup — this browser's studio is already reachable via Studio → HA">
          Drop a studio project JSON here
          <span class="droplinks">
            <a href="#" id="drop-browse">browse</a> ·
            <a href="#" id="drop-paste">paste</a>
          </span>
          — fallback for files from another machine or backup
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

    $('b-pull').onclick = () => this._run(() => this._pull());
    $('b-seed').onclick = () => this._run(() => this._seed());
    $('b-push').onclick = () => this._run(() => this._pushStored());
    $('b-open-editor').onclick = () =>
      this._navigate((this._fpConfig && this._fpConfig.editor_url) || '');
    $('b-export').onclick = () => this._run(() => this._export(false));
    $('b-apply').onclick = () => this._run(() => this._export(true));
    $('b-sync').onclick = () => this._run(() => this._sync());
    $('b-tweaks').onclick = () => {
      const t = $('tweaks');
      t.style.display = t.style.display === 'none' ? 'block' : 'none';
    };
    $('b-reset').onclick = () => {
      if (
        !window.confirm(
          'Reset the stored plan to empty? The editor will show "no plan" ' +
            '— the first-install state. A canonical backup is written first.'
        )
      )
        return;
      this._run(async () => {
        const r = await this._call('floorplan_reset', {});
        this._status(`Plan reset to empty (backup: ${r.backup_path || 'none'})`);
      });
    };

    // zone editor: picking a device pre-checks its rooms + markers,
    // selects its marker in studio, and shows its colour (studio room
    // fill → zone.color → default). Listbox edits mirror into studio's
    // selection and autosave; studio clicks mirror back via the poll.
    $('zone-dev').onchange = () => {
      this._fillZoneRow();
      const devSel = $('zone-dev');
      if (devSel.value) {
        if (this._resolvedEditor === 'hfs') {
          this._hfsSelectDevice(devSel.value);
        } else {
          this._ensureStudioEdit();
          this._studioClick(this._studioElForMember(devSel.value), false);
        }
      }
    };
    $('zone-rooms').onchange = () => this._pushZoneSelToStudio();
    $('zone-members').onchange = () => this._pushZoneSelToStudio();
    // caption edits don't touch studio selection — autosave only
    $('zone-caption').onchange = () => this._queueZoneSave();
    // the swatch is the highlight outline colour — stored on the
    // zone, it never repaints the rooms' base fills
    $('zone-color').onchange = () => this._queueZoneSave();
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
      const url = this._config.device_view_url;
      if (url) {
        closePanel();
        this._navigate(url);
      }
    };

    this._fillProjectSelect();

    const drop = $('drop');
    const file = $('file');
    drop.onclick = () => file.click();
    $('drop-browse').onclick = (e) => {
      e.preventDefault();
      e.stopPropagation();
      file.click();
    };
    $('drop-paste').onclick = async (e) => {
      e.preventDefault();
      e.stopPropagation();
      try {
        const text = await navigator.clipboard.readText();
        if (!text.trim().startsWith('{')) {
          this._status('Paste ignored — clipboard does not hold JSON text');
          return;
        }
        this._run(() => this._store(text, 'pasted JSON'));
      } catch (err) {
        this._status(`Clipboard read failed (${err.message}) — click the dropzone and Ctrl+V instead`);
      }
    };
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
    drop.onpaste = (e) => {
      const text = (e.clipboardData || window.clipboardData)?.getData('text') || '';
      if (!text.trim().startsWith('{')) return; // let other pastes through
      e.preventDefault();
      this._run(() => this._store(text, 'pasted JSON'));
    };

    // editor capability rows (studio pull/push vs hfs open-editor)
    // survive a re-render this way — _fetchConfig may resolve after
    // the DOM was already built
    this._applyEditorCaps();
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
function _fpIsHfsCard(el) {
  return (
    (el.tagName === 'HFS-FLOORPLAN-CARD' ||
      el.tagName === 'FLOORPLAN-STUDIO-CARD') &&
    typeof el._floorKey === 'function'
  );
}

function _fpFloorplanCards() {
  const cards = [];
  const walk = (root) => {
    for (const el of root.querySelectorAll('*')) {
      if (el.tagName === 'FLOORPLAN-CARD' || _fpIsHfsCard(el))
        cards.push(el);
      if (el.shadowRoot) walk(el.shadowRoot);
    }
  };
  walk(document);
  return cards;
}

function _fpZoneApply(toggles, clear, skipCard) {
  for (const card of _fpFloorplanCards()) {
    if (_fpIsHfsCard(card)) {
      // index-based DOM — the overlay module resolves the logical
      // element ids; skipCard is honoured inside the overlay
      window.__ramsesHfsZoneApply?.(card, toggles, clear, card === skipCard);
      continue;
    }
    if (skipCard && card === skipCard) continue;
    const strip = (root, keepClasses) => {
      for (const el of root.querySelectorAll('[class]')) {
        for (const c of [...(el.classList || [])]) {
          if (c.startsWith('rx-zone-') && (!keepClasses || !keepClasses.has(c)))
            el.classList.remove(c);
        }
      }
    };
    if (clear && !(toggles || []).length) {
      // blanket clear: strip every rx-zone-* class on this card —
      // used by the device-view bridge before the popup opens
      strip(card.shadowRoot || card);
      continue;
    }
    if (!clear && (toggles || []).length) {
      const incoming = new Set((toggles || []).map((t) => t.class));
      strip(card.shadowRoot || card, incoming);
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
