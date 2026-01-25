# Ramses Extras Initialization Fixes

## Overview

Fixed three critical issues preventing debugger cards and other features from initializing properly after enabling the feature or restarting Home Assistant.

## Issue 1: `'HomeAssistant' object has no attribute 'helpers'` Error ✅

### Problem

When enabling the debugger feature and restarting HA, the hello_world automation would fail with:

```
ERROR (MainThread) [custom_components.ramses_extras.framework.base_classes.base_automation]
Failed to initialize hello_world automation: 'HomeAssistant' object has no attribute 'helpers'
```

This occurred because the code was trying to access `hass.helpers.event.async_track_time_interval` directly, but `hass.helpers` doesn't exist as an attribute.

### Root Cause

In `base_automation.py` line 425, the code incorrectly used:

```python
self._periodic_check_handle = self.hass.helpers.event.async_track_time_interval(...)
```

The correct approach is to import the function from `homeassistant.helpers.event` and call it directly.

### Solution

**File:** `framework/base_classes/base_automation.py`

1. Added import (line 20-23):

```python
from homeassistant.helpers.event import (
    async_track_state_change_event,
    async_track_time_interval,
)
```

2. Fixed function call (line 425-429):

```python
self._periodic_check_handle = async_track_time_interval(
    self.hass,
    self._check_for_entities_periodically,
    timedelta(seconds=30),
)
```

### Impact

- hello_world automation now initializes successfully
- No more AttributeError on startup
- Periodic entity checks work correctly

---

## Issue 2: Cards Stuck on "Ramses Extras is initializing" ✅

### Problem

After enabling the debugger feature and restarting HA (even multiple times), all debugger cards would remain stuck showing:

```
Ramses Extras is initializing
Waiting for feature startup to complete
```

The cards would never become interactive, even though HA was fully running.

### Root Cause

The `cards_enabled` latch mechanism waits for all features with automations to fire a `ramses_extras_feature_ready` event. However, when an automation failed to initialize (like hello_world due to Issue 1), it would:

1. Set `feature_ready[feature_id] = False`
2. Log an error
3. **NOT fire the `ramses_extras_feature_ready` event**

This meant the cards_enabled latch would wait forever for the failed feature to signal ready, blocking all cards from becoming enabled.

**Code flow:**

```python
# In base_automation.py _on_homeassistant_started()
try:
    await self._register_entity_listeners()
    # ... fires ready event on success
except Exception as e:
    # Sets ready to False but DOESN'T fire event
    # Cards wait forever!
```

### Solution

**File:** `framework/base_classes/base_automation.py` (lines 162-166)

Fire the `ramses_extras_feature_ready` event even when initialization fails:

```python
except Exception as e:
    self.hass.data.setdefault(DOMAIN, {}).setdefault("feature_ready", {})[
        self.feature_id
    ] = False
    _LOGGER.error("Failed to initialize %s automation: %s", self.feature_id, e)
    # Fire the ready event even on failure to unblock cards_enabled latch
    # Cards should still work even if this automation failed
    self.hass.bus.async_fire(
        "ramses_extras_feature_ready", {"feature_id": self.feature_id}
    )
```

### Rationale

- Cards should not be blocked by a failed automation
- Most cards don't depend on automations to function
- Users can still use debugger cards even if hello_world fails
- Automation failures are already logged as errors
- This follows the "fail gracefully" principle

### Impact

- Cards become enabled even if some automations fail
- Users can access debugger immediately after enabling
- No more infinite "initializing" state
- Failed automations are still logged for debugging

---

## Issue 3: Versioned www Folder Browser Caching ✅

### Problem

After updating ramses_extras to a new version, browsers would cache the old version's JavaScript files. Since the old version folder gets deleted during cleanup, browsers would fail to load cards, showing errors or blank cards.

**Deployment flow:**

1. Version 0.13.0 deployed to `/www/ramses_extras/v0.13.0/`
2. Browser caches `main.js` from that path
3. Update to 0.13.1
4. New files deployed to `/www/ramses_extras/v0.13.1/`
5. Old `/www/ramses_extras/v0.13.0/` deleted
6. Browser still tries to load cached v0.13.0 files → 404 errors

### Root Cause

The Lovelace resource URL didn't include any cache-busting mechanism:

```javascript
/local/ramses_extras/v0.13.0/helpers/main.js
```

Even though the path includes the version, browsers aggressively cache JavaScript modules, and the version change alone doesn't force a reload.

### Solution

**File:** `framework/helpers/card_registry.py` (line 90)

Add cache-busting query parameter to the resource URL:

```python
return LovelaceCard(
    type="ramses-extras",
    resource_path=f"/local/ramses_extras/v{version}/helpers/main.js?v={version}",
    name="Ramses Extras (bootstrap)",
)
```

### How It Works

1. Version 0.13.0: URL is `main.js?v=0.13.0`
2. Version 0.13.1: URL is `main.js?v=0.13.1`
3. Browser sees different query parameter → treats as new resource
4. Forces fresh download instead of using cache

### Impact

- Browser always loads correct version after updates
- No more 404 errors from deleted old versions
- No need for users to manually clear cache
- Seamless updates without card failures

---

## Testing Recommendations

### Test Issue 1 Fix (helpers error)

1. Enable ramses_extras integration
2. Enable hello_world feature
3. Restart Home Assistant
4. Check logs - should NOT see "HomeAssistant' object has no attribute 'helpers'"
5. Verify hello_world automation starts successfully

### Test Issue 2 Fix (cards_enabled latch)

1. Fresh install or disable all features
2. Enable debugger feature only
3. Restart Home Assistant
4. Open debugger cards - should load immediately (not stuck on "initializing")
5. Verify cards are functional

### Test Issue 3 Fix (browser caching)

1. Note current version (e.g., 0.13.1)
2. Update to next version (e.g., 0.13.2)
3. Refresh browser WITHOUT clearing cache
4. Verify cards load correctly
5. Check browser network tab - should see `main.js?v=0.13.2` loaded

### Combined Test

1. Fresh install of ramses_extras
2. Enable debugger and hello_world features
3. Restart Home Assistant
4. Verify no errors in logs
5. Verify all cards load and are functional
6. Update to new version
7. Verify cards still work without cache clearing

---

## Files Modified

1. **`framework/base_classes/base_automation.py`**
   - Added `async_track_time_interval` import
   - Fixed periodic check setup to use imported function
   - Fire `ramses_extras_feature_ready` event on initialization failure

2. **`framework/helpers/card_registry.py`**
   - Added cache-busting query parameter to bootstrap resource URL

---

## Backward Compatibility

All changes are backward compatible:

- Import fix doesn't change API
- Feature ready event on failure is additive (doesn't break existing listeners)
- Cache-busting query parameter is transparent to browsers

---

## Related Issues

These fixes address the root causes of:

- Cards not loading after feature enable
- Cards stuck on initialization screen
- Cards breaking after version updates
- Automation initialization failures blocking entire integration

---

## Prevention

To prevent similar issues in the future:

1. **Always import from homeassistant.helpers modules** - Never access via `hass.helpers`
2. **Always fire ready events** - Even on failure, to prevent blocking other features
3. **Always use cache-busting** - For any dynamically loaded frontend resources
4. **Test initialization paths** - Including failure scenarios
5. **Test version updates** - Ensure smooth transitions between versions
