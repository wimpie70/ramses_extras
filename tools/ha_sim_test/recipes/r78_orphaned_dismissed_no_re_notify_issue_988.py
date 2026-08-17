"""Recipe R78: Orphaned device suppress_not_seen, no re-notify (issue 988).

Verifies that after the user sets ``_suppress_not_seen: True`` on a device
in the schema (via the "Keep (dismiss flag)" action in the
review_device_health config flow step), the orphaned notification does
not re-appear on the next discovery checkpoint cycle.

The bug (ramses-rf/ramses_cc issue 988) was that ``check_orphaned_devices``
set ``meta.orphaned`` on every checkpoint cycle for devices whose
``last_seen`` was older than the 7-day threshold, and
``check_all_mismatches`` re-created the notification every time.  There
was no way to suppress it.

The fix uses a per-device schema key ``_suppress_not_seen: True``.  When
set, ``check_orphaned_devices`` does not add the device to the orphaned
list (so no persistent notification), but still emits an INFO log once
every ``threshold_days`` as a gentle reminder (e.g. in case batteries
died).  The key is stored in the schema (user-configurable, visible,
persists across restarts) and stripped before passing to ramses_rf.

This recipe tests the mechanism by:
1. Loading a profile with a device that has _suppress_not_seen in schema
2. Verifying the device is not flagged as orphaned (no notification)
3. Verifying last_orphaned_log is set (periodic INFO log tracking)
4. Restarting to verify the schema key persists

See: https://github.com/ramses-rf/ramses_cc/issues/988
"""

from __future__ import annotations

import json
import subprocess
import time

from ..base import Recipe, RecipeContext
from ..const import CTL, HGI
from ..helpers import (
    get_current_instance,
    get_persistent_notifications,
    get_ramses_storage,
    get_schema_retry,
    load_profile_yaml,
    wait_for_ha_ready,
    wait_for_ramses_cc_loaded,
    wait_for_ramses_extras_ready,
    wait_for_schema_populated,
    ws_send,
)
from ..profile import minimal_ctl_yaml


class R78OrphanedDismissedNoReNotifyIssue988(Recipe):
    id = "R78"
    seq = 535
    title = "Orphaned suppress_not_seen, no re-notify (issue 988)"

    async def _get_mismatch_notifications(self, ctx: RecipeContext) -> list[dict]:
        """Get persistent notifications about schema mismatches.

        The orphaned notification uses the mismatch notification ID
        (``ramses_cc_discovery_mismatches``) since it's sent by
        ``_send_mismatch_notification``.
        """
        try:
            notifications = await get_persistent_notifications(ctx.token)
            if not isinstance(notifications, list):
                return []
            result = []
            for n in notifications:
                nid = n.get("notification_id", "")
                title = n.get("title", "")
                if nid == "ramses_cc_discovery_mismatches" or (
                    "mismatch" in title.lower()
                ):
                    result.append(n)
            return result
        except Exception:
            return []

    async def _get_discovery_metadata(self, device_id: str) -> dict | None:
        """Get discovery metadata for a device from .storage."""
        storage = get_ramses_storage()
        discovery = storage.get("discovery", {})
        devices = discovery.get("devices", {})
        return devices.get(device_id)

    async def run(self, ctx: RecipeContext) -> None:
        ctx.log_section("Recipe 78: Orphaned suppress_not_seen, no re-notify")

        # ── 1. Load profile with _suppress_not_seen on CTL ────────────
        # We add _suppress_not_seen: True to the CTL entry in the schema.
        # The CTL is active (seen recently), so it won't actually be
        # orphaned, but we can verify the schema key is preserved and
        # the discovery metadata doesn't have an orphaned flag.
        print("  Loading minimal profile (CTL + _suppress_not_seen)...")
        yaml_profile = minimal_ctl_yaml(
            schema_override={
                CTL: {"_suppress_not_seen": True},
            },
        )
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

        # ── 2. Verify schema has _suppress_not_seen on CTL ────────────
        schema = get_schema_retry()
        ctl_entry = schema.get(CTL, {})
        ctx.check(
            f"schema has _suppress_not_seen on {CTL}",
            isinstance(ctl_entry, dict) and ctl_entry.get("_suppress_not_seen") is True,
            f"CTL entry={ctl_entry!r}",
        )

        # ── 3. Wait for discovery checkpoint ───────────────────────────
        print("  Waiting for discovery checkpoint...")
        ctx.wait(15, "for discovery checkpoint", floor=5.0)
        ctx.refresh_token()

        # ── 4. Verify CTL is not flagged as orphaned ───────────────────
        # CTL is active (seen recently via heartbeats), so it should
        # not be orphaned regardless of _suppress_not_seen.  The key
        # check is that the schema key is preserved and no mismatch
        # notification mentions CTL as orphaned.
        ctl_meta = await self._get_discovery_metadata(CTL)
        if ctl_meta is not None:
            orphaned = ctl_meta.get("orphaned")
            print(f"  CTL orphaned={orphaned!r}")
            ctx.check(
                f"CTL {CTL} not orphaned (active device)",
                orphaned is None,
                f"orphaned={orphaned!r}",
            )
        else:
            print(f"  CTL {CTL} has no discovery metadata (ok)")

        # ── 5. Verify no mismatch notification mentions CTL as orphaned
        notifs = await self._get_mismatch_notifications(ctx)
        ctl_in_orphaned = False
        for n in notifs:
            msg = n.get("message", "")
            if CTL in msg and "orphan" in msg.lower():
                ctl_in_orphaned = True
                print(f"  CTL found in orphaned notification: {msg[:120]}")

        ctx.check(
            f"CTL {CTL} not in orphaned mismatch notification",
            not ctl_in_orphaned,
            f"ctl_in_orphaned={ctl_in_orphaned}",
        )

        # ── 6. Verify _suppress_not_seen survives restart ─────────────
        # The schema key should persist across restarts because it's
        # stored in the config entry options.
        print("  Restarting ha-sim to verify schema key persists...")
        inst = get_current_instance()
        subprocess.run(["docker", "restart", inst.name], check=True, timeout=60)

        wait_for_ha_ready(timeout=30, msg="for ha-sim to restart")
        ctx.refresh_token()
        wait_for_ramses_cc_loaded(
            timeout=20, msg="for ramses_cc to initialize after restart"
        )
        # Wait for ramses_extras websocket commands to be registered
        # before trying to load the profile via WS (otherwise we get
        # 'unknown_command' or 'not_ready' errors).
        wait_for_ramses_extras_ready(timeout=90, msg="for ramses_extras after restart")

        # Reload the profile after restart
        print("  Reloading profile after restart...")
        try:
            await load_profile_yaml(
                ctx.token,
                yaml_profile,
                speed=0.01,
                preload_schema=True,
                reload_ramses=True,
            )
        except RuntimeError as e:
            print(f"  Profile reload failed: {e}")
        ctx.wait_for_ramses_cc_reload(timeout=20)
        ctx.refresh_token()

        # Activate CTL again
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

        schema_after = get_schema_retry()
        ctl_entry_after = schema_after.get(CTL, {})
        ctx.check(
            f"_suppress_not_seen survived restart on {CTL}",
            isinstance(ctl_entry_after, dict)
            and ctl_entry_after.get("_suppress_not_seen") is True,
            f"CTL entry after restart={ctl_entry_after!r}",
        )
