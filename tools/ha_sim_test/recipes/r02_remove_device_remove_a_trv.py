"""Recipe R02: remove_device — remove a TRV."""

from __future__ import annotations

import json
import subprocess
import time
import urllib.request
from datetime import datetime as dt
from datetime import timedelta

from ..base import Recipe, RecipeContext
from ..const import CO2, CTL, DHW, FAN, HA_URL, HGI, REM, TRV
from ..helpers import (
    call_service,
    find_battery_entity,
    find_entity_for_device,
    get_cached_schema,
    get_entities,
    get_entity_attributes,
    get_known_list,
    get_persistent_notifications,
    get_ramses_storage,
    get_schema,
    get_schema_retry,
    load_profile_yaml,
    wait_for,
    write_ramses_storage,
    ws_send,
)
from ..profile import MIXED_KL, MIXED_SCHEMA, mixed_yaml


class R02RemoveDeviceRemoveATrv(Recipe):
    id = "R02"
    seq = 30
    title = "remove_device — remove a TRV"

    async def run(self, ctx: RecipeContext) -> None:
        ctx.log_section(f"Recipe 2: remove_device — remove TRV {TRV}")

        schema_before = get_schema_retry()
        trv_in_schema = TRV in json.dumps(schema_before)
        print(f"  TRV in schema: {trv_in_schema}")

        if trv_in_schema:
            entities_before = get_entities(ctx.token)
            trv_entity_before = find_entity_for_device(
                entities_before, TRV, prefix="trv_"
            )
            trv_eid = trv_entity_before["entity_id"] if trv_entity_before else "None"
            print(f"  TRV entity before: {trv_eid}")

            try:
                call_service(
                    ctx.token, "ramses_cc", "remove_device", {"device_id": TRV}
                )
                print("  remove_device call succeeded")

                # Poll until the TRV is removed from the config entry schema.
                # Under parallel load, the removal may not propagate to
                # .storage within the initial 3s wait.
                def _trv_removed() -> bool:
                    schema = get_schema()
                    return TRV not in json.dumps(schema)

                wait_for(
                    _trv_removed,
                    timeout=15,
                    interval=1,
                    msg=f"for {TRV} to be removed from schema",
                    floor=2.0,
                )

                # Check config entry schema (remove_device updates this directly).
                # The cached schema (.storage/ramses_cc) may still have the device
                # because async_save_client_state writes the LEARNED schema from
                # ramses_rf, which sync_learned_topology can merge back in.
                schema_after = get_schema()
                ctx.check(
                    "TRV removed from schema",
                    TRV not in json.dumps(schema_after),
                    f"schema still contains {TRV}",
                )

                kl_after = get_known_list()
                ctx.check(
                    "TRV removed from known_list",
                    TRV not in kl_after,
                    f"known_list still has {TRV}",
                )

                entities_after = get_entities(ctx.token)
                trv_entity_after = find_entity_for_device(
                    entities_after, TRV, prefix="trv_"
                )
                trv_eid_after = (
                    trv_entity_after["entity_id"] if trv_entity_after else "?"
                )
                ctx.check(
                    "TRV entity removed",
                    trv_entity_after is None,
                    f"entity still exists: {trv_eid_after}",
                )
            except RuntimeError as e:
                ctx.check("remove_device TRV call", False, str(e)[:80])
        # ── Part 2: HGI rejection check (merged from R03) ────────────
        ctx.log_section("Recipe 2: remove_device — HGI rejection")
        try:
            call_service(ctx.token, "ramses_cc", "remove_device", {"device_id": HGI})
            ctx.check("HGI removal raises error", False, "(no error raised)")
        except RuntimeError as e:
            ctx.check("HGI removal raises error", True, str(e)[:80])

        # ── Part 3: CTL / main_tcs removal (merged from R04) ─────────
        ctx.log_section(f"Recipe 2: remove_device — CTL {CTL} / main_tcs removal")
        schema_ctl = get_schema_retry()
        if CTL in schema_ctl:
            try:
                call_service(
                    ctx.token, "ramses_cc", "remove_device", {"device_id": CTL}
                )
                ctx.wait(3, "for CTL removal")
                schema_after_ctl = get_schema_retry()
                ctx.check(
                    "CTL top-level key removed",
                    CTL not in schema_after_ctl,
                    f"schema still contains {CTL}",
                )
                storage_r04 = get_ramses_storage()
                main_tcs = storage_r04.get("main_tcs")
                ctx.check(
                    "main_tcs cleared",
                    main_tcs is None,
                    f"main_tcs is still {main_tcs}",
                )
            except RuntimeError as e:
                ctx.check("remove_device CTL call", False, str(e)[:80])
