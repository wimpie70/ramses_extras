"""Recipe R115: End-to-end TX/RX verification through MQTT broker.

Verifies that TX and RX both work end-to-end through the ha-sim MQTT
broker, not just structural properties.  Uses the device simulator's
inject_message service for RX and send_packet for TX.

Tests:
1. RX: inject a packet via device_simulator_inject_message → verify
   it reaches the coordinator (log check).
2. TX: call send_packet service → verify the frame is sent (log check).
3. TX with different verbs: I, W → verify each is sent.
4. TX to different device IDs → verify routing works.
5. MQTT bridge exclusion methods exist (exclude/unexclude).
6. Coordinator uses set-based exclusion with is_connected check.
7. Config flow uses runtime port map for primary HGI identification.
8. Non-primary label respects _preferred_type when primary is MQTT.
"""

from __future__ import annotations

import subprocess

from ..base import Recipe, RecipeContext
from ..const import CTL
from ..helpers import (
    call_service,
    docker_exec_python,
    get_current_instance,
)


class R115EndToEndTxRx(Recipe):
    id = "R115"
    seq = 1150
    title = "End-to-end TX/RX through MQTT broker (issue 1185)"
    tags = (
        "pooled",
        "multi-hgi",
        "phase2",
        "tx",
        "rx",
        "mqtt",
        "e2e",
        "issue-1185",
    )

    async def run(self, ctx: RecipeContext) -> None:
        """Verify end-to-end TX/RX through the MQTT broker."""
        ctx.log_section("Recipe 115: End-to-end TX/RX through MQTT")

        ctx.wait_for_ramses_cc_loaded(timeout=20)
        ctx.refresh_token()

        inst = get_current_instance()
        hgi_id = inst.hgi_id

        def grep_log(pattern: str, tail: int = 5) -> str:
            """Grep the HA log for a pattern."""
            r = subprocess.run(
                [
                    "docker",
                    "exec",
                    inst.name,
                    "bash",
                    "-c",
                    f"grep '{pattern}' /config/home-assistant.log | tail -{tail}",
                ],
                capture_output=True,
                text=True,
            )
            return r.stdout

        # ---------------------------------------------------------------------------
        # Test 1: RX — inject a packet via device_simulator_inject_message
        # ---------------------------------------------------------------------------
        rx_code = "30C9"
        try:
            call_service(
                ctx.token,
                "ramses_extras",
                "device_simulator_inject_message",
                {
                    "source_id": "01:150000",
                    "dst": hgi_id,
                    "code": rx_code,
                    "payload": "000834",
                    "verb": "I",
                },
            )
            ctx.wait(3, "for injected packet to propagate")
            log_out = grep_log(rx_code)
            rx_seen = rx_code in log_out
            ctx.check(
                f"RX: injected packet ({rx_code}) reached coordinator",
                rx_seen,
                f"log={log_out[:200]}",
            )
        except Exception as e:
            ctx.check(
                f"RX: injected packet ({rx_code}) reached coordinator",
                False,
                f"exception: {str(e)[:200]}",
            )

        # ---------------------------------------------------------------------------
        # Test 2: TX — call send_packet service
        # ---------------------------------------------------------------------------
        # NOTE: In an MQTT-only pool, there's no serial echo, so the
        # protocol waits for the echo timeout (20s × 3 = 60s).  The
        # call_service HTTP timeout is 30s, so it may raise.  The TX
        # frame IS sent (appears in log) — the timeout is just waiting
        # for the echo.  We catch the timeout and still check the log.
        # ---------------------------------------------------------------------------
        tx_code = "3150"
        try:
            try:
                call_service(
                    ctx.token,
                    "ramses_cc",
                    "send_packet",
                    {
                        "device_id": CTL,
                        "verb": "RQ",
                        "code": tx_code,
                        "payload": "00",
                    },
                )
            except RuntimeError as e:
                if "timed out" not in str(e).lower():
                    raise
            ctx.wait(3, "for TX frame to appear in log")
            log_out = grep_log(tx_code)
            tx_seen = tx_code in log_out
            ctx.check(
                f"TX: send_packet ({tx_code}) frame sent",
                tx_seen,
                f"log={log_out[:200]}",
            )
        except Exception as e:
            ctx.check(
                f"TX: send_packet ({tx_code}) frame sent",
                False,
                f"error: {str(e)[:200]}",
            )

        # ---------------------------------------------------------------------------
        # Test 3: TX with different verbs (I, W)
        # ---------------------------------------------------------------------------
        for verb, code, payload in [
            ("I", "1F09", "00"),
            ("W", "2309", "0001"),
        ]:
            try:
                try:
                    call_service(
                        ctx.token,
                        "ramses_cc",
                        "send_packet",
                        {
                            "device_id": CTL,
                            "verb": verb,
                            "code": code,
                            "payload": payload,
                        },
                    )
                except RuntimeError as e:
                    if "timed out" not in str(e).lower():
                        raise
                ctx.wait(2, f"for {verb} {code} frame in log")
                log_out = grep_log(code)
                ctx.check(
                    f"TX: {verb} {code} frame sent",
                    code in log_out,
                    f"log={log_out[:150]}",
                )
            except Exception as e:
                ctx.check(
                    f"TX: {verb} {code} frame sent",
                    False,
                    f"error: {str(e)[:200]}",
                )

        # ---------------------------------------------------------------------------
        # Test 4: TX to different device IDs
        # ---------------------------------------------------------------------------
        for target_dev in ["04:150003", "37:120000"]:
            try:
                try:
                    call_service(
                        ctx.token,
                        "ramses_cc",
                        "send_packet",
                        {
                            "device_id": target_dev,
                            "verb": "RQ",
                            "code": "3150",
                            "payload": "00",
                        },
                    )
                except RuntimeError as e:
                    if "timed out" not in str(e).lower():
                        raise
                ctx.wait(2, f"for TX to {target_dev} in log")
                log_out = grep_log(f"{target_dev}.*3150")
                ctx.check(
                    f"TX: to {target_dev} routed correctly",
                    target_dev in log_out,
                    f"log={log_out[:150]}",
                )
            except Exception as e:
                ctx.check(
                    f"TX: to {target_dev} routed correctly",
                    False,
                    f"error: {str(e)[:200]}",
                )

        # ---------------------------------------------------------------------------
        # Test 5: MQTT bridge exclusion methods exist
        # ---------------------------------------------------------------------------
        try:
            result = docker_exec_python(
                """
import json, sys
sys.path.insert(0, "/config/custom_components")
try:
    from custom_components.ramses_cc.mqtt_pool_bridge import RamsesMqttPoolBridge
    print(json.dumps({
        "has_exclude": hasattr(RamsesMqttPoolBridge, "exclude_hgi_id"),
        "has_unexclude": hasattr(RamsesMqttPoolBridge, "unexclude_hgi_id"),
    }))
except Exception as e:
    print(json.dumps({"error": str(e)[:200]}))
""",
                timeout=15,
            )
            ctx.check(
                "MQTT bridge: exclude_hgi_id method exists",
                result.get("has_exclude", False),
                f"result={result}",
            )
            ctx.check(
                "MQTT bridge: unexclude_hgi_id method exists",
                result.get("has_unexclude", False),
                f"result={result}",
            )
        except Exception as e:
            ctx.check(
                "MQTT bridge: exclude_hgi_id method exists",
                False,
                f"exception: {str(e)[:200]}",
            )
            ctx.check(
                "MQTT bridge: unexclude_hgi_id method exists",
                False,
                f"exception: {str(e)[:200]}",
            )

        # ---------------------------------------------------------------------------
        # Test 6: Coordinator uses set-based exclusion with is_connected check
        # ---------------------------------------------------------------------------
        try:
            result = docker_exec_python(
                """
import json, sys
sys.path.insert(0, "/config/custom_components")
try:
    from custom_components.ramses_cc.coordinator import RamsesCoordinator
    import inspect
    src = inspect.getsource(RamsesCoordinator)
    print(json.dumps({
        "has_set_based": "_excluded_serial_hgi_ids" in src,
        "has_single_id": "_last_excluded_hgi_id" in src,
        "has_is_connected_check": "is_connected" in src,
    }))
except Exception as e:
    print(json.dumps({"error": str(e)[:200]}))
""",
                timeout=15,
            )
            ctx.check(
                "Coordinator: uses set-based exclusion (_excluded_serial_hgi_ids)",
                result.get("has_set_based", False),
                f"result={result}",
            )
            ctx.check(
                "Coordinator: checks is_connected before excluding",
                result.get("has_is_connected_check", False),
                f"result={result}",
            )
        except Exception as e:
            ctx.check(
                "Coordinator: uses set-based exclusion",
                False,
                f"exception: {str(e)[:200]}",
            )
            ctx.check(
                "Coordinator: checks is_connected before excluding",
                False,
                f"exception: {str(e)[:200]}",
            )

        # ---------------------------------------------------------------------------
        # Test 7: Config flow uses runtime port map for primary HGI
        # ---------------------------------------------------------------------------
        try:
            result = docker_exec_python(
                """
import json, sys, inspect
sys.path.insert(0, "/config/custom_components")
try:
    from custom_components.ramses_cc import config_flow
    src = inspect.getsource(config_flow)
    print(json.dumps({
        "has_runtime_map": "_runtime_map" in src or "_runtime_port_hgi_map" in src,
    }))
except Exception as e:
    print(json.dumps({"error": str(e)[:200]}))
""",
                timeout=15,
            )
            ctx.check(
                "Config flow: uses runtime port map for primary HGI identification",
                result.get("has_runtime_map", False),
                f"result={result}",
            )
        except Exception as e:
            ctx.check(
                "Config flow: uses runtime port map for primary HGI identification",
                False,
                f"exception: {str(e)[:200]}",
            )

        # ---------------------------------------------------------------------------
        # Test 8: Non-primary label respects _preferred_type when primary is MQTT
        # ---------------------------------------------------------------------------
        try:
            result = docker_exec_python(
                """
import json, sys, inspect
sys.path.insert(0, "/config/custom_components")
try:
    from custom_components.ramses_cc import config_flow
    src = inspect.getsource(config_flow)
    has_pref_check = (
        "_preferred_type" in src
        and 'preferred == "usb"' in src
    )
    print(json.dumps({
        "has_pref_check": has_pref_check,
    }))
except Exception as e:
    print(json.dumps({"error": str(e)[:200]}))
""",
                timeout=15,
            )
            ctx.check(
                "Config flow: non-primary label checks _preferred_type"
                " before MQTT fallback",
                result.get("has_pref_check", False),
                f"result={result}",
            )
        except Exception as e:
            ctx.check(
                "Config flow: non-primary label checks _preferred_type"
                " before MQTT fallback",
                False,
                f"exception: {str(e)[:200]}",
            )

        # ---------------------------------------------------------------------------
        # Summary
        # ---------------------------------------------------------------------------
        ctx.log_section("Recipe 115: Summary")
