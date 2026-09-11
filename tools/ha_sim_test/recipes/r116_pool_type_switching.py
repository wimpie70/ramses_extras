"""Recipe R116: Live pool type switching via _preferred_type.

Verifies that switching _preferred_type between mqtt and usb at runtime
keeps the pool connected and TX working.  Uses the HA websocket API
(load_profile_yaml) to update the config entry options, since HA caches
config entries in memory and writing to the storage file alone doesn't
update the running instance.
"""

from __future__ import annotations

import subprocess

from ..base import Recipe, RecipeContext
from ..helpers import (
    call_service,
    get_current_instance,
)
from ..multi_hgi_helpers import (
    ensure_multi_hgi_config,
    set_preferred_type_via_profile,
)


class R116PoolTypeSwitching(Recipe):
    id = "R116"
    seq = 1160
    title = "Live pool type switching via _preferred_type (issue 1185)"
    tags = (
        "pooled",
        "multi-hgi",
        "phase2",
        "switching",
        "preferred_type",
        "issue-1185",
        "live",
    )

    async def run(self, ctx: RecipeContext) -> None:
        """Verify live pool type switching."""
        ctx.log_section("Recipe 116: Live pool type switching")
        ctx.wait_for_ramses_cc_loaded(timeout=20)
        ctx.refresh_token()

        # Ensure multi-HGI config is set up (profile load resets schema).
        # Loads a custom profile with both HGIs via websocket.
        await ensure_multi_hgi_config(
            token=ctx.token,
            ha_url=get_current_instance().ha_url,
        )
        ctx.wait_for_ramses_cc_loaded(timeout=30)
        ctx.refresh_token()

        inst = get_current_instance()
        hgi_primary = "18:001234"
        hgi_secondary = "18:149488"

        def grep_log(pattern: str, tail: int = 5) -> str:
            r = subprocess.run(
                [
                    "docker",
                    "exec",
                    inst.name,
                    "bash",
                    "-c",
                    f"tail -n 2000 /config/home-assistant.log"
                    f" | grep -iE '{pattern}' | tail -{tail}",
                ],
                capture_output=True,
                text=True,
            )
            return r.stdout

        async def switch_and_wait(hgi_id: str, ptype: str, label: str) -> bool:
            """Switch _preferred_type via profile load and wait for reload."""
            ok = await set_preferred_type_via_profile(
                container=inst.name,
                hgi_id=hgi_id,
                ptype=ptype,
                token=ctx.token,
                ha_url=inst.ha_url,
            )
            ctx.wait_for_ramses_cc_loaded(timeout=30)
            ctx.refresh_token()
            return ok

        def send_packet() -> None:
            """Send a test packet."""
            try:
                call_service(
                    ctx.token,
                    "ramses_cc",
                    "send_packet",
                    {
                        "device_id": "01:150000",
                        "verb": "RQ",
                        "code": "3150",
                        "payload": "00",
                    },
                )
            except Exception:
                pass

        def check_tx() -> bool:
            """Check if a 3150 TX frame appears in the log."""
            send_packet()
            ctx.wait(3, "for TX frame in log", floor=2)
            logs = grep_log("TX.*3150|3150.*TX", tail=3)
            return bool(logs)

        # ---------------------------------------------------------------------------
        # Test 1: Verify initial state — two MQTT HGIs in pool
        # ---------------------------------------------------------------------------
        logs = grep_log("MqttCallbackPool.*child.*connected", tail=3)
        ctx.check(
            "Initial: 2/2 MQTT children connected",
            "2/2 connected" in logs,
            detail=f"logs: {logs[:200]}",
        )

        # ---------------------------------------------------------------------------
        # Test 2: Switch secondary HGI _preferred_type from mqtt to usb
        # ---------------------------------------------------------------------------
        ctx.check(
            "Switch: secondary _preferred_type set to usb",
            await switch_and_wait(hgi_secondary, "usb", "secondary→usb"),
        )

        # ---------------------------------------------------------------------------
        # Test 3: Pool still has connected children after switch
        # ---------------------------------------------------------------------------
        logs = grep_log("MqttCallbackPool.*child.*connected", tail=3)
        ctx.check(
            "After switch: pool still has connected children",
            "connected" in logs,
            detail=f"logs: {logs[:200]}",
        )

        # ---------------------------------------------------------------------------
        # Test 4: TX works after secondary switch to usb
        # ---------------------------------------------------------------------------
        ctx.check(
            "TX works after secondary switch to usb",
            check_tx(),
            detail="No 3150 TX frame found in log",
        )

        # ---------------------------------------------------------------------------
        # Test 5: Switch secondary back to mqtt
        # ---------------------------------------------------------------------------
        ctx.check(
            "Switch: secondary _preferred_type set back to mqtt",
            await switch_and_wait(hgi_secondary, "mqtt", "secondary→mqtt"),
        )

        # ---------------------------------------------------------------------------
        # Test 6: TX works after switching back to mqtt
        # ---------------------------------------------------------------------------
        ctx.check(
            "TX works after switching back to mqtt",
            check_tx(),
            detail="No 3150 TX frame found in log",
        )

        # ---------------------------------------------------------------------------
        # Test 7: Switch primary to usb
        # ---------------------------------------------------------------------------
        ctx.check(
            "Switch: primary _preferred_type set to usb",
            await switch_and_wait(hgi_primary, "usb", "primary→usb"),
        )

        # ---------------------------------------------------------------------------
        # Test 8: Pool adapts to primary usb switch without crash
        # ---------------------------------------------------------------------------
        error_logs = grep_log("ERROR.*ramses_cc|ERROR.*ramses_tx", tail=3)
        ctx.check(
            "Pool adapts to primary usb switch without crash",
            not error_logs,
            detail=f"Errors: {error_logs[:200] if error_logs else 'none'}",
        )

        # ---------------------------------------------------------------------------
        # Test 9: Switch primary back to mqtt
        # ---------------------------------------------------------------------------
        ctx.check(
            "Switch: primary _preferred_type set back to mqtt",
            await switch_and_wait(hgi_primary, "mqtt", "primary→mqtt"),
        )

        # ---------------------------------------------------------------------------
        # Test 10: TX works after restoring primary to mqtt
        # ---------------------------------------------------------------------------
        ctx.check(
            "TX works after restoring primary to mqtt",
            check_tx(),
            detail="No 3150 TX frame found in log",
        )

        ctx.check(
            "All pool type switching checks passed",
            ctx.failed == 0,
        )
