"""Recipe R137: Real-time new-device notification (issue 1257 item 2.1).

Verifies that ``DiscoveryScan.set_new_device_callback`` (ramses_rf) wired
into the coordinator's debounced discovery checkpoint flags a brand-new
device for review within seconds of its first packet — instead of
waiting for the 5-minute periodic checkpoint.

Proof point: a heartbeat injected mid-session must produce a
``ramses_cc_discovery`` persistent notification listing the new device
in far less than the 5-minute poll interval.

See: https://github.com/ramses-rf/ramses_cc/issues/1257
"""

from __future__ import annotations

import asyncio
import re as _re
import time

from ..base import Recipe, RecipeContext
from ..helpers import (
    call_service,
    get_persistent_notifications,
    load_profile_yaml,
    wait_for_schema_populated,
    wait_for_transport_ready,
)
from ..profile import minimal_ctl_dhw_yaml

# A TRV id not present in any profile or schema — guaranteed unknown.
_NEW_TRV = "04:210001"
_ID_RE = _re.compile(r"`(\d{2}:\d{6})`")


class R137RealtimeNewDeviceNotificationIssue1257(Recipe):
    id = "R137"
    seq = 1370
    title = "Real-time new-device notification (issue 1257, item 2.1)"

    async def _notified_ids(self, ctx: RecipeContext) -> set[str]:
        """Device ids listed in the ramses_cc_discovery notification."""
        try:
            notifications = await get_persistent_notifications(ctx.token)
        except Exception:
            return set()
        if not isinstance(notifications, list):
            return set()
        ids: set[str] = set()
        for n in notifications:
            if n.get("notification_id") == "ramses_cc_discovery":
                ids.update(_ID_RE.findall(n.get("message", "")))
        return ids

    async def run(self, ctx: RecipeContext) -> None:
        ctx.log_section("Recipe 137: Real-time new-device notification")

        # ── 1. Minimal profile: CTL + DHW are schema-known, so their
        #       traffic never produces NEW flags. ─────────────────────
        print("  Loading minimal profile (CTL + DHW)...")
        try:
            await load_profile_yaml(
                ctx.token,
                minimal_ctl_dhw_yaml(),
                speed=0.01,
                preload_schema=True,
                reload_ramses=True,
            )
        except RuntimeError as e:
            ctx.check(
                "Profile loaded for R137",
                False,
                f"Profile load failed: {str(e)[:100]}",
            )
            return
        ctx.wait_for_ramses_cc_reload(timeout=20)
        ctx.refresh_token()
        wait_for_transport_ready(timeout=30)
        wait_for_schema_populated(min_keys=3, timeout=15)

        # ── 2. Inject a heartbeat from a brand-new device ─────────────
        print(f"  Injecting 1FC9 heartbeat from {_NEW_TRV}...")
        t0 = time.monotonic()
        for i in range(3):
            try:
                call_service(
                    ctx.token,
                    "ramses_extras",
                    "device_simulator_inject_message",
                    {
                        "source_id": _NEW_TRV,
                        "code": "1FC9",
                        "payload": "0030C912E294",
                        "verb": "I",
                    },
                )
            except RuntimeError as e:
                print(f"  Inject {i} failed: {str(e)[:60]}")
            time.sleep(2)

        # ── 3. The new device must be flagged in the discovery
        #       notification quickly.  Without the real-time callback a
        #       mid-session device only surfaces at the next 5-minute
        #       checkpoint — a 60s window proves the callback path. ────
        notified = _NEW_TRV in await self._notified_ids(ctx)
        deadline = time.monotonic() + 60
        while not notified and time.monotonic() < deadline:
            await asyncio.sleep(2)
            notified = _NEW_TRV in await self._notified_ids(ctx)
        elapsed = time.monotonic() - t0
        print(f"  {_NEW_TRV} notified after {elapsed:.1f}s")

        ctx.check(
            f"new device {_NEW_TRV} in discovery notification within 60s",
            notified,
            f"notified_ids={sorted(await self._notified_ids(ctx))}",
        )
        ctx.check(
            "notification fired well under the 5-min poll interval",
            notified and elapsed < 60,
            f"elapsed={elapsed:.1f}s",
        )
