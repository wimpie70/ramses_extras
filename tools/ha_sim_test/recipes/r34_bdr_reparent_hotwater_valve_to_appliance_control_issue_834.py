"""Recipe R34: BDR re-parent hotwater_valve → appliance_control (issue 834)."""

from __future__ import annotations

import json
import subprocess

import yaml as _yaml

from ..base import Recipe, RecipeContext
from ..const import CTL, DHW, FAN, HGI, REM
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


class R34BdrReparentHotwaterValveToApplianceControlIssue834(Recipe):
    id = "R34"
    seq = 360
    title = "BDR re-parent hotwater_valve → appliance_control (issue 834)"

    async def run(self, ctx: RecipeContext) -> None:
        # Issue 834 race condition: the controller's 000C binding table has
        # a BDR in the HTG slot (domain FA = hotwater_valve), but the BDR is
        # actually the appliance_control (domain FC).  When the 000C HTG
        # binding arrives first, the BDR is incorrectly bound as
        # hotwater_valve to a spuriously-created DhwZone.  When the 000C
        # APP binding arrives later, the BDR must be re-parented from
        # DhwZone.hotwater_valve to System.appliance_control.
        #
        # This recipe simulates the race:
        #   1. Inject 000C RP with HTG role (0E) → BDR bound as hotwater_valve
        #   2. Inject 000C RP with APP role (0F) → BDR re-parented to
        #      appliance_control
        #
        # The profile has NO DHW sensor — the re-parenting is suppressed
        # when a DHW sensor exists (the system genuinely has DHW in that
        # case).
        ctx.log_section(
            "Recipe 34: BDR re-parent hotwater_valve → appliance_control "
            "(issue 834 race condition)"
        )

        # NOTE: the serial number must be < 262144 (18-bit max), otherwise
        # the hex_id overflows into the device-type bits and convert_from_hex
        # returns a different device_id (e.g. 13:834001 → 0x40B9D1 → 16:047569).
        # 13:083400 references issue 834 while staying within the valid range.
        bdr_id = "13:083400"
        # dev_id_to_hex_id("13:083400") = (13 << 18) + 83400 = 0x3545C8
        bdr_hex_id = "3545C8"

        # --- Clear ALL cached state from previous tests (e.g. R29 binds BDR
        # as appliance_control and writes it to the config entry schema).
        # Both .storage/ramses_cc (client state cache) AND the CONF_SCHEMA in
        # core.config_entries persist across docker restarts (bind mount).
        # deep_merge preserves old keys like system: {appliance_control: ...}
        # from the cached schema even when the config schema sets system: {}.
        # The ramses.db message database also persists and replays old 000C
        # packets (including the 000F003545C8 APP binding from a previous run)
        # which would trigger the re-parenting before our manual inject.
        # We must stop the container, delete all three, and restart to get
        # a truly clean state for this race condition test.
        print("  Stopping ha-sim and clearing cached state...")
        clear_cached_state(ctx.log_monitor, label="R34 pre-restart")
        ctx.wait_for(is_ha_ready, timeout=30, msg="for ha-sim to start up")
        ctx.log_monitor.reset_baseline()
        ctx.refresh_token()
        ctx.wait_for(is_ramses_cc_loaded, timeout=15, msg="for ramses_cc to initialize")

        # --- Build a custom profile without DHW sensor ---
        # The mixed profile has stored_hotwater: {sensor: DHW}.  We remove
        # it so the DhwZone created by the 000C HTG binding has no sensor,
        # which is the precondition for re-parenting.
        # We also explicitly clear `system` to prevent the schema merge from
        # preserving appliance_control bindings from previous tests (e.g. R29).
        schema_r34 = dict(MIXED_SCHEMA)
        ctl_schema_r34 = dict(schema_r34.get(CTL, {}))
        # Remove stored_hotwater — this system has NO DHW
        ctl_schema_r34.pop("stored_hotwater", None)
        # Explicitly clear system to prevent merge preserving old bindings
        ctl_schema_r34["system"] = {}
        schema_r34[CTL] = ctl_schema_r34

        kl_r34 = dict(MIXED_KL)
        kl_r34[bdr_id] = {"class": "BDR"}
        # Remove the DHW sensor from the known_list — this system has NO DHW,
        # so the DHW sensor should not be present to create a DhwZone
        kl_r34.pop(DHW, None)

        # The BDR must also be in the schema (SSOT mode derives known_list
        # from schema, so a known_list-only entry would be dropped).
        schema_r34[bdr_id] = {}

        profile_r34 = {
            "known_list": kl_r34,
            "_enforce_known_list": {"enabled": True},
            "_schema": schema_r34,
        }
        yaml_text_r34 = _yaml.dump(
            profile_r34, default_flow_style=False, sort_keys=False
        )

        print("  Loading profile (no DHW sensor, BDR in known_list)...")
        try:
            await load_profile_yaml(ctx.token, yaml_text_r34, speed=0.01)
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

        # --- Step 1: Inject 000C RP with HTG role (0E) ---
        # This binds the BDR as hotwater_valve (domain FA) to a DhwZone.
        # 000C payload (long format, 12 chars):
        #   00 (idx) + 0E (HTG role) + 00 (pad) + 40B9D1 (hex_id for 13:834001)
        htg_payload = f"000E00{bdr_hex_id}"
        print(f"  Injecting 000C RP (HTG/hotwater_valve) from CTL for BDR {bdr_id}...")
        print(f"    payload: {htg_payload}")
        try:
            call_service(
                ctx.token,
                "ramses_extras",
                "device_simulator_inject_message",
                {
                    "source_id": CTL,
                    "dst": HGI,
                    "code": "000C",
                    "payload": htg_payload,
                    "verb": "RP",
                },
            )
            print("    000C RP (HTG) injected")
        except RuntimeError as e:
            print(f"    Inject failed: {str(e)[:80]}")

        ctx.wait(5, "for 000C HTG processing")
        try:
            call_service(ctx.token, "ramses_cc", "sync_topology")
        except RuntimeError as e:
            print(f"  sync_topology failed: {e}")
        ctx.wait(10, "for sync_learned_topology")
        try:
            call_service(ctx.token, "ramses_cc", "force_update")
        except RuntimeError:
            pass
        ctx.wait(5, "for save")

        schema_step1 = get_schema_retry()
        ctl_step1 = schema_step1.get(CTL, {})
        system_step1 = (
            ctl_step1.get("system", {}) if isinstance(ctl_step1, dict) else {}
        )
        dhw_step1 = (
            ctl_step1.get("stored_hotwater", {}) if isinstance(ctl_step1, dict) else {}
        )

        print("  After HTG inject:")
        print(f"    system = {json.dumps(system_step1)[:120]}")
        print(f"    stored_hotwater = {json.dumps(dhw_step1)[:120]}")

        # Check 1: BDR is bound as hotwater_valve (the incorrect state)
        ctx.check(
            f"BDR {bdr_id} is hotwater_valve after 000C HTG",
            dhw_step1.get("hotwater_valve") == bdr_id,
            f"hotwater_valve={dhw_step1.get('hotwater_valve')}",
        )

        # Check 2: BDR is NOT appliance_control yet
        ctx.check(
            f"BDR {bdr_id} is NOT appliance_control after 000C HTG",
            system_step1.get("appliance_control") != bdr_id,
            f"appliance_control={system_step1.get('appliance_control')}",
        )

        # --- Step 2: Inject 000C RP with APP role (0F) ---
        # This should re-parent the BDR from DhwZone.hotwater_valve (FA)
        # to System.appliance_control (FC), because the DhwZone has no
        # DHW sensor.
        # 000C payload (long format, 12 chars):
        #   00 (idx) + 0F (APP role) + 00 (pad) + 40B9D1 (hex_id)
        app_payload = f"000F00{bdr_hex_id}"
        print(
            f"  Injecting 000C RP (APP/appliance_control) from CTL for BDR {bdr_id}..."
        )
        print(f"    payload: {app_payload}")
        try:
            call_service(
                ctx.token,
                "ramses_extras",
                "device_simulator_inject_message",
                {
                    "source_id": CTL,
                    "dst": HGI,
                    "code": "000C",
                    "payload": app_payload,
                    "verb": "RP",
                },
            )
            print("    000C RP (APP) injected")
        except RuntimeError as e:
            print(f"    Inject failed: {str(e)[:80]}")

        ctx.wait(5, "for 000C APP processing")
        try:
            call_service(ctx.token, "ramses_cc", "sync_topology")
        except RuntimeError as e:
            print(f"  sync_topology failed: {e}")
        ctx.wait(10, "for sync_learned_topology")
        try:
            call_service(ctx.token, "ramses_cc", "force_update")
        except RuntimeError:
            pass
        ctx.wait(5, "for save")

        schema_step2 = get_schema_retry()
        ctl_step2 = schema_step2.get(CTL, {})
        system_step2 = (
            ctl_step2.get("system", {}) if isinstance(ctl_step2, dict) else {}
        )
        dhw_step2 = (
            ctl_step2.get("stored_hotwater", {}) if isinstance(ctl_step2, dict) else {}
        )

        print("  After APP inject:")
        print(f"    system = {json.dumps(system_step2)[:120]}")
        print(f"    stored_hotwater = {json.dumps(dhw_step2)[:120]}")

        # Check 3: BDR is now appliance_control (re-parented)
        ctx.check(
            f"BDR {bdr_id} is appliance_control after 000C APP (re-parented)",
            system_step2.get("appliance_control") == bdr_id,
            f"appliance_control={system_step2.get('appliance_control')}",
        )

        # Check 4: BDR is NO LONGER hotwater_valve
        ctx.check(
            f"BDR {bdr_id} is NOT hotwater_valve after re-parenting",
            dhw_step2.get("hotwater_valve") != bdr_id,
            f"hotwater_valve={dhw_step2.get('hotwater_valve')}",
        )

        # Check 5: stored_hotwater should be empty (DhwZone cleaned up)
        ctx.check(
            "stored_hotwater is empty after re-parenting",
            not dhw_step2
            or (
                isinstance(dhw_step2, dict)
                and not dhw_step2.get("hotwater_valve")
                and not dhw_step2.get("heating_valve")
                and not dhw_step2.get("sensor")
            ),
            f"stored_hotwater={json.dumps(dhw_step2)[:120]}",
        )
