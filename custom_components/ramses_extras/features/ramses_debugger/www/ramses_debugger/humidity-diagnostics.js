/**
 * Humidity sensor location diagnostics - pure analysis functions.
 *
 * Detects whether a FAN's reported "outdoor" relative humidity is measured
 * on the untreated outdoor air or inside the supply duct (after heat
 * recovery / bypass), as observed on Orcon and ClimaRad units.
 *
 * Method: during a bypass perturbation (supply temperature drops while
 * reported RH rises), the dewpoint computed from RH paired with the
 * *correct* temperature stays constant, because absolute moisture is
 * conserved through the exchanger. The pairing with the lowest dewpoint
 * spread wins. See ramses_extras issue 304.
 *
 * @module humidity-diagnostics
 */

const MAGNUS_A = 17.27;
const MAGNUS_B = 237.7;

/** Minimum number of merged samples needed for a verdict. */
export const MIN_SAMPLES = 10;

/** Minimum supply temperature range (°C) for a conclusive run. */
export const MIN_SUPPLY_RANGE_C = 1.0;

/** Relative improvement needed for one pairing to win over the other. */
export const VERDICT_MARGIN = 0.8;

/**
 * Dewpoint in °C from temperature and relative humidity (Magnus).
 *
 * @param {number} tempC Temperature in °C.
 * @param {number} rhPct Relative humidity in %.
 * @returns {number|null} Dewpoint in °C or null when inputs are invalid.
 */
export function dewpointCelsius(tempC, rhPct) {
  if (!Number.isFinite(tempC) || !Number.isFinite(rhPct)) {
    return null;
  }
  const rh = Math.min(Math.max(rhPct, 0.01), 100) / 100;
  const gamma = Math.log(rh) + (MAGNUS_A * tempC) / (MAGNUS_B + tempC);
  return (MAGNUS_B * gamma) / (MAGNUS_A - gamma);
}

/**
 * Parse one entity's history_during_period response into [{t, v}].
 *
 * Handles both the minimal_response shape ({s, lc} where lc is a unix
 * timestamp in seconds) and the regular shape ({state, last_changed} ISO).
 *
 * @param {Array<Object>} raw Array of state objects from history ws.
 * @returns {Array<{t: number, v: number}>} Sorted numeric samples.
 */
export function parseHistorySeries(raw) {
  if (!Array.isArray(raw)) {
    return [];
  }
  const out = [];
  for (const item of raw) {
    if (!item || typeof item !== 'object') {
      continue;
    }
    let v;
    let t;
    if ('s' in item) {
      v = Number(item.s);
      t = Number(item.lc) * 1000;
    } else if ('state' in item) {
      v = Number(item.state);
      const changed = item.lu ?? item.last_updated ?? item.last_changed;
      t = typeof changed === 'number' ? changed * 1000 : Date.parse(changed);
    } else {
      continue;
    }
    if (Number.isFinite(v) && Number.isFinite(t)) {
      out.push({ t, v });
    }
  }
  out.sort((a, b) => a.t - b.t);
  return out;
}

/**
 * Forward-fill several series onto their union timeline.
 *
 * @param {Array<Array<{t: number, v: number}>>} seriesList Parsed series.
 * @returns {Array<{t: number, values: number[]}>} Samples where every
 *   series has a known value.
 */
export function mergeSeries(seriesList) {
  const times = new Set();
  for (const series of seriesList) {
    for (const p of series) {
      times.add(p.t);
    }
  }
  const timeline = [...times].sort((a, b) => a - b);
  const merged = [];
  const idx = seriesList.map(() => 0);
  for (const t of timeline) {
    const values = seriesList.map((series, i) => {
      while (idx[i] < series.length && series[idx[i]].t <= t) {
        idx[i] += 1;
      }
      return idx[i] > 0 ? series[idx[i] - 1].v : null;
    });
    if (values.every((v) => v !== null)) {
      merged.push({ t, values });
    }
  }
  return merged;
}

/**
 * Population standard deviation.
 *
 * @param {number[]} values Numbers.
 * @returns {number} Standard deviation (0 for empty input).
 */
export function stdDev(values) {
  if (values.length === 0) {
    return 0;
  }
  const mean = values.reduce((a, b) => a + b, 0) / values.length;
  const variance =
    values.reduce((acc, v) => acc + (v - mean) * (v - mean), 0) /
    values.length;
  return Math.sqrt(variance);
}

/**
 * Pearson correlation coefficient.
 *
 * @param {number[]} xs First series.
 * @param {number[]} ys Second series (same length).
 * @returns {number|null} Correlation in [-1, 1] or null if undefined.
 */
export function pearson(xs, ys) {
  const n = Math.min(xs.length, ys.length);
  if (n < 2) {
    return null;
  }
  const mx = xs.slice(0, n).reduce((a, b) => a + b, 0) / n;
  const my = ys.slice(0, n).reduce((a, b) => a + b, 0) / n;
  let num = 0;
  let dx = 0;
  let dy = 0;
  for (let i = 0; i < n; i += 1) {
    const ax = xs[i] - mx;
    const ay = ys[i] - my;
    num += ax * ay;
    dx += ax * ax;
    dy += ay * ay;
  }
  const den = Math.sqrt(dx * dy);
  return den === 0 ? null : num / den;
}

/**
 * Analyse parsed history series and return the location verdict.
 *
 * @param {Object} input Parsed series.
 * @param {Array<{t: number, v: number}>} input.rh Reported outdoor RH (%).
 * @param {Array<{t: number, v: number}>} input.outdoorTemp Outdoor temp (°C).
 * @param {Array<{t: number, v: number}>} input.supplyTemp Supply temp (°C).
 * @returns {Object} Result: {verdict, reason, samples, supplyRange,
 *   dewpointStdSupply, dewpointStdOutdoor, corrRhSupply}.
 *   verdict is 'supply', 'outdoor' or 'inconclusive'.
 */
export function analyzeHumidityLocation({ rh, outdoorTemp, supplyTemp }) {
  const merged = mergeSeries([rh, outdoorTemp, supplyTemp]);
  const result = {
    verdict: 'inconclusive',
    reason: null,
    samples: merged.length,
    supplyRange: null,
    dewpointStdSupply: null,
    dewpointStdOutdoor: null,
    corrRhSupply: null,
  };
  if (merged.length < MIN_SAMPLES) {
    result.reason = 'not_enough_samples';
    return result;
  }

  const rhVals = merged.map((m) => m.values[0]);
  const outVals = merged.map((m) => m.values[1]);
  const supVals = merged.map((m) => m.values[2]);

  result.supplyRange = Math.max(...supVals) - Math.min(...supVals);

  const dpSupply = [];
  const dpOutdoor = [];
  const rhAligned = [];
  const supAligned = [];
  for (let i = 0; i < merged.length; i += 1) {
    const ds = dewpointCelsius(supVals[i], rhVals[i]);
    const do_ = dewpointCelsius(outVals[i], rhVals[i]);
    if (ds !== null && do_ !== null) {
      dpSupply.push(ds);
      dpOutdoor.push(do_);
      rhAligned.push(rhVals[i]);
      supAligned.push(supVals[i]);
    }
  }
  if (dpSupply.length < MIN_SAMPLES) {
    result.reason = 'not_enough_samples';
    return result;
  }

  result.dewpointStdSupply = stdDev(dpSupply);
  result.dewpointStdOutdoor = stdDev(dpOutdoor);
  result.corrRhSupply = pearson(rhAligned, supAligned);

  if (result.supplyRange < MIN_SUPPLY_RANGE_C) {
    result.reason = 'supply_temp_flat';
    return result;
  }

  if (result.dewpointStdSupply < result.dewpointStdOutdoor * VERDICT_MARGIN) {
    result.verdict = 'supply';
  } else if (
    result.dewpointStdOutdoor < result.dewpointStdSupply * VERDICT_MARGIN
  ) {
    result.verdict = 'outdoor';
  } else {
    result.reason = 'ambiguous';
  }
  return result;
}
