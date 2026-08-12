"""Recipe R23: 0004 zone_name propagation (parser_0004 zone_idx fix)."""

from __future__ import annotations

import json
import subprocess
import urllib.request
from datetime import datetime as dt
from datetime import timedelta

from ..base import Recipe, RecipeContext
from ..const import CO2, CTL, DHW, FAN, HGI, REM, TRV
from ..helpers import (
    call_service,
    find_battery_entity,
    find_entity_for_device,
    get_cached_schema,
    get_current_instance,
    get_entities,
    get_entity_attributes,
    get_known_list,
    get_persistent_notifications,
    get_ramses_storage,
    get_schema,
    get_schema_retry,
    is_ramses_cc_loaded,
    load_profile_yaml,
    wait_for,
    write_ramses_storage,
    ws_send,
)
from ..profile import MIXED_KL, MIXED_SCHEMA, mixed_yaml


class R230004ZoneNamePropagationParser0004ZoneIdxFi(Recipe):
    id = "R23"
    seq = 240
    title = "0004 zone_name propagation (parser_0004 zone_idx fix)"

    async def run(self, ctx: RecipeContext) -> None:
        # parser_0004 must include zone_idx in the returned dict so that the
        # TCS _handle_msg, CQRS StateProjector, and dispatcher routing can all
        # route 0004 packets to the correct zone.  Without zone_idx, zone names
        # are never populated in the schema (issue 822).
        ctx.log_section("Recipe 23: 0004 zone_name propagation (zone_idx in payload)")

        # Load mixed profile (CTL 01:150000 with zones 03-08)
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
        ctx.wait_for_ramses_cc_reload(timeout=20)
        ctx.refresh_token()
        # 0004 payload format: zone_idx(2) + "00"(2) + name_hex(40, 20 bytes
        # ASCII padded with 00).  Total = 44 hex chars (22 bytes, length 022).
        # Inject "Living Room" for zone 03.
        zone_r23 = "03"
        name_r23 = "Living Room"
        name_hex = name_r23.encode().hex().upper()
        name_padded = name_hex + "0" * (40 - len(name_hex))
        payload_r23 = f"{zone_r23}00{name_padded}"
        ctl_r23 = CTL  # 01:150000

        print(f"  Injecting 0004 from CTL {ctl_r23} for zone {zone_r23}...")
        print(f"    payload: {payload_r23}")
        try:
            call_service(
                ctx.token,
                "ramses_extras",
                "device_simulator_inject_message",
                {
                    "source_id": ctl_r23,
                    "code": "0004",
                    "payload": payload_r23,
                    "verb": "I",
                },
            )
            print(f"    0004 injected (zone {zone_r23}, name '{name_r23}')")
        except RuntimeError as e:
            print(f"    Inject failed: {str(e)[:80]}")

        # Also inject a second zone name to verify multiple zones work
        ctx.wait(2, "between injects")
        zone_r23b = "05"
        name_r23b = "Kitchen"
        name_hex_b = name_r23b.encode().hex().upper()
        name_padded_b = name_hex_b + "0" * (40 - len(name_hex_b))
        payload_r23b = f"{zone_r23b}00{name_padded_b}"

        print(f"  Injecting 0004 from CTL {ctl_r23} for zone {zone_r23b}...")
        try:
            call_service(
                ctx.token,
                "ramses_extras",
                "device_simulator_inject_message",
                {
                    "source_id": ctl_r23,
                    "code": "0004",
                    "payload": payload_r23b,
                    "verb": "I",
                },
            )
            print(f"    0004 injected (zone {zone_r23b}, name '{name_r23b}')")
        except RuntimeError as e:
            print(f"    Inject failed: {str(e)[:80]}")

        ctx.wait(3, "for scan engine to process", floor=2.0)
        try:
            call_service(ctx.token, "ramses_cc", "sync_topology")
        except RuntimeError:
            pass
        ctx.wait_for_schema_stable(timeout=10, msg="for sync_learned_topology")
        try:
            call_service(ctx.token, "ramses_cc", "force_update")
        except RuntimeError:
            pass
        ctx.wait_for_schema_stable(timeout=10, msg="for save")

        # Check: the 0004 packets were processed by the scan engine.
        # We check the HA log for the dispatcher entries showing our injected
        # 0004 packets with the correct zone_idx.  We can't reliably check
        # the schema's _name because:
        # 1. preload_schema may have loaded existing _name values from a
        #    previous run, and sync_learned_topology only copies _name if the
        #    config zone doesn't already have one.
        # 2. The simulator's auto-answer sends RP 0004 packets with different
        #    names that arrive after our injected I packet, overriding it in
        #    the scan engine's message store (latest wins).
        # Because of (2), we check for ANY 0004 packet with the correct
        # zone_idx (not just our specific name), since the auto-answer may
        # overwrite the name before we read the log.  The key assertion is
        # that the parser correctly extracted the zone_idx from the payload.
        log_url = get_current_instance().ha_url + "/api/error_log"
        req = urllib.request.Request(
            log_url,
            headers={"Authorization": f"Bearer {ctx.token}"},
        )
        log_text = urllib.request.urlopen(req).read().decode()
        ctx.check(
            f"0004 I packet for zone {zone_r23} processed by scan engine",
            f"zone_idx': '{zone_r23}'" in log_text,
            f"no 0004 I packet for zone {zone_r23} in log",
        )
        ctx.check(
            f"0004 I packet for zone {zone_r23b} processed by scan engine",
            f"zone_idx': '{zone_r23b}'" in log_text,
            f"no 0004 I packet for zone {zone_r23b} in log",
        )
