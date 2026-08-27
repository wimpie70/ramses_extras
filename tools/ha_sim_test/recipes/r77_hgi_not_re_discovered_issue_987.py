"""Recipe R77: HGI device not re-discovered every cycle (issue 987).

Verifies that HGI (18:) devices in the schema are not marked as REMOVED
and re-notified as "newly discovered" on every discovery checkpoint
cycle.

The bug (ramses-rf/ramses_cc issue 987) was that ``_strip_and_orchestrate``
drops all ``18:`` entries from the schema (correct for feeding ramses_rf's
Gateway), but ``_extract_device_ids_from_stripped`` then operated on the
already-stripped schema, so HGI device IDs were never included in
``schema_device_ids``.  ``sync_with_schema`` marked them as REMOVED every
5-minute checkpoint, and ``check_for_new_devices`` re-notified them.

The fix uses ``_extract_schema_device_ids`` (unstripped) for discovery
sync, which includes HGI entries.

This recipe adds a foreign HGI to the schema, injects a packet from it
so the scan engine sees it, then verifies it's not re-notified after a
discovery checkpoint.

See: https://github.com/ramses-rf/ramses_cc/issues/987
"""

from __future__ import annotations

import subprocess
import time

from ..base import Recipe, RecipeContext
from ..const import CTL, HGI
from ..helpers import (
    call_service,
    get_current_instance,
    get_persistent_notifications,
    get_ramses_storage,
    get_schema_retry,
    load_profile_yaml,
    wait_for_ha_ready,
    wait_for_ramses_cc_loaded,
    wait_for_schema_populated,
    ws_send,
)
from ..profile import minimal_ctl_yaml

# A foreign HGI that we'll add to the schema and inject packets from
_FOREIGN_HGI = "18:999999"


class R77HgiNotRediscoveredIssue987(Recipe):
    id = "R77"
    seq = 530
    title = "HGI not re-discovered every cycle (issue 987)"

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

    async def _get_discovery_metadata(self, device_id: str) -> dict | None:
        """Get discovery metadata for a device from .storage."""
        storage = get_ramses_storage()
        discovery = storage.get("discovery", {})
        devices = discovery.get("devices", {})
        return devices.get(device_id)

    async def run(self, ctx: RecipeContext) -> None:
        ctx.log_section("Recipe 77: HGI not re-discovered every cycle")

        # ── 1. Load profile with a foreign HGI in the schema ──────────
        # We add a foreign HGI (18:999999) to the schema so it's a known
        # device.  The bug would cause it to be stripped from
        # schema_device_ids, marked as REMOVED, and re-notified.
        print("  Loading minimal profile (CTL + foreign HGI)...")
        yaml_profile = minimal_ctl_yaml(
            schema_override={
                _FOREIGN_HGI: {"_class": "HGI", "_owner": "not-me"},
            },
            extra_kl={
                _FOREIGN_HGI: {"class": "HGI"},
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
            ctx.check(
                "Profile loaded for R77 HGI test",
                False,
                f"Profile load failed: {str(e)[:100]}",
            )
            return
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

        # ── 2. Verify schema has the foreign HGI entry ────────────────
        schema = get_schema_retry()
        hgi_entry = schema.get(_FOREIGN_HGI, {})
        ctx.check(
            f"schema has foreign HGI {_FOREIGN_HGI} entry",
            isinstance(hgi_entry, dict) and hgi_entry.get("_class") == "HGI",
            f"HGI entry={hgi_entry!r}",
        )

        # ── 3. Inject a packet from the foreign HGI so scan sees it ───
        # This ensures the scan engine has the foreign HGI in its device
        # list, so check_for_new_devices would try to re-notify it if
        # the bug were present (metadata marked as REMOVED).
        print(f"  Injecting packet from foreign HGI {_FOREIGN_HGI}...")
        try:
            await call_service(
                ctx.token,
                "ramses_cc",
                "inject_message",
                {
                    "src_id": _FOREIGN_HGI,
                    "code": "10E0",
                    "payload": (
                        "000001C8A2050367FEFFFFFFFFFF"
                        "1D0807E6564D442D3135524D5338362D3200000000000000"
                    ),
                },
            )
            print("  Packet injected")
        except Exception as e:
            print(f"  Inject failed (non-fatal): {e}")

        # Wait for the scan engine to process the packet
        ctx.wait(5, "for scan engine to process packet", floor=3.0)

        # ── 4. Count notifications before checkpoint ──────────────────
        notifs_before = await self._get_discovery_notifications(ctx)
        notif_before = len(notifs_before)
        print(f"  Discovery notifications before wait: {notif_before}")

        # ── 5. Wait for discovery checkpoint cycle ────────────────────
        # The initial check runs ~10s after startup.  Wait 15s for it.
        print("  Waiting for discovery checkpoint cycle...")
        ctx.wait(15, "for discovery checkpoint", floor=5.0)
        ctx.refresh_token()

        # ── 6. Verify no new discovery notifications for foreign HGI ──
        notifs_after = await self._get_discovery_notifications(ctx)
        notif_after = len(notifs_after)
        print(f"  Discovery notifications after wait: {notif_after}")

        # Check that no notification mentions the foreign HGI device ID
        hgi_in_notif = False
        for n in notifs_after:
            msg = n.get("message", "")
            if _FOREIGN_HGI in msg:
                hgi_in_notif = True
                print(f"  Foreign HGI found in notification: {msg[:120]}")

        ctx.check(
            f"foreign HGI {_FOREIGN_HGI} not in any discovery notification",
            not hgi_in_notif,
            f"hgi_in_notif={hgi_in_notif}",
        )

        ctx.check(
            "no new discovery notifications after checkpoint",
            notif_after <= notif_before,
            f"notifications before={notif_before}, after={notif_after} "
            f"(increase = bug: HGI was stripped from schema_device_ids)",
        )

        # ── 7. Verify foreign HGI metadata is not REMOVED ─────────────
        # If the bug is present, sync_with_schema would mark the foreign
        # HGI as REMOVED every cycle.  After the fix, it should be
        # ACCEPTED (since it's in the schema) or not have metadata yet.
        hgi_meta = await self._get_discovery_metadata(_FOREIGN_HGI)
        if hgi_meta is not None:
            hgi_status = hgi_meta.get("status", "unknown")
            ctx.check(
                f"foreign HGI {_FOREIGN_HGI} discovery metadata not REMOVED",
                hgi_status != "removed",
                f"status={hgi_status!r}",
            )
            print(f"  Foreign HGI discovery status: {hgi_status}")
        else:
            print(f"  Foreign HGI {_FOREIGN_HGI} has no discovery metadata yet")
