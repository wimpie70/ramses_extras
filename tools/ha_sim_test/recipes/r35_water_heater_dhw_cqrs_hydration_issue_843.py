"""Recipe R35: Water heater DHW CQRS hydration (issue 843)."""

from __future__ import annotations

import json

from ..base import Recipe, RecipeContext
from ..const import CTL, DHW
from ..helpers import (
    call_service,
    get_entities,
    ws_send,
)


class R35WaterHeaterDhwCqrsHydrationIssue843(Recipe):
    id = "R35"
    seq = 360
    title = "Water heater DHW CQRS hydration (issue 843)"

    async def run(self, ctx: RecipeContext) -> None:
        # The Phase 2.95 CQRS cutover in ramses_rf redirected DhwZone getters
        # (temperature, setpoint, mode) from the legacy SQLite message store
        # to in-memory CQRS read-models (temp_state / dhw_state).  However,
        # the CQRS ingestion engines never routed DHW opcodes (1260, 10A0,
        # 1F41) to the DhwZone because those payloads carry no
        # zone_idx/domain_id.
        #
        # As a result, the ramses_cc water_heater entity reported None for
        # current/target temperature (while the underlying DHW sensor entity
        # still showed its value).
        #
        # This recipe injects 1260 (DHW temp), 10A0 (DHW params/setpoint),
        # and 1F41 (DHW mode) into the simulator and verifies the
        # water_heater entity picks up the values.
        ctx.log_section("Recipe 34: Water heater DHW CQRS hydration (issue 843)")

        # 1. Load mixed profile (has CTL 01:150000 with stored_hotwater
        #    sensor 07:150000)
        print("  Loading mixed profile (CTL + DHW sensor)...")
        try:
            await ws_send(
                ctx.token,
                {
                    "type": "ramses_extras/device_simulator/load_profile",
                    "profile": "mixed",
                    "speed": 0.01,
                    "preload_schema": True,
                    "reload_ramses_cc": True,
                    "enable_auto_answer": True,
                },
            )
            print("  mixed profile loaded")
        except RuntimeError as e:
            print(f"  Profile load failed: {e}")
        ctx.wait(15, "for ramses_cc reload with mixed profile")
        ctx.refresh_token()
        ctx.wait(5, "for ramses_cc to initialize")

        # Activate CTL and DHW for heartbeats
        for dev_id, name in [(CTL, "CTL"), (DHW, "DHW")]:
            try:
                await ws_send(
                    ctx.token,
                    {
                        "type": "ramses_extras/device_simulator/"
                        "activate_profile_device",
                        "device_id": dev_id,
                    },
                )
                print(f"    {name} activated")
            except RuntimeError:
                pass
        ctx.wait(10, "for CTL/DHW heartbeats + schema population")

        # Silence the DHW sensor's periodic emitter before injecting, to
        # reduce noise from the sim's own 1260 heartbeats at 100x speed.
        # The assertion below checks `is not None` (not an exact value)
        # since the sim's internal temp may still arrive via cached/queued
        # packets, but silencing minimises the race window.
        print(f"  Silencing DHW {DHW} periodic emitter to prevent overwrite...")
        try:
            await ws_send(
                ctx.token,
                {
                    "type": "ramses_extras/device_simulator/silence_devices",
                    "device_ids": [DHW],
                    "set_suppress": False,
                },
            )
            print(f"    DHW {DHW} emitter silenced")
        except RuntimeError as e:
            print(f"    Silence failed (continuing): {str(e)[:80]}")
        ctx.wait(2, "for emitter cancellation to take effect")

        # 2. Inject 1260 I from DHW sensor (07:150000)
        #    Payload: 00 + temp_hex(55.0°C = 0x157C) = 00157C
        #    The DHW sensor is the source; the DhwZone must receive this
        #    via the new CQRS routing (src_dev.tcs.dhw).
        print(f"  Injecting 1260 I from DHW {DHW} (temp=55.0°C)...")
        try:
            call_service(
                ctx.token,
                "ramses_extras",
                "device_simulator_inject_message",
                {
                    "source_id": DHW,
                    "code": "1260",
                    "payload": "00157C",
                    "verb": "I",
                },
            )
            print("    1260 I injected")
        except RuntimeError as e:
            print(f"    Inject failed: {str(e)[:80]}")
        ctx.wait(3, "for 1260 to process")

        # 3. Inject 10A0 RP from CTL (01:150000) — DHW params/setpoint
        #    Payload: 00 + setpoint(50.0°C=0x1388) + overrun(00) + diff(10.0°C=0x03E8)
        #    = 0013880003E8
        #    The CTL is the source; the DhwZone must receive this via the
        #    new CQRS routing (src_dev.tcs.dhw).
        print(f"  Injecting 10A0 I from CTL {CTL} (setpoint=50.0°C)...")
        try:
            call_service(
                ctx.token,
                "ramses_extras",
                "device_simulator_inject_message",
                {
                    "source_id": CTL,
                    "code": "10A0",
                    "payload": "0013880003E8",
                    "verb": "I",
                },
            )
            print("    10A0 I injected")
        except RuntimeError as e:
            print(f"    Inject failed: {str(e)[:80]}")
        ctx.wait(3, "for 10A0 to process")

        # 4. Inject 1F41 I from CTL (01:150000) — DHW mode
        #    Payload: 00 + active(00=False) + mode(00=follow_schedule) + FFFFFF
        #    = 000000FFFFFF
        print(f"  Injecting 1F41 I from CTL {CTL} (mode=follow_schedule)...")
        try:
            call_service(
                ctx.token,
                "ramses_extras",
                "device_simulator_inject_message",
                {
                    "source_id": CTL,
                    "code": "1F41",
                    "payload": "000000FFFFFF",
                    "verb": "I",
                },
            )
            print("    1F41 I injected")
        except RuntimeError as e:
            print(f"    Inject failed: {str(e)[:80]}")
        ctx.wait(5, "for 1F41 to process")

        # Force entity state update
        try:
            call_service(ctx.token, "ramses_cc", "force_update")
        except RuntimeError:
            pass
        ctx.wait(5, "for entity state write")

        # 5. Find the water_heater entity for the DhwZone
        #    The DhwZone ID is CTL + "_HW" (e.g. "01:150000_HW"), but the
        #    HA entity_id is slugified from the device name, which is
        #    "stored_hw" (ramses_cc uses has_entity_name=True with name=None,
        #    so HA derives the slug from the device name, not the unique_id).
        entities = get_entities(ctx.token)
        wh_entity = None
        for e in entities:
            if e["entity_id"].startswith("water_heater."):
                wh_entity = e
                break

        wh_eid = wh_entity["entity_id"] if wh_entity else "None"
        wh_state = wh_entity.get("state") if wh_entity else None
        wh_attrs = wh_entity.get("attributes", {}) if wh_entity else {}
        current_temp = wh_attrs.get("current_temperature")
        target_temp = wh_attrs.get("temperature")
        operation = wh_state

        print(f"  water_heater entity: {wh_eid}")
        print(
            f"  state={operation!r}  "
            f"current_temp={current_temp!r}  target_temp={target_temp!r}"
        )
        print(f"  attrs={json.dumps(wh_attrs)[:200]}")

        # Check 1: water_heater entity exists
        ctx.check(
            "water_heater entity exists for DhwZone",
            wh_entity is not None,
            f"entity_id={wh_eid}",
        )

        # Check 2: current_temperature is hydrated from 1260 (not None)
        #
        #    WITHOUT FIX: None (CQRS read-model never hydrated)
        #    WITH FIX: a float value from 1260 packets
        #
        #    We assert `is not None` rather than `== 55.0` because the sim's
        #    own 1260 heartbeat (carrying the sim's internal temp, e.g.
        #    58.9°C) may arrive after our injected 1260 and overwrite the
        #    value.  The key assertion is that the CQRS hydration pipeline
        #    is functional (value is not None), not the exact temperature.
        ctx.check(
            "water_heater current_temperature hydrated from 1260 (not None)",
            current_temp is not None,
            f"current_temperature={current_temp!r} (None = bug present, issue 843)",
        )

        # Check 3: target_temperature (setpoint) is hydrated from 10A0 (50.0°C)
        #    WITHOUT FIX: None (CQRS read-model never hydrated)
        #    WITH FIX: 50.0
        ctx.check(
            "water_heater target_temperature hydrated from 10A0 (50.0°C)",
            target_temp is not None and target_temp == 50.0,
            f"temperature={target_temp!r} (None = bug present, issue 843)",
        )

        # Check 4: operation mode is hydrated from 1F41 (follow_schedule → auto)
        #    WITHOUT FIX: None or fallback
        #    WITH FIX: "auto" (follow_schedule maps to STATE_AUTO)
        ctx.check(
            "water_heater operation mode hydrated from 1F41 (auto)",
            operation is not None and operation == "auto",
            f"operation={operation!r} (None/unexpected = bug present, issue 843)",
        )
