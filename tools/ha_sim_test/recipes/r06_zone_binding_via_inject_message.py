"""Recipe R06: Zone binding via inject_message."""

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


class R06ZoneBindingViaInjectMessage(Recipe):
    id = "R06"
    seq = 10
    title = "Zone binding via inject_message"

    async def run(self, ctx: RecipeContext) -> None:
        ctx.log_section("Recipe 6/14: Zone binding via inject_message")

        # 000C payload format: zone_idx(1) + zone_type(1) + pad(1) + dev_hex_id(3)
        # The dev_hex_id is NOT the raw device address — it's the transformed hex
        # from ramses_rf.address.dev_id_to_hex_id().
        # 04:150003 → dev_id_to_hex_id → "1249F3"
        # zone_type 08 = rad_actuator
        # We inject zone 09 (doesn't exist yet) with TRV 04:150003
        target_zone = "09"
        trv_hex_id = "1249F3"  # dev_id_to_hex_id("04:150003")
        inject_payload = f"{target_zone}0800{trv_hex_id}"

        schema_before_inject = get_schema_retry()
        ctl_schema = schema_before_inject.get(CTL, {})
        zones_before = (
            ctl_schema.get("zones", {}) if isinstance(ctl_schema, dict) else {}
        )
        print(f"  Zones before inject: {list(zones_before.keys())}")
        print(f"  Inject payload: {inject_payload}")

        # Inject as an RP from CTL to HGI (normal response pattern)
        try:
            result = call_service(
                ctx.token,
                "ramses_extras",
                "device_simulator_inject_message",
                {
                    "source_id": CTL,
                    "dst": HGI,
                    "code": "000C",
                    "payload": inject_payload,
                    "verb": "RP",
                },
            )
            print(f"  Injected 000C packet: {result}")
        except RuntimeError as e:
            print(f"  Inject failed: {e}")

        # Wait for the 000C packet to be received and processed by ramses_rf
        ctx.wait(5, "for 000C packet to be processed by ramses_rf")

        # Trigger sync_topology to process the injected packet
        try:
            call_service(ctx.token, "ramses_cc", "sync_topology")
            print("  sync_topology called")
        except RuntimeError as e:
            print(f"  sync_topology failed: {e}")

        ctx.wait(10, "for sync_learned_topology to process")

        # Trigger a save to persist the synced schema to .storage
        try:
            call_service(ctx.token, "ramses_cc", "force_update")
        except RuntimeError:
            pass
        ctx.wait(5, "for save_client_state")

        # Use cached schema (more reliable than config entry during sync)
        schema_after_inject = get_cached_schema()
        ctl_schema_after = schema_after_inject.get(CTL, {})
        zones_after = (
            ctl_schema_after.get("zones", {})
            if isinstance(ctl_schema_after, dict)
            else {}
        )
        print(f"  Zones after inject: {list(zones_after.keys())}")

        # Check that zone 09 was created by the injected 000C packet.
        # Note: ramses_rf prevents moving a device from one zone to another at
        # runtime ("can't change parent"), so we only check zone creation, not
        # that the TRV was moved into it.
        zone_09 = zones_after.get(target_zone, {})
        ctx.check(
            f"Zone {target_zone} created by inject",
            target_zone in zones_after,
            f"zones={list(zones_after.keys())}",
        )
        if target_zone in zones_after:
            ctx.check(
                f"Zone {target_zone} has radiator_valve class",
                zone_09.get("class") == "radiator_valve"
                if isinstance(zone_09, dict)
                else False,
                f"zone_{target_zone}={json.dumps(zone_09)[:200]}",
            )
