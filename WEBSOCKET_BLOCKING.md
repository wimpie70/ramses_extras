# WebSocket Blocking on Version Mismatch

## Overview

When a version mismatch is detected between frontend and backend, all WebSocket calls are now **blocked** to prevent compatibility issues.

## Implementation

### Changes to `card-services.js`

Added version mismatch check at the start of `callWebSocket()`:

```javascript
export async function callWebSocket(hass, message) {
  return new Promise((resolve, reject) => {
    // Allow initialization-related calls to bypass version mismatch check
    const isInitializationCall = message?.type === 'ramses_extras/default/get_cards_enabled';

    // Block WebSocket calls if there's a version mismatch (except initialization)
    if (window.ramsesExtras?._versionMismatch && !isInitializationCall) {
      const mismatch = window.ramsesExtras._versionMismatch;
      reject({
        version_mismatch: true,
        code: 'version_mismatch',
        message: `Version mismatch detected (Frontend: ${mismatch.frontend}, Backend: ${mismatch.backend}). Please hard refresh your browser.`,
        frontend: mismatch.frontend,
        backend: mismatch.backend,
      });
      return;
    }

    // ... rest of WebSocket call
  });
}
```

### Affected Functions

1. **`callWebSocket(hass, message)`** - Directly checks for mismatch
2. **`callWebSocketShared(hass, message, options)`** - Inherits check via `callWebSocket()`

Both functions will reject with a `version_mismatch` error when versions don't match.

### Bypass for Initialization

The `ramses_extras/default/get_cards_enabled` WebSocket call is **allowed to bypass** the version mismatch check. This is necessary to:

- Allow the "Home Assistant is initializing" banner to appear correctly
- Detect when cards are enabled/disabled
- Ensure proper initialization flow even with version mismatch

All other WebSocket calls are blocked when there's a version mismatch.

## Behavior

### When Version Mismatch Detected:

1. **Orange banner appears** on all cards (auto-injected by base card)
2. **All WebSocket calls are blocked** immediately
3. **Error is returned** with clear message:
   ```javascript
   {
     version_mismatch: true,
     code: 'version_mismatch',
     message: 'Version mismatch detected (Frontend: 0.13.7, Backend: 0.13.9). Please hard refresh your browser.',
     frontend: '0.13.7',
     backend: '0.13.9'
   }
   ```

### User Experience:

- Cards will show the orange banner with "Hard Refresh" button
- Cards won't be able to fetch new data (WebSocket calls blocked)
- Existing cached data may still be displayed
- User must hard refresh (Ctrl+Shift+R) to resolve

## Benefits

1. **Prevents incompatibility issues** - Mismatched frontend/backend can cause errors
2. **Forces user action** - User must refresh to continue using cards
3. **Clear messaging** - Banner explains what's wrong and how to fix it
4. **Fail-safe behavior** - Better to block than to allow potentially broken functionality

## Error Handling in Cards

Cards should handle the `version_mismatch` error gracefully:

```javascript
try {
  const result = await callWebSocket(hass, message);
  // Process result
} catch (error) {
  if (error.version_mismatch) {
    // Version mismatch - banner is already shown
    // Card can display cached data or show placeholder
    return;
  }
  // Handle other errors
}
```

## Testing

1. Deploy backend with version 0.13.9
2. Keep frontend cached at 0.13.7 (don't hard refresh)
3. Open any card
4. Observe:
   - Orange banner appears
   - WebSocket calls are blocked
   - Console shows version mismatch error
5. Click "Hard Refresh" button
6. Observe:
   - Banner disappears
   - WebSocket calls work normally

## Deployment

```bash
make install
docker restart hass
```

Then test by:

1. Loading cards with old cached frontend
2. Verifying banner appears and WS calls are blocked
3. Hard refreshing to resolve
