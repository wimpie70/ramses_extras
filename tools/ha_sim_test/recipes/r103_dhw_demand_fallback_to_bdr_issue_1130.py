"""Recipe R103: DHW demand fallback to hotwater_valve BDR (issue 1130).

Verifies that the Stored HW (DhwZone) entity's ``heat_demand`` and
``relay_demand`` sensors show the demand from the configured
``hotwater_valve`` BDR when the DhwZone's own ``demand_state`` is
not populated by 0008|FA / 3150|FA packets.

Before the fix (ramses-rf/ramses_cc issue 1130):
  - Stored HW ``heat_demand`` was always ``Unknown`` (no 3150|FA
    packets exist for DHW on real systems).
  - Stored HW ``relay_demand`` tracked CH heat demand (0008|FC routed
    to the TCS, not the DhwZone) or stayed at 0%.

After the fix:
  - DhwZone.heat_demand falls back to the hotwater_valve BDR's
    relay_demand when demand_state.heat_demand is None.
  - DhwZone.relay_demand falls back to the hotwater_valve BDR's
    relay_demand when demand_state.relay_demand is None.
  - The BDR's relay_demand itself has a 3EF0 actuator_state fallback,
    so injecting a 3EF0 I with modulation_level=100% on the BDR
    should propagate to the Stored HW entity.

See: https://github.com/ramses-rf/ramses_cc/issues/1130
"""

from __future__ import annotations

import json
import time

import yaml as _yaml

from ..base import Recipe, RecipeContext
from ..const import CTL, DHW, HGI
from ..helpers import (
    call_service,
    clear_cached_state,
    get_entities,
    get_schema_retry,
    load_profile_yaml,
    wait_for,
    wait_for_ramses_extras_ready,
    wait_for_schema_populated,
    wait_for_transport_ready,
    ws_send,
)
from ..profile import MIXED_SCHEMA, get_mixed_kl

# BDR device ID — serial < 262144 (18-bit max) for valid hex_id.
BDR_ID = "13:113001"


class R103DhwDemandFallbackToBdrIssue1130(Recipe):
    id = "R103"
    seq = 1030
    title = "DHW demand fallback to hotwater_valve BDR (issue 1130)"
    tags = ("dhw", "heat_demand", "relay_demand", "bdr", "3ef0", "0008")

    async def run(self, ctx: RecipeContext) -> None:
        ctx.log_section(
            "Recipe 103: DHW demand fallback to hotwater_valve BDR (issue 1130)"
        )

        # --- 1. Clear cached state and restart ---
        print("  Stopping ha-sim and clearing cached state...")
        clear_cached_state(ctx.log_monitor, label="R103 pre-restart")
        ctx.wait_for_ha_ready(timeout=30)
        ctx.log_monitor.reset_baseline()
        ctx.refresh_token()
        ctx.wait_for_ramses_cc_loaded(timeout=30)
        wait_for_ramses_extras_ready(timeout=90, msg="for ramses_extras after restart")

        # --- 2. Build a custom profile with BDR as hotwater_valve ---
        # The schema declares:
        #   stored_hotwater.sensor = DHW (07:150000)
        #   stored_hotwater.hotwater_valve = BDR (13:113001)
        # This mirrors the real-world topology from issue 1130.
        schema_r103 = dict(MIXED_SCHEMA)
        ctl_schema = dict(schema_r103.get(CTL, {}))
        ctl_schema["stored_hotwater"] = {
            "sensor": DHW,
            "hotwater_valve": BDR_ID,
        }
        schema_r103[CTL] = ctl_schema
        schema_r103[BDR_ID] = {}

        kl_r103 = get_mixed_kl()
        kl_r103[BDR_ID] = {"class": "BDR"}

        profile_r103 = {
            "known_list": kl_r103,
            "_enforce_known_list": {"enabled": True},
            "_schema": schema_r103,
        }
        yaml_text = _yaml.dump(profile_r103, default_flow_style=False, sort_keys=False)

        print("  Loading profile (BDR as hotwater_valve)...")
        try:
            await load_profile_yaml(ctx.token, yaml_text, speed=0.01)
            print("  Profile loaded")
        except RuntimeError as e:
            print(f"  Profile load failed: {e}")
        ctx.wait_for_ramses_cc_reload(timeout=30)
        ctx.refresh_token()
        wait_for_transport_ready(timeout=30)

        # Activate CTL and BDR for heartbeats
        for dev_id, name in [(CTL, "CTL"), (BDR_ID, "BDR")]:
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
        wait_for_schema_populated(min_keys=5, timeout=20)

        # --- 3. Verify schema has BDR as hotwater_valve ---
        schema = get_schema_retry()
        ctl_entry = schema.get(CTL, {})
        dhw_section = ctl_entry.get("stored_hotwater", {})
        if isinstance(dhw_section, dict):
            hw_valve = dhw_section.get("hotwater_valve")
        else:
            hw_valve = None

        print(f"  schema stored_hotwater: {json.dumps(dhw_section)[:120]}")
        ctx.check(
            f"schema has BDR {BDR_ID} as hotwater_valve",
            hw_valve == BDR_ID,
            f"hotwater_valve={hw_valve!r}",
        )

        # --- 4. Inject 3EF0 I from BDR (modulation_level=100%) ---
        #    3EF0 payload (7 bytes):
        #      +0  B  domain_idx (00 = FC for appliance_control, but
        #                   BDR uses its own domain)
        #      +1  H  modulation_level (0x00C8 = 100%)
        #      +3  B  trailing (FF)
        #    The BDR's relay_demand property falls back to
        #    act_state.modulation_level when demand_state.relay_demand
        #    is None.  The DhwZone's heat_demand/relay_demand then
        #    fall back to the BDR's relay_demand.
        print(f"  Injecting 3EF0 I from BDR {BDR_ID} (modulation_level=100%)...")
        try:
            call_service(
                ctx.token,
                "ramses_extras",
                "device_simulator_inject_message",
                {
                    "source_id": BDR_ID,
                    "code": "3EF0",
                    "payload": "00C8FF00FFFF00",
                    "verb": "I",
                },
            )
            print("    3EF0 I injected (modulation=100%)")
        except RuntimeError as e:
            print(f"    Inject failed: {str(e)[:80]}")
        ctx.wait(3, "for 3EF0 to process", floor=2.0)

        # Force entity state update
        try:
            call_service(ctx.token, "ramses_cc", "force_update")
        except RuntimeError:
            pass
        ctx.wait(5, "for entity state write", floor=3.0)

        # --- 5. Find the water_heater entity and its demand sensors ---
        def _find_wh_entity() -> dict | None:
            entities = get_entities(ctx.token)
            for e in entities:
                if e["entity_id"].startswith("water_heater."):
                    return e
            return None

        def _find_dhw_sensor(entity_id_fragment: str) -> dict | None:
            entities = get_entities(ctx.token)
            for e in entities:
                eid = e["entity_id"]
                if (
                    eid.startswith("sensor.")
                    and entity_id_fragment in eid
                    and ("heat_demand" in eid or "relay_demand" in eid)
                ):
                    return e
            return None

        wait_for(
            _find_wh_entity,
            timeout=15,
            interval=2,
            msg="for water_heater entity",
        )

        # --- 6. Poll for demand values to become non-None ---
        #    Re-inject 3EF0 + force_update periodically because async
        #    attribute resolution has a cooldown.
        _re_inject_interval = 3.0
        _last_inject_time = 0.0
        _poll_result: dict = {}

        def _dhw_demand_hydrated() -> bool:
            nonlocal _last_inject_time

            # Look for sensor entities on the DhwZone (01:150000_HW)
            # The sensor entity_id pattern is:
            #   sensor.01_150000_hw_heat_demand
            #   sensor.01_150000_hw_relay_demand
            entities = get_entities(ctx.token)
            hw_heat = None
            hw_relay = None
            for e in entities:
                eid = e["entity_id"]
                if not eid.startswith("sensor."):
                    continue
                if "hw_heat_demand" in eid:
                    hw_heat = e
                elif "hw_relay_demand" in eid:
                    hw_relay = e

            if hw_heat is not None and hw_relay is not None:
                heat_val = hw_heat.get("state")
                relay_val = hw_relay.get("state")
                if heat_val is not None and relay_val is not None:
                    _poll_result.clear()
                    _poll_result.update(
                        {
                            "heat_demand": heat_val,
                            "relay_demand": relay_val,
                            "heat_entity": hw_heat["entity_id"],
                            "relay_entity": hw_relay["entity_id"],
                        }
                    )
                    return True

            # Throttle re-injection
            now = time.monotonic()
            if now - _last_inject_time < _re_inject_interval:
                return False
            _last_inject_time = now
            try:
                call_service(
                    ctx.token,
                    "ramses_extras",
                    "device_simulator_inject_message",
                    {
                        "source_id": BDR_ID,
                        "code": "3EF0",
                        "payload": "00C8FF00FFFF00",
                        "verb": "I",
                    },
                )
            except RuntimeError:
                pass
            try:
                call_service(ctx.token, "ramses_cc", "force_update")
            except RuntimeError:
                pass
            return False

        print("  Polling for DHW demand sensors (60s timeout)...")
        hydrated = wait_for(
            _dhw_demand_hydrated,
            timeout=60,
            interval=3,
            msg="for DHW heat_demand/relay_demand to hydrate from BDR",
            floor=10.0,
        )

        if hydrated and _poll_result:
            result = dict(_poll_result)
        else:
            # Fallback: read whatever we have
            entities = get_entities(ctx.token)
            hw_heat = None
            hw_relay = None
            for e in entities:
                eid = e["entity_id"]
                if not eid.startswith("sensor."):
                    continue
                if "hw_heat_demand" in eid:
                    hw_heat = e
                elif "hw_relay_demand" in eid:
                    hw_relay = e
            result = {
                "heat_demand": hw_heat.get("state") if hw_heat else None,
                "relay_demand": hw_relay.get("state") if hw_relay else None,
                "heat_entity": hw_heat["entity_id"] if hw_heat else "None",
                "relay_entity": (hw_relay["entity_id"] if hw_relay else "None"),
            }

        heat_demand = result["heat_demand"]
        relay_demand = result["relay_demand"]
        heat_entity = result["heat_entity"]
        relay_entity = result["relay_entity"]

        print(f"  DHW heat_demand sensor: {heat_entity}")
        print(f"    state={heat_demand!r}")
        print(f"  DHW relay_demand sensor: {relay_entity}")
        print(f"    state={relay_demand!r}")

        # --- 7. Assertions ---
        # WITHOUT FIX: heat_demand=Unknown, relay_demand=Unknown or 0%
        # WITH FIX: both should be non-None, reflecting the BDR's state
        ctx.check(
            "DHW heat_demand hydrated from BDR fallback (not Unknown)",
            heat_demand is not None and heat_demand != "unknown",
            f"heat_demand={heat_demand!r} (None/unknown = bug present, issue 1130)",
        )

        ctx.check(
            "DHW relay_demand hydrated from BDR fallback (not Unknown)",
            relay_demand is not None and relay_demand != "unknown",
            f"relay_demand={relay_demand!r} (None/unknown = bug present, issue 1130)",
        )

        # --- 8. Also verify the BDR's own relay_demand sensor ---
        #    The BDR should have its own relay_demand sensor that works
        #    via the 3EF0 actuator_state fallback.
        bdr_relay = None
        entities = get_entities(ctx.token)
        bdr_suffix = BDR_ID.replace(":", "_")
        for e in entities:
            eid = e["entity_id"]
            if (
                eid.startswith("sensor.")
                and bdr_suffix in eid
                and "relay_demand" in eid
            ):
                bdr_relay = e
                break

        bdr_relay_val = bdr_relay.get("state") if bdr_relay else None
        bdr_relay_eid = bdr_relay["entity_id"] if bdr_relay else "not found"
        print(f"  BDR relay_demand sensor: {bdr_relay_eid}")
        print(f"    state={bdr_relay_val!r}")

        ctx.check(
            f"BDR {BDR_ID} relay_demand sensor exists",
            bdr_relay is not None,
            f"entity_id={bdr_relay_eid}",
        )

        ctx.check(
            "BDR relay_demand hydrated from 3EF0 (not Unknown)",
            bdr_relay_val is not None and bdr_relay_val != "unknown",
            f"relay_demand={bdr_relay_val!r}",
        )
