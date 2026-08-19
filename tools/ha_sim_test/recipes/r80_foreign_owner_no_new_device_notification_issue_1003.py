"""Recipe R80: Foreign-owned device not flagged as "new" (issue 1003).

Verifies that a device in the schema with ``_owner`` different from the
root ``_owner`` (foreign-owned) is NOT flagged as "new device discovered"
on every scan cycle.

The bug (ramses-rf/ramses_cc issue 1003) was that
``_extract_schema_device_ids`` delegated to
``_derive_known_list_from_schema``, which excludes foreign-owned devices
from the known_list (correct for ramses_rf).  But the discovery manager
used the same set to check "is this device already in the schema?" — so
foreign-owned devices were never recognized as configured and got
re-flagged as NEW on every scan.

The fix separates the two concerns:
- ``_derive_known_list_from_schema``: excludes foreign (for ramses_rf)
- ``_extract_schema_device_ids``: includes ALL (for discovery tracking)

This recipe tests the fix by:
1. Loading a profile with a FAN that has a foreign-owned REM in
   orphans_hvac (``_owner: not-me``)
2. Injecting packets from the foreign device so the scan engine sees it
3. Waiting for the discovery checkpoint
4. Verifying no "New devices discovered" notification appears for it

See: https://github.com/ramses-rf/ramses_cc/issues/1003
"""

from __future__ import annotations

import subprocess
import time

from ..base import Recipe, RecipeContext
from ..const import CTL, HGI
from ..helpers import (
    get_current_instance,
    get_persistent_notifications,
    get_schema_retry,
    load_profile_yaml,
    wait_for,
    wait_for_ha_ready,
    wait_for_ramses_cc_loaded,
    wait_for_ramses_extras_ready,
    wait_for_schema_populated,
    ws_send,
)
from ..profile import _build_yaml

# A foreign-owned device — uses a 37: prefix (REM/DIS/CO2 range) so the
# scan engine will classify it.  It's in orphans_hvac with _owner: not-me.
_FOREIGN_DEV = "37:199999"


class R80ForeignOwnerNoNewDeviceNotificationIssue1003(Recipe):
    id = "R80"
    seq = 540
    title = "Foreign-owned device not flagged as new (issue 1003)"

    async def _get_discovery_notifications(self, ctx: RecipeContext) -> list[dict]:
        """Get persistent notifications about newly discovered devices."""
        try:
            notifications = await get_persistent_notifications(ctx.token)
            if not isinstance(notifications, list):
                return []
            result = []
            for n in notifications:
                nid = n.get("notification_id", "")
                title = n.get("title", "")
                if nid == "ramses_cc_discovery" or "new device" in title.lower():
                    result.append(n)
            return result
        except Exception:
            return []

    async def run(self, ctx: RecipeContext) -> None:
        ctx.log_section("Recipe 80: Foreign-owned device not flagged as new")

        # ── 1. Load profile with foreign-owned device ─────────────────
        # The profile has:
        # - HGI (gateway)
        # - CTL (main controller, _owner: me)
        # - A foreign device in orphans_hvac with _owner: not-me
        # The foreign device is NOT in the known_list (it's foreign), so
        # ramses_rf will treat it as unknown.  But it IS in the schema,
        # so the discovery manager should know it's already configured.
        print("  Loading profile with foreign-owned device...")
        kl = {
            HGI: {"class": "HGI"},
            CTL: {"class": "CTL"},
        }
        schema = {
            CTL: {},
            "_owner": "me",
            "orphans_hvac": [_FOREIGN_DEV],
            _FOREIGN_DEV: {"_class": "REM", "_owner": "not-me"},
        }
        yaml_profile = _build_yaml(kl, schema)
        try:
            await load_profile_yaml(
                ctx.token,
                yaml_profile,
                speed=0.01,
                preload_schema=True,
                reload_ramses=True,
            )
            print("  Profile loaded")
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
        wait_for_schema_populated(min_keys=2, timeout=15)

        # ── 2. Verify schema has the foreign device ───────────────────
        schema = get_schema_retry()
        foreign_entry = schema.get(_FOREIGN_DEV)
        ctx.check(
            f"schema has foreign device {_FOREIGN_DEV} with _owner: not-me",
            isinstance(foreign_entry, dict) and foreign_entry.get("_owner") == "not-me",
            f"entry={foreign_entry!r}",
        )

        # Verify it's in orphans_hvac
        orphans = schema.get("orphans_hvac", [])
        ctx.check(
            f"{_FOREIGN_DEV} is in orphans_hvac",
            _FOREIGN_DEV in orphans,
            f"orphans_hvac={orphans!r}",
        )

        # ── 3. Inject a packet from the foreign device ────────────────
        # This makes the scan engine "see" the device so check_for_new_devices
        # would flag it as NEW if the bug is present.
        print(f"  Injecting packet from foreign device {_FOREIGN_DEV}...")
        frame = f" I --- {_FOREIGN_DEV} --:------ {_FOREIGN_DEV} 22F1 003 000107"
        try:
            await ws_send(
                ctx.token,
                {
                    "type": "ramses_extras/device_simulator/inject_packet",
                    "frame": frame,
                },
            )
        except RuntimeError:
            pass

        # ── 4. Wait for discovery checkpoint ───────────────────────────
        # The discovery manager runs check_for_new_devices periodically.
        # If the bug is present, the foreign device will be flagged as NEW.
        print("  Waiting for discovery checkpoint...")
        ctx.wait(15, "for discovery checkpoint", floor=5.0)
        ctx.refresh_token()

        # ── 5. Verify no "new device" notification for foreign device ──
        notifs = await self._get_discovery_notifications(ctx)
        foreign_notif = False
        for n in notifs:
            msg = n.get("message", "")
            if _FOREIGN_DEV in msg:
                foreign_notif = True
                title = n.get("title", "")
                print(f"  FOUND notification: [{title}] {msg[:120]}")

        ctx.check(
            f"no 'new device' notification for foreign-owned {_FOREIGN_DEV}",
            not foreign_notif,
            f"notifications={len(notifs)}, foreign_notif={foreign_notif}",
        )

        # ── 6. Summary ────────────────────────────────────────────────
        total_notifs = len(notifs)
        print(
            f"  Total discovery notifications: {total_notifs} "
            f"(foreign device flagged: {foreign_notif})"
        )
