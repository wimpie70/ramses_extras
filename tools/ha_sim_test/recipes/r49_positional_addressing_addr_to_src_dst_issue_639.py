"""Recipe R49: Positional addressing — addr1/addr2/addr3 to src/dst (issue 639).

Issue 639 rule 2: "Positional Addressing Only".  DTOs use ``addr1``,
``addr2``, ``addr3`` (positional MAC addresses), not ``src`` or ``dst``.
Translating positional addresses to logical source/destination based on
verbs is an OSI Layer 7 domain responsibility that lives in ``ramses_rf``.

This recipe verifies that:
1. ``CommandDTO`` and ``PacketDTO`` use ``addr1/addr2/addr3`` (not src/dst).
2. The ``Packet`` parser correctly resolves positional addresses to
   logical src/dst based on the verb.

The RAMSES II positional addressing rules (verified against the packet
parser):

    I  broadcast:  addr1=src, addr2=--:------, addr3=src (same device)
    I  directed:   addr1=src, addr2=dst,      addr3=--:------
    RQ directed:   addr1=src, addr2=dst,      addr3=--:------
    RP directed:   addr1=dst, addr2=src,      addr3=--:------
    W  directed:   addr1=src, addr2=dst,      addr3=--:------

See: https://github.com/ramses-rf/ramses_rf/issues/639
"""

from __future__ import annotations

from ..base import Recipe, RecipeContext
from ..helpers import docker_exec_python


class R49PositionalAddressingAddrToSrcDstIssue639(Recipe):
    id = "R49"
    seq = 500
    title = "Positional addressing — addr1/addr2/addr3 to src/dst (issue 639)"

    async def run(self, ctx: RecipeContext) -> None:
        ctx.log_section(
            "Recipe 49: Positional addressing — addr to src/dst (issue 639)"
        )

        # Run the entire inspection inside the container
        code = """
import dataclasses, json

result = {"checks": [], "ok": True}

# 1. Check CommandDTO and PacketDTO field names
try:
    from ramses_tx.dtos import CommandDTO, PacketDTO

    cfields = {f.name for f in dataclasses.fields(CommandDTO)}
    pfields = {f.name for f in dataclasses.fields(PacketDTO)}

    result["command_dto_fields"] = sorted(cfields)
    result["packet_dto_fields"] = sorted(pfields)
    result["command_dto_has_addr"] = (
        "addr1" in cfields and "addr2" in cfields and "addr3" in cfields
        and "src" not in cfields and "dst" not in cfields
    )
    result["packet_dto_has_addr"] = (
        "addr1" in pfields and "addr2" in pfields and "addr3" in pfields
        and "src" not in pfields and "dst" not in pfields
    )
except ImportError as e:
    result["error"] = f"DTO import failed: {e}"
    result["ok"] = False
    print(json.dumps(result))
    raise SystemExit

# 2. Test Packet.from_dict with positional addresses
#    The frame format is: VER RSSI ADDR1 ADDR2 ADDR3 CODE LEN PAYLOAD
#    Verbs are space-padded to 2 chars: " I", " W", "RQ", "RP"
#    from_dict takes (dtm, {rssi, frame}) where frame excludes the RSSI
#    (it's prepended from the rssi field).
from ramses_tx import Packet

test_cases = [
    {
        "name": "I broadcast (sensor announces)",
        "frame": " I --- 01:150003 --:------ 01:150003 30C9 003 030AC0",
        "expected_src": "01:150003",
        "expected_dst": "01:150003",
    },
    {
        "name": "I directed (REM sends to FAN)",
        "frame": " I --- 37:168270 32:153289 --:------ 22F1 003 000307",
        "expected_src": "37:168270",
        "expected_dst": "32:153289",
    },
    {
        "name": "RQ directed (HGI asks CTL)",
        "frame": "RQ --- 18:001234 01:150000 --:------ 0002 001 00",
        "expected_src": "18:001234",
        "expected_dst": "01:150000",
    },
    {
        "name": "RP directed (CTL replies to HGI)",
        "frame": "RP --- 01:150000 18:001234 --:------ 0002 002 0000",
        "expected_src": "01:150000",
        "expected_dst": "18:001234",
    },
    {
        "name": "W directed (HGI writes to CTL)",
        "frame": " W --- 18:001234 01:150000 --:------ 2E04 008 00FFFFFFFFFFFF00",
        "expected_src": "18:001234",
        "expected_dst": "01:150000",
    },
]

for tc in test_cases:
    try:
        pkt = Packet.from_dict("2026-01-01T00:00:00", {
            "rssi": "000",
            "frame": tc["frame"],
        })
        src_id = pkt.src.id
        dst_id = pkt.dst.id

        result["checks"].append({
            "name": tc["name"],
            "src_ok": src_id == tc["expected_src"],
            "dst_ok": dst_id == tc["expected_dst"],
            "got_src": src_id,
            "got_dst": dst_id,
        })
    except Exception as e:
        result["checks"].append({
            "name": tc["name"],
            "error": f"{type(e).__name__}: {e}",
        })

print(json.dumps(result))
"""
        result = docker_exec_python(code, timeout=30)

        if not result.get("ok"):
            ctx.check(
                "DTO and Packet inspection runs",
                False,
                result.get("error", "unknown"),
            )
            return

        ctx.check("DTO and Packet inspection runs", True, "")

        # 1. Verify CommandDTO uses addr1/addr2/addr3
        ctx.check(
            "CommandDTO uses addr1/addr2/addr3 (not src/dst)",
            result.get("command_dto_has_addr", False),
            f"fields={result.get('command_dto_fields', [])}",
        )

        # 2. Verify PacketDTO uses addr1/addr2/addr3
        ctx.check(
            "PacketDTO uses addr1/addr2/addr3 (not src/dst)",
            result.get("packet_dto_has_addr", False),
            f"fields={result.get('packet_dto_fields', [])}",
        )

        # 3. Verify each test case
        for check in result.get("checks", []):
            name = check.get("name", "?")
            if "error" in check:
                ctx.check(
                    f"{name}: packet construction succeeds",
                    False,
                    check["error"],
                )
            else:
                ctx.check(
                    f"{name}: src correct",
                    check.get("src_ok", False),
                    f"got src={check.get('got_src')}",
                )
                ctx.check(
                    f"{name}: dst correct",
                    check.get("dst_ok", False),
                    f"got dst={check.get('got_dst')}",
                )
