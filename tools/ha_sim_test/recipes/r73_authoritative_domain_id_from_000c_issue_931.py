"""Recipe R73: Authoritative domain_id from 000C — FA/F9/FC placement (issue 931)."""

from __future__ import annotations

import json

import yaml as _yaml

from ..base import Recipe, RecipeContext
from ..const import CTL, DHW
from ..helpers import (
    call_service,
    clear_cached_state,
    get_current_instance,
    get_schema_retry,
    load_profile_yaml,
    wait_for,
    wait_for_schema_populated,
    ws_send,
)
from ..profile import MIXED_SCHEMA, get_mixed_kl


class R73AuthoritativeDomainIdFrom000CIssue931(Recipe):
    id = "R73"
    seq = 730
    title = "Authoritative domain_id from 000C — FA/F9/FC placement (issue 931)"

    async def run(self, ctx: RecipeContext) -> None:
        # Issue 931: the scan engine now tracks authoritative domain_id
        # (FC/FA/F9) from 000C binding tables, and sync_learned_topology
        # uses this to place BDR relays instead of the old "1100" heuristic.
        #
        # This recipe tests all three domain placements:
        #   1. 000C with role 0E, index 00 → FA → hotwater_valve
        #   2. 000C with role 0E, index 01 → F9 → heating_valve
        #   3. 000C with role 0F → FC → appliance_control
        #
        # Three BDRs are discovered via 3B00/3EF0 broadcasts (which gives
        # all of them a non-authoritative FC hint).  They are accepted and
        # end up in orphans_heat.  Then 000C bindings are injected to
        # assign authoritative domains.  sync_learned_topology step 2b
        # places them from orphans_heat based on the authoritative domain.
        ctx.log_section("Recipe 73: Authoritative domain_id from 000C (issue 931)")

        # Device IDs — serial numbers < 262144 (18-bit max)
        bdr_fa = "13:093101"  # → hotwater_valve (FA)
        bdr_f9 = "13:093102"  # → heating_valve (F9)
        bdr_fc = "13:093103"  # → appliance_control (FC)
        # hex_id = (device_type << 18) + serial
        # 13:093101 → (13 << 18) + 93101 = 3500973 = 0x356BAD
        hex_fa = "356BAD"
        # 13:093102 → (13 << 18) + 93102 = 3500974 = 0x356BAE
        hex_f9 = "356BAE"
        # 13:093103 → (13 << 18) + 93103 = 3500975 = 0x356BAF
        hex_fc = "356BAF"

        # --- Clear cached state ---
        print("  Stopping ha-sim and clearing cached state...")
        clear_cached_state(ctx.log_monitor, label="R73 pre-restart")
        ctx.wait_for_ha_ready(timeout=30)
        ctx.log_monitor.reset_baseline()
        ctx.refresh_token()
        ctx.wait_for_ramses_cc_loaded(timeout=30)

        # --- Build a custom profile with CTL + DHW sensor (no BDRs) ---
        # BDRs will be discovered via 3B00/3EF0 broadcasts, then accepted.
        schema_r73 = dict(MIXED_SCHEMA)
        ctl_schema = dict(schema_r73.get(CTL, {}))
        # Clear system and stored_hotwater to start fresh
        ctl_schema["system"] = {}
        ctl_schema["stored_hotwater"] = {"sensor": DHW}
        schema_r73[CTL] = ctl_schema

        kl_r73 = get_mixed_kl()

        profile_r73 = {
            "known_list": kl_r73,
            "_enforce_known_list": {"enabled": True},
            "_schema": schema_r73,
        }
        yaml_text = _yaml.dump(profile_r73, default_flow_style=False, sort_keys=False)

        print("  Loading profile (CTL + DHW, no BDRs)...")
        try:
            await load_profile_yaml(ctx.token, yaml_text, speed=0.01)
            print("  Profile loaded")
        except RuntimeError as e:
            print(f"  Profile load failed: {e}")
        ctx.wait_for_ramses_cc_reload(timeout=30)
        ctx.refresh_token()

        # Activate CTL for heartbeats
        try:
            await ws_send(
                ctx.token,
                {
                    "type": "ramses_extras/device_simulator/activate_profile_device",
                    "device_id": CTL,
                },
            )
        except RuntimeError:
            pass
        wait_for_schema_populated(timeout=20)

        # --- Inject 3B00/3EF0 from all 3 BDRs (discover them) ---
        # No dst parameter — defaults to broadcast (--:------), like R29.
        for bdr_id in (bdr_fa, bdr_f9, bdr_fc):
            for code in ("3B00", "3EF0"):
                try:
                    call_service(
                        ctx.token,
                        "ramses_extras",
                        "device_simulator_inject_message",
                        {
                            "source_id": bdr_id,
                            "code": code,
                            "payload": "00C8",
                            "verb": "I",
                        },
                    )
                    print(f"    {code} I injected from {bdr_id}")
                except RuntimeError:
                    pass

        # Wait for scan engine to process
        ctx.wait(5, "for scan engine to process 3B00/3EF0")

        # Accept all 3 BDRs
        for bdr_id in (bdr_fa, bdr_f9, bdr_fc):
            try:
                call_service(
                    ctx.token,
                    "ramses_cc",
                    "accept_discovered_device",
                    {"device_id": bdr_id},
                )
                print(f"    {bdr_id} accepted")
            except RuntimeError:
                pass

        # Wait for include list update
        wait_for(
            lambda: all(bdr in get_schema_retry() for bdr in (bdr_fa, bdr_f9, bdr_fc)),
            timeout=15,
            interval=2,
            msg="for all BDRs to appear in schema",
        )

        # Trigger sync to process the 3B00/3EF0 hints
        try:
            call_service(ctx.token, "ramses_cc", "sync_topology")
        except RuntimeError:
            pass

        # Wait for sync to complete
        wait_for(
            lambda: _schema_stable(get_schema_retry()),
            timeout=15,
            interval=2,
            msg="for schema to stabilise after 3B00/3EF0",
        )

        # Verify BDRs are in orphans_heat (not yet placed by 000C)
        schema_pre = get_schema_retry()
        orphans_pre = schema_pre.get("orphans_heat", [])
        print(f"  BDRs in orphans_heat before 000C: {orphans_pre}")

        # --- Inject 000C bindings for all 3 domains ---
        # FA: 000C with role 0E, index 00 → hotwater_valve
        fa_payload = f"000E00{hex_fa}"
        # F9: 000C with role 0E, index 01 → heating_valve
        f9_payload = f"010E00{hex_f9}"
        # FC: 000C with role 0F → appliance_control
        fc_payload = f"000F00{hex_fc}"

        for label, payload, bdr_id in (
            ("FA/hotwater_valve", fa_payload, bdr_fa),
            ("F9/heating_valve", f9_payload, bdr_f9),
            ("FC/appliance_control", fc_payload, bdr_fc),
        ):
            print(f"  Injecting 000C RP ({label}) from CTL for {bdr_id}...")
            print(f"    payload: {payload}")
            try:
                call_service(
                    ctx.token,
                    "ramses_extras",
                    "device_simulator_inject_message",
                    {
                        "source_id": CTL,
                        "dst": get_current_instance().hgi_id,
                        "code": "000C",
                        "payload": payload,
                        "verb": "RP",
                    },
                )
                print(f"    000C RP ({label}) injected")
            except RuntimeError as e:
                print(f"    Inject failed: {str(e)[:80]}")

        # Poll until all 3 BDRs are placed by their authoritative domain
        _retry_count = 0

        def _all_placed() -> bool:
            nonlocal _retry_count
            schema = get_schema_retry()
            ctl = schema.get(CTL, {})
            if not isinstance(ctl, dict):
                return False
            system = ctl.get("system", {})
            dhw = ctl.get("stored_hotwater", {})
            fa_ok = dhw.get("hotwater_valve") == bdr_fa
            f9_ok = dhw.get("heating_valve") == bdr_f9
            fc_ok = system.get("appliance_control") == bdr_fc
            if fa_ok and f9_ok and fc_ok:
                return True
            _retry_count += 1
            if _retry_count % 2 == 0:
                # Re-inject 000C bindings
                for payload in (fa_payload, f9_payload, fc_payload):
                    try:
                        call_service(
                            ctx.token,
                            "ramses_extras",
                            "device_simulator_inject_message",
                            {
                                "source_id": CTL,
                                "dst": get_current_instance().hgi_id,
                                "code": "000C",
                                "payload": payload,
                                "verb": "RP",
                            },
                        )
                    except RuntimeError:
                        pass
            try:
                call_service(ctx.token, "ramses_cc", "sync_topology")
            except RuntimeError:
                pass
            return False

        wait_for(
            _all_placed,
            timeout=60,
            interval=3,
            msg="for 000C to place all 3 BDRs by domain",
            floor=15.0,
        )

        schema_final = get_schema_retry()
        ctl_final = schema_final.get(CTL, {})
        system_final = (
            ctl_final.get("system", {}) if isinstance(ctl_final, dict) else {}
        )
        dhw_final = (
            ctl_final.get("stored_hotwater", {}) if isinstance(ctl_final, dict) else {}
        )
        orphans_heat = schema_final.get("orphans_heat", [])

        print("  Final schema:")
        print(f"    system = {json.dumps(system_final)[:120]}")
        print(f"    stored_hotwater = {json.dumps(dhw_final)[:120]}")
        print(f"    orphans_heat = {orphans_heat}")

        # Check 1: FA BDR → hotwater_valve
        ctx.check(
            f"BDR {bdr_fa} is hotwater_valve (domain FA from 000C)",
            dhw_final.get("hotwater_valve") == bdr_fa,
            f"hotwater_valve={dhw_final.get('hotwater_valve')}",
        )

        # Check 2: F9 BDR → heating_valve
        ctx.check(
            f"BDR {bdr_f9} is heating_valve (domain F9 from 000C)",
            dhw_final.get("heating_valve") == bdr_f9,
            f"heating_valve={dhw_final.get('heating_valve')}",
        )

        # Check 3: FC BDR → appliance_control
        ctx.check(
            f"BDR {bdr_fc} is appliance_control (domain FC from 000C)",
            system_final.get("appliance_control") == bdr_fc,
            f"appliance_control={system_final.get('appliance_control')}",
        )

        # Check 4: FA BDR is NOT appliance_control (no misclassification)
        ctx.check(
            f"BDR {bdr_fa} (FA) is NOT appliance_control",
            system_final.get("appliance_control") != bdr_fa,
            f"appliance_control={system_final.get('appliance_control')}",
        )

        # Check 5: FC BDR is NOT hotwater_valve (no misclassification)
        ctx.check(
            f"BDR {bdr_fc} (FC) is NOT hotwater_valve",
            dhw_final.get("hotwater_valve") != bdr_fc,
            f"hotwater_valve={dhw_final.get('hotwater_valve')}",
        )

        # Check 6: CTL comment shows authoritative domain from 000C.
        # The 000C RP is sent from the CTL, so the scan engine sets
        # domain_id on the CTL (not on the BDR in the payload).  The
        # comment staleness fix (issue 931) rebuilds the CTL's comment
        # with authoritative phrasing when is_authoritative_domain=True.
        # Note: the last 000C injected determines the CTL's domain_id
        # (FC in this case, since the FC binding is injected last).
        comments = schema_final.get("device_comments", {})
        ctl_comment = comments.get(CTL, "")
        ctx.check(
            "CTL comment shows authoritative domain from 000C "
            "(issue 931 comment staleness fix — no 'hint' phrasing)",
            "domain F" in ctl_comment  # FA, F9, or FC
            and "hint" not in ctl_comment.lower(),
            f"comment={ctl_comment[:120]}",
        )


def _schema_stable(schema: dict, min_keys: int = 5) -> bool:
    """Quick check that schema has enough keys."""
    return len(schema) >= min_keys
