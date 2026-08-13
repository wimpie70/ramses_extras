"""Recipe R75: Zone class inference + BDR hotwater_valve fallback (issue 947).

Issue 947 regression — reproduces the scenario reported in
ramses-rf/ramses_cc#947: after clearing the cache and schema, discovery
finds TRV zones but the discovered schema is missing the ``class``
attribute (e.g. ``radiator_valve``) and the DHW BDR relay is orphaned
instead of being associated with ``stored_hotwater.hotwater_valve``.

Two fixes are tested:

1. **Zone class inference (ramses_cc):** ``sync_learned_topology`` now
   infers ``radiator_valve`` for zones that have TRV (04:) actuators and
   no explicit class.  In passive scan mode, ramses_rf's learned schema
   returns ``class=None`` for all zones (eavesdropping is disabled), so
   without inference the config schema never gets a zone class — climate
   entities show default names and lack the expected behaviour.

2. **BDR hotwater_valve fallback (ramses_cc):** when a BDR (13:)
   broadcasts 3EF0 (TPI loop), the scan engine assigns a
   non-authoritative FC domain hint.  Step 2b only uses authoritative
   domain_ids (from 000C bindings), so the BDR stays in
   ``orphans_heat``.  But when ``appliance_control`` is already occupied
   by another device (e.g. an OTB) and ``hotwater_valve`` is empty, the
   BDR is most likely the DHW valve relay — both relays broadcast 3EF0,
   and a BDR with no zone assignment is the DHW valve, not a zone
   actuator.

Expected (correct) behaviour:
  - TRV zones get ``class: radiator_valve`` after sync_learned_topology
  - BDR (13:094705) → stored_hotwater.hotwater_valve (fallback from
    non-auth FC hint, because appliance_control is occupied by OTB)
  - OTB (10:094701) → system.appliance_control (FC domain)

See: https://github.com/ramses-rf/ramses_cc/issues/947
"""

from __future__ import annotations

import json

import yaml as _yaml

from ..base import Recipe, RecipeContext
from ..const import CTL, DHW
from ..helpers import (
    async_clear_cached_state,
    call_service,
    get_current_instance,
    get_schema_retry,
    is_ramses_cc_loaded,
    load_profile_yaml,
    wait_for,
    wait_for_schema_populated,
    ws_send,
)
from ..profile import MIXED_SCHEMA, get_mixed_kl


class R75ZoneClassAndBdrFallbackIssue947(Recipe):
    id = "R75"
    seq = 750
    title = "Zone class inference + BDR hotwater_valve fallback (issue 947)"

    async def run(self, ctx: RecipeContext) -> None:
        # Issue 947 scenario (peternash, 2026-08-13):
        #   OTB 10:064873 = appliance_control (FC domain, via 3EF0)
        #   BDR 13:042605 = hotwater_valve   (FA domain, but no 000C seen)
        #   DHW sensor 07:050121 present
        #   12 heating zones with TRV actuators, no zone class
        #
        # The packet log showed ZERO 0004 (zone name) and ZERO 000C
        # (binding table) packets.  Both relays broadcast 3EF0 as I.
        # Without the fixes:
        #   - Zones have class=None (eavesdropping disabled in ramses_rf)
        #   - BDR stays in orphans_heat (non-auth FC hint ignored by 2b)
        ctx.log_section(
            "Recipe 75: Zone class inference + BDR hotwater_valve fallback (issue 947)"
        )

        # Device IDs — serial numbers < 262144 (18-bit max)
        otb_id = "10:094701"  # OTB = appliance_control
        bdr_id = "13:094705"  # BDR = hotwater_valve (fallback)

        # --- Clear ALL cached state ---
        print("  Clearing cached state...")
        await async_clear_cached_state(ctx, label="R75 pre-restart")
        ctx.log_monitor.reset_baseline()

        # --- Build a custom profile ---
        # Schema declares:
        #   system.appliance_control = OTB (10:094701)
        #   stored_hotwater.sensor = DHW (07:150000)
        #   zones with TRV actuators but NO class (simulating fresh
        #   discovery where ramses_rf returns class=None)
        #
        # The BDR is NOT in the schema — it will be discovered via 3EF0
        # broadcasts and accepted, then placed by the fallback heuristic.
        schema_r75 = dict(MIXED_SCHEMA)
        ctl_schema_r75 = dict(schema_r75.get(CTL, {}))
        # Override system + stored_hotwater
        ctl_schema_r75["system"] = {"appliance_control": otb_id}
        ctl_schema_r75["stored_hotwater"] = {"sensor": DHW}
        # Remove class from zones to simulate fresh discovery
        zones_r75 = dict(ctl_schema_r75.get("zones", {}))
        for zone_idx, zone in zones_r75.items():
            if isinstance(zone, dict):
                zone.pop("class", None)
        ctl_schema_r75["zones"] = zones_r75
        schema_r75[CTL] = ctl_schema_r75

        kl_r75 = get_mixed_kl()
        kl_r75[otb_id] = {"class": "OTB"}
        kl_r75[bdr_id] = {"class": "BDR"}
        # OTB and BDR must be in the schema (SSOT mode derives known_list
        # from schema, so known_list-only entries are dropped).  The BDR
        # is a root entry with no zone/system/DHW role — it goes to
        # orphans_heat.  The 3EF0 injection then gives it a non-auth FC
        # domain hint, and sync_learned_topology step 2f places it as
        # hotwater_valve (since appliance_control is occupied by the OTB).
        schema_r75[otb_id] = {}
        schema_r75[bdr_id] = {}
        # BDR starts in orphans_heat (no zone/system/DHW role)
        schema_r75["orphans_heat"] = [bdr_id]

        profile_r75 = {
            "known_list": kl_r75,
            "_enforce_known_list": {"enabled": True},
            "_schema": schema_r75,
        }
        yaml_text_r75 = _yaml.dump(
            profile_r75, default_flow_style=False, sort_keys=False
        )

        print(
            "  Loading profile "
            "(OTB=appliance_control, DHW sensor, TRV zones no class)..."
        )
        try:
            await load_profile_yaml(ctx.token, yaml_text_r75, speed=0.01)
            print("  Profile loaded")
        except RuntimeError as e:
            print(f"  Profile load failed: {e}")
        ctx.wait_for_ramses_cc_reload(timeout=20)
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
        wait_for_schema_populated(timeout=15)

        # Wait for the device simulator's MQTT client to connect.
        # After clear_cached_state restarts the container, the device
        # simulator's MQTT client takes ~10-15s to connect.  Injected
        # packets are silently dropped while the client is not connected.
        ctx.wait(15, "for simulator MQTT client to connect")

        # --- Step 1: BDR broadcasts 3B00/3EF0 I (TPI loop) ---
        # This gives the BDR a non-authoritative FC domain hint.
        # The OTB also broadcasts 3B00/3EF0 I (it's the appliance_control).
        # We inject multiple rounds because the first injection may be
        # lost if the MQTT client is still connecting.
        for round_num in range(3):
            print(f"  Injection round {round_num + 1}/3...")
            for code in ("3B00", "3EF0"):
                for src_id in (bdr_id, otb_id):
                    try:
                        call_service(
                            ctx.token,
                            "ramses_extras",
                            "device_simulator_inject_message",
                            {
                                "source_id": src_id,
                                "code": code,
                                "payload": "00C8",
                                "verb": "I",
                            },
                        )
                        print(f"    {code} I injected from {src_id}")
                    except RuntimeError as e:
                        print(f"    Inject failed: {str(e)[:80]}")
                    ctx.wait(1, "between injects")
            ctx.wait(3, "between injection rounds")

        # Wait for BDR to appear in schema (it's already there from the
        # profile, but this ensures the scan engine has processed the
        # 3B00/3EF0 injections and assigned the domain_id hint)
        wait_for(
            lambda: bdr_id in get_schema_retry(),
            timeout=15,
            interval=2,
            msg="for BDR to appear in schema",
        )

        # Trigger sync_topology to process the 3EF0 hints and place BDR
        print("  Triggering sync_topology...")
        try:
            call_service(ctx.token, "ramses_cc", "sync_topology")
        except RuntimeError as e:
            print(f"  sync_topology failed: {e}")
        ctx.wait_for_schema_stable(timeout=10, msg="for sync_learned_topology")
        try:
            call_service(ctx.token, "ramses_cc", "force_update")
        except RuntimeError:
            pass
        ctx.wait_for_schema_stable(timeout=8, msg="for save_client_state")

        schema_r75 = get_schema_retry()
        ctl_r75 = schema_r75.get(CTL, {})
        system_r75 = ctl_r75.get("system", {}) if isinstance(ctl_r75, dict) else {}
        dhw_r75 = (
            ctl_r75.get("stored_hotwater", {}) if isinstance(ctl_r75, dict) else {}
        )
        zones_r75 = ctl_r75.get("zones", {}) if isinstance(ctl_r75, dict) else {}
        orphans_heat = schema_r75.get("orphans_heat", [])

        print("  Final schema:")
        print(f"    system = {json.dumps(system_r75)[:120]}")
        print(f"    stored_hotwater = {json.dumps(dhw_r75)[:120]}")
        print(f"    orphans_heat = {orphans_heat}")

        # --- Check 1: OTB is appliance_control ---
        ctx.check(
            f"OTB {otb_id} is appliance_control",
            system_r75.get("appliance_control") == otb_id,
            f"appliance_control={system_r75.get('appliance_control')}",
        )

        # --- Check 2: BDR is hotwater_valve (fallback from non-auth FC) ---
        # The BDR broadcasts 3EF0 (non-auth FC hint), but appliance_control
        # is already occupied by the OTB.  The fallback heuristic in
        # sync_learned_topology step 2f should place it as hotwater_valve.
        ctx.check(
            f"BDR {bdr_id} is hotwater_valve (fallback, issue 947)",
            dhw_r75.get("hotwater_valve") == bdr_id,
            f"hotwater_valve={dhw_r75.get('hotwater_valve')}",
        )

        # --- Check 3: BDR is NOT in orphans_heat ---
        ctx.check(
            f"BDR {bdr_id} is NOT in orphans_heat",
            bdr_id not in orphans_heat,
            f"orphans_heat={orphans_heat}",
        )

        # --- Check 4: BDR is NOT appliance_control ---
        ctx.check(
            f"BDR {bdr_id} is NOT appliance_control",
            system_r75.get("appliance_control") != bdr_id,
            f"appliance_control={system_r75.get('appliance_control')}",
        )

        # --- Check 5: Zones with TRV actuators have class=radiator_valve ---
        # sync_learned_topology step 2e infers radiator_valve for zones
        # with TRV (04:) actuators and no explicit class.
        trv_zones_with_class = 0
        trv_zones_without_class = 0
        for zone_idx, zone in zones_r75.items():
            if not isinstance(zone, dict):
                continue
            actuators = zone.get("actuators", [])
            if not isinstance(actuators, list):
                continue
            # Check if all actuators are TRVs (04: prefix)
            trv_actuators = [
                a for a in actuators if isinstance(a, str) and a.startswith("04:")
            ]
            if trv_actuators and len(trv_actuators) == len(actuators):
                if zone.get("class") == "radiator_valve":
                    trv_zones_with_class += 1
                else:
                    trv_zones_without_class += 1
                    print(
                        f"    Zone {zone_idx} has TRV actuators but "
                        f"class={zone.get('class')}"
                    )

        ctx.check(
            f"TRV zones have class=radiator_valve "
            f"({trv_zones_with_class} found, {trv_zones_without_class} missing)",
            trv_zones_with_class > 0 and trv_zones_without_class == 0,
            f"with_class={trv_zones_with_class} "
            f"without_class={trv_zones_without_class}",
        )

        # --- Check 6: Schema is stable after second sync (no loop) ---
        print("  Triggering second sync_topology (loop detection)...")
        try:
            call_service(ctx.token, "ramses_cc", "sync_topology")
        except RuntimeError as e:
            print(f"  sync_topology failed: {e}")
        ctx.wait(5, "for second sync_learned_topology", floor=3.0)
        try:
            call_service(ctx.token, "ramses_cc", "force_update")
        except RuntimeError:
            pass
        ctx.wait_for_schema_stable(timeout=8, msg="for save")

        schema_r75_2 = get_schema_retry()
        ctl_r75_2 = schema_r75_2.get(CTL, {})
        system_r75_2 = (
            ctl_r75_2.get("system", {}) if isinstance(ctl_r75_2, dict) else {}
        )
        dhw_r75_2 = (
            ctl_r75_2.get("stored_hotwater", {}) if isinstance(ctl_r75_2, dict) else {}
        )
        orphans_heat_2 = schema_r75_2.get("orphans_heat", [])

        print(f"  system (2nd sync) = {json.dumps(system_r75_2)[:120]}")
        print(f"  stored_hotwater (2nd sync) = {json.dumps(dhw_r75_2)[:120]}")

        ctx.check(
            "No loop: OTB still appliance_control after 2nd sync",
            system_r75_2.get("appliance_control") == otb_id,
            f"appliance_control={system_r75_2.get('appliance_control')}",
        )

        ctx.check(
            "No loop: BDR still hotwater_valve after 2nd sync",
            dhw_r75_2.get("hotwater_valve") == bdr_id,
            f"hotwater_valve={dhw_r75_2.get('hotwater_valve')}",
        )

        ctx.check(
            "No loop: BDR not in orphans after 2nd sync",
            bdr_id not in orphans_heat_2,
            f"orphans_heat={orphans_heat_2}",
        )
