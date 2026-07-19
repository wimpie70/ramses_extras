"""Recipe R25: Phase 3c — fix mismatch, notification dismissed."""

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


class R25Phase3cFixMismatchNotificationDismissed(Recipe):
    id = "R25"
    seq = 290
    title = "Phase 3c — fix mismatch, notification dismissed"

    async def run(self, ctx: RecipeContext) -> None:
        ctx.log_section("Recipe 25: Phase 3c — fix mismatch, notification dismissed")

        # Reload with correct _class — mismatch should clear
        fixed_yaml = mixed_yaml()  # default MIXED_SCHEMA has no _class override
        await load_profile_yaml(ctx.token, fixed_yaml, speed=0.01)
        ctx.wait(5, "for profile reload")

        try:
            call_service(ctx.token, "ramses_cc", "sync_topology")
        except RuntimeError:
            pass
        ctx.wait(5, "for mismatch recheck")
        try:
            call_service(ctx.token, "ramses_cc", "force_update")
        except RuntimeError:
            pass
        ctx.wait(3, "for save")

        # Check 1: FAN remote entity should NOT have class_mismatch attribute
        entities_fixed = get_entities(ctx.token)
        fan_remote_fixed = None
        for e in entities_fixed:
            eid = e.get("entity_id", "")
            if "32_150000" in eid and eid.startswith("remote."):
                fan_remote_fixed = e
                break
        fan_attrs_fixed = (
            fan_remote_fixed.get("attributes", {}) if fan_remote_fixed else {}
        )
        ctx.check(
            "FAN remote entity has no class_mismatch after fix",
            "class_mismatch" not in fan_attrs_fixed,
            f"class_mismatch={fan_attrs_fixed.get('class_mismatch')}",
        )

        # Check 2: Mismatch notification should be dismissed
        notifications_after = await get_persistent_notifications(ctx.token)
        mismatch_notif_after = [
            n
            for n in notifications_after
            if "mismatch" in n.get("title", "").lower()
            or "mismatch" in n.get("notification_id", "").lower()
        ]
        ctx.check(
            "Mismatch notification dismissed after fix",
            len(mismatch_notif_after) == 0,
            f"remaining={[n.get('notification_id') for n in mismatch_notif_after]}",
        )
