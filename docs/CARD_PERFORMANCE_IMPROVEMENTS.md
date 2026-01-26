# Card Performance and Stability Improvements

## Overview
This document describes three major improvements to the Ramses Extras card infrastructure to address excessive re-renders, version mismatch detection, and WebSocket call optimization.

## Problems Addressed

### 1. Excessive Re-renders Causing Input Disruption
**Problem**: Cards were re-rendering on every Home Assistant state change, making input fields unusable (search box would reset while typing). This was especially severe when multiple cards were installed on the same dashboard.

**Root Cause**: The `set hass()` method is called by HA on every state change. Even with throttling, cards would still render frequently, disrupting user input.

### 2. No Version Mismatch Detection
**Problem**: Users would load cached JavaScript from an old version after upgrading the integration, leading to confusing behavior with no indication that a hard refresh was needed.

**Root Cause**: No mechanism to compare frontend version (cached JS) with backend version (upgraded integration).

### 3. Excessive WebSocket Calls
**Problem**: Frequent re-renders triggered duplicate WebSocket calls, increasing backend load and causing performance degradation.

**Root Cause**: Short cache TTLs (0-500ms) and no request coalescing meant every render could trigger new backend requests.

## Solutions Implemented

### 1. Render Debouncing System

**Files Modified**:
- `custom_components/ramses_extras/framework/www/ramses-base-card.js`

**Changes**:
- Added `_scheduleRender(immediate)` method that debounces render calls by 100ms
- Replaced all direct `render()` calls with `_scheduleRender()` throughout base card
- Added render scheduling state tracking (`_renderScheduled`, `_renderDebounceTimer`)
- Enhanced `_restoreUIState()` to preserve input values across renders
- Immediate renders (`_scheduleRender(true)`) used only for critical updates (config changes, connection changes)

**Benefits**:
- Input fields remain stable during typing
- Multiple rapid state changes coalesce into single render
- Cursor position and selection preserved across renders
- Scroll positions maintained

**Example**:
```javascript
// Before: Direct render on every hass update
if (this.shouldUpdate()) {
  this.render();
}

// After: Debounced render
if (this.shouldUpdate()) {
  this._scheduleRender();
}
```

### 2. Version Mismatch Detection

**Files Modified**:
- `custom_components/ramses_extras/framework/helpers/websocket_base.py`
- `custom_components/ramses_extras/framework/www/card-services.js`
- `custom_components/ramses_extras/framework/www/version-banner.js` (new)
- `custom_components/ramses_extras/features/ramses_debugger/www/ramses_debugger/ramses-log-explorer.js`

**Backend Changes**:
- Modified `BaseWebSocketCommand._send_success()` to inject `_backend_version` into all WebSocket responses
- Version retrieved from `hass.data[DOMAIN]["_integration_version"]`

**Frontend Changes**:
- Added `_checkVersionMismatch()` in `card-services.js` to compare versions on every WS response
- Stores mismatch info in `window.ramsesExtras._versionMismatch`
- Logs warning to console when mismatch detected
- Created reusable `version-banner.js` component for displaying warnings
- Integrated banner into log explorer card (can be added to other cards)

**Banner Features**:
- Prominent orange warning banner
- Shows frontend vs backend version
- "Hard Refresh" button to reload with cache bypass
- Only shown once per session (not on every render)

**Example Response**:
```json
{
  "text": "log content...",
  "start_line": 1000,
  "end_line": 1200,
  "_backend_version": "0.12.1"
}
```

### 3. Enhanced WebSocket Caching

**Files Modified**:
- `custom_components/ramses_extras/framework/www/card-services.js`

**Changes**:
- Increased default cache TTL from 0ms to 2000ms (2 seconds)
- Increased cache size limit from 512 to 1024 entries
- Enhanced documentation explaining cache behavior
- Existing in-flight request deduplication maintained

**Benefits**:
- Rapid re-renders use cached data instead of hitting backend
- Multiple cards polling same endpoint share cached results
- Reduced backend load during dashboard navigation
- Memory-safe with automatic cache eviction

**Example**:
```javascript
// Before: No caching by default
await callWebSocketShared(hass, message, { cacheMs: 0 });

// After: 2-second cache by default
await callWebSocketShared(hass, message, { cacheMs: 2000 });

// Cards can override for specific needs
await callWebSocketShared(hass, message, { cacheMs: 500 }); // Shorter for real-time data
```

## Testing Recommendations

### 1. Test Render Debouncing
- Open log explorer card
- Start typing in search box
- Verify text remains stable and cursor doesn't jump
- Open multiple debugger cards on same dashboard
- Verify smooth typing experience

### 2. Test Version Detection
- Upgrade integration to new version
- Reload Home Assistant
- Open any debugger card without hard refresh
- Verify orange banner appears with version info
- Click "Hard Refresh" button
- Verify banner disappears after refresh

### 3. Test WebSocket Caching
- Open browser dev tools → Network tab
- Filter for WebSocket messages
- Open log explorer and navigate between files
- Verify reduced number of duplicate requests
- Open multiple cards polling same data
- Verify requests are shared (check timestamps)

## Performance Metrics

**Expected Improvements**:
- **Render frequency**: Reduced by ~90% during rapid state changes
- **Input responsiveness**: No dropped keystrokes or cursor jumps
- **WebSocket calls**: Reduced by ~60-80% for typical dashboard usage
- **Backend load**: Proportional reduction in log/search operations

## Migration Notes

**For Card Developers**:
- No breaking changes to card API
- Cards automatically benefit from debouncing
- To add version banner, import and call `getVersionMismatchBanner()` in render
- Existing `callWebSocketShared()` calls automatically use new defaults

**For Users**:
- No configuration changes required
- Hard refresh recommended after upgrade to see improvements immediately
- Version mismatch warnings help identify when refresh is needed

## Future Enhancements

**Potential Improvements**:
1. Add IntersectionObserver to skip renders for off-screen cards
2. Implement request batching for multiple simultaneous WS calls
3. Add configurable debounce timing per card type
4. Extend version banner to all card types automatically
5. Add telemetry to track render frequency and cache hit rates

## Related Files

**Core Infrastructure**:
- `framework/www/ramses-base-card.js` - Base card with debouncing
- `framework/www/card-services.js` - WebSocket utilities with caching
- `framework/www/version-banner.js` - Version mismatch UI component
- `framework/helpers/websocket_base.py` - Backend version injection

**Example Integration**:
- `features/ramses_debugger/www/ramses_debugger/ramses-log-explorer.js` - Log explorer with banner

## Changelog

**Version 0.12.1** (2026-01-26):
- ✅ Added render debouncing system (100ms)
- ✅ Implemented version mismatch detection
- ✅ Enhanced WebSocket caching (2s default TTL)
- ✅ Created reusable version banner component
- ✅ Integrated improvements into log explorer card
