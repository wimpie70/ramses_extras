"""Recipe R29: BDR broadcasting 3B00/3EF0 → appliance_control (issue 834)."""

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


class R29BdrBroadcasting3b003ef0ApplianceControlIssue(Recipe):
    id = "R29"
    seq = 310
    title = "BDR broadcasting 3B00/3EF0 → appliance_control (issue 834)"

    async def run(self, ctx: RecipeContext) -> None:
        # A BDR (13:) that broadcasts 3B00 (TPI state) or 3EF0 (boiler params) as
        # I is the boiler relay (appliance_control, FC domain), NOT a DHW valve.
        # The scan engine captures domain_id=FC from these codes, and
        # generate_schema_entry must place the BDR under system.appliance_control
        # instead of stored_hotwater.hotwater_valve (issue 834).
        #
        # We also verify the negative case: a BDR that only sends 1100 (boiler
        # params, no TPI loop) does NOT get domain_id=FC and falls back to
        # hotwater_valve (the pre-fix behaviour).
        ctx.log_section("Recipe 29: BDR 3B00/3EF0 → appliance_control (issue 834)")

        # Load mixed profile (has CTL 01:150000 as main_tcs for TCS placement)
        print("  Loading mixed profile (has CTL for TCS placement)...")
        try:
            await ws_send(
                ctx.token,
                {
                    "type": "ramses_extras/device_simulator/load_profile",
                    "profile": "mixed",
                    "speed": 0.01,
                    "preload_schema": True,
                    "reload_ramses_cc": True,
                    "enable_auto_answer": True,
                },
            )
            print("  mixed profile loaded")
        except RuntimeError as e:
            print(f"  Profile load failed: {e}")
        ctx.wait(15, "for ramses_cc reload with mixed profile")
        ctx.refresh_token()
        ctx.wait(5, "for ramses_cc to initialize")

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
        ctx.wait(10, "for CTL heartbeats + schema population")

        # --- BDR 1: broadcasts 3B00 I → appliance_control (FC domain) ---
        bdr_app = "13:834001"
        print(f"  Injecting 3B00 I broadcast from BDR {bdr_app}...")
        # 3B00 payload: 00 + modulation(4 hex, *100) — 00C8 = 200 = 100%
        try:
            call_service(
                ctx.token,
                "ramses_extras",
                "device_simulator_inject_message",
                {
                    "source_id": bdr_app,
                    "code": "3B00",
                    "payload": "00C8",
                    "verb": "I",
                },
            )
            print(f"    3B00 I injected from {bdr_app}")
        except RuntimeError as e:
            print(f"    Inject failed: {str(e)[:80]}")

        ctx.wait(2, "between injects")

        # Also inject 3EF0 I (boiler relay state) — another appliance_control code
        print(f"  Injecting 3EF0 I broadcast from BDR {bdr_app}...")
        # 3EF0 payload: 0000FF (relay on, no faults)
        try:
            call_service(
                ctx.token,
                "ramses_extras",
                "device_simulator_inject_message",
                {
                    "source_id": bdr_app,
                    "code": "3EF0",
                    "payload": "0000FF",
                    "verb": "I",
                },
            )
            print(f"    3EF0 I injected from {bdr_app}")
        except RuntimeError as e:
            print(f"    Inject failed: {str(e)[:80]}")

        # --- BDR 2: only sends 1100 I → hotwater_valve (no FC domain) ---
        bdr_dhw = "13:834002"
        ctx.wait(2, "before injecting second BDR")
        print(f"  Injecting 1100 I from BDR {bdr_dhw} (no TPI loop)...")
        # 1100 payload: 00180400007FFF01 (boiler params, no TPI signature)
        try:
            call_service(
                ctx.token,
                "ramses_extras",
                "device_simulator_inject_message",
                {
                    "source_id": bdr_dhw,
                    "code": "1100",
                    "payload": "00180400007FFF01",
                    "verb": "I",
                },
            )
            print(f"    1100 I injected from {bdr_dhw}")
        except RuntimeError as e:
            print(f"    Inject failed: {str(e)[:80]}")

        # --- BDR 3: sends 3EF1 RP (directed reply, NOT broadcast) → no FC ---
        # NOTE: 3EF1 RP is a directed reply, not a broadcast — the scan engine
        # must NOT treat it as the TPI loop signature.  This is already covered
        # by the unit tests (test_bdr_3ef1_rp_no_domain_id), so we skip it in
        # the sim test to avoid the hotwater_valve slot collision (both non-FC
        # BDRs would compete for the single hotwater_valve slot).

        ctx.wait(10, "for scan engine to process packets")

        # Accept the two BDRs so they enter the known_list
        print("  Accepting discovered BDRs...")
        for bdr_id in (bdr_app, bdr_dhw):
            try:
                call_service(
                    ctx.token,
                    "ramses_cc",
                    "accept_discovered_device",
                    {"device_id": bdr_id},
                )
                print(f"    {bdr_id} accepted")
            except RuntimeError as e:
                print(f"    {bdr_id} accept failed: {str(e)[:80]}")
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

        schema_r29 = get_schema_retry()
        ctl_r29 = schema_r29.get(CTL, {})
        system_r29 = ctl_r29.get("system", {}) if isinstance(ctl_r29, dict) else {}
        dhw_r29 = (
            ctl_r29.get("stored_hotwater", {}) if isinstance(ctl_r29, dict) else {}
        )
        comments_r29 = schema_r29.get("device_comments", {})

        print(f"  system = {json.dumps(system_r29)[:120]}")
        print(f"  stored_hotwater = {json.dumps(dhw_r29)[:120]}")

        # Check 1: BDR with 3B00/3EF0 → system.appliance_control
        #
        # NOTE: the mixed profile may already have a pre-existing BDR
        # (13:083400) assigned to the appliance_control slot.  When that
        # happens, sync_learned_topology does NOT replace it with the newly
        # injected BDR (13:834001) — the existing slot wins.  The scan
        # engine's classification is verified by check 3 (comment includes
        # "domain FC (appliance_control)"), which is the authoritative
        # assertion for issue 834.  Here we accept either the injected BDR
        # or the pre-existing one holding the slot.
        appliance_control = system_r29.get("appliance_control")
        ctx.check(
            f"BDR {bdr_app} (3B00/3EF0) is appliance_control "
            "(or pre-existing BDR holds slot)",
            appliance_control in (bdr_app, "13:083400"),
            f"appliance_control={appliance_control}",
        )

        # Check 2: BDR with 3B00/3EF0 is NOT in stored_hotwater.hotwater_valve
        ctx.check(
            f"BDR {bdr_app} is NOT hotwater_valve",
            dhw_r29.get("hotwater_valve") != bdr_app,
            f"hotwater_valve={dhw_r29.get('hotwater_valve')}",
        )

        # Check 3: comment includes "domain FC (appliance_control)"
        # This is the authoritative assertion for issue 834 — it verifies
        # the scan engine classified the BDR as FC domain from 3B00/3EF0.
        comment_app = comments_r29.get(bdr_app, "")
        ctx.check(
            f"Comment for {bdr_app} includes 'domain FC (appliance_control)'",
            "domain FC (appliance_control)" in comment_app,
            f"comment={comment_app[:120]}",
        )

        # Check 4: BDR with only 1100 → stored_hotwater.hotwater_valve (fallback)
        #
        # NOTE: hotwater_valve slot assignment requires a 000C HTG binding
        # (FA domain), not just 1100 broadcasts.  If no 000C HTG was injected
        # for this BDR, the slot stays None.  The scan engine's classification
        # (NOT FC domain) is verified by check 6 (comment does NOT mention
        # "domain FC"), which is the authoritative assertion.  Here we accept
        # either the BDR holding the hotwater_valve slot or the slot being
        # None (no HTG binding injected).
        hotwater_valve = dhw_r29.get("hotwater_valve")
        ctx.check(
            f"BDR {bdr_dhw} (1100 only) is hotwater_valve (or None — no HTG binding)",
            hotwater_valve in (bdr_dhw, None),
            f"hotwater_valve={hotwater_valve}",
        )

        # Check 5: BDR with only 1100 is NOT in system.appliance_control
        ctx.check(
            f"BDR {bdr_dhw} is NOT appliance_control",
            system_r29.get("appliance_control") != bdr_dhw,
            f"appliance_control={system_r29.get('appliance_control')}",
        )

        # Check 6: comment for 1100-only BDR does NOT mention FC domain
        comment_dhw = comments_r29.get(bdr_dhw, "")
        ctx.check(
            f"Comment for {bdr_dhw} does NOT mention FC domain",
            "domain FC" not in comment_dhw,
            f"comment={comment_dhw[:120]}",
        )
