# Issue: SIGNAL_UPDATE emission is coupled to the Event platform (Learn event)

## Summary

All device-entity state updates in ramses_cc depend on a single
`async_dispatcher_send(SIGNAL_UPDATE_{id})` call that lives inside
`RamsesLearnEvent.async_process_msg` in `event.py`.  The Learn event was
intended as an optional, user-activated feature (only fires when
`learn_device_id` is set), but during the March 2026 refactor that split
`event.py` out of `__init__.py`, the signal emission moved with it and
became the sole update path for every entity.

A second, related problem: entities whose values must be fetched (not
pushed by inbound RF traffic) have `should_poll = False` and rely on a
ramses_rf-internal poller that is dysfunctional.  The HA dev docs
recommend letting HA own the polling for these entities instead.

We propose **two PRs** to address both concerns:

- **PR 1 — Decouple signal emission from the Event platform** (the
  single-point-of-failure fix)
- **PR 2 — Let HA poll fetch-driven entities** (the `should_poll` fix,
  per HA dev docs)

Both are standalone, independent of the `feature/passive-scan-cc` branch
and of Step 4 of the schema architecture plan.  PR 2 benefits from PR 1
being merged first, but can be done independently.

## Cause

### What the original code looked like

Before commit `79a6bf9` (March 2026, "working events ex reload, learn_cmd
svc, i18n, cleanup init"), `__init__.py` contained
`async_register_domain_events` with this handler:

```python
@callback
def async_process_msg(msg: Message, *args: Any, **kwargs: Any) -> None:
    """Process a message from the event bus and pass it on."""
    async_dispatcher_send(hass, f"{SIGNAL_UPDATE}_{msg.src.id}")
    if msg.dst and msg.dst.id != msg.src.id:
        async_dispatcher_send(hass, f"{SIGNAL_UPDATE}_{msg.dst.id}")

    # ...then regex/learn event handling (only if configured)
```

The `SIGNAL_UPDATE` emission lived in `__init__.py` — at the integration
setup layer — and was independent of the Learn/Regex event logic.

### What happened during the split

When `event.py` was created and the event entities (`RamsesLearnEvent`,
`RamsesRegexEvent`) were moved out of `__init__.py`, the entire
`async_process_msg` callback moved into `RamsesLearnEvent.__init__` as the
entity's `event_callback`.  The `SIGNAL_UPDATE` emission went with it.

The commented-out code in `__init__.py` (visible in commit `79a6bf9`)
shows the old handler was deleted and not rewired elsewhere.  No
replacement signal emitter was added to `__init__.py` or `coordinator.py`.

### The 50 ms sleep band-aid

Commit `4dd1657` (June 2026, "defer SIGNAL_UPDATE to avoid stale
hvac_state reads") added a 50 ms `asyncio.sleep` inside the Learn event's
`_send_signals` because the signal was being emitted *before* ramses_rf's
CQRS ingestion engine had finished updating device state.  The commit
message itself notes:

> This is a pragmatic fix. The 50ms delay is a heuristic that works in
> practice but needs further testing. A more robust solution would be to
> have ramses_rf expose a post-ingestion hook.

### Why the signal coupling is a problem

1. **Single point of failure:** if the Event platform fails to load, is
   disabled, or the `RamsesLearnEvent` entity is removed, **all entity
   updates silently stop**.  No other emitter exists, and
   `_attr_should_poll = False` on all `RamsesEntity` subclasses means
   there is no fallback polling.

2. **Wrong layer:** `SIGNAL_UPDATE_{id}` semantically means "ramses_rf has
   ingested a packet for device X" — a statement about the
   Gateway/coordinator boundary, not a HA event entity.  A UI-facing
   feature has become a hidden dependency of the core state pipeline.

3. **Timing by sleep:** the 50 ms `asyncio.sleep` is a heuristic.  Under
   heavy load it may not be enough; under idle it is unnecessary latency;
   and it is fragile against future ramses_rf refactors that add await
   points.

### Why the ramses_rf poller for `filter_remaining` is dysfunctional

The `FilterChange` class in ramses_rf has a poller that sends `RQ 10D0`
every 12 hours.  However, it only starts when discovery is disabled:

```python
# ramses_rf/devices/hvac_ventilators.py, line 95
if getattr(self._gwy.config, "disable_discovery", False):
    self._start_handle = asyncio.get_running_loop().call_soon(self.start_poller)
```

When discovery is enabled (the normal case), the `RQ 10D0` is supposed to
come from the discovery scan's command list.  But if discovery isn't
actively scanning for that device, or the scan interval is long, the
value goes stale.  This is the "filter_remaining 10DA never fires"
complaint from the discussion.

On top of that, `fan_handler.py` has a HACK — a one-time forced
`RQ 10D0` with a TODO to remove it:

```python
# fan_handler.py, line 223
# HACK: Force one time RQ of 10D0 - TODO(eb): remove when PR #632 is working
cmd = Command.from_cli(f"RQ {device.id} 10D0 00")
await device._gwy.async_send_cmd(cmd)
```

This is a band-aid for the dysfunctional poller.

### HA development guidelines

The HA dev docs describe the intended push-vs-poll split:

- [Appropriate polling](https://developers.home-assistant.io/docs/core/integration-quality-scale/rules/appropriate-polling)
- [Integration fetching data](https://developers.home-assistant.io/docs/integration_fetching_data)

Key principle from the fetching-data page:

> If you can map exactly one device endpoint to a single entity, you can
> fetch the data for this entity inside the `update()`/`async_update()`
> methods. Make sure polling is set to `True` and Home Assistant will call
> this method regularly.

Our code should follow these principles:

| Situation                                          | HA recommendation                                   | Current state                                              |
|----------------------------------------------------|-----------------------------------------------------|------------------------------------------------------------|
| Value is push-delivered (inbound RF packets)       | `should_poll = False`, update via callbacks/signals | Works, but signal comes from the wrong layer (PR 1)        |
| Value must be fetched (e.g. fan `filter_remaining`) | `should_poll = True`, fetch in `async_update()`     | `should_poll = False` + dysfunctional ramses_rf poller (PR 2) |
| Many endpoints batched via coordinator             | `DataUpdateCoordinator` polling to batch-fetch      | Coordinator exists but `_async_update_data` is a no-op     |

## Scope

This issue is **not** part of:
- The current `feature/passive-scan-cc` PR (schema SSOT / discovery work)
- Step 4 of the schema architecture plan (full `StateUpdatedEvent` rewrite,
  blocked on ramses_rf CQRS StateProjector)

Both PRs are standalone interim fixes.  PR 1 restores the pre-March-2026
architecture with one improvement: `await asyncio.sleep(0)` instead of
the old immediate send (which caused the stale-state bug).  PR 2 moves
fetch-driven entities to the HA-recommended polling pattern.

## PR 1 — Decouple signal emission from the Event platform

### 1. Move signal emission to the coordinator

Register a packet handler in `coordinator.py` `async_start()` that owns
the `SIGNAL_UPDATE` emission:

```python
# coordinator.py, in async_start() after self.client is confirmed
@callback
def _on_packet(dto: PacketDTO) -> None:
    """Emit SIGNAL_UPDATE after ramses_rf has ingested the packet."""
    async def _signal_after_ingestion() -> None:
        await asyncio.sleep(0)  # yield to ramses_rf's create_task'd ingestion
        src_id = dto.addr1
        async_dispatcher_send(self.hass, f"{SIGNAL_UPDATE}_{src_id}")
        if dto.addr2 and dto.addr2 != dto.addr1:
            async_dispatcher_send(self.hass, f"{SIGNAL_UPDATE}_{dto.addr2}")

    self.hass.async_create_task(_signal_after_ingestion())

self.entry.async_on_unload(self.client.add_msg_handler(_on_packet))
```

`PacketDTO` exposes `addr1` (source) and `addr2` (destination) directly,
so there is no need to construct a `Message` object just to read device
IDs.  The `await asyncio.sleep(0)` yields once to the event loop, letting
the Gateway's `create_task`'d ingestion coroutine run before entities
read state — a deterministic replacement for the 50 ms heuristic.

### 2. Remove signal emission from RamsesLearnEvent

In `event.py`, delete the `_send_signals` block (the `asyncio.sleep(0.05)`
and `async_dispatcher_send` calls).  `RamsesLearnEvent.async_process_msg`
becomes only the learn-event firing logic:

```python
@callback
def async_process_msg(dto: PacketDTO, *args: Any, **kwargs: Any) -> None:
    """Process a message for the Learn event (only fires if learn_id set)."""
    try:
        msg = Message(dto)
    except PacketInvalid:
        return

    if (
        coordinator.learn_device_id is not None
        and coordinator.learn_device_id == msg.src.id
    ):
        event_data = {
            "type": RamsesEventType.LEARN,
            "src": msg.src.id,
            "code": str(msg.code),
            "packet": repr(msg),
        }
        self.update_data(event_data)
```

The Learn event is now just a Learn event — it only does something when
`learn_device_id` is set, exactly as intended.

### 3. Clean up imports

- `event.py`: remove `asyncio`, `async_dispatcher_send`, and
  `SIGNAL_UPDATE` from imports (no longer used there).
- `coordinator.py`: add `SIGNAL_UPDATE` to the `.const` import, add
  `PacketDTO` to the `ramses_tx.dtos` import, add `callback` to the
  `homeassistant.core` import.

### What PR 1 achieves

- The Event platform is no longer load-bearing — disabling it won't break
  entity updates.
- The 50 ms magic sleep is replaced by a deterministic
  `await asyncio.sleep(0)`.
- The Learn event and Regex event go back to being optional UI-facing
  features, only active when configured.
- The signal emission lives at the coordinator/Gateway boundary, which is
  semantically correct.

### PR 1 files touched

- `custom_components/ramses_cc/coordinator.py` — add `_on_packet` handler
  in `async_start()`, add imports
- `custom_components/ramses_cc/event.py` — remove `_send_signals` block
  from `RamsesLearnEvent.async_process_msg`, clean up imports

## PR 2 — Let HA poll fetch-driven entities

### Background

The `filter_remaining` sensor is a 1:1 entity-to-endpoint mapping —
exactly the case the HA dev docs describe for `should_poll = True` +
`async_update()`.  Currently it has `should_poll = False` (inherited from
`RamsesEntity`) and relies on ramses_rf's `FilterChange._poller`, which
only starts when discovery is disabled (see Cause section above).

The approach: let HA own the polling schedule.  `async_update()` sends
the `RQ 10D0` command (fire-and-forget).  The fan responds, the `10D0`
packet arrives, CQRS ingestion updates `hvac_state.filter_remaining_days`,
and `SIGNAL_UPDATE` fires — which is the push path PR 1 fixes.  The entity
then reads the fresh value in `_async_update_and_write_state`.

### 1. Set `should_poll = True` for fetch-driven entity descriptions

In `sensor.py`, the `filter_remaining` and `filter_remaining_percent`
entity descriptions need a way to opt into polling.  This can be done via
a flag on `RamsesSensorEntityDescription` (e.g. `should_poll: bool =
False`) that `RamsesSensor` reads to set `_attr_should_poll`:

```python
# sensor.py
@dataclass(frozen=True, kw_only=True)
class RamsesSensorEntityDescription(RamsesEntityDescription, SensorEntityDescription):
    ...
    should_poll: bool = False  # opt-in for fetch-driven entities
```

```python
# sensor.py, entity descriptions
RamsesSensorEntityDescription(
    key=SZ_FILTER_REMAINING,
    ramses_rf_attr=SZ_FILTER_REMAINING,
    name="Filter remaining",
    native_unit_of_measurement=UnitOfTime.DAYS,
    should_poll=True,          # <-- fetch via async_update()
    poll_command="10D0",       # <-- RQ code to send
),
RamsesSensorEntityDescription(
    key=SZ_FILTER_REMAINING_PERCENT,
    ramses_rf_attr=SZ_FILTER_REMAINING_PERCENT,
    name="Filter remaining (%)",
    native_unit_of_measurement=PERCENTAGE,
    should_poll=True,
    poll_command="10D0",
),
```

### 2. Implement `async_update()` on RamsesSensor

```python
# sensor.py, in RamsesSensor
async def async_update(self) -> None:
    """Send RQ to refresh the value from the device (for poll-driven entities)."""
    if not self.entity_description.should_poll:
        return  # push-driven entities: no-op, signal handles updates
    poll_cmd = self.entity_description.poll_command
    if poll_cmd:
        cmd = Command.from_cli(f"RQ {self._device.id} {poll_cmd} 00")
        try:
            await self._device._gwy.async_send_cmd(cmd)
        except Exception as err:
            _LOGGER.debug("Poll %s for %s failed: %s", poll_cmd, self._device.id, err)
    # Don't read state here — the response arrives via SIGNAL_UPDATE
    # and _async_update_and_write_state reads the fresh hvac_state
```

`async_update()` sends the RQ (fire-and-forget).  HA owns the schedule
(respects update intervals, backoff, sleep).  The ramses_rf poller and
the `fan_handler.py` HACK both become unnecessary.

### 3. Remove the ramses_rf poller and fan_handler HACK

After PR 2 is verified working:

- Remove the `FilterChange._poller` / `start_poller` / `stop_poller`
  logic from ramses_rf (or gate it behind `disable_discovery` only, which
  is already the case — just confirm it's not needed when HA polls).
- Remove the HACK in `fan_handler.py` lines 223-234 (the one-time forced
  `RQ 10D0` with the TODO).

### 4. The dead coordinator heartbeat

The `RamsesCoordinator` is a `DataUpdateCoordinator` with
`update_interval = scan_interval`, but `_async_update_data` does nothing
(returns `None`).  With PR 2, individual entities own their own polling
via `async_update()`, so the coordinator heartbeat serves no purpose.
Either:

- **Remove `update_interval`** from the coordinator entirely (it's not
  batching any fetches), or
- **Give `_async_update_data` real work** if there are batch-fetch
  operations that make sense at the coordinator level.

This is a cleanup item that can be part of PR 2 or a follow-up.

### What PR 2 achieves

- Fetch-driven entities (like `filter_remaining`) refresh on a HA-managed
  schedule instead of relying on a dysfunctional ramses_rf poller.
- The `fan_handler.py` HACK can be removed.
- Follows the HA dev docs recommendation for 1:1 entity-to-endpoint
  polling.
- HA owns the scheduling (update intervals, backoff, sleep) — ramses_rf
  doesn't need to manage its own poller.

### PR 2 files touched

- `custom_components/ramses_cc/sensor.py` — add `should_poll` /
  `poll_command` to entity description, implement `async_update()`
- `custom_components/ramses_cc/fan_handler.py` — remove the one-time
  `RQ 10D0` HACK
- `ramses_rf/src/ramses_rf/devices/hvac_ventilators.py` — remove or
  deprecate `FilterChange._poller` (optional, can be follow-up)
- `custom_components/ramses_cc/coordinator.py` — remove or repurpose
  `update_interval` (optional, can be follow-up)

## What neither PR does (deliberately)

- Neither PR waits for ramses_rf's `StateUpdatedEvent` (Step 4 of the
  schema architecture plan).  That is the longer-term fix, blocked on
  ramses_rf CQRS work.
- Neither PR belongs in the `feature/passive-scan-cc` branch.  Both are
  small, focused changes that can go in independently.

## References

- [HA dev docs: Appropriate polling](https://developers.home-assistant.io/docs/core/integration-quality-scale/rules/appropriate-polling)
- [HA dev docs: Integration fetching data](https://developers.home-assistant.io/docs/integration_fetching_data)
- [signal_update_flow.md](./signal_update_flow.md) — mermaid diagrams of
  current vs proposed flow
- [schema_architecture.md, Step 4](./schema_architecture.md) — long-term
  `StateUpdatedEvent` plan (blocked on ramses_rf)
- Commit `79a6bf9` — the March 2026 split that moved signal emission into
  `event.py`
- Commit `4dd1657` — the June 2026 50 ms sleep band-aid
- ramses_rf `hvac_ventilators.py` `FilterChange._poller` — the
  dysfunctional poller (only starts when discovery is disabled)
- ramses_cc `fan_handler.py` line 223 — the `RQ 10D0` HACK with TODO
