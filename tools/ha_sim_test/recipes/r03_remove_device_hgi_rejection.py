"""Recipe R03: remove_device — HGI rejection."""

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


class R03RemoveDeviceHgiRejection(Recipe):
    id = "R03"
    seq = 20
    title = "remove_device — HGI rejection"

    async def run(self, ctx: RecipeContext) -> None:
        ctx.log_section("Recipe 3: remove_device — HGI rejection")
        try:
            call_service(ctx.token, "ramses_cc", "remove_device", {"device_id": HGI})
            ctx.check("HGI removal raises error", False, "(no error raised)")
        except RuntimeError as e:
            ctx.check("HGI removal raises error", True, str(e)[:80])
