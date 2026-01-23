# Getting Started (Users)

## Prerequisites

- Home Assistant installed and running.
- The `ramses_cc` integration installed and working (device communication).
- `ramses_extras` installed (typically via HACS or manual install).

## Ramses RF prerequisite: bound REM (for FAN-related features)

When using FAN-related features, make sure Ramses RF has the **bound** trait defined for your FAN.

Example:

```
"37:168270":
  class: REM
"32:153289":
  bound: "37:168270"
  class: FAN
```

## Enable Ramses Extras (UI)

1. Go to:
   - **Settings → Devices & Services**
2. Click:
   - **Add Integration**
3. Search for:
   - **Ramses Extras**
4. Select which features to enable.

## Verify it is working

- Check Home Assistant logs for `ramses_extras` startup messages.
- Confirm expected entities appear for enabled features.

## Lovelace cards

Some features provide custom Lovelace cards (JavaScript). Once the integration is set up and cards are deployed/registered, you can add cards through the Lovelace UI.

## Next

- Architecture overview: [Overview](Overview.md)
- Deeper: [Feature System](Feature-System.md)

Back to: [Home](Home.md)
