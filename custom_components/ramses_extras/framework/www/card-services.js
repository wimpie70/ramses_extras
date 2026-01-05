/* eslint-disable no-console */
/**
 * Card Services - WebSocket and Service Call Utilities
 *
 * This module provides utility functions for cards to interact with Home Assistant
 * via WebSocket commands and service calls.
 */

/**
 * Send a WebSocket command to Home Assistant
 *
 * @param {Object} hass - Home Assistant instance
 * @param {Object} message - WebSocket message to send
 * @returns {Promise<Object>} Response from WebSocket command
 */
export async function callWebSocket(hass, message) {
  return new Promise((resolve, reject) => {
    try {
      // Use Home Assistant's WebSocket API
      hass.callWS(message)
        .then((result) => {
          resolve(result);
        })
        .catch((error) => {
          console.error('WebSocket message failed:', error);
          reject(error);
        });
    } catch (error) {
      console.error('Error sending WebSocket message:', error);
      reject(error);
    }
  });
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
          console.error('Service call failed:', error);
          reject(error);
        });
    } catch (error) {
      console.error('Error calling service:', error);
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
          console.error('Service call failed:', error);
          reject(error);
        });
    } catch (error) {
      console.error('Error calling service:', error);
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
  return hass.states[entityId] !== undefined;
}

/**
 * Get entity state
 *
 * @param {Object} hass - Home Assistant instance
 * @param {string} entityId - Entity ID
 * @returns {Object|null} Entity state or null if not found
 */
export function getEntityState(hass, entityId) {
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
  console.log(' Clearing all card services caches');
  _devicesCache = null;
  _devicesCacheTimestamp = 0;
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
    console.log('📦 Returning cached devices list');
    return _devicesCache;
  }

  console.log('🔄 Fetching fresh devices list from WebSocket');
  const response = await callWebSocket(hass, {
    type: 'ramses_extras/get_available_devices',
  });

  // Cache the result
  _devicesCache = response.devices || [];
  _devicesCacheTimestamp = now;

  console.log(`✅ Cached ${_devicesCache.length} devices for ${CACHE_DURATION}ms`);
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
