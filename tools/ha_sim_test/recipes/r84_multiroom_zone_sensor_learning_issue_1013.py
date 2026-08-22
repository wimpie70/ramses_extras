"""Recipe R84: Multi-room zone sensor learning (issue 1013).

This recipe tests whether the ramses_rf eavesdropper can learn a representative
TRV sensor for a multi-room zone that is NOT included in the CTL's 30C9 zone
temperature array.

In real Evohome systems, the CTL only broadcasts temperatures for zones where it
knows the sensor. Multi-room zones (zones with multiple TRVs but no designated
sensor) are absent from the 30C9 array. This means ``zone.temperature()`` returns
``None`` for these zones, and the 30C9-based eavesdropper cannot match TRV
temperatures to zone temperatures.

The recipe mimics the scenario from issue 1013:
- CTL + 3 TRVs in zone 0B (multi-room, no sensor)
- CTL + 1 TRV in zone 03 (single-TRV, sensor = TRV)
- CTL broadcasts 30C9 array with zone 03 but NOT zone 0B
- TRVs broadcast 30C9 temperatures
- TRVs send 3150 heat_demand with their zone_index

Expected: zone 0B should NOT learn a sensor (zone.temperature() is None).
If it does, there's a mechanism we haven't identified in the eavesdropper code.
"""

from __future__ import annotations

import yaml

from ..base import Recipe, RecipeContext
from ..const import CTL
from ..helpers import (
    _get_ramses_cc_entry_id,
    call_service,
    clear_cached_state,
    get_entities,
    get_schema_retry,
    load_profile_yaml,
    wait_for,
    wait_for_transport_ready,
)


class R84MultiRoomZoneSensorLearningIssue1013(Recipe):
    id = "R84"
    seq = 840
    title = "Multi-room zone sensor learning (issue 1013)"

    async def run(self, ctx: RecipeContext) -> None:
        ctx.log_section("Recipe 84: Multi-room zone sensor learning (issue 1013)")

        # Device IDs (simulator namespace)
        trv_a = "04:150003"  # zone 0B TRV (candidate sensor)
        trv_b = "04:150004"  # zone 0B TRV
        trv_c = "04:150005"  # zone 0B TRV
        trv_d = "04:150006"  # zone 03 TRV (single-TRV zone)

        zone_mr = "0B"  # multi-room zone (3 TRVs, no sensor)
        zone_st = "03"  # single-TRV zone (sensor = TRV)

        # Profile: CTL + 4 TRVs, zone 0B has 3 TRVs (no sensor), zone 03 has 1 TRV
        schema = {
            "main_tcs": CTL,
            CTL: {
                "_class": "CTL",
                "zones": {
                    zone_mr: {
                        "class": "radiator_valve",
                        "sensor": None,
                        "actuators": [trv_a, trv_b, trv_c],
                    },
                    zone_st: {
                        "class": "radiator_valve",
                        "sensor": trv_d,
                        "actuators": [trv_d],
                    },
                },
            },
            trv_a: {"_class": "TRV"},
            trv_b: {"_class": "TRV"},
            trv_c: {"_class": "TRV"},
            trv_d: {"_class": "TRV"},
        }
        profile = {
            "known_list": {
                CTL: {"class": "CTL"},
                trv_a: {"class": "TRV"},
                trv_b: {"class": "TRV"},
                trv_c: {"class": "TRV"},
                trv_d: {"class": "TRV"},
            },
            "_enforce_known_list": {"enabled": True},
            "_schema": schema,
        }

        clear_cached_state(ctx.log_monitor, label="R84 pre-restart")
        ctx.wait_for_ha_ready(timeout=30)
        ctx.log_monitor.reset_baseline()
        ctx.refresh_token()
        ctx.wait_for_ramses_cc_loaded(timeout=30)

        print("  Loading multi-room zone profile (zone 0B: 3 TRVs, no sensor)...")
        await load_profile_yaml(
            ctx.token,
            yaml.dump(profile, default_flow_style=False, sort_keys=False),
            speed=0.01,
            enable_eavesdrop=True,
        )
        ctx.wait_for_ramses_cc_reload(timeout=20)
        ctx.refresh_token()
        wait_for_transport_ready(timeout=30)
        wait_for(
            lambda: (
                zone_mr
                in get_schema_retry(max_tries=3, delay=1).get(CTL, {}).get("zones", {})
            ),
            timeout=15,
            interval=1,
            msg="for multi-room zone schema",
            floor=3.0,
        )

        def _inject(
            source_id: str,
            code: str,
            payload: str,
            verb: str = "I",
            dst: str = "--:------",
        ) -> None:
            call_service(
                ctx.token,
                "ramses_extras",
                "device_simulator_inject_message",
                {
                    "source_id": source_id,
                    "dst": dst,
                    "code": code,
                    "payload": payload,
                    "verb": verb,
                },
            )

        # Step 1: Inject 3150 packets to bind TRVs as actuators to zones
        # 3150 payload: zone_index(1 byte) + heat_demand(1 byte)
        print("  Step 1: Injecting 3150 heat_demand packets for zone binding...")
        _inject(trv_a, "3150", f"{zone_mr}00")
        ctx.wait(0.5, "after 3150 from trv_a")
        _inject(trv_b, "3150", f"{zone_mr}00")
        ctx.wait(0.5, "after 3150 from trv_b")
        _inject(trv_c, "3150", f"{zone_mr}00")
        ctx.wait(0.5, "after 3150 from trv_c")
        _inject(trv_d, "3150", f"{zone_st}00")
        ctx.wait(1, "after 3150 from trv_d")

        # Check actuator binding
        schema_after_3150 = get_schema_retry(max_tries=3, delay=1)
        zone_mr_schema = (
            schema_after_3150.get(CTL, {}).get("zones", {}).get(zone_mr, {})
        )
        zone_st_schema = (
            schema_after_3150.get(CTL, {}).get("zones", {}).get(zone_st, {})
        )
        print(f"  Zone {zone_mr} after 3150: {zone_mr_schema}")
        print(f"  Zone {zone_st} after 3150: {zone_st_schema}")

        ctx.check(
            f"zone {zone_mr} has actuators after 3150",
            len(zone_mr_schema.get("actuators", [])) > 0,
            f"zone={zone_mr_schema}",
        )

        # Step 2: Inject CTL 30C9 zone array WITHOUT zone 0B
        # This mimics real Evohome behaviour: CTL only broadcasts temps for
        # zones where it knows the sensor. Zone 0B (multi-room, no sensor) is absent.
        # Payload format: zone_idx(1) + temp_hex(2) per zone, prefixed with "00"
        # Zone 03 temp = 21.0C = 0x0834
        print("  Step 2: Injecting CTL 30C9 zone array (without multi-room zone)...")
        ctl_payload_1 = f"00{zone_st}0834"  # zone 03: 21.0C
        _inject(CTL, "30C9", ctl_payload_1)
        ctx.wait(1, "after first CTL 30C9")

        # Step 3: Inject TRV 30C9 temperature broadcasts
        # trv_a (zone 0B): 21.0C = 0x0834 — matches zone 03's temp!
        # trv_d (zone 03): 21.0C = 0x0834
        print("  Step 3: Injecting TRV 30C9 temperature broadcasts...")
        _inject(trv_d, "30C9", "000834")  # zone 03 TRV: 21.0C
        ctx.wait(0.5, "after trv_d 30C9")
        _inject(trv_a, "30C9", "000834")  # zone 0B TRV: 21.0C (same as zone 03!)
        ctx.wait(0.5, "after trv_a 30C9")
        _inject(trv_b, "30C9", "000820")  # zone 0B TRV: 20.8C
        ctx.wait(0.5, "after trv_b 30C9")
        _inject(trv_c, "30C9", "000810")  # zone 0B TRV: 20.8C
        ctx.wait(2, "for eavesdropper processing")

        # Check if any sensor was learned for zone 0B
        schema_after_30c9 = get_schema_retry(max_tries=3, delay=1)
        zone_mr_after = schema_after_30c9.get(CTL, {}).get("zones", {}).get(zone_mr, {})
        zone_st_after = schema_after_30c9.get(CTL, {}).get("zones", {}).get(zone_st, {})
        print(f"  Zone {zone_mr} after 30C9: {zone_mr_after}")
        print(f"  Zone {zone_st} after 30C9: {zone_st_after}")

        ctx.check(
            f"zone {zone_mr} has NO sensor (multi-room, not in CTL array)",
            zone_mr_after.get("sensor") is None,
            f"zone={zone_mr_after}",
        )

        # Step 4: Inject a second CTL 30C9 with a CHANGED temperature for zone 03
        # This triggers _eavesdrop_from_controller_broadcast, which looks for
        # TRVs with matching temp that broadcast after the previous CTL array.
        print("  Step 4: Injecting second CTL 30C9 with changed zone 03 temp...")
        ctl_payload_2 = f"00{zone_st}0840"  # zone 03: 21.12C (changed from 21.0C)
        _inject(CTL, "30C9", ctl_payload_2)
        ctx.wait(1, "after second CTL 30C9")

        # Inject TRV 30C9 with matching temp for the changed zone
        _inject(
            trv_d, "30C9", "000840"
        )  # zone 03 TRV: 21.12C (matches changed zone 03)
        ctx.wait(0.5, "after trv_d 30C9 match")
        _inject(trv_a, "30C9", "000840")  # zone 0B TRV: also 21.12C (collision!)
        ctx.wait(2, "for eavesdropper processing")

        schema_after_change = get_schema_retry(max_tries=3, delay=1)
        zone_mr_final = (
            schema_after_change.get(CTL, {}).get("zones", {}).get(zone_mr, {})
        )
        zone_st_final = (
            schema_after_change.get(CTL, {}).get("zones", {}).get(zone_st, {})
        )
        print(f"  Zone {zone_mr} final: {zone_mr_final}")
        print(f"  Zone {zone_st} final: {zone_st_final}")

        # The eavesdropper should NOT bind trv_a to zone 0B because:
        # 1. zone 0B is not in the CTL 30C9 array (zone.temperature() is None)
        # 2. trv_a's temp matches zone 03's temp, but trv_d also matches
        #    (collision abstinence prevents binding)
        ctx.check(
            f"zone {zone_mr} still has NO sensor after temp change",
            zone_mr_final.get("sensor") is None,
            f"zone={zone_mr_final}",
        )

        # Step 5: Try the scenario from comment 1 — inject a TRV 30C9 that
        # matches NO zone temp (unique temperature), see if it gets bound
        # to any zone via _eavesdrop_from_trv_broadcast
        print("  Step 5: Injecting TRV with unique temp (no zone match)...")
        _inject(trv_a, "30C9", "000999")  # 24.57C — no zone has this temp
        ctx.wait(2, "for eavesdropper processing")

        schema_unique = get_schema_retry(max_tries=3, delay=1)
        zone_mr_unique = schema_unique.get(CTL, {}).get("zones", {}).get(zone_mr, {})
        print(f"  Zone {zone_mr} after unique temp: {zone_mr_unique}")

        ctx.check(
            f"zone {zone_mr} has NO sensor after unique temp",
            zone_mr_unique.get("sensor") is None,
            f"zone={zone_mr_unique}",
        )

        # Step 6: Force topology sync and check final state
        print("  Step 6: Force topology sync...")
        call_service(ctx.token, "ramses_cc", "sync_topology")
        ctx.wait(3, "for topology sync")

        final_schema = get_schema_retry()
        zone_mr_final2 = final_schema.get(CTL, {}).get("zones", {}).get(zone_mr, {})
        zone_st_final2 = final_schema.get(CTL, {}).get("zones", {}).get(zone_st, {})
        print(f"  Zone {zone_mr} final after sync: {zone_mr_final2}")
        print(f"  Zone {zone_st} final after sync: {zone_st_final2}")

        ctx.check(
            f"zone {zone_mr} has NO sensor after sync_topology",
            zone_mr_final2.get("sensor") is None,
            f"zone={zone_mr_final2}",
        )

        # Step 7: HGI polling — inject RQ 30C9 from HGI → RP 30C9 from CTL
        # This is the key mechanism from the peternash conversation logs:
        # HGIs actively poll the CTL for individual zone temps (including
        # multi-room zones NOT in the CTL's broadcast array). The CTL responds
        # with RP 30C9 containing the zone temperature. This sets
        # zone.temperature() for the multi-room zone, enabling the eavesdropper
        # to match TRV 30C9 broadcasts.
        #
        # In passive scan mode (no HGI polling), this doesn't happen, so the
        # eavesdropper can't learn sensors for multi-room zones.
        print("  Step 7: HGI polling — RQ/RP 30C9 for multi-room zone 0B...")
        hgi = "18:001234"

        # HGI polls CTL for zone 0B temperature
        # RQ 30C9 payload is just the zone_index (1 byte)
        _inject(hgi, "30C9", zone_mr, verb="RQ", dst=CTL)
        ctx.wait(0.5, "after HGI RQ 30C9")

        # CTL responds with RP 30C9: zone_index(1) + temperature(2)
        # Zone 0B temp = 21.0C = 0x0834
        rp_payload = f"{zone_mr}0834"
        _inject(CTL, "30C9", rp_payload, verb="RP", dst=hgi)
        ctx.wait(1, "after CTL RP 30C9 for zone 0B")

        # Now inject TRV 30C9 with matching temperature
        # trv_a (zone 0B): 21.0C = 0x0834 — matches zone 0B's polled temp!
        print("  Step 7b: Inject TRV 30C9 matching the polled zone 0B temp...")
        _inject(trv_a, "30C9", f"{zone_mr}0834")  # zone 0B, 21.0C
        ctx.wait(2, "for eavesdropper processing")

        # The eavesdropper learns the sensor in ramses_rf's internal state,
        # but it needs a sync_topology to propagate to ramses_cc's config schema.
        print("  Step 7c: Force topology sync to propagate learned sensor...")
        call_service(ctx.token, "ramses_cc", "sync_topology")
        ctx.wait(3, "for topology sync")

        schema_after_poll = get_schema_retry(max_tries=3, delay=1)
        zone_mr_polled = (
            schema_after_poll.get(CTL, {}).get("zones", {}).get(zone_mr, {})
        )
        print(f"  Zone {zone_mr} after HGI polling: {zone_mr_polled}")

        # The eavesdropper SHOULD now be able to learn the sensor, because:
        # 1. HGI polled CTL for zone 0B temp → zone.temperature() = 21.0C
        # 2. trv_a broadcast 30C9 with temp 21.0C → matches zone 0B
        # 3. No other zone has temp 21.0C (zone 03 was changed to 21.12C in step 4)
        # 4. Collision abstinence: only one zone matches → trv_a bound as sensor
        ctx.check(
            f"zone {zone_mr} learns sensor via HGI polling",
            zone_mr_polled.get("sensor") == trv_a,
            f"zone={zone_mr_polled}",
        )

        # Summary
        print()
        print("  === Summary ===")
        print(f"  Multi-room zone {zone_mr} (not in CTL 30C9 array):")
        print(f"    sensor = {zone_mr_polled.get('sensor')}")
        print(f"    actuators = {zone_mr_polled.get('actuators')}")
        print(f"  Single-TRV zone {zone_st} (in CTL 30C9 array):")
        zone_st_final = schema_after_poll.get(CTL, {}).get("zones", {}).get(zone_st, {})
        print(f"    sensor = {zone_st_final.get('sensor')}")
        print(f"    actuators = {zone_st_final.get('actuators')}")
        print()
        if zone_mr_polled.get("sensor") == trv_a:
            print("  CONFIRMED: HGI polling (RQ/RP 30C9) enables sensor learning")
            print("  for multi-room zones not in CTL 30C9 array.")
            print("  This is the mechanism that was lost in passive scan mode.")
        elif zone_mr_polled.get("sensor") is None:
            print("  CONFIRMED: eavesdropper cannot learn sensor for multi-room zone")
            print("  not in CTL 30C9 array, even with HGI polling.")
            print("  The RQ/RP 30C9 path may not set zone.temperature() in ramses_rf.")
        else:
            print(f"  UNEXPECTED: sensor={zone_mr_polled.get('sensor')}")
            print("  This needs further investigation.")
