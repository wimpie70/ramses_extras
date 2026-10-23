/* global MutationObserver */

import * as logger from './logger.js';

function getBootstrapVersion() {
  try {
    if (import.meta && import.meta.url) {
      const URLCtor =
        (typeof window !== 'undefined' && window.URL) ||
        (typeof globalThis !== 'undefined' && globalThis.URL) ||
        null;
      if (!URLCtor) {
        return null;
      }

      const url = new URLCtor(import.meta.url);
      const v = url.searchParams.get('v');
      return v || null;
    }
  } catch {
    // ignore
  }
  return null;
}

function detectAssetBase() {
  const fromPath = (path) => {
    if (!path) {
      return null;
    }
    const marker = '/helpers/main.js';
    const idx = path.indexOf(marker);
    if (idx === -1) {
      return null;
    }
    return path.slice(0, idx);
  };

  try {
    if (import.meta && import.meta.url) {
      const URLCtor =
        (typeof window !== 'undefined' && window.URL) ||
        (typeof globalThis !== 'undefined' && globalThis.URL) ||
        null;
      if (!URLCtor) {
        return null;
      }

      const url = new URLCtor(import.meta.url);
      const base = fromPath(url.pathname);
      if (base) {
        return base;
      }
    }
  } catch {
    // ignore
  }

  if (typeof document === 'undefined') {
    return null;
  }

  const fromScript = (src) => {
    return fromPath(src);
  };

  if (document.currentScript?.src) {
    const base = fromScript(document.currentScript.src);
    if (base) {
      return base;
    }
  }

  const scripts = document.getElementsByTagName('script');
  for (let i = scripts.length - 1; i >= 0; i--) {
    const base = fromScript(scripts[i]?.src);
    if (base) {
      return base;
    }
  }

  return null;
}

const CARD_MODULES = [
  {
    tag: 'hvac-fan-card',
    modulePath: '../features/hvac_fan_card/hvac-fan-card.js',
  },
  {
    tag: 'ramses-fan-map',
    modulePath: '../features/sensor_control/ramses-fan-map.js',
  },
  {
    tag: 'hello-world',
    modulePath: '../features/hello_world/hello-world.js',
  },
  {
    tag: 'ramses-traffic-analyser',
    modulePath: '../features/ramses_debugger/ramses-traffic-analyser.js',
  },
  {
    tag: 'ramses-log-explorer',
    modulePath: '../features/ramses_debugger/ramses-log-explorer.js',
  },
  {
    tag: 'ramses-packet-log-explorer',
    modulePath: '../features/ramses_debugger/ramses-packet-log-explorer.js',
  },
  {
    tag: 'ramses-humidity-diagnostics',
    modulePath: '../features/ramses_debugger/ramses-humidity-diagnostics.js',
  },
  {
    tag: 'device-simulator-card',
    modulePath: '../features/device_simulator/device-simulator-card.js',
  },
  {
    tag: 'device-status-card',
    modulePath: '../features/device_status_card/device-status-card.js',
  },
  {
    tag: 'ramses-floorplan-actions',
    modulePath: '../features/floorplan_helper/ramses-floorplan-actions.js',
  },
  {
    tag: 'ramses-editor-embed',
    modulePath: '../features/floorplan_helper/ramses-editor-embed.js',
  },
  {
    // not a card we render — the tags of the hosts we overlay: loads
    // whenever an hfs renderer card is on the page. `floorplan-studio-card`
    // is upstream's own tag (fresh installs); `hfs-floorplan-card` is our
    // renamed copy for hosts where the legacy studio card is installed too.
    tag: 'hfs-floorplan-card',
    extraTags: ['floorplan-studio-card'],
    modulePath: '../features/floorplan_helper/ramses-hfs-overlay.js',
  },
];

const loaded = new Set();

// The `?v=` key only changes when the backend recomputes its asset hash
// at startup, so between deploys a cached feature module can keep
// serving — and Firefox's hard refresh does not bypass the cache for
// dynamic import() calls the way it does for parser subresources. Stamp
// every import with the page-load time so a reload always revalidates;
// the module map still dedupes within the session.
const loadStamp = Date.now().toString(36);

async function loadCardModule(cardDef) {
  // dedupe on the module, not the tag — one module may serve several
  // element names (the overlay attaches to both hfs card tags)
  if (loaded.has(cardDef.modulePath)) {
    return;
  }

  loaded.add(cardDef.modulePath);
  logger.debug('ramses_extras: loading card module for', cardDef.tag, cardDef.modulePath);

  const version = window.ramsesExtras?.version || getBootstrapVersion();
  const qs = [
    version && `v=${encodeURIComponent(version)}`,
    `_=${loadStamp}`,
  ].filter(Boolean).join('&');
  const modulePath = `${cardDef.modulePath}?${qs}`;

  try {
    await import(modulePath);
    logger.debug('ramses_extras: loaded card module for', cardDef.tag);
  } catch (err) {
    logger.warn('ramses_extras: failed to load card module', cardDef, err);
  }
}

function scanAndLoad() {
  for (const cardDef of CARD_MODULES) {
    if (loaded.has(cardDef.modulePath)) {
      continue;
    }

    const tags = [cardDef.tag, ...(cardDef.extraTags || [])];
    if (tags.some((t) => document.querySelector(t))) {
      Promise.resolve(window.ramsesExtras?._featuresLoaded)
        .catch(() => {})
        .then(() => loadCardModule(cardDef));
    }
  }
}

(function init() {
  if (typeof document === 'undefined') {
    return;
  }

  window.ramsesExtras = window.ramsesExtras || {};
  const bootstrapVersion = getBootstrapVersion();
  const assetBase = detectAssetBase();
  if (assetBase) {
    window.ramsesExtras.assetBase = assetBase.startsWith('/www/')
      ? assetBase.replace('/www', '/local')
      : assetBase;
  }

  logger.debug('ramses_extras: main.js bootstrap init');

  // Load feature configuration (version, debug settings, etc.)
  if (!window.ramsesExtras._featuresLoaded) {
    window.ramsesExtras._featuresLoaded = Promise.resolve();
  }

  if (window.ramsesExtras.assetBase) {
    window.ramsesExtras._featuresLoaded = new Promise((resolve) => {
      const featuresScript = document.createElement('script');
      const versionSuffix = bootstrapVersion
        ? `?v=${encodeURIComponent(bootstrapVersion)}&_=${loadStamp}`
        : `?_=${loadStamp}`;
      featuresScript.src = `${window.ramsesExtras.assetBase}/helpers/ramses-extras-features.js${versionSuffix}`;
      featuresScript.onload = () => {
        logger.debug('ramses_extras: features loaded');
        resolve();
      };
      featuresScript.onerror = () => {
        logger.warn('ramses_extras: failed to load features file');
        resolve();
      };
      document.head.appendChild(featuresScript);
    });
  }

  window.ramsesExtras._featuresLoaded
    .then(() => Promise.all(CARD_MODULES.map(loadCardModule)))
    .catch((err) => {
      logger.warn('ramses_extras: failed to preload card modules', err);
    });

  const observer = new MutationObserver(() => {
    scanAndLoad();

    if (loaded.size >= CARD_MODULES.length) {
      observer.disconnect();
    }
  });

  observer.observe(document.body, {
    childList: true,
    subtree: true,
  });
})();
