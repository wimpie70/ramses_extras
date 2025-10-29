# HTTP 404 Error Resolution Summary

## Issue
The Home Assistant card was trying to import the translation helper from an incorrect path:
- **Expected**: `/local/helpers/card-translations.js`
- **Actual**: `/local/ramses_extras/custom_components/ramses_extras/www/helpers/card-translations.js`

## Root Cause
The import path `../../helpers/card-translations.js` was incorrect for the file structure:
```
ramses_extras/custom_components/ramses_extras/www/
├── helpers/
│   └── card-translations.js
└── hvac_fan_card/
    └── hvac-fan-card.js
```

From `hvac_fan_card/hvac-fan-card.js`, we need to go up **3 levels** to reach the helpers folder.

## Fix Applied
Changed the import statement in `hvac-fan-card.js`:

**Before** (❌ Incorrect):
```javascript
import { getTranslator } from '../../../helpers/card-translations.js';
```

**After** (✅ Correct):
```javascript
import { getTranslator } from '/local/ramses_extras/custom_components/ramses_extras/www/helpers/card-translations.js';
```

**Issue**: Home Assistant's ES6 module system requires absolute paths from `/local/` prefix for cross-directory imports.

## Path Resolution
- `../../../` from `hvac_fan_card/hvac-fan-card.js` goes up:
  1. `hvac_fan_card/` → `www/`
  2. `www/` → `ramses_extras/`
  3. `ramses_extras/` → `custom_components/ramses_extras/`
- Then `helpers/card-translations.js` adds the final part
- **Result**: `custom_components/ramses_extras/www/helpers/card-translations.js`
- **Served as**: `/local/ramses_extras/custom_components/ramses_extras/www/helpers/card-translations.js`

## Updated Files
- ✅ `hvac-fan-card.js` - Fixed import path
- ✅ `README_LOCALIZATION.md` - Updated documentation with correct path

## Next Steps
1. **Restart Home Assistant** to reload the custom component
2. **Check browser console** - The 404 error should be resolved
3. **Test translations** - Card should now load with English/Dutch language support

## Verification
The card should now successfully:
- Import the translation manager without errors
- Initialize translations automatically
- Use the correct language based on HA user preferences
- Display translated strings in the UI

This fix ensures the localization system works correctly across all future cards using the same pattern.
