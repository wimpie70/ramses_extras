# SIGNAL_UPDATE architecture — history and current flow

Mermaid diagrams visualising the entity-refresh signal flow described in
[ramses_cc PR 764 comment 4905294337](https://github.com/ramses-rf/ramses_cc/pull/764#issuecomment-4905294337)
and the subsequent implementation in [issue 794](https://github.com/ramses-rf/ramses_cc/issues/794)
(shipped in 0.58.0).

## Chapters

- [1. Historical flow (0.57.5) — Learn event entity was the sole signal emitter](#1-historical-flow-0575--learn-event-entity-was-the-sole-signal-emitter)
- [2. The 0.56.7 bug — stale-state race](#2-the-0567-bug--stale-state-race)
- [3. Current flow (0.58.0+) — coordinator owns the signal emission](#3-current-flow-0580--coordinator-owns-the-signal-emission)
- [4. What changed and why](#4-what-changed-and-why)
- [5. Resolved questions](#5-resolved-questions)
- [6. Future upgrade — StateUpdatedEvent](#6-future-upgrade--stateupdatedevent)

---

<a id="1-historical-flow-0575--learn-event-entity-was-the-sole-signal-emitter"></a>
## 1. Historical flow (0.57.5) — Learn event entity was the sole signal emitter

This was the architecture before issue 794. It is kept for historical context.

```mermaid
flowchart TD
    subgraph ramses_tx["ramses_tx / protocol layer"]
        RX["_msg_received<br/>(protocol/base.py)"]
        CT["loop.create_task<br/>(Gateway._msg_handler)"]
        SYNC["extra msg-handlers<br/>invoked synchronously"]
    end

    subgraph ramses_rf["ramses_rf / Gateway"]
        INGEST["CQRS ingestion engine<br/>updates device state"]
    end

    subgraph ramses_cc_event["ramses_cc / event.py (OLD — load-bearing)"]
        LEARN["RamsesLearnEvent.async_process_msg<br/>(only runs if Platform.EVENT loaded)"]
        SLEEP["asyncio.sleep(0.05)<br/>magic 50ms deferral"]
        SEND["_send_signals<br/>async_dispatcher_send"]
    end

    subgraph ramses_cc_entities["ramses_cc / entities (should_poll=False)"]
        ENT["RamsesEntity._async_update_and_write_state<br/>reads device state + async_write_ha_state"]
    end

    RX -->|"schedules (does not run yet)"| CT
    RX -->|"runs synchronously"| SYNC
    SYNC --> LEARN
    LEARN --> SLEEP
    SLEEP --> SEND
    SEND -->|"SIGNAL_UPDATE_{src}"| ENT
    SEND -->|"SIGNAL_UPDATE_{dst}"| ENT
    CT --> INGEST
    INGEST -.->|"state must be ready<br/>before ENT reads it"| ENT

    classDef problem fill:#fdd,stroke:#c33,color:#900
    classDef fragile fill:#ffe,stroke:#cc3,color:#660
    class LEARN,SLEEP,SEND problem
    class SEND,ENT fragile
```

### Why this was fragile

- **Single point of failure:** `LEARN` only ran if `Platform.EVENT` loaded and the
  entity was added to hass. If the event platform failed to load, was disabled, or the
  entity was removed, **all entity updates silently stopped**. No other emitter, no
  fallback polling (`_attr_should_poll = False`).
- **Wrong layer:** `SIGNAL_UPDATE_{id}` semantically means *"ramses_rf has finished
  ingesting a packet for device X"* — a statement about the Gateway/coordinator
  layer, not a HA event entity. A UI-facing feature was a hidden dependency of the
  core state pipeline.
- **Timing by sleep:** the 50ms `asyncio.sleep` was a heuristic. Under heavy load
  (issue 666 CPU ramp) it might not be enough; under idle it was unnecessary latency;
  and it was fragile against future ramses_rf refactors that add await points.

[top](#signal_update-architecture--history-and-current-flow)

---

<a id="2-the-0567-bug--stale-state-race"></a>
## 2. The 0.56.7 bug — stale-state race

```mermaid
sequenceDiagram
    participant RX as _msg_received
    participant CT as create_task<br/>(Gateway ingestion)
    participant LEARN as Learn callback<br/>(sync, pre-0.57.5)
    participant ENT as RamsesEntity

    RX->>RX: packet arrives
    RX->>CT: schedule Gateway._msg_handler (create_task)
    Note over CT: NOT run yet — still queued
    RX->>LEARN: invoke extra handlers synchronously
    LEARN->>ENT: SIGNAL_UPDATE_{src} (immediate)
    ENT->>ENT: async_write_ha_state reads STALE state
    Note over ENT: last_changed never advances
    CT->>CT: Gateway ingestion finally runs (too late)
    Note over RX,ENT: Update lands only by event-loop scheduling luck<br/>"1-2 updates a day" symptom (issue 674)
```

PR 737 fixed the timing symptom by deferring the signal send via
`asyncio.sleep(0.05)` + `async_create_task`, released in **0.57.5**.
This addressed the symptom but not the structural fragility.

[top](#signal_update-architecture--history-and-current-flow)

---

<a id="3-current-flow-0580--coordinator-owns-the-signal-emission"></a>
## 3. Current flow (0.58.0+) — coordinator owns the signal emission

Implemented in [issue 794](https://github.com/ramses-rf/ramses_cc/issues/794),
shipped in 0.58.0. The coordinator registers a raw packet handler that
emits `SIGNAL_UPDATE` after a deterministic yield.

```mermaid
flowchart TD
    subgraph ramses_tx["ramses_tx / protocol layer"]
        RX["_msg_received<br/>(protocol/base.py)"]
        CT["loop.create_task<br/>(Gateway._msg_handler)"]
        SYNC["extra msg-handlers<br/>invoked synchronously"]
    end

    subgraph ramses_rf["ramses_rf / Gateway"]
        INGEST["CQRS ingestion engine<br/>updates device state"]
    end

    subgraph ramses_cc_coord["ramses_cc / coordinator.py"]
        HANDLER["_on_packet<br/>msg handler registered at coordinator setup"]
        YIELD["await asyncio.sleep(0)<br/>deterministic yield to ingestion"]
        SEND["async_dispatcher_send<br/>SIGNAL_UPDATE_{src} / {dst}"]
    end

    subgraph ramses_cc_event["ramses_cc / event.py (slimmed)"]
        LEARN["RamsesLearnEvent<br/>fires learn events only<br/>(no longer load-bearing)"]
    end

    subgraph ramses_cc_entities["ramses_cc / entities"]
        ENT["RamsesEntity._async_update_and_write_state<br/>reads device state + async_write_ha_state"]
        POLL["should_poll + async_update + poll_codes<br/>poll-driven path for entities that opt in"]
    end

    RX -->|"schedules (does not run yet)"| CT
    RX -->|"runs synchronously"| SYNC
    SYNC --> HANDLER
    HANDLER --> YIELD
    YIELD --> SEND
    SEND -->|"SIGNAL_UPDATE_{src}"| ENT
    SEND -->|"SIGNAL_UPDATE_{dst}"| ENT
    CT --> INGEST
    INGEST -.->|"state ready before ENT reads it"| ENT
    SYNC -.->|"still fires, but only<br/>for learn events"| LEARN
    POLL -.->|"fallback for entities<br/>that opt in"| ENT

    classDef good fill:#dfd,stroke:#393,color:#060
    classDef neutral fill:#eef,stroke:#36c,color:#036
    classDef fallback fill:#ffd,stroke:#990,color:#440
    class HANDLER,YIELD,SEND good
    class LEARN neutral
    class POLL fallback
```

### Coordinator handler (implemented)

```python
# coordinator.py — _on_packet raw handler
@callback
def _on_packet(dto: PacketDTO) -> None:
    async def _signal_after_ingestion() -> None:
        await asyncio.sleep(0)  # yield to ramses_rf's create_task'd ingestion
        async_dispatcher_send(self.hass, f"{SIGNAL_UPDATE}_{dto.src.id}")
        if dto.dst and dto.dst.id != dto.src.id:
            async_dispatcher_send(self.hass, f"{SIGNAL_UPDATE}_{dto.dst.id}")
    self.hass.async_create_task(_signal_after_ingestion())

self.client.add_msg_handler(_on_packet)
```

The 50ms `asyncio.sleep` in `event.py` was deleted. The event entity is
no longer load-bearing for the state pipeline.

[top](#signal_update-architecture--history-and-current-flow)

---

<a id="4-what-changed-and-why"></a>
## 4. What changed and why

```mermaid
flowchart LR
    A["Single point of failure"] -->|removed| B["Coordinator owns emission<br/>event platform optional"]
    C["Wrong layer"] -->|fixed| D["Signal emitted at the<br/>Gateway/coordinator boundary"]
    E["Magic 50ms sleep"] -->|replaced| F["Deterministic<br/>await asyncio.sleep(0)"]
    G["No observability"] -->|added| H["Single place to log<br/>which device signalled"]
    I["Event entity load-bearing"] -->|decoupled| J["Event entity can be<br/>disabled without breaking updates"]
    K["No fallback path"] -->|added| L["should_poll + poll_codes<br/>for entities that opt in"]
```

[top](#signal_update-architecture--history-and-current-flow)

---

<a id="5-resolved-questions"></a>
## 5. Resolved questions

The open questions from the original proposal have been resolved:

| Question | Resolution |
|----------|------------|
| **Yield strategy:** `asyncio.sleep(0)` vs explicit ramses_rf hook? | **`asyncio.sleep(0)` chosen** (interim). Works in practice — `create_task`'d ingestion runs on the next loop iteration. StateUpdatedEvent remains a future upgrade for deterministic ingestion-complete signalling. |
| **Fallback polling:** safety-net poll interval? | **Yes — `should_poll` + `async_update` + `poll_codes`** provide a poll-driven path for entities that opt in. Not all entities use this; most rely on the signal. |
| **Migration path:** both emitters during transition? | **Hard cutover.** The coordinator handler replaced the event entity's `_send_signals` block. The 50ms sleep in `event.py` was deleted. |
| **`SIGNAL_NEW_DEVICES` interaction?** | **No interaction.** The fan_handler / number-platform parameter entities use `SIGNAL_NEW_DEVICES`, not `SIGNAL_UPDATE`. Unaffected. |

[top](#signal_update-architecture--history-and-current-flow)

---

<a id="6-future-upgrade--stateupdatedevent"></a>
## 6. Future upgrade — StateUpdatedEvent

Step 4 is functionally done. The remaining future work is replacing
`asyncio.sleep(0)` with a deterministic ingestion-complete hook:

```mermaid
flowchart LR
    NOW["NOW (0.58.0+)<br/>coordinator _on_packet<br/>+ asyncio.sleep(0)<br/>+ should_poll fallback"]
    FUTURE["FUTURE<br/>StateUpdatedEvent from<br/>CQRS StateProjector<br/>(ramses_rf #530 Phase 3)"]

    NOW -->|"upgrade when ramses_rf<br/>CQRS events are live"| FUTURE

    classDef now fill:#dfd,stroke:#393,color:#060
    classDef future fill:#eef,stroke:#36c,color:#036
    class NOW now
    class FUTURE future
```

StateUpdatedEvent is no longer a **blocker** — it is a **future upgrade** to
replace the `asyncio.sleep(0)` yield with a deterministic ingestion-complete
hook. The current solution works correctly; the upgrade would make the timing
guarantee explicit rather than relying on event-loop scheduling.
