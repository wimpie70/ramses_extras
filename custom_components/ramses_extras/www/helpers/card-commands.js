/**
 * Command definitions and utilities for Home Assistant custom cards
 * Provides centralized command management for ventilation systems
 */

/**
 * Fan command definitions for ventilation systems
 * Supports Orcon and other compatible systems
 */
export const FAN_COMMANDS = {
  // Basic fan speed commands
  'request10D0': {
    code: '10D0',
    verb: 'RQ',
    payload: '00',  // Request 10D0
    description: 'Request system status'
  },

  // Fan mode commands
  'away': {
    code: '22F1',
    verb: ' I',
    payload: '000007',  // Away mode
    description: 'Set fan to away mode'
  },
  'low': {
    code: '22F1',
    verb: ' I',
    payload: '000107',  // Low speed
    description: 'Set fan to low speed'
  },
  'medium': {
    code: '22F1',
    verb: ' I',
    payload: '000207',  // Medium speed
    description: 'Set fan to medium speed'
  },
  'high': {
    code: '22F1',
    verb: ' I',
    payload: '000307',  // High speed
    description: 'Set fan to high speed'
  },
  'auto': {
    code: '22F1',
    verb: ' I',
    payload: '000407',  // Auto mode
    description: 'Set fan to auto mode'
  },
  'auto2': {
    code: '22F1',
    verb: ' I',
    payload: '000507',  // Auto2 mode
    description: 'Set fan to auto2 mode'
  },
  'boost': {
    code: '22F1',
    verb: ' I',
    payload: '000607',  // Boost mode
    description: 'Set fan to boost mode'
  },
  'disable': {
    code: '22F1',
    verb: ' I',
    payload: '000707',  // Disable mode
    description: 'Disable fan'
  },
  'active': {
    code: '22F1',
    verb: ' I',
    payload: '000807',  // Active mode
    description: 'Set fan to active mode'
  },

  // Maintenance commands
  'filter_reset': {
    code: '10D0',
    verb: ' W',
    payload: '00FF',  // Filter reset
    description: 'Reset filter timer'
  },

  // Timer commands
  'high_15': {
    code: '22F3',
    verb: ' I',
    payload: '00120F03040404',  // 15 minutes timer
    description: 'Set 15 minute timer'
  },
  'high_30': {
    code: '22F3',
    verb: ' I',
    payload: '00121E03040404',  // 30 minutes timer
    description: 'Set 30 minute timer'
  },
  'high_60': {
    code: '22F3',
    verb: ' I',
    payload: '00123C03040404',  // 60 minutes timer
    description: 'Set 60 minute timer'
  },

  // Bypass commands
  'bypass_close': {
    code: '22F7',
    verb: ' W',
    payload: '0000EF',  // Bypass close
    description: 'Close bypass'
  },
  'bypass_open': {
    code: '22F7',
    verb: ' W',
    payload: '00C8EF',  // Bypass open
    description: 'Open bypass'
  },
  'bypass_auto': {
    code: '22F7',
    verb: ' W',
    payload: '00FFEF',  // Bypass auto
    description: 'Set bypass to auto mode'
  },

  // Status request commands
  'request31DA': {
    code: '31DA',
    verb: 'RQ',
    payload: '00',
    description: 'Request 31DA status'
  },
};

/**
 * Get command definition by key
 * @param {string} commandKey - Command key
 * @returns {Object|null} Command definition or null if not found
 */
export function getCommand(commandKey) {
  return FAN_COMMANDS[commandKey] || null;
}

/**
 * Get all available command keys
 * @returns {Array<string>} Array of command keys
 */
export function getAvailableCommands() {
  return Object.keys(FAN_COMMANDS);
}

/**
 * Get commands by category
 * @param {string} category - Category ('fan', 'timer', 'bypass', 'maintenance', 'status')
 * @returns {Object} Commands in the specified category
 */
export function getCommandsByCategory(category) {
  const categories = {
    fan: ['away', 'low', 'medium', 'high', 'active', 'auto', 'auto2', 'boost', 'disable'],
    timer: ['high_15', 'high_30', 'high_60'],
    bypass: ['bypass_close', 'bypass_open', 'bypass_auto'],
    maintenance: ['filter_reset'],
    status: ['request10D0', 'request31DA']
  };

  const categoryCommands = {};
  if (categories[category]) {
    categories[category].forEach(key => {
      if (FAN_COMMANDS[key]) {
        categoryCommands[key] = FAN_COMMANDS[key];
      }
    });
  }

  return categoryCommands;
}

/**
 * Validate command key exists
 * @param {string} commandKey - Command key to validate
 * @returns {boolean} True if command exists
 */
export function isValidCommand(commandKey) {
  return commandKey in FAN_COMMANDS;
}

/**
 * Get command description
 * @param {string} commandKey - Command key
 * @returns {string} Command description or empty string
 */
export function getCommandDescription(commandKey) {
  const command = getCommand(commandKey);
  return command ? command.description : '';
}
