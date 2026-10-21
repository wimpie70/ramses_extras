"""Recipe R154: UFH window_open suppression and circuit names (PR 1360).

Verifies https://github.com/ramses-rf/ramses_cc/pull/1360:

1. ``window_open`` binary sensor suppression for UFH zones:
   - A radiator valve zone (``09``, ``class: radiator_valve``) registers a
     ``window_open`` binary sensor (``unique_id: 01:150000_09-window_open``).
   - Underfloor heating zones (``0A`` and ``0B``,
     ``class: underfloor_heating``) do NOT register ``window_open`` binary
     sensors, because UFH zones do not use TRVs or emit ``12B0`` frames.

2. ``UfhCircuit`` friendly device naming and ``suggested_area``:
   - When a ``UfhCircuit`` is bound to a named zone (``0A``,
     ``_name: "Living Room"``), its HA device registry entry is named
     ``"Living Room Circuit 00"`` (never ``"<bound method ...>"``) and its
     area is assigned from ``suggested_area="Living Room"``.
   - When a ``UfhCircuit`` is bound to an unnamed zone (``0B``), its HA
     device registry entry falls back to ``"UFH Circuit 02:150050_01"``.
"""

from __future__ import annotations

from typing import Any

from ..base import Recipe, RecipeContext
from ..const import CTL, HGI, TRV
from ..helpers import (
    load_profile_yaml,
    wait_for_async,
    wait_for_transport_ready,
    ws_send,
)
from ..profile import _build_yaml

_UFC = "02:150050"
_THM_RAD = "22:150001"
_THM_UFH = "22:150002"

# Use zone indices 09-0B so pre-existing entity registry entries for
# zones 00-08 from the base HA storage snapshot cannot cause false
# positives.
_ZONE_RAD = "09"
_ZONE_UFH_NAMED = "0A"
_ZONE_UFH_UNNAMED = "0B"

_ZONE_UFH_NAME = "Living Room"

_CCT_BOUND_NAMED_ID = f"{_UFC}_00"
_CCT_BOUND_UNNAMED_ID = f"{_UFC}_01"

_RAD_WINDOW_UID = f"{CTL}_{_ZONE_RAD}-window_open"
_UFH_NAMED_WINDOW_UID = f"{CTL}_{_ZONE_UFH_NAMED}-window_open"
_UFH_UNNAMED_WINDOW_UID = f"{CTL}_{_ZONE_UFH_UNNAMED}-window_open"


def _profile_yaml() -> str:
    """Build profile with 1 RAD zone, 2 UFH zones, and 1 UFC with 2 circuits."""
    kl = {
        HGI: {"class": "HGI"},
        CTL: {"class": "CTL"},
        _UFC: {"class": "UFC"},
        _THM_RAD: {"class": "THM"},
        _THM_UFH: {"class": "THM"},
        TRV: {"class": "TRV"},
    }
    schema = {
        CTL: {
            "underfloor_heating": {
                _UFC: {
                    "circuits": {
                        "00": {"zone_index": _ZONE_UFH_NAMED},
                        "01": {"zone_index": _ZONE_UFH_UNNAMED},
                    }
                }
            },
            "zones": {
                _ZONE_RAD: {
                    "_name": "Kitchen",
                    "class": "radiator_valve",
                    "sensor": _THM_RAD,
                    "actuators": [TRV],
                },
                _ZONE_UFH_NAMED: {
                    "_name": _ZONE_UFH_NAME,
                    "class": "underfloor_heating",
                    "sensor": _THM_UFH,
                },
                _ZONE_UFH_UNNAMED: {
                    "class": "underfloor_heating",
                },
            },
        },
    }
    return _build_yaml(kl, schema)


class R154UfhWindowOpenAndCircuitNamesPr1360(Recipe):
    id = "R154"
    seq = 1540
    title = "UFH window_open suppression and circuit names (PR 1360)"
    tags = ("ufh", "binary_sensor", "device_registry", "pr_1360")

    async def _get_entity_registry(self, ctx: RecipeContext) -> list[dict[str, Any]]:
        """Return all entries in the HA entity registry."""
        resp: Any = await ws_send(ctx.token, {"type": "config/entity_registry/list"})
        if isinstance(resp, list):
            return resp
        entities = resp.get("entities", [])
        return entities if isinstance(entities, list) else []

    async def _get_device_by_ramses_id(
        self, ctx: RecipeContext, ramses_id: str
    ) -> dict[str, Any] | None:
        """Look up a device registry entry by its ramses_cc identifier."""
        resp: Any = await ws_send(ctx.token, {"type": "config/device_registry/list"})
        devices = resp if isinstance(resp, list) else resp.get("devices", [])
        for dev in devices:
            if not isinstance(dev, dict):
                continue
            for ident in dev.get("identifiers", []):
                if (
                    isinstance(ident, list)
                    and len(ident) == 2
                    and ident[0] == "ramses_cc"
                    and ident[1] == ramses_id
                ):
                    return dev
        return None

    async def run(self, ctx: RecipeContext) -> None:
        ctx.log_section(
            "Recipe 154: UFH window_open suppression & circuit names (PR 1360)"
        )

        # Drop stale ``<tcs>_NN-window_open`` registry entries for the UFH
        # zones before arranging: an entry left behind by an earlier
        # lifecycle where the zone was not underfloor-heated is no longer
        # provided, but still reads as a suppression failure.
        stale_uids = {_UFH_NAMED_WINDOW_UID, _UFH_UNNAMED_WINDOW_UID}
        for entry in await self._get_entity_registry(ctx):
            if entry.get("unique_id") in stale_uids and (
                entity_id := entry.get("entity_id")
            ):
                print(f"  Removing stale registry entry {entity_id}")
                await ws_send(
                    ctx.token,
                    {
                        "type": "config/entity_registry/remove",
                        "entity_id": entity_id,
                    },
                )

        # Arrange: Load profile with RAD zone 00, named UFH zone 01,
        # unnamed UFH zone 02, and UFC 02:150050 with circuits 00 & 01.
        print("  Loading UFH + RAD profile...")
        try:
            await load_profile_yaml(
                ctx.token,
                _profile_yaml(),
                speed=0.01,
                preload_schema=True,
                reload_ramses=True,
            )
        except RuntimeError as err:
            ctx.check("profile loaded", False, detail=str(err)[:200])
            return

        ctx.wait_for_ramses_cc_reload(timeout=30)
        ctx.refresh_token()
        wait_for_transport_ready(timeout=30)
        ctx.wait_for_schema_stable(timeout=15)

        # Act: Wait for the coordinator to discover zones and UFH circuits
        # and register their entities and child devices.
        async def _rad_window_and_circuits_registered() -> bool:
            entities = await self._get_entity_registry(ctx)
            uids = {e.get("unique_id") for e in entities}
            dev_named = await self._get_device_by_ramses_id(ctx, _CCT_BOUND_NAMED_ID)
            dev_unnamed = await self._get_device_by_ramses_id(
                ctx, _CCT_BOUND_UNNAMED_ID
            )
            return (
                _RAD_WINDOW_UID in uids
                and dev_named is not None
                and dev_unnamed is not None
            )

        ready = await wait_for_async(
            _rad_window_and_circuits_registered,
            timeout=45,
            interval=2.0,
            msg="for RAD window_open and UFH circuit devices to register",
            floor=15.0,
        )
        ctx.check(
            "RAD window_open and UFH circuit devices registered",
            ready,
        )

        # Assert 1: window_open exists for RAD zone 00, but is suppressed
        # for UFH zones 01 and 02.
        entities = await self._get_entity_registry(ctx)
        uids = {str(e.get("unique_id")) for e in entities}

        ctx.check(
            f"RAD zone {_ZONE_RAD} has window_open binary_sensor",
            _RAD_WINDOW_UID in uids,
            f"expected {_RAD_WINDOW_UID} in entity registry",
        )
        ctx.check(
            f"UFH zone {_ZONE_UFH_NAMED} suppresses window_open binary_sensor",
            _UFH_NAMED_WINDOW_UID not in uids,
            f"unexpected {_UFH_NAMED_WINDOW_UID} found in entity registry",
        )
        ctx.check(
            f"UFH zone {_ZONE_UFH_UNNAMED} suppresses window_open binary_sensor",
            _UFH_UNNAMED_WINDOW_UID not in uids,
            f"unexpected {_UFH_UNNAMED_WINDOW_UID} found in entity registry",
        )

        # Assert 2: Circuit 00 (bound to named zone 01 "Living Room") gets
        # friendly name "Living Room Circuit 00" and never "<bound method".
        expected_named = f"{_ZONE_UFH_NAME} Circuit 00"

        async def _circuit_named_resolved() -> bool:
            dev = await self._get_device_by_ramses_id(ctx, _CCT_BOUND_NAMED_ID)
            return dev is not None and dev.get("name") == expected_named

        await wait_for_async(
            _circuit_named_resolved,
            timeout=20,
            interval=2.0,
            msg=f"for {_CCT_BOUND_NAMED_ID} name={expected_named!r}",
            floor=5.0,
        )

        dev_named = await self._get_device_by_ramses_id(ctx, _CCT_BOUND_NAMED_ID)
        named_actual = dev_named.get("name") if dev_named else None
        named_area = dev_named.get("area_id") if dev_named else None
        print(f"  Circuit 00 device: name={named_actual!r}, area_id={named_area!r}")

        ctx.check(
            f"bound circuit {_CCT_BOUND_NAMED_ID} has friendly zone name",
            named_actual == expected_named,
            f"name={named_actual!r}, expected={expected_named!r}",
        )
        ctx.check(
            f"bound circuit {_CCT_BOUND_NAMED_ID} name is not coroutine repr",
            named_actual is not None and "bound method" not in named_actual,
            f"name={named_actual!r}",
        )
        ctx.check(
            f"bound circuit {_CCT_BOUND_NAMED_ID} assigned area from zone name",
            named_area is not None and "bound_method" not in str(named_area),
            f"area_id={named_area!r}",
        )

        # Assert 3: Circuit 01 (bound to unnamed zone 02) uses fallback
        # name "UFH Circuit 02:150050_01".
        expected_unnamed = f"UFH Circuit {_CCT_BOUND_UNNAMED_ID}"
        dev_unnamed = await self._get_device_by_ramses_id(ctx, _CCT_BOUND_UNNAMED_ID)
        unnamed_actual = dev_unnamed.get("name") if dev_unnamed else None
        print(f"  Circuit 01 device: name={unnamed_actual!r}")

        ctx.check(
            f"unnamed-zone circuit {_CCT_BOUND_UNNAMED_ID} uses fallback name",
            unnamed_actual == expected_unnamed,
            f"name={unnamed_actual!r}, expected={expected_unnamed!r}",
        )
