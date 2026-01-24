# Frontend Architecture

This page is derived from `docs/RAMSES_EXTRAS_ARCHITECTURE.md` section 9.

## JavaScript card system

Ramses Extras uses an **on-demand loading** architecture for Lovelace UI
components.

### Bootstrap loading (`main.js`)

Instead of registering every custom card as a separate Lovelace resource, the
integration registers a single **bootstrap resource** (`main.js`).

- `main.js` uses a `MutationObserver` to watch for Ramses Extras custom element
  tags appearing in the DOM.
- When a tag is detected, it uses dynamic `import()` to load the corresponding
  card module from its (versioned) deployment path.

Result: dashboards only download the cards they actually use.

### Base card pattern (`RamsesBaseCard`)

All Ramses Extras cards extend:

- Source: `custom_components/ramses_extras/framework/www/ramses-base-card.js`
- Deployed: `/local/ramses_extras/v{version}/helpers/ramses-base-card.js`

The base card centralizes:

- lifecycle (`connectedCallback()` / `disconnectedCallback()`)
- gating/validation and shared UX states
- a consistent "subclass implements `_renderContent()`" pattern

### Feature enablement and startup latches

Cards are gated by two backend-driven readiness mechanisms:

- `enabled_features`
  - loaded via WebSocket (`ramses_extras/default/get_enabled_features`)
  - exposed at runtime as `window.ramsesExtras.features`
  - used by `RamsesBaseCard.isFeatureEnabled()`
- `cards_enabled`
  - loaded via WebSocket (`ramses_extras/default/get_cards_enabled`)
  - prevents cards from rendering before backend startup completes

### Option updates (live frontend refresh)

When the config entry options change, Ramses Extras fires a HA event
`ramses_extras_options_updated`. The base card subscribes to this event and
updates runtime globals such as:

- `window.ramsesExtras.features`
- `window.ramsesExtras.debug`
- `window.ramsesExtras.frontendLogLevel`
- `window.ramsesExtras.logLevel`
- `window.ramsesExtras.cardsEnabled`

All card instances re-render after an update so feature-disabled placeholders
appear/disappear immediately.

### Deployment & versioning

To avoid stale browser caches, static assets are deployed to a versioned path:

`/config/www/ramses_extras/v{version}/...`

Only one Lovelace resource is registered:

- URL: `/local/ramses_extras/v{version}/helpers/main.js`
- Type: `module`

### Theme-adaptive styling

Cards and editors should use Home Assistant theme variables (e.g.
`--primary-text-color`, `--ha-card-background`) so they render correctly across
themes.

### Visual editor registration requirements

To support HA’s visual editor, each card must provide:

- `static getConfigElement()`
- `static getStubConfig()`

And ensure the editor web component is registered exactly once.

## Real-time message system

For cards that need real-time device state (e.g. HVAC), the frontend uses a
message broker approach:

`31DA message -> RamsesMessageBroker -> handler -> card update`

Cards typically register listeners in `connectedCallback()` and implement
message handlers like `handle_31DA()`.

## Translation system

Translations are feature-centric:

- Integration translations: `custom_components/ramses_extras/translations/`
- Feature translations: `custom_components/ramses_extras/features/{feature}/www/{feature}/translations/`

## Template systems

Frontend cards may use a template system under:

`custom_components/ramses_extras/features/{feature}/www/{feature}/templates/`

Feature `const.py` is intended to be the "source of truth" for entity mappings
and template metadata so frontend and backend can stay aligned.

## Entity resolution in cards

Cards treat `hass.states` as the source of truth and derive entity IDs via a
feature-centric mapping layer.

The base card exposes `getRequiredEntities()`, which loads entity mappings via
WebSocket (`ramses_extras/get_entity_mappings`) using:

- `device_id`
- `feature_id`

Results are cached per card instance to avoid repeated WebSocket calls.

## Contents

- JavaScript card system
- Real-time message system
- Translation system
- Template systems
- Entity resolution in cards

Back to: [Home](Home.md)
Prev: [Home Assistant Integration](Home-Assistant-Integration.md)
Next: [Development Guide](Development-Guide.md)
