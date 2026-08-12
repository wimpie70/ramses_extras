"""Recipe R19: Zone binding from broadcast traffic (passive scan) [A]."""

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
    is_ramses_cc_loaded,
    load_profile_yaml,
    wait_for,
    wait_for_discovered_device,
    wait_for_schema_populated,
    write_ramses_storage,
    ws_send,
)
from ..profile import MIXED_KL, MIXED_SCHEMA, mixed_yaml


class R19ZoneBindingFromBroadcastTrafficPassiveScanA(Recipe):
    id = "R19"
    seq = 190
    title = "Zone binding from broadcast traffic (passive scan) [A]"

    async def run(self, ctx: RecipeContext) -> None:
        ctx.log_section("Recipe 19: Zone binding from broadcast TRV traffic")

        # TRVs broadcast zone-binding codes (30C9, 3150, 2309) with dst=--:------.
        # The scan engine captures zone_idx from the payload even for broadcasts.
        # sync_learned_topology should then infer the CTL from main_tcs and add
        # the TRV as a zone sensor.
        # We need a CTL in the known_list for zones to be created, so we load
        # the mixed profile (which has CTL + FAN + REM) instead of fresh_start.

        # Load mixed profile (has CTL for zone creation)
        # Use reload_ramses_cc=False to avoid restarting the ramses_rf MQTT
        # transport, which can destabilise on warm-started containers (the
        # broker disconnects the new client before the old one is cleaned up).
        # The mixed profile is already loaded in the setup phase; this reload
        # just ensures a clean schema without breaking the transport.
        print("  Loading mixed profile (has CTL for zone creation)...")
        try:
            await ws_send(
                ctx.token,
                {
                    "type": "ramses_extras/device_simulator/load_profile",
                    "profile": "mixed",
                    "speed": 0.01,
                    "preload_schema": True,
                    "reload_ramses_cc": False,
                    "enable_auto_answer": True,
                },
            )
            print("  mixed profile loaded")
        except RuntimeError as e:
            print(f"  Profile load failed: {e}")
        ctx.wait_for_ramses_cc_reload(timeout=20)
        ctx.refresh_token()
        # Activate CTL for heartbeats
        try:
            await ws_send(
                ctx.token,
                {
                    "type": "ramses_extras/device_simulator/activate_profile_device",
                    "device_id": CTL,
                },
            )
        except RuntimeError:
            pass
        wait_for_schema_populated(timeout=15)

        # Inject 30C9 (temperature) broadcast packets from TRVs with zone_idx
        # 30C9 payload: zone_idx(2 hex) + temperature(4 hex, *100)
        # Use valid zone indices 02-0B (ramses_rf max 12 zones: 00-0B)
        broadcast_trvs = [
            ("04:200002", "02"),
            ("04:200003", "03"),
            ("04:200004", "04"),
            ("04:200005", "05"),
        ]
        temp_hex = "0708"  # 18.00C

        print(f"  Injecting 30C9 broadcast packets from {len(broadcast_trvs)} TRVs...")
        for trv_id, zone_idx in broadcast_trvs:
            payload = f"{zone_idx}{temp_hex}"
            try:
                call_service(
                    ctx.token,
                    "ramses_extras",
                    "device_simulator_inject_message",
                    {
                        "source_id": trv_id,
                        "code": "30C9",
                        "payload": payload,
                        "verb": "I",
                    },
                )
                print(f"    {trv_id} -> zone {zone_idx}: 30C9 payload={payload}")
            except RuntimeError as e:
                print(f"    {trv_id} -> zone {zone_idx}: FAILED - {str(e)[:80]}")
            time.sleep(0.5)

        # Also inject 3150 (heat demand) — another zone-binding code
        print("  Injecting 3150 (heat demand) broadcast packets...")
        for trv_id, zone_idx in broadcast_trvs:
            payload = f"{zone_idx}00"
            try:
                call_service(
                    ctx.token,
                    "ramses_extras",
                    "device_simulator_inject_message",
                    {
                        "source_id": trv_id,
                        "code": "3150",
                        "payload": payload,
                        "verb": "I",
                    },
                )
            except RuntimeError as e:
                print(f"    {trv_id} -> 3150: FAILED - {str(e)[:80]}")
            time.sleep(0.5)

        # Accept the discovered TRVs (polls until scan engine has them)
        print("  Accepting discovered TRVs...")
        for trv_id, zone_idx in broadcast_trvs:
            ok = wait_for_discovered_device(ctx.token, trv_id, timeout=15)
            if ok:
                print(f"    {trv_id} accepted")
            else:
                print(f"    {trv_id} accept timed out")
        ctx.wait(3, "for ramses_rf include list update")

        # Trigger sync_topology to update the schema
        print("  Triggering sync_topology...")
        try:
            call_service(ctx.token, "ramses_cc", "sync_topology")
        except RuntimeError as e:
            print(f"  sync_topology failed: {e}")
        ctx.wait_for_schema_stable(timeout=10, msg="for sync_learned_topology")
        try:
            call_service(ctx.token, "ramses_cc", "force_update")
        except RuntimeError:
            pass
        ctx.wait_for_schema_stable(timeout=10, msg="for save_client_state")

        # Check that zones were created from broadcast traffic
        schema_r19 = get_schema_retry()
        ctl_r19 = schema_r19.get(CTL, {})
        zones_r19 = ctl_r19.get("zones", {}) if isinstance(ctl_r19, dict) else {}
        zone_ids_r19 = list(zones_r19.keys())
        print(f"  Zones from broadcast: {zone_ids_r19}")

        for trv_id, zone_idx in broadcast_trvs:
            zone = zones_r19.get(zone_idx, {})
            sensor = zone.get("sensor") if isinstance(zone, dict) else None
            actuators = zone.get("actuators", []) if isinstance(zone, dict) else []
            # TRV should be in the zone — as sensor if the zone had no sensor,
            # or as actuator if the zone already had a sensor (from CTL config)
            ctx.check(
                f"TRV {trv_id} added to zone {zone_idx}",
                sensor == trv_id or trv_id in actuators,
                f"zone_{zone_idx}={json.dumps(zone)[:100]}",
            )

        # Check that device_comments include zone info
        comments_r19 = schema_r19.get("device_comments", {})
        for trv_id, zone_idx in broadcast_trvs:
            comment = comments_r19.get(trv_id, "")
            ctx.check(
                f"Comment for {trv_id} includes zone {zone_idx}",
                f"zone {zone_idx}" in comment,
                f"comment={comment[:100]}",
            )
