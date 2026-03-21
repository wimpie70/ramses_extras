/**
 * Entity validation utilities for Home Assistant custom cards
 * Provides common validation patterns for entity checking
 */

/**
 * Validate core entities required for ventilation cards
 * @param {Object} hass - Home Assistant instance
 * @param {Object} config - Card configuration
 * @returns {Object} Validation results with available/missing entities
 */
export function validateCoreEntities(hass, config) {
  if (!hass || !config) {
    return {
      valid: false,
      error: 'Missing hass or config',
      available: [],
      missing: []
    };
  }

  // Core entities that should exist
  const coreEntities = {
    'Indoor Temperature': config.indoor_temp_entity,
    'Outdoor Temperature': config.outdoor_temp_entity,
    'Indoor Humidity': config.indoor_humidity_entity,
    'Outdoor Humidity': config.outdoor_humidity_entity,
    'Supply Temperature': config.supply_temp_entity,
    'Exhaust Temperature': config.exhaust_temp_entity,
    'Fan Speed': config.fan_speed_entity,
    'Fan Mode': config.fan_mode_entity,
    'Bypass': config.bypass_entity,
  };

  const missingCoreEntities = [];
  const availableCoreEntities = [];

  Object.entries(coreEntities).forEach(([name, entityId]) => {
    // Only consider it missing if an entityId was provided but doesn't exist
    if (entityId) {
      if (entityExists(hass, entityId)) {
        availableCoreEntities.push(name);
      } else {
        missingCoreEntities.push(name);
      }
    }
  });

  return {
    valid: missingCoreEntities.length === 0,
    available: availableCoreEntities,
    missing: missingCoreEntities,
    total: Object.keys(coreEntities).length,
    availableCount: availableCoreEntities.length
  };
}

/**
 * Validate dehumidification entities
 * @param {Object} hass - Home Assistant instance
 * @param {Object} config - Card configuration
 * @returns {Object} Validation results for dehumidification entities
 */
export function validateDehumidifyEntities(hass, config) {
  if (!hass || !config) {
    return {
      available: false,
      entities: [],
      error: 'Missing hass or config'
    };
  }

  const dehumEntities = {
    'Dehumidify Mode': config.dehum_mode_entity,
    'Dehumidify Active': config.dehum_active_entity,
  };

  const missingDehumEntities = [];
  const availableDehumEntities = [];

  Object.entries(dehumEntities).forEach(([name, entityId]) => {
    if (entityId) {
      if (entityExists(hass, entityId)) {
        availableDehumEntities.push(name);
      } else {
        missingDehumEntities.push(name);
      }
    }
  });

  const entitiesAvailable = availableDehumEntities.length === Object.keys(dehumEntities).length;

  return {
    available: entitiesAvailable,
    entities: availableDehumEntities,
    missing: missingDehumEntities,
    modeEntity: config.dehum_mode_entity,
    activeEntity: config.dehum_active_entity
  };
}

/**
 * Validate absolute humidity entities
 * @param {Object} hass - Home Assistant instance
 * @param {Object} config - Card configuration
 * @returns {Object} Validation results for absolute humidity entities
 */
export function validateAbsoluteHumidityEntities(hass, config) {
  if (!hass || !config) {
    return {
      available: false,
      entities: [],
      error: 'Missing hass or config'
    };
  }

  const absHumidEntities = {
    'Indoor Absolute Humidity': config.indoor_abs_humid_entity,
    'Outdoor Absolute Humidity': config.outdoor_abs_humid_entity,
  };

  const missingAbsEntities = [];
  const availableAbsEntities = [];

  Object.entries(absHumidEntities).forEach(([name, entityId]) => {
    if (entityId) {
      if (entityExists(hass, entityId)) {
        availableAbsEntities.push(name);
      } else {
        missingAbsEntities.push(name);
      }
    }
  });

  return {
    available: availableAbsEntities,
    missing: missingAbsEntities,
    indoorEntity: config.indoor_abs_humid_entity,
    outdoorEntity: config.outdoor_abs_humid_entity
  };
}

/**
 * Validate CO2 control entities
 * @param {Object} hass - Home Assistant instance
 * @param {Object} config - Card configuration
 * @returns {Object} Validation results for CO2 control entities
 */
export function validateCO2ControlEntities(hass, config) {
  if (!hass || !config) {
    return {
      available: false,
      entities: [],
      error: 'Missing hass or config'
    };
  }

  const co2Entities = {
    'CO2 Control': config.co2_control_entity,
    'CO2 Active': config.co2_active_entity,
  };

  const missingCO2Entities = [];
  const availableCO2Entities = [];

  Object.entries(co2Entities).forEach(([name, entityId]) => {
    if (entityId) {
      if (entityExists(hass, entityId)) {
        availableCO2Entities.push(name);
      } else {
        missingCO2Entities.push(name);
      }
    }
  });

  const entitiesAvailable = availableCO2Entities.length === Object.keys(co2Entities).length;

  return {
    available: entitiesAvailable,
    entities: availableCO2Entities,
    missing: missingCO2Entities,
    controlEntity: config.co2_control_entity,
    activeEntity: config.co2_active_entity,
    zoneStatusEntity: config.co2_zone_status_entity
  };
}

/**
 * Check if entity exists and is available
 * @param {Object} hass - Home Assistant instance
 * @param {string} entityId - Entity ID to check
 * @returns {boolean} True if entity exists
 */
export function entityExists(hass, entityId) {
  if (!hass || !hass.states) return false;
  const entity = hass.states[entityId];
  return entity !== undefined && entity !== null;
}

/**
 * Get comprehensive entity validation report
 * @param {Object} hass - Home Assistant instance
 * @param {Object} config - Card configuration
 * @returns {Object} Complete validation report
 */
export function getEntityValidationReport(hass, config) {
  const core = validateCoreEntities(hass, config);
  const dehumidify = validateDehumidifyEntities(hass, config);
  const absoluteHumidity = validateAbsoluteHumidityEntities(hass, config);
  const co2Control = validateCO2ControlEntities(hass, config);

  return {
    overall: {
      valid: core.valid,
      totalEntities: core.total + 2 + 2 + 2, // core + dehumidify + abs humidity + co2
      availableEntities: core.availableCount + dehumidify.entities.length + absoluteHumidity.available.length + co2Control.entities.length
    },
    core,
    dehumidify,
    absoluteHumidity,
    co2Control,
    summary: {
      available: [
        ...core.available,
        ...dehumidify.entities,
        ...absoluteHumidity.available,
        ...co2Control.entities
      ],
      missing: [
        ...core.missing,
        ...dehumidify.missing,
        ...absoluteHumidity.missing,
        ...co2Control.missing
      ]
    }
  };
}
