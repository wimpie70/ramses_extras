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
  input[type=file] { display: none; }
`;

const TWEAKS_KEY = 'ramses-floorplan-actions-tweaks';

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
    this._projects = [];   // studio projects [{id, name, updatedAt}]
    this._busy = false;
    this._tweaks = {};
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
    if (!this._fpConfig && hass) {
      this._fetchConfig();
      this._refreshProjects();
    }
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
    const el = document.querySelector('floorplan-studio-card');
    return el && el.shadowRoot ? el.shadowRoot : null;
  }

  _studioSelectedMarkers() {
    // Selected markers render a dashed #38bdf8 ring as first child of
    // their <g translate(x y)> inside the entities layer (edit mode only).
    const root = this._studioRoot();
    if (!root) return [];
    return [...root.querySelectorAll('g[data-layer="entities"] > g')]
      .map((g) => {
        const ring = g.querySelector(':scope > circle');
        const sel =
          ring &&
          ring.getAttribute('stroke') === '#38bdf8' &&
          ring.getAttribute('stroke-dasharray');
        const m = /translate\(\s*([-\d.e]+)[ ,]+([-\d.e]+)\s*\)/.exec(
          g.getAttribute('transform') || ''
        );
        return sel && m ? { x: parseFloat(m[1]), y: parseFloat(m[2]), el: g } : null;
      })
      .filter(Boolean);
  }

  _fiberMarker(g) {
    // Walk the React fiber for the host <g> up to MarkerNode, whose
    // props carry the live marker object from studio's store — mutating
    // it makes the change part of studio's own state (persisted by its
    // autosave on the next edit).
    const key = Object.keys(g).find((k) => k.startsWith('__reactFiber$'));
    let f = key ? g[key] : null;
    while (f) {
      if (f.memoizedProps && f.memoizedProps.marker) return f.memoizedProps.marker;
      f = f.return;
    }
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
      this._status('No markers selected in studio (switch to edit mode, select with the select tool)');
      return;
    }
    let mutated = 0;
    for (const m of sel) {
      const marker = this._fiberMarker(m.el);
      if (marker && marker.style) {
        marker.style.size = size;
        mutated += 1;
      }
      this._patchMarkerDom(m.el, size);
    }
    // also persist into studio's stored project so a reload keeps it
    const id = this._selectedProjectId();
    if (id) {
      try {
        const db = await openFpDb();
        const project = await idbReq(db.transaction('projects').objectStore('projects').get(id));
        if (project) {
          let n = 0;
          for (const floor of project.floors || []) {
            for (const mk of floor.markers || []) {
              if (sel.some((s) => Math.abs(mk.x - s.x) < 0.5 && Math.abs(mk.y - s.y) < 0.5)) {
                mk.style.size = size;
                n += 1;
              }
            }
          }
          await idbReq(db.transaction('projects', 'readwrite').objectStore('projects').put(project));
          db.close();
          this._status(
            `Resized ${sel.length} selected marker(s) to ${size}px` +
              (mutated === sel.length ? '' : ` (${sel.length - mutated} patched in DOM only)`) +
              `, ${n} written to project storage`
          );
          return;
        }
        db.close();
      } catch { /* fall through to DOM-only message */ }
    }
    this._status(`Resized ${sel.length} selected marker(s) to ${size}px (DOM only)`);
  }

  _selectedProjectId() {
    const sel = this.shadowRoot.getElementById('project');
    return sel && sel.value ? sel.value : null;
  }

  async _pull() {
    const id = this._selectedProjectId();
    if (!id) { this._status('No studio project selected'); return; }
    const db = await openFpDb();
    const project = await idbReq(
      db.transaction('projects').objectStore('projects').get(id)
    );
    db.close();
    if (!project) { this._status('Project not found in studio storage'); return; }
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
      `pulled '${project.name || id}'` + (resized ? `, ${resized} markers resized` : '')
    );
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
    this._status(this._syncSummary(r));
  }

  _syncSummary(r) {
    const a = r.assignments || [];
    const c = r.areas_created || [];
    const o = r.entities_without_area_room || [];
    return `Sync: ${a.length} entities assigned, ${c.length} areas created` +
      (o.length ? `, ${o.length} outside rooms` : '') +
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
          <button id="b-tweaks" class="secondary"
            title="Card tweaks — saved in this browser">⚙ Tweaks</button>
        </div>
        <div class="tweaks" id="tweaks" style="display:none">
          <div class="row">
            <label for="tw-size" title="Icon size in px for markers generated by Seed">Marker icon size</label>
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
        </div>
        <div class="drop" id="drop"
          title="For project files from another machine or a backup — this browser's studio is already reachable via Pull">
          Drop a studio project JSON here (or click to browse) — fallback
          for files from another machine or backup
          <input id="file" type="file" accept=".json,application/json">
        </div>
        <textarea class="log" id="status" readonly
          title="Result log — selectable, copy with Ctrl+C"></textarea>
      </ha-card>`;

    const $ = (id) => this.shadowRoot.getElementById(id);
    $('b-studio').onclick = () =>
      this._navigate(this._config.studio_url || (this._fpConfig || {}).planner_url || '/floorplan-studio');
    $('b-pull').onclick = () => this._run(() => this._pull());
    $('b-seed').onclick = () => this._run(() => this._seed());
    $('b-export').onclick = () => this._run(() => this._export());
    $('b-sync').onclick = () => this._run(() => this._sync());
    $('b-resize').onclick = () => this._run(() => this._resizeSelected());
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
    twSize.onchange = () =>
      this._saveTweak('marker_size', twSize.value ? Number(twSize.value) : undefined);
    twName.onchange = () => this._saveTweak('seed_name', twName.value || undefined);
    twSync.onchange = () => this._saveTweak('sync_on_pull', twSync.checked);
    twNorm.onchange = () => this._saveTweak('normalize_sizes', twNorm.checked);

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

window.customCards = window.customCards || [];
window.customCards.push({
  type: 'ramses-floorplan-actions',
  name: 'Ramses Floorplan Actions',
  description: 'Action bar + studio project bridge for floorplan-studio workflows',
});
