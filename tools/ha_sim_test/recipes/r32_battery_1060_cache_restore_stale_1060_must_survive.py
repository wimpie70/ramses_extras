"""Recipe R32: Battery (1060) cache restore — stale 1060 must survive."""

from __future__ import annotations

import json
import subprocess
import time
import urllib.request
from datetime import UTC, timedelta
from datetime import datetime as dt

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


class R32Battery1060CacheRestoreStale1060MustSurvive(Recipe):
    id = "R32"
    seq = 340
    title = "Battery (1060) cache restore — stale 1060 must survive"

    async def run(self, ctx: RecipeContext) -> None:
        # Same regression class as issue 822 / 0004 zone names: 1060
        # (device_battery) was in HIGH_VOLUME_STATUS_CODES but is sent only
        # 1/day, so a cached 1060 older than 1h was skipped by
        # _restore_cached_packets on restart and the battery binary sensor went
        # Unknown.  Tracked in issue 840 (with before/after screenshots +
        # ramses_cc.zip from before restart).
        #
        # The ha-sim TRV emits 1060 every 13.5s (TRV.yaml), so the bug does NOT
        # manifest naturally — we must age the cached 1060 timestamps in
        # .storage/ramses_cc to >1h ago before restarting, reproducing the
        # real-world condition (the only 1060 in cache is >1h old because
        # battery devices send 1/day).
        ctx.log_section("Recipe 32: Battery 1060 cache restore (stale >1h, issue 840)")

        # 1. Load mixed profile + activate CTL/TRV/DHW for heartbeats
        print("  Loading mixed profile (CTL/TRV/DHW for 1060 traffic)...")
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

        for dev_id, name in [(CTL, "CTL"), (TRV, "TRV"), (DHW, "DHW")]:
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
        ctx.wait(15, "for 1060 battery packets to populate message_store")

        # 2. Force a fresh 1060 I from TRV (battery 100%, low=0)
        #    schema: ^0[0-9A-F](FF|[0-9A-F]{2})0[01]$  (idx, level, low_flag)
        #    payload 006400 = idx 00, level 64 (100%), low-flag 00
        print(f"  Injecting 1060 I from TRV {TRV} (battery 100%, low=0)...")
        try:
            call_service(
                ctx.token,
                "ramses_extras",
                "device_simulator_inject_message",
                {
                    "source_id": TRV,
                    "code": "1060",
                    "payload": "006400",
                    "verb": "I",
                },
            )
            print("    1060 I injected")
        except RuntimeError as e:
            print(f"    Inject failed: {str(e)[:80]}")
        ctx.wait(5, "for 1060 to process")
        try:
            call_service(ctx.token, "ramses_cc", "force_update")
        except RuntimeError:
            pass
        ctx.wait(5, "for entity state write")

        # 3. Verify the TRV battery binary sensor has a state before restart
        entities_r32 = get_entities(ctx.token)
        bat_before = find_battery_entity(entities_r32, TRV)
        bat_state_before = bat_before.get("state") if bat_before else None
        bat_eid = bat_before["entity_id"] if bat_before else "None"
        print(f"  Battery entity: {bat_eid}  state={bat_state_before!r}")
        ctx.check(
            "TRV battery binary sensor has state before restart",
            bat_before is not None and bat_state_before in ("on", "off"),
            f"state={bat_state_before!r} entity={bat_eid}",
        )

        # 4. Age every cached 1060 packet to 2h ago in .storage/ramses_cc.
        #    This reproduces the real-world condition: the only 1060 in cache
        #    is >1h old (battery devices send 1/day).  Other codes keep their
        #    real timestamps so the rest of the schema restores normally.
        #    We must stop ha-sim before writing (HA overwrites storage on
        #    shutdown), then start it again to trigger _restore_cached_packets.
        storage_r32 = get_ramses_storage()
        packets_r32 = storage_r32.get("client_state", {}).get("packets", {})
        n_1060 = sum(
            1
            for p in packets_r32.values()
            if isinstance(p, dict) and p.get("code") == "1060"
        )
        print(f"  Found {n_1060} cached 1060 packets to age")
        ctx.check(
            "Cached 1060 packets exist to age",
            n_1060 > 0,
            f"found {n_1060} 1060 in cache (need at least 1)",
        )

        aged_ts = (dt.now(tz=UTC) - timedelta(hours=2)).isoformat(
            timespec="microseconds"
        )
        new_packets_r32: dict = {}
        for ts, pkt in packets_r32.items():
            if isinstance(pkt, dict) and pkt.get("code") == "1060":
                # Collapse all 1060 to one aged timestamp (only the latest
                # matters for restore — ramses_cc keeps the newest per code)
                new_packets_r32[aged_ts] = pkt
            else:
                new_packets_r32[ts] = pkt
        storage_r32["client_state"]["packets"] = new_packets_r32

        # Capture logs before stop (docker stop wipes the in-memory log buffer
        # only on restart, but capture anyway for completeness)
        ctx.log_monitor.capture_before_restart("R32 pre-restart")

        print("  Stopping ha-sim to write aged .storage/ramses_cc...")
        subprocess.run(["docker", "stop", "ha-sim"], capture_output=True)
        ctx.wait(2, "for container to stop")

        wrote = write_ramses_storage(storage_r32)
        ctx.check(
            "Aged .storage/ramses_cc written (1060 timestamps → 2h ago)",
            wrote,
            "write_ramses_storage returned False",
        )

        print("  Starting ha-sim to trigger _restore_cached_packets...")
        subprocess.run(["docker", "start", "ha-sim"], capture_output=True)
        ctx.wait(20, "for ha-sim to start up")
        ctx.log_monitor.reset_baseline()
        ctx.refresh_token()
        ctx.wait(10, "for ramses_cc to restore cached packets + create entities")

        # 5. Check the battery binary sensor state after restart.
        #    WITHOUT FIX (1060 in HIGH_VOLUME_STATUS_CODES): the aged 1060 is
        #      >1h old → skipped by _restore_cached_packets → message_store has
        #      no 1060 → battery entity = Unknown/None.
        #    WITH FIX (1060 removed from HIGH_VOLUME_STATUS_CODES): the aged
        #      1060 is restored → battery entity retains its state.
        entities_r32_after = get_entities(ctx.token)
        bat_after = find_battery_entity(entities_r32_after, TRV)
        bat_state_after = bat_after.get("state") if bat_after else None
        bat_eid_after = bat_after["entity_id"] if bat_after else "None"
        print(f"Battery after restart: {bat_eid_after}  state={bat_state_after!r}")
        ctx.check(
            "TRV battery binary sensor retained state after restart (stale 1060)",
            bat_after is not None and bat_state_after in ("on", "off"),
            f"state={bat_state_after!r} (Unknown/None = bug present, issue 840)",
        )
