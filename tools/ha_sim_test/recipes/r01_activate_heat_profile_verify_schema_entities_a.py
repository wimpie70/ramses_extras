"""Recipe R01: Activate heat profile → verify schema + entities [A]."""

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


class R01ActivateHeatProfileVerifySchemaEntitiesA(Recipe):
    id = "R01"
    seq = 150
    title = "Activate heat profile → verify schema + entities [A]"

    async def run(self, ctx: RecipeContext) -> None:
        ctx.log_section("Recipe 1: Heat profile activation + schema/entities")

        # Load heat_only profile via load_profile_yaml (no docker restart)
        print("  Loading heat_only profile via load_profile_yaml...")
        heat_kl = {
            HGI: {"class": "HGI"},
            CTL: {"class": "CTL"},
            "04:150000": {"class": "TRV"},
            DHW: {"class": "DHW"},
        }
        heat_schema = {
            CTL: {
                "zones": {"01": {"sensor": CTL, "actuators": ["04:150000"]}},
                "stored_hotwater": {"sensor": DHW},
            },
        }
        import yaml as _yaml_heat

        heat_profile = {
            "known_list": heat_kl,
            "_enforce_known_list": {"enabled": True},
            "_schema": heat_schema,
        }
        heat_yaml_text = _yaml_heat.dump(
            heat_profile, default_flow_style=False, sort_keys=False
        )
        try:
            await load_profile_yaml(ctx.token, heat_yaml_text)
            print("  heat_only profile loaded")
        except RuntimeError as e:
            print(f"  Profile load failed: {str(e)[:80]}")
        ctx.wait(15, "for ramses_cc reload with heat_only")
        ctx.refresh_token()
        ctx.wait(5, "for ramses_cc to initialize")

        # Activate CTL, TRV, DHW
        for dev, slug in [(CTL, "CTL"), ("04:150000", "TRV"), (DHW, "DHW")]:
            try:
                await ws_send(
                    ctx.token,
                    {
                        "type": "ramses_extras/device_simulator/activate_device",
                        "device_id": dev,
                        "slug": slug,
                    },
                )
                print(f"    {slug} {dev} activated")
            except RuntimeError:
                pass  # may already be active
        ctx.wait(10, "for heartbeats + schema population (100x speed)")

        schema_r1 = get_schema_retry()
        kl_r1 = get_known_list()
        entities_r1 = get_entities(ctx.token)
        ctx.check(
            "CTL in schema after heat profile",
            CTL in schema_r1,
            f"schema keys={list(schema_r1.keys())}",
        )
        ctx.check(
            "CTL in known_list after heat profile",
            CTL in kl_r1,
            f"known_list keys={list(kl_r1.keys())[:10]}",
        )
        ctl_entity = find_entity_for_device(entities_r1, CTL, prefix="ctl_")
        ctx.check("CTL entity created", ctl_entity is not None, "no ctl_ entity found")
        trv_entity = find_entity_for_device(entities_r1, "04:150000", prefix="trv_")
        ctx.check(
            "TRV entity created", trv_entity is not None, "no trv_ entity for 04:150000"
        )
        dhw_entity = find_entity_for_device(entities_r1, DHW, prefix="dhw_")
        ctx.check(
            "DHW entity created", dhw_entity is not None, "no dhw_ entity for 07:150000"
        )
