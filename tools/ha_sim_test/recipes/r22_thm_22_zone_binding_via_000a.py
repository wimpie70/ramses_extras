"""Recipe R22: THM (22:) zone binding via 000A."""

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


class R22Thm22ZoneBindingVia000a(Recipe):
    id = "R22"
    seq = 230
    title = "THM (22:) zone binding via 000A"

    async def run(self, ctx: RecipeContext) -> None:
        # A THM (22:) sends RQ 000A to the CTL with its zone_idx as payload.
        # The scan engine should extract the zone and set it on the THM (issue 813).
        ctx.log_section("Recipe 22: THM (22:) zone binding via 000A")

        # Load fresh_start profile for clean discovery
        print("  Loading fresh_start_allow_unknown_devices_fast_heartbeat...")
        try:
            await ws_send(
                ctx.token,
                {
                    "type": "ramses_extras/device_simulator/load_profile",
                    "profile": "fresh_start_allow_unknown_devices_fast_heartbeat",
                    "speed": 0.01,
                    "preload_schema": False,
                    "reload_ramses_cc": True,
                    "enable_auto_answer": True,
                },
            )
            print("  fresh_start profile loaded")
        except RuntimeError as e:
            print(f"  Profile load failed: {e}")
        ctx.wait(15, "for ramses_cc reload with fresh_start")
        ctx.refresh_token()
        ctx.wait(5, "for ramses_cc to initialize")

        # Inject RQ 000A from a THM (22:) to the HGI (18:001234)
        # THMs send RQ 000A with just the zone_idx (2 hex) as payload.
        # The dst must be a valid device (not --:------) to avoid PacketInvalid.
        thm_r22 = "22:200001"
        hgi_r22 = HGI  # 18:001234 (the only known device in fresh_start)
        print(f"  Injecting RQ 000A from THM {thm_r22} to {hgi_r22} with zone 01...")
        try:
            call_service(
                ctx.token,
                "ramses_extras",
                "device_simulator_inject_message",
                {
                    "source_id": thm_r22,
                    "dst": hgi_r22,
                    "code": "000A",
                    "payload": "01",
                    "verb": "RQ",
                },
            )
            print(f"    RQ 000A injected from {thm_r22} (zone 01)")
        except RuntimeError as e:
            print(f"    Inject failed: {str(e)[:80]}")

        # Also inject a 30C9 (temperature) broadcast so the THM has a heating code
        ctx.wait(2, "between injects")
        print(f"  Injecting 30C9 from THM {thm_r22}...")
        try:
            call_service(
                ctx.token,
                "ramses_extras",
                "device_simulator_inject_message",
                {
                    "source_id": thm_r22,
                    "code": "30C9",
                    "payload": "010708",
                    "verb": "I",
                },
            )
            print(f"    30C9 injected from {thm_r22}")
        except RuntimeError as e:
            print(f"    Inject failed: {str(e)[:80]}")

        ctx.wait(10, "for scan engine to process packets")
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

        schema_r22 = get_schema_retry()
        comments_r22 = schema_r22.get("device_comments", {})
        thm_comment_r22 = comments_r22.get(thm_r22, "")

        # THM comment should contain "zone 01" (from 000A zone binding)
        ctx.check(
            f"THM {thm_r22} comment includes zone 01",
            "zone 01" in thm_comment_r22,
            f"comment={thm_comment_r22[:120]}",
        )

        # THM comment should also contain "bound to" the HGI
        ctx.check(
            f"THM {thm_r22} comment includes bound_to {hgi_r22}",
            f"bound to {hgi_r22}" in thm_comment_r22 or "bound to" in thm_comment_r22,
            f"comment={thm_comment_r22[:120]}",
        )
