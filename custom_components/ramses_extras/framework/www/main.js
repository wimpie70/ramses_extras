/* global MutationObserver */

import * as logger from './logger.js';

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
];

const loaded = new Set();

async function loadCardModule(cardDef) {
  if (loaded.has(cardDef.tag)) {
    return;
  }

  loaded.add(cardDef.tag);
  logger.debug('ramses_extras: loading card module for', cardDef.tag, cardDef.modulePath);

  try {
    await import(cardDef.modulePath);
    logger.debug('ramses_extras: loaded card module for', cardDef.tag);
  } catch (err) {
    logger.warn('ramses_extras: failed to load card module', cardDef, err);
  }
}

function scanAndLoad() {
  for (const cardDef of CARD_MODULES) {
    if (loaded.has(cardDef.tag)) {
      continue;
    }

    if (document.querySelector(cardDef.tag)) {
      loadCardModule(cardDef);
    }
  }
}

(function init() {
  if (typeof document === 'undefined') {
    return;
  }

  window.ramsesExtras = window.ramsesExtras || {};
  const assetBase = detectAssetBase();
  if (assetBase) {
    window.ramsesExtras.assetBase = assetBase;
  }

  logger.debug('ramses_extras: main.js bootstrap init');

  // Load feature configuration (version, debug settings, etc.)
  if (assetBase) {
    const featuresScript = document.createElement('script');
    featuresScript.src = `${assetBase}/helpers/ramses-extras-features.js`;
    featuresScript.onload = () => {
      logger.debug('ramses_extras: features loaded');
    };
    featuresScript.onerror = () => {
      logger.warn('ramses_extras: failed to load features file');
    };
    document.head.appendChild(featuresScript);
  }

  Promise.all(CARD_MODULES.map(loadCardModule)).catch((err) => {
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
