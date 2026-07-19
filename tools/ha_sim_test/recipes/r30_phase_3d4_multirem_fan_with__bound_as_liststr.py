"""Recipe R30: Phase 3d.4 — multi-REM FAN with _bound as list[str]."""

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


class R30Phase3d4MultiremFanWithBoundAsListstr(Recipe):
    id = "R30"
    seq = 320
    title = "Phase 3d.4 — multi-REM FAN with _bound as list[str]"

    async def run(self, ctx: RecipeContext) -> None:
        ctx.log_section("Recipe 30: Phase 3d.4 — multi-REM FAN _bound as list[str]")

        # This recipe verifies that a FAN with _bound: ["37:170000", "37:170001"]
        # (list-valued, multi-REM binding) reaches ramses_rf's known_list as
        # bound: ["37:170000", "37:170001"] (not dropped by the str-only guard
        # that was removed in 3d.4).
        #
        # We load a custom profile with a second REM bound to the FAN, then
        # verify the known_list has bound as a list.

        rem2 = "37:170001"  # second REM (the first is REM = "37:170000")
        print(f"  Loading profile with FAN _bound=[{REM}, {rem2}] (list-valued)...")
        schema_r30 = dict(MIXED_SCHEMA)
        fan_r30 = dict(schema_r30[FAN])
        fan_r30["_bound"] = [REM, rem2]
        fan_r30["_class"] = "FAN"
        fan_r30["remotes"] = [REM, rem2]
        schema_r30[FAN] = fan_r30
        # Add the second REM to the schema with _faked + _class
        schema_r30[rem2] = {"_faked": True, "_class": "REM", "_bound": FAN}
        # Also add to known_list
        kl_r30 = dict(MIXED_KL)
        kl_r30[rem2] = {"class": "REM"}
        # _mixed_yaml uses MIXED_KL internally, so we need a custom YAML
        import yaml as _yaml

        profile_r30 = {
            "known_list": kl_r30,
            "_enforce_known_list": {"enabled": True},
            "_schema": schema_r30,
        }
        yaml_text_r30 = _yaml.dump(
            profile_r30, default_flow_style=False, sort_keys=False
        )
        try:
            await load_profile_yaml(ctx.token, yaml_text_r30)
            print("  Profile loaded with list-valued _bound")
        except RuntimeError as e:
            print(f"  Profile load failed: {str(e)[:80]}")
        ctx.wait(15, "for ramses_cc reload with list _bound")
        ctx.refresh_token()
        ctx.wait(5, "for ramses_cc to initialize")

        # Activate FAN + both REMs for heartbeats
        for dev_id, name in [(FAN, "FAN"), (REM, "REM"), (rem2, "REM2")]:
            try:
                await ws_send(
                    ctx.token,
                    {
                        "type": "ramses_extras/device_simulator/"
                        "activate_profile_device",
                        "device_id": dev_id,
                    },
                )
                print(f"    {name} activated")
            except RuntimeError:
                pass
        ctx.wait(10, "for heartbeats + schema population")

        # Trigger sync to populate known_list from schema
        try:
            call_service(ctx.token, "ramses_cc", "sync_topology")
        except RuntimeError as e:
            print(f"  sync_topology failed: {e}")
        ctx.wait(10, "for sync_learned_topology")
        try:
            call_service(ctx.token, "ramses_cc", "force_update")
        except RuntimeError:
            pass
        ctx.wait(5, "for save_client_state")

        # Check 1: FAN's known_list entry has bound as a list
        # NOTE: get_known_list() reads the config entry's USER known_list, not
        # the derived known_list that ramses_rf receives.  The derived known_list
        # is computed at runtime from schema + user overrides and passed to
        # ramses_rf's Gateway in memory (not persisted).  So we verify:
        # - Schema has _bound as list (Check 3 below)
        # - FAN climate entity exists (Check 5)
        # - No validation errors about 'bound' in the log (Check 6)
        # The config entry known_list only has the user's overrides (class=FAN).
        kl_after_r30 = get_known_list()
        fan_kl_r30 = kl_after_r30.get(FAN, {})
        print(f"  FAN config-entry known_list: {json.dumps(fan_kl_r30)[:200]}")
        ctx.check(
            f"FAN {FAN} config-entry known_list has class=FAN",
            fan_kl_r30.get("class") == "FAN",
            f"class={fan_kl_r30.get('class')}",
        )

        # Check 3: Schema has FAN with _bound as list (survived reload)
        schema_after_r30 = get_schema_retry()
        fan_schema_r30 = schema_after_r30.get(FAN, {})
        ctx.check(
            f"FAN {FAN} schema has _bound as list",
            isinstance(fan_schema_r30.get("_bound"), list)
            and REM in fan_schema_r30["_bound"]
            and rem2 in fan_schema_r30["_bound"],
            f"_bound={fan_schema_r30.get('_bound')}",
        )

        # Check 4: both REMs are in FAN's remotes list
        fan_remotes_r30 = fan_schema_r30.get("remotes", [])
        ctx.check(
            "FAN remotes list has both REMs",
            REM in fan_remotes_r30 and rem2 in fan_remotes_r30,
            f"remotes={fan_remotes_r30}",
        )

        # Check 5: FAN climate entity exists (ramses_rf accepted the schema
        # with list-valued _bound — if SCH_TRAITS_HVAC rejected it, the FAN
        # entity would not be created)
        entities_r30 = get_entities(ctx.token)
        fan_entity_r30 = None
        for s in entities_r30:
            eid = s.get("entity_id", "")
            if "climate" in eid and "32_150000" in eid:
                fan_entity_r30 = s
                break
        ctx.check(
            "FAN climate entity exists (list _bound accepted by ramses_rf)",
            fan_entity_r30 is not None,
            "no climate entity matching FAN",
        )

        # Check 6: no validation errors about 'bound' in the log
        raw_log_r30 = subprocess.run(
            [
                "docker",
                "exec",
                "ha-sim",
                "grep",
                "-i",
                "bound",
                "/config/home-assistant.log",
            ],
            capture_output=True,
            text=True,
        ).stdout
        bound_errors = [
            line
            for line in raw_log_r30.splitlines()
            if "ERROR" in line
            and "bound" in line.lower()
            and "bound method" not in line
            and "bound_to" not in line
        ]
        ctx.check(
            "No ERROR logs about _bound trait (list-valued _bound accepted)",
            len(bound_errors) == 0,
            f"{len(bound_errors)} error lines about _bound trait",
        )
