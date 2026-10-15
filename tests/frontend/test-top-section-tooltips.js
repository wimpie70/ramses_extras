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

describe('createTopSection supply-humidity layout', () => {
  const supplyData = {
    ...templateData,
    outdoorHumidityLocation: 'supply',
    tempControlHtml: '<div class="temp-control-mock">Temp → Off</div>',
    balanceTriggersHtml: '<div class="balance-mock">Balance → On + Passive</div>',
    co2StatusHtml: '<div class="co2-status-mock">CO2 → Off</div>',
    co2ZonesHtml: '<div class="co2-zones-mock">Zone status: idle</div>',
  };

  test('outdoor layout keeps the humidity row with outdoor temp', () => {
    const html = createTopSection(templateData, noTranslations);
    const topLeft = html.match(/top-left[\s\S]*?(?=r-xtrs-hvac-fan-corner-value top-right)/)[0];
    expect(topLeft).toContain('id="outdoorHumidity"');
    expect(topLeft).toContain('id="outdoorAbsHumidity"');

    const bottomRight = html.match(
      /bottom-right[\s\S]*?(?=r-xtrs-hvac-fan-corner-value bottom-left)/
    )[0];
    expect(bottomRight).toContain('id="supplyTemp"');
    expect(bottomRight).not.toContain('id="outdoorHumidity"');
  });

  test('supply layout moves the humidity row to the supply corner', () => {
    const html = createTopSection(supplyData, noTranslations);
    const topLeft = html.match(/top-left[\s\S]*?(?=r-xtrs-hvac-fan-corner-value top-right)/)[0];
    expect(topLeft).not.toContain('id="outdoorHumidity"');

    const bottomRight = html.match(
      /bottom-right[\s\S]*?(?=r-xtrs-hvac-fan-corner-value bottom-left)/
    )[0];
    expect(bottomRight).toContain('id="supplyTemp"');
    expect(bottomRight).toContain('id="outdoorHumidity"');
    expect(bottomRight).toContain('id="outdoorAbsHumidity"');
    expect(bottomRight).toContain('supply duct');
  });

  test('supply layout moves feature status left, zones stay right', () => {
    const html = createTopSection(supplyData, noTranslations);
    const topLeft = html.match(/top-left[\s\S]*?(?=r-xtrs-hvac-fan-corner-value top-right)/)[0];
    expect(topLeft).toContain('Temp → Off');
    expect(topLeft).toContain('Balance → On + Passive');
    expect(topLeft).toContain('CO2 → Off');
    expect(topLeft).not.toContain('Zone status: idle');

    const topRight = html.match(
      /top-right[\s\S]*?(?=r-xtrs-hvac-fan-corner-value bottom-right)/
    )[0];
    expect(topRight).toContain('Zone status: idle');
    expect(topRight).not.toContain('Temp → Off');
    expect(topRight).not.toContain('Balance → On + Passive');
    expect(topRight).not.toContain('CO2 → Off');
  });
});

describe('createTopSection bottom stats', () => {
  test('fan mode sits on the top stats line', () => {
    const html = createTopSection(templateData, noTranslations);
    const statsTop = html.match(/stats-top[\s\S]*?stats-bottom/)[0];
    expect(statsTop).toContain('id="fanMode"');
    const statsBottom = html.match(/stats-bottom[\s\S]*?<\/div>\s*<\/div>\s*<\/div>/)[0];
    expect(statsBottom).not.toContain('id="fanMode"');
  });

  test('connection status is icon-only (tooltip carries the text)', () => {
    const html = createTopSection(templateData, noTranslations);
    const status = html.match(/id="connectionStatus"[\s\S]*?<\/div>\s*<\/div>/)[0];
    expect(status).toContain('connection-icon');
    expect(status).not.toContain('Online');
    expect(status).not.toContain('Offline');
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
