"""Recipe R21: CTL (01:) does not get zone_idx from 000A packets."""

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


class R21Ctl01DoesNotGetZoneIdxFrom000aPackets(Recipe):
    id = "R21"
    seq = 220
    title = "CTL (01:) does not get zone_idx from 000A packets"

    async def run(self, ctx: RecipeContext) -> None:
        # The CTL sends 000A with zone config for multiple zones.  The first 2
        # hex chars are the zone being configured, NOT the CTL's own zone.
        # The scan engine must NOT set zone_idx on the CTL (issue 813).
        ctx.log_section("Recipe 21: CTL (01:) does not get zone_idx from 000A")

        # Load mixed profile (has CTL 01:150000 as main_tcs)
        print("  Loading mixed profile via websocket...")
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

        # Inject 000A from CTL with zone 02 payload
        # 000A I payload: zone_idx(2) + bitmap(2) + min_temp(4) + max_temp(4) = 12 hex
        ctl_r21 = CTL  # 01:150000
        print(f"  Injecting 000A from CTL {ctl_r21} with zone 02 payload...")
        try:
            call_service(
                ctx.token,
                "ramses_extras",
                "device_simulator_inject_message",
                {
                    "source_id": ctl_r21,
                    "code": "000A",
                    "payload": "020008000200",
                    "verb": "I",
                },
            )
            print(f"    000A injected from {ctl_r21} (zone 02)")
        except RuntimeError as e:
            print(f"    Inject failed: {str(e)[:80]}")

        # Also inject 000A with a different zone (05) to verify CTL doesn't
        # pick up any zone
        ctx.wait(2, "between injects")
        print(f"  Injecting 000A from CTL {ctl_r21} with zone 05 payload...")
        try:
            call_service(
                ctx.token,
                "ramses_extras",
                "device_simulator_inject_message",
                {
                    "source_id": ctl_r21,
                    "code": "000A",
                    "payload": "050008000500",
                    "verb": "I",
                },
            )
            print(f"    000A injected from {ctl_r21} (zone 05)")
        except RuntimeError as e:
            print(f"    Inject failed: {str(e)[:80]}")

        ctx.wait(5, "for scan engine to process")
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

        schema_r21 = get_schema_retry()
        comments_r21 = schema_r21.get("device_comments", {})
        ctl_comment_r21 = comments_r21.get(ctl_r21, "")

        # CTL comment should NOT contain "zone 02" or "zone 05"
        ctx.check(
            "CTL comment has no zone 02 from 000A",
            "zone 02" not in ctl_comment_r21,
            f"comment={ctl_comment_r21[:120]}",
        )
        ctx.check(
            "CTL comment has no zone 05 from 000A",
            "zone 05" not in ctl_comment_r21,
            f"comment={ctl_comment_r21[:120]}",
        )

        # CTL should NOT be a zone sensor for zones 02-08 (the 000A packets
        # we injected were for zones 02 and 05).  Zone 01 is the CTL's own
        # zone — it IS the sensor for zone 01 in the RAMSES protocol, so we
        # skip that check.
        ctl_zones_r21 = schema_r21.get(ctl_r21, {}).get("zones", {})
        for zid, zone in ctl_zones_r21.items():
            if zid == "01":
                continue  # CTL is legitimately the sensor for its own zone 01
            if isinstance(zone, dict):
                ctx.check(
                    f"CTL not sensor of zone {zid}",
                    zone.get("sensor") != ctl_r21,
                    f"sensor={zone.get('sensor')}",
                )
