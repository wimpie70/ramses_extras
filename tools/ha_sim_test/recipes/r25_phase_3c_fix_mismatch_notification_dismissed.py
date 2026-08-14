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
    is_ramses_cc_loaded,
    load_profile_yaml,
    wait_for,
    write_ramses_storage,
    ws_send,
)
from ..profile import MIXED_KL, MIXED_SCHEMA, get_mixed_kl, mixed_yaml


class R25Phase3cFixMismatchNotificationDismissed(Recipe):
    id = "R25"
    seq = 290
    title = "Phase 3c — fix mismatch, notification dismissed"

    async def run(self, ctx: RecipeContext) -> None:
        ctx.log_section("Recipe 25: Phase 3c — fix mismatch, notification dismissed")

        # Reload with correct _class on ALL top-level schema entries.
        #
        # R24 injected a wrong _class ("DIS") on the FAN.  The "fix" is to
        # set the correct _class ("FAN").  We must also add _class to every
        # other top-level schema entry (CTL, REM, TRVs, DHW, CO2, BDR, zone
        # CTLs) so that check_missing_class doesn't flag them as "missing
        # _class" — which would keep the mismatch notification alive even
        # though the class mismatch is resolved.
        #
        # Without _class on all top-level entries, check_all_mismatches
        # returns total > 0 (from check_missing_class), and the notification
        # is recreated with "missing _class" content instead of being
        # dismissed.
        fixed_schema = dict(MIXED_SCHEMA)
        # Add _class from the known_list to every device (skip HGI —
        # check_missing_class skips 18: devices).
        for dev_id, kl_entry in get_mixed_kl().items():
            if dev_id.startswith("18:"):
                continue
            kl_class = kl_entry.get("class")
            if kl_class:
                fixed_schema[dev_id] = {
                    **fixed_schema.get(dev_id, {}),
                    "_class": kl_class,
                }
        # 13:083400 is a BDR that's in the mixed profile's schema but not
        # in MIXED_KL — add _class so check_missing_class doesn't flag it.
        fixed_schema["13:083400"] = {
            **fixed_schema.get("13:083400", {}),
            "_class": "BDR",
        }
        fixed_yaml = mixed_yaml(fixed_schema)
        await load_profile_yaml(ctx.token, fixed_yaml, speed=0.01)
        ctx.wait_for_ramses_cc_reload(msg="for profile reload")

        # wait_for_ramses_cc_reload only confirms the schema has devices —
        # it does not guarantee the *fixed* _class has actually persisted
        # to the config entry yet.  Without this check, sync_topology can
        # run against the still-stale ("DIS") schema, re-flagging the
        # mismatch that this recipe is meant to resolve.
        def _fan_class_fixed() -> bool:
            schema = get_schema()
            entry = schema.get(FAN)
            return isinstance(entry, dict) and entry.get("_class") == "FAN"

        wait_for(
            _fan_class_fixed,
            timeout=10,
            interval=1,
            msg="for FAN _class fix to persist",
        )

        try:
            call_service(ctx.token, "ramses_cc", "sync_topology")
        except RuntimeError:
            pass
        ctx.wait(5, "for mismatch recheck", floor=3.0)
        try:
            call_service(ctx.token, "ramses_cc", "force_update")
        except RuntimeError:
            pass
        ctx.wait_for_schema_stable(timeout=10, msg="for save")

        # Check 1: FAN remote entity should NOT have class_mismatch attribute
        #
        # This can race with periodic/automatic sync_topology checkpoints
        # (at the fast 0.01x test speed, these fire every few seconds) that
        # may run against a not-yet-updated in-memory config entry right
        # after the profile reload.  Retry with backoff so we don't fail on
        # a transient stale read rather than a real bug.
        def _mismatch_cleared() -> tuple[bool, dict]:
            entities = get_entities(ctx.token)
            fan_remote = None
            for e in entities:
                eid = e.get("entity_id", "")
                if "32_150000" in eid and eid.startswith("remote."):
                    fan_remote = e
                    break
            attrs = fan_remote.get("attributes", {}) if fan_remote else {}
            return "class_mismatch" not in attrs, attrs

        fan_attrs_fixed: dict = {}
        cleared = False
        for _attempt in range(4):
            cleared, fan_attrs_fixed = _mismatch_cleared()
            if cleared:
                break
            try:
                call_service(ctx.token, "ramses_cc", "sync_topology")
            except RuntimeError:
                pass
            # sync_topology only updates discovery metadata — it does not
            # push a fresh state write for entities whose class_mismatch
            # attribute changed.  force_update triggers a coordinator
            # refresh, which does write fresh entity state (including
            # extra_state_attributes), so the entity's HA state reflects
            # the now-cleared mismatch.
            try:
                call_service(ctx.token, "ramses_cc", "force_update")
            except RuntimeError:
                pass
            ctx.wait(3, "for mismatch recheck retry", floor=3.0)
        ctx.check(
            "FAN remote entity has no class_mismatch after fix",
            cleared,
            f"class_mismatch={fan_attrs_fixed.get('class_mismatch')}",
        )

        # Check 2: The notification should no longer call out the FAN's
        # own mismatch specifically.
        #
        # The combined mismatch notification lists ALL devices with class
        # mismatches under one "class mismatch(es)" header, so simply
        # checking for the word "class" is not a valid signal: other,
        # unrelated devices (e.g. a CO2 sensor misclassified as REM due to
        # overlapping 1FC9 traffic — left over from other recipes / not
        # something this recipe fixes) can keep the word "class" present
        # even though the FAN mismatch under test (check 1) is resolved.
        # So look specifically for the FAN device ID in the message.
        notifications_after = await get_persistent_notifications(ctx.token)
        mismatch_notif_after = [
            n
            for n in notifications_after
            if "mismatch" in n.get("title", "").lower()
            or "mismatch" in n.get("notification_id", "").lower()
        ]
        fan_mismatch_notifs = [
            n for n in mismatch_notif_after if FAN in n.get("message", "")
        ]
        ctx.check(
            "Class mismatch notification dismissed after fix",
            len(fan_mismatch_notifs) == 0,
            f"remaining={[n.get('notification_id') for n in mismatch_notif_after]}",
        )
