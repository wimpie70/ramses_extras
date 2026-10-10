/**
 * Unit tests for top-section.js tooltips (issue 246)
 *
 * Every value display on the card carries a `title` attribute so users
 * can hover for an explanation. These tests assert the title attributes
 * exist and that the `t()` translation function is honoured.
 */

import { describe, expect, test } from '@jest/globals';

import { createTopSection } from '../../custom_components/ramses_extras/features/hvac_fan_card/www/hvac_fan_card/templates/top-section.js';
import { createControlsSection } from '../../custom_components/ramses_extras/features/hvac_fan_card/www/hvac_fan_card/templates/controls-section.js';

const templateData = {
  outdoorTemp: '15',
  outdoorHumidity: '60',
  outdoorAbsHumidity: '7.1',
  indoorTemp: '22',
  indoorHumidity: '45',
  indoorAbsHumidity: '8.2',
  comfortTemp: '21',
  supplyTemp: '20',
  exhaustTemp: '18',
  exhaustFanSpeed: '55%',
  supplyFanSpeed: '55%',
  fanMode: 'auto',
  fanControlModeLabel: 'Auto',
  co2Level: '700',
  supplyFlowRate: '40',
  exhaustFlowRate: '40',
  efficiency: 75,
  timerMinutesRemaining: 0,
  airflowSvg: '<svg></svg>',
  filterDaysRemaining: 145,
  balanceTriggersHtml: '',
  co2ZonesHtml: '',
  indoorHumidityClass: '',
  co2LevelClass: '',
  transportAvailable: true,
  isCalibrating: false,
  tempControlHtml: '',
};

// t() that reports every key as missing → templates use fallbacks
const noTranslations = () => '';

// t() that returns a marker so we can verify the key is looked up
const markerTranslations = (key) => `TR:${key}`;

describe('createTopSection tooltips', () => {
  const html = createTopSection(templateData, noTranslations);

  test.each([
    'Outside air',
    'Inside air',
    'Outdoor temperature',
    'Indoor temperature',
    'Outdoor relative humidity',
    'Indoor relative humidity',
    'Absolute humidity',
    'CO₂ level',
    'Heat recovery efficiency',
    'filter needs replacement',
    'Comfort temperature',
    'Supply temperature',
    'Exhaust temperature',
    'Supply fan',
    'Exhaust fan',
    'Current fan mode',
    'boost timer',
  ])('contains tooltip: %s', (text) => {
    expect(html).toContain(`title="`);
    expect(html).toContain(text);
  });

  test('uses translations when t() returns a value', () => {
    const translated = createTopSection(templateData, markerTranslations);
    expect(translated).toContain('title="TR:tooltips.outdoor_temp"');
    expect(translated).toContain('title="TR:tooltips.abs_humidity"');
    expect(translated).toContain('title="TR:tooltips.filter_days"');
  });
});

describe('createControlsSection tooltips', () => {
  const config = {
    device_id: '32:153289',
    dehum_mode_entity: 'switch.dehumidify_32_153289',
    co2_control_entity: 'switch.co2_control_32_153289',
    temp_control_entity: 'switch.temp_control_32_153289',
  };
  const html = createControlsSection(true, true, config, noTranslations, true, true);

  test.each([
    'away mode',
    'extras automation',
    'dehumidify',
    'CO₂-based ventilation',
    'temperature control',
    'low speed',
    'medium speed',
    'high speed',
    '15 minutes',
    '30 minutes',
    '60 minutes',
    'automatic control',
    'heat recovery',
    'free cooling',
  ])('contains tooltip: %s', (text) => {
    expect(html).toContain(`title="`);
    expect(html).toContain(text);
  });
});
