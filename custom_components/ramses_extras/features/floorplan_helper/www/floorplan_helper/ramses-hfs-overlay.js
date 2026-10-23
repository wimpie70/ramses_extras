/**
 * Ramses Extras — hfs card overlay.
 *
 * Layers our gesture + zone semantics onto vespassassina's
 * `hfs-floorplan-card` renderer (their card draws walls/rooms/3D
 * natively; this module adds what their renderer cannot express):
 *
 *   tap a device marker   -> zone toggle for zone owners, else our
 *                            device popup (hvac-fan card etc.)
 *   double tap a device   -> always our device popup
 *   zone highlight        -> the module listens for the same
 *                            `floorplan_zone_toggle` event the
 *                            floorplan-card path uses and paints an
 *                            overlay layer inside their <svg>
 *
 * Their card's `tap_action`/`hold_action` only offer
 * popup|more-info|toggle|none (no fire-dom-event), so the card is
 * configured with `tap_action: none` and this layer owns gestures.
 * Hold still fires their native more-info.
 *
 * The element ids in zone toggles are our logical ids
 * (`area.<room slug>`, entity ids, `device.<id>`); the overlay maps
 * them to the card's index-based DOM (`data-r`, `data-x`) using the
 * stored layout — nothing is written back into their JSON.
 */
/* global MutationObserver, DOMParser */

'use strict';

const DOMAIN = 'ramses_extras';
const HFS_TAG = 'HFS-FLOORPLAN-CARD';
const HFS_PANEL_TAG = 'FLOORPLAN-STUDIO-PANEL';
const TAP_SLOP_PX = 6; // their own pan-vs-tap threshold (actions.ts)
const OVERLAY_ID = 'ramses-hfs-overlay';
const CAPTIONS_ID = 'ramses-hfs-captions';
const ANIM_STYLE_ID = 'ramses-hfs-anim';
const SYMBOL_SHEET =
  '/local/ramses_extras/features/floorplan_helper/symbol-sheet.svg';

let _hfsLayout = null; // floorplan_studio/load payload
let _entityDevice = {}; // entity_id -> topology device record
let _deviceById = {}; // device_id -> topology device record
let _zones = {}; // device_zones option {device_id: {areas, devices, color}}
let _deviceIcons = {}; // device_id -> ramses icon key (icon_for_device)
let _deviceRoles = {}; // device_id -> {role: [entity_ids]} (CLASS_ROLES)
let _deviceCaptions = {}; // device_id -> [[entity_id, suffix], ...]
let _deviceDomains = {}; // device_id -> 'hvac' | 'heat'
let _stateEnts = new Set(); // every entity that can drive color/spin

// Domain tints — the base marker colour, below the rx-* state signals.
const DOMAIN_TINTS = { hvac: '#1b5e20', heat: '#0d47a1' };

// Non-ramses entities (DIY valves, sensors) have no topology device —
// same entity-domain fallback the generated card applies
// (markers.py _ENTITY_DOMAIN_ICONS).
const ENTITY_ICONS = {
  cover: 'pipe-valve',
  valve: 'pipe-valve',
  sensor: 'gauge',
  binary_sensor: 'thermometer',
};
let _iconPaths = null; // icon key -> mdi path d, from the symbol sheet
let _started = false;

function _hfsHass() {
  const ha = document.querySelector('home-assistant');
  return ha ? ha.hass : null;
}

function _slug(value) {
  return String(value || '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/_+/g, '_')
    .replace(/^_|_$/g, '');
}

async function _hfsLoadState() {
  const hass = _hfsHass();
  if (!hass || !hass.callWS) return;
  try {
    const topo = await hass.callWS({
      type: 'ramses_extras/floorplan_helper/get_topology',
    });
    _entityDevice = {};
    _deviceById = {};
    for (const d of (topo && topo.devices) || []) {
      const did = String(d.device_id || '');
      if (did) _deviceById[did] = d;
      if (d.primary_entity) _entityDevice[d.primary_entity] = d;
      for (const e of d.entities || []) {
        if (e.entity_id) _entityDevice[e.entity_id] = d;
      }
    }
  } catch {
    _entityDevice = {};
    _deviceById = {};
  }
  try {
    const cfg = await hass.callWS({
      type: 'ramses_extras/floorplan_helper/get_config',
    });
    _zones = cfg.device_zones || {};
    _deviceIcons = cfg.device_icons || {};
    _deviceRoles = cfg.device_roles || {};
    _deviceCaptions = cfg.device_captions || {};
    _deviceDomains = cfg.device_domains || {};
    _stateEnts = new Set();
    for (const roles of Object.values(_deviceRoles)) {
      for (const ents of Object.values(roles)) {
        for (const eid of ents) _stateEnts.add(eid);
      }
    }
    for (const pairs of Object.values(_deviceCaptions)) {
      for (const p of pairs) _stateEnts.add(p[0]);
    }
  } catch {
    _zones = {};
    _deviceIcons = {};
    _deviceRoles = {};
    _deviceCaptions = {};
    _deviceDomains = {};
  }
  await _hfsLoadIcons();
  await _hfsLoadLayout();
}

// The mdi paths behind our icon keys already ship in the
// floorplan-helper symbol sheet — parse them once so hfs's `other`
// glyph can be swapped for the same icon the generated card shows.
async function _hfsLoadIcons() {
  if (_iconPaths) return;
  _iconPaths = {};
  try {
    const res = await fetch(SYMBOL_SHEET);
    const doc = new DOMParser().parseFromString(
      await res.text(),
      'image/svg+xml'
    );
    for (const sym of doc.querySelectorAll('symbol[id^="icon."]')) {
      const paths = sym.querySelectorAll('path[d]');
      const last = paths[paths.length - 1];
      if (last) _iconPaths[sym.id.slice(5)] = last.getAttribute('d');
    }
  } catch {
    _iconPaths = {};
  }
}

async function _hfsLoadLayout() {
  const hass = _hfsHass();
  if (!hass || !hass.callWS) return;
  try {
    const r = await hass.callWS({ type: 'floorplan_studio/load' });
    _hfsLayout = (r && r.layout) || r || null;
  } catch {
    _hfsLayout = null;
  }
  _hfsRepaintAll();
}

// --- per-card plumbing ----------------------------------------------------

function _hfsCards() {
  const cards = [];
  const walk = (root) => {
    for (const el of root.querySelectorAll('*')) {
      if (el.tagName === HFS_TAG) cards.push(el);
      if (el.shadowRoot) walk(el.shadowRoot);
    }
  };
  walk(document);
  return cards;
}

function _hfsFloorKey(card) {
  // The card keeps the shown floor on `_floorKey()` (no data attribute
  // in the DOM); fall back to the only floor when there's just one.
  try {
    const k = typeof card._floorKey === 'function' ? card._floorKey() : null;
    if (k && _hfsLayout && _hfsLayout.floors && _hfsLayout.floors[k]) return k;
  } catch {
    /* private-shape drift — fall through to the single-floor guess */
  }
  const keys = Object.keys((_hfsLayout && _hfsLayout.floors) || {});
  return keys.length === 1 ? keys[0] : null;
}

function _hfsFloor(card) {
  const key = _hfsFloorKey(card);
  return key ? _hfsLayout.floors[key] : null;
}

function _hfsDevice(card, index) {
  const floor = _hfsFloor(card);
  return ((floor && floor.devices) || [])[index] || null;
}

// --- gestures --------------------------------------------------------------

function _hfsTapDevice(card, index) {
  const dev = _hfsDevice(card, index);
  const entity = dev && dev.entity;
  if (!entity) return;
  const topo = _entityDevice[entity];
  const did = String((topo && topo.device_id) || '');
  const hass = _hfsHass();
  if (!hass || !hass.callService) return;
  if (did && _zones[did]) {
    // zone owner: tap toggles the zone, resolved server-side
    hass.callService(DOMAIN, 'floorplan_zone_toggle', { device_id: did });
  } else {
    hass.callService(DOMAIN, 'floorplan_device_view', { entity });
  }
}

function _hfsOpenDevice(card, index) {
  const dev = _hfsDevice(card, index);
  if (dev && dev.entity) {
    const hass = _hfsHass();
    if (hass && hass.callService) {
      hass.callService(DOMAIN, 'floorplan_device_view', { entity: dev.entity });
    }
  }
}

function _hfsAttach(card) {
  if (card.__rxHfsAttached) return;
  const root = card.shadowRoot;
  if (!root) return; // retried by the scan loop
  card.__rxHfsAttached = true;
  card.__rxZones = new Map(); // class -> Set of logical element ids

  let down = null;
  root.addEventListener(
    'pointerdown',
    (e) => {
      if (e.isPrimary === false) down = null;
      else down = { x: e.clientX, y: e.clientY };
    },
    true
  );
  root.addEventListener(
    'pointerup',
    (e) => {
      if (!down) return;
      const dx = e.clientX - down.x;
      const dy = e.clientY - down.y;
      down = null;
      if (dx * dx + dy * dy > TAP_SLOP_PX * TAP_SLOP_PX) return; // a pan
      const g =
        e.target && e.target.closest
          ? e.target.closest('g[data-x]')
          : null;
      if (g) _hfsTapDevice(card, Number(g.getAttribute('data-x')));
    },
    true
  );
  root.addEventListener(
    'dblclick',
    (e) => {
      const g =
        e.target && e.target.closest
          ? e.target.closest('g[data-x]')
          : null;
      if (g) _hfsOpenDevice(card, Number(g.getAttribute('data-x')));
    },
    true
  );

  // their card re-renders the svg on state changes; re-paint the zone
  // overlay whenever the plan subtree is swapped out from under it.
  // Mutations *inside* our own overlay layer are ignored — painting
  // would otherwise retrigger the observer in an endless loop.
  const mo = new MutationObserver((records) => {
    for (const r of records) {
      const own = (n) =>
        n &&
        n.nodeType === 1 &&
        (n.id === OVERLAY_ID ||
          n.id === ANIM_STYLE_ID ||
          n.id === CAPTIONS_ID ||
          (n.closest && n.closest(`#${OVERLAY_ID},#${CAPTIONS_ID}`)));
      if (r.target && r.target.nodeType === 1 && own(r.target)) continue;
      if (r.type === 'attributes') {
        // live patches write attributes — re-decorate unless the write
        // was ours (a converged value produces no follow-up change)
        _hfsQueuePaint(card);
        return;
      }
      let allOwn = true;
      for (const n of [...r.addedNodes, ...r.removedNodes]) {
        if (!own(n)) {
          allOwn = false;
          break;
        }
      }
      if (!allOwn) {
        _hfsQueuePaint(card);
        return;
      }
    }
  });
  mo.observe(root, {
    childList: true,
    subtree: true,
    attributes: true,
    attributeFilter: ['d', 'style'],
  });
  _hfsPaint(card);
}

function _hfsQueuePaint(card) {
  // coalesce a render burst into one paint per microtask
  if (card.__rxPaintQueued) return;
  card.__rxPaintQueued = true;
  Promise.resolve().then(() => {
    card.__rxPaintQueued = false;
    _hfsPaint(card);
  });
}

// --- zone overlay ----------------------------------------------------------

function _hfsRoomIndex(floor, slug) {
  const rooms = (floor && floor.rooms) || [];
  return rooms.findIndex(
    (r) => _slug(r.area) === slug || _slug(r.name) === slug
  );
}

function _hfsDeviceIndex(floor, elementId) {
  const devices = (floor && floor.devices) || [];
  // element ids are entity ids, or `device.<did>` as fallback
  let want = elementId;
  if (want.startsWith('device.')) {
    const dev = _deviceById[want.slice(7)];
    want = (dev && dev.primary_entity) || '';
    if (!want) return -1;
  }
  return devices.findIndex((d) => String(d.entity || '') === want);
}

function _hfsZoneColor(cls) {
  // rx-zone-<slug did>[-dev]
  const m = /^rx-zone-(.+?)(-dev)?$/.exec(cls);
  if (!m) return null;
  for (const [did, z] of Object.entries(_zones)) {
    if (_slug(did) === m[1]) return z.color || '#22c55e';
  }
  return '#22c55e';
}

// Same speed->duration mapping the generated card's rx-spin* rules
// compute: >75% fast, >40% medium, >0% slow; mode names for
// text-valued sensors. Entities are pre-sorted speed-first.
function _hfsSpinDuration(did) {
  const roles = _deviceRoles[did];
  const ents = roles && roles.fan_rate;
  if (!ents || !ents.length) return null;
  const hass = _hfsHass();
  if (!hass) return null;
  for (const eid of ents) {
    const st = hass.states[eid];
    if (!st) continue;
    const s = String(st.state).toLowerCase();
    const n = parseFloat(s);
    if (n > 75) return '0.7s';
    if (n > 40) return '1.4s';
    if (n > 0) return '3.2s';
    if (`|high|boost|`.includes(`|${s}|`)) return '0.7s';
    if (`|medium|normal|`.includes(`|${s}|`)) return '1.4s';
    if (`|low|auto|away|`.includes(`|${s}|`)) return '3.2s';
  }
  return null;
}

// Extras markers that aren't topology devices (DIY valves, zigbee
// sensors) tint by the zone owner they belong to.
function _hfsZoneOwner(entity) {
  for (const [did, z] of Object.entries(_zones)) {
    if ((z.devices || []).includes(entity)) return did;
  }
  return null;
}

// State colours mirroring the generated card's rx-* classes — the
// same stylesheet-order precedence (later rule wins): window_open >
// heat_demand > offline > domain tint > online. Devices with no
// class roles and no domain keep the hfs-native idle look.
// Returns {fill, opacity} or null.
function _hfsStateColor(did, entity) {
  const hass = _hfsHass();
  const roles = (did && _deviceRoles[did]) || null;
  const any =
    hass && roles
      ? (role, pred) =>
          (roles[role] || []).some((e) => {
            const st = hass.states[e];
            return st && pred(String(st.state).toLowerCase());
          })
      : () => false;
  if (any('window_open', (s) => s === 'on'))
    return { fill: '#039be5', opacity: '1' };
  if (any('heat_demand', (s) => Number(s) > 0))
    return { fill: '#ef6c00', opacity: '1' };
  if (
    roles &&
    roles.status &&
    roles.status.length &&
    !any('status', (s) => s === 'on')
  )
    return { fill: '#9e9e9e', opacity: '0.65' };
  const dom =
    (did && _deviceDomains[did]) ||
    _deviceDomains[_hfsZoneOwner(entity)] ||
    '';
  if (DOMAIN_TINTS[dom]) return { fill: DOMAIN_TINTS[dom], opacity: '1' };
  if (any('status', (s) => s === 'on'))
    return { fill: '#2e7d32', opacity: '1' };
  return null;
}

// Inject the spin keyframes once per shadow root (a childList write
// our observer skips via its id).
function _hfsAnimStyle(root) {
  if (root.getElementById(ANIM_STYLE_ID)) return;
  const st = document.createElement('style');
  st.id = ANIM_STYLE_ID;
  st.textContent = '@keyframes rx-hfs-spin{to{transform:rotate(360deg)}}';
  root.prepend(st);
}

// Per-device decoration: swap the icon path's `d` for our ramses icon
// (their `other` glyph is a '?') and give fan markers the
// speed-proportional spin the generated card applies via rx-spin*.
// Attribute/style writes don't reach the childList observer, so this
// is loop-free.
function _hfsDecorate(svg, floor) {
  if (!floor) return;
  const devices = floor.devices || [];
  for (const g of svg.querySelectorAll('g.dev[data-x]')) {
    const dev = devices[Number(g.getAttribute('data-x'))];
    if (!dev || !dev.entity) continue;
    const topo = _entityDevice[dev.entity];
    const did = topo && String(topo.device_id || '');
    const icon =
      g.querySelector('circle.halo + path') ||
      g.querySelector('path:not(.cone)');
    if (!icon) continue;
    const key =
      (did && _deviceIcons[did]) ||
      ENTITY_ICONS[String(dev.entity).split('.')[0]];
    const d = key && _iconPaths && _iconPaths[key];
    if (d && icon.getAttribute('d') !== d) icon.setAttribute('d', d);
    const dur = did && _hfsSpinDuration(did);
    const want = dur ? `rx-hfs-spin ${dur} linear infinite` : '';
    if (icon.style.animation !== want) {
      icon.style.animation = want;
      icon.style.transformBox = dur ? 'fill-box' : '';
      icon.style.transformOrigin = dur ? 'center' : '';
    }
    const color = _hfsStateColor(did, dev.entity);
    const fill = color ? color.fill : '';
    const opacity = color ? color.opacity : '';
    if (icon.style.fill !== fill) icon.style.fill = fill;
    if (icon.style.fillOpacity !== opacity) icon.style.fillOpacity = opacity;
  }
}

// State captions under each marker — the same pairs the generated
// card's text_set emits (entity state + suffix, ' / '-joined). The
// marker's own transform carries its centre and scale: icon box is
// 24 local units, so centre = translate + 12k and the halo ends at
// 16k. Lives in its own layer so a rebuild never fights hfs's DOM.
function _hfsCaptions(svg, floor) {
  const ns = 'http://www.w3.org/2000/svg';
  let layer = svg.querySelector(`#${CAPTIONS_ID}`);
  const hass = _hfsHass();
  const caps = [];
  if (floor && hass) {
    for (const g of svg.querySelectorAll('g.dev[data-x]')) {
      const dev = (floor.devices || [])[Number(g.getAttribute('data-x'))];
      if (!dev || !dev.entity) continue;
      const topo = _entityDevice[dev.entity];
      const did = topo && String(topo.device_id || '');
      const pairs = did && _deviceCaptions[did];
      if (!pairs || !pairs.length) continue;
      const parts = [];
      for (const p of pairs) {
        const st = hass.states[p[0]];
        if (st) parts.push(String(st.state) + (p[1] || ''));
      }
      if (!parts.length) continue;
      let cx = dev.x;
      let cy = dev.y;
      let k = 1;
      const m =
        /translate\(\s*([-\d.e]+)[ ,]+([-\d.e]+)\s*\)\s*scale\(\s*([-\d.e]+)\s*\)/.exec(
          g.getAttribute('transform') || ''
        );
      if (m) {
        k = parseFloat(m[3]);
        cx = parseFloat(m[1]) + 12 * k;
        cy = parseFloat(m[2]) + 12 * k;
      }
      if (!Number.isFinite(cx) || !Number.isFinite(cy)) continue;
      caps.push({ x: cx, y: cy + 22 * k, k, s: parts.join(' / ') });
    }
  }
  if (!caps.length) {
    if (layer) layer.remove();
    return;
  }
  if (!layer) {
    layer = document.createElementNS(ns, 'g');
    layer.id = CAPTIONS_ID;
    layer.setAttribute('pointer-events', 'none');
    svg.appendChild(layer);
  }
  layer.textContent = '';
  for (const c of caps) {
    const t = document.createElementNS(ns, 'text');
    t.setAttribute('x', String(c.x));
    t.setAttribute('y', String(c.y));
    t.setAttribute('text-anchor', 'middle');
    t.setAttribute('font-size', String(11 * c.k));
    t.setAttribute('fill', 'var(--fp-text)');
    t.setAttribute('paint-order', 'stroke');
    t.setAttribute('stroke', 'var(--fp-bg)');
    t.setAttribute('stroke-width', String(2.5 * c.k));
    t.textContent = c.s;
    layer.appendChild(t);
  }
}

function _hfsPaint(card) {
  if (!card.shadowRoot || !card.__rxZones) return;
  _hfsAnimStyle(card.shadowRoot);
  const svg = card.shadowRoot.querySelector('svg');
  const floor = _hfsFloor(card);
  if (svg) {
    _hfsDecorate(svg, floor);
    _hfsCaptions(svg, floor);
  }
  const state = card.__rxZones;
  const stale = svg && svg.querySelector(`#${OVERLAY_ID}`);

  // nothing to paint: don't create the layer — an appended node in the
  // observed subtree costs an observer round-trip on every re-render
  if (![...state.values()].some((ids) => ids.size)) {
    if (stale) stale.remove();
    return;
  }
  let layer = stale;
  if (svg && !layer) {
    layer = document.createElementNS('http://www.w3.org/2000/svg', 'g');
    layer.id = OVERLAY_ID;
    layer.setAttribute('pointer-events', 'none');
    svg.appendChild(layer);
  }
  if (!layer) return;
  layer.textContent = '';

  if (!floor) return;

  for (const [cls, ids] of state) {
    if (!ids.size) continue;
    const color = _hfsZoneColor(cls);
    for (const id of ids) {
      if (id.startsWith('area.')) {
        const i = _hfsRoomIndex(floor, id.slice(5));
        const room = floor.rooms[i];
        if (i < 0 || !room || !room.pts) continue;
        const poly = document.createElementNS(
          'http://www.w3.org/2000/svg',
          'polygon'
        );
        poly.setAttribute(
          'points',
          room.pts.map((p) => `${p[0]},${p[1]}`).join(' ')
        );
        poly.setAttribute('fill', color);
        poly.setAttribute('fill-opacity', '0.18');
        poly.setAttribute('stroke', color);
        poly.setAttribute('stroke-width', '3');
        poly.setAttribute('vector-effect', 'non-scaling-stroke');
        layer.appendChild(poly);
      } else {
        const i = _hfsDeviceIndex(floor, id);
        const dev = floor.devices[i];
        if (i < 0 || !dev || dev.x === undefined) continue;
        const ring = document.createElementNS(
          'http://www.w3.org/2000/svg',
          'circle'
        );
        ring.setAttribute('cx', String(dev.x));
        ring.setAttribute('cy', String(dev.y));
        ring.setAttribute('r', '30');
        ring.setAttribute('fill', 'none');
        ring.setAttribute('stroke', color);
        ring.setAttribute('stroke-width', '4');
        ring.setAttribute('vector-effect', 'non-scaling-stroke');
        ring.setAttribute('stroke-dasharray', '8 5');
        layer.appendChild(ring);
      }
    }
  }
}

const _hfsPanels = new Set();

function _hfsRepaintAll() {
  for (const card of _hfsCards()) _hfsPaint(card);
  for (const panel of _hfsPanels) _hfsDecoratePanel(panel);
}

// Entry point used by the floorplan-actions module's zone apply —
// toggles carry {class, elements} with logical ids; `toggle` flips
// membership exactly like classList.toggle does on real elements.
function _hfsZoneApply(card, toggles, clear, skip) {
  if (!card.__rxZones) card.__rxZones = new Map();
  const state = card.__rxZones;
  if (clear && !(toggles || []).length) {
    state.clear();
  } else if (!skip) {
    for (const t of toggles || []) {
      let set = state.get(t.class);
      if (!set) state.set(t.class, (set = new Set()));
      for (const id of t.elements || []) {
        if (clear) set.delete(id);
        else if (set.has(id)) set.delete(id);
        else set.add(id);
      }
      if (!set.size) state.delete(t.class);
    }
  }
  _hfsPaint(card);
}
window.__ramsesHfsZoneApply = _hfsZoneApply;

// --- editor panel: icons only (the editor owns its own gestures) ----------

function _hfsPanelEditor(panel) {
  return (
    panel.shadowRoot &&
    panel.shadowRoot.querySelector('floorplan-studio-editor')
  );
}

function _hfsDecoratePanel(panel) {
  const ed = _hfsPanelEditor(panel);
  const root = ed && ed.shadowRoot;
  if (!root) return;
  _hfsAnimStyle(root);
  const floorKey = ed.floor;
  const floor =
    floorKey && _hfsLayout && _hfsLayout.floors
      ? _hfsLayout.floors[floorKey]
      : null;
  for (const svg of root.querySelectorAll('svg')) {
    _hfsDecorate(svg, floor);
  }
}

function _hfsAttachPanel(panel) {
  if (panel.__rxHfsPanel) return;
  panel.__rxHfsPanel = true;
  _hfsPanels.add(panel);
  const tryAttach = () => {
    const ed = _hfsPanelEditor(panel);
    if (!ed || !ed.shadowRoot) return false;
    // icon swaps are attribute writes — no childList feedback loop
    const mo = new MutationObserver(() => {
      if (panel.__rxIconsQueued) return;
      panel.__rxIconsQueued = true;
      Promise.resolve().then(() => {
        panel.__rxIconsQueued = false;
        _hfsDecoratePanel(panel);
      });
    });
    mo.observe(ed.shadowRoot, { childList: true, subtree: true });
    _hfsDecoratePanel(panel);
    return true;
  };
  if (!tryAttach()) {
    // the editor element appears after the panel's first load
    const wait = new MutationObserver(() => {
      if (tryAttach()) wait.disconnect();
    });
    wait.observe(panel.shadowRoot || panel, {
      childList: true,
      subtree: true,
    });
  }
}

// --- zones-tool bridge -------------------------------------------------
// The actions card's zone editor mirrors the plan editor's selection;
// for hfs that state lives on the editor element (`st.sel`, `floor`) —
// private but stable to poll. The card resolves indices itself (it has
// its own entity→device map); we only hand it the live handles.
function _hfsEditorEl() {
  for (const panel of _hfsPanels) {
    const ed = _hfsPanelEditor(panel);
    if (ed) return ed;
  }
  let found = null;
  const walk = (root) => {
    for (const el of root.querySelectorAll('*')) {
      if (found) return;
      if (el.tagName === 'FLOORPLAN-STUDIO-EDITOR') {
        found = el;
        return;
      }
      if (el.shadowRoot) walk(el.shadowRoot);
    }
  };
  walk(document);
  return found;
}

window.__ramsesHfsInfo = () => ({
  layout: _hfsLayout,
  editor: _hfsEditorEl(),
});

// --- save → export bridge --------------------------------------------------
// hfs's editor emits `layout-changed` after every edit and its store
// fires `floorplan_studio_updated` on every landed write (user Save,
// our seed, syncs — see editors/hfs.py async_store). Debounced:
// edits autosave via ed.save(), landed writes regenerate the
// floorplan cards — the editor stays SSOT without a button press.

let _autoSaveTimer = 0;
let _exportTimer = 0;

function _hfsAutoSave() {
  const info = window.__ramsesHfsInfo();
  const ed = info && info.editor;
  if (!ed || !ed.st || !ed.st.dirty) return;
  // mid-placement (asideMode 'place') or a room being placed — let
  // the user finish the gesture before the save snapshot runs
  if (ed.asideMode === 'place' || ed.placeRoom) return;
  try {
    ed.save();
  } catch (e) {
    // the editor surfaces validation errors itself
    console.debug('ramses-hfs: autosave skipped', e);
  }
}

async function _hfsAutoExport() {
  const hass = _hfsHass();
  if (!hass || !hass.callService) return;
  // collapse bursts and skip when an explicit export just ran (the
  // actions card stamps window.__ramsesHfsLastExport)
  if (Date.now() - (window.__ramsesHfsLastExport || 0) < 5000) return;
  window.__ramsesHfsLastExport = Date.now();
  try {
    await hass.callService('ramses_extras', 'floorplan_export', {
      apply: true,
    });
    console.info('ramses-hfs: plan saved — floorplan cards regenerated');
  } catch (e) {
    console.warn('ramses-hfs: auto-export failed', e);
  }
}

let _bridged = false;
function _hfsBridge() {
  if (_bridged) return;
  _bridged = true;
  // composed+bubbling events from the hfs editor element; gate on
  // composedPath so a studio (tinkersoder) editor can't reach us
  document.addEventListener('layout-changed', (ev) => {
    const ed = window.__ramsesHfsInfo().editor;
    if (!ed || !ev.composedPath().includes(ed)) return;
    clearTimeout(_autoSaveTimer);
    _autoSaveTimer = setTimeout(_hfsAutoSave, 2500);
  });
  // "focus lost" — leaving the tab flushes pending edits
  document.addEventListener('visibilitychange', () => {
    if (document.hidden) {
      clearTimeout(_autoSaveTimer);
      _hfsAutoSave();
    }
  });
  window.addEventListener('blur', () => {
    clearTimeout(_autoSaveTimer);
    _hfsAutoSave();
  });
}

// --- boot: discovery + state -----------------------------------------------

function _hfsScan() {
  for (const card of _hfsCards()) _hfsAttach(card);
  const walk = (root) => {
    for (const el of root.querySelectorAll('*')) {
      if (el.tagName === HFS_PANEL_TAG) _hfsAttachPanel(el);
      if (el.shadowRoot) walk(el.shadowRoot);
    }
  };
  walk(document);
}

function _hfsStart() {
  if (_started) return;
  const hass = _hfsHass();
  if (!hass) return;
  _started = true;
  _hfsLoadState().then(_hfsScan);
  if (hass.connection && hass.connection.subscribeEvents) {
    // their store fires this on every landed save — maps follow the
    // edit and generated cards regenerate, debounced past bursts
    hass.connection.subscribeEvents(() => {
      _hfsLoadLayout();
      clearTimeout(_exportTimer);
      _exportTimer = setTimeout(_hfsAutoExport, 1200);
    }, 'floorplan_studio_updated');
    // spin duration follows the fan-speed entities live — their card
    // only patches attributes on those updates, which would otherwise
    // leave a stale animation (and the observer re-decorates anyway)
    hass.connection.subscribeEvents((e) => {
      const eid = e && e.data && e.data.entity_id;
      if (eid && _stateEnts.has(eid)) _hfsRepaintAll();
    }, 'state_changed');
  }
  // late-added cards: rescan on navigation plus a slow fallback — a
  // deep shadow-DOM walk is not cheap on a busy dashboard
  window.addEventListener('location-changed', _hfsScan);
  const timer = setInterval(() => {
    _hfsScan();
    if (!_hfsHass()) clearInterval(timer);
  }, 10000);
}

_hfsBridge();
_hfsStart();
if (!_started) {
  const timer = setInterval(() => {
    _hfsStart();
    if (_started) clearInterval(timer);
  }, 1500);
}
