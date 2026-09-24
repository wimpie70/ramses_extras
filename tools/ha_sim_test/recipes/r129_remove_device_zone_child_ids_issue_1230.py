"""Recipe R129: remove_device — zone/DHW child ids (issue 1230).

Zones and UFH circuits register in the HA device registry with
``parent_id_index`` identifiers (``01:150000_04``, ``01:150000_HW``).
remove_device must accept those ids, delete the matching zone/circuit
entry from the schema, drop the registry entry — and
sync_learned_topology must not re-add the zone from the learned schema
(the sim keeps sending packets for it).
"""

from __future__ import annotations

import json

from ..base import Recipe, RecipeContext
from ..const import CTL, DHW
from ..helpers import (
    call_service,
    get_schema,
    get_schema_retry,
    load_profile_yaml,
    wait_for,
    ws_send,
)
from ..profile import mixed_yaml

_ZONE_IDX = "04"
_ZONE_CHILD_ID = f"{CTL}_{_ZONE_IDX}"  # "01:150000_04"
_DHW_CHILD_ID = f"{CTL}_HW"  # "01:150000_HW"


class R129RemoveDeviceZoneChildIds(Recipe):
    id = "R129"
    seq = 1290
    title = "remove_device — zone/DHW child ids (issue 1230)"

    async def _child_in_device_registry(
        self, ctx: RecipeContext, child_id: str
    ) -> bool:
        """Check the HA device registry for a child (``XX:NNNNNN_II``) id."""
        try:
            resp = await ws_send(ctx.token, {"type": "config/device_registry/list"})
            devices = resp if isinstance(resp, list) else resp.get("devices", [])
            for dev in devices:
                for ident in dev.get("identifiers", []):
                    if (
                        isinstance(ident, list)
                        and len(ident) == 2
                        and ident[0] == "ramses_cc"
                        and ident[1] == child_id
                    ):
                        return True
        except Exception as e:  # noqa: BLE001
            print(f"    _child_in_device_registry error: {e}")
        return False

    async def _child_in_entity_registry(
        self, ctx: RecipeContext, child_id: str
    ) -> bool:
        """Check the HA entity registry for the child's unique_id."""
        try:
            resp = await ws_send(ctx.token, {"type": "config/entity_registry/list"})
            entities = resp if isinstance(resp, list) else resp.get("entities", [])
            return any(e.get("unique_id") == child_id for e in entities)
        except Exception as e:  # noqa: BLE001
            print(f"    _child_in_entity_registry error: {e}")
            return False

    async def run(self, ctx: RecipeContext) -> None:
        ctx.log_section("Recipe 129: remove_device — zone/DHW child ids (issue 1230)")

        # Load the mixed profile for a predictable starting state:
        # CTL with zones 03-08 and stored_hotwater.
        print("  Loading mixed profile (zones 03-08 + DHW)...")
        try:
            await load_profile_yaml(
                ctx.token,
                mixed_yaml(),
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
        ctl_entry = schema.get(CTL, {})
        zones = ctl_entry.get("zones", {}) if isinstance(ctl_entry, dict) else {}
        print(f"  Zones before: {sorted(zones)}, DHW: {'stored_hotwater' in ctl_entry}")
        ctx.check(
            f"zone {_ZONE_IDX} present before removal",
            _ZONE_IDX in zones,
            f"zones={sorted(zones)}",
        )
        ctx.check(
            "stored_hotwater present before removal",
            "stored_hotwater" in ctl_entry,
            "no stored_hotwater under CTL",
        )
        print(
            f"  {_ZONE_CHILD_ID} in device registry: "
            f"{await self._child_in_device_registry(ctx, _ZONE_CHILD_ID)}"
        )

        # 1. Remove a heating zone by its registry child id.  Before the
        # fix this call was rejected by the device_id regex; after the
        # fix it removes zones[04] plus the device registry entry.
        try:
            call_service(
                ctx.token,
                "ramses_cc",
                "remove_device",
                {"device_id": _ZONE_CHILD_ID},
            )
            print(f"  remove_device {_ZONE_CHILD_ID} call succeeded")

            wait_for(
                lambda: _ZONE_IDX not in get_schema().get(CTL, {}).get("zones", {}),
                timeout=30,
                interval=2,
                msg=f"for zone {_ZONE_IDX} to be removed from schema",
                floor=15.0,
            )

            schema = get_schema()
            ctl_entry = schema.get(CTL, {})
            zones = ctl_entry.get("zones", {})
            ctx.check(
                f"zone {_ZONE_IDX} removed from schema",
                _ZONE_IDX not in zones,
                f"zones={sorted(zones)}",
            )
            ctx.check(
                "other zones kept",
                "03" in zones and "05" in zones,
                f"zones={sorted(zones)}",
            )
            ctx.check(
                "stored_hotwater kept",
                "stored_hotwater" in ctl_entry,
                "stored_hotwater missing under CTL",
            )
            ctx.check(
                "zone child removed from device registry",
                not await self._child_in_device_registry(ctx, _ZONE_CHILD_ID),
                f"{_ZONE_CHILD_ID} still registered",
            )
            ctx.check(
                "zone entity removed from entity registry",
                not await self._child_in_entity_registry(ctx, _ZONE_CHILD_ID),
                f"{_ZONE_CHILD_ID} entities still registered",
            )
        except RuntimeError as e:
            ctx.check("remove_device zone child call", False, str(e)[:120])

        # 2. Resurrection check — the learned schema still contains the
        # zone (ramses_rf has no remove API), so a sync cycle must not
        # write it back into the config entry schema.
        try:
            call_service(ctx.token, "ramses_cc", "sync_topology")
            print("  sync_topology called")
        except RuntimeError as e:
            print(f"  sync_topology failed: {e}")
        try:
            call_service(ctx.token, "ramses_cc", "force_update")
        except RuntimeError:
            pass
        ctx.wait_for_schema_stable(timeout=10, msg="for sync + save")

        zones = get_schema().get(CTL, {}).get("zones", {})
        ctx.check(
            f"zone {_ZONE_IDX} not resurrected by sync_learned_topology",
            _ZONE_IDX not in zones,
            f"zones={sorted(zones)}",
        )

        # 3. Negative checks: a well-formed but unknown child id must
        # fail "not found", and a malformed id must fail validation.
        try:
            call_service(
                ctx.token,
                "ramses_cc",
                "remove_device",
                {"device_id": f"{CTL}_0A"},
            )
            ctx.check("unknown child id rejected", False, "call unexpectedly succeeded")
        except RuntimeError as e:
            # ServiceValidationError surfaces as HTTP 500 over REST —
            # the response body doesn't carry the "not found" message.
            ctx.check(
                "unknown child id rejected",
                "500" in str(e) or "400" in str(e),
                str(e)[:100],
            )
        try:
            call_service(
                ctx.token,
                "ramses_cc",
                "remove_device",
                {"device_id": f"{CTL}-05"},
            )
            ctx.check(
                "malformed child id rejected", False, "call unexpectedly succeeded"
            )
        except RuntimeError as e:
            ctx.check(
                "malformed child id rejected",
                "regular expression" in str(e).lower() or "400" in str(e),
                str(e)[:100],
            )

        # 4. Remove the DHW zone via <tcs>_HW.  Lowercase input also
        # exercises the case-insensitive service schema + upper() in the
        # handler.
        try:
            call_service(
                ctx.token,
                "ramses_cc",
                "remove_device",
                {"device_id": _DHW_CHILD_ID.lower()},
            )
            print(f"  remove_device {_DHW_CHILD_ID.lower()} call succeeded")

            wait_for(
                lambda: "stored_hotwater" not in get_schema().get(CTL, {}),
                timeout=30,
                interval=2,
                msg="for stored_hotwater to be removed from schema",
                floor=15.0,
            )

            ctl_entry = get_schema().get(CTL, {})
            ctx.check(
                "stored_hotwater removed via _HW child id",
                "stored_hotwater" not in ctl_entry,
                f"ctl={json.dumps(ctl_entry)[:150]}",
            )
            ctx.check(
                "zones kept after DHW removal",
                "03" in ctl_entry.get("zones", {}),
                f"zones={sorted(ctl_entry.get('zones', {}))}",
            )
            ctx.check(
                "DHW child removed from device registry",
                not await self._child_in_device_registry(ctx, _DHW_CHILD_ID),
                f"{_DHW_CHILD_ID} still registered",
            )
        except RuntimeError as e:
            ctx.check("remove_device _HW child call", False, str(e)[:120])
