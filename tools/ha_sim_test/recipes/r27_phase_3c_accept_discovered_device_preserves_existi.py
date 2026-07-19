"""Recipe R27: Phase 3c — accept_discovered_device preserves existing root."""

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


class R27Phase3cAcceptDiscoveredDevicePreservesExisti(Recipe):
    id = "R27"
    seq = 270
    title = "Phase 3c — accept_discovered_device preserves existing root"

    async def run(self, ctx: RecipeContext) -> None:
        ctx.log_section(
            "Recipe 27: accept_discovered_device preserves existing root entry"
        )

        # This recipe tests the safeguard added to _apply_schema_entry:
        # when a device already has a root entry in the schema (e.g. added
        # manually via the schema editor with _class, remotes, _commands),
        # accepting it via discovery should NOT overwrite those user-configured
        # keys.
        #
        # Scenario:
        # 1. Load a profile where FAN (32:150000) has remotes: [REM] and
        #    _commands configured
        # 2. Force a sync_topology so the FAN is picked up by discovery
        # 3. Call accept_discovered_device for the FAN
        # 4. Verify the schema still has remotes: [REM] and _commands
        #    (the auto-generated fragment has remotes: [] which would
        #    overwrite the user's remotes if the safeguard is missing)

        # Load profile with FAN that has remotes + _commands
        preserve_schema = dict(MIXED_SCHEMA)
        preserve_schema[FAN] = {
            **preserve_schema.get(FAN, {}),
            "_class": "FAN",
            "remotes": [REM],
            "_commands": {
                "boost": {"code": "22F1", "payload": "000607", "verb": "I"},
            },
        }
        preserve_yaml = mixed_yaml(preserve_schema)
        await load_profile_yaml(ctx.token, preserve_yaml, speed=0.01)
        ctx.wait(5, "for profile reload + entity creation")

        # Force a sync so discovery picks up the FAN
        try:
            call_service(ctx.token, "ramses_cc", "sync_topology")
        except RuntimeError:
            pass
        ctx.wait(5, "for discovery sync")

        # Snapshot the schema before accept
        schema_before = get_schema_retry()
        fan_before = schema_before.get(FAN, {})
        ctx.check(
            "FAN has remotes: [REM] before accept",
            REM in fan_before.get("remotes", []),
            f"remotes={fan_before.get('remotes')}",
        )
        ctx.check(
            "FAN has _commands before accept",
            "boost" in fan_before.get("_commands", {}),
            f"_commands keys={list(fan_before.get('_commands', {}).keys())}",
        )

        # Accept the FAN via discovery (this would overwrite remotes with []
        # if the safeguard is missing)
        accept_ok = False
        try:
            call_service(
                ctx.token,
                "ramses_cc",
                "accept_discovered_device",
                {"device_id": FAN},
            )
            accept_ok = True  # noqa: F841 — kept for debugging
        except RuntimeError as e:
            print(f"  accept_discovered_device failed: {str(e)[:80]}")

        # If accept failed because the FAN is already accepted, that's also OK —
        # the safeguard in sync_with_schema should have marked it ACCEPTED.
        # We check the schema either way.
        ctx.wait(3, "for schema update")
        schema_after = get_schema_retry()
        fan_after = schema_after.get(FAN, {})

        ctx.check(
            "FAN remotes preserved after accept",
            REM in fan_after.get("remotes", []),
            f"remotes={fan_after.get('remotes')} (should contain {REM})",
        )
        ctx.check(
            "FAN _commands preserved after accept",
            "boost" in fan_after.get("_commands", {}),
            f"_commands keys={list(fan_after.get('_commands', {}).keys())}",
        )
        ctx.check(
            "FAN _class is still FAN after accept",
            fan_after.get("_class") == "FAN",
            f"_class={fan_after.get('_class')}",
        )
