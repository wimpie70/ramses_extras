"""Recipe R71: 1260 DHW temperature value accuracy (regression guard)."""

from __future__ import annotations

from ..base import Recipe, RecipeContext
from ..const import DHW
from ..helpers import (
    call_service,
    docker_exec_python,
    grep_ha_log,
    wait_for_schema_populated,
    ws_send,
)


class R71OneTwoSixZeroTempValueAccuracy(Recipe):
    id = "R71"
    seq = 710
    title = "1260 DHW temperature value accuracy (regression guard)"
    tags = ("decoder", "1260", "dhw")

    async def run(self, ctx: RecipeContext) -> None:
        # R35 checks that the water_heater entity's current_temperature is
        # not None (CQRS hydration pipeline functional), but does NOT verify
        # the actual decoded temperature value matches the injected payload.
        #
        # This recipe injects 1260 packets with known temperatures and
        # verifies the decoded value in the HA log matches exactly.  This
        # catches regressions in the hex_to_temp decoder (e.g. wrong scaling,
        # sign handling, or byte offset errors).
        ctx.log_section(
            "Recipe 71: 1260 DHW temperature value accuracy (regression guard)"
        )

        # 1. Load mixed profile (DHW 07:150000 is in the known_list)
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

        # Silence the DHW sensor's periodic emitter to prevent its own
        # 1260 heartbeats from interfering with our injected values.
        print(f"  Silencing DHW {DHW} periodic emitter...")
        try:
            await ws_send(
                ctx.token,
                {
                    "type": "ramses_extras/device_simulator/silence_devices",
                    "device_ids": [DHW],
                    "set_suppress": False,
                },
            )
            print(f"    DHW {DHW} emitter silenced")
        except RuntimeError as e:
            print(f"    Silence failed (continuing): {str(e)[:80]}")
        ctx.wait(2, "for emitter cancellation to take effect")

        # --- Test cases: (payload, expected_temp_c, description) ---
        # 1260 payload format: 00 + temp_hex (4 hex chars, signed int16, /100)
        # hex_to_temp converts: int(value, 16) / 100, with sign handling
        test_cases = [
            ("00157C", 55.0, "55.0C (typical DHW temp)"),
            ("001388", 50.0, "50.0C (low DHW temp)"),
            ("001964", 65.0, "65.0C (high DHW temp)"),
            ("000000", 0.0, "0.0C (zero temp)"),
        ]

        for payload, expected_temp, desc in test_cases:
            print(f"  Injecting 1260 I from DHW {DHW} ({desc})...")
            print(f"    payload: {payload}")
            try:
                call_service(
                    ctx.token,
                    "ramses_extras",
                    "device_simulator_inject_message",
                    {
                        "source_id": DHW,
                        "code": "1260",
                        "payload": payload,
                        "verb": "I",
                    },
                )
                print(f"    1260 I injected ({desc})")
            except RuntimeError as e:
                print(f"    Inject failed: {str(e)[:80]}")
            ctx.wait(2, "for 1260 to process", floor=1.5)

            # --- Decode verification via docker_exec_python ---
            # Call the parser directly inside the container to verify the
            # decoded fields. This is more reliable than grepping logs, which
            # depends on ramses_rf's event logging format and level.
            decode_code = f"""
import json

try:
    from ramses_rf.payloads.dhw import DhwTempPayload

    # {desc}
    payload_hex = "{payload}"
    result = DhwTempPayload.from_bytes(bytearray.fromhex(payload_hex))

    print(json.dumps({{
        "ok": True,
        "temperature": result.temperature,
    }}))
except Exception as e:
    import traceback
    print(json.dumps({{
        "error": f"{{type(e).__name__}}: {{e}}",
        "traceback": traceback.format_exc()[:1000],
        "ok": False,
    }}))
"""
            result = docker_exec_python(decode_code, timeout=30)

            if not result.get("ok"):
                ctx.check(
                    f"1260 {desc}: parser executed without error",
                    False,
                    result.get("error"),
                )
                continue

            decoded_temp = result.get("temperature")

            print(f"    decoded temperature: {decoded_temp}")

            ctx.check(
                f"1260 {desc}: decoded temperature = {expected_temp}",
                decoded_temp is not None and abs(decoded_temp - expected_temp) < 0.01,
                f"decoded={decoded_temp!r} expected={expected_temp}",
            )

        # --- Negative test: ensure no parser errors (only in recent log
        # lines to avoid matching the giant storage dump at startup) ---
        error_lines = grep_ha_log(
            "parser.*1260.*AssertionError|decoder.*1260.*AssertionError",
            since_lines=200,
        )

        ctx.check(
            "No AssertionError from 1260 parser",
            len(error_lines) == 0,
            f"errors={len(error_lines)}",
        )
