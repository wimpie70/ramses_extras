"""Recipe R18: add_faked_rem service — creates faked REM bound to FAN."""

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


class R18AddFakedRemServiceCreatesFakedRemBoundToF(Recipe):
    id = "R18"
    seq = 180
    title = "add_faked_rem service — creates faked REM bound to FAN"

    async def run(self, ctx: RecipeContext) -> None:
        ctx.log_section("Recipe 18: add_faked_rem service")

        # add_faked_rem creates a virtual REM device bound to a FAN.
        # It should:
        #   1. Create a discovery metadata entry with _faked/_bound/_class traits
        #   2. Merge the schema entry into the config entry schema (persisted)
        #   3. Trigger discover_known_devices to create the HA entity
        #
        # We use a fresh device ID to avoid conflicts with existing REMs.

        faked_rem_id = "37:999999"
        ctx.shared["faked_rem_id"] = faked_rem_id
        print(f"  Adding faked REM {faked_rem_id} bound to {FAN}...")
        try:
            call_service(
                ctx.token,
                "ramses_cc",
                "add_faked_rem",
                {
                    "device_id": faked_rem_id,
                    "bound_to": FAN,
                    "alias": "Test Faked REM",
                },
            )
            print("  add_faked_rem service call succeeded")
            ctx.wait(3, "for schema merge + entity creation")
            # Force a save cycle to persist the config entry
            try:
                call_service(ctx.token, "ramses_cc", "force_update")
            except RuntimeError:
                pass
            ctx.wait(5, "for config entry persistence")
            ctx.check("add_faked_rem service call succeeds", True, "")
        except RuntimeError as e:
            ctx.check("add_faked_rem service call succeeds", False, str(e)[:80])

        # Verify the faked REM appears in the known_list (no DeviceNotFoundError
        # log spam) by checking the HA log for errors about this device.
        log_data_r18 = ctx.log_monitor.collect()
        all_log_lines = log_data_r18.get("errors", []) + log_data_r18.get(
            "warnings", []
        )
        faked_errors = [
            line
            for line in all_log_lines
            if faked_rem_id in line
            and ("DeviceNotFoundError" in line or "excluded" in line)
        ]
        ctx.check(
            f"no DeviceNotFoundError for {faked_rem_id}",
            len(faked_errors) == 0,
            f"{len(faked_errors)} error lines",
        )

        # Verify the schema entry was persisted with _ prefix traits by
        # reading the config entry from .storage (API may be stale).
        schema_r18 = get_schema_retry()
        entry_traits = schema_r18.get(faked_rem_id, {})
        ctx.check(
            f"schema has {faked_rem_id} with _faked trait",
            isinstance(entry_traits, dict) and entry_traits.get("_faked") is True,
            f"got: {entry_traits}",
        )
        ctx.check(
            f"schema has {faked_rem_id} with _bound to {FAN}",
            isinstance(entry_traits, dict) and entry_traits.get("_bound") == FAN,
            f"got: {entry_traits}",
        )

        # Check that the REM was added to the FAN's remotes list
        fan_entry_r18 = schema_r18.get(FAN, {})
        fan_remotes = (
            fan_entry_r18.get("remotes", []) if isinstance(fan_entry_r18, dict) else []
        )
        ctx.check(
            f"REM {faked_rem_id} in FAN {FAN} remotes list",
            faked_rem_id in fan_remotes,
            f"remotes={fan_remotes}",
        )
