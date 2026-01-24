# Debugging and Troubleshooting

This page is derived from `docs/RAMSES_EXTRAS_ARCHITECTURE.md` section 11.

This page collects common issues, debugging tools, and configuration tips.

## Common issues and solutions

### Feature not loading

Symptoms:

- Feature doesn't appear in HA configuration options.

Things to check:

- `AVAILABLE_FEATURES` registration in `const.py`
- feature factory function exists and imports correctly
- HA logs for import/initialization errors
- feature folder structure is correct

### Entities not created

Symptoms:

- Feature is enabled but no entities appear.

Things to check:

- feature enabled + device selected in the options flow
- `SimpleEntityManager` logs for entity creation/removal issues
- device discovery is working

### JavaScript cards not loading

Symptoms:

- Card doesn’t appear, or you see errors in the UI.

Things to check:

- asset deployment completed successfully
- files exist under `config/www/ramses_extras/` (versioned path)
- browser console for JS errors
- feature is UI-enabled
- hard refresh your browser cache

### WebSocket command failures

Symptoms:

- WebSocket commands return errors or time out.

Things to check:

- command handler is registered during setup
- required parameters are present and valid
- `device_id` exists and is formatted correctly
- HA logs for WebSocket-related errors

### Performance issues

Symptoms:

- Slow entity changes, high memory usage, laggy UI.

Things to try:

- use bulk operations for entity changes where supported
- cache frequently accessed data
- reduce UI update frequency where appropriate

## Debug tools

### SimpleEntityManager

- Use validation on startup to troubleshoot missing/extra entities.
- Inspect logs around entity creation/removal.
- Confirm the device feature matrix state is what you expect.

### WebSocket testing

- Use `callWebSocket()` in browser console to test commands.

### Message listener debug

- Inspect registered listeners via `RamsesMessageBroker` helper methods.

### RamsesBaseCard debug logging

Frontend debug output can be enabled via:

```javascript
window.ramsesExtras = window.ramsesExtras || {};
window.ramsesExtras.debug = true;
```

This flag is normally driven by integration options and pushed via the
`ramses_extras_options_updated` event.

## Working debug tool examples

### SimpleEntityManager validation (Python)

```python
entity_manager = SimpleEntityManager(hass)
await entity_manager.validate_entities_on_startup()
```

### WebSocket testing (browser console)

```javascript
const result = await callWebSocket(hass, {
  type: 'ramses_extras/default/get_bound_rem',
  device_id: '32:153289'
});
console.log(result);
```

## Debug configuration

### Logging configuration

Home Assistant logging is the authoritative way to get backend debug output.

```yaml
logger:
  default: info
  logs:
    custom_components.ramses_extras: debug
    custom_components.ramses_extras.framework: debug
    custom_components.ramses_extras.features: debug
```

### Integration options

The options flow exposes settings that affect backend + frontend debugging:

- `frontend_log_level` controls browser console verbosity
- `log_level` adjusts runtime integration log level
- `debug_mode` exists for legacy compatibility and is derived from
  `frontend_log_level == "debug"`

## Contents

- Common issues and solutions
- Debug tools
- Working debug tool examples
- Debug configuration

Back to: [Home](Home.md)
Prev: [Development Guide](Development-Guide.md)
Next: [API Reference](API-Reference.md)
