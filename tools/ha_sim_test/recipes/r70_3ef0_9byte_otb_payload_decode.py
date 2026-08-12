"""Recipe R70: 3EF0 9-byte OTB payload decode (regression guard for PR 1031)."""

from __future__ import annotations

import ast
import json

from ..base import Recipe, RecipeContext
from ..const import CTL
from ..helpers import (
    call_service,
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
        # This recipe injects both a 9-byte and a 6-byte 3EF0 I packet from
        # the CTL (which is in the known_list) and verifies:
        #   1. The 9-byte payload decodes with ch_enabled, ch_setpoint, and
        #      max_rel_modulation fields (the bytes 4-8 that PR 1031 dropped).
        #   2. The 6-byte payload decodes with modulation_level and flags
        #      (the basic fields shared with the 9-byte variant).
        #   3. No parser AssertionError or ERROR log for either packet.
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

        # Check log for the 9-byte decoded payload
        log_9byte = grep_ha_log("3EF0.*009.*00C8100000FF035064")
        # Also check the event handler log which shows the decoded payload dict
        event_9byte = grep_ha_log(
            "ramses_cc_regex_match.*3EF0.*ch_enabled.*ch_setpoint.*max_rel_modulation"
        )

        ctx.check(
            "9-byte 3EF0 packet received by protocol layer",
            len(log_9byte) > 0,
            f"log_lines={len(log_9byte)}",
        )

        # Extract the decoded payload from the event log
        decoded_9byte: dict[str, object] = {}
        for line in event_9byte:
            if "'ch_setpoint'" in line:
                try:
                    payload_str = line.split("'payload': ", 1)[1]
                    payload_str = payload_str.split(", 'packet'")[0]
                    decoded_9byte = ast.literal_eval(payload_str)
                    break
                except IndexError, SyntaxError:
                    continue

        print(f"  decoded 9-byte payload: {json.dumps(decoded_9byte)[:200]}")

        ctx.check(
            "9-byte 3EF0 decoded with ch_enabled field (bytes 6-8 not dropped)",
            "ch_enabled" in decoded_9byte,
            f"keys={list(decoded_9byte.keys())[:10]}",
        )
        ctx.check(
            "9-byte 3EF0 ch_enabled=True (bit 0 of byte 6)",
            decoded_9byte.get("ch_enabled") is True,
            f"ch_enabled={decoded_9byte.get('ch_enabled')!r}",
        )
        ctx.check(
            "9-byte 3EF0 ch_setpoint=80 (byte 7)",
            decoded_9byte.get("ch_setpoint") == 80,
            f"ch_setpoint={decoded_9byte.get('ch_setpoint')!r}",
        )
        ctx.check(
            "9-byte 3EF0 max_rel_modulation=0.5 (byte 8, hex_to_percent(0x64))",
            decoded_9byte.get("max_rel_modulation") == 0.5,
            f"max_rel_modulation={decoded_9byte.get('max_rel_modulation')!r}",
        )
        ctx.check(
            "9-byte 3EF0 modulation_level=1.0 (byte 1, shared with 6-byte)",
            decoded_9byte.get("modulation_level") == 1.0,
            f"modulation_level={decoded_9byte.get('modulation_level')!r}",
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

        # Check log for the 6-byte decoded payload
        event_6byte = grep_ha_log(
            "ramses_cc_regex_match.*3EF0.*modulation_level.*ch_active"
        )

        decoded_6byte: dict[str, object] = {}
        for line in event_6byte:
            if "'ch_active'" in line and "00C8100000FF035064" not in line:
                try:
                    payload_str = line.split("'payload': ", 1)[1]
                    payload_str = payload_str.split(", 'packet'")[0]
                    decoded_6byte = ast.literal_eval(payload_str)
                    break
                except IndexError, SyntaxError:
                    continue

        print(f"  decoded 6-byte payload: {json.dumps(decoded_6byte)[:200]}")

        ctx.check(
            "6-byte 3EF0 decoded with modulation_level (byte 1)",
            "modulation_level" in decoded_6byte,
            f"keys={list(decoded_6byte.keys())[:10]}",
        )
        ctx.check(
            "6-byte 3EF0 does NOT have ch_setpoint (no bytes 6-8)",
            "ch_setpoint" not in decoded_6byte,
            f"ch_setpoint={decoded_6byte.get('ch_setpoint', 'absent')!r}",
        )

        # --- Check for parser errors (only in recent log lines to avoid
        # matching the giant storage dump at startup which contains "3EF0"
        # in packet data) ---
        error_lines = grep_ha_log(
            "parser.*3EF0.*AssertionError|decoder.*3EF0.*AssertionError",
            since_lines=200,
        )
        # The "unknown_3EF0" WARNING is expected (CTL doesn't normally send 3EF0)
        # but an AssertionError would indicate a parser regression.

        ctx.check(
            "No AssertionError from 3EF0 parser (9-byte and 6-byte)",
            len(error_lines) == 0,
            f"errors={len(error_lines)}",
        )
