/* eslint-disable no-console */

const _getRoot = () => {
  if (typeof window !== 'undefined') {
    return window;
  }
  return globalThis;
};

const _getFrontendLogLevel = () => {
  const root = _getRoot();
  const level = root?.ramsesExtras?.frontendLogLevel;
  if (typeof level === 'string' && level) {
    return level;
  }

  return root?.ramsesExtras?.debug === true ? 'debug' : 'info';
};

const _FRONTEND_LOG_LEVELS = {
  error: 0,
  warning: 1,
  info: 2,
  debug: 3,
};

const _shouldLog = (level) => {
  const current = _FRONTEND_LOG_LEVELS[_getFrontendLogLevel()] ?? _FRONTEND_LOG_LEVELS.info;
  const requested = _FRONTEND_LOG_LEVELS[level] ?? _FRONTEND_LOG_LEVELS.info;
  return requested <= current;
};

export const debug = (...args) => {
  if (typeof console === 'undefined') {
    return;
  }
  if (_shouldLog('debug')) {
    console.log(...args);
  }
};

export const info = (...args) => {
  if (typeof console === 'undefined') {
    return;
  }
  if (_shouldLog('info')) {
    (console.info || console.log).apply(console, args);
  }
};

export const warn = (...args) => {
  if (typeof console === 'undefined') {
    return;
  }
  if (_shouldLog('warning')) {
    (console.warn || console.log).apply(console, args);
  }
};

export const error = (...args) => {
  if (typeof console === 'undefined') {
    return;
  }
  if (_shouldLog('error')) {
    (console.error || console.log).apply(console, args);
  }
};

if (typeof window !== 'undefined') {
  window.ramsesExtrasLogger = window.ramsesExtrasLogger || {
    debug,
    info,
    warn,
    error,
  };
}
