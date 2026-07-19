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
                ctx.wait(3, "for coordinator refresh")

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
        else:
            print(f"  SKIP: TRV {TRV} not in schema")
