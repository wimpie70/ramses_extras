# Version Banner - Automatic Injection on All Cards

## Changes Made

### 1. **Added to Base Card** (`ramses-base-card.js`)

- Added import: `import { getVersionMismatchBanner } from './version-banner.js';`
- Added automatic injection in `render()` method:
  - After `_renderContent()` is called, `_injectVersionBanner()` runs automatically
  - Finds the `<ha-card>` element and prepends the banner if there's a version mismatch
  - Uses DOM manipulation to inject the banner element

### 2. **Updated Log Explorer** (`ramses-log-explorer.js`)

- Removed manual import of `getVersionMismatchBanner`
- No changes needed to `_renderContent()` - works exactly as before
- Banner is automatically injected by the base card

## How It Works

**Completely automatic!** Cards extending `RamsesBaseCard` don't need to do anything:

```javascript
_renderContent() {
  // Just render your card normally
  this.shadowRoot.innerHTML = `
    <style>
      /* your styles */
    </style>
    <ha-card header="My Card">
      <!-- your card content -->
    </ha-card>
  `;

  // Banner is automatically injected here by base card
}
```

The base card's `render()` flow:

1. Check if HA is initialized → show "initializing" placeholder if not
2. Check if feature is enabled → show "disabled" placeholder if not
3. Check if config is valid → show "config error" if not
4. Call `_renderContent()` → card renders normally
5. **Call `_injectVersionBanner()` → banner auto-injected if needed**

## Benefits

1. **Zero Code Changes**: Existing cards work automatically
2. **Standardized**: Same pattern as initialization placeholders
3. **Consistent**: Same banner styling across all cards
4. **No Overhead**: If versions match, no DOM manipulation occurs
5. **Future-Proof**: New cards automatically get the banner

## Next Steps

To deploy:

```bash
make install
docker restart hass
```

Then hard refresh your browser (Ctrl+Shift+R) to see the banner on **all cards** when there's a version mismatch.
