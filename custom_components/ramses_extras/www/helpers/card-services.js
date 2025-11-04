/**
 * Service utilities for Home Assistant custom cards
 * Provides common service call patterns and error handling
 */

/**
 * Call Home Assistant service with error handling
 * @param {Object} hass - Home Assistant instance
 * @param {string} domain - Service domain
 * @param {string} service - Service name
 * @param {Object} serviceData - Service data
 * @returns {Promise<Object>} Service call result
 */
export async function callService(hass, domain, service, serviceData = {}) {
  if (!hass) {
    throw new Error('Home Assistant instance not available');
  }

  try {
    const result = await hass.callService(domain, service, serviceData);
    // console.log(`✅ Service ${domain}.${service} called successfully`);
    return result;
  } catch (error) {
    console.error(`❌ Service call ${domain}.${service} failed:`, error);
    throw error;
  }
}

/**
 * Send WebSocket message with error handling
 * @param {Object} hass - Home Assistant instance
 * @param {Object} message - WebSocket message
 * @returns {Promise<Object>} WebSocket response
 */
export async function callWebSocket(hass, message) {
  if (!hass) {
    throw new Error('Home Assistant instance not available');
  }

  try {
    const result = await hass.callWS(message);
    // console.log(`✅ WebSocket message sent successfully`);
    return result;
  } catch (error) {
    console.error(`❌ WebSocket message failed:`, error);
    throw error;
  }
}

/**
 * Get bound REM device for a given device ID
 * @param {Object} hass - Home Assistant instance
 * @param {string} deviceId - Device ID
 * @returns {Promise<string|null>} Bound REM device ID or null
 */
export async function getBoundRemDevice(hass, deviceId) {
  if (!hass) {
    throw new Error('Home Assistant instance not available');
  }

  const sensorId = 'climate.' + deviceId.replace(/:/g, '_');
  try {
    const boundRem = hass.states[sensorId]?.attributes?.bound_rem;
    if (boundRem) {
      // console.log(`✅ Found bound REM: ${boundRem}`);
      return boundRem;
    }
    console.log(`⚠️ No bound REM found for device: ${deviceId}. You can set it in Ramses RF`);
    return null;
  } catch (error) {
    console.error(`❌ Error getting bound REM device:`, error);
    return null; // Don't throw error, just return null
  }
}

/**
 * Send packet via ramses_cc service
 * @param {Object} hass - Home Assistant instance
 * @param {string} deviceId - Target device ID
 * @param {string} fromId - Source device ID
 * @param {string} verb - Packet verb
 * @param {string} code - Packet code
 * @param {string} payload - Packet payload
 * @returns {Promise<Object>} Service call result
 */
export async function sendPacket(hass, deviceId, fromId, verb, code, payload) {
  // console.log(`send_packet to: ${deviceId}, from ${fromId} ${verb} ${code}  ${payload}`)
  return await callService(hass, 'ramses_cc', 'send_packet', {
    device_id: deviceId,
    from_id: fromId,
    verb: verb,
    code: code,
    payload: payload
  });
}

/**
 * Set fan parameter via ramses_cc service
 * @param {Object} hass - Home Assistant instance
 * @param {string} deviceId - Device ID
 * @param {string} paramId - Parameter ID
 * @param {string} value - Parameter value
 * @returns {Promise<Object>} Service call result
 */
export async function setFanParameter(hass, deviceId, paramId, value) {
  return await callService(hass, 'ramses_cc', 'set_fan_param', {
    device_id: deviceId,
    param_id: paramId,
    value: value.toString()
  });
}

/**
 * Toggle switch entity
 * @param {Object} hass - Home Assistant instance
 * @param {string} entityId - Switch entity ID
 * @returns {Promise<Object>} Service call result
 */
export async function toggleSwitch(hass, entityId) {
  return await callService(hass, 'switch', 'toggle', {
    entity_id: entityId
  });
}

/**
 * Turn on switch entity
 * @param {Object} hass - Home Assistant instance
 * @param {string} entityId - Switch entity ID
 * @returns {Promise<Object>} Service call result
 */
export async function turnOnSwitch(hass, entityId) {
  return await callService(hass, 'switch', 'turn_on', {
    entity_id: entityId
  });
}

/**
 * Turn off switch entity
 * @param {Object} hass - Home Assistant instance
 * @param {string} entityId - Switch entity ID
 * @returns {Promise<Object>} Service call result
 */
export async function turnOffSwitch(hass, entityId) {
  return await callService(hass, 'switch', 'turn_off', {
    entity_id: entityId
  });
}

/**
 * Check if entity exists and is available
 * @param {Object} hass - Home Assistant instance
 * @param {string} entityId - Entity ID to check
 * @returns {boolean} True if entity exists and is available
 */
export function entityExists(hass, entityId) {
  if (!hass || !hass.states) return false;
  const entity = hass.states[entityId];
  return entity !== undefined && entity !== null;
}

/**
 * Get entity state safely
 * @param {Object} hass - Home Assistant instance
 * @param {string} entityId - Entity ID
 * @param {any} defaultValue - Default value if entity doesn't exist
 * @returns {any} Entity state or default value
 */
export function getEntityState(hass, entityId, defaultValue = null) {
  if (!entityExists(hass, entityId)) return defaultValue;
  return hass.states[entityId].state;
}

/**
 * Get entity attributes safely
 * @param {Object} hass - Home Assistant instance
 * @param {string} entityId - Entity ID
 * @param {Object} defaultValue - Default value if entity doesn't exist
 * @returns {Object} Entity attributes or default value
 */
export function getEntityAttributes(hass, entityId, defaultValue = {}) {
  if (!entityExists(hass, entityId)) return defaultValue;
  return hass.states[entityId].attributes || defaultValue;
}
