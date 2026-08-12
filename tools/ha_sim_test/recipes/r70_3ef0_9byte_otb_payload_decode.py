"""Recipe R70: 3EF0 9-byte OTB payload decode (regression guard for PR 1031)."""

from __future__ import annotations

import json

from ..base import Recipe, RecipeContext
from ..const import CTL
from ..helpers import (
    call_service,
    docker_exec_python,
    grep_ha_log,
    wait_for_schema_populated,
    ws_send,
)


class R70ThreeEf0NineByteOtbPayloadDecode(Recipe):
    id = "R70"
    seq = 700
    title = "3EF0 9-byte OTB payload decode (PR 1031 regression guard)"
    tags = ("decoder", "3ef0", "otb")

    async def run(self, ctx: RecipeContext) -> None:
        # PR 1031 introduced a regression where ActuatorStatePayload (3EF0)
        # dropped bytes 4-8 for 9-byte payloads from R8820A OTBs.  The 9-byte
        # variant carries ch_enabled, ch_setpoint, and max_rel_modulation in
        # bytes 6-8 — fields that are absent from the 3-byte and 6-byte
        # variants.
        #
        # This recipe:
        #   1. Injects a 9-byte and 6-byte 3EF0 I packet via the simulator
        #      (E2E: verifies the injection path works).
        #   2. Calls the parser directly via docker_exec_python to verify
        #      the decoded fields (structural: reliable, no log-grep fragility).
        #   3. Checks for parser AssertionError in the HA log.
        ctx.log_section(
            "Recipe 70: 3EF0 9-byte OTB payload decode (PR 1031 regression guard)"
        )

        # 1. Load mixed profile (CTL is in the known_list)
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

        # --- 9-byte 3EF0 I from CTL ---
        # Payload: 00C8100000FF035064 (9 bytes = 18 hex chars)
        #   00      context
        #   C8      modulation_level = hex_to_percent("C8") = 1.0 (100%)
        #   10      _flags_2 (valid: "00", "10", "11")
        #   00      _flags_3 (no active flags: ch/dhw/cool/flame all False)
        #   00FF    _unknown_4, _unknown_5
        #   03      _flags_6 (bit 0=ch_enabled=True, bit 1=required set)
        #   50      ch_setpoint = 0x50 = 80
        #   64      max_rel_modulation = hex_to_percent("64") = 0.5 (50%)
        payload_9byte = "00C8100000FF035064"
        print(f"  Injecting 9-byte 3EF0 I from CTL {CTL}...")
        print(f"    payload: {payload_9byte}")
        try:
            call_service(
                ctx.token,
                "ramses_extras",
                "device_simulator_inject_message",
                {
                    "source_id": CTL,
                    "code": "3EF0",
                    "payload": payload_9byte,
                    "verb": "I",
                },
            )
            print("    3EF0 9-byte injected")
        except RuntimeError as e:
            print(f"    Inject failed: {str(e)[:80]}")
        ctx.wait(3, "for 3EF0 9-byte to process", floor=2.0)

        # Check log for the 9-byte packet (simulator publish confirmation)
        log_9byte = grep_ha_log("3EF0.*009.*00C8100000FF035064")

        ctx.check(
            "9-byte 3EF0 packet received by protocol layer",
            len(log_9byte) > 0,
            f"log_lines={len(log_9byte)}",
        )

        # --- 6-byte 3EF0 I from CTL (for comparison) ---
        # Payload: 0000100000FF (6 bytes = 12 hex chars)
        #   00      context
        #   00      modulation_level = 0.0
        #   10      _flags_2
        #   00      _flags_3 (no active flags)
        #   00FF    _unknown_4, _unknown_5
        payload_6byte = "0000100000FF"
        print(f"  Injecting 6-byte 3EF0 I from CTL {CTL}...")
        print(f"    payload: {payload_6byte}")
        try:
            call_service(
                ctx.token,
                "ramses_extras",
                "device_simulator_inject_message",
                {
                    "source_id": CTL,
                    "code": "3EF0",
                    "payload": payload_6byte,
                    "verb": "I",
                },
            )
            print("    3EF0 6-byte injected")
        except RuntimeError as e:
            print(f"    Inject failed: {str(e)[:80]}")
        ctx.wait(3, "for 3EF0 6-byte to process", floor=2.0)

        # --- Decode verification via docker_exec_python ---
        # Call the parser directly inside the container to verify the
        # decoded fields.  This is more reliable than grepping logs, which
        # depends on ramses_rf's event logging format and level.
        decode_code = f"""
import json

try:
    from ramses_rf.parsers.heating import parser_3ef0

    # Build a mock message — parser_3ef0(payload, msg) accesses
    # msg.src.type and msg.len
    class MockSrc:
        type = None  # not JIM, so skips the Jasper branch

    class MockMsg:
        def __init__(self, length):
            self.len = length
            self.src = MockSrc()

    # 9-byte payload: 00C8100000FF035064
    msg9 = MockMsg(9)
    result9 = parser_3ef0("{payload_9byte}", msg9)

    # 6-byte payload: 0000100000FF
    msg6 = MockMsg(6)
    result6 = parser_3ef0("{payload_6byte}", msg6)

    d9 = result9 if isinstance(result9, dict) else {{}}
    d6 = result6 if isinstance(result6, dict) else {{}}
    print(json.dumps({{
        "ok": True,
        "r9_keys": sorted(d9.keys()),
        "r9_ch_enabled": d9.get("ch_enabled"),
        "r9_ch_setpoint": d9.get("ch_setpoint"),
        "r9_max_rel_modulation": d9.get("max_rel_modulation"),
        "r9_modulation_level": d9.get("modulation_level"),
        "r6_keys": sorted(d6.keys()),
        "r6_modulation_level": d6.get("modulation_level"),
        "r6_has_ch_setpoint": "ch_setpoint" in d6,
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
                "3EF0 parser runs without error",
                False,
                result.get("error", "unknown"),
            )
            # Skip remaining checks if parser crashed
            ctx.check(
                "9-byte 3EF0 decoded with ch_enabled field",
                False,
                "parser error",
            )
            ctx.check(
                "9-byte 3EF0 ch_enabled=True (bit 0 of byte 6)",
                False,
                "parser error",
            )
            ctx.check("9-byte 3EF0 ch_setpoint=80 (byte 7)", False, "parser error")
            ctx.check("9-byte 3EF0 max_rel_modulation=0.5", False, "parser error")
            ctx.check("9-byte 3EF0 modulation_level=1.0", False, "parser error")
            ctx.check(
                "6-byte 3EF0 decoded with modulation_level",
                False,
                "parser error",
            )
            ctx.check(
                "6-byte 3EF0 does NOT have ch_setpoint",
                False,
                "parser error",
            )
            ctx.check(
                "No AssertionError from 3EF0 parser",
                False,
                "parser error",
            )
            return

        ctx.check("3EF0 parser runs without error", True, "")

        # 9-byte checks
        r9_keys = result.get("r9_keys", [])
        ctx.check(
            "9-byte 3EF0 decoded with ch_enabled field (bytes 6-8 not dropped)",
            "ch_enabled" in r9_keys,
            f"keys={r9_keys[:10]}",
        )
        ctx.check(
            "9-byte 3EF0 ch_enabled=True (bit 0 of byte 6)",
            result.get("r9_ch_enabled") is True,
            f"ch_enabled={result.get('r9_ch_enabled')!r}",
        )
        ctx.check(
            "9-byte 3EF0 ch_setpoint=80 (byte 7)",
            result.get("r9_ch_setpoint") == 80,
            f"ch_setpoint={result.get('r9_ch_setpoint')!r}",
        )
        ctx.check(
            "9-byte 3EF0 max_rel_modulation=0.5 (byte 8, hex_to_percent(0x64))",
            result.get("r9_max_rel_modulation") == 0.5,
            f"max_rel_modulation={result.get('r9_max_rel_modulation')!r}",
        )
        ctx.check(
            "9-byte 3EF0 modulation_level=1.0 (byte 1, shared with 6-byte)",
            result.get("r9_modulation_level") == 1.0,
            f"modulation_level={result.get('r9_modulation_level')!r}",
        )

        # 6-byte checks
        r6_keys = result.get("r6_keys", [])
        ctx.check(
            "6-byte 3EF0 decoded with modulation_level (byte 1)",
            "modulation_level" in r6_keys,
            f"keys={r6_keys[:10]}",
        )
        ctx.check(
            "6-byte 3EF0 does NOT have ch_setpoint (no bytes 6-8)",
            result.get("r6_has_ch_setpoint") is False,
            f"ch_setpoint={result.get('r6_has_ch_setpoint')!r}",
        )

        # --- Check for parser errors in the HA log ---
        error_lines = grep_ha_log(
            "parser.*3EF0.*AssertionError|decoder.*3EF0.*AssertionError",
            since_lines=200,
        )

        ctx.check(
            "No AssertionError from 3EF0 parser (9-byte and 6-byte)",
            len(error_lines) == 0,
            f"errors={len(error_lines)}",
        )
