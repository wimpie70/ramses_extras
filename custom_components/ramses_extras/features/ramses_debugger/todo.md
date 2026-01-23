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

## Ramses debugger improvements

### 1) Shared backend cache (avoid duplicated work across multiple cards)
- [x] Add a cache object under `hass.data[DOMAIN]["ramses_debugger"]` (e.g. `debugger_cache`)
- [x] Cache keys must include:
  - request type (tail/search/traffic-stats/messages)
  - file_id + configured base path + file mtime/size (avoid stale results)
  - all request params (e.g. `offset_lines`, `max_lines`, `query`, `before/after`, filters)
- [x] Add a short TTL for expensive operations (e.g. 0.5–2s) to dedupe polling bursts
- [x] Add max cache entries + eviction policy (LRU-ish or oldest-first)
- [x] Ensure cache never merges results across different ranges (e.g. two Log Explorers with different offsets)
- [x] Add a debug WebSocket endpoint for cache stats (+ optional reset)

### 2) Log source improvements (tail/search)
- [ ] Consolidate duplicated file resolution logic into a single backend helper
- [ ] Ensure allowlisting prevents reading outside the configured base directory
- [ ] Consider incremental tail (only read new bytes) as a later optimization (optional)

### 3) Traffic collector: cap flows + explain what a flow is
- [ ] Define "flow": a unique `(src, dst)` pair observed in `ramses_cc_message` events
- [ ] Add configurable caps:
  - max flows (unique `(src, dst)` pairs)
  - max global message buffer (for message browsing)
  - max messages per flow
- [ ] Eviction policy for flows when max is reached (drop oldest by last_seen/first_seen)

### 4) Config flow (Advanced settings)
- [ ] Add debugger options:
  - debugger cache TTL (ms)
  - debugger cache max entries
  - traffic flow cap
  - traffic buffer sizes (global + per-flow)
  - default polling interval (ms) for debugger cards
- [ ] Add UI copy/help text explaining:
  - what a flow is
  - why caching exists (multi-card pages)
  - trade-offs of lower/higher polling intervals

### 5) Frontend: reduce redundant polling across multiple instances
- [ ] Use a shared per-feature JS cache (e.g. `window.ramsesExtras.ramsesDebugger`) for:
  - last results per request key
  - in-flight requests per request key (promise de-dup)
- [ ] Make polling interval consistent across cards by default:
  - read from config-flow options via the existing `ramses_extras_options_updated` mechanism
  - allow per-card override only when explicitly set
- [ ] Ensure multiple Log Explorers with different offsets do not block each other

### 6) Documentation
- [ ] Add Sphinx-style docstrings to the main backend modules:
  - [traffic_collector.py](cci:7://file:///home/willem/dev/ramses_extras/custom_components/ramses_extras/features/ramses_debugger/traffic_collector.py:0:0-0:0)
  - [messages_provider.py](cci:7://file:///home/willem/dev/ramses_extras/custom_components/ramses_extras/features/ramses_debugger/messages_provider.py:0:0-0:0)
  - [log_backend.py](cci:7://file:///home/willem/dev/ramses_extras/custom_components/ramses_extras/features/ramses_debugger/log_backend.py:0:0-0:0)
  - [websocket_commands.py](cci:7://file:///home/willem/dev/ramses_extras/custom_components/ramses_extras/features/ramses_debugger/websocket_commands.py:0:0-0:0)
- [ ] Document cache invariants (keys include file state + request params)

### 7) Tests / validation
- [ ] Add/adjust unit tests for:
  - cache keying and TTL behavior
  - file resolution allowlisting
  - flow eviction behavior
- [ ] Run focused pytest for debugger feature
- [ ] Run `make local-ci` for final validation


## Acceptance criteria
- With ramses_cc message events enabled, Traffic Analyser shows live counts changing
- Log Explorer can filter HA logs and return ±N context around matches
- Log Explorer output is easy to copy/paste (plain + markdown)
- Zoom dialogs work for both cards
- Reset clears Traffic Analyser stats immediately
 - Traffic Analyser shows codes and verbs counters per flow
 - Traffic Analyser can open Log Explorer via action button
 - Message listing (when implemented) allows drilling down to raw + parsed message details
