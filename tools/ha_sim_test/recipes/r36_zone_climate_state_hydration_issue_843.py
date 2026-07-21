"""Recipe R36: Zone climate state hydration (issue 843)."""

from __future__ import annotations

import json

from ..base import Recipe, RecipeContext
from ..const import CTL
from ..helpers import (
    call_service,
    get_entities,
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
        ctx.wait(15, "for ramses_cc reload with mixed profile")
        ctx.refresh_token()
        ctx.wait(5, "for ramses_cc to initialize")

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
        ctx.wait(10, "for CTL heartbeats + schema population")

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
        ctx.wait(5, "for 2349 to process")

        # Force entity state update
        try:
            call_service(ctx.token, "ramses_cc", "force_update")
        except RuntimeError:
            pass
        ctx.wait(5, "for entity state write")

        # 4. Find the climate entity for zone 03
        #    ramses_cc creates climate entities for each zone.  The entity_id
        #    is climate.<slugified_zone_name>.  We search for any climate
        #    entity whose attributes reference zone_idx 03.
        entities = get_entities(ctx.token)
        climate_entity = None
        for e in entities:
            if not e["entity_id"].startswith("climate."):
                continue
            attrs = e.get("attributes", {})
            # ramses_cc stores the zone_idx in the entity's device or
            # attributes.  Check the unique_id pattern (CTL_zone_idx).
            # Also check if the entity has a temperature attribute (zones
            # do, other climate entities like DHW don't).
            if attrs.get("zone_idx") == zone_idx:
                climate_entity = e
                break

        # Fallback: if no zone_idx attribute, look for the first climate
        # entity that has a temperature attribute (not the DHW water_heater).
        if climate_entity is None:
            for e in entities:
                if not e["entity_id"].startswith("climate."):
                    continue
                attrs = e.get("attributes", {})
                if "temperature" in attrs or "current_temperature" in attrs:
                    climate_entity = e
                    break

        cl_eid = climate_entity["entity_id"] if climate_entity else "None"
        cl_state = climate_entity.get("state") if climate_entity else None
        cl_attrs = climate_entity.get("attributes", {}) if climate_entity else {}
        target_temp = cl_attrs.get("temperature")

        print(f"  climate entity: {cl_eid}")
        print(f"  state={cl_state!r}  target_temp={target_temp!r}")
        print(f"  attrs={json.dumps(cl_attrs)[:200]}")

        # Check 1: climate entity exists
        ctx.check(
            "climate entity exists for zone 03",
            climate_entity is not None,
            f"entity_id={cl_eid}",
        )

        # Check 2: climate entity state is 'heat' (not None/unknown)
        #    WITHOUT FIX: None (zone_state.mode never hydrated from 2349)
        #    WITH FIX: "heat" (system_mode=auto, zone_mode=follow_schedule,
        #              setpoint=21°C > min_temp)
        ctx.check(
            "climate state is 'heat' (not unknown/None)",
            cl_state is not None and cl_state == "heat",
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
