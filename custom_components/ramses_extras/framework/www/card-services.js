/**
 * Card Services - WebSocket and Service Call Utilities
 *
 * This module provides utility functions for cards to interact with Home Assistant
 * via WebSocket commands and service calls.
 */

import * as logger from './logger.js';

/**
 * Stable stringify for WebSocket cache keys.
 *
 * This produces a deterministic string representation for plain objects so
 * multiple card instances can share the same cache key for equivalent requests.
 *
 * @param {any} value
 * @returns {string}
 */
function _stableStringify(value) {
  const t = typeof value;
  if (value == null || t === 'string' || t === 'number' || t === 'boolean') {
    return JSON.stringify(value);
  }
  if (Array.isArray(value)) {
    return `[${value.map((v) => _stableStringify(v)).join(',')}]`;
  }
  if (t === 'object') {
    const keys = Object.keys(value).sort();
    const parts = keys.map((k) => `${JSON.stringify(k)}:${_stableStringify(value[k])}`);
    return `{${parts.join(',')}}`;
  }
  return JSON.stringify(String(value));
}

function _getSharedWsState() {
  window.ramsesExtras = window.ramsesExtras || {};
  window.ramsesExtras._sharedWs = window.ramsesExtras._sharedWs || {
    inflight: new Map(),
    results: new Map(),
  };
  return window.ramsesExtras._sharedWs;
}

/**
 * Check for version mismatch between frontend and backend
 * @param {Object} result - WebSocket response
 */
function _checkVersionMismatch(result) {
  if (!result || typeof result !== 'object') {
    return;
  }

  const backendVersion = result._backend_version;
  if (!backendVersion) {
    return;
  }

  window.ramsesExtras = window.ramsesExtras || {};
  const frontendVersion = window.ramsesExtras.version;

  if (!frontendVersion) {
    return;
  }

  if (backendVersion !== frontendVersion) {
    if (!window.ramsesExtras._versionMismatch) {
      window.ramsesExtras._versionMismatch = {
        frontend: frontendVersion,
        backend: backendVersion,
        detected: Date.now(),
      };
      logger.warn(
        `Version mismatch detected! Frontend: ${frontendVersion}, Backend: ${backendVersion}. ` +
        'Please hard refresh your browser (Ctrl+Shift+R or Cmd+Shift+R).'
      );
    }
  }
}

/**
 * Send a WebSocket command to Home Assistant
 *
 * @param {Object} hass - Home Assistant instance
 * @param {Object} message - WebSocket message to send
 * @returns {Promise<Object>} Response from WebSocket command
 */
export async function callWebSocket(hass, message) {
  return new Promise((resolve, reject) => {
    // Block WebSocket calls if there's a version mismatch
    if (window.ramsesExtras?._versionMismatch) {
      const mismatch = window.ramsesExtras._versionMismatch;
      reject({
        version_mismatch: true,
        code: 'version_mismatch',
        message: `Version mismatch detected (Frontend: ${mismatch.frontend}, Backend: ${mismatch.backend}). Please hard refresh your browser.`,
        frontend: mismatch.frontend,
        backend: mismatch.backend,
      });
      return;
    }

    try {
      // Use Home Assistant's WebSocket API
      hass.callWS(message)
        .then((result) => {
          _checkVersionMismatch(result);
          resolve(result);
        })
        .catch((error) => {
          const code = error?.code || error?.error?.code;
          const messageText =
            error?.message ||
            error?.error?.message ||
            error?.toString?.() ||
            '';

          const isNotAvailable =
            code === 'unknown_command' ||
            code === 'not_found' ||
            messageText.includes('unknown_command') ||
            messageText.includes('Unknown command');

          if (isNotAvailable) {
            reject({
              not_available: true,
              code: code || 'unknown_command',
              message: messageText,
              original: error,
            });
            return;
          }

          logger.error('WebSocket message failed:', error);
          reject(error);
        });
    } catch (error) {
      logger.error('Error sending WebSocket message:', error);
      reject(error);
    }
  });
}

/**
 * Shared WebSocket helper with enhanced caching and in-flight de-dup.
 *
 * Rationale:
 * - Multiple Ramses Debugger cards can poll the same backend endpoint.
 * - For expensive operations (tail/search/stats), we want to avoid doing
 *   duplicate work in the frontend and backend.
 * - Excessive re-renders can cause WS spam; longer caching prevents this.
 *
 * Behavior:
 * - Computes a stable cache key from the message (or explicit `key`).
 * - If there is an in-flight request for that key, returns the same Promise.
 * - Optionally caches successful results for `cacheMs`.
 * - Default cache increased to 2000ms to reduce render-triggered spam.
 *
 * @param {Object} hass
 * @param {Object} message
 * @param {Object} options
 * @param {number} options.cacheMs - Cache duration in ms (default 2000)
 * @param {string|null} options.key - Custom cache key
 * @returns {Promise<any>}
 */
export async function callWebSocketShared(hass, message, { cacheMs = 2000, key = null } = {}) {
  const state = _getSharedWsState();
  const now = Date.now();

  const cacheKey = key || _stableStringify(message);

  const cached = state.results.get(cacheKey);
  if (cached && typeof cached === 'object') {
    const ts = Number(cached.ts || 0);
    if (cacheMs > 0 && (now - ts) < cacheMs) {
      return cached.value;
    }
  }

  const inflight = state.inflight.get(cacheKey);
  if (inflight && typeof inflight === 'object' && inflight.promise) {
    return inflight.promise;
  }

  const promise = callWebSocket(hass, message)
    .then((result) => {
      state.inflight.delete(cacheKey);
      if (cacheMs > 0) {
        state.results.set(cacheKey, { ts: now, value: result });

        // Limit cache size to prevent memory bloat
        while (state.results.size > 1024) {
          const oldestKey = state.results.keys().next().value;
          if (!oldestKey) {
            break;
          }
          state.results.delete(oldestKey);
        }
      }
      return result;
    })
    .catch((error) => {
      state.inflight.delete(cacheKey);
      throw error;
    });

  state.inflight.set(cacheKey, { ts: now, promise });
  return promise;
}

/**
 * Send a packet using the ramses_cc service (legacy function)
 *
 * @param {Object} hass - Home Assistant instance
 * @param {Object} data - Packet data
 * @returns {Promise<Object>} Response from service call
 */
export async function sendPacket(hass, data) {
  return new Promise((resolve, reject) => {
    try {
      hass.callService('ramses_cc', 'send_packet', data)
        .then((result) => {
          resolve(result);
        })
        .catch((error) => {
          logger.error('Service call failed:', error);
          reject(error);
        });
    } catch (error) {
      logger.error('Error calling service:', error);
      reject(error);
    }
  });
}

/**
 * Get bound REM device information
 *
 * @param {Object} hass - Home Assistant instance
 * @param {string} deviceId - Device ID
 * @returns {Promise<Object>} Bound REM device information
 */
export async function getBoundRemDevice(hass, deviceId) {
  return callWebSocket(hass, {
    type: 'ramses_extras/get_bound_rem',
    device_id: deviceId,
  });
}

/**
 * Call a Home Assistant service
 *
 * @param {Object} hass - Home Assistant instance
 * @param {string} domain - Service domain
 * @param {string} service - Service name
 * @param {Object} data - Service data
 * @returns {Promise<Object>} Service call result
 */
export async function callService(hass, domain, service, data) {
  return new Promise((resolve, reject) => {
    try {
      hass.callService(domain, service, data)
        .then((result) => {
          resolve(result);
        })
        .catch((error) => {
          logger.error('Service call failed:', error);
          reject(error);
        });
    } catch (error) {
      logger.error('Error calling service:', error);
      reject(error);
    }
  });
}

/**
 * Check if an entity exists
 *
 * @param {Object} hass - Home Assistant instance
 * @param {string} entityId - Entity ID to check
 * @returns {boolean} True if entity exists
 */
export function entityExists(hass, entityId) {
  if (!hass || !hass.states || !entityId) {
    return false;
  }
  const entity = hass.states[entityId];
  return entity !== undefined && entity !== null;
}

/**
 * Get entity state
 *
 * @param {Object} hass - Home Assistant instance
 * @param {string} entityId - Entity ID
 * @returns {Object|null} Entity state or null if not found
 */
export function getEntityState(hass, entityId) {
  if (!hass || !hass.states || !entityId) {
    return null;
  }
  return hass.states[entityId] || null;
}

/**
 * Set fan parameter (legacy function - now uses WebSocket)
 *
 * @param {Object} hass - Home Assistant instance
 * @param {string} deviceId - Device ID
 * @param {string} paramId - Parameter ID
 * @param {string} value - Parameter value
 * @returns {Promise<Object>} WebSocket response
 */
export async function setFanParameter(hass, deviceId, paramId, value) {
  return callService(hass, 'ramses_extras', 'set_fan_parameter', {
    device_id: deviceId,
    param_id: paramId,
    value: value,
  });
}

/**
 * Send a fan command (fire-and-forget)
 *
 * @param {Object} hass - Home Assistant instance
 * @param {string} deviceId - Device ID
 * @param {string} command - Command key (e.g. fan_high, fan_request31DA)
 * @returns {Promise<Object>} Service call result
 */
export async function sendFanCommand(hass, deviceId, command) {
  return callService(hass, 'ramses_extras', 'send_fan_command', {
    device_id: deviceId,
    command: command,
  });
}

/**
 * Refresh all fan parameters (2411 sequence)
 *
 * @param {Object} hass - Home Assistant instance
 * @param {string} deviceId - Device ID
 * @param {string} fromId - Optional source device ID
 * @returns {Promise<Object>} Service call result
 */
export async function refreshFanParameters(hass, deviceId, fromId = null) {
  const data = { device_id: deviceId };
  if (fromId) data.from_id = fromId;
  return callService(hass, 'ramses_extras', 'update_fan_params', data);
}

// Cache for available devices to prevent duplicate requests
let _devicesCache = null;
let _devicesCacheTimestamp = 0;
const CACHE_DURATION = 30000; // 30 seconds cache

/**
 * Clear all caches (useful for debugging or hard refresh)
 */
export function clearAllCaches() {
  logger.debug(' Clearing all card services caches');
  _devicesCache = null;
  _devicesCacheTimestamp = 0;

  try {
    const shared = _getSharedWsState();
    shared.inflight.clear();
    shared.results.clear();
  } catch {
    // ignore
  }
}

/**
 * Format a device ID for use in entity IDs (replace colons with underscores)
 * @param {string} deviceId - Device ID in colon format (e.g., "01:02:03")
 * @returns {string} Device ID in underscore format (e.g., "01_02_03")
 */
export function formatDeviceId(deviceId) {
  if (!deviceId) return 'unknown_device';
  return deviceId.toString().replace(/:/g, '_');
}

/**
 * Build a complete entity ID from device ID and suffix
 * @param {string} deviceId - Device ID
 * @param {string} domain - HA domain (e.g., "sensor", "switch")
 * @param {string} entitySuffix - Entity suffix (e.g., "hello_world_switch")
 * @returns {string} Complete entity ID
 */
export function buildEntityId(deviceId, domain, entitySuffix) {
  const formattedId = formatDeviceId(deviceId);
  return `${domain}.${entitySuffix}_${formattedId}`;
}

/**
 * Get available Ramses RF devices for card editors (with caching)
 *
 * @param {Object} hass - Home Assistant instance
 * @returns {Promise<Array>} List of available devices with device_id, device_type, model, and capabilities
 */
export async function getAvailableDevices(hass) {
  const now = Date.now();

  // Return cached data if still valid
  if (_devicesCache && (now - _devicesCacheTimestamp) < CACHE_DURATION) {
    logger.debug('📦 Returning cached devices list');
    return _devicesCache;
  }

  logger.debug('🔄 Fetching fresh devices list from WebSocket');
  const response = await callWebSocket(hass, {
    type: 'ramses_extras/get_available_devices',
  });

  // Cache the result
  _devicesCache = response.devices || [];
  _devicesCacheTimestamp = now;

  logger.debug(`✅ Cached ${_devicesCache.length} devices for ${CACHE_DURATION}ms`);
  return _devicesCache;
}

/**
 * Normalize a device descriptor for editor dropdowns
 * @param {Object} device - Raw device object from backend
 * @returns {Object} Normalized descriptor with id, label and slug metadata
 */
export function normalizeDeviceDescriptor(device = {}) {
  const id = device.device_id || device.id || '';
  const slugs = Array.isArray(device.slugs)
    ? device.slugs.map((slug) => slug?.toString()).filter(Boolean)
    : [];

  const slugLabel =
    device.slug_label ||
    (slugs.length ? slugs.join(', ') : '');

  const detail =
    slugLabel ||
    device.device_type ||
    device.model ||
    device.type ||
    '';

  const label = detail ? `${id} (${detail})` : id;

  return {
    id,
    slugs,
    slugLabel,
    detail,
    label,
    raw: device,
  };
}

/**
 * Filter devices by allowed slug codes
 * @param {Array} devices - Device list from backend
 * @param {Array} allowedSlugs - Slug codes to include (e.g. ['FAN'])
 * @returns {Array} Filtered devices
 */
export function filterDevicesBySlugs(devices = [], allowedSlugs = ['*']) {
  if (!Array.isArray(devices)) {
    return [];
  }

  if (!allowedSlugs || allowedSlugs.includes('*')) {
    return devices;
  }

  const normalizedAllowed = allowedSlugs.map((slug) => slug.toUpperCase());

  return devices.filter((device) => {
    const slugs = Array.isArray(device.slugs)
      ? device.slugs.map((slug) => slug?.toString().toUpperCase()).filter(Boolean)
      : [];

    if (slugs.length === 0 && device.slug_label) {
      slugs.push(...device.slug_label.split(',').map((slug) => slug.trim().toUpperCase()));
    }

    if (slugs.length === 0 && device.device_type) {
      slugs.push(device.device_type.toUpperCase());
    }

    return slugs.some((slug) => normalizedAllowed.includes(slug));
  });
}
