"""Recipe R28: Foreign HGI — 0004 zone names not blocked by block_list."""

from __future__ import annotations

import json
import subprocess
import time
import urllib.request
from datetime import datetime as dt
from datetime import timedelta

from ..base import Recipe, RecipeContext
from ..const import CO2, CTL, DHW, FAN, HA_URL, HGI, REM, TRV
from ..helpers import (
    call_service,
    find_battery_entity,
    find_entity_for_device,
    get_cached_schema,
    get_entities,
    get_entity_attributes,
    get_known_list,
    get_persistent_notifications,
    get_ramses_storage,
    get_schema,
    get_schema_retry,
    load_profile_yaml,
    write_ramses_storage,
    ws_send,
)
from ..profile import MIXED_KL, MIXED_SCHEMA, mixed_yaml


class R28ForeignHgi0004ZoneNamesNotBlockedByBlockL(Recipe):
    id = "R28"
    seq = 300
    title = "Foreign HGI — 0004 zone names not blocked by block_list"

    async def run(self, ctx: RecipeContext) -> None:
        # When a foreign HGI (18: with _owner != root _owner) is present,
        # ramses_cc must NOT put it in the block_list.  The controller sends
        # 0004 zone name RPs addressed to the foreign HGI, and the active
        # gateway eavesdrops on those responses.  If the foreign HGI is in
        # the block_list, the protocol filter drops the 0004 RPs before the
        # foreign-HGI exception can fire, and zone names stay None (issue 822).
        ctx.log_section("Recipe 28: Foreign HGI — 0004 zone names not blocked")

        # Build a YAML profile with _owner: me and a foreign HGI 18:999999
        # with _owner: not-me.  The foreign HGI is not in the known_list.
        foreign_hgi_r28 = "18:999999"
        r28_schema = dict(MIXED_SCHEMA)
        r28_schema["_owner"] = "me"
        r28_schema[CTL] = dict(r28_schema.get(CTL, {}))
        r28_schema[CTL]["_owner"] = "me"
        # Add the foreign HGI as a foreign device (not in known_list)
        r28_schema[foreign_hgi_r28] = {"_owner": "not-me"}
        r28_yaml = mixed_yaml(r28_schema)

        print("  Loading profile with foreign HGI 18:999999 (_owner: not-me)...")
        try:
            await load_profile_yaml(ctx.token, r28_yaml, speed=0.01)
            print("  Profile loaded")
        except RuntimeError as e:
            print(f"  Profile load failed: {e}")
        ctx.wait(15, "for ramses_cc reload with foreign HGI profile")
        ctx.refresh_token()
        ctx.wait(5, "for ramses_cc to initialize")

        # Verify the foreign HGI is in the schema
        schema_r28_init = get_schema_retry()
        ctx.check(
            "Foreign HGI 18:999999 is in schema",
            foreign_hgi_r28 in schema_r28_init,
            f"18: keys={[k for k in schema_r28_init if k.startswith('18:')]}",
        )

        # Inject a 0004 RP from CTL to the foreign HGI (zone name "Bedroom")
        zone_r28 = "03"
        name_r28 = "Bedroom"
        name_hex_r28 = name_r28.encode().hex().upper()
        name_padded_r28 = name_hex_r28 + "0" * (40 - len(name_hex_r28))
        payload_r28 = f"{zone_r28}00{name_padded_r28}"

        print(f"  Injecting 0004 RP from CTL {CTL} to foreign HGI {foreign_hgi_r28}...")
        print(f"    payload: {payload_r28} (zone {zone_r28}, name '{name_r28}')")
        try:
            call_service(
                ctx.token,
                "ramses_extras",
                "device_simulator_inject_message",
                {
                    "source_id": CTL,
                    "dst": foreign_hgi_r28,
                    "code": "0004",
                    "payload": payload_r28,
                    "verb": "RP",
                },
            )
            print(f"    0004 RP injected (zone {zone_r28}, name '{name_r28}')")
        except RuntimeError as e:
            print(f"    Inject failed: {str(e)[:80]}")

        ctx.wait(5, "for scan engine to process 0004 RP")
        try:
            call_service(ctx.token, "ramses_cc", "sync_topology")
        except RuntimeError:
            pass
        ctx.wait(5, "for sync_learned_topology")
        try:
            call_service(ctx.token, "ramses_cc", "force_update")
        except RuntimeError:
            pass
        ctx.wait(5, "for save")

        schema_r28 = get_schema_retry()
        ctl_zones_r28 = schema_r28.get(CTL, {}).get("zones", {})

        # Check 1: zone 03 should have _name = "Bedroom" — the 0004 RP was
        # addressed to the foreign HGI but the active gateway eavesdropped on it
        zone_03_r28 = ctl_zones_r28.get(zone_r28, {})
        ctx.check(
            f"Zone {zone_r28} has _name from 0004 RP to foreign HGI",
            isinstance(zone_03_r28, dict) and zone_03_r28.get("_name") == name_r28,
            f"_name={zone_03_r28.get('_name') if isinstance(zone_03_r28, dict) else 'N/A'}",  # noqa: E501
        )

        # Check 2: foreign HGI should NOT be in the block_list (after fix).
        # We can't directly inspect the block_list, but we can verify the
        # foreign HGI is not being filtered by checking that packets from it
        # are processed.  Inject a 30C9 I from the foreign HGI — if it's
        # blocked, the scan engine won't see it.
        print(f"  Injecting 30C9 I from foreign HGI {foreign_hgi_r28}...")
        try:
            call_service(
                ctx.token,
                "ramses_extras",
                "device_simulator_inject_message",
                {
                    "source_id": foreign_hgi_r28,
                    "code": "30C9",
                    "payload": "0308AC",
                    "verb": "I",
                },
            )
            print("    30C9 I injected")
        except RuntimeError as e:
            print(f"    Inject failed: {str(e)[:80]}")

        ctx.wait(5, "for scan engine to process 30C9")
        try:
            call_service(ctx.token, "ramses_cc", "sync_topology")
        except RuntimeError:
            pass
        ctx.wait(5, "for sync_learned_topology")
        try:
            call_service(ctx.token, "ramses_cc", "force_update")
        except RuntimeError:
            pass
        ctx.wait(3, "for save")

        # The foreign HGI should appear in the schema (it was already there
        # from the profile, but the 30C9 should not cause a FILTER EXCEPTION)
        schema_r28b = get_schema_retry()
        ctx.check(
            "Foreign HGI still in schema after 30C9 inject",
            foreign_hgi_r28 in schema_r28b,
            f"keys={[k for k in schema_r28b if k.startswith('18:')]}",
        )
