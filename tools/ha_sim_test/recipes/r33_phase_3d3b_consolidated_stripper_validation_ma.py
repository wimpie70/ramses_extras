"""Recipe R33: Phase 3d.3b — consolidated stripper: validation matches gateway."""

from __future__ import annotations

import json
import subprocess

from ..base import Recipe, RecipeContext
from ..const import CTL, DHW, FAN, HGI, REM
from ..helpers import (
    call_service,
    get_current_instance,
    get_entities,
    get_schema_retry,
    is_ramses_cc_loaded,
    load_profile_yaml,
    wait_for,
    wait_for_schema_populated,
    ws_send,
)
from ..profile import MIXED_KL, MIXED_SCHEMA, get_mixed_kl


class R33Phase3d3bConsolidatedStripperValidationMa(Recipe):
    id = "R33"
    seq = 350
    title = "Phase 3d.3b — consolidated stripper: validation matches gateway"

    async def run(self, ctx: RecipeContext) -> None:
        ctx.log_section(
            "Recipe 33: Phase 3d.3b — consolidated stripper validation = gateway"
        )

        # This recipe verifies that strip_traits_for_validation() (config_flow)
        # and _strip_schema_extensions() (gateway feeding) produce the same
        # result, since both now call the shared _strip_and_orchestrate().
        #
        # We load a profile with complex traits that exercise the orchestration:
        #   - _owner at root level (stripped by both paths)
        #   - _disabled on a TRV (stripped, device stays in known_list)
        #   - _alias on a zone (stripped, zone survives)
        #   - A trait-only HVAC entry (e.g. {"_alias": "HRU"}) → moved to
        #     orphans_hvac or dropped
        #   - A device already in remotes[] list (should NOT duplicate in
        #     orphans_hvac — the placed_in_lists bug fix from 3d.3b)
        #
        # If validation and gateway feeding diverge, we'd see either:
        #   - A validation error (config_flow rejects the schema), OR
        #   - A gateway ERROR log (ramses_rf rejects the schema it receives)
        #   - Missing entities (gateway silently drops a device)

        # Build a complex schema that exercises all orchestration paths
        schema_r33 = dict(MIXED_SCHEMA)
        schema_r33["_owner"] = "me"  # root _owner — stripped by both paths

        # CTL with _owner + zone with _alias
        ctl_r33 = dict(schema_r33[CTL])
        ctl_r33["_owner"] = "me"
        zones_r33 = dict(ctl_r33.get("zones", {}))
        z03_r33 = dict(zones_r33.get("03", {}))
        z03_r33["_alias"] = "Bedroom"
        zones_r33["03"] = z03_r33
        ctl_r33["zones"] = zones_r33
        schema_r33[CTL] = ctl_r33

        # FAN with _bound (list) + _class + remotes
        fan_r33 = dict(schema_r33[FAN])
        fan_r33["_bound"] = [REM]
        fan_r33["_class"] = "FAN"
        fan_r33["_commands"] = {"_comment": "test"}
        schema_r33[FAN] = fan_r33

        # REM with _faked + _class + _bound (str) — already in FAN's remotes[]
        # This tests the placed_in_lists check: REM is in FAN's remotes[] AND
        # has a root entry with traits.  The root entry should be dropped (not
        # moved to orphans_hvac — would duplicate).
        schema_r33[REM] = {"_faked": True, "_class": "REM", "_bound": FAN}

        # A trait-only HVAC device (29:999999 with only _alias) — should be
        # moved to orphans_hvac (not dropped, since it's HVAC without a
        # parent list placement).
        trait_only_hvac = "29:999999"
        schema_r33[trait_only_hvac] = {"_alias": "Orphan HUM"}

        # A disabled TRV (04:500001 with _disabled=True) — trait stripped,
        # device stays in known_list, no entity created
        disabled_trv = "04:500001"
        schema_r33[disabled_trv] = {"_disabled": True, "_class": "TRV"}

        # Build the profile
        kl_r33 = get_mixed_kl()
        kl_r33[trait_only_hvac] = {"class": "HUM"}
        kl_r33[disabled_trv] = {"class": "TRV"}
        import yaml as _yaml

        profile_r33 = {
            "known_list": kl_r33,
            "_enforce_known_list": {"enabled": True},
            "_schema": schema_r33,
        }
        yaml_text_r33 = _yaml.dump(
            profile_r33, default_flow_style=False, sort_keys=False
        )

        print("  Loading profile with complex traits (orphan, disabled, _owner)...")
        # Capture log baseline before profile load so we can filter the
        # "Schema passed to ramses_rf" grep to only this recipe's reload.
        # In the full suite, previous recipes' reloads leave stale log
        # lines that cause the grep to pick up the wrong schema.
        import datetime as _dt

        _log_baseline = _dt.datetime.now(_dt.UTC).isoformat()
        try:
            await load_profile_yaml(ctx.token, yaml_text_r33)
            print("  Profile loaded successfully (validation passed)")
            ctx.check(
                "Config_flow validation passes with complex traits",
                True,
                "",
            )
        except RuntimeError as e:
            ctx.check(
                "Config_flow validation passes with complex traits",
                False,
                str(e)[:120],
            )
            return  # can't continue if profile load failed

        ctx.wait_for_ramses_cc_reload(timeout=20)
        ctx.refresh_token()
        # Activate CTL + FAN + REM for heartbeats
        for dev_id, name in [(CTL, "CTL"), (FAN, "FAN"), (REM, "REM")]:
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

        # Check 1: Schema survived the round-trip (gateway accepted it)
        schema_after_r33 = get_schema_retry()
        ctx.check(
            "Schema populated after gateway feeding (no validation error)",
            bool(schema_after_r33) and CTL in schema_after_r33,
            f"schema keys={list(schema_after_r33.keys())[:10]}",
        )

        # The config entry schema keeps _ traits (by design).  The stripping
        # happens at gateway feed time.  We verify the gateway's view by
        # grepping the log for "Schema passed to ramses_rf" — this is the
        # stripped schema that _strip_and_orchestrate() produced.
        # Use --since 120s to filter to only this recipe's reload window,
        # avoiding stale lines from previous recipes in the full suite.
        gw_log = (
            subprocess.run(
                [
                    "docker",
                    "logs",
                    "--since",
                    "120s",
                    get_current_instance().name,
                ],
                capture_output=True,
                text=True,
                timeout=10,
            ).stderr
            or ""
        )
        # Filter to only lines after our baseline timestamp.
        # The log lines have ANSI color codes at the start, so we need to
        # strip them before extracting the timestamp.
        # Log format (after ANSI strip): "2026-08-17 22:19:26.625 DEBUG ..."
        # The container logs are in the container's local timezone, while
        # _log_baseline is in UTC.  We get the container's UTC offset and
        # convert the baseline accordingly.
        import re as _re

        _ansi_re = _re.compile(r"\x1b\[[0-9;]*m")
        # Get container timezone offset (e.g. +0200)
        try:
            tz_out = subprocess.run(
                ["docker", "exec", get_current_instance().name, "date", "+%z"],
                capture_output=True,
                text=True,
                timeout=5,
            ).stdout.strip()
            tz_hours = int(tz_out[:3])  # +02 or -05
            tz_mins = int(tz_out[0] + tz_out[3:5])  # +00 or -30
        except Exception:
            tz_hours, tz_mins = 0, 0
        from datetime import datetime as _dt2
        from datetime import timedelta as _td2

        baseline_utc = _dt2.fromisoformat(_log_baseline)
        baseline_local = baseline_utc + _td2(hours=tz_hours, minutes=tz_mins)
        baseline_str = baseline_local.strftime("%Y-%m-%d %H:%M:%S")
        all_gw_lines = [
            line for line in gw_log.splitlines() if "Schema passed to ramses_rf" in line
        ]
        gw_lines = []
        for line in all_gw_lines:
            # Strip ANSI codes then extract timestamp (first 19 chars)
            clean = _ansi_re.sub("", line)
            ts = clean[:19] if len(clean) >= 19 else ""
            if ts >= baseline_str:
                gw_lines.append(line)
        # Use the first NON-EMPTY schema line after the baseline — the first
        # line after a profile reload is often {} (from the unload phase),
        # and the second line has the actual stripped schema from the reload.
        # Subsequent lines (from sync/force_update) may have a different
        # schema that doesn't include all test devices.
        gw_schema_str = ""
        for line in gw_lines:
            if "{}" not in line.split("Schema passed to ramses_rf: ", 1)[-1]:
                gw_schema_str = line
                break
        if not gw_schema_str and gw_lines:
            gw_schema_str = gw_lines[0]
        ctx.check(
            "Gateway received stripped schema (log captured)",
            bool(gw_schema_str),
            "no 'Schema passed to ramses_rf' line in log",
        )

        # Check 2: _owner was stripped from the schema that reached the gateway
        ctx.check(
            "_owner stripped from gateway schema (consolidated stripper)",
            "_owner" not in gw_schema_str,
            f"_owner={'present' if '_owner' in gw_schema_str else 'absent'}"
            " in gateway schema",
        )

        # Check 3: Zone _alias was stripped but zone survived
        # (zone 03 should be in the gateway schema, but _alias should not)
        z03_in_gw = "'03':" in gw_schema_str or '"03":' in gw_schema_str
        alias_in_gw = "_alias" in gw_schema_str
        ctx.check(
            "Zone 03 survived, _alias stripped (gateway schema)",
            z03_in_gw and not alias_in_gw,
            f"zone_03={z03_in_gw}, _alias={alias_in_gw}",
        )

        # Check 4: REM root entry was dropped (it's in FAN's remotes[] list,
        # so it should NOT appear as a root key in the gateway schema).
        # The placed_in_lists check in _strip_and_orchestrate prevents
        # duplication — the REM is already in FAN's remotes[], so its root
        # entry is dropped (not moved to orphans_hvac).
        # We check for the pattern '37:170000': { (root key) vs '37:170000'
        # inside a list (which is expected — it's in FAN's remotes[]).
        rem_as_root = f"'{REM}':" in gw_schema_str
        ctx.check(
            f"REM {REM} root entry dropped (placed_in_lists check)",
            not rem_as_root,
            f"REM as root key in gateway schema: {rem_as_root}",
        )

        # Check 5: Trait-only HVAC device (29:999999) moved to orphans_hvac
        # (not dropped, not in root with traits — the orchestrator moved it)
        # The gateway schema should contain "orphans_hvac": ['29:999999']
        orphan_in_orphans_gw = (
            trait_only_hvac in gw_schema_str and "orphans_hvac" in gw_schema_str
        )
        ctx.check(
            f"Trait-only HVAC {trait_only_hvac} moved to orphans_hvac",
            orphan_in_orphans_gw,
            f"in orphans_hvac={orphan_in_orphans_gw}",
        )

        # Check 6: FAN entity exists (gateway accepted the schema with
        # _bound as list + _commands)
        entities_r33 = get_entities(ctx.token)
        fan_entity_r33 = None
        for s in entities_r33:
            eid = s.get("entity_id", "")
            if "climate" in eid and "32_150000" in eid:
                fan_entity_r33 = s
                break
        ctx.check(
            "FAN climate entity exists (gateway accepted complex schema)",
            fan_entity_r33 is not None,
            "no climate entity matching FAN",
        )

        # Check 7: CTL entity exists (zone 03 survived with _alias stripped)
        ctl_entity_r33 = None
        for s in entities_r33:
            eid = s.get("entity_id", "")
            if "climate" in eid and "01_150000" in eid and "zone" not in eid:
                ctl_entity_r33 = s
                break
        ctx.check(
            "CTL climate entity exists (zone _alias stripped, zone kept)",
            ctl_entity_r33 is not None,
            "no climate entity matching CTL",
        )

        # Check 8: No ERROR logs about schema validation from ramses_rf
        # (if validation and gateway diverge, ramses_rf would log errors
        # about invalid keys or invalid structure)
        raw_log_r33 = subprocess.run(
            [
                "docker",
                "exec",
                get_current_instance().name,
                "grep",
                r"ERROR.*schema\|ERROR.*validation\|ERROR.*SCH_GLOBAL\|"
                r"ERROR.*PREVENT_EXTRA\|ERROR.*invalid.*key",
                "/config/home-assistant.log",
            ],
            capture_output=True,
            text=True,
        ).stdout
        schema_errors = [
            line
            for line in raw_log_r33.splitlines()
            if "ramses_cc" in line or "ramses_rf" in line
        ]
        ctx.check(
            "No ramses_cc/ramses_rf ERROR logs about schema validation",
            len(schema_errors) == 0,
            f"{len(schema_errors)} schema validation error lines",
        )
