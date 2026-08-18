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
    is_ramses_cc_loaded,
    load_profile_yaml,
    wait_for,
    wait_for_async,
    wait_for_transport_ready,
    write_ramses_storage,
    ws_send,
)
from ..profile import MIXED_KL, MIXED_SCHEMA, get_mixed_kl, mixed_yaml


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
        # Build a custom known_list that does NOT include class=FAN for the
        # FAN device — otherwise _merge_known_list_into_schema would
        # overwrite the schema's _class=DIS with _class=FAN from the
        # known_list, defeating the purpose of the mismatch test.
        import yaml as _yaml

        mismatch_kl = get_mixed_kl()
        fan_kl = dict(mismatch_kl.get(FAN, {}))
        fan_kl.pop("class", None)
        mismatch_kl[FAN] = fan_kl
        profile = {
            "known_list": mismatch_kl,
            "_enforce_known_list": {"enabled": True},
            "_schema": mismatch_schema,
        }
        mismatch_yaml = _yaml.dump(profile, default_flow_style=False, sort_keys=False)
        await load_profile_yaml(ctx.token, mismatch_yaml, speed=0.01)
        ctx.wait_for_ramses_cc_reload(msg="for profile reload")
        ctx.refresh_token()
        # Wait for the MQTT transport to reconnect after the reload,
        # otherwise the 1FC9 heartbeat injection is silently dropped
        # and the scan engine never sees 32:150000.
        wait_for_transport_ready(timeout=30)

        # Activate the FAN device so it starts sending messages and the
        # remote entity is created.  On fresh containers (parallel runs),
        # the FAN is not yet active and no entities exist.
        try:
            await ws_send(
                ctx.token,
                {
                    "type": "ramses_extras/device_simulator/activate_profile_device",
                    "device_id": FAN,
                },
            )
            print(f"  FAN {FAN} activated")
        except RuntimeError as e:
            if "already_active" in str(e):
                print(f"  FAN {FAN} already active")
            else:
                print(f"  FAN activate failed: {str(e)[:80]}")
                # If the FAN is not in the profile, the profile load failed
                # and all subsequent checks will be false negatives.  Bail.
                if "not defined in profile" in str(e):
                    ctx.check(
                        "FAN remote entity has class_mismatch attribute",
                        False,
                        "FAN not in profile (profile load failed)",
                    )
                    ctx.check(
                        "Persistent notification for mismatches exists",
                        False,
                        "FAN not in profile (profile load failed)",
                    )
                    return

        # Inject a 1FC9 heartbeat from the FAN so the scan engine tracks
        # 32:150000 and can detect the _class=DIS mismatch.  The profile
        # reload stops all simulator devices, so without this injection the
        # scan engine has no data for 32:150000 and check_class_mismatches
        # skips it.  Retry up to 3 times — the MQTT endpoint may not be
        # fully connected immediately after the reload.
        for attempt in range(3):
            try:
                call_service(
                    ctx.token,
                    "ramses_extras",
                    "device_simulator_inject_message",
                    {
                        "source_id": FAN,
                        "code": "1FC9",
                        "payload": "00",
                        "verb": "I",
                    },
                )
                break
            except RuntimeError as e:
                print(
                    f"    FAN heartbeat inject attempt {attempt + 1} failed:"
                    f" {str(e)[:80]}"
                )
                ctx.wait(3, "before retry")
        ctx.wait(5, "for FAN heartbeat to reach scan engine", floor=4.0)

        # Force a sync cycle to trigger mismatch detection
        try:
            call_service(ctx.token, "ramses_cc", "sync_topology")
        except RuntimeError:
            pass
        ctx.wait(5, "for mismatch detection", floor=4.0)
        try:
            call_service(ctx.token, "ramses_cc", "force_update")
        except RuntimeError:
            pass
        ctx.wait_for_schema_stable(timeout=10, msg="for save")

        # Check 1: FAN remote entity should have class_mismatch attribute
        # The remote entity (remote.fan_32_150000) inherits from RamsesEntity
        # which surfaces mismatch flags. Search by device_id only.
        # Poll until the mismatch attribute appears.  Re-trigger sync_topology
        # periodically because mismatch detection only runs during sync cycles.
        _sync_retry_count = 0

        def _has_class_mismatch() -> bool:
            nonlocal _sync_retry_count
            entities = get_entities(ctx.token)
            for e in entities:
                eid = e.get("entity_id", "")
                if "32_150000" in eid and eid.startswith("remote."):
                    if "class_mismatch" in e.get("attributes", {}):
                        return True
            # Re-trigger sync + force_update every other poll to force
            # mismatch detection and entity state write.
            _sync_retry_count += 1
            if _sync_retry_count % 2 == 0:
                try:
                    call_service(ctx.token, "ramses_cc", "sync_topology")
                except RuntimeError:
                    pass
                try:
                    call_service(ctx.token, "ramses_cc", "force_update")
                except RuntimeError:
                    pass
            return False

        wait_for(
            _has_class_mismatch,
            timeout=60,
            interval=3,
            msg="for class_mismatch attribute to appear",
            floor=10.0,
        )
        # Read final state for the check
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

        # Check 2: Persistent notification should exist.
        # Poll until the notification is created by the mismatch detection cycle.
        async def _has_mismatch_notif() -> bool:
            notifications = await get_persistent_notifications(ctx.token)
            return any(
                "mismatch" in n.get("title", "").lower()
                or "mismatch" in n.get("notification_id", "").lower()
                for n in notifications
            )

        await wait_for_async(
            _has_mismatch_notif,
            timeout=30,
            interval=2,
            msg="for mismatch notification to appear",
            floor=5.0,
        )
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
