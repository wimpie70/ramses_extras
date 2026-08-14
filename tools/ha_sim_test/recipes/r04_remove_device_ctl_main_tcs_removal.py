"""Recipe R04: remove_device — CTL (main_tcs) removal."""

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


class R04RemoveDeviceCtlMainTcsRemoval(Recipe):
    id = "R04"
    seq = 40
    title = "remove_device — CTL (main_tcs) removal"

    async def run(self, ctx: RecipeContext) -> None:
        ctx.log_section(f"Recipe 4: remove_device — CTL {CTL} / main_tcs removal")

        schema_before = get_schema_retry()
        ctl_in_schema = CTL in schema_before
        main_tcs_before = schema_before.get("main_tcs")
        print(f"  CTL in schema: {ctl_in_schema}, main_tcs={main_tcs_before}")

        if ctl_in_schema:
            try:
                call_service(
                    ctx.token, "ramses_cc", "remove_device", {"device_id": CTL}
                )
                print("  remove_device CTL call succeeded")
                ctx.wait(3, "for refresh")

                schema_after = get_schema_retry()
                ctx.check(
                    "CTL top-level key removed",
                    CTL not in schema_after,
                    f"schema still has key {CTL}",
                )
                ctx.check(
                    "main_tcs cleared",
                    schema_after.get("main_tcs") is None,
                    f"main_tcs={schema_after.get('main_tcs')}",
                )
            except RuntimeError as e:
                ctx.check("remove_device CTL call", False, str(e)[:80])
        else:
            print(f"  SKIP: CTL {CTL} not in schema")
