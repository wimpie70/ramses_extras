"""Recipe R134: remove_device — registry-only orphans (issue 1246).

A device dropped from the schema without going through ``remove_device``
(e.g. the passive device scan leftovers of issue 1238 once the schema is
cleaned, or any schema/profile change) leaves an orphan entry in the HA
device registry.  This recipe creates such orphans by first loading a
profile with two THM zone sensors (plus their zone child devices), then
loading a CTL-only profile — the sensors and zone children stay behind
in the device registry, no longer referenced by the schema.

Verified:

- ``ramses_cc.remove_device`` accepts registry-only orphans (both a
  plain device id and a ``<tcs>_<idx>`` zone child id),
- HA's ``config/device_registry/remove_config_entry`` websocket delete
  works via ``async_remove_config_entry_device``,
- an in-schema device (the CTL) is refused by that hook,
- a completely unknown id is still refused by the service.
"""

from __future__ import annotations

import asyncio
import json

from ..base import Recipe, RecipeContext
from ..const import CTL
from ..helpers import (
    _get_ramses_cc_entry_id,
    call_service,
    get_schema_retry,
    load_profile_yaml,
    ws_send,
)
from ..profile import minimal_ctl_yaml

_SENSOR_1 = "04:099998"
_SENSOR_2 = "04:099999"
_ZONE_CHILD_3 = f"{CTL}_03"
_ZONE_CHILD_4 = f"{CTL}_04"
_UNKNOWN = "99:099999"


class R134RemoveDeviceRegistryOrphans(Recipe):
    id = "R134"
    seq = 1340
    title = "remove_device — registry-only orphans (issue 1246)"

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
        tries: int = 15,
    ) -> dict | None:
        """Poll the device registry until a device appears/disappears."""
        dev = None
        for _ in range(tries):
            dev = await self._registry_device(ctx, ramses_id)
            if (dev is not None) == present:
                return dev
            await asyncio.sleep(1)
        return dev

    async def run(self, ctx: RecipeContext) -> None:
        ctx.log_section(
            "Recipe 134: remove_device — registry-only orphans (issue 1246)"
        )

        # 1. Load a profile with two THM zone sensors — this registers
        #    the sensors and the zone child devices in the HA registry.
        print("  Loading profile with 2 zone sensors...")
        try:
            await load_profile_yaml(
                ctx.token,
                minimal_ctl_yaml(
                    schema_override={
                        CTL: {
                            "zones": {
                                "03": {
                                    "sensor": _SENSOR_1,
                                    "actuators": [],
                                },
                                "04": {
                                    "sensor": _SENSOR_2,
                                    "actuators": [],
                                },
                            }
                        }
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

        orphan_ids = (_SENSOR_1, _SENSOR_2, _ZONE_CHILD_3, _ZONE_CHILD_4)
        registered = {}
        for rid in orphan_ids:
            registered[rid] = await self._wait_registry(ctx, rid)
        ctx.check(
            "orphans registered before schema shrink",
            all(registered.values()),
            f"registered={[k for k, v in registered.items() if v]}",
        )

        # 2. Shrink the schema to CTL-only — the sensors and zone child
        #    devices stay in the HA registry as registry-only orphans.
        print("  Loading CTL-only profile (orphans remain in registry)...")
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
        for rid in (_SENSOR_1, _SENSOR_2):
            ctx.check(
                f"{rid} absent from schema",
                rid not in schema_str,
                "still referenced by schema",
            )

        for rid in orphan_ids:
            dev = await self._registry_device(ctx, rid)
            ctx.check(
                f"{rid} still in device registry (orphan)",
                dev is not None,
                "registry entry already gone",
            )

        # 3. remove_device on a registry-only orphan — before the fix
        #    this raised "not found in schema"; now it removes the
        #    registry entry.
        try:
            call_service(
                ctx.token,
                "ramses_cc",
                "remove_device",
                {"device_id": _SENSOR_1},
            )
            print(f"  remove_device {_SENSOR_1} call succeeded")
            dev = await self._wait_registry(ctx, _SENSOR_1, present=False)
            ctx.check(
                "orphan sensor removed via remove_device",
                dev is None,
                f"{_SENSOR_1} still registered",
            )
        except RuntimeError as e:
            ctx.check(
                "orphan sensor removed via remove_device",
                False,
                str(e)[:120],
            )

        # Same for a zone child orphan (<tcs>_<idx>).
        try:
            call_service(
                ctx.token,
                "ramses_cc",
                "remove_device",
                {"device_id": _ZONE_CHILD_3},
            )
            print(f"  remove_device {_ZONE_CHILD_3} call succeeded")
            dev = await self._wait_registry(ctx, _ZONE_CHILD_3, present=False)
            ctx.check(
                "orphan zone child removed via remove_device",
                dev is None,
                f"{_ZONE_CHILD_3} still registered",
            )
        except RuntimeError as e:
            ctx.check(
                "orphan zone child removed via remove_device",
                False,
                str(e)[:120],
            )

        # 4. HA's standard device delete (websocket
        #    config/device_registry/remove_config_entry) — enabled by
        #    async_remove_config_entry_device (issue 1246).
        entry_id = _get_ramses_cc_entry_id()
        orphan = await self._registry_device(ctx, _ZONE_CHILD_4)
        if orphan and entry_id:
            try:
                await ws_send(
                    ctx.token,
                    {
                        "type": "config/device_registry/remove_config_entry",
                        "config_entry_id": entry_id,
                        "device_id": orphan["id"],
                    },
                )
                ctx.check(
                    "WS delete accepted for orphan child",
                    True,
                )
                dev = await self._wait_registry(ctx, _ZONE_CHILD_4, present=False)
                ctx.check(
                    "orphan child removed via WS delete",
                    dev is None,
                    f"{_ZONE_CHILD_4} still registered",
                )
            except RuntimeError as e:
                ctx.check(
                    "WS delete accepted for orphan child",
                    False,
                    str(e)[:120],
                )
        else:
            ctx.check(
                "WS delete accepted for orphan child",
                False,
                f"no registry entry ({_ZONE_CHILD_4}) or entry_id",
            )

        orphan = await self._registry_device(ctx, _SENSOR_2)
        if orphan and entry_id:
            try:
                await ws_send(
                    ctx.token,
                    {
                        "type": "config/device_registry/remove_config_entry",
                        "config_entry_id": entry_id,
                        "device_id": orphan["id"],
                    },
                )
                dev = await self._wait_registry(ctx, _SENSOR_2, present=False)
                ctx.check(
                    "orphan sensor removed via WS delete",
                    dev is None,
                    f"{_SENSOR_2} still registered",
                )
            except RuntimeError as e:
                ctx.check(
                    "orphan sensor removed via WS delete",
                    False,
                    str(e)[:120],
                )
        else:
            ctx.check(
                "orphan sensor removed via WS delete",
                False,
                f"no registry entry ({_SENSOR_2}) or entry_id",
            )

        # 5. Negative: the hook must refuse a device still in the schema
        #    (the CTL) — removing it via WS must fail.
        ctl_dev = await self._registry_device(ctx, CTL)
        if ctl_dev and entry_id:
            try:
                await ws_send(
                    ctx.token,
                    {
                        "type": "config/device_registry/remove_config_entry",
                        "config_entry_id": entry_id,
                        "device_id": ctl_dev["id"],
                    },
                )
                ctx.check(
                    "WS delete refused for in-schema CTL",
                    False,
                    "call unexpectedly succeeded",
                )
            except RuntimeError:
                ctx.check("WS delete refused for in-schema CTL", True)
            ctx.check(
                "CTL still registered",
                await self._registry_device(ctx, CTL) is not None,
                "CTL device entry lost",
            )
        else:
            ctx.check(
                "WS delete refused for in-schema CTL",
                False,
                "no CTL registry entry or entry_id",
            )

        # 6. Negative: a completely unknown id is still refused by the
        #    remove_device service (not in schema, not in registry).
        try:
            call_service(
                ctx.token,
                "ramses_cc",
                "remove_device",
                {"device_id": _UNKNOWN},
            )
            ctx.check(
                "unknown id rejected by remove_device",
                False,
                "call unexpectedly succeeded",
            )
        except RuntimeError as e:
            # ServiceValidationError surfaces as HTTP 400/500 over REST.
            ctx.check(
                "unknown id rejected by remove_device",
                "500" in str(e) or "400" in str(e),
                str(e)[:100],
            )
