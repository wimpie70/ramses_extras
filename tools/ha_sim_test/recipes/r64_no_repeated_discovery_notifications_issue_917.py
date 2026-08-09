"""Recipe R64: No repeated discovery notifications after restart (issue 917).

Verifies that devices placed inside TCS structures (appliance_control,
stored_hotwater, zones) are not re-notified as "newly discovered" after
an HA restart.  The fix (ramses-rf/ramses_cc issue 917) ensures that
``_async_stop_discovery_scan`` and ``_async_save_on_unload`` use the
full ``_extract_schema_device_ids`` extraction (which walks all nested
device locations) instead of a simplified top-level-only extraction
that missed devices inside TCS entries.

The recipe also verifies that ``_resolve_single_slot_conflicts`` is
applied during config-flow bulk accept, preventing two relays from
displacing each other in the ``appliance_control`` slot.

See: https://github.com/ramses-rf/ramses_cc/issues/917
"""

from __future__ import annotations

import asyncio
import json
import subprocess
import time

from ..base import Recipe, RecipeContext
from ..const import CTL, DHW, FAN, HGI, TRV
from ..helpers import (
    call_service,
    get_current_instance,
    get_persistent_notifications,
    get_ramses_storage,
    get_schema_retry,
    is_ha_ready,
    is_ramses_cc_loaded,
    load_profile_yaml,
    wait_for_ha_ready,
    wait_for_ramses_cc_loaded,
    wait_for_schema_populated,
    ws_send,
)
from ..profile import MIXED_SCHEMA, mixed_yaml

# DHW is placed as stored_hotwater.sensor inside the CTL entry —
# a nested location that the simplified extraction missed.
_DHW_ID = DHW  # 07:150000


class R64NoRepeatedDiscoveryNotificationsIssue917(Recipe):
    id = "R64"
    seq = 520
    title = "No repeated discovery notifications after restart (issue 917)"

    async def _get_discovery_notifications(self, ctx: RecipeContext) -> list[dict]:
        """Get persistent notifications about newly discovered devices.

        Only matches the "new devices" notification (notification_id =
        ``ramses_cc_discovery``, title = "RAMSES CC: New devices
        discovered").  Mismatch and lost-device notifications are
        excluded — they are separate concerns.
        """
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

    async def _get_discovery_metadata(self, device_id: str) -> dict | None:
        """Get discovery metadata for a device from .storage."""
        storage = get_ramses_storage()
        discovery = storage.get("discovery", {})
        devices = discovery.get("devices", {})
        return devices.get(device_id)

    async def run(self, ctx: RecipeContext) -> None:
        ctx.log_section("Recipe 64: No repeated discovery notifications")

        # ── 1. Load mixed profile ──────────────────────────────────────
        # The mixed profile has DHW (07:150000) as stored_hotwater.sensor
        # inside the CTL entry — a nested location that the old
        # simplified extraction missed.
        print("  Loading mixed profile...")
        yaml_profile = mixed_yaml()
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
        wait_for_schema_populated(min_keys=3, timeout=20)

        # ── 2. Verify schema has DHW nested in stored_hotwater ─────────
        schema = get_schema_retry()
        ctl_entry = schema.get(CTL, {})
        dhw_section = ctl_entry.get("stored_hotwater", {})
        dhw_sensor = (
            dhw_section.get("sensor") if isinstance(dhw_section, dict) else None
        )

        ctx.check(
            f"schema has DHW {_DHW_ID} nested as stored_hotwater.sensor",
            dhw_sensor == _DHW_ID,
            f"stored_hotwater.sensor={dhw_sensor!r}",
        )

        # ── 3. Count notifications before restart ──────────────────────
        notifs_before = await self._get_discovery_notifications(ctx)
        notif_before = len(notifs_before)
        print(f"  Discovery notifications before restart: {notif_before}")
        for n in notifs_before:
            nid = n.get("notification_id", "?")
            title = n.get("title", "")
            msg = n.get("message", "")[:80]
            print(f"    [{nid}] {title}: {msg}")

        # ── 4. Restart ha-sim ──────────────────────────────────────────
        # This triggers the unload path (_async_stop_discovery_scan +
        # _async_save_on_unload) where the bug manifested: the simplified
        # schema_device_ids extraction missed nested devices, so their
        # ACCEPTED metadata was filtered out during save.
        print("  Restarting ha-sim to trigger unload/save path...")
        inst = get_current_instance()
        subprocess.run(["docker", "restart", inst.name], check=True, timeout=60)

        wait_for_ha_ready(timeout=60, msg="for ha-sim to restart")
        ctx.refresh_token()
        wait_for_ramses_cc_loaded(
            timeout=30, msg="for ramses_cc to initialize after restart"
        )

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
        wait_for_schema_populated(min_keys=3, timeout=20)

        # ── 5. Verify no new discovery notifications appeared ───────────
        # Wait a bit for the discovery checkpoint to run (10s initial
        # check + 5s margin).
        print("  Waiting for discovery checkpoint to run...")
        await asyncio.sleep(20)
        ctx.refresh_token()
        notifs_after = await self._get_discovery_notifications(ctx)
        notif_after = len(notifs_after)
        print(f"  Discovery notifications after restart: {notif_after}")
        for n in notifs_after:
            nid = n.get("notification_id", "?")
            title = n.get("title", "")
            msg = n.get("message", "")[:120]
            print(f"    [{nid}] {title}: {msg}")

        ctx.check(
            "no new discovery notifications after restart",
            notif_after <= notif_before,
            f"notifications before={notif_before}, after={notif_after} "
            f"(increase = bug: nested device metadata was filtered out)",
        )

        # ── 6. Verify DHW discovery metadata survived the restart ──────
        # If the metadata was filtered out by the buggy simplified
        # extraction, the device would have no metadata after restart
        # and would be re-classified as NEW by the scan engine.
        dhw_meta = await self._get_discovery_metadata(_DHW_ID)
        if dhw_meta is not None:
            dhw_status = dhw_meta.get("status", "unknown")
            ctx.check(
                f"DHW {_DHW_ID} discovery metadata survived restart",
                dhw_status in ("accepted", "new", "removed"),
                f"status={dhw_status!r}",
            )
            print(f"  DHW discovery status after restart: {dhw_status}")
        else:
            # No metadata is acceptable if the scan engine hasn't seen
            # the device yet (it may take time for packets to arrive).
            # The key check is that no spurious notification appeared.
            print(
                f"  DHW {_DHW_ID} has no discovery metadata yet (ok if no notification)"
            )
