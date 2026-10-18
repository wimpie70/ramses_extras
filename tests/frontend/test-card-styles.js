/**
 * Unit tests for card-styles.js corner layout (issue 314)
 *
 * The bottom-right corner value (supply temp, plus the outdoor RH row in
 * the supply layout) must keep its content hugging the card's right edge,
 * and on narrow cards the humidity row wraps so it cannot slide under the
 * centered stats block and become unreadable.
 */

import { describe, expect, test } from '@jest/globals';

import { CARD_STYLE } from '../../custom_components/ramses_extras/features/hvac_fan_card/www/hvac_fan_card/card-styles.js';

describe('card styles bottom corner alignment', () => {
  test('bottom-right rows are right-aligned', () => {
    expect(CARD_STYLE).toMatch(
      /\.bottom-right :is\([^)]*\.r-xtrs-hvac-fan-temp-value[^)]*\)\s*\{\s*justify-content: flex-end/
    );
    expect(CARD_STYLE).toMatch(
      /\.bottom-right :is\([^)]*\.r-xtrs-hvac-fan-humidity-row[^)]*\)\s*\{\s*justify-content: flex-end/
    );
  });

  test('bottom-left rows stay left-aligned', () => {
    expect(CARD_STYLE).toMatch(/\.bottom-left :is\([^)]*\)\s*\{\s*justify-content: flex-start/);
  });
});

describe('card styles narrow-card fallback', () => {
  test('card root is a query container', () => {
    expect(CARD_STYLE).toMatch(
      /\.r-xtrs-hvac-fan-ventilation-card\s*\{[^}]*container-type: inline-size/
    );
  });

  test('container query caps the bottom-right corner and wraps the humidity row', () => {
    const containerBlock = CARD_STYLE.match(/@container[\s\S]*?(?=@media|\*\/)/);
    expect(containerBlock).not.toBeNull();
    const block = containerBlock[0];
    expect(block).toContain('max-width: 96px');
    expect(block).toContain('flex-wrap: wrap');
    expect(block).toContain('display: none');
  });
});
