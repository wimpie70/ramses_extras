"""Recipe R72: 3150 heat_demand value accuracy (regression guard)."""

from __future__ import annotations

from ..base import Recipe, RecipeContext
from ..const import TRV
from ..helpers import (
    call_service,
    grep_ha_log,
    wait_for_schema_populated,
    ws_send,
)


class R72ThreeOneFiveZeroHeatDemandValueAccuracy(Recipe):
    id = "R72"
    seq = 720
    title = "3150 heat_demand value accuracy (regression guard)"
    tags = ("decoder", "3150", "heat_demand")

    async def run(self, ctx: RecipeContext) -> None:
        # No existing recipe verifies specific 3150 heat_demand values.
        # R19 injects 3150 but only checks zone binding, not the decoded
        # demand percentage.  A regression in parse_valve_demand or
        # hex_to_percent could silently change the decoded value without
        # any test catching it.
        #
        # This recipe injects 3150 packets with known heat_demand values
        # and verifies the decoded percentage in the HA log matches exactly.
        # It tests both single-zone (non-array) and multi-zone (array) payloads.
        ctx.log_section("Recipe 72: 3150 heat_demand value accuracy (regression guard)")

        # 1. Load mixed profile (TRV 04:150003 and CTL 01:150000 are in known_list)
        print("  Loading mixed profile...")
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
        ctx.wait_for_ramses_cc_reload(timeout=20)
        ctx.refresh_token()
        wait_for_schema_populated(min_keys=5, timeout=20)

        # --- Single-zone test cases ---
        # 3150 payload format: zone_idx(2 hex) + demand(2 hex)
        # parse_valve_demand converts: hex_to_percent(value, high_res=True)
        # hex_to_percent: int(value, 16) / 200, range 0.0-1.0
        #   "00" -> 0.0, "64" -> 0.5, "C8" -> 1.0
        test_cases = [
            ("00C8", 1.0, "100% demand (0xC8)"),
            ("0064", 0.5, "50% demand (0x64)"),
            ("0000", 0.0, "0% demand (0x00)"),
            ("0032", 0.25, "25% demand (0x32)"),
        ]

        for payload, expected_demand, desc in test_cases:
            print(f"  Injecting 3150 I from TRV {TRV} ({desc})...")
            print(f"    payload: {payload}")
            try:
                call_service(
                    ctx.token,
                    "ramses_extras",
                    "device_simulator_inject_message",
                    {
                        "source_id": TRV,
                        "code": "3150",
                        "payload": payload,
                        "verb": "I",
                    },
                )
                print(f"    3150 I injected ({desc})")
            except RuntimeError as e:
                print(f"    Inject failed: {str(e)[:80]}")
            ctx.wait(2, "for 3150 to process", floor=1.5)

            # Check the decoded payload in the HA log
            # The event handler logs: 'payload': {'heat_demand': <value>}
            log_lines = grep_ha_log(
                f"ramses_cc_regex_match.*3150.*{TRV.replace(':', '.')}.*{payload}"
            )

            decoded_demand: float | None = None
            for line in log_lines:
                if "'heat_demand'" in line:
                    try:
                        payload_str = line.split("'heat_demand': ", 1)[1]
                        payload_str = payload_str.split(",")[0].rstrip("}")
                        decoded_demand = float(payload_str)
                        break
                    except IndexError, ValueError:
                        continue

            print(f"    decoded heat_demand: {decoded_demand}")

            ctx.check(
                f"3150 {desc}: decoded heat_demand = {expected_demand}",
                decoded_demand is not None
                and abs(decoded_demand - expected_demand) < 0.001,
                f"decoded={decoded_demand!r} expected={expected_demand}",
            )

        # --- Multi-zone (array) test ---
        # 3150 array payload: zone_idx + demand repeated for each zone
        # e.g. "03C80464" = zone 03 at 100%, zone 04 at 50%
        # The parser returns a list of dicts with zone_idx and heat_demand
        array_payload = "03C80464"
        print(f"  Injecting 3150 I array from TRV {TRV} (zone 03=100%, zone 04=50%)...")
        print(f"    payload: {array_payload}")
        try:
            call_service(
                ctx.token,
                "ramses_extras",
                "device_simulator_inject_message",
                {
                    "source_id": TRV,
                    "code": "3150",
                    "payload": array_payload,
                    "verb": "I",
                },
            )
            print("    3150 I array injected")
        except RuntimeError as e:
            print(f"    Inject failed: {str(e)[:80]}")
        ctx.wait(2, "for 3150 array to process", floor=1.5)

        # For array payloads, the event log shows a list of dicts
        array_log = grep_ha_log(
            f"ramses_cc_regex_match.*3150.*{TRV.replace(':', '.')}.*{array_payload}"
        )

        # Check that the array was decoded as a list with zone_idx fields
        array_decoded = False
        for line in array_log:
            if "'zone_idx'" in line and "'heat_demand'" in line:
                array_decoded = True
                # Verify zone 03 demand = 1.0
                has_zone_03 = "'03'" in line and "1.0" in line
                has_zone_04 = "'04'" in line and "0.5" in line
                z3 = "found" if has_zone_03 else "missing"
                z4 = "found" if has_zone_04 else "missing"
                print(f"    array decoded: zone_03={z3}, zone_04={z4}")
                ctx.check(
                    "3150 array: zone 03 decoded with heat_demand=1.0",
                    has_zone_03,
                    f"line={line[:200]}",
                )
                ctx.check(
                    "3150 array: zone 04 decoded with heat_demand=0.5",
                    has_zone_04,
                    f"line={line[:200]}",
                )
                break

        ctx.check(
            "3150 array payload decoded as list with zone_idx fields",
            array_decoded,
            f"log_lines={len(array_log)}",
        )

        # --- Check for parser errors (only in recent log lines to avoid
        # matching the giant storage dump at startup which contains "3150"
        # in packet data) ---
        error_lines = grep_ha_log(
            "parser.*3150.*AssertionError|decoder.*3150.*AssertionError",
            since_lines=200,
        )

        ctx.check(
            "No AssertionError from 3150 parser",
            len(error_lines) == 0,
            f"errors={len(error_lines)}",
        )
