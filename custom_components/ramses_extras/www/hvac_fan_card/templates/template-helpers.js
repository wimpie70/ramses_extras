/**
 * Template Helpers
 * Utility functions for data transformation and calculations
 */

/**
 * Calculate heat recovery efficiency based on temperature differences
 * @param {string|number} supplyTemp - Supply air temperature
 * @param {string|number} exhaustTemp - Exhaust air temperature
 * @param {string|number} outdoorTemp - Outdoor air temperature
 * @returns {number} Efficiency percentage (0-100) or 75 if data invalid
 */
function calculateEfficiency(supplyTemp, exhaustTemp, outdoorTemp, indoorTemp) {
  console.log('🔍 DEBUG - Efficiency calculation inputs:', { supplyTemp, exhaustTemp, outdoorTemp, indoorTemp });

  if (supplyTemp === '?' || exhaustTemp === '?' || outdoorTemp === '?' || indoorTemp === '?') {
    console.log('🔍 DEBUG - Invalid input values, returning default 75');
    return 75; // Default fallback value
  }

  const supply = parseFloat(supplyTemp);
  const exhaust = parseFloat(exhaustTemp);
  const outdoor = parseFloat(outdoorTemp);
  const indoor = parseFloat(indoorTemp);

  console.log('🔍 DEBUG - Parsed values:', { supply, exhaust, outdoor, indoor });

  if (isNaN(supply) || isNaN(exhaust) || isNaN(outdoor) || isNaN(indoor)) {
    console.log('🔍 DEBUG - NaN values detected, returning default 75');
    return 75; // Default fallback value
  }

  // Check if indoor temperature makes sense (should be warmest)
  if (indoor <= supply) {
    console.log('🔍 DEBUG - Indoor temperature not warmer than supply - using alternative calculation');
    // Fallback to original calculation if indoor data seems wrong
    const tempDiff = exhaust - outdoor;
    if (Math.abs(tempDiff) < 0.1) return 75;
    return Math.max(0, Math.min(100, Math.round(((supply - outdoor) / (exhaust - outdoor) * 100) * 10) / 10));
  }

  // Calculate the raw efficiency first
  const efficiency = (supply - outdoor) / (indoor - outdoor) * 100;
  console.log('🔍 DEBUG - Alternative efficiency formula: (supply - outdoor) / (indoor - outdoor) * 100%');
  console.log('🔍 DEBUG - Calculated efficiency:', efficiency);

  // Check if supply temperature makes sense (shouldn't be warmer than indoor)
  if (supply > indoor) {
    console.log('🔍 DEBUG - Supply temperature warmer than indoor - possible additional heating or sensor issue');
    console.log('🔍 DEBUG - Supply > Indoor - this suggests additional heating from ventilators');
    // If supply is warmer than indoor, the efficiency calculation gives > 100%
    // This is possible with additional electrical heating, but cap it at 100% for display
    return Math.max(0, Math.min(100, Math.round(efficiency * 10) / 10));
  }

  return Math.max(0, Math.min(100, Math.round(efficiency * 10) / 10));
}

/**
 * Create template data object from raw values
 * @param {Object} rawData - Raw sensor values
 * @returns {Object} Formatted template data
 */
export function createTemplateData(rawData) {
  const {
    indoorTemp, outdoorTemp, indoorHumidity, outdoorHumidity,
    indoorAbsHumidity, outdoorAbsHumidity,  // Integration-provided values (preferred)
    supplyTemp, exhaustTemp, fanSpeed, fanMode, co2Level, flowRate,
    dehumMode, dehumActive, comfortTemp, timerMinutes = 0, efficiency = 75
  } = rawData;

  // Calculate efficiency from temperature data if not provided
  const calculatedEfficiency = efficiency !== 75
    ? efficiency
    : calculateEfficiency(supplyTemp, exhaustTemp, outdoorTemp, indoorTemp);

  console.log('🔍 DEBUG - Efficiency decision:', {
    providedEfficiency: efficiency,
    condition: efficiency !== 75,
    finalEfficiency: calculatedEfficiency,
    calculationTriggered: efficiency === 75
  });

  // Use integration-provided absolute humidity directly (no calculation fallback)
  console.log('🔍 DEBUG - Using integration absolute humidity:', {
    indoorAbsHumidity,
    outdoorAbsHumidity
  });

  return {
    // Temperature and humidity values
    indoorTemp: indoorTemp || '?',
    outdoorTemp: outdoorTemp || '?',
    indoorHumidity: indoorHumidity || '?',
    outdoorHumidity: outdoorHumidity || '?',
    supplyTemp: supplyTemp || '?',
    exhaustTemp: exhaustTemp || '?',

    // Absolute humidity from integration (no calculation)
    indoorAbsHumidity: indoorAbsHumidity,
    outdoorAbsHumidity: outdoorAbsHumidity,

    // Fan and air quality data
    fanSpeed: fanSpeed || 'speed ?',
    fanMode: fanMode || 'auto',
    co2Level: co2Level || '?',
    flowRate: flowRate || '?',
    efficiency: calculatedEfficiency,

    // Dehumidifier and comfort settings
    dehumMode: dehumMode || 'off',
    dehumActive: dehumActive || 'off',
    comfortTemp: comfortTemp || '?',

    // Timer and bypass state
    timerMinutes: timerMinutes,
    bypassState: 'auto' // This would come from actual bypass sensor
  };
}
