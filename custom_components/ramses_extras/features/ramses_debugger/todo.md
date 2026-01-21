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

### Step 1: Feature skeleton (no behaviour changes)
- [x] **Deliverable**
  - Create `features/ramses_debugger/` feature scaffold based on `hello_world`
  - Add feature definition + register feature with extras registry
  - Add websocket registration stubs (no-op)
  - Add `www/` stubs for both cards
- [x] **Tests**
  - run existing unit tests (no new tests required yet)
- [x] **Commit**
  - `feat(ramses_debugger): scaffold feature with websocket + www stubs`

### Step 2: Traffic backend (collector + aggregation)
- [x] **Deliverable**
  - Subscribe to `ramses_cc_message`
  - Maintain aggregation data structures
  - Add `traffic/get_stats` + `traffic/reset_stats` websocket commands
- [x] **Tests**
  - unit tests for aggregation logic (pure python)
  - unit tests for websocket handlers (mock hass bus + sample events)
- [x] **Commit**
  - `feat(ramses_debugger): traffic collector + websocket stats API`

### Step 3: Traffic card (MVP UI)
- [x] **Deliverable**
  - Table rendering + basic filters + polling websocket
  - Zoom dialog
- [x] **Tests**
  - keep python tests passing
  - manual live check in HA (card loads, table renders)
- [x] **Commit**
  - `feat(ramses_debugger): traffic analyser card MVP`

### Step 4: Log backend (file discovery + tail + search)
- [x] **Deliverable**
  - Config option for HA log file path
  - `log/list_files`, `log/get_tail`, `log/search`
  - Context extraction (±N lines) + merge overlap
  - Output formatting: plain + markdown
- [x] **Tests**
  - unit tests for log scanning + context merge (use temp files)
  - unit tests for rotated file discovery
- [x] **Commit**
  - `feat(ramses_debugger): log explorer websocket API (tail/search/context)`

### Step 5: Log Explorer card (MVP UI)
- [x] **Deliverable**
  - File picker + filter form + results pane
  - Wrap/nowrap toggle + copy-as-markdown
  - Zoom dialog
- [x] **Tests**
  - keep python tests passing
  - manual live check in HA (filters return expected chunks)
- [x] **Commit**
  - `feat(ramses_debugger): log explorer card MVP`

### Step 6: Cross-filtering Traffic → Logs
- [x] **Deliverable**
  - Traffic row click opens Log Explorer prefilled (src/dst, optional codes)
- [x] **Tests**
  - manual live check
- [x] **Commit**
  - `feat(ramses_debugger): cross-filter traffic to log explorer`

### Step 7: Hardening + limits + UX polish
- [x] **Deliverable**
  - enforce `max_matches`, `max_chars`, safe defaults
  - traceback block extraction (if enabled)
  - better empty/error states
- [x] **Tests**
  - add tests for max limits
  - `make local-ci`
- [x] **Commit**
  - `refactor(ramses_debugger): harden log search + add limits`

### Step 8: CI + documentation ready
- [x] **Deliverable**
  - ensure `make local-ci` passes
  - update this TODO if new learnings arise
- [x] **Tests**
  - `make local-ci`
- [x] **Commit**
  - `chore(ramses_debugger): local-ci green`

### Step 9: UI/UX improvements
- [x] **Deliverable**
  - cards render full width
  - no `device_id` required while editing
  - bounded, scrollable output panes
  - working copy buttons
  - Traffic → Logs popup full width + resizable
  - highlighting for matches and WARNING/ERROR lines
  - default case-insensitive search
  - Traffic table improvements
    - show all verbs + counts
    - show codes + counts
    - deterministic per-device cell background colors (no background for HGI `18:`)
    - show device alias (if known) and always show device type slug (`FAN`, `REM`, `HGI`, ...)
    - prefer action buttons over row-click
      - Logs (opens embedded Log Explorer)
      - Details (raw flow JSON)
      - Messages (placeholder)
- [x] **Tests**
  - manual check in HA
  - `make local-ci`
- [x] **Commit**
  - `feat(ramses_debugger): UI/UX polish for traffic + log cards`

### Step 10: Unified Messages API (HA log / packet log / live traffic)
- [x] **Deliverable**
  - Backend
    - add a single websocket command that can query multiple sources
      - `messages/get_messages` (one-shot)
        - params
          - `sources`: list of sources to query, in priority order
            - `traffic_buffer` (in-memory, from `ramses_cc_message` events)
            - `packet_log` (ramses packet/message log, e.g. `ramses_log`)
            - `ha_log` (Home Assistant log file)
          - filters: src, dst, verb, code, since, until, limit
          - `dedupe`: bool (optional; on by default)
        - response
          - list of normalized messages
            - dtm, src, dst, verb, code
            - payload (raw)
            - packet (raw)
            - source (`traffic_buffer` | `packet_log` | `ha_log`)
            - raw_line (when source is a log file)
            - parse_warnings (optional)
- [x] **Deliverable (continued)**
  - implement providers
      - TrafficCollector ring buffers
        - bounded global and per-flow buffers
        - store raw event fields (dtm/src/dst/verb/code/payload/packet)
      - Packet log provider
        - parse actual traffic records from `ramses_log`
      - HA log provider
        - parse messages from HA log lines (note: will include duplicates from multiple loggers)
        - use dedupe key (dtm+src+dst+verb+code+packet/payload) when possible
  - UI
    - Traffic Analyser: wire Messages button to call `messages/get_messages`
      - default `sources`: [`traffic_buffer`, `packet_log`, `ha_log`]
      - list view: dtm, verb, code, src, dst, payload/packet (collapsed)
      - drill-down placeholder: “Message details”
    - Packet Log Explorer + Log Explorer (later): reuse the same normalized message UI
- [x] **Tests**
  - unit tests for buffering/filtering and dedupe
  - websocket handler tests (each provider)
- [x] **Commit**
  - `feat(ramses_debugger): unified messages API (traffic/packet/ha log)`

### Step 11: Packet Log Explorer (future card)
- [ ] **Deliverable**
  - Backend
    - packet log parsing should be implemented as a provider for Step 10 (`sources: packet_log`)
    - add optional packet-log specific commands only if needed for UX
      - file selection / rotated files
      - faster indexed search
  - UI
    - new Lovelace card: Packet Log Explorer
      - file selection + search filters
      - results list of messages
      - message detail drill-down
- [ ] **Tests**
  - unit tests for parsing + search limits
- [ ] **Commit**
  - `feat(ramses_debugger): packet log explorer (backend + card)`

## Ramses debugger improvements

### Traffic analyzer
- [x] what is the source of the traffic, can we choose between a ha logfile, packet_log or 'live' ?
- [x] select all: doesn't toggle all select boxes
- [x] details: I don't think this adds value, we can remove this.
- [x] logs button: i think it's better to change this into 'copy selection' so the user can paste this in another card.
- [x] reset: what does it do ? it takes a while before the results field is cleared.
- [x] fix: ha_log doesn't give any results yet

### Messages (from traffic analyzer)
- [ ] colors on top id's (selection)
- [ ] list all selected messages: what is the source ? in traffic analyzer i see a total of 4 msgs, but in 'Messages' I see a lot more. This should be the same source
- [x] add toggle for parsed values
- [x] add auto hor scrollbar on Payload
- [ ] fix dest/src/broadcast, still shows 2026-01-21T08:30:14.883783 	I 	1298 	37:126776 	--:------ 	Y 	003 0001D7
- [x] make the columns sortable and default on time: earliest first

### Log explorer
- [x] allow multi-line paste to act as OR search
- [ ] auto hor scrollbar on tail result (without wrap we go outside the window)
- [ ] editable before and after
- [ ] move search options after tail result
- [ ] horizontal line between search blocks (instead of newline)
- [ ] bg colors on id's
- [ ] font color: log source between [] : green

### Packet explorer
- [ ] the details button is out of the window scope.
- [ ] When clicking on details, i would expect to see parsed message, but maybe use 1 toggle button to switch to parsed values instead of payload
- [ ] In the result field, we cannot copy/past text, this would be very handy
- [ ] the search (or filter) doesn't work, remove it ?
- [ ] make the columns sortable and default on time: earliest first
- [ ] instead of wrap set a auto hor. scrollbar on payload
- [ ] bg colors on id's
- [ ] broadcast still not working

## Acceptance criteria
- With ramses_cc message events enabled, Traffic Analyser shows live counts changing
- Log Explorer can filter HA logs and return ±N context around matches
- Log Explorer output is easy to copy/paste (plain + markdown)
- Zoom dialogs work for both cards
- Reset clears Traffic Analyser stats immediately
 - Traffic Analyser shows codes and verbs counters per flow
 - Traffic Analyser can open Log Explorer via action button
 - Message listing (when implemented) allows drilling down to raw + parsed message details
