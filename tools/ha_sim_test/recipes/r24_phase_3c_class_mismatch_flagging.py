"""Recipe R24: Phase 3c — class mismatch flagging."""

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


class R24Phase3cClassMismatchFlagging(Recipe):
    id = "R24"
    seq = 280
    title = "Phase 3c — class mismatch flagging"

    async def run(self, ctx: RecipeContext) -> None:
        ctx.log_section("Recipe 24: Phase 3c — class mismatch flagging")

        # This recipe tests that when the schema has a wrong _class for a
        # device, the mismatch is detected and surfaced as:
        # 1. A persistent notification
        # 2. An entity attribute (class_mismatch)
        #
        # We load a profile where the FAN (32:150000) has _class="DIS"
        # instead of "FAN", then check that the mismatch is flagged.

        mismatch_schema = dict(MIXED_SCHEMA)
        mismatch_schema[FAN] = {
            **mismatch_schema.get(FAN, {}),
            "_class": "DIS",  # wrong class — should be FAN
        }
        mismatch_yaml = mixed_yaml(mismatch_schema)
        await load_profile_yaml(ctx.token, mismatch_yaml, speed=0.01)
        ctx.wait(5, "for profile reload + entity creation")

        # Force a sync cycle to trigger mismatch detection
        try:
            call_service(ctx.token, "ramses_cc", "sync_topology")
        except RuntimeError:
            pass
        ctx.wait(5, "for mismatch detection")
        try:
            call_service(ctx.token, "ramses_cc", "force_update")
        except RuntimeError:
            pass
        ctx.wait(3, "for save")

        # Check 1: FAN remote entity should have class_mismatch attribute
        # The remote entity (remote.fan_32_150000) inherits from RamsesEntity
        # which surfaces mismatch flags. Search by device_id only.
        entities = get_entities(ctx.token)
        fan_remote = None
        for e in entities:
            eid = e.get("entity_id", "")
            if "32_150000" in eid and eid.startswith("remote."):
                fan_remote = e
                break
        fan_attrs = fan_remote.get("attributes", {}) if fan_remote else {}
        ctx.check(
            "FAN remote entity has class_mismatch attribute",
            "class_mismatch" in fan_attrs,
            f"attrs keys={list(fan_attrs.keys())[:15]}",
        )
        if "class_mismatch" in fan_attrs:
            ctx.check(
                "class_mismatch shows schema=DIS, discovery=FAN",
                "DIS" in fan_attrs["class_mismatch"]
                and "FAN" in fan_attrs["class_mismatch"],
                f"class_mismatch={fan_attrs['class_mismatch']}",
            )

        # Check 2: Persistent notification should exist
        notifications = await get_persistent_notifications(ctx.token)
        mismatch_notif = [
            n
            for n in notifications
            if "mismatch" in n.get("title", "").lower()
            or "mismatch" in n.get("notification_id", "").lower()
        ]
        ctx.check(
            "Persistent notification for mismatches exists",
            len(mismatch_notif) > 0,
            f"notifications={[n.get('notification_id') for n in notifications]}",
        )
