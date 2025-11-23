# HVAC Fan Card Path Fix

**Date**: 2025-11-23
**Issue**: 404 error when loading hvac-fan-card.js
**Error**: `GET http://localhost:8123/local/hvac_fan_card/hvac-fan-card.js [HTTP/1.1 404 Not Found]`

## Problem Analysis

The 404 error was caused by old/duplicate entries in the Home Assistant `lovelace_resources` storage file. The browser was trying to load the card from an old path instead of the correct new path.

### Old Paths (Incorrect)

- `/local/hvac_fan_card/hvac-fan-card.js`
- `/local/features/hvac_fan_card/hvac_fan_card/hvac-fan-card.js`
- `/local/community/ramses_extras/hvac_fan_card/hvac-fan-card.js`

### Correct Path (New Structure)

- `/local/ramses_extras/features/hvac_fan_card/hvac-fan-card.js`

## Root Cause

The `lovelace_resources` storage file (`/home/willem/docker_files/hass/config/.storage/lovelace_resources`) contained multiple entries for the hvac-fan-card from previous deployments. When Home Assistant loaded the card, it used the first matching entry, which was an old path that no longer existed.

## Solution

### 1. Automatic Cleanup (Code Fix)

Updated [`_register_lovelace_resources_storage()`](custom_components/ramses_extras/__init__.py:518) in `__init__.py` to automatically clean up old hvac-fan-card entries before registering the new one.

**Changes Made:**

- Added cleanup logic to remove old hvac-fan-card entries (lines 573-589)
- Old entries are identified by checking if they contain "hvac" but don't have the new `/ramses_extras/features/` structure
- Updated save condition to include when old entries are removed (line 600)

**Code Added:**

```python
# Clean up old hvac-fan-card entries before adding new ones
# This removes duplicate/old paths from previous deployments
cleaned_resources = []
removed_old_entries = []
for resource in existing_resources:
    url = resource.get("url", "")
    # Remove old hvac-fan-card entries (not in the new features/ structure)
    if "hvac" in url.lower() and "/ramses_extras/features/" not in url:
        removed_old_entries.append(url)
        _LOGGER.info(f"🗑️  Removing old hvac-fan-card entry: {url}")
    else:
        cleaned_resources.append(resource)

if removed_old_entries:
    _LOGGER.info(f"✅ Cleaned up {len(removed_old_entries)} old hvac-fan-card entries")
    existing_resources = cleaned_resources
    existing_card_urls = {
        resource["url"]
        for resource in existing_resources
        if resource.get("type") == "module"
    }
```

### 2. Manual Cleanup Script (Optional)

Created [`cleanup_lovelace_resources.py`](cleanup_lovelace_resources.py) for manual cleanup if needed.

**Usage:**

```bash
cd ramses_extras
sudo python3 cleanup_lovelace_resources.py
```

## Verification

After the fix, the integration will:

1. Automatically detect old hvac-fan-card entries on startup
2. Remove them from the lovelace_resources storage
3. Register only the correct path: `/local/ramses_extras/features/hvac_fan_card/hvac-fan-card.js`

### Files Are Correctly Deployed

The files are already correctly deployed to:

```
/home/willem/docker_files/hass/config/www/ramses_extras/features/hvac_fan_card/
├── hvac-fan-card.js
├── hvac-fan-card-editor.js
├── airflow-diagrams.js
├── card-styles.js
├── message-handlers.js
├── templates/
└── translations/
```

## Testing

To test the fix:

1. **Restart Home Assistant** to trigger the cleanup and re-registration
2. **Check the logs** for cleanup messages:
   - `🗑️  Removing old hvac-fan-card entry: ...`
   - `✅ Cleaned up X old hvac-fan-card entries`
3. **Verify in browser** that the card loads from the correct path
4. **Check lovelace_resources** to confirm only the correct entry exists:
   ```bash
   cat /home/willem/docker_files/hass/config/.storage/lovelace_resources | python3 -m json.tool | grep -A 3 "hvac"
   ```

## Expected Result

After restart, you should see only one hvac-fan-card entry in lovelace_resources:

```json
{
  "id": "hvac-fan-card",
  "url": "/local/ramses_extras/features/hvac_fan_card/hvac-fan-card.js",
  "type": "module"
}
```

And the browser should successfully load:

```
GET http://localhost:8123/local/ramses_extras/features/hvac_fan_card/hvac-fan-card.js [HTTP/1.1 200 OK]
```

## Architecture Compliance

This fix aligns with the target deployment structure documented in:

- [`docs/RAMSES_EXTRAS_ARCHITECTURE.md`](docs/RAMSES_EXTRAS_ARCHITECTURE.md) (lines 118-186)
- [`docs/JS_FEATURE_REORGANIZATION.md`](docs/JS_FEATURE_REORGANIZATION.md) (lines 74-104)

The correct structure is:

```
hass/config/www/ramses_extras/
├── helpers/                   # Shared utilities
│   └── [helper files]
└── features/                  # Feature-specific cards
    └── hvac_fan_card/         # Each feature gets its own folder
        └── [card files]
```

## Related Files

- [`custom_components/ramses_extras/__init__.py`](custom_components/ramses_extras/__init__.py) - Main integration file with cleanup logic
- [`custom_components/ramses_extras/framework/helpers/paths.py`](custom_components/ramses_extras/framework/helpers/paths.py) - Path constants
- [`cleanup_lovelace_resources.py`](cleanup_lovelace_resources.py) - Manual cleanup script
- [`docs/RAMSES_EXTRAS_ARCHITECTURE.md`](docs/RAMSES_EXTRAS_ARCHITECTURE.md) - Architecture documentation
- [`docs/JS_FEATURE_REORGANIZATION.md`](docs/JS_FEATURE_REORGANIZATION.md) - Reorganization plan
