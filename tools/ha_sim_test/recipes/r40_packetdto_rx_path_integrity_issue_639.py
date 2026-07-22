"""Recipe R40: PacketDTO RX path integrity (issue 639 rule 4).

Issue 639 rule 4: "No Decoding Callbacks".  ``ramses_tx`` must not parse or
decode the payload string.  The ``_PAYLOAD_DECODER_CB`` bridge must be
destroyed.  ``ramses_tx`` yields the raw hex string; ``ramses_rf`` decodes it.

This recipe verifies:
1. ``PacketDTO`` has only L1/L2 fields (no decoded payload).
2. A raw packet injected via the simulator flows through to entity state.
3. No ``_PAYLOAD_DECODER_CB`` bridge exists in the transport layer.

See: https://github.com/ramses-rf/ramses_rf/issues/639
"""

from __future__ import annotations

from ..base import Recipe, RecipeContext
from ..const import CTL
from ..helpers import (
    call_service,
    docker_exec_python,
    get_entities,
    ws_send,
)


class R40PacketDtoRxPathIntegrityIssue639(Recipe):
    id = "R40"
    seq = 410
    title = "PacketDTO RX path integrity (issue 639 rule 4)"

    async def run(self, ctx: RecipeContext) -> None:
        ctx.log_section("Recipe 40: PacketDTO RX path integrity (issue 639)")

        # 1. Verify PacketDTO has only L1/L2 fields (inside container)
        code = """
import dataclasses, json
try:
    from ramses_tx.dtos import PacketDTO
    fields = sorted(f.name for f in dataclasses.fields(PacketDTO))
    print(json.dumps({"fields": fields, "ok": True}))
except ImportError as e:
    print(json.dumps({"error": str(e), "ok": False}))
"""
        result = docker_exec_python(code)

        if not result.get("ok"):
            ctx.check(
                "PacketDTO importable from ramses_tx.dtos",
                False,
                result.get("error", "unknown"),
            )
            return

        ctx.check("PacketDTO importable from ramses_tx.dtos", True, "")

        field_names = set(result["fields"])

        # Allowed L1/L2 fields per issue 639
        allowed_fields = {
            "timestamp",
            "rssi",
            "verb",
            "seq",
            "addr1",
            "addr2",
            "addr3",
            "code",
            "length",
            "payload",
        }

        ctx.check(
            "PacketDTO has only L1/L2 fields",
            field_names == allowed_fields,
            f"extra: {field_names - allowed_fields}, "
            f"missing: {allowed_fields - field_names}",
        )

        # No decoded/structured payload fields
        forbidden_fields = {
            "decoded_payload",
            "parsed_payload",
            "device_type",
            "zone_idx",
            "temperature",
            "src",
            "dst",
        }
        found_forbidden = field_names & forbidden_fields
        ctx.check(
            "PacketDTO has no decoded payload fields",
            len(found_forbidden) == 0,
            f"found: {found_forbidden}",
        )

        # 2. Check that _PAYLOAD_DECODER_CB is not used in the transport
        code2 = """
import inspect, json
try:
    from ramses_tx.protocol import fsm
    src = inspect.getsource(fsm)
    has_cb = "_PAYLOAD_DECODER_CB" in src
    print(json.dumps({"has_decoder_cb": has_cb, "ok": True}))
except Exception as e:
    print(json.dumps({"error": str(e), "ok": False}))
"""
        result2 = docker_exec_python(code2)

        if result2.get("ok"):
            ctx.check(
                "protocol_fsm has no _PAYLOAD_DECODER_CB bridge",
                not result2.get("has_decoder_cb", True),
                "_PAYLOAD_DECODER_CB still referenced in protocol_fsm",
            )
        else:
            ctx.check(
                "protocol_fsm importable for inspection",
                False,
                result2.get("error", "unknown"),
            )

        # 3. Verify a raw 30C9 packet hydrates entity state via the RX path
        print("  Loading mixed profile for RX path test...")
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
        except RuntimeError as e:
            print(f"  Profile load failed: {e}")
        ctx.wait(15, "for ramses_cc reload")
        ctx.refresh_token()
        ctx.wait(5, "for ramses_cc to initialize")

        # Activate CTL
        try:
            await ws_send(
                ctx.token,
                {
                    "type": ("ramses_extras/device_simulator/activate_profile_device"),
                    "device_id": CTL,
                },
            )
        except RuntimeError:
            pass
        ctx.wait(10, "for CTL heartbeats")

        # Inject a 30C9 I packet from the zone-03 sensor (01:150003)
        #    payload: 03 + hex_for_temp(22.0)
        #    22.0°C = 0x0AC0 → "030AC0"
        print("  Injecting 30C9 I from 01:150003 (zone 03, 22.0°C)...")
        try:
            call_service(
                ctx.token,
                "ramses_extras",
                "device_simulator_inject_message",
                {
                    "source_id": "01:150003",
                    "code": "30C9",
                    "payload": "030AC0",
                    "verb": "I",
                },
            )
            print("    30C9 I injected")
        except RuntimeError as e:
            print(f"    Inject failed: {str(e)[:80]}")
        ctx.wait(5, "for 30C9 to process")

        # Force entity state update
        try:
            call_service(ctx.token, "ramses_cc", "force_update")
        except RuntimeError:
            pass
        ctx.wait(3, "for entity state write")

        # Check that a climate entity for zone 03 exists and has a temperature
        entities = get_entities(ctx.token)
        zone_climate = None
        for e in entities:
            if not e["entity_id"].startswith("climate."):
                continue
            attrs = e.get("attributes", {})
            if attrs.get("zone_idx") == "03":
                zone_climate = e
                break

        ctx.check(
            "climate entity for zone 03 exists after 30C9 RX",
            zone_climate is not None,
            "no climate entity with zone_idx=03",
        )

        if zone_climate:
            temp = zone_climate.get("attributes", {}).get("current_temperature")
            ctx.check(
                "zone 03 climate has current_temperature after 30C9 RX",
                temp is not None,
                f"current_temperature={temp}",
            )
