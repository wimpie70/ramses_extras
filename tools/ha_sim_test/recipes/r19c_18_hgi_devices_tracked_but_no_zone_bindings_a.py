"""Recipe R19c: 18: (HGI) devices tracked but no zone bindings [A]."""

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


class R19c18HgiDevicesTrackedButNoZoneBindingsA(Recipe):
    id = "R19c"
    seq = 210
    title = "18: (HGI) devices tracked but no zone bindings [A]"

    async def run(self, ctx: RecipeContext) -> None:
        ctx.log_section("Recipe 19c: 18: (HGI) devices tracked but no zone bindings")

        # Inject a 30C9 packet from an 18: device — the scan engine should
        # track it (as HGI type) but NOT set zone_idx or bound_to.
        hgi_dev = "18:999999"
        print(f"  Injecting 30C9 from {hgi_dev} (should be tracked, no zone)...")
        try:
            call_service(
                ctx.token,
                "ramses_extras",
                "device_simulator_inject_message",
                {
                    "source_id": hgi_dev,
                    "code": "30C9",
                    "payload": "020708",
                    "verb": "I",
                },
            )
        except RuntimeError as e:
            print(f"  Inject failed: {e}")

        ctx.wait(5, "for scan engine to process")
        try:
            call_service(ctx.token, "ramses_cc", "sync_topology")
        except RuntimeError:
            pass
        ctx.wait(5, "for sync_learned_topology")
        try:
            call_service(ctx.token, "ramses_cc", "force_update")
        except RuntimeError:
            pass
        ctx.wait(5, "for save")

        schema_r19c = get_schema_retry()
        ctl_r19c = schema_r19c.get(CTL, {})
        zones_r19c = ctl_r19c.get("zones", {}) if isinstance(ctl_r19c, dict) else {}

        # HGI should NOT be a zone sensor (18: is not a valid SEN prefix)
        for zone in zones_r19c.values():
            if isinstance(zone, dict):
                ctx.check(
                    "18: device not a zone sensor",
                    zone.get("sensor") != hgi_dev,
                    f"sensor={zone.get('sensor')}",
                )
                break

        # HGI should NOT have zones created under it in the schema
        hgi_entry_r19c = schema_r19c.get(hgi_dev, {})
        if isinstance(hgi_entry_r19c, dict):
            ctx.check(
                "18: device has no zones in schema",
                "zones" not in hgi_entry_r19c,
                f"keys={list(hgi_entry_r19c.keys())}",
            )
