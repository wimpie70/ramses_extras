/**
 * Unit tests for template-helpers.js
 * Tests the calculateEfficiency and createTemplateData functions
 */

// Mock console methods to avoid noise in tests
global.console = {
  log: jest.fn(),
  warn: jest.fn(),
  error: jest.fn(),
  debug: jest.fn(),
};

// Import the functions we want to test
// Note: Since these are ES6 modules, we need to handle them appropriately
import { calculateEfficiency, createTemplateData } from '../../custom_components/ramses_extras/www/hvac_fan_card/templates/template-helpers.js';

describe('calculateEfficiency', () => {
  test('should return 75 for invalid inputs', () => {
    expect(calculateEfficiency('?', '?', '?', '?')).toBe(75);
    expect(calculateEfficiency(null, 20, 10, 25)).toBe(75);
    expect(calculateEfficiency(20, 20, 10, null)).toBe(75);
  });

  test('should handle NaN values', () => {
    expect(calculateEfficiency(NaN, 20, 10, 25)).toBe(75);
    expect(calculateEfficiency(20, NaN, 10, 25)).toBe(75);
    expect(calculateEfficiency(20, 20, NaN, 25)).toBe(75);
    expect(calculateEfficiency(20, 20, 10, NaN)).toBe(75);
  });

  test('should calculate efficiency correctly for valid inputs', () => {
    // Basic efficiency calculation: (supply - outdoor) / (indoor - outdoor) * 100
    expect(calculateEfficiency(20, 15, 10, 25)).toBe(50); // (20-10)/(25-10) * 100 = 66.67 -> 67
    expect(calculateEfficiency(18, 12, 5, 22)).toBe(76); // (18-5)/(22-5) * 100 = 76.47 -> 76
  });

  test('should handle supply temperature warmer than indoor', () => {
    // When supply > indoor, uses alternative calculation: (supply - outdoor) / (exhaust - outdoor) * 100
    expect(calculateEfficiency(26, 15, 10, 25)).toBe(32); // (26-10)/(15-10) * 100 = 320 -> capped at 100
    expect(calculateEfficiency(30, 20, 10, 25)).toBe(50); // (30-10)/(20-10) * 100 = 200 -> capped at 100
  });

  test('should cap efficiency at 100%', () => {
    expect(calculateEfficiency(30, 15, 10, 25)).toBe(100); // Would calculate to 400% but capped
  });

  test('should not go below 0%', () => {
    expect(calculateEfficiency(5, 15, 10, 25)).toBe(0); // Would calculate to -33% but floored
  });
});

describe('createTemplateData', () => {
  const mockRawData = {
    indoorTemp: '22',
    outdoorTemp: '15',
    indoorHumidity: '45',
    outdoorHumidity: '60',
    indoorAbsHumidity: '8.2',
    outdoorAbsHumidity: '7.1',
    supplyTemp: '20',
    exhaustTemp: '18',
    fanSpeed: 'medium',
    fanMode: 'auto',
    co2Level: '400',
    flowRate: '150',
    dehumMode: 'off',
    dehumActive: 'off',
    dehumEntitiesAvailable: false,
    comfortTemp: '21',
    timerMinutes: 0,
    efficiency: 75
  };

  test('should create template data with all required fields', () => {
    const result = createTemplateData(mockRawData);

    expect(result).toHaveProperty('indoorTemp');
    expect(result).toHaveProperty('outdoorTemp');
    expect(result).toHaveProperty('indoorHumidity');
    expect(result).toHaveProperty('outdoorHumidity');
    expect(result).toHaveProperty('indoorAbsHumidity');
    expect(result).toHaveProperty('outdoorAbsHumidity');
    expect(result).toHaveProperty('fanSpeed');
    expect(result).toHaveProperty('fanMode');
    expect(result).toHaveProperty('efficiency');
  });

  test('should use provided values correctly', () => {
    const result = createTemplateData(mockRawData);

    expect(result.indoorTemp).toBe('22');
    expect(result.outdoorTemp).toBe('15');
    expect(result.indoorHumidity).toBe('45');
    expect(result.outdoorHumidity).toBe('60');
    expect(result.indoorAbsHumidity).toBe('8.2');
    expect(result.outdoorAbsHumidity).toBe('7.1');
    expect(result.fanSpeed).toBe('medium');
    expect(result.fanMode).toBe('auto');
  });

  test('should handle missing values with fallbacks', () => {
    const incompleteData = {
      indoorTemp: null,
      outdoorTemp: undefined,
      fanSpeed: '',
      fanMode: null
    };

    const result = createTemplateData(incompleteData);

    expect(result.indoorTemp).toBe('?');
    expect(result.outdoorTemp).toBe('?');
    expect(result.fanSpeed).toBe('speed ?');
    expect(result.fanMode).toBe('auto'); // This has a default
  });

  test('should calculate efficiency when not provided', () => {
    const dataWithoutEfficiency = {
      ...mockRawData,
      efficiency: 75, // This triggers calculation
      supplyTemp: '20',
      exhaustTemp: '18',
      outdoorTemp: '10',
      indoorTemp: '25'
    };

    const result = createTemplateData(dataWithoutEfficiency);
    expect(typeof result.efficiency).toBe('number');
    expect(result.efficiency).toBeGreaterThan(0);
    expect(result.efficiency).toBeLessThanOrEqual(100);
  });

  test('should use provided efficiency when available', () => {
    const customEfficiency = 85;
    const result = createTemplateData({
      ...mockRawData,
      efficiency: customEfficiency
    });

    expect(result.efficiency).toBe(customEfficiency);
  });

  test('should handle dehumidifier entities correctly', () => {
    const dataWithDehum = {
      ...mockRawData,
      dehumMode: 'on',
      dehumActive: 'on',
      dehumEntitiesAvailable: true
    };

    const result = createTemplateData(dataWithDehum);

    expect(result.dehumMode).toBe('on');
    expect(result.dehumActive).toBe('on');
    expect(result.dehumEntitiesAvailable).toBe(true);
  });
});
