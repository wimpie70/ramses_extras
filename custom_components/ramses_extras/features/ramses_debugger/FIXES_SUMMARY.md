# Ramses Debugger Fixes Summary

## Overview

Fixed three critical issues in the Ramses Debugger feature that were affecting user experience across all debugger cards.

## Issue 1: Cards Losing Focus/Content on Re-render ✅

### Problem
When debugger cards re-rendered (which happens frequently with live data), users would lose:
- Input focus (cursor position in search boxes)
- Text selection
- Scroll positions
- Search results would sometimes be cleared

This made the debugger cards frustrating to use, especially when typing queries or reviewing results.

### Solution
Added reusable UI state preservation helpers to the base card class that all cards can use:

**New Base Card Methods:**
- `_preserveUIState(scrollElementIds)` - Captures focus, selection, and scroll positions before render
- `_restoreUIState(state)` - Restores captured state after render

**Updated Cards:**
1. **Log Explorer** - Simplified to use new base card helpers (was using custom implementation)
2. **Traffic Analyser** - Added UI state preservation for table scroll and focus
3. **Packet Log Explorer** - Added UI state preservation for controls

**Files Modified:**
- `framework/www/ramses-base-card.js` - Added helper methods (lines 273-343)
- `features/ramses_debugger/www/ramses_debugger/ramses-log-explorer.js` - Simplified render method
- `features/ramses_debugger/www/ramses_debugger/ramses-traffic-analyser.js` - Added state preservation
- `features/ramses_debugger/www/ramses_debugger/ramses-packet-log-explorer.js` - Added state preservation

## Issue 2: Known Devices Only Filter ✅

### Problem
Debugger cards showed ALL messages including those from unknown/unregistered devices, making it hard to focus on devices actually configured in Home Assistant.

### Solution
Added "Known devices only" filter option to the messages viewer component:

**Features:**
- Checkbox toggle in messages viewer controls
- Filters messages to only show those where src OR dst is a known device
- Uses `ramses_extras/get_available_devices` WebSocket to fetch device list
- Cached device list to avoid repeated WebSocket calls
- Filter applies to Traffic Analyser and Packet Log Explorer (not Log Explorer, as requested)

**Implementation:**
- Added `_knownDevicesOnly` flag and `_knownDevices` Set to track state
- Added `_loadKnownDevices()` method to fetch devices via WebSocket
- Filter applied before pair grouping to ensure consistency
- Event listener toggles filter and triggers refresh

**Files Modified:**
- `features/ramses_debugger/www/ramses_debugger/ramses-messages-viewer.js`
  - Lines 49-50: Added state variables
  - Lines 78-80: Config handling
  - Lines 85-100: Load known devices method
  - Lines 110-113: Load devices on refresh if needed
  - Lines 254-262: Apply filter to messages
  - Lines 390-393: UI checkbox
  - Lines 542-548: Event listener

## Issue 3: Select All Toggles ✅

### Problem
When many device pairs or codes were present, users had to manually check/uncheck each one individually, which was tedious.

### Solution
Added "Select All" and "Deselect All" buttons for both device pairs and codes:

**Features:**
- Buttons appear above device pairs section with label "Device Pairs:"
- Buttons appear above codes section with label "Codes:"
- "Select All" checks all visible items
- "Deselect All" unchecks all items
- Buttons styled consistently with existing UI

**Implementation:**
- Added button elements in HTML template
- Event listeners set `_pairFilterTouched` / `_codeFilterTouched` flags
- Select All: Creates new Set with all available items
- Deselect All: Clears the Set
- Triggers re-render to update UI

**Files Modified:**
- `features/ramses_debugger/www/ramses_debugger/ramses-messages-viewer.js`
  - Lines 395-399: Device pairs buttons UI
  - Lines 415-419: Codes buttons UI
  - Lines 550-584: Event listeners for all four buttons

## Testing Recommendations

### Issue 1 (UI State Preservation)
1. Open Log Explorer and type a search query - cursor should stay in place during auto-refresh
2. Scroll through Traffic Analyser table - scroll position should be preserved on data updates
3. Select text in any card - selection should remain after re-render

### Issue 2 (Known Devices Filter)
1. Open Traffic Analyser or Packet Log Explorer
2. Check "Known devices only" checkbox
3. Verify only messages involving registered devices are shown
4. Uncheck - verify all messages reappear

### Issue 3 (Select All Toggles)
1. Open Traffic Analyser with multiple device pairs visible
2. Click "Select All" under Device Pairs - all should be checked
3. Click "Deselect All" - all should be unchecked
4. Repeat for Codes section

## Backward Compatibility

All changes are backward compatible:
- New base card methods are optional (cards work without calling them)
- Known devices filter defaults to OFF (existing behavior)
- Select all buttons are additive features

## Performance Impact

Minimal performance impact:
- UI state preservation: O(n) where n = number of scroll elements (typically 1-3)
- Known devices filter: Single WebSocket call cached for session
- Select all: O(n) where n = number of items, but only on button click

## Future Enhancements

Potential improvements for future consideration:
- Add select all for verbs (currently only pairs and codes)
- Persist filter preferences across sessions
- Add "invert selection" button
- Add keyboard shortcuts for select all/deselect all
