"""Recipe R11: Full lifecycle — discover → accept → remove."""

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


class R11FullLifecycleDiscoverAcceptRemove(Recipe):
    id = "R11"
    seq = 90
    title = "Full lifecycle — discover → accept → remove"

    async def run(self, ctx: RecipeContext) -> None:
        ctx.log_section("Recipe 11: Discover → accept → remove lifecycle")

        # Use a brand-new device ID that's not in any profile or schema, so the
        # discovery manager will treat it as truly unknown.
        new_trv = "04:200001"

        # Load fresh_start_allow_unknown_devices_fast_heartbeat profile
        # (enforce_known_list=False, known_list=HGI only, remove_database=True)
        print("  Loading fresh_start_allow_unknown_devices_fast_heartbeat...")
        try:
            result = await ws_send(
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
            print(f"  Profile loaded: {result.get('actions', [])[:3]}")
        except RuntimeError as e:
            print(f"  Profile load failed: {e}")

        ctx.wait(15, "for ramses_cc reload with fresh_start profile")

        # Inject several 1FC9 heartbeats from the new TRV to trigger discovery
        print(f"  Injecting 1FC9 heartbeats from {new_trv}...")
        for i in range(3):
            try:
                call_service(
                    ctx.token,
                    "ramses_extras",
                    "device_simulator_inject_message",
                    {
                        "source_id": new_trv,
                        "code": "1FC9",
                        "payload": "0030C912E294",
                        "verb": "I",
                    },
                )
            except RuntimeError as e:
                print(f"  Inject {i} failed: {str(e)[:60]}")
            time.sleep(2)

        ctx.wait(10, "for discovery scan to detect the new TRV")

        # Try to accept the discovered device
        print(f"  Accepting discovered device {new_trv}...")
        accept_ok = False
        try:
            call_service(
                ctx.token,
                "ramses_cc",
                "accept_discovered_device",
                {
                    "device_id": new_trv,
                },
            )
            print("  accept_discovered_device succeeded")
            accept_ok = True
        except RuntimeError as e:
            print(f"  accept_discovered_device failed: {str(e)[:80]}")

        ctx.check(
            "TRV discovered and accepted",
            accept_ok,
            "accept_discovered_device raised error (TRV not in discovery list)",
        )

        if accept_ok:
            # Wait for the ramses_rf client to update its include list
            ctx.wait(5, "for ramses_rf include list update")

            # Inject a temperature packet so the entity gets a state
            print(f"  Injecting 30C9 temperature from {new_trv}...")
            try:
                call_service(
                    ctx.token,
                    "ramses_extras",
                    "device_simulator_inject_message",
                    {
                        "source_id": new_trv,
                        "code": "30C9",
                        "payload": "00210A",
                        "verb": "I",
                    },
                )
            except RuntimeError:
                pass

            ctx.wait(8, "for entity creation + state propagation")

            # Verify TRV is now in schema (known_list is auto-derived from schema)
            schema_after_accept = get_schema_retry()
            entities_after_accept = get_entities(ctx.token)

            ctx.check(
                "TRV in schema after accept",
                new_trv in json.dumps(schema_after_accept),
                f"schema keys={list(schema_after_accept.keys())[:10]}",
            )
            ctx.check(
                "TRV entity created after accept",
                find_entity_for_device(entities_after_accept, new_trv, prefix="trv_")
                is not None,
                "entity not found",
            )

            # Now remove it
            print(f"  Removing {new_trv}...")
            try:
                call_service(
                    ctx.token,
                    "ramses_cc",
                    "remove_device",
                    {
                        "device_id": new_trv,
                    },
                )
                print("  remove_device succeeded")
                ctx.wait(3, "for coordinator refresh")

                schema_after_remove = get_schema_retry()
                entities_after_remove = get_entities(ctx.token)

                ctx.check(
                    "TRV removed from schema",
                    new_trv not in json.dumps(schema_after_remove),
                    f"schema still has {new_trv}",
                )
                ctx.check(
                    "TRV entity removed",
                    find_entity_for_device(
                        entities_after_remove, new_trv, prefix="trv_"
                    )
                    is None,
                    "entity still exists",
                )
            except RuntimeError as e:
                ctx.check("remove_device after accept", False, str(e)[:80])

        # Reload mixed profile to restore state for subsequent tests
        print("  Reloading mixed profile...")
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
            ctx.wait(15, "for ramses_cc reload + mixed profile")
        except RuntimeError as e:
            print(f"  Mixed profile reload failed: {e}")
