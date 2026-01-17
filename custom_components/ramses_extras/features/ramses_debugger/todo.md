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
- HA log file path
- Future: packet log file path

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

## Milestones
- [ ] Update this TODO as requirements evolve
- [ ] Create feature skeleton based on hello_world (factory, const, websocket stubs, www stubs)
- [ ] Implement backend: traffic collector + in-memory stats
- [ ] Implement backend: log file search + context extraction
- [ ] Implement websocket commands + tests
- [ ] Implement cards: Traffic Analyser + Log Explorer + zoom dialogs
- [ ] Implement cross-filtering (Traffic -> Logs)
- [ ] Add reset/export UX
- [ ] CI: `make local-ci`

## Acceptance criteria
- With ramses_cc message events enabled, Traffic Analyser shows live counts changing
- Traffic filters work (src/dst/code/verb)
- Log Explorer can filter HA logs and return ±N context around matches
- Log Explorer output is easy to copy/paste (plain + markdown)
- Zoom dialogs work for both cards
- Reset clears Traffic Analyser stats immediately
