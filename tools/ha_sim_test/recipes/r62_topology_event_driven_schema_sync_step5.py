"""Recipe R62: Topology event-driven schema sync (Phase 4 Step 5).

Verifies that ramses_cc's ``Gateway.set_schema_updated_callback``
subscription writes topology changes back to the config entry
near-real-time, instead of waiting up to ``SAVE_STATE_INTERVAL`` (5 min)
for the polling fallback.

Test flow:
  1. Load fresh_start profile (empty schema, enforce_known_list=False).
  2. Inject a 1FC9 heartbeat from a new TRV to trigger discovery.
  3. Accept the discovered device — this promotes its class and adds it
     to the schema via a ``TopologyChangedEvent``.
  4. Assert the config entry's ``CONF_SCHEMA`` is updated within 10
     seconds (well under the 5-min polling interval), proving the
     event-driven path fired.
  5. Inject a burst of 3 more 1FC9 packets from a second new TRV and
     verify the schema updates again within 10 seconds (debounced
     single write, not 3 separate writes).
  6. Verify no unexpected errors in the HA log.

See:
  https://github.com/ramses-rf/ramses_rf/pull/997 (event bus & handshake)
  ramses_cc coordinator.py: ``_on_rf_schema_updated``,
  ``_debounced_topology_sync``, ``set_schema_updated_callback``
"""

from __future__ import annotations

import json
import subprocess
import time
from datetime import datetime as dt

from ..base import Recipe, RecipeContext
from ..helpers import (
    call_service,
    get_schema_retry,
    grep_ha_log,
    wait_for,
)


class R62TopologyEventDrivenSchemaSyncStep5(Recipe):
    id = "R62"
    seq = 620
    title = "Topology event-driven schema sync (Phase 4 Step 5)"

    async def run(self, ctx: RecipeContext) -> None:
        ctx.log_section("Recipe 62: Topology event-driven schema sync (Step 5)")

        # Use device IDs that aren't in any profile or schema.
        new_trv_1 = "04:200062"
        new_trv_2 = "04:200063"

        # ── 1. Load fresh_start profile ──────────────────────────────────
        print("  Loading fresh_start_allow_unknown_devices_fast_heartbeat...")
        try:
            from ..helpers import ws_send

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

        # Wait for DiscoveryManager to start (count-based to avoid stale
        # log matches from previous recipes — same pattern as R11).
        def _count_discovery_starts() -> int:
            inst_name = _get_container_name()
            result = subprocess.run(
                ["docker", "logs", inst_name],
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
            floor=10.0,
        )

        # ── 2. Inject 1FC9 from new TRV to trigger discovery ─────────────
        print(f"  Injecting 1FC9 heartbeats from {new_trv_1}...")
        for i in range(3):
            try:
                call_service(
                    ctx.token,
                    "ramses_extras",
                    "device_simulator_inject_message",
                    {
                        "source_id": new_trv_1,
                        "code": "1FC9",
                        "payload": "0030C912E294",
                        "verb": "I",
                    },
                )
            except RuntimeError as e:
                print(f"  Inject {i} failed: {str(e)[:60]}")
            time.sleep(2)

        # Wait for discovery scan to detect the TRV
        def _trv_discovered() -> bool:
            return len(grep_ha_log(new_trv_1.replace(":", "_"), since_lines=200)) > 0

        wait_for(
            _trv_discovered,
            timeout=20,
            interval=2,
            msg="for discovery scan to detect the new TRV",
            floor=3.0,
        )

        # ── 3. Accept the discovered device ──────────────────────────────
        print(f"  Accepting discovered device {new_trv_1}...")
        accept_ok = False
        try:
            call_service(
                ctx.token,
                "ramses_cc",
                "accept_discovered_device",
                {"device_id": new_trv_1},
            )
            print("  accept_discovered_device succeeded")
            accept_ok = True
        except RuntimeError as e:
            print(f"  accept_discovered_device failed: {str(e)[:80]}")

        ctx.check(
            "TRV discovered and accepted",
            accept_ok,
            "accept_discovered_device raised error",
        )

        if not accept_ok:
            # Can't continue without the accept
            await self._restore_mixed_profile(ctx)
            return

        # ── 4. Assert schema updates within 10s (event-driven, not poll) ─
        # The polling fallback runs every 5 minutes.  If the schema
        # updates within 10 seconds, it MUST be the event-driven path.
        _accept_time = dt.now()
        print(f"  Waiting for schema to include {new_trv_1} (event-driven)...")

        def _trv_in_schema() -> bool:
            schema = get_schema_retry(max_tries=3, delay=1)
            return new_trv_1 in json.dumps(schema)

        schema_updated = wait_for(
            _trv_in_schema,
            timeout=10,
            interval=1,
            msg=f"for {new_trv_1} to appear in schema (event-driven)",
            floor=3.0,
        )

        _update_time = dt.now()
        _elapsed = (_update_time - _accept_time).total_seconds()

        _timeout_note = (
            " (timeout — polling fallback may be needed)" if not schema_updated else ""
        )
        ctx.check(
            "Schema updated within 10s (event-driven, not 5-min poll)",
            schema_updated,
            f"elapsed={_elapsed:.1f}s{_timeout_note}",
        )

        if schema_updated:
            ctx.check(
                "Schema update was fast (< 30s, well under 5-min poll)",
                _elapsed < 30,
                f"elapsed={_elapsed:.1f}s",
            )

        # ── 5. Burst test: 3 rapid 1FC9 from a second TRV ────────────────
        # Inject 3 1FC9 packets in rapid succession.  The debounce should
        # coalesce them into a single save cycle.  We verify the second
        # TRV appears in the schema within 10s (event-driven) — we can't
        # easily count config-entry writes from outside, but the fast
        # update proves the event path is working for the burst too.
        print(f"  Injecting burst of 3x 1FC9 from {new_trv_2}...")
        for i in range(3):
            try:
                call_service(
                    ctx.token,
                    "ramses_extras",
                    "device_simulator_inject_message",
                    {
                        "source_id": new_trv_2,
                        "code": "1FC9",
                        "payload": "0030C912E294",
                        "verb": "I",
                    },
                )
            except RuntimeError:
                pass
            time.sleep(0.5)  # rapid burst — 0.5s apart

        # Wait for discovery + accept
        def _trv2_discovered() -> bool:
            return len(grep_ha_log(new_trv_2.replace(":", "_"), since_lines=200)) > 0

        wait_for(
            _trv2_discovered,
            timeout=20,
            interval=2,
            msg=f"for discovery scan to detect {new_trv_2}",
            floor=3.0,
        )

        try:
            call_service(
                ctx.token,
                "ramses_cc",
                "accept_discovered_device",
                {"device_id": new_trv_2},
            )
            print(f"  accept_discovered_device succeeded for {new_trv_2}")
        except RuntimeError as e:
            print(f"  accept_discovered_device failed for {new_trv_2}: {str(e)[:80]}")

        _burst_accept_time = dt.now()

        def _trv2_in_schema() -> bool:
            schema = get_schema_retry(max_tries=3, delay=1)
            return new_trv_2 in json.dumps(schema)

        burst_updated = wait_for(
            _trv2_in_schema,
            timeout=10,
            interval=1,
            msg=f"for {new_trv_2} to appear in schema (burst, event-driven)",
            floor=3.0,
        )

        _burst_update_time = dt.now()
        _burst_elapsed = (_burst_update_time - _burst_accept_time).total_seconds()

        ctx.check(
            "Burst: schema updated within 10s (debounced event-driven)",
            burst_updated,
            f"elapsed={_burst_elapsed:.1f}s",
        )

        # ── 6. Verify both TRVs are in the final schema ──────────────────
        final_schema = get_schema_retry()
        ctx.check(
            f"Both TRVs in final schema ({new_trv_1}, {new_trv_2})",
            new_trv_1 in json.dumps(final_schema)
            and new_trv_2 in json.dumps(final_schema),
            f"schema keys={list(final_schema.keys())[:10]}",
        )

        # ── 7. Cleanup: restore mixed profile ────────────────────────────
        await self._restore_mixed_profile(ctx)

    async def _restore_mixed_profile(self, ctx: RecipeContext) -> None:
        """Restore the mixed profile for subsequent recipes."""
        print("  Reloading mixed profile...")
        try:
            from ..helpers import ws_send

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


def _get_container_name() -> str:
    """Get the current container name from the helpers contextvar."""
    from ..helpers import get_current_instance

    return get_current_instance().name
