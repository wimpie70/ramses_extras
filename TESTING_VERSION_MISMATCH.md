# Testing Version Mismatch Detection

## How to Simulate a Version Mismatch

To test the version mismatch banner and WebSocket blocking without actually deploying different versions:

### Method 1: Browser Console (Recommended)

Open the browser console and run:

```javascript
// Simulate a version mismatch
window.ramsesExtras._versionMismatch = {
  frontend: '0.13.0',
  backend: '0.14.2',
  detected: Date.now(),
};

// Option A: Reload page to trigger re-render of all cards
location.reload();

// Option B: Force re-render without reload (banner appears on next render or WS call)
document
  .querySelectorAll(
    'hvac-fan-card, ramses-log-explorer, ramses-packet-log-explorer, ramses-traffic-analyser'
  )
  .forEach((card) => {
    if (card._scheduleRender) card._scheduleRender(true);
  });
```

**Important Notes:**

- Just setting `window.ramsesExtras.version = "0.13.0"` is **NOT enough** - you must set the `_versionMismatch` object
- When you reload the page, `window.ramsesExtras.version` gets reset to the actual frontend version from the loaded code
- The banner will appear either:
  - Immediately on next render (if you force re-render)
  - When any WebSocket call fails with version mismatch
  - On next page reload

### Method 2: Modify Frontend Version Before Deploy

Edit `manifest.json` to have a different version before deploying:

```json
{
  "version": "0.13.0"
}
```

Then deploy and test with a backend that has version `0.14.2`.

### Method 3: Modify Backend Response

Temporarily modify the backend to return a different version in the WebSocket response.

## What to Test

### 1. Banner Appears on All Cards

After setting the version mismatch, the orange banner should appear on:

- ✅ HVAC Fan Card
- ✅ Log Explorer
- ✅ Packet Log Explorer
- ✅ Traffic Analyser
- ✅ Hello World Card
- ✅ Any custom feature cards

The banner should appear **immediately on render**, not just when a WebSocket call is made.

### 2. WebSocket Calls Are Blocked

Try to:

- Click buttons that trigger WebSocket calls
- Load data in cards
- Refresh card data

Expected behavior:

- ✅ Calls are blocked immediately
- ✅ Console shows one error message per card (no spam)
- ✅ Error message indicates version mismatch

### 3. Initialization Call Bypasses Block

The `ramses_extras/default/get_cards_enabled` call should still work even with version mismatch.

### 4. Hard Refresh Resolves Issue

Click the "Hard Refresh" button on the banner or press `Ctrl+Shift+R`:

- ✅ Banner disappears
- ✅ WebSocket calls work normally
- ✅ Cards function properly

## Console Commands for Testing

```javascript
// Check current version
console.log('Frontend:', window.ramsesExtras.version);
console.log('Mismatch:', window.ramsesExtras._versionMismatch);

// Simulate mismatch
window.ramsesExtras._versionMismatch = {
  frontend: '0.13.0',
  backend: '0.14.2',
  detected: Date.now(),
};

// Force all cards to re-render
document
  .querySelectorAll(
    'hvac-fan-card, ramses-log-explorer, ramses-packet-log-explorer, ramses-traffic-analyser'
  )
  .forEach((card) => {
    if (card.render) card.render();
  });

// Clear mismatch
delete window.ramsesExtras._versionMismatch;

// Force re-render again
document
  .querySelectorAll(
    'hvac-fan-card, ramses-log-explorer, ramses-packet-log-explorer, ramses-traffic-analyser'
  )
  .forEach((card) => {
    if (card.render) card.render();
  });
```

## Expected Console Output

When version mismatch is detected, you should see:

```
⚠️ Version mismatch detected: Frontend 0.13.0, Backend 0.14.2
HvacFanCard: Version mismatch detected - stopping entity mapping retries
```

**NOT:**

```
HvacFanCard: Failed to load entity mappings: ...
HvacFanCard: Failed to load entity mappings: ...
HvacFanCard: Failed to load entity mappings: ...
(repeated many times)
```

## Troubleshooting

### Banner doesn't appear on HVAC Fan Card

- Check that `window.ramsesExtras._versionMismatch` is set (not just `version`)
- Trigger a re-render by interacting with the card or reloading the page
- Check console for errors in `_injectVersionBanner()`

### Banner appears multiple times

- This should not happen - the base card checks if banner already exists in DOM
- If it does, check for multiple `ha-card` elements or CSS selector issues

### WebSocket calls still work despite mismatch

- Check that `window.ramsesExtras._versionMismatch` is properly set
- Verify the call is not the initialization call (`ramses_extras/default/get_cards_enabled`)
- Check console for blocking messages

### Console spam continues

- Verify retry prevention is working in `_loadEntityMappings()` and `_checkAndLoadInitialState()`
- Check that `_entityMappingsLoadFailed` flag is being set
- Look for other code paths that might be retrying WebSocket calls
