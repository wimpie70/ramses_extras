# Ramses Debugger (Ramses Extras Feature) - TODO

## Goal
Provide fast, structured debugging tools for ramses_cc / ramses_rf by combining:
- traffic analysis (who talks to who, how often)
- log exploration (filter + context extraction, easy to copy/paste)

This feature provides multiple Lovelace cards:
- Traffic Analyser (spreadsheet-like comms matrix)
- Log Explorer (filter HA log file with context extraction)
- Future: Packet Log Explorer (parse ramses packet/message log)

## Data sources (authoritative)
### Traffic Analyser
- Home Assistant event: `ramses_cc_message` (enabled via ramses_cc advanced feature `message_events`)
  - fields: dtm, src, dst, verb, code, payload, packet
- Optional event: `ramses_cc.fan_param_updated`

### Log Explorer
- Home Assistant log file path (e.g. `home-assistant.log`)
- Optional: rotated log file selection (e.g. `home-assistant.log.1`)

### Future: Packet Log Explorer
- packet/message log file path (e.g. `ramses_log`)

## MVP requirements
### Traffic Analyser card
- Collect `ramses_cc_message` events
- Maintain in-memory aggregates:
  - totals, counts by (src,dst), counts by code, counts by verb
  - last_seen timestamps
- Expose stats via WebSocket command(s)
- Provide Lovelace card:
  - sortable/filterable table
  - zoom mode (fullscreen dialog)
  - reset button

### Log Explorer card
- Read HA log file on-demand (no in-memory retention required)
- Provide filters:
  - logger name/namespace (string contains, e.g. `[ramses_tx.transport]`)
  - level (ERROR/WARNING/INFO/DEBUG)
  - include/exclude text (literal)
  - time window (last N minutes) OR tail window (last N lines)
  - context extraction: ±N lines around matches (merge overlaps)
  - block extraction for tracebacks (optional in MVP, but high value)
- Output formatting:
  - return results as plain text
  - return results as a Markdown code block (easy to paste into issues/LLMs)
- Provide Lovelace card:
  - filter controls + results panel
  - zoom mode (fullscreen dialog)
  - copy-to-clipboard button

### Cross-filtering (Traffic -> Logs)
- Clicking a Traffic Analyser row can pre-fill Log Explorer filters:
  - include device ids (src/dst)
  - optionally include top code(s)

## Non-goals (for MVP)
- RSSI/signal strength (unless reliably available)
- Persistent storage of Traffic Analyser statistics
- Full text indexing of log files (start with streaming scan / tail)

## Backend design
### Configuration (config flow)
- HA log file path -> we may get this from ha configuration ?
- Future: packet log file path -> we can get this from ramses_cc configuration

Notes:
- Support choosing a rotated log file from the card (e.g. current vs previous)
- Optionally allow overriding the log path via config flow options

### Traffic collector
- Lives in `hass.data[DOMAIN]["ramses_debugger"]["traffic_analyser"]`
- Subscribes to `hass.bus.async_listen("ramses_cc_message", handler)`

### Traffic aggregation model
- key: `(src, dst)`
  - count_total
  - last_seen
  - verbs_counter
  - codes_counter
- global totals:
  - total_count
  - by_code counter
  - by_verb counter

### Log Explorer implementation approach
- WebSocket command receives filter request
- Filter block: starting time-end time
- Backend reads log file on-demand and returns:
  - context blocks (merged)
  - rendered plain text + markdown

No retention is required; the backend can always re-read the file.

## WebSocket API
### Traffic Analyser
- `ramses_extras/ramses_debugger/traffic/get_stats`
  - params: filters (src/dst/code/verb), window (since_reset / last_N_minutes), limit
- `ramses_extras/ramses_debugger/traffic/reset_stats`
- optional: `ramses_extras/ramses_debugger/traffic/export_stats` (csv/json)

### Log Explorer
- `ramses_extras/ramses_debugger/log/list_files`
  - returns: available log files (current + rotated, based on configured path)
- `ramses_extras/ramses_debugger/log/get_tail`
  - params: file_id, max_lines, max_chars
- `ramses_extras/ramses_debugger/log/search`
  - params:
    - file_id
    - include (string)
    - exclude (string)
    - level (optional)
    - logger (optional)
    - since_minutes (optional)
    - tail_lines (optional)
    - max_matches
    - context_lines
    - include_tracebacks (bool)
  - returns:
    - blocks (with start/end line numbers)
    - text_plain
    - text_markdown

## Frontend card design
### Traffic Analyser
- Table view similar to spreadsheet:
  - Sender ID, Addressee ID, Frequency, FREQ%, Top Verbs, Top Codes, Last Seen
- Filtering controls
- Row click -> zoom dialog with breakdown
- Cross-link: open Log Explorer with prefilled filters

### Log Explorer
- Filter controls:
  - file selector (current / previous)
  - logger filter
  - level filter
  - include/exclude text
  - time or tail window
  - context lines (±N)
- Results pane:
  - wrap/nowrap toggle for long lines
  - copy-as-markdown button
- Zoom dialog mode

### Future: Packet Log Explorer
- Parse/visualize raw packets from `ramses_log`
- Filter by src/dst/code/verb and correlate with Traffic Analyser

## Workflow recipe (testable, incremental commits)
Each larger step should result in a commit that is:
- small enough to review
- testable (unit tests and/or a simple live check)
- keeps CI green

Suggested workflow per step:
- implement
- add/adjust tests
- run the next tests depending on what was changed (py/.js...)
- run a focused local test
- run a pytest . to check if other tests don't fail
- run mypy . ruff format --check, ruff check (--fix)
- run .js linter tests
- run `pre-commit run -a`  and/or `make local-ci` when the change is bigger or touches multiple areas
- commit

## Ramses debugger issues

### FIXED: Cards losing focus/content on re-render
- **Root cause**: Cards were overriding `render()` and calling `super.render()`, which triggered full DOM replacement via `innerHTML` in `_renderContent()`, destroying scroll positions before restoration could happen
- **Solution**:
  - Removed `render()` overrides from all debugger cards (Log Explorer, Packet Log Explorer, Traffic Analyser)
  - Wrapped `_renderContent()` to call `_preserveUIState()` before and `_restoreUIState()` after the actual rendering logic (now in `_renderContentImpl()`)
  - This ensures state preservation happens at the right time in the render cycle
- **Cards updated**:
  - `ramses-log-explorer.js`: Preserves scroll for `tailPre` and `resultPre`
  - `ramses-packet-log-explorer.js`: Preserves scroll for `fileSelect`, `loadMode`, `limitFilter`
  - `ramses-traffic-analyser.js`: Preserves scroll for table wrapper and handles dialog state

### FIXED: WebSocket connection loss and no reconnection
- **Root cause**: When WebSocket connection was lost and restored, cards didn't re-fetch their data because `_onConnected()` was only called during initial DOM connection, not on reconnection
- **Solution**:
  - Modified `ramses-base-card.js` `set hass()` method to call `_onConnected()` when connection is restored
  - Added reconnection logic in both the 'ready' event handler and timeout fallback path
  - Cards now automatically re-fetch data when WebSocket connection is restored
- **Affected cards**: All debugger cards (Log Explorer, Packet Log Explorer, Traffic Analyser) now properly reconnect and refresh data
But we still have problems that after some time HA is no longer responding. I have upgraded HA and disabled _extras. I no longer saw this disconnect so far, but i then went to a dashboard with still a card installed and get:message: "Unknown command.", original: {…} }
logger.js:56:35
Sending
Object { type: "ramses_extras/default/get_cards_enabled" }
connection-mixin.ts:184:21
Error
Object { code: "unknown_command", message: "Unknown command." }
connection-mixin.ts:194:32
Sending
Object { type: "ramses_extras/default/get_cards_enabled" }
connection-mixin.ts:184:21
Error
Object { code: "unknown_command", message: "Unknown command." }
connection-mixin.ts:194:32
Sending
Object { type: "ramses_extras/default/get_cards_enabled" }
connection-mixin.ts:184:21
Error
Object { code: "unknown_command", message: "Unknown command." }
connection-mixin.ts:194:32
Sending
Object { type: "ramses_extras/default/get_cards_enabled" }
connection-mixin.ts:184:21
Error
Object { code: "unknown_command", message: "Unknown command." }
connection-mixin.ts:194:32
Sending
Object { type: "ramses_extras/default/get_cards_enabled" }
connection-mixin.ts:184:21
Error
Object { code: "unknown_command", message: "Unknown command." }
connection-mixin.ts:194:32
Sending
Object { type: "ramses_extras/default/get_cards_enabled" }
connection-mixin.ts:184:21

We should prevent this for happening too often (may cause problems)
Also I suspect we have created some kind of loop causing HA to freeze.

--- update: I did install the latest version of HA and the problem with HA becoming unavailable seems gone.


Log Explorer
- move zoom button from search header to search result blocks.
- when hitting zoom button, open dialog, with possibility to load more of the logs (arrow up -> add 50 msgs extra before search result, arrow down -> add 50 msgs extra after search result (like we do with the other log +50 lines up/down, but now we add extra lines (enlarge the block))) Now we don't see enough eg. on a long traceback

Upgrade to new _extras:
Cards cannot find the correct version. (www deployed to new version folder, but still looking for the old one)

Still problem with scroll position/focus
Here's what I found:
Yes, focus loss and scrolling "jumps" during card re-renders are known issues in Home Assistant, often stemming from how the underlying
LitElement framework and dashboard layout engine handle updates.
1. Focus Loss on Re-render
Focus loss typically occurs if the entire card or a specific input field is completely replaced in the DOM rather than being patched.

    Sub-component Re-creation: If your code re-creates a sub-component inside a render() function rather than updating its properties, the element unmounts and remounts. This causes the browser to lose the focused state as the original element no longer exists.
    Editor Glitches: Some custom cards, like the HACS Expander Card, have reported "redraw loops" in the editor UI that can flush your changes every few seconds if you aren't using the YAML mode.

1. Scrolling "Jumping" and Resetting
Scrolling issues are frequently reported, particularly when cards change size or visibility dynamically.

    Layout Reflows: When a card re-renders and momentarily has a different height (e.g., while waiting for data), the browser may correct the scroll position to the "intermediate" height, causing the page to "jump".
    Conditional Card Flashing: Using Conditional Cards can sometimes cause the entire dashboard to reload or "flash" when an entity appears or disappears, which disrupts the scroll position and state of other elements like camera streams.
    Nested Card Issues: Specific combinations, such as nesting the Windrose Card inside a Bubble Card pop-up, have been known to cause "endless scrolling" or scrollbars that jump to the bottom of the page when an action is performed.

1. Touch & Mobile Glitches
On mobile devices, scrolling can be particularly finicky due to touch interactions.

    Accidental Triggers: Users often report accidentally triggering switches or buttons while trying to scroll.
    Scroll Invisibility: In some recent updates (like 2024.7 beta), certain CSS mods for scrolling and max-height ceased to function, leading to cards that would no longer scroll as expected.

Best Practices to Prevent These Issues:

    Use display: none instead of if/else: If you are building a card, use CSS to hide elements instead of removing them from the DOM to keep their state and position "warmed up".
    Stabilize Container Height: Set a min-height on your card or its containers to prevent the layout from collapsing and jumping during data updates.
    Leverage Card-Mod: If you encounter scroll-blocking, the community often uses the Lovelace Card-Mod to explicitly force overflow: scroll or other layout fixes.

## Acceptance criteria
- With ramses_cc message events enabled, Traffic Analyser shows live counts changing
- Log Explorer can filter HA logs and return ±N context around matches
- Log Explorer output is easy to copy/paste (plain + markdown)
- Zoom dialogs work for both cards
- Reset clears Traffic Analyser stats immediately
 - Traffic Analyser shows codes and verbs counters per flow
 - Traffic Analyser can open Log Explorer via action button
 - Message listing (when implemented) allows drilling down to raw + parsed message details
