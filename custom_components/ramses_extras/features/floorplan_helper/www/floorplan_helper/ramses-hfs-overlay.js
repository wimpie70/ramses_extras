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
/* global MutationObserver */

'use strict';

const DOMAIN = 'ramses_extras';
const HFS_TAG = 'HFS-FLOORPLAN-CARD';
const TAP_SLOP_PX = 6; // their own pan-vs-tap threshold (actions.ts)
const OVERLAY_ID = 'ramses-hfs-overlay';

let _hfsLayout = null; // floorplan_studio/load payload
let _entityDevice = {}; // entity_id -> topology device record
let _deviceById = {}; // device_id -> topology device record
let _zones = {}; // device_zones option {device_id: {areas, devices, color}}
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
  } catch {
    _zones = {};
  }
  await _hfsLoadLayout();
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
          (n.closest && n.closest(`#${OVERLAY_ID}`)));
      if (r.target && r.target.nodeType === 1 && own(r.target)) continue;
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
  mo.observe(root, { childList: true, subtree: true });
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

function _hfsPaint(card) {
  if (!card.shadowRoot || !card.__rxZones) return;
  const svg = card.shadowRoot.querySelector('svg');
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

  const floor = _hfsFloor(card);
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

function _hfsRepaintAll() {
  for (const card of _hfsCards()) _hfsPaint(card);
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

// --- boot: discovery + state -----------------------------------------------

function _hfsScan() {
  for (const card of _hfsCards()) _hfsAttach(card);
}

function _hfsStart() {
  if (_started) return;
  const hass = _hfsHass();
  if (!hass) return;
  _started = true;
  _hfsLoadState().then(_hfsScan);
  if (hass.connection && hass.connection.subscribeEvents) {
    // their store fires this on every save — maps follow the edit
    hass.connection.subscribeEvents(
      () => _hfsLoadLayout(),
      'floorplan_studio_updated'
    );
  }
  // late-added cards: rescan on navigation plus a slow fallback — a
  // deep shadow-DOM walk is not cheap on a busy dashboard
  window.addEventListener('location-changed', _hfsScan);
  const timer = setInterval(() => {
    _hfsScan();
    if (!_hfsHass()) clearInterval(timer);
  }, 10000);
}

_hfsStart();
if (!_started) {
  const timer = setInterval(() => {
    _hfsStart();
    if (_started) clearInterval(timer);
  }, 1500);
}
