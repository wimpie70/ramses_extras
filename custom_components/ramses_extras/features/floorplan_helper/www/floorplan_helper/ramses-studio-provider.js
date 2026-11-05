// Ramses Extras → Floorplan Studio provider.
//
// Registers a device source (Ramses Extras get_topology, HA-registry
// fallback, offline paste) through the public floorplanStudio plugin API
// only — no editor internals. Deployed with floorplan_helper's www assets
// and registered as a Lovelace module resource by the integration; the
// script itself retries until window.floorplanStudio exists.
//
// Zones: get_topology folds evohome zone sub-devices (<ctl>_<idx>, <ctl>_HW)
// into their physical sensor/actuator device — that is the model this
// provider mirrors, so no separate ZON markers are emitted. Zone topology
// (heat_zones) is used server-side by floorplan_seed_studio.

const TOPOLOGY_WS = 'ramses_extras/floorplan_helper/get_topology';
const PLUGIN_ID = 'ramses';
const DBG = '[ramses]';
const dlog = (...a) => console.debug(DBG, ...a);
const dwarn = (...a) => console.warn(DBG, ...a);

// ---------------------------------------------------------------------------
// Device classes, icons, groups
// ---------------------------------------------------------------------------

/** RAMSES id, optionally with zone index ("_02") or DHW ("_HW") suffix. */
const DEVICE_ID_FULL = /^(\d{2}):(\d{6})(?:_([0-9A-Fa-f]{2}|HW))?$/;
const DEVICE_ID_IN_TEXT = /(?<!\w|\d:)(\d{2}:\d{6})(?:_([0-9A-Fa-f]{2}|HW))?(?!\w|:\d)/g;

/** Fixed-meaning id prefixes (ramses_rf DEVICE_ID_REGEX). HVAC prefixes are ambiguous. */
const PREFIX_CLASS = {
  '01': 'CTL', '02': 'UFC', '03': 'THM', '04': 'TRV', '07': 'DHW',
  '10': 'OTB', '12': 'THM', '13': 'BDR', '18': 'HGI', '22': 'THM',
  '23': 'CTL', '34': 'THM',
};

const KNOWN_CLASSES = new Set([
  'CTL', 'UFC', 'THM', 'TRV', 'DHW', 'OTB', 'BDR', 'HGI', 'ZON', 'SEN', 'PRG', 'RFG',
  'FAN', 'HVAC', 'REM', 'RND', 'DIS', 'CO2', 'HUM', 'SWI',
]);

const HEAT_CLASSES = new Set(['CTL', 'UFC', 'THM', 'TRV', 'DHW', 'OTB', 'BDR', 'ZON', 'SEN', 'PRG']);
const HVAC_CLASSES = new Set(['FAN', 'HVAC', 'REM', 'RND', 'DIS', 'CO2', 'HUM', 'SWI', 'RFG']);

/** Class → MDI icon. Mirrors floorplan_helper's icon map. */
const CLASS_ICON = {
  FAN: 'fan', HVAC: 'fan', TRV: 'radiator', CTL: 'thermostat', ZON: 'home-thermometer',
  OTB: 'water-boiler', DHW: 'water-boiler', REM: 'remote', RND: 'remote', SWI: 'remote',
  DIS: 'tablet', HGI: 'router-wireless', RFG: 'router-wireless', BDR: 'pipe-valve',
  UFC: 'pipe-valve', CO2: 'molecule-co2', HUM: 'water-percent', THM: 'thermometer',
  SEN: 'thermometer', PRG: 'thermostat',
};

const CLASS_LABEL = {
  CTL: 'Controller', ZON: 'Heating zone', TRV: 'Radiator valve', THM: 'Thermostat / sensor',
  SEN: 'Sensor', UFC: 'UFH controller', DHW: 'Hot water', OTB: 'OpenTherm bridge',
  BDR: 'Relay', HGI: 'Gateway', RFG: 'Gateway', FAN: 'Ventilation unit', HVAC: 'HVAC device',
  REM: 'Remote', RND: 'Remote', SWI: 'Switch', DIS: 'Display', CO2: 'CO₂ sensor',
  HUM: 'Humidity sensor', PRG: 'Programmer',
};

const GROUP_COLOR = { heat: '#f97316', hvac: '#38bdf8', hgi: '#a78bfa', orphan: '#ffc107' };

/** Fill the neutral presentation fields the editor consumes (ImportDevice). */
function present(d) {
  d.icon = CLASS_ICON[d.device_class] ?? 'help-circle';
  d.color = GROUP_COLOR[d.group] ?? GROUP_COLOR.orphan;
  d.kind = CLASS_LABEL[d.device_class] ?? d.device_class;
  d.suggested = d.group !== 'hgi';
  return d;
}

function groupForClass(cls) {
  if (cls === 'HGI') return 'hgi';
  if (HEAT_CLASSES.has(cls)) return 'heat';
  if (HVAC_CLASSES.has(cls)) return 'hvac';
  return 'orphan';
}

/** Best class from the id alone ("" when the prefix is ambiguous). */
function classFromId(deviceId) {
  const m = DEVICE_ID_FULL.exec(deviceId);
  if (!m) return '';
  if (m[3]) return m[3].toUpperCase() === 'HW' ? 'DHW' : 'ZON';
  return PREFIX_CLASS[m[1]] ?? '';
}

/** Ambiguous HVAC prefixes (29/30/32/37…): guess from what entities the device exposes. */
function classFromEntities(entities) {
  const domains = new Set(entities.map((e) => e.domain));
  const roles = new Set(entities.map((e) => e.role));
  if (domains.has('fan') || domains.has('climate') || roles.has('fan_rate')) return 'FAN';
  if (domains.has('remote')) return 'REM';
  if (roles.has('co2')) return 'CO2';
  if (roles.has('humidity')) return 'HUM';
  if (roles.has('temperature')) return 'THM';
  return '';
}

/**
 * Normalise whatever class hint we got (ramses_rf _SLUG, ramses_cc device
 * model, "unknown") into one of KNOWN_CLASSES. Zone/DHW id suffixes win —
 * generic hints like "SEN" mislabel TRVs and zone sub-devices.
 */
function normaliseClass(hint, deviceId, entities) {
  const fromId = classFromId(deviceId);
  if (fromId === 'ZON' || fromId === 'DHW' || fromId === 'HGI') return fromId;
  const token = String(hint ?? '').trim().split(/[\s(]/)[0].toUpperCase();
  if (KNOWN_CLASSES.has(token) && token !== 'SEN') return token;
  if (/^controller/i.test(String(hint ?? ''))) return 'CTL';
  if (/^ufh/i.test(String(hint ?? ''))) return 'UFC';
  return fromId || classFromEntities(entities) || 'HVAC';
}

// ---------------------------------------------------------------------------
// Entities: roles + primary selection
// ---------------------------------------------------------------------------

/** Ordered like floorplan_helper's ENTITY_ROLE_PATTERNS (first match wins). */
const ROLE_PATTERNS = [
  ['status', ['_status']],
  ['heat_demand', ['heat_demand']],
  ['window_open', ['window_open']],
  ['battery', ['battery']],
  ['fan_rate', ['fan_rate', 'fan_speed', 'fan_mode']],
  ['co2', ['co2_level', 'co2_control', 'co2']],
  ['temperature', ['temperature', 'indoor_temp', 'outdoor_temp', '_temp']],
  ['humidity', ['humidity']],
  ['setpoint', ['setpoint']],
];

function classifyEntity(entityId) {
  const name = (entityId.split('.')[1] ?? entityId).toLowerCase();
  for (const [role, patterns] of ROLE_PATTERNS)
    if (patterns.some((p) => name.includes(p))) return role;
  return 'other';
}

const PRIMARY_DOMAIN_ORDER = ['climate', 'water_heater', 'remote', 'fan', 'switch'];
const PRIMARY_ROLE_ORDER = ['temperature', 'co2', 'humidity', 'heat_demand', 'fan_rate'];

/** Same preference as floorplan_helper, plus a measurement fallback. */
function selectPrimaryEntity(entities) {
  for (const d of PRIMARY_DOMAIN_ORDER) {
    const hit = entities.find((e) => e.domain === d);
    if (hit) return hit.entity_id;
  }
  for (const r of PRIMARY_ROLE_ORDER) {
    const hit = entities.find((e) => e.role === r && e.domain === 'sensor');
    if (hit) return hit.entity_id;
  }
  const nonBattery = entities.find((e) => e.role !== 'battery');
  return (nonBattery ?? entities[0])?.entity_id ?? null;
}

const toEntity = (entity_id, extra = {}) => ({
  entity_id,
  domain: entity_id.split('.')[0],
  role: classifyEntity(entity_id),
  ...extra,
});

const str = (v) => (typeof v === 'string' && v ? v : null);

// ---------------------------------------------------------------------------
// Marker gestures — mirrors services' studio_actions_for_device: a zone
// parent taps to toggle its member markers' ring class, hold opens
// more-info, double opens the device popup (hvac_fan_card for FANs).
// serviceData is YAML — the same payloads the generated rules emit.
// ---------------------------------------------------------------------------

const slugify = (v) =>
  String(v ?? '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/_+/g, '_')
    .replace(/^_|_$/g, '');

/** evohome zones → {parent_device_id: {members}} — parent = sensor else 1st actuator. */
function zonesFromHeatZones(heatZones) {
  const zones = {};
  for (const z of heatZones ?? []) {
    const actuators = (z.actuators ?? []).map(String);
    const parent = str(z.sensor) ?? actuators[0];
    if (!parent || zones[parent]) continue;
    zones[parent] = { members: actuators.filter((a) => a !== parent), name: z.name ?? '' };
  }
  return zones;
}

const deviceViewAction = (d) => ({
  kind: 'call-service',
  service: 'ramses_extras.floorplan_device_view',
  serviceData: `device_id: ${d.device_id}\nentity: ${d.primary_entity ?? ''}`,
});

function actionsFor(d, zones, primaryById) {
  const dbl = deviceViewAction(d);
  if (zones[d.device_id]) {
    const elements = zones[d.device_id].members.map((m) => primaryById.get(m)).filter(Boolean);
    return {
      tap: {
        kind: 'call-service',
        service: 'ramses_extras.floorplan_zone_toggle',
        serviceData: `toggles:\n  - class: rx-zone-${slugify(d.device_id)}_dev\n    elements:${
          elements.length ? `\n      - ${elements.join('\n      - ')}` : ' []'
        }`,
      },
      hold: { kind: 'more-info' },
      double: dbl,
    };
  }
  // FANs are the flagship gesture: double-tap opens the hvac_fan_card popup.
  if (d.device_class === 'FAN' || d.device_class === 'HVAC') return { double: dbl };
  return undefined;
}

// ---------------------------------------------------------------------------
// Source 1: Ramses Extras get_topology result
// ---------------------------------------------------------------------------

function isExtrasTopology(v) {
  return !!v && typeof v === 'object' && Array.isArray(v.devices);
}

/** Normalise `ramses_extras/floorplan_helper/get_topology` output. */
function normaliseExtrasTopology(raw) {
  if (!isExtrasTopology(raw)) throw new Error('Not a Ramses Extras topology (no "devices" list)');
  const areas = raw.areas && typeof raw.areas === 'object' ? raw.areas : {};
  const floors = raw.floors && typeof raw.floors === 'object' ? raw.floors : {};
  const devices = [];
  for (const d of raw.devices) {
    const device_id = str(d?.device_id);
    if (!device_id) continue;
    const entities = (Array.isArray(d.entities) ? d.entities : [])
      .map((e) => (typeof e === 'string' ? { entity_id: e } : e))
      .filter((e) => str(e.entity_id))
      .map((e) =>
        toEntity(e.entity_id, {
          role: str(e.role) ?? classifyEntity(e.entity_id),
          area_id: str(e.area_id),
          name: str(e.name) ?? undefined,
        }),
      );
    const device_class = normaliseClass(str(d.device_class), device_id, entities);
    const area_id = str(d.area_id) ?? entities.find((e) => e.area_id)?.area_id ?? null;
    const primary = str(d.primary_entity);
    devices.push(
      present({
        device_id,
        device_class,
        // Extras' group is authoritative for heat/hvac/hgi, but it reports
        // non-rf children as "orphan" — derive those from the class.
        group: str(d.group) && d.group !== 'orphan' ? d.group : groupForClass(device_class),
        parent: str(d.parent),
        area_id,
        area_name: str(d.area_name) ?? (area_id ? areas[area_id]?.name ?? null : null),
        display_name: str(d.display_name) ?? `${device_class} ${device_id}`,
        primary_entity:
          primary && entities.some((e) => e.entity_id === primary)
            ? primary
            : selectPrimaryEntity(entities),
        entities,
      }),
    );
  }
  const zones = zonesFromHeatZones(raw.heat_zones);
  const primaryById = new Map(devices.map((d) => [d.device_id, d.primary_entity]));
  for (const d of devices) {
    const actions = actionsFor(d, zones, primaryById);
    if (actions) d.actions = actions;
  }
  return { source: 'ramses_extras', sourceLabel: 'Ramses Extras floorplan helper', devices, areas, floors };
}

// ---------------------------------------------------------------------------
// Source 2: plain ramses_cc via the HA registries (no Ramses Extras topology)
// ---------------------------------------------------------------------------

const RAMSES_PLATFORMS = new Set(['ramses_cc', 'ramses_extras']);

function ramsesIdOf(dev) {
  for (const [platform, ident] of dev.identifiers ?? []) {
    if (RAMSES_PLATFORMS.has(platform) && DEVICE_ID_FULL.test(String(ident))) return String(ident);
  }
  return null;
}

function topologyFromRegistries(devices, entities, areaList, floorList) {
  const areas = {};
  for (const a of areaList) areas[a.area_id] = { name: a.name, floor_id: a.floor_id ?? null };
  const floors = {};
  for (const f of floorList) floors[f.floor_id] = { name: f.name, level: f.level ?? null };

  const haToRamses = new Map();
  for (const d of devices) {
    const rid = ramsesIdOf(d);
    if (rid && !d.disabled_by) haToRamses.set(d.id, rid);
  }

  const byDevice = new Map();
  for (const e of entities) {
    if (e.disabled_by || !e.device_id || !haToRamses.has(e.device_id)) continue;
    const list = byDevice.get(e.device_id) ?? [];
    list.push(toEntity(e.entity_id, { area_id: e.area_id ?? null, name: e.name ?? e.original_name ?? undefined }));
    byDevice.set(e.device_id, list);
  }

  const out = [];
  for (const d of devices) {
    const device_id = haToRamses.get(d.id);
    if (!device_id) continue;
    const ents = byDevice.get(d.id) ?? [];
    const device_class = normaliseClass(d.model, device_id, ents);
    const area_id = ents.find((e) => e.area_id)?.area_id ?? d.area_id ?? null;
    // HA ≥2026.9 child devices carry parent_device_id instead of via_device_id.
    const parentHa = d.via_device_id ?? d.parent_device_id;
    out.push(
      present({
        device_id,
        device_class,
        group: groupForClass(device_class),
        parent: parentHa ? haToRamses.get(parentHa) ?? null : null,
        area_id,
        area_name: area_id ? areas[area_id]?.name ?? null : null,
        display_name: d.name_by_user || d.name || `${device_class} ${device_id}`,
        primary_entity: selectPrimaryEntity(ents),
        entities: ents,
      }),
    );
  }
  out.sort((a, b) => a.device_id.localeCompare(b.device_id));
  // No heat_zones here (extras topology only) — still give FANs the
  // double-tap device popup.
  for (const d of out) {
    if (d.device_class === 'FAN' || d.device_class === 'HVAC')
      d.actions = { double: deviceViewAction(d) };
  }
  return { source: 'ramses_cc', sourceLabel: 'ramses_cc registries', devices: out, areas, floors };
}

// ---------------------------------------------------------------------------
// Source 3: bare device ids (known_list, schema…) matched to HA entities
// ---------------------------------------------------------------------------

/** Every distinct RAMSES device id in a blob of text (null address 63:* skipped). */
function extractDeviceIds(text) {
  const seen = new Set();
  for (const m of text.matchAll(DEVICE_ID_IN_TEXT)) {
    if (m[1].startsWith('63:')) continue;
    seen.add(m[2] ? `${m[1]}_${m[2].toUpperCase() === 'HW' ? 'HW' : m[2]}` : m[1]);
  }
  return [...seen];
}

const idSlug = (id) => id.replace(':', '_').toLowerCase();

/**
 * Attach HA entities to ids by the id slug inside the entity_id
 * (`climate.01_123456_02`, `sensor.04_123456_temperature`…). An entity goes
 * to the longest matching id, so zone entities don't also land on the CTL.
 */
function topologyFromIds(ids, haEntities) {
  const slugs = ids.map((id) => ({ id, slug: idSlug(id) })).sort((a, b) => b.slug.length - a.slug.length);
  const byId = new Map(ids.map((id) => [id, []]));
  for (const e of haEntities) {
    const obj = (e.entity_id.split('.')[1] ?? '').toLowerCase();
    const hit = slugs.find(({ slug }) => {
      const i = obj.indexOf(slug);
      if (i < 0) return false;
      const before = i === 0 || obj[i - 1] === '_';
      const after = obj.length === i + slug.length || obj[i + slug.length] === '_';
      return before && after;
    });
    if (hit) byId.get(hit.id).push(toEntity(e.entity_id, { area_id: e.area_id ?? null, name: e.friendly_name }));
  }
  const devices = ids.map((device_id) => {
    const ents = byId.get(device_id) ?? [];
    const device_class = normaliseClass(null, device_id, ents);
    const area_id = ents.find((e) => e.area_id)?.area_id ?? null;
    return present({
      device_id,
      device_class,
      group: groupForClass(device_class),
      area_id,
      area_name: null,
      display_name: `${CLASS_LABEL[device_class] ?? device_class} ${device_id}`,
      primary_entity: selectPrimaryEntity(ents),
      entities: ents,
    });
  });
  return { source: 'device_ids', sourceLabel: 'device ids in text', devices, areas: {}, floors: {} };
}

// ---------------------------------------------------------------------------
// Live fetch: get_topology first, HA registries as fallback
// ---------------------------------------------------------------------------

function errText(e) {
  if (!e) return 'unknown error';
  if (typeof e === 'string') return e;
  return [e.code, e.message].filter(Boolean).join(': ') || String(e);
}

async function fetchTopology(ws) {
  let extrasError = '';
  try {
    const raw = await ws({ type: TOPOLOGY_WS });
    const topology = normaliseExtrasTopology(raw?.result ?? raw);
    if (topology.devices.length) return { topology };
    extrasError = 'Ramses Extras returned no devices';
  } catch (e) {
    extrasError = errText(e);
  }

  const [devices, entities, areas, floors] = await Promise.all([
    ws({ type: 'config/device_registry/list' }),
    ws({ type: 'config/entity_registry/list' }),
    ws({ type: 'config/area_registry/list' }).catch(() => []),
    ws({ type: 'config/floor_registry/list' }).catch(() => []),
  ]);
  const topology = topologyFromRegistries(devices, entities, areas, floors);
  if (!topology.devices.length)
    throw new Error('No RAMSES devices found — is ramses_cc set up on this Home Assistant?');
  return {
    topology,
    note: /unknown.command|unknown_command|not found/i.test(extrasError)
      ? 'Ramses Extras floorplan helper not found — read devices straight from the ramses_cc registries.'
      : `Ramses Extras topology unavailable (${extrasError}) — read devices straight from the ramses_cc registries.`,
  };
}

// ---------------------------------------------------------------------------
// Paste / file input sniffing
// ---------------------------------------------------------------------------

const isProject = (v) => !!v && typeof v === 'object' && Array.isArray(v.floors);

/** Peel the wrappers HA puts around results (WS `result`, service `response`). */
function unwrap(v) {
  let cur = v;
  for (let i = 0; i < 4 && cur && typeof cur === 'object' && !Array.isArray(cur); i++) {
    if (cur.result && typeof cur.result === 'object') cur = cur.result;
    else if (cur.response && typeof cur.response === 'object') cur = cur.response;
    else if (cur.service_response && typeof cur.service_response === 'object') cur = cur.service_response;
    else break;
  }
  return cur;
}

/**
 * Sniff pasted/loaded text. Accepts JSON (or YAML when a global yaml lib is
 * present): a get_topology result, a floorplan_seed_studio response /
 * studio project, or any text containing RAMSES device ids.
 */
function parseRamsesInput(text, ctx) {
  const src = text.trim();
  if (!src) return { kind: 'nomatch' };

  let data;
  try {
    data = JSON.parse(src);
  } catch {
    const y = window.jsyaml ?? window.jsYAML ?? window.YAML;
    try {
      data = y ? y.load(src) : undefined;
    } catch {
      data = undefined;
    }
  }
  data = unwrap(data);

  if (data && typeof data === 'object') {
    if (typeof data.project_json === 'string') {
      try {
        const p = JSON.parse(data.project_json);
        if (isProject(p)) return { kind: 'project', project: p };
      } catch {
        return { kind: 'error', error: 'project_json is not valid JSON.' };
      }
    }
    if (isProject(data.project_json)) return { kind: 'project', project: data.project_json };
    if (isProject(data)) return { kind: 'project', project: data };
    if (isExtrasTopology(data)) {
      try {
        return { kind: 'topology', topology: normaliseExtrasTopology(data) };
      } catch (e) {
        return { kind: 'error', error: e.message };
      }
    }
  }

  const ids = extractDeviceIds(src);
  if (ids.length) return { kind: 'topology', topology: topologyFromIds(ids, ctx.entities ?? []) };
  return { kind: 'nomatch' };
}

// ---------------------------------------------------------------------------
// Toolbar action: seed a pre-placed project via the floorplan_seed_studio
// service and merge the returned project fragment. Interim surface until the
// editor grows a dedicated capability slot for plan/room sources.
// ---------------------------------------------------------------------------

async function seedDevices(api) {
  const resp = await api.callWS({
    type: 'call_service',
    domain: 'ramses_extras',
    service: 'floorplan_seed_studio',
    service_data: {},
    return_response: true,
  });
  const json = resp?.response?.project_json ?? resp?.project_json ?? resp?.response ?? resp;
  const res = api.importProject(typeof json === 'string' ? json : JSON.stringify(json), { mode: 'merge' });
  return `Seed devices: merged ${res.markers} markers${res.rooms ? ` + ${res.rooms} rooms` : ''}`;
}

// ---------------------------------------------------------------------------
// Registration
// ---------------------------------------------------------------------------

function register(api) {
  api.registerPlugin({
    id: PLUGIN_ID,
    apiVersion: 1,
    provides: {
      deviceSources: [
        {
          id: 'ramses',
          title: 'RAMSES RF / Ramses Extras',
          description: 'evohome / RAMSES-II devices — zones, TRVs, thermostats, ventilation, CO₂ sensors, remotes',
          fetch: (ws) => fetchTopology(ws),
          parse: parseRamsesInput,
        },
      ],
      actions: [
        {
          id: 'ramses.seed-devices',
          label: 'Seed devices',
          icon: 'devices',
          location: 'toolbar',
          title: 'Run ramses_extras.floorplan_seed_studio and merge the result',
        },
      ],
      iconMap: { ...CLASS_ICON },
      // Fan runs → pulse (binary only; speed-proportional spin needs a
      // studio animation variant — flagged as a follow-up).
      stateRulePresets: [
        {
          entityRole: 'fan_rate',
          mode: 'threshold',
          compare: '>',
          value: 0,
          color: '#fbbf24',
          animation: 'pulse',
        },
      ],
      css: '/local/ramses_extras/features/floorplan_helper/ramses-floorplan.css',
    },
  });
  // Toolbar action clicks arrive as CustomEvents — we own ours.
  window.addEventListener(api.events.ACTION, (e) => {
    const d = e.detail ?? {};
    if (d.actionId !== 'ramses.seed-devices') return;
    seedDevices(api).then(
      (txt) => dlog(txt),
      (err) => dwarn('seed failed', err),
    );
  });
  dlog('floorplan-studio provider registered');
}

// Wait for the API (the editor card may load after this resource).
(function waitForApi(tries) {
  if (window.floorplanStudio) return register(window.floorplanStudio);
  if (tries > 0) setTimeout(() => waitForApi(tries - 1), 500);
})(40);
