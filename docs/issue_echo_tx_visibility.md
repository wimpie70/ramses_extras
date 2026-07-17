# Issue: Echo suppression and Tx visibility for ramses_extras debugger

## Context

ramses_rf issue 765 ("Chore: Silence 0.57.6 Duplicate RQ packets in ramses
Packet Log") reports that every RQ is logged twice, a few ms apart.  This
was split from issue 757, where the duplicate RQs appeared with two
different HGI source IDs.

The discussion raised two questions that affect ramses_extras:

1. If ramses_rf silences internal echoes, will the debugger still see all
   traffic?
2. Can code built on top of ramses_rf access outgoing traffic (Tx) over
   the same channel as the log?

This document traces the current packet flow, identifies the duplication
source, and proposes a solution that gives ramses_extras full Tx+Rx
visibility without requiring a user option.

## Current architecture

### Two paths to the debugger

ramses_extras receives messages through two channels, both in
`framework/helpers/ramses_message_stream.py`:

1. **`add_msg_handler`** (line 157) — ramses_extras registers directly
   with `coordinator.client.add_msg_handler(self._handle_msg)`.  This is
   the same handler list that `RamsesLearnEvent` and the Gateway's
   `_msg_handler` use.  It fires for every inbound `PacketDTO` that
   passes the device ID filter — **including the HGI80 echo of our own
   transmitted commands**.

2. **`ramses_cc_message` HA bus event** (line 67) — legacy fallback for
   older ramses_cc versions (< 0.55.6).

### How the packet log gets written

The packet log (`packet_log.log`) is written by a separate path.
`Packet.__init__` calls `PKT_LOGGER.info(...)` for every Packet object
created (`ramses_tx/packet.py` line 102-103).  This fires for:

- **Inbound packets** (echoes + replies + broadcasts) via `pkt_received`
  → `_pkt_received` → the Packet already exists from the transport layer
- **Outbound packets** via `_log_tx_packet` in
  `ramses_tx/transport/base.py` (line 248-260) — this creates a
  `Packet(dt_now(), frame_clean)` purely for logging, before the frame
  is written to the serial port

So the packet log already gets **both** Tx and Rx.  The `add_msg_handler`
path only gets **Rx** (including echoes of our Tx).

### The duplicate RQ problem

For a single `RQ` command with `num_repeats=2` (used by many sensors,
ventilators, and remotes), the log sees:

| Source                                  | What              | Log lines |
|-----------------------------------------|-------------------|-----------|
| `_log_tx_packet`                        | Our Tx frame #1   | 1         |
| HGI80 echo of Tx #1 → `pkt_received`    | Echo of Tx #1     | 1         |
| `_log_tx_packet`                        | Our Tx frame #2   | 1         |
| HGI80 echo of Tx #2 → `pkt_received`    | Echo of Tx #2     | 1         |
| Device RP → `pkt_received`              | Reply             | 1         |

That's 4 RQ-looking lines + 1 RP.  The `_log_tx_packet` lines and the
echo lines are **both** our own command, logged twice per transmission.

### Why num_repeats causes the duplicate

Many callers in ramses_rf pass `num_repeats=2`:

- `heat_sensors.py`: `async_send_cmd(cmd, num_repeats=2, ...)`
- `hvac_ventilators.py`: `async_send_cmd(cmd, num_repeats=2, ...)`
- `hvac_remotes.py`: `async_send_cmd(cmd, num_repeats=2, ...)`
- `hvac_sensors.py`: `async_send_cmd(cmd, num_repeats=2, ...)`

The QoS code in `protocol/core.py` (line 248-251) tries to zero
`num_repeats` when `wait_for_reply` is True, but for many codes
`wait_for_reply` is forced to False:

```python
if self._disable_qos is None and cmd.code not in _CODES:
    qos._wait_for_reply = False  # num_repeats NOT zeroed
```

So RQs for codes outside `_CODES` (0006, 0404, 0418, 1FC9) are sent
twice, each producing its own echo — 4 packets on the wire (2 sends + 2
echoes), 4 entries in the log.

## The problem with silencing echoes

### What would be lost

If ramses_rf filters out HGI80 echoes before they reach `_msg_received`,
the debugger loses outbound visibility.  The `add_msg_handler` path
only fires for Rx — it does not fire for Tx.  The only way ramses_extras
currently sees Tx is indirectly via the HGI80 echo coming back as Rx.

You would **not** see all traffic.  You'd see all *inbound* traffic, but
lose visibility of your own outbound commands.  For a debugging tool
that's a significant loss — you can no longer correlate RQ→RP pairs,
can't see if a command was actually sent, can't diagnose "why didn't
the device respond" (was the RQ sent? was it sent twice?).

### Why a user option is the wrong approach

Making echo suppression a user option means that for every support
request we'd need to check whether it's On or Off.  That's unnecessary
overhead.  Echoes are **always** duplicates of Tx — there's no scenario
where seeing the echo adds information that the Tx log line doesn't
already provide.  Suppression should be the default, not a toggle.

## Proposed solution

Three changes in ramses_rf, no changes needed in ramses_extras:

### 1. Expose Tx to add_msg_handler

Call msg handlers from `_send_frame` (or `_log_tx_packet`) with the
outbound `PacketDTO`, tagged `is_tx=True`.  This gives ramses_extras
(and any other consumer) real-time access to outbound traffic through
the same channel as inbound.

```python
# ramses_tx/transport/base.py, in write_frame() or _log_tx_packet()
# After logging the Tx frame, also dispatch to msg handlers
if self._protocol and hasattr(self._protocol, '_msg_received'):
    dto = PacketDTO(
        timestamp=dt_now(),
        rssi="000",
        verb=...,  # parsed from frame
        ...
        is_tx=True,  # new field or marker
    )
    self._protocol._msg_received(dto)
```

ramses_extras' `_handle_msg` in `ramses_message_stream.py` would then
receive Tx packets directly, without relying on the echo.  The
`is_tx` marker lets consumers distinguish Tx from Rx if needed.

### 2. Stop logging echoes in the packet log

The echo is a duplicate — it's our own frame bounced back by the radio.
The packet log already has the Tx line from `_log_tx_packet`.  The echo
adds no information.

The challenge: the log write happens inside `Packet.__init__` (line
102-103), which runs before `_msg_received` dispatches to handlers.  So
the echo is logged before anyone can tag it.

Options:

- **Move the log write out of `Packet.__init__`** into `_pkt_received`,
  where it can check "is this an echo of a recent Tx?" before logging.
  This is the clean fix but touches a hot path.
- **Pass an `is_echo` flag to the Packet constructor** when creating it
  from the echo path, and skip the log in `_validate` when that flag is
  set.
- **Post-filter in `PktLogFilter`** (`ramses_tx/logger.py` line 147) —
  check for an echo marker in the log record's extra data.

The FSM still needs the echo for QoS state tracking, so the echo must
still reach `context.pkt_received(pkt)` — only the **log write** should
be suppressed.

### 3. Fix num_repeats for RQs

The root cause of issue 765.  RQs that expect a reply should have
`num_repeats=0`.  The QoS code tries to do this but the
`wait_for_reply = False` override for non-`_CODES` prevents it.

Fix: either don't force `wait_for_reply = False` for RQs, or zero
`num_repeats` for RQs regardless of `wait_for_reply`.  This eliminates
the duplicate transmissions, not just the duplicate log entries.

## What the result looks like

With all three changes applied, for a single RQ command:

| Source                | What        | Log lines | add_msg_handler |
|-----------------------|-------------|-----------|-----------------|
| `_log_tx_packet`      | Our Tx      | 1         | 1 (is_tx=True)  |
| Device RP             | Reply       | 1         | 1               |

- Packet log: 1 RQ + 1 RP (was 4 RQ + 1 RP)
- ramses_extras: sees both Tx and Rx in real time (was Rx-only via echo)
- No user option needed — it's always correct
- No RF bandwidth wasted on duplicate transmissions

## Impact on ramses_extras

### No code changes needed

ramses_extras already handles `PacketDTO` objects through
`add_msg_handler`.  If ramses_rf dispatches Tx through the same channel
(with an `is_tx` marker), ramses_extras' `_handle_msg` will receive them
automatically.

The `TrafficCollector` counts every message — it will now count Tx
packets too, giving a more accurate picture of RF bus activity.  The
`messages_provider.py` dedup logic (line 788-804) already handles
cross-source dedup, so Tx packets from `add_msg_handler` won't duplicate
with packet-log entries.

### What ramses_extras could optionally do

- **Tag Tx packets in the UI**: if `is_tx=True` is available on the
  `PacketDTO`, the Packet Log Explorer and Traffic Analyser could show
  Tx packets with a distinct colour or icon, making it visually clear
  which messages are outbound vs inbound.
- **Filter by direction**: add a Tx/Rx/Both filter in the debugger UI.

These are enhancements, not requirements.  The core fix is in ramses_rf.

## Files involved (ramses_rf)

- `src/ramses_tx/transport/base.py` — `_log_tx_packet`: dispatch Tx to
  msg handlers
- `src/ramses_tx/protocol/base.py` — `pkt_received` / `_pkt_received`:
  suppress echo log writes
- `src/ramses_tx/packet.py` — `Packet.__init__` / `_validate`: support
  `is_echo` flag to skip logging
- `src/ramses_tx/protocol/core.py` — `_send_cmd`: fix `num_repeats` for
  RQs
- `src/ramses_tx/dtos.py` — `PacketDTO`: add `is_tx` field (optional)

## References

- ramses_cc issue 765: https://github.com/ramses-rf/ramses_cc/issues/765
- ramses_cc issue 757: https://github.com/ramses-rf/ramses_cc/issues/757
- `ramses_tx/transport/base.py` `_log_tx_packet` — Tx logging
- `ramses_tx/packet.py` `Packet.__init__` — packet log write
- `ramses_tx/protocol/base.py` `_msg_received` — handler dispatch
- `ramses_tx/protocol/core.py` `_send_cmd` — QoS / num_repeats logic
- `ramses_extras/framework/helpers/ramses_message_stream.py` —
  `add_msg_handler` registration and message handling
- `ramses_extras/features/ramses_debugger/messages_provider.py` —
  packet log parsing and dedup
