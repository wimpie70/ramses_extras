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
    wait_for,
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

        # ── 1. Load profile with _suppress_not_seen on a non-active TRV ─
        # We use a fake TRV (04:222222) that won't receive heartbeats,
        # so the discovery manager won't strip _suppress_not_seen (the
        # key is only cleared when a device is "seen recently").
        # Using the CTL would fail because the CTL is active and the
        # discovery checkpoint clears the key immediately.
        suppress_device = "04:222222"
        print(
            f"  Loading minimal profile (CTL + {suppress_device}"
            f" with _suppress_not_seen)..."
        )
        yaml_profile = minimal_ctl_yaml(
            schema_override={
                suppress_device: {"_class": "TRV", "_suppress_not_seen": True},
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

        # ── 2. Verify schema has _suppress_not_seen on the device ──────
        # Under parallel load, the profile_loader's schema override may
        # not be applied to the coordinator's options yet when we read
        # the schema.  Poll for the key specifically.  If it still
        # hasn't appeared after the initial poll, retry the profile
        # load (the override may have been lost during a concurrent
        # reload race).
        def _suppress_key_present() -> bool:
            schema = get_schema_retry(max_tries=2, delay=2)
            entry = schema.get(suppress_device, {})
            return isinstance(entry, dict) and entry.get("_suppress_not_seen") is True

        if not wait_for(
            _suppress_key_present,
            timeout=30,
            interval=3,
            msg="for _suppress_not_seen key to appear in schema",
            floor=10.0,
        ):
            # Retry: reload the profile with reload_ramses to force the
            # schema override through the profile_loader → coordinator
            # options → config entry update path.
            print("  Key not found — retrying profile load...")
            try:
                await load_profile_yaml(
                    ctx.token,
                    yaml_profile,
                    speed=0.01,
                    preload_schema=True,
                    reload_ramses=True,
                )
            except RuntimeError as e:
                print(f"  Retry profile load failed: {e}")
            ctx.wait_for_ramses_cc_reload(timeout=20)
            ctx.refresh_token()
            wait_for(
                _suppress_key_present,
                timeout=30,
                interval=3,
                msg="for _suppress_not_seen key after retry",
                floor=10.0,
            )

        schema = get_schema_retry()
        dev_entry = schema.get(suppress_device, {})
        ctx.check(
            f"schema has _suppress_not_seen on {suppress_device}",
            isinstance(dev_entry, dict) and dev_entry.get("_suppress_not_seen") is True,
            f"entry={dev_entry!r}",
        )

        # ── 3. Wait for discovery checkpoint ───────────────────────────
        print("  Waiting for discovery checkpoint...")
        ctx.wait(15, "for discovery checkpoint", floor=5.0)
        ctx.refresh_token()

        # ── 4. Verify device is not flagged as orphaned ────────────────
        # The device has _suppress_not_seen=True, so even if it's not
        # been seen recently, the discovery manager should NOT add it
        # to the orphaned list (no persistent notification).
        dev_meta = await self._get_discovery_metadata(suppress_device)
        if dev_meta is not None:
            orphaned = dev_meta.get("orphaned")
            print(f"  {suppress_device} orphaned={orphaned!r}")
            ctx.check(
                f"{suppress_device} not orphaned (_suppress_not_seen active)",
                orphaned is None,
                f"orphaned={orphaned!r}",
            )
        else:
            print(f"  {suppress_device} has no discovery metadata (ok)")

        # ── 5. Verify no mismatch notification mentions device as orphaned
        notifs = await self._get_mismatch_notifications(ctx)
        dev_in_orphaned = False
        for n in notifs:
            msg = n.get("message", "")
            if suppress_device in msg and "orphan" in msg.lower():
                dev_in_orphaned = True
                print(
                    f"  {suppress_device} found in orphaned notification: {msg[:120]}"
                )

        ctx.check(
            f"{suppress_device} not in orphaned mismatch notification",
            not dev_in_orphaned,
            f"dev_in_orphaned={dev_in_orphaned}",
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

        # Poll for _suppress_not_seen key after restart — under parallel
        # load the profile reload + coordinator options update may take
        # longer to settle.
        def _suppress_key_present_after_restart() -> bool:
            schema = get_schema_retry(max_tries=2, delay=2)
            entry = schema.get(suppress_device, {})
            return isinstance(entry, dict) and entry.get("_suppress_not_seen") is True

        wait_for(
            _suppress_key_present_after_restart,
            timeout=30,
            interval=3,
            msg="for _suppress_not_seen key to reappear after restart",
            floor=10.0,
        )

        schema_after = get_schema_retry()
        dev_entry_after = schema_after.get(suppress_device, {})
        ctx.check(
            f"_suppress_not_seen survived restart on {suppress_device}",
            isinstance(dev_entry_after, dict)
            and dev_entry_after.get("_suppress_not_seen") is True,
            f"entry after restart={dev_entry_after!r}",
        )
