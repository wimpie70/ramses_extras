# Home Assistant Card Localization System

This project includes a comprehensive localization system for Home Assistant custom cards that follows HA conventions and provides flexible multi-language support.

## Overview

The localization system uses **card-specific translation folders** approach, where each card owns its translations. This provides better maintainability, scalability, and follows Home Assistant's own patterns.

## Structure

```
www/
├── helpers/
│   └── card-translations.js          ← Reusable translation manager
└── your_card/
    ├── your-card.js                  ← Card with localization integration
    ├── translations/
    │   ├── en.json                   ← English (default)
    │   ├── nl.json                   ← Dutch
    │   ├── de.json                   ← German (example)
    │   └── [other languages].json
    └── templates/
```

## Key Features

- **Smart Language Detection**: Automatically detects user's preferred language from HA
- **Fallback Support**: Falls back to English if translation missing
- **String Interpolation**: Support for dynamic values like `{minutes} min`
- **Translation Caching**: Prevents duplicate file loading
- **Error Handling**: Graceful degradation if translations fail
- **HA Convention Compliance**: Matches your `ramses_cc` component pattern

## Usage

### 1. Setting Up Translations

Create translation files in your card's `translations/` folder:

**translations/en.json** (English - required as fallback):
```json
{
  "card": {
    "title": "My Card",
    "settings": "Settings"
  },
  "controls": {
    "start": "Start",
    "stop": "Stop",
    "status_active": "{status} Active"
  }
}
```

**translations/nl.json** (Dutch - optional):
```json
{
  "card": {
    "title": "Mijn Kaart",
    "settings": "Instellingen"
  },
  "controls": {
    "start": "Start",
    "stop": "Stop",
    "status_active": "{status} Actief"
  }
}
```

### 2. Integrating with Your Card

```javascript
// Import the translation system
import { getTranslator } from '/local/ramses_extras/custom_components/ramses_extras/www/helpers/card-translations.js';

class MyCard extends HTMLElement {
  constructor() {
    super();
    this.translator = null;
    this.initTranslations();
  }

  async initTranslations() {
    try {
      const cardPath = './www/your_card';
      this.translator = await getTranslator('your-card', cardPath);
      console.log('🌍 Card translations initialized');
    } catch (error) {
      console.warn('⚠️ Failed to initialize translations:', error);
      this.translator = {
        t: (key) => key,
        has: () => false,
        getCurrentLanguage: () => 'en'
      };
    }
  }

  // Helper method for translations
  t(key, params = {}) {
    return this.translator ? this.translator.t(key, params) : key;
  }

  render() {
    // Use translations in your HTML
    const html = `
      <h1>${this.t('card.title')}</h1>
      <button>${this.t('controls.start')}</button>
      <p>${this.t('controls.status_active', { status: 'System' })}</p>
    `;

    this.shadowRoot.innerHTML = html;
  }
}
```

### 3. Translation Keys

Use dot notation for nested translations:
- `card.title` → "My Card"
- `controls.status_active` → "System Active"
- `parameters.temperature` → "Temperature"

### 4. String Interpolation

Support dynamic values in translations:
```json
{
  "timer_minutes": "{minutes} min remaining",
  "status_active": "{device} is {status}"
}
```

Usage:
```javascript
this.t('timer_minutes', { minutes: 15 })    // "15 min remaining"
this.t('status_active', { device: 'Fan', status: 'Active' })  // "Fan is Active"
```

## Adding New Languages

1. Copy an existing translation file (e.g., `en.json`)
2. Rename it to the language code (e.g., `de.json` for German)
3. Translate all the strings
4. The system will automatically detect and use it

## Language Detection

The system detects languages in this order:
1. **Home Assistant user preference** (`hass.language`)
2. **Browser language** (`navigator.language`)
3. **English fallback** (default)

## Error Handling

- Missing translation files → Falls back to English
- Invalid translation files → Uses key as fallback
- Network errors → Graceful degradation with console warnings
- Non-existent translation keys → Returns the key itself

## Performance

- **Lazy Loading**: Only loads translations when needed
- **Caching**: Prevents duplicate HTTP requests
- **Efficient**: Small translation files load quickly
- **Async**: Non-blocking translation initialization

## FAN Commands Integration (HVAC Fan Card Example)

The HVAC Fan Card demonstrates integration with real HVAC commands using the `FAN_COMMANDS` object:

```javascript
static get FAN_COMMANDS() {
  return {
    'bypass_open': {
      code: '22F7',
      verb: ' W',
      payload: '00C8EF'  // Bypass open command
    },
    'bypass_close': {
      code: '22F7',
      verb: ' W',
      payload: '0000EF'  // Bypass close command
    },
    'bypass_auto': {
      code: '22F7',
      verb: ' W',
      payload: '00FFEF'  // Bypass auto command
    },
    'high_15': {
      code: '22F3',
      verb: ' I',
      payload: '00120F03040404'  // 15 minutes timer
    },
    'high_30': {
      code: '22F3',
      verb: ' I',
      payload: '00121E03040404'  // 30 minutes timer
    },
    'high_60': {
      code: '22F3',
      verb: ' I',
      payload: '00123C03040404'  // 60 minutes timer
    }
  };
}
```

**Command Sending**:
- Bypass commands update UI immediately and SVG when entity state changes
- Timer commands convert minutes to command keys (e.g., '15' → 'high_15')
- All commands use the card's `sendFanCommand()` method which handles WebSocket communication
- UI feedback provided via `updateBypassUI()` and `updateTimerUI()` methods

**Global Function Bindings**:
```javascript
window.setBypassMode = function(mode) {
  const card = document.querySelector('hvac-fan-card');
  if (card) {
    card.sendBypassCommand(mode);
  }
};

window.setTimer = function(minutes) {
  const card = document.querySelector('hvac-fan-card');
  if (card) {
    card.setTimer(minutes);
  }
};
```

## Examples in This Project

- **HVAC Fan Card**: Complete implementation with English and Dutch support
- **Reusable Helper**: `card-translations.js` can be used by any card

## Best Practices

1. **Keep translations granular**: Use meaningful key names like `controls.start_button`
2. **Use interpolation**: Avoid concatenating strings in code
3. **Provide context**: Add comments for translators when needed
4. **Test all languages**: Ensure UI works with different string lengths
5. **Document keys**: Keep a key reference for translators

## Troubleshooting

**404 errors on translation files**: Check that files are in `translations/` folder with correct language codes
**Import errors**: Verify import path is `../../helpers/card-translations.js`
**Missing translations**: Check browser console for loading errors
**Wrong language**: Verify HA user language settings

This localization system provides a professional, scalable solution for multi-language Home Assistant custom cards.
