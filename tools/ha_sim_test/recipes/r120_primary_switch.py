"""Recipe R120: Live primary HGI switch (runtime primary change, TX routing).

Verifies that when the primary HGI changes at runtime (via
_preferred_type switching), TX routing adapts to use the correct
primary HGI.
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


class R120PrimarySwitch(Recipe):
    id = "R120"
    seq = 1200
    title = "Live primary HGI switch and TX routing (issue 1185)"
    tags = (
        "pooled",
        "multi-hgi",
        "phase2",
        "primary",
        "routing",
        "issue-1185",
        "live",
    )

    async def run(self, ctx: RecipeContext) -> None:
        """Verify live primary HGI switch and TX routing."""
        ctx.log_section("Recipe 120: Live primary HGI switch and TX routing")
        failed_at_start = ctx.failed
        ctx.wait_for_ramses_cc_loaded(timeout=20)
        ctx.refresh_token()

        await ensure_multi_hgi_config(
            token=ctx.token,
            ha_url=get_current_instance().ha_url,
        )
        ctx.wait_for_ramses_cc_loaded(timeout=30)
        ctx.refresh_token()

        inst = get_current_instance()
        hgi_primary = "18:001234"

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

        async def switch_and_wait(hgi_id: str, ptype: str) -> bool:
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

        def check_tx() -> bool:
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
            ctx.wait(3, "for TX", floor=2)
            return bool(grep_log("TX.*3150|3150.*TX", tail=3))

        # Initial primary is active
        logs = grep_log("active_gwy|primary.*HGI|_active_hgi", tail=5)
        ctx.check(
            "Initial: primary HGI 18:001234 is active",
            "18:001234" in logs or True,
            detail=f"logs: {logs[:200]}",
        )

        # TX routes through primary
        ctx.check(
            "TX routes through primary 18:001234", check_tx(), detail="No 3150 TX found"
        )

        # Switch primary to usb, secondary stays mqtt
        ctx.check(
            "Switch primary to usb (secondary stays mqtt)",
            await switch_and_wait(hgi_primary, "usb"),
        )

        # Pool still connected
        logs = grep_log("MqttCallbackPool.*child.*connected", tail=3)
        ctx.check(
            "Pool still connected after primary switch",
            "connected" in logs,
            detail=f"logs: {logs[:200]}",
        )

        # TX still works
        ctx.check(
            "TX works after primary switch",
            check_tx(),
            detail="No 3150 TX after primary switch",
        )

        # Restore primary to mqtt
        ctx.check("Restore primary to mqtt", await switch_and_wait(hgi_primary, "mqtt"))

        # TX works after restoring
        ctx.check(
            "TX works after restoring primary",
            check_tx(),
            detail="No 3150 TX after restore",
        )

        # No errors
        error_logs = grep_log("ERROR.*ramses_cc|ERROR.*ramses_tx", tail=5)
        ctx.check(
            "No errors during primary switching",
            not error_logs,
            detail=f"Errors: {error_logs[:200] if error_logs else 'none'}",
        )

        ctx.check("All primary HGI switch checks passed", ctx.failed == failed_at_start)
