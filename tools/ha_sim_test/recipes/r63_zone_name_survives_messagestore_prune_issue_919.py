"""Recipe R63: Zone name survives MessageStore pruning (issue 919).

Verifies that zone names are not lost when the MessageStore prunes 0004
packets after 24h.  The fix (ramses-rf/ramses_cc issue 919) ensures
``Zone._update_schema`` hydrates ``zone_state.name`` from the schema's
``_name`` trait, so the name persists even without 0004 packets in the
MessageStore.

This recipe simulates the pruning by restarting the ha-sim container
(which clears the in-memory MessageStore) and verifying the zone's
device registry name is still the schema-derived name (not the fallback
``"RAD 01:150000_03"`` form).

See: https://github.com/ramses-rf/ramses_cc/issues/919
"""

from __future__ import annotations

import asyncio
import subprocess
import time

from ..base import Recipe, RecipeContext
from ..const import CTL
from ..helpers import (
    call_service,
    get_current_instance,
    get_schema_retry,
    is_ha_ready,
    is_ramses_cc_loaded,
    load_profile_yaml,
    wait_for_ha_ready,
    wait_for_ramses_cc_loaded,
    wait_for_ramses_extras_ready,
    wait_for_schema_populated,
    wait_for_transport_ready,
    ws_send,
)
from ..profile import minimal_ctl_zone_yaml

# Zone we'll test — zone 03 in the mixed profile
_ZONE_IDX = "03"
_ZONE_NAME = "Lounge"

# Zone device ID is "<ctl_id>_<zone_idx>" e.g. "01:150000_03"
_ZONE_DEVICE_ID = f"{CTL}_{_ZONE_IDX}"


class R63ZoneNameSurvivesMessagestorePruneIssue919(Recipe):
    id = "R63"
    seq = 510
    title = "Zone name survives MessageStore pruning (issue 919)"

    async def _get_device_name(self, ctx: RecipeContext) -> str | None:
        """Get the device registry name for the zone device."""
        try:
            resp = await ws_send(ctx.token, {"type": "config/device_registry/list"})
            # ws_send returns the result field; for device_registry/list
            # the result is a list of device dicts directly.
            devices = resp if isinstance(resp, list) else resp.get("devices", [])
            for dev in devices:
                identifiers = dev.get("identifiers", [])
                for ident in identifiers:
                    if isinstance(ident, list) and len(ident) == 2:
                        if ident[0] == "ramses_cc" and ident[1] == _ZONE_DEVICE_ID:
                            return dev.get("name")
            # Debug: show what ramses_cc devices are in the registry
            ramses_devs = [
                (d.get("name"), d.get("identifiers"))
                for d in devices
                if any(
                    isinstance(i, list) and len(i) == 2 and i[0] == "ramses_cc"
                    for i in d.get("identifiers", [])
                )
            ]
            if ramses_devs:
                print(f"    ramses_cc devices in registry: {ramses_devs[:5]}")
            else:
                print(
                    f"    No ramses_cc devices found in registry "
                    f"(total devices: {len(devices)})"
                )
            return None
        except Exception as e:
            print(f"    _get_device_name error: {e}")
            return None

    async def _wait_for_device_name(
        self, ctx: RecipeContext, timeout: int = 60, interval: float = 3
    ) -> str | None:
        """Poll for the device name to appear and contain the zone name."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            name = await self._get_device_name(ctx)
            if name is not None and _ZONE_NAME.lower() in name.lower():
                return name
            await asyncio.sleep(interval)
        # Return whatever we got (even if it doesn't match)
        return await self._get_device_name(ctx)

    async def run(self, ctx: RecipeContext) -> None:
        ctx.log_section("Recipe 63: Zone name survives MessageStore pruning")

        # ── 1. Load minimal profile with _name on zone 03 ───────────
        #    Only CTL + HGI needed (2 devices, not 19) — the zone name
        #    is a schema trait on the CTL entry, no sensor required.
        #    Clear any stale _alias from prior recipes (e.g. R09 sets
        #    _alias='Living Room') so the device registry picks up
        #    _name='Lounge' instead.
        print(
            f"  Loading minimal profile with _name='{_ZONE_NAME}'"
            f" on zone {_ZONE_IDX}..."
        )
        yaml_profile = minimal_ctl_zone_yaml(
            zone_idx=_ZONE_IDX,
            zone_name=_ZONE_NAME,
            clear_alias=True,
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

        # Wait for the MQTT transport to reconnect after the reload,
        # otherwise sync_topology/force_update can't reach the gateway
        # and the device registry won't update.
        wait_for_transport_ready(timeout=30)

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
        wait_for_schema_populated(min_keys=2, timeout=20)

        # Force a device registry refresh — prior recipes (e.g. R33 sets
        # _alias='Bedroom') may have left a stale name in the device
        # registry.  sync_topology + force_update triggers
        # _async_update_device which reads the current Zone.name()
        # (now 'Lounge' from _name, since _alias is cleared).
        try:
            call_service(ctx.token, "ramses_cc", "sync_topology")
        except RuntimeError:
            pass
        try:
            call_service(ctx.token, "ramses_cc", "force_update")
        except RuntimeError:
            pass
        ctx.wait(3, "for device registry name refresh")

        # ── 2. Verify schema has _name on zone 03 ─────────────────────
        schema_before = get_schema_retry()
        ctl_schema = schema_before.get(CTL, {})
        zones_before = ctl_schema.get("zones", {})
        zone_03_before = zones_before.get(_ZONE_IDX, {})
        name_before = (
            zone_03_before.get("_name") if isinstance(zone_03_before, dict) else None
        )

        ctx.check(
            f"schema has _name='{_ZONE_NAME}' on zone {_ZONE_IDX} before restart",
            name_before == _ZONE_NAME,
            f"_name={name_before!r}",
        )

        # ── 3. Check the device registry name for zone 03 ─────────────
        #    The device registry name is set by _async_update_device from
        #    Zone.name().  If Zone.name() returns None, the fallback
        #    "RAD 01:150000_03" is used instead.  This is what the user
        #    sees in the HA UI as the device name.
        print(f"  Waiting for device registry name to contain '{_ZONE_NAME}'...")
        device_name_before = await self._wait_for_device_name(ctx, timeout=30)

        ctx.check(
            f"device registry name contains '{_ZONE_NAME}' before restart",
            device_name_before is not None
            and _ZONE_NAME.lower() in device_name_before.lower(),
            f"device_name={device_name_before!r} "
            f"(fallback like 'RAD {_ZONE_DEVICE_ID}' = bug)",
        )

        # ── 4. Restart ha-sim to clear the in-memory MessageStore ──────
        #    This simulates the 24h pruning: after restart, there are no
        #    0004 packets in the MessageStore.  Without the fix,
        #    Zone.name() returns None → _async_update_device falls back
        #    to "RAD 01:150000_03".  With the fix, Zone._update_schema
        #    hydrates zone_state.name from the schema's _name.
        print("  Restarting ha-sim to clear MessageStore (simulates 24h pruning)...")
        inst = get_current_instance()
        subprocess.run(["docker", "restart", inst.name], check=True, timeout=60)

        wait_for_ha_ready(timeout=60, msg="for ha-sim to restart")
        ctx.refresh_token()
        wait_for_ramses_cc_loaded(
            timeout=30, msg="for ramses_cc to initialize after restart"
        )
        # Wait for ramses_extras websocket commands to be registered
        # before trying to load the profile via WS (otherwise we get
        # 'unknown_command' or 'not_ready' errors).
        wait_for_ramses_extras_ready(timeout=90, msg="for ramses_extras after restart")

        # Reload the profile after restart (the restart clears the
        # simulator state, so we need to re-load the profile with _name)
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

        # Wait for the MQTT transport to reconnect after the reload,
        # otherwise sync_topology/force_update can't reach the gateway
        # and the device registry won't update.
        wait_for_transport_ready(timeout=30)

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
        wait_for_schema_populated(min_keys=2, timeout=20)

        # Force device registry refresh after restart too
        try:
            call_service(ctx.token, "ramses_cc", "sync_topology")
        except RuntimeError:
            pass
        try:
            call_service(ctx.token, "ramses_cc", "force_update")
        except RuntimeError:
            pass
        ctx.wait(3, "for device registry name refresh after restart")

        # ── 5. Verify zone name survived the restart ──────────────────
        #    Wait for the device to reappear and check its registry name
        #    still contains the zone name (not the fallback).
        print(
            f"  Waiting for device registry name to contain "
            f"'{_ZONE_NAME}' after restart..."
        )
        device_name_after = await self._wait_for_device_name(ctx, timeout=30)

        ctx.check(
            f"device registry name contains '{_ZONE_NAME}' after restart",
            device_name_after is not None
            and _ZONE_NAME.lower() in device_name_after.lower(),
            f"device_name={device_name_after!r} "
            f"(fallback form like 'RAD {_ZONE_DEVICE_ID}' = bug present, issue 919)",
        )

        # Check: device name is NOT the fallback form
        is_fallback = (
            device_name_after is not None
            and _ZONE_NAME.lower() not in device_name_after.lower()
            and CTL.replace(":", "_") in device_name_after
        )
        ctx.check(
            "device name is NOT the device-ID fallback form",
            not is_fallback,
            f"device_name={device_name_after!r} (looks like fallback = bug, issue 919)",
        )

        # ── 6. Verify schema still has _name on zone 03 ───────────────
        schema_after = get_schema_retry()
        ctl_schema_after = schema_after.get(CTL, {})
        zones_after = ctl_schema_after.get("zones", {})
        zone_03_after = zones_after.get(_ZONE_IDX, {})
        name_after = (
            zone_03_after.get("_name") if isinstance(zone_03_after, dict) else None
        )

        ctx.check(
            f"schema still has _name='{_ZONE_NAME}' on zone {_ZONE_IDX} after restart",
            name_after == _ZONE_NAME,
            f"_name={name_after!r}",
        )
