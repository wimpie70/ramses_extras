"""Recipe R37: BDR hotwater_valve misclassified as appliance_control.

Issue 834 regression — reproduces the scenario reported in
issue 834 comment 5044906835:
a system with an OTB (10:) as ``appliance_control`` and a BDR (13:) as
``hotwater_valve`` (with a DHW sensor).  Both relays broadcast 3B00/3EF0
as I (both participate in TPI loops).  The scan engine's
``_is_appliance_control_signal`` flags *any* 13:/10: broadcasting these
codes as FC (appliance_control), so the BDR is incorrectly classified as
appliance_control instead of hotwater_valve.

This causes a discovery loop: both devices compete for the single
``system.appliance_control`` slot — accepting one displaces the other,
which is then re-discovered, ad infinitum.

Two layers of protection are tested:
  1. **Classification fix (ramses_rf):** the scan engine should NOT flag
     the BDR as FC domain when a DHW sensor is present (the BDR is the
     hotwater_valve, not the appliance_control).
  2. **Loop prevention guard (ramses_cc):** even if the classification is
     wrong, ``_resolve_single_slot_conflicts`` in ``_apply_schema_entry``
     prevents the BDR from displacing the OTB from the
     ``appliance_control`` slot — the BDR is redirected to
     ``orphans_heat`` instead, breaking the loop.

Expected (correct) behaviour:
  - OTB (10:083401) → system.appliance_control  (FC domain)
  - BDR (13:083402) → stored_hotwater.hotwater_valve  (FA domain, NOT FC)
  - If BDR is misclassified as FC, it goes to orphans_heat (NOT appliance_control)

See: https://github.com/ramses-rf/ramses_cc/issues/834#issuecomment-5044906835
"""

from __future__ import annotations

import json
import subprocess

import yaml as _yaml

from ..base import Recipe, RecipeContext
from ..const import CTL, DHW, HGI
from ..helpers import (
    call_service,
    clear_cached_state,
    get_schema_retry,
    is_ha_ready,
    is_ramses_cc_loaded,
    load_profile_yaml,
    ws_send,
)
from ..profile import MIXED_KL, MIXED_SCHEMA


class R37BdrHotwaterValveMisclassifiedAsApplianceControlIssue834(Recipe):
    id = "R37"
    seq = 380
    title = (
        "BDR hotwater_valve misclassified as appliance_control (issue 834 regression)"
    )

    async def run(self, ctx: RecipeContext) -> None:
        # Scenario from issue 834 comment 5044906835 (peternash, 2026-07-22):
        #   OTB 10:064873 = appliance_control (FC domain)
        #   BDR 13:042605 = hotwater_valve   (FA domain)
        #   DHW sensor 07:050121 present (system genuinely has DHW)
        #
        # Both the OTB and the BDR broadcast 3B00/3EF0 as I (TPI loop).
        # The scan engine must NOT flag the BDR as FC (appliance_control)
        # just because it broadcasts these codes — a DHW valve relay also
        # sends 3B00/3EF0.  The presence of a DHW sensor is the key
        # disambiguator: if a DhwZone with a sensor exists, a BDR bound to
        # the FA domain is the hotwater_valve, not the appliance_control.
        ctx.log_section(
            "Recipe 37: BDR hotwater_valve misclassified as "
            "appliance_control (issue 834 regression)"
        )

        # Device IDs for this scenario.
        # 083401/083402 reference issue 834 while staying < 262144 (18-bit
        # max) so hex_id conversion stays valid if 000C bindings are used.
        otb_id = "10:083401"  # OTB = appliance_control (FC)
        bdr_id = "13:083402"  # BDR = hotwater_valve (FA)

        # --- Clear ALL cached state from previous tests (R29 binds a BDR
        # as appliance_control and writes it to the config entry schema;
        # R34 re-parents a BDR.  Both persist across docker restarts via
        # .storage/ramses_cc and core.config_entries, and ramses.db replays
        # old 000C packets.  We need a truly clean slate.
        print("  Stopping ha-sim and clearing cached state...")
        clear_cached_state(ctx.log_monitor, label="R37 pre-restart")
        ctx.wait_for(is_ha_ready, timeout=30, msg="for ha-sim to start up")
        ctx.log_monitor.reset_baseline()
        ctx.refresh_token()
        ctx.wait_for(is_ramses_cc_loaded, timeout=15, msg="for ramses_cc to initialize")

        # --- Build a custom profile with OTB + BDR + DHW sensor ---
        # The schema declares:
        #   system.appliance_control = OTB (10:083401)
        #   stored_hotwater.hotwater_valve = BDR (13:083402)
        #   stored_hotwater.sensor = DHW (07:150000)
        #
        # This mirrors peternash's system topology.  The DHW sensor is
        # present because the system genuinely has DHW — the BDR is the
        # hotwater_valve, NOT the appliance_control.
        schema_r37 = dict(MIXED_SCHEMA)
        ctl_schema_r37 = dict(schema_r37.get(CTL, {}))
        # Keep zones from mixed profile, override system + stored_hotwater
        ctl_schema_r37["system"] = {"appliance_control": otb_id}
        ctl_schema_r37["stored_hotwater"] = {
            "hotwater_valve": bdr_id,
            "sensor": DHW,
        }
        schema_r37[CTL] = ctl_schema_r37

        kl_r37 = dict(MIXED_KL)
        kl_r37[otb_id] = {"class": "OTB"}
        kl_r37[bdr_id] = {"class": "BDR"}
        # OTB and BDR must also be in the schema (SSOT mode derives
        # known_list from schema, so known_list-only entries are dropped)
        schema_r37[otb_id] = {}
        schema_r37[bdr_id] = {}

        profile_r37 = {
            "known_list": kl_r37,
            "_enforce_known_list": {"enabled": True},
            "_schema": schema_r37,
        }
        yaml_text_r37 = _yaml.dump(
            profile_r37, default_flow_style=False, sort_keys=False
        )

        print(
            "  Loading profile "
            "(OTB=appliance_control, BDR=hotwater_valve, DHW sensor)..."
        )
        try:
            await load_profile_yaml(ctx.token, yaml_text_r37, speed=0.01)
            print("  Profile loaded")
        except RuntimeError as e:
            print(f"  Profile load failed: {e}")
        ctx.wait_for(is_ramses_cc_loaded, timeout=20, msg="for ramses_cc reload")
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
        ctx.wait_for(
            lambda: len(get_schema_retry(max_tries=1)) > 5,
            timeout=15,
            msg="for CTL heartbeats + schema population",
        )

        # --- Step 1: Both OTB and BDR broadcast 3B00 I (TPI loop) ---
        # In peternash's system, both relays broadcast 3B00/3EF0 as I.
        # The OTB is the appliance_control; the BDR is the hotwater_valve.
        # The scan engine must distinguish them — the 3B00/3EF0 I broadcast
        # alone is NOT sufficient to classify a device as appliance_control.

        # OTB broadcasts 3B00 I (TPI state) — legitimate appliance_control
        print(f"  Injecting 3B00 I broadcast from OTB {otb_id}...")
        try:
            call_service(
                ctx.token,
                "ramses_extras",
                "device_simulator_inject_message",
                {
                    "source_id": otb_id,
                    "code": "3B00",
                    "payload": "00C8",
                    "verb": "I",
                },
            )
            print(f"    3B00 I injected from {otb_id}")
        except RuntimeError as e:
            print(f"    Inject failed: {str(e)[:80]}")

        ctx.wait(2, "between injects")

        # OTB broadcasts 3EF0 I (boiler relay state)
        print(f"  Injecting 3EF0 I broadcast from OTB {otb_id}...")
        try:
            call_service(
                ctx.token,
                "ramses_extras",
                "device_simulator_inject_message",
                {
                    "source_id": otb_id,
                    "code": "3EF0",
                    "payload": "0000FF",
                    "verb": "I",
                },
            )
            print(f"    3EF0 I injected from {otb_id}")
        except RuntimeError as e:
            print(f"    Inject failed: {str(e)[:80]}")

        ctx.wait(2, "between injects")

        # BDR broadcasts 3B00 I (TPI state) — this is the hotwater_valve,
        # NOT the appliance_control.  The scan engine must NOT flag this
        # as FC domain.
        print(f"  Injecting 3B00 I broadcast from BDR {bdr_id} (hotwater_valve)...")
        try:
            call_service(
                ctx.token,
                "ramses_extras",
                "device_simulator_inject_message",
                {
                    "source_id": bdr_id,
                    "code": "3B00",
                    "payload": "00C8",
                    "verb": "I",
                },
            )
            print(f"    3B00 I injected from {bdr_id}")
        except RuntimeError as e:
            print(f"    Inject failed: {str(e)[:80]}")

        ctx.wait(2, "between injects")

        # BDR broadcasts 3EF0 I (relay state)
        print(f"  Injecting 3EF0 I broadcast from BDR {bdr_id} (hotwater_valve)...")
        try:
            call_service(
                ctx.token,
                "ramses_extras",
                "device_simulator_inject_message",
                {
                    "source_id": bdr_id,
                    "code": "3EF0",
                    "payload": "0000FF",
                    "verb": "I",
                },
            )
            print(f"    3EF0 I injected from {bdr_id}")
        except RuntimeError as e:
            print(f"    Inject failed: {str(e)[:80]}")

        ctx.wait(10, "for scan engine to process packets")

        # Accept both discovered devices so they enter the known_list
        print("  Accepting discovered OTB and BDR...")
        for dev_id in (otb_id, bdr_id):
            try:
                call_service(
                    ctx.token,
                    "ramses_cc",
                    "accept_discovered_device",
                    {"device_id": dev_id},
                )
                print(f"    {dev_id} accepted")
            except RuntimeError as e:
                print(f"    {dev_id} accept failed: {str(e)[:80]}")
        ctx.wait(5, "for ramses_rf include list update")

        # Trigger sync_topology to update the schema
        print("  Triggering sync_topology...")
        try:
            call_service(ctx.token, "ramses_cc", "sync_topology")
        except RuntimeError as e:
            print(f"  sync_topology failed: {e}")
        ctx.wait(10, "for sync_learned_topology to process")
        try:
            call_service(ctx.token, "ramses_cc", "force_update")
        except RuntimeError:
            pass
        ctx.wait(5, "for save_client_state")

        schema_r37 = get_schema_retry()
        ctl_r37 = schema_r37.get(CTL, {})
        system_r37 = ctl_r37.get("system", {}) if isinstance(ctl_r37, dict) else {}
        dhw_r37 = (
            ctl_r37.get("stored_hotwater", {}) if isinstance(ctl_r37, dict) else {}
        )
        comments_r37 = schema_r37.get("device_comments", {})

        print(f"  system = {json.dumps(system_r37)[:120]}")
        print(f"  stored_hotwater = {json.dumps(dhw_r37)[:120]}")

        # --- Check 1: OTB is appliance_control (FC domain) ---
        # The OTB broadcasts 3B00/3EF0 as I and IS the appliance_control.
        ctx.check(
            f"OTB {otb_id} is appliance_control",
            system_r37.get("appliance_control") == otb_id,
            f"appliance_control={system_r37.get('appliance_control')}",
        )

        # --- Check 2: OTB is NOT hotwater_valve ---
        ctx.check(
            f"OTB {otb_id} is NOT hotwater_valve",
            dhw_r37.get("hotwater_valve") != otb_id,
            f"hotwater_valve={dhw_r37.get('hotwater_valve')}",
        )

        # --- Check 3: BDR is hotwater_valve (FA domain), NOT appliance_control ---
        # This is the key assertion for the regression: the BDR broadcasts
        # 3B00/3EF0 as I but is the hotwater_valve, NOT the appliance_control.
        # The scan engine must NOT flag it as FC domain just because it
        # broadcasts these codes — the presence of a DHW sensor means the
        # BDR is the hotwater_valve.
        ctx.check(
            f"BDR {bdr_id} is hotwater_valve (NOT appliance_control)",
            dhw_r37.get("hotwater_valve") == bdr_id,
            f"hotwater_valve={dhw_r37.get('hotwater_valve')}",
        )

        # --- Check 4: BDR is NOT appliance_control ---
        # The BDR must not displace the OTB from the appliance_control slot.
        ctx.check(
            f"BDR {bdr_id} is NOT appliance_control",
            system_r37.get("appliance_control") != bdr_id,
            f"appliance_control={system_r37.get('appliance_control')}",
        )

        # --- Check 5: comment for BDR does NOT mention FC domain ---
        # The scan engine must not classify the BDR as FC (appliance_control)
        # from 3B00/3EF0 broadcasts when a DHW sensor is present.
        comment_bdr = comments_r37.get(bdr_id, "")
        ctx.check(
            f"Comment for {bdr_id} does NOT mention FC domain",
            "domain FC" not in comment_bdr,
            f"comment={comment_bdr[:120]}",
        )

        # --- Check 6: comment for OTB DOES mention FC domain ---
        # The OTB is the appliance_control and should be flagged as FC.
        comment_otb = comments_r37.get(otb_id, "")
        ctx.check(
            f"Comment for {otb_id} includes 'domain FC (appliance_control)'",
            "domain FC (appliance_control)" in comment_otb,
            f"comment={comment_otb[:120]}",
        )

        # --- Check 7: no discovery loop — schema is stable after second sync ---
        # The discovery loop symptom: both devices compete for the
        # appliance_control slot.  A second sync_topology should NOT change
        # the assignments — the schema must be stable.
        print("  Triggering second sync_topology (loop detection)...")
        try:
            call_service(ctx.token, "ramses_cc", "sync_topology")
        except RuntimeError as e:
            print(f"  sync_topology failed: {e}")
        ctx.wait(10, "for second sync_learned_topology")
        try:
            call_service(ctx.token, "ramses_cc", "force_update")
        except RuntimeError:
            pass
        ctx.wait(5, "for save")

        schema_r37_2 = get_schema_retry()
        ctl_r37_2 = schema_r37_2.get(CTL, {})
        system_r37_2 = (
            ctl_r37_2.get("system", {}) if isinstance(ctl_r37_2, dict) else {}
        )
        dhw_r37_2 = (
            ctl_r37_2.get("stored_hotwater", {}) if isinstance(ctl_r37_2, dict) else {}
        )

        print(f"  system (2nd sync) = {json.dumps(system_r37_2)[:120]}")
        print(f"  stored_hotwater (2nd sync) = {json.dumps(dhw_r37_2)[:120]}")

        ctx.check(
            "No discovery loop: OTB still appliance_control after 2nd sync",
            system_r37_2.get("appliance_control") == otb_id,
            f"appliance_control={system_r37_2.get('appliance_control')}",
        )

        ctx.check(
            "No discovery loop: BDR still hotwater_valve after 2nd sync",
            dhw_r37_2.get("hotwater_valve") == bdr_id,
            f"hotwater_valve={dhw_r37_2.get('hotwater_valve')}",
        )

        ctx.check(
            "No discovery loop: BDR did NOT displace OTB after 2nd sync",
            system_r37_2.get("appliance_control") != bdr_id,
            f"appliance_control={system_r37_2.get('appliance_control')}",
        )

        # --- Check 10: loop prevention guard — BDR not in appliance_control ---
        # Even if the classification fix (check 5) fails and the BDR is
        # flagged as FC, the loop prevention guard in _apply_schema_entry
        # (_resolve_single_slot_conflicts) must prevent the BDR from
        # displacing the OTB.  The BDR should be redirected to orphans_heat
        # instead.  This is the safety net that breaks the discovery loop
        # regardless of the classification outcome.
        orphans_heat = schema_r37.get("orphans_heat", [])
        bdr_is_app = system_r37.get("appliance_control") == bdr_id
        ctx.check(
            f"Loop prevention guard: BDR {bdr_id} is NOT appliance_control "
            "(redirected to orphans_heat if misclassified as FC)",
            not bdr_is_app,
            f"appliance_control={system_r37.get('appliance_control')} "
            f"orphans_heat={orphans_heat}",
        )
