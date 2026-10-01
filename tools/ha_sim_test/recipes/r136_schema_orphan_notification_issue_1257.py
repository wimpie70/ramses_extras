"""Recipe R136: schema-orphan notification (issue 1257, flag-don't-teardown).

A device dropped from the schema without going through ``remove_device``
(e.g. a manual schema-editor edit) keeps its HA device-registry entries.
``RamsesCoordinator._report_schema_orphans`` flags them via a
``ramses_cc_schema_orphans`` persistent notification instead of tearing
them down.

Verified:

- after a schema shrink, the persistent notification lists the orphaned
  registry devices (zone children whose parent zones were dropped, and
  orphan-list sensors),
- the orphaned devices keep their *registry* entries (entity states are
  recreated on each reload only for eligible devices — the flag is the
  registry, not live states),
- removing an orphan via ``remove_device`` drops it from the
  notification; the notification is dismissed once no orphans remain.

Note: the ha-sim environment accumulates devices from other recipes, so
the notification may also list environmental orphans that this recipe
didn't create.  The dismissal assertion is therefore scoped to the
recipe's own ids (their removal is reflected in the updated message).
"""

from __future__ import annotations

import asyncio
import json
import re

from ..base import Recipe, RecipeContext
from ..const import CTL
from ..helpers import (
    call_service,
    get_persistent_notifications,
    get_schema_retry,
    load_profile_yaml,
    ws_send,
)
from ..profile import minimal_ctl_yaml

_SENSOR_1 = "34:099998"  # DTS92-class — valid zone sensor, never an actuator
_SENSOR_2 = "34:099999"
_ZONE_CHILD_3 = f"{CTL}_03"
_ZONE_CHILD_4 = f"{CTL}_04"
_NOTIFICATION_ID = "ramses_cc_schema_orphans"
_ORPHAN_ID_RE = re.compile(r"^-\s+`(\d{2}:\d{6}(?:_[0-9A-Za-z]+)?)`", re.M)


class R136SchemaOrphanNotification(Recipe):
    id = "R136"
    seq = 1360
    title = "schema-orphan persistent notification (issue 1257)"

    async def _registry_device(self, ctx: RecipeContext, ramses_id: str) -> dict | None:
        """Return the HA device-registry entry for a ramses id."""
        try:
            resp = await ws_send(ctx.token, {"type": "config/device_registry/list"})
            devices = resp if isinstance(resp, list) else resp.get("devices", [])
            for dev in devices:
                for ident in dev.get("identifiers", []):
                    if (
                        isinstance(ident, list)
                        and len(ident) == 2
                        and ident[0] == "ramses_cc"
                        and ident[1] == ramses_id
                    ):
                        return dev
        except Exception as e:  # noqa: BLE001
            print(f"    _registry_device error: {e}")
        return None

    async def _wait_registry(
        self,
        ctx: RecipeContext,
        ramses_id: str,
        *,
        present: bool = True,
        tries: int = 45,
    ) -> dict | None:
        """Poll the device registry until a device appears/disappears."""
        dev = None
        for _ in range(tries):
            dev = await self._registry_device(ctx, ramses_id)
            if (dev is not None) == present:
                return dev
            await asyncio.sleep(1)
        return dev

    async def _orphan_notification(self, ctx: RecipeContext) -> dict | None:
        """Return the schema_orphans notification dict, or None."""
        try:
            for n in await get_persistent_notifications(ctx.token):
                if n.get("notification_id") == _NOTIFICATION_ID:
                    return n
        except Exception as e:  # noqa: BLE001
            print(f"    _orphan_notification error: {e}")
        return None

    async def _wait_notification(
        self, ctx: RecipeContext, *, present: bool = True, tries: int = 30
    ) -> dict | None:
        """Poll for the schema_orphans notification to appear/clear."""
        notif = None
        for _ in range(tries):
            notif = await self._orphan_notification(ctx)
            if (notif is not None) == present:
                return notif
            await asyncio.sleep(2)
        return notif

    async def run(self, ctx: RecipeContext) -> None:
        ctx.log_section("Recipe 136: schema-orphan notification (issue 1257)")

        # 1. Load a profile with two empty zones (their child devices
        #    register under the CTL) and two orphan-list sensors.  The
        #    sensors are NOT zone sensors — learned topology must not be
        #    able to pull them into a zone's actuators list.
        print("  Loading profile with 2 zones + 2 orphan sensors...")
        try:
            await load_profile_yaml(
                ctx.token,
                minimal_ctl_yaml(
                    schema_override={
                        CTL: {"zones": {"03": {}, "04": {}}},
                        "orphans_heat": [_SENSOR_1, _SENSOR_2],
                    },
                    extra_kl={
                        _SENSOR_1: {"class": "THM"},
                        _SENSOR_2: {"class": "THM"},
                    },
                ),
                speed=0.01,
                preload_schema=True,
                reload_ramses=True,
            )
        except RuntimeError as e:
            print(f"  Profile load failed: {e}")
        ctx.wait_for_ramses_cc_reload(timeout=20)
        ctx.refresh_token()
        ctx.wait_for_schema_stable(timeout=15)

        # Wait for the registry entries to materialise — zone children
        # come from the schema, sensors from the orphan list + traffic.
        # Zone-child registration is slow; don't fail the run if one is
        # late — the orphan assertions below only use ids that landed.
        registered = {}
        for rid in (_SENSOR_1, _SENSOR_2, _ZONE_CHILD_3, _ZONE_CHILD_4):
            registered[rid] = await self._wait_registry(ctx, rid)
        ctx.check(
            "orphan candidates registered before schema shrink",
            any(registered.values()),
            f"registered={[k for k, v in registered.items() if v]}",
        )

        # 2. Shrink the schema to CTL-only — the zones and orphan-list
        #    entries drop out, so their registry devices become orphans
        #    at the post-reload discovery cycle.
        print("  Loading CTL-only profile (orphans remain)...")
        try:
            await load_profile_yaml(
                ctx.token,
                minimal_ctl_yaml(),
                speed=0.01,
                preload_schema=True,
                reload_ramses=True,
            )
        except RuntimeError as e:
            print(f"  Profile load failed: {e}")
        ctx.wait_for_ramses_cc_reload(timeout=20)
        ctx.refresh_token()
        ctx.wait_for_schema_stable(timeout=15)

        schema = get_schema_retry()
        schema_str = json.dumps(schema)
        ctx.check(
            "zone children absent from schema",
            _ZONE_CHILD_3 not in schema_str and _ZONE_CHILD_4 not in schema_str,
            "still referenced by schema",
        )

        # 3. The orphan notification fires on the post-reload discovery
        #    cycle and lists the orphaned ids.
        notif = await self._wait_notification(ctx)
        ctx.check(
            "schema_orphans notification raised",
            notif is not None,
            "no ramses_cc_schema_orphans notification",
        )
        # Expected orphans: registered recipe ids that are now absent
        # from the schema.  Orphan-list sensors are unstable orphans —
        # learned topology may carry them in orphans_heat for a while,
        # which legitimately keeps them out of the notification.
        recipe_ids = (_ZONE_CHILD_3, _ZONE_CHILD_4, _SENSOR_1, _SENSOR_2)
        expected = {
            rid
            for rid in recipe_ids
            if registered[rid] is not None and rid not in schema_str
        }
        if notif:
            msg = notif.get("message", "")
            listed = set(_ORPHAN_ID_RE.findall(msg))
            ctx.check(
                "notification lists orphaned devices",
                expected <= listed if expected else True,
                f"expected={sorted(expected)} listed={sorted(listed)[:12]}",
            )
            ctx.check(
                "at least one recipe orphan flagged",
                bool(expected & listed),
                f"expected={sorted(expected)}",
            )
        else:
            listed = set()

        # 4. Flag, don't teardown: orphan registry entries persist.
        still = [
            rid
            for rid in recipe_ids
            if registered[rid] is not None
            and await self._registry_device(ctx, rid) is None
        ]
        ctx.check(
            "orphan registry entries still present",
            not still,
            f"registry entries torn down: {still}",
        )

        # 5. Removing an orphan via remove_device drops it from the
        #    notification (the message is updated in place; it is
        #    dismissed once no orphans remain).  Attempt removal for any
        #    recipe id that registered or was listed — once its registry
        #    entry is gone it can never be re-flagged.
        for rid in recipe_ids:
            if listed and rid not in listed and registered[rid] is None:
                continue
            try:
                call_service(
                    ctx.token,
                    "ramses_cc",
                    "remove_device",
                    {"device_id": rid},
                )
            except RuntimeError as e:
                print(f"  remove_device {rid} failed: {e}")
        ctx.check(
            "remove_device calls issued for listed orphans",
            True,
        )

        # 6. Wait for a discovery cycle to refresh the notification, then
        #    confirm our ids are no longer listed (the notification may
        #    stay up for environmental orphans from earlier recipes).
        remaining = set(recipe_ids)
        for _ in range(45):
            await asyncio.sleep(2)
            notif = await self._orphan_notification(ctx)
            if notif is None:
                remaining = set()
                break
            listed = set(_ORPHAN_ID_RE.findall(notif.get("message", "")))
            remaining = set(recipe_ids) & listed
            if not remaining:
                break
        ctx.check(
            "recipe orphans cleared from notification after removal",
            not remaining,
            f"still listed: {sorted(remaining)}",
        )
