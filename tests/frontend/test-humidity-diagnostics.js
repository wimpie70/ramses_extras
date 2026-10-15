/**
 * Unit tests for humidity-diagnostics.js (issue 304)
 *
 * The diagnostic detects whether a FAN's reported outdoor RH is measured
 * on the untreated outdoor air or in the supply duct, by comparing
 * dewpoint stability between the two temperature pairings.
 */

import { describe, expect, test } from '@jest/globals';

import {
  analyzeHumidityLocation,
  dewpointCelsius,
  mergeSeries,
  parseHistorySeries,
  pearson,
  stdDev,
} from '../../custom_components/ramses_extras/features/ramses_debugger/www/ramses_debugger/humidity-diagnostics.js';

const ts = (min) => 1_700_000_000_000 + min * 60_000;

/**
 * Build a series of `{t, v}` points every minute.
 * @param {(i: number) => number} fn Value at minute i.
 * @param {number} n Number of minutes.
 */
function series(fn, n = 20) {
  return Array.from({ length: n }, (_, i) => ({ t: ts(i), v: fn(i) }));
}

describe('dewpointCelsius', () => {
  test('100% RH returns the temperature itself', () => {
    expect(dewpointCelsius(10, 100)).toBeCloseTo(10, 1);
  });

  test('known value: 20°C 50% ≈ 9.3°C', () => {
    expect(dewpointCelsius(20, 50)).toBeCloseTo(9.3, 0);
  });

  test('invalid input returns null', () => {
    expect(dewpointCelsius(NaN, 50)).toBeNull();
    expect(dewpointCelsius(20, NaN)).toBeNull();
  });
});

describe('parseHistorySeries', () => {
  test('parses minimal_response {s, lc} rows', () => {
    const rows = [
      { s: '10.5', lc: 1700000000 },
      { s: '11.0', lc: 1700000060 },
    ];
    const out = parseHistorySeries(rows);
    expect(out).toHaveLength(2);
    expect(out[0]).toEqual({ t: 1700000000000, v: 10.5 });
    expect(out[1].v).toBe(11);
  });

  test('parses regular {state, last_changed} rows', () => {
    const rows = [{ state: '73', last_changed: '2023-11-14T22:13:20.000Z' }];
    const out = parseHistorySeries(rows);
    expect(out).toHaveLength(1);
    expect(out[0].v).toBe(73);
  });

  test('drops non-numeric states and bad input', () => {
    expect(parseHistorySeries(null)).toEqual([]);
    expect(
      parseHistorySeries([
        { s: 'on', lc: 1 },
        { s: '5', lc: 2 },
      ])
    ).toEqual([{ t: 2000, v: 5 }]);
  });
});

describe('mergeSeries', () => {
  test('forward-fills onto the union timeline', () => {
    const a = [
      { t: 0, v: 1 },
      { t: 10, v: 2 },
    ];
    const b = [{ t: 5, v: 100 }];
    const merged = mergeSeries([a, b]);
    // t=5: a holds 1, b starts 100; t=10: a=2, b holds 100
    expect(merged.map((m) => m.values)).toEqual([
      [1, 100],
      [2, 100],
    ]);
  });

  test('skips times before all series have a value', () => {
    const a = [{ t: 0, v: 1 }];
    const b = [{ t: 5, v: 9 }];
    const merged = mergeSeries([a, b]);
    expect(merged).toHaveLength(1);
    expect(merged[0].t).toBe(5);
  });
});

describe('stdDev / pearson', () => {
  test('stdDev of constant series is 0', () => {
    expect(stdDev([3, 3, 3])).toBe(0);
    expect(stdDev([])).toBe(0);
  });

  test('pearson detects perfect inverse correlation', () => {
    expect(pearson([1, 2, 3], [3, 2, 1])).toBeCloseTo(-1, 5);
    expect(pearson([1, 2, 3], [1, 2, 3])).toBeCloseTo(1, 5);
    expect(pearson([1], [2])).toBeNull();
  });
});

describe('analyzeHumidityLocation', () => {
  test('supply-duct sensor: RH rising as supply drops → verdict supply', () => {
    // Simulates the Orcon bypass run: supply temp drops 14→11 °C while
    // the reported RH rises so that dewpoint stays ~8.7 °C constant.
    const supT = series((i) => 14 - i * 0.15);
    const rh = series(
      (i) =>
        100 *
        // keep dewpoint ~constant vs supply temp: RH = f(supT)
        (Math.exp((17.27 * 8.7) / (237.7 + 8.7)) /
          Math.exp((17.27 * supT[i].v) / (237.7 + supT[i].v)))
    );
    const outT = series(() => 6.5); // ambient temp ~constant

    const res = analyzeHumidityLocation({
      rh,
      outdoorTemp: outT,
      supplyTemp: supT,
    });
    expect(res.verdict).toBe('supply');
    expect(res.dewpointStdSupply).toBeLessThan(res.dewpointStdOutdoor);
    expect(res.corrRhSupply).toBeLessThan(-0.8);
  });

  test('outdoor sensor: RH moves with outdoor temp → verdict outdoor', () => {
    const outT = series((i) => 8 + Math.sin(i / 4) * 2);
    const rh = series((i) => 60 + Math.sin(i / 4) * 10);
    const supT = series(() => 16); // supply temp held by recovery

    const res = analyzeHumidityLocation({
      rh,
      outdoorTemp: outT,
      supplyTemp: supT,
    });
    // supply temp flat → inconclusive even though outdoor pairing may win
    expect(res.verdict).toBe('inconclusive');
    expect(res.reason).toBe('supply_temp_flat');
  });

  test('too few samples → inconclusive', () => {
    const short = series((i) => i, 3);
    const res = analyzeHumidityLocation({
      rh: short,
      outdoorTemp: short,
      supplyTemp: short,
    });
    expect(res.verdict).toBe('inconclusive');
    expect(res.reason).toBe('not_enough_samples');
  });
});
