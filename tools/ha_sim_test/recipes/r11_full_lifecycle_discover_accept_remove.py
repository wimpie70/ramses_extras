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
    get_current_instance,
    get_entities,
    get_entity_attributes,
    get_known_list,
    get_persistent_notifications,
    get_ramses_storage,
    get_schema,
    get_schema_retry,
    grep_ha_log,
    is_ramses_cc_loaded,
    load_profile_yaml,
    wait_for,
    wait_for_transport_ready,
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

        ctx.wait_for_ramses_cc_reload(timeout=20)
        ctx.refresh_token()
        # Wait for the MQTT transport to reconnect after the reload,
        # otherwise injected packets are silently dropped.
        wait_for_transport_ready(timeout=30)

        # Wait for the DiscoveryManager to start before injecting heartbeats.
        # The fresh_start profile reload triggers a new DiscoveryScan that
        # replaces the old one.  If we inject 1FC9 before the new scan starts,
        # the heartbeats are detected by the old scan and lost when the new
        # scan starts (it only imports devices from the schema, which doesn't
        # include the new TRV).
        #
        # Count the "started" lines before the reload and wait for the
        # count to increase — otherwise the wait_for would match stale
        # "started" lines from previous recipes in the docker logs.
        def _count_discovery_starts() -> int:
            inst = get_current_instance()
            result = subprocess.run(
                ["docker", "logs", inst.name],
                capture_output=True,
                text=True,
                timeout=15,
            )
            logs = (result.stderr or "") + (result.stdout or "")
            return logs.count("DiscoveryManager: started (passive scan running)")

        _discovery_count_before = _count_discovery_starts()

        def _discovery_started() -> bool:
            return _count_discovery_starts() > _discovery_count_before

        wait_for(
            _discovery_started,
            timeout=30,
            interval=2,
            msg="for DiscoveryManager to start",
            floor=15.0,
        )

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

        # Poll for the TRV appearing in discovery scan logs
        def _trv_discovered() -> bool:
            return len(grep_ha_log(new_trv.replace(":", "_"), since_lines=200)) > 0

        wait_for(
            _trv_discovered,
            timeout=20,
            interval=2,
            msg="for discovery scan to detect the new TRV",
            floor=5.0,
        )

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
            wait_for(
                lambda: new_trv in get_known_list(),
                timeout=10,
                interval=1,
                msg="for ramses_rf include list update",
                floor=2.0,
            )

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

            # Poll for the TRV entity to appear
            def _trv_entity_created() -> bool:
                entities = get_entities(ctx.token)
                return find_entity_for_device(entities, new_trv) is not None

            wait_for(
                _trv_entity_created,
                timeout=15,
                interval=2,
                msg="for entity creation + state propagation",
                floor=3.0,
            )

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

                def _trv_removed() -> bool:
                    schema = get_schema_retry()
                    return new_trv not in json.dumps(schema)

                wait_for(
                    _trv_removed,
                    timeout=15,
                    interval=1,
                    msg=f"TRV {new_trv} to be removed from schema",
                    floor=5.0,
                )

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
            ctx.wait_for_ramses_cc_reload(timeout=20)
        except RuntimeError as e:
            print(f"  Mixed profile reload failed: {e}")
