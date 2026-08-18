"""Recipe R31: Phase 3d.6 — _commands override precedence (E2E)."""

from __future__ import annotations

import json
import subprocess
import time
import urllib.request
from datetime import datetime as dt
from datetime import timedelta

from ..base import Recipe, RecipeContext
from ..const import CO2, CTL, DHW, FAN, HGI, REM, TRV
from ..helpers import (
    call_service,
    find_battery_entity,
    find_entity_for_device,
    get_cached_schema,
    get_current_instance,
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
    wait_for_schema_populated,
    wait_for_transport_ready,
    write_ramses_storage,
    ws_send,
)
from ..profile import MIXED_KL, MIXED_SCHEMA, get_mixed_kl, mixed_yaml


class R31Phase3d6CommandsOverridePrecedenceE2e(Recipe):
    id = "R31"
    seq = 330
    title = "Phase 3d.6 — _commands override precedence (E2E)"

    async def run(self, ctx: RecipeContext) -> None:
        ctx.log_section("Recipe 31: Phase 3d.6 — _commands override precedence (E2E)")

        # This recipe verifies that set_fan_mode uses the FAN's _commands
        # (dict template) instead of the native ramses_rf builder.  We inject
        # a custom _commands entry for "low" on the FAN, call set_fan_mode,
        # and verify the custom packet is sent (not the native one).
        #
        # We can't easily intercept the sent packet in ha-sim, but we CAN
        # verify:
        # 1. The climate entity exists and has fan_modes including "low"
        # 2. set_fan_mode("low") succeeds (no error)
        # 3. The FAN's _commands in the schema has the dict template
        # 4. The log shows "Intercepted fan_mode" (the override path)

        print("  Loading profile with FAN _commands dict template for 'low'...")
        schema_r31 = dict(MIXED_SCHEMA)
        fan_r31 = dict(schema_r31[FAN])
        fan_r31["_bound"] = [REM]
        fan_r31["_class"] = "FAN"
        fan_r31["remotes"] = [REM]
        fan_r31["_commands"] = {
            "_comment": "Test override commands",
            "low": {"verb": "W", "code": "22F1", "payload": "000406"},
        }
        schema_r31[FAN] = fan_r31
        schema_r31[REM] = {"_faked": True, "_class": "REM", "_bound": FAN}
        profile_r31 = {
            "known_list": get_mixed_kl(),
            "_enforce_known_list": {"enabled": True},
            "_schema": schema_r31,
        }
        import yaml as _yaml

        yaml_text_r31 = _yaml.dump(
            profile_r31, default_flow_style=False, sort_keys=False
        )
        try:
            await load_profile_yaml(ctx.token, yaml_text_r31)
            print("  Profile loaded with _commands dict template")
        except RuntimeError as e:
            print(f"  Profile load failed: {str(e)[:80]}")
        ctx.wait_for_ramses_cc_reload(timeout=20)
        ctx.refresh_token()
        wait_for_transport_ready(timeout=30)
        # Activate FAN + REM for heartbeats
        for dev_id, name in [(FAN, "FAN"), (REM, "REM"), (CO2, "CO2")]:
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
        wait_for_schema_populated(timeout=15)

        # Trigger sync
        try:
            call_service(ctx.token, "ramses_cc", "sync_topology")
        except RuntimeError as e:
            print(f"  sync_topology failed: {e}")
        ctx.wait_for_schema_stable(timeout=15, msg="for sync_learned_topology")
        try:
            call_service(ctx.token, "ramses_cc", "force_update")
        except RuntimeError:
            pass
        ctx.wait_for_schema_stable(timeout=10, msg="for save_client_state")

        # Check 1: FAN schema has _commands with dict template for "low".
        #    On fresh containers, the config entry update may not have
        #    persisted yet — poll for the _commands key to appear.

        def _commands_persisted() -> bool:
            schema = get_schema_retry()
            fan = schema.get(FAN, {})
            cmds = fan.get("_commands", {})
            return isinstance(cmds.get("low"), dict)

        wait_for(
            _commands_persisted,
            timeout=15,
            interval=3,
            msg="for _commands.low to persist in schema",
            floor=5.0,
        )
        schema_after_r31 = get_schema_retry()
        fan_schema_r31 = schema_after_r31.get(FAN, {})
        fan_commands_r31 = fan_schema_r31.get("_commands", {})
        ctx.check(
            f"FAN {FAN} schema has _commands.low as dict template",
            isinstance(fan_commands_r31.get("low"), dict)
            and fan_commands_r31["low"].get("code") == "22F1"
            and fan_commands_r31["low"].get("payload") == "000406",
            f"_commands.low={fan_commands_r31.get('low')}",
        )

        # Check 2: climate entity exists for FAN
        entities_r31 = get_entities(ctx.token)
        climate_entity = None
        for s in entities_r31:
            eid = s.get("entity_id", "")
            if "climate" in eid and ("32_150000" in eid or "fan_32_150000" in eid):
                climate_entity = s
                break
        climate_eid = climate_entity["entity_id"] if climate_entity else "None"
        print(f"  Climate entity for FAN: {climate_eid}")
        ctx.check(
            "Climate entity exists for FAN",
            climate_entity is not None,
            f"no climate entity matching FAN {FAN}",
        )

        if climate_entity:
            # Check 3: fan_modes includes "low" (from _commands)
            fan_modes = climate_entity.get("attributes", {}).get("fan_modes", [])
            print(f"  fan_modes: {fan_modes}")
            ctx.check(
                "fan_modes includes 'low' (from _commands)",
                "low" in fan_modes,
                f"fan_modes={fan_modes}",
            )

            # Check 4: set_fan_mode("low") succeeds — the override path should
            # build the packet from the dict template and send it.
            # We capture the log before/after to verify "Intercepted fan_mode"
            # appears (the override path logs this).
            import datetime as _dt

            _log_baseline_r31 = _dt.datetime.now(_dt.UTC).isoformat()
            print(f"  Calling climate.set_fan_mode(low) on {climate_eid}...")
            try:
                call_service(
                    ctx.token,
                    "climate",
                    "set_fan_mode",
                    {"entity_id": climate_eid, "fan_mode": "low"},
                )
                print("  set_fan_mode succeeded")
                ctx.check(
                    "set_fan_mode(low) succeeds with _commands override", True, ""
                )
            except RuntimeError as e:
                ctx.check(
                    "set_fan_mode(low) succeeds with _commands override",
                    False,
                    str(e)[:120],
                )

            ctx.wait(3, "for log to flush")

            # Check 5: log shows "Intercepted fan_mode" (override path was taken)
            # Use docker logs --since with the baseline timestamp to search
            # only recent logs (avoids matching stale entries from previous
            # recipes in the full suite).
            baseline_docker_r31 = _dt.datetime.fromisoformat(
                _log_baseline_r31
            ).strftime("%Y-%m-%dT%H:%M:%S")
            raw_log_result = subprocess.run(
                [
                    "docker",
                    "logs",
                    "--since",
                    baseline_docker_r31,
                    get_current_instance().name,
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )
            raw_log_r31 = raw_log_result.stderr or raw_log_result.stdout
            intercepted = "Intercepted fan_mode" in raw_log_r31
            ctx.check(
                "Log shows 'Intercepted fan_mode' (override path taken)",
                intercepted,
                f"{'found' if intercepted else 'NOT found in logs since baseline'}",
            )
