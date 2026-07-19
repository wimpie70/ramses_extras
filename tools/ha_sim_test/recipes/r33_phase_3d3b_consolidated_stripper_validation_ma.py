"""Recipe R33: Phase 3d.3b — consolidated stripper: validation matches gateway."""

from __future__ import annotations

import json
import subprocess

from ..base import Recipe, RecipeContext
from ..const import CTL, DHW, FAN, HGI, REM
from ..helpers import (
    call_service,
    get_entities,
    get_schema_retry,
    load_profile_yaml,
    ws_send,
)
from ..profile import MIXED_KL, MIXED_SCHEMA


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
        kl_r33 = dict(MIXED_KL)
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

        ctx.wait(15, "for ramses_cc reload with complex traits")
        ctx.refresh_token()
        ctx.wait(5, "for ramses_cc to initialize")

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
        ctx.wait(10, "for heartbeats + schema population")

        # Trigger sync
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

        # Check 1: Schema survived the round-trip (gateway accepted it)
        schema_after_r33 = get_schema_retry()
        ctx.check(
            "Schema populated after gateway feeding (no validation error)",
            bool(schema_after_r33) and CTL in schema_after_r33,
            f"schema keys={list(schema_after_r33.keys())[:10]}",
        )

        # Check 2: _owner was stripped from the schema that reached the gateway
        # (both validation and gateway paths strip _ keys)
        ctx.check(
            "_owner stripped from schema (consolidated stripper)",
            "_owner" not in schema_after_r33,
            f"_owner={'present' if '_owner' in schema_after_r33 else 'absent'}",
        )

        # Check 3: Zone _alias was stripped but zone survived
        ctl_after_r33 = schema_after_r33.get(CTL, {})
        zones_after_r33 = (
            ctl_after_r33.get("zones", {}) if isinstance(ctl_after_r33, dict) else {}
        )
        z03_after_r33 = zones_after_r33.get("03", {})
        ctx.check(
            "Zone 03 survived (trait stripped, zone kept)",
            "03" in zones_after_r33 and "_alias" not in z03_after_r33,
            f"zone_03={json.dumps(z03_after_r33)[:100]}",
        )

        # Check 4: REM root entry was dropped (it's in FAN's remotes[] list,
        # so it should NOT appear as a root entry or in orphans_hvac)
        rem_in_root = REM in schema_after_r33
        orphans = schema_after_r33.get("orphans_hvac", [])
        rem_in_orphans = REM in orphans
        ctx.check(
            f"REM {REM} not duplicated (root dropped, not in orphans)",
            not rem_in_root and not rem_in_orphans,
            f"root={rem_in_root}, orphans={rem_in_orphans}",
        )

        # Check 5: Trait-only HVAC device (29:999999) moved to orphans_hvac
        # (not dropped, not in root with traits)
        orphan_in_root = trait_only_hvac in schema_after_r33
        orphan_in_orphans = trait_only_hvac in orphans
        ctx.check(
            f"Trait-only HVAC {trait_only_hvac} moved to orphans_hvac",
            orphan_in_orphans and not orphan_in_root,
            f"root={orphan_in_root}, orphans={orphan_in_orphans}",
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
                "ha-sim",
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
