"""Recipe R118: Live TX/RX after transport type switch (all verbs).

Verifies that TX/RX works for RQ, I, and W frames after switching
_preferred_type back and forth.  Uses the HA websocket API to update
config entry options.
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


class R118TxRxAfterSwitch(Recipe):
    id = "R118"
    seq = 1180
    title = "Live TX/RX (all verbs) after transport type switch (issue 1185)"
    tags = (
        "pooled",
        "multi-hgi",
        "phase2",
        "tx",
        "rx",
        "switching",
        "issue-1185",
        "live",
    )

    async def run(self, ctx: RecipeContext) -> None:
        """Verify TX/RX for all verbs after transport type switch."""
        ctx.log_section("Recipe 118: TX/RX after transport type switch")
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
        hgi_secondary = "18:149488"

        def grep_log(pattern: str, tail: int = 5) -> str:
            r = subprocess.run(
                [
                    "docker",
                    "exec",
                    inst.name,
                    "bash",
                    "-c",
                    f"tail -n 500 /config/home-assistant.log"
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

        def send_and_verify(verb: str, code: str, payload: str, label: str) -> bool:
            """Send a packet and verify TX + echo in the log."""
            try:
                call_service(
                    ctx.token,
                    "ramses_cc",
                    "send_packet",
                    {
                        "device_id": "01:150000",
                        "verb": verb,
                        "code": code,
                        "payload": payload,
                    },
                )
            except Exception:
                pass
            ctx.wait(3, f"for {label} in log", floor=2)
            tx = grep_log(f"TX.*{code}|{code}.*TX", tail=3)
            echo = grep_log(f"echo.*{code}|{code}.*echo", tail=3)
            return bool(tx) and bool(echo)

        # Baseline
        ctx.check(
            "Baseline: RQ 3150 TX + echo",
            send_and_verify("RQ", "3150", "00", "RQ 3150"),
        )
        ctx.check(
            "Baseline: I 1F09 TX + echo", send_and_verify("I", "1F09", "00", "I 1F09")
        )
        ctx.check(
            "Baseline: W 2309 TX + echo", send_and_verify("W", "2309", "0001", "W 2309")
        )

        # Switch secondary to usb
        ctx.check(
            "Switch secondary to usb", await switch_and_wait(hgi_secondary, "usb")
        )
        ctx.check(
            "After usb switch: RQ 3150 TX + echo",
            send_and_verify("RQ", "3150", "00", "RQ 3150"),
        )
        ctx.check(
            "After usb switch: I 1F09 TX + echo",
            send_and_verify("I", "1F09", "00", "I 1F09"),
        )
        ctx.check(
            "After usb switch: W 2309 TX + echo",
            send_and_verify("W", "2309", "0001", "W 2309"),
        )

        # Switch secondary back to mqtt
        ctx.check(
            "Switch secondary back to mqtt",
            await switch_and_wait(hgi_secondary, "mqtt"),
        )
        ctx.check(
            "After mqtt restore: RQ 3150 TX + echo",
            send_and_verify("RQ", "3150", "00", "RQ 3150"),
        )
        ctx.check(
            "After mqtt restore: I 1F09 TX + echo",
            send_and_verify("I", "1F09", "00", "I 1F09"),
        )
        ctx.check(
            "After mqtt restore: W 2309 TX + echo",
            send_and_verify("W", "2309", "0001", "W 2309"),
        )

        # No final echo timeouts (intermediate retries are OK)
        timeouts = grep_log("Echo timeout.*attempt 3/3", tail=10)
        ctx.check(
            "No final echo timeouts during switching",
            not timeouts,
            detail=f"Final timeouts: {timeouts[:200] if timeouts else 'none'}",
        )

        ctx.check("All TX/RX after switch checks passed", ctx.failed == failed_at_start)
