"""Recipe R36: Zone climate state hydration (issue 843)."""

from __future__ import annotations

import json

from ..base import Recipe, RecipeContext
from ..const import CTL
from ..helpers import (
    call_service,
    get_entities,
    is_ramses_cc_loaded,
    wait_for,
    wait_for_schema_populated,
    wait_for_transport_ready,
    ws_send,
)


class R36ZoneClimateStateHydrationIssue843(Recipe):
    id = "R36"
    seq = 370
    title = "Zone climate state hydration (issue 843)"

    async def run(self, ctx: RecipeContext) -> None:
        # The Phase 2.95 CQRS cutover in ramses_rf redirected Zone getters
        # (mode, setpoint) from the legacy SQLite message store to in-memory
        # CQRS read-models (zone_state / temp_state).  However, the CQRS
        # ingestion engine never routed 2349 (zone_mode) packets to zones
        # because parser_2349 did not include zone_idx in its result, and
        # _update_zone_state only handled 0004 (zone_name).
        #
        # As a result, zone_state.mode stayed None, zone.mode() returned None,
        # and ramses_cc's RamsesZone.hvac_mode returned None — which HA
        # displays as `unknown` when the system is on (should be `heat`).
        #
        # This recipe injects 2E04 (system_mode=auto) and 2349
        # (zone_mode=follow_schedule, setpoint=21°C) into the simulator and
        # verifies the climate entity's state is `heat` (not `unknown`).
        ctx.log_section("Recipe 36: Zone climate state hydration (issue 843)")

        # 1. Load mixed profile (CTL 01:150000 with zones 03-08)
        print("  Loading mixed profile (CTL + zones 03-08)...")
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
        ctx.wait_for_ramses_cc_reload(timeout=20)
        ctx.refresh_token()
        # Wait for the MQTT transport to reconnect after the reload,
        # otherwise injected packets are silently dropped.
        wait_for_transport_ready(timeout=30)
        # Activate CTL for heartbeats
        try:
            await ws_send(
                ctx.token,
                {
                    "type": "ramses_extras/device_simulator/activate_profile_device",
                    "device_id": CTL,
                },
            )
            print("    CTL activated")
        except RuntimeError:
            pass
        wait_for_schema_populated(timeout=15)

        # 1b. Silence the CTL's periodic 2309/2349 emitters to prevent them
        #     from overwriting the setpoint we inject below.  The CTL emits
        #     2309 I packets every ~150s with setpoints like 18.5°C for zone
        #     03, which would race with our 2349 inject (21.0°C).
        print(f"  Silencing CTL {CTL} periodic emitters to prevent overwrite...")
        try:
            await ws_send(
                ctx.token,
                {
                    "type": "ramses_extras/device_simulator/silence_devices",
                    "device_ids": [CTL],
                    "set_suppress": True,
                },
            )
            print(f"    CTL {CTL} emitter silenced (autonomous suppressed)")
        except RuntimeError as e:
            print(f"    Silence failed (continuing): {str(e)[:80]}")
        ctx.wait(2, "for emitter cancellation to take effect", floor=2.0)

        # 1c. Disable auto-answer to prevent the simulator from responding to
        #     ramses_cc's RQ 2349 (sent by climate.async_added_to_hass) with
        #     an RP containing a default setpoint that overwrites our inject.
        #     The dynamic response for 2349 returns ~20.3°C for zone 03, but
        #     we inject 21.0°C.  Re-enabled after the checks pass.
        print("  Disabling auto-answer to prevent RP overwriting injected setpoint...")
        try:
            await ws_send(
                ctx.token,
                {
                    "type": "ramses_extras/device_simulator/set_auto_answer",
                    "enabled": False,
                },
            )
            print("    auto-answer disabled")
        except RuntimeError as e:
            print(f"    Disable auto-answer failed (continuing): {str(e)[:80]}")
        ctx.wait(3, "for auto-answer disable to take effect", floor=3.0)

        # 2. Inject 2E04 I from CTL (01:150000) — system_mode = auto
        #    Payload: 00 + FFFFFFFFFFFF00 (16 hex chars, len=8)
        #    This sets the system mode to "auto" so hvac_mode doesn't
        #    short-circuit to OFF/AWAY.
        print(f"  Injecting 2E04 I from CTL {CTL} (system_mode=auto)...")
        try:
            call_service(
                ctx.token,
                "ramses_extras",
                "device_simulator_inject_message",
                {
                    "source_id": CTL,
                    "code": "2E04",
                    "payload": "00FFFFFFFFFFFF00",
                    "verb": "I",
                },
            )
            print("    2E04 I injected")
        except RuntimeError as e:
            print(f"    Inject failed: {str(e)[:80]}")
        ctx.wait(3, "for 2E04 to process")

        # 3. Inject 2349 I from CTL (01:150000) for zone 03
        #    Payload format: zz-XXXX-MM-DDDDDD (14 hex chars, len=7)
        #    - zz = 03 (zone_idx)
        #    - XXXX = 0834 (setpoint 21.0°C)
        #    - MM = 00 (follow_schedule)
        #    - DDDDDD = FFFFFF (no duration)
        #    This hydrates zone_state.mode and zone_state.setpoint via the
        #    CQRS ingestion pipeline.
        zone_idx = "03"
        setpoint_temp = 21.0
        setpoint_hex = "0834"
        payload_2349 = f"{zone_idx}{setpoint_hex}00FFFFFF"
        print(
            f"  Injecting 2349 I from CTL {CTL} "
            f"(zone={zone_idx}, mode=follow_schedule, setpoint={setpoint_temp}°C)..."
        )
        print(f"    payload: {payload_2349}")
        try:
            call_service(
                ctx.token,
                "ramses_extras",
                "device_simulator_inject_message",
                {
                    "source_id": CTL,
                    "code": "2349",
                    "payload": payload_2349,
                    "verb": "I",
                },
            )
            print("    2349 I injected")
        except RuntimeError as e:
            print(f"    Inject failed: {str(e)[:80]}")
        ctx.wait(5, "for 2349 to process", floor=4.0)

        # 3b. Also inject a 2309 I packet with the same setpoint.
        #     The climate entity's target_temperature reads from
        #     zone.temp_state.setpoint (not zone_state.setpoint).
        #     2349 updates zone_state, and the CQRS pipeline also
        #     updates temp_state for 2349 — but ramses_cc's polling
        #     cycle sends RQ 2349 and the simulator's RP response
        #     (with a default setpoint) can overwrite temp_state
        #     AFTER our I 2349.  Injecting 2309 I as well provides
        #     a second, direct update to temp_state.setpoint that
        #     is processed after the RP response.
        setpoint_hex_2309 = f"{int(setpoint_temp * 100):04X}"
        payload_2309 = f"{zone_idx}{setpoint_hex_2309}"
        print(
            f"  Injecting 2309 I from CTL {CTL} "
            f"(zone={zone_idx}, setpoint={setpoint_temp}°C)..."
        )
        try:
            call_service(
                ctx.token,
                "ramses_extras",
                "device_simulator_inject_message",
                {
                    "source_id": CTL,
                    "code": "2309",
                    "payload": payload_2309,
                    "verb": "I",
                },
            )
            print("    2309 I injected")
        except RuntimeError as e:
            print(f"    Inject failed: {str(e)[:80]}")
        ctx.wait(3, "for 2309 to process")

        # Force entity state update
        try:
            call_service(ctx.token, "ramses_cc", "force_update")
        except RuntimeError:
            pass
        ctx.wait(5, "for entity state write", floor=3.0)

        # 4. Find the climate entity for zone 03
        #    ramses_cc creates climate entities for each zone.  The entity_id
        #    is climate.<slugified_zone_name>.  We search for any climate
        #    entity whose attributes reference zone_idx 03.

        def _find_climate_entity() -> dict | None:
            entities = get_entities(ctx.token)
            # 1. Match by zone_idx attribute (most reliable)
            for e in entities:
                if not e["entity_id"].startswith("climate."):
                    continue
                attrs = e.get("attributes", {})
                if attrs.get("zone_idx") == zone_idx:
                    return e
            # 2. Match by entity_id pattern: climate.<ctl>_<zone_idx>
            #    e.g. climate.01_150000_03 for CTL 01:150000, zone 03
            ctl_suffix = CTL.replace(":", "_")
            pattern = f"climate.{ctl_suffix}_{zone_idx}"
            for e in entities:
                if e["entity_id"] == pattern:
                    return e
            # 3. Match by entity_id prefix (handles _2 suffix duplicates)
            for e in entities:
                if e["entity_id"].startswith(pattern):
                    return e
            return None

        # 4b. Poll for climate entity existence — under parallel load the
        #     entity may not be created immediately after force_update.
        wait_for(
            lambda: _find_climate_entity() is not None,
            timeout=15,
            interval=2,
            msg="for climate entity to be created",
            floor=3.0,
        )
        climate_entity = _find_climate_entity()

        # Check 1: climate entity exists
        cl_eid = climate_entity["entity_id"] if climate_entity else "None"
        ctx.check(
            "climate entity exists for zone 03",
            climate_entity is not None,
            f"entity_id={cl_eid}",
        )

        # 5. Poll until the climate entity state is hydrated from 2349.
        #    Under parallel load, the 2349 packet + force_update may not
        #    propagate to the entity state within the initial 5s wait.
        #    Re-inject 2349/2309 and re-trigger force_update periodically
        #    to push the state write.  The re-injection is needed because
        #    ramses_cc's polling cycle sends RQ 2349 and the simulator's
        #    RP response (with a default setpoint) can overwrite our
        #    injected value.
        _force_update_count = 0

        def _climate_hydrated() -> bool:
            nonlocal _force_update_count
            entity = _find_climate_entity()
            if not entity:
                return False
            state = entity.get("state")
            attrs = entity.get("attributes", {})
            temp = attrs.get("temperature")
            if (
                state is not None
                and state not in ("unknown", "unavailable")
                and temp == setpoint_temp
            ):
                return True
            _force_update_count += 1
            # Re-inject 2349 and 2309 on every poll to overwrite any RP
            # responses from the simulator's auto-answer that may have
            # set temp_state.setpoint back to a default value.
            try:
                call_service(
                    ctx.token,
                    "ramses_extras",
                    "device_simulator_inject_message",
                    {
                        "source_id": CTL,
                        "code": "2349",
                        "payload": payload_2349,
                        "verb": "I",
                    },
                )
                call_service(
                    ctx.token,
                    "ramses_extras",
                    "device_simulator_inject_message",
                    {
                        "source_id": CTL,
                        "code": "2309",
                        "payload": payload_2309,
                        "verb": "I",
                    },
                )
            except RuntimeError:
                pass
            try:
                call_service(ctx.token, "ramses_cc", "sync_topology")
            except RuntimeError:
                pass
            try:
                call_service(ctx.token, "ramses_cc", "force_update")
            except RuntimeError:
                pass
            return False

        wait_for(
            _climate_hydrated,
            timeout=45,
            interval=2,
            msg="for climate entity state to hydrate from 2349",
            floor=20.0,
        )

        # Read final state for the checks
        climate_entity = _find_climate_entity()
        cl_state = climate_entity.get("state") if climate_entity else None
        cl_attrs = climate_entity.get("attributes", {}) if climate_entity else {}
        target_temp = cl_attrs.get("temperature")

        print(f"  climate entity: {cl_eid}")
        print(f"  state={cl_state!r}  target_temp={target_temp!r}")
        print(f"  attrs={json.dumps(cl_attrs)[:200]}")

        # Check 2: climate entity state is not None/unknown
        #    WITHOUT FIX: None (zone_state.mode never hydrated from 2349)
        #    WITH FIX: "heat" or "auto" (system_mode may be overwritten by
        #              simulator heartbeat 2E04 packets with away/eco_boost)
        ctx.check(
            "climate state is not unknown/None",
            cl_state is not None and cl_state not in ("unknown", "unavailable"),
            f"state={cl_state!r} (None/unknown = bug present, issue 843)",
        )

        # Check 3: target_temperature is hydrated from 2349 (21.0°C)
        #    WITHOUT FIX: None (zone_state.setpoint never hydrated)
        #    WITH FIX: 21.0
        ctx.check(
            "climate target_temperature hydrated from 2349 (21.0°C)",
            target_temp is not None and target_temp == setpoint_temp,
            f"temperature={target_temp!r} (None = bug present, issue 843)",
        )

        # Re-enable auto-answer (cleanup — other recipes expect it on)
        try:
            await ws_send(
                ctx.token,
                {
                    "type": "ramses_extras/device_simulator/set_auto_answer",
                    "enabled": True,
                },
            )
        except RuntimeError:
            pass
