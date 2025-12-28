/* eslint-disable no-console */
/* global MutationObserver */

const isDebugEnabled = () => window.ramsesExtras?.debug === true;
const debugLog = (...args) => {
  if (isDebugEnabled()) {
    console.log(...args);
  }
};

function detectAssetBase() {
  if (typeof document === 'undefined') {
    return null;
  }

  const fromScript = (src) => {
    if (!src) {
      return null;
    }
    const marker = '/helpers/main.js';
    const idx = src.indexOf(marker);
    if (idx === -1) {
      return null;
    }
    return src.slice(0, idx);
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
];

const loaded = new Set();

async function loadCardModule(cardDef) {
  if (loaded.has(cardDef.tag)) {
    return;
  }

  loaded.add(cardDef.tag);
  debugLog('ramses_extras: loading card module for', cardDef.tag, cardDef.modulePath);

  try {
    await import(cardDef.modulePath);
    debugLog('ramses_extras: loaded card module for', cardDef.tag);
  } catch (err) {
    console.warn('ramses_extras: failed to load card module', cardDef, err);
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

  debugLog('ramses_extras: main.js bootstrap init');

  Promise.all(CARD_MODULES.map(loadCardModule)).catch((err) => {
    console.warn('ramses_extras: failed to preload card modules', err);
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
