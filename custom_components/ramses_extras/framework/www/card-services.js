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
  return callWebSocket(hass, {
    type: 'ramses_extras/default/set_fan_parameter',
    device_id: deviceId,
    param_id: paramId,
    value: value,
  });
}
