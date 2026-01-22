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

### All cards/dialogs:
- [x] selective re-render...when something changes we loose focus/position on where we were and scroll back to the top. This is for all cards/popups.
- [x] we cannot select text from the results, we need this for copy/paste. Is there a z-index problem ? This goes for all cards/popups
- [ ] we don't have the maximum width for the cards. Should we set base-column-count to 1 ? or adapt column-size ?


### Traffic analyzer
- [x] what is the source of the traffic, can we choose between a ha logfile, packet_log or 'live' ?
- [x] select all: doesn't toggle all select boxes
- [x] details: I don't think this adds value, we can remove this.
- [x] logs button: i think it's better to change this into 'copy selection' so the user can paste this in another card.
- [x] reset: what does it do ? it takes a while before the results field is cleared.
- [x] fix: ha_log doesn't give any results yet, add some ha logs so you can see what goes on

### Messages (from traffic analyzer)
- [x] colors on top id's (selection)
- [x] on top id's: add selection boxes so we can hide id-pairs from the result (only select/deselect 1 way)
- [x] on top: add selection boxes for the verbs as we did for the id-pairs so we can hide/show them from the result
- [x] on top next to verbs: add selection boxes for the codes as we did for the id-pairs so we can hide/show them from the result
- [x] improve multi-select filtering (only show messages for selected flows, both directions)
- [x] add toggle for parsed values, and make it switch between payload and parsed values (toggle is there, but not working yet)
- [x] add auto hor scrollbar on Payload
- [x] fix dest/src/broadcast, still shows 2026-01-21T08:30:14.883783 	I 	1298 	37:126776 	--:------ 	Y 	003 0001D7
- [x] make ALL the columns sortable and default on time: earliest first

### Log explorer
- [x] allow multi-line paste to act as OR search
- [x] auto hor scrollbar on tail result (wrap or no wrap)
- [x] editable before and after
- [x] move 'Search scans the full file....' behind the tail (with the search section)
- [-] horizontal line between search blocks (instead of newline) (skip for now)
- [x] bg colors on id's
- [x] font color: log source between [] : green, but only on the source, not other lists:
- [x] what's the diff between refresh and Tail. Seems they both refresh. If so, we can remove refresh button
- [x] add 50 lines up and 50 lines down buttons, so we can scroll thru the whole file without loading the whole log file. Now we make the block (200 lines) bigger or smaller. I want to move focus: EOF -200 till EOF -> EOF-250 till EOF-50, etc...
- [x] on Zoom we want the same bg colors / fontcolors
- [x] detect and highlight Traceback blocks (include preceding "Detected blocking call" line)

### Packet explorer

### Refactor plan (Option A)
- [x] Strategy agreed: Packet Log Explorer should reuse the same UI as the Traffic Analyzer Messages dialog (with file selector + load mode)
- [x] Extract Messages UI into shared component (chips: pairs/verbs/codes, sort, payload/parsed toggle)
- [x] Traffic Analyzer: Messages dialog uses shared component (no behavioral change)
- [x] Packet Log Explorer: switch to shared component UI
- [x] Packet Log Explorer: add selectbox for load mode (auto-load vs manual Load button)

### Backend
- [x] avoid blocking imports (importlib.import_module) in the HA event loop during feature setup

### other

- [] fix automation not sending fan speed commands:2026-01-22 12:23:59.592 DEBUG (MainThread) [custom_components.ramses_extras.features.humidity_control.platforms.switch] simulating set_device_fan_speed
2026-01-22 12:23:59.593 INFO (MainThread) [custom_components.ramses_extras.features.humidity_control.services] Setting fan speed to high for device 32_153289
2026-01-22 12:23:59.593 DEBUG (MainThread) [custom_components.ramses_extras.framework.helpers.ramses_commands] Send Command - Command definition: None
2026-01-22 12:23:59.593 WARNING (MainThread) [custom_components.ramses_extras.features.humidity_control.services] Failed to send fan speed command high to device 32_153289
2026-01-22 12:23:59.593 WARNING (MainThread) [custom_components.ramses_extras.features.humidity_control.services] Failed to set fan speed for device 32_153289
2026-01-22 12:23:59.593 INFO (MainThread) [custom_components.ramses_extras.features.humidity_control.services] Dehumidification activated: switch.dehumidify_32_153289
2026-01-22 12:23:59.593 INFO (MainThread) [custom_components.ramses_extras.features.humidity_control.automation] Dehumidification activated: High indoor RH: 58.0% > 57.0% with indoor abs (5.28) > outdoor abs (2.33) + offset (0.10)
2026-01-22 12:23:59.593 DEBUG (MainThread) [custom_components.ramses_extras.features.humidity_control.platforms.binary_sensor] Binary sensor Dehumidifying Active 32_153289 state set to True /// we get this warning, but on the card, the speed IS set to high...


## Acceptance criteria
- With ramses_cc message events enabled, Traffic Analyser shows live counts changing
- Log Explorer can filter HA logs and return ±N context around matches
- Log Explorer output is easy to copy/paste (plain + markdown)
- Zoom dialogs work for both cards
- Reset clears Traffic Analyser stats immediately
 - Traffic Analyser shows codes and verbs counters per flow
 - Traffic Analyser can open Log Explorer via action button
 - Message listing (when implemented) allows drilling down to raw + parsed message details
