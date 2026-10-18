"""Recipe R156: PacketDTO/Packet raw_payload migration & CLASS_BY_SLUG (issue 1357).

Conditionally verifies:
- https://github.com/ramses-rf/ramses_rf/pull/1327 (item 2.1 of issue 1357:
  drop PR 10 transition raw-string fallbacks on ``PacketDTO.payload`` and
  ``Packet.payload``; migrate ``Message._format_frame``, ``Message.__eq__``,
  ``DiscoveryScan`` ``000C`` domain-id extraction, ``extract_context_value``
  ``3220`` data-ID slice, ``_BaseProtocol`` sync-cycle windowing, and
  ``PortTransport._packet_read`` ``PUZZ`` signature matching to
  ``raw_payload`` / ``PayloadBase``).
- https://github.com/ramses-rf/ramses_cc/pull/1366 (item 1.3 of issue 1357:
  drop the ``_CLASS_BY_SLUG`` ``try/except ImportError`` fallback in
  ``custom_components/ramses_cc/coordinator.py``).

If either PR is not yet installed in ``ha-sim``, its section is skipped
gracefully so the recipe passes both before and after merge.
"""

from __future__ import annotations

from ..base import Recipe, RecipeContext
from ..helpers import docker_exec_python


class R156RawPayloadAndClassBySlugIssue1357(Recipe):
    """Verify issue 1357 items 1.3 (ramses_cc) and 2.1 (ramses_rf)."""

    id = "R156"
    seq = 1560
    title = "PacketDTO/Packet raw_payload & CLASS_BY_SLUG (PR 1327 / PR 1366)"
    tags = ("packetdto", "payload", "discovery_scan", "pr_1327", "pr_1366")

    async def run(self, ctx: RecipeContext) -> None:
        """Run conditional PR 1327 and PR 1366 checks in ha-sim."""
        ctx.log_section(
            "Recipe 156: PacketDTO/Packet raw_payload & CLASS_BY_SLUG "
            "(PR 1327 / PR 1366)"
        )

        result = docker_exec_python(
            """
import json
import pathlib
from datetime import UTC, datetime as dt
from unittest.mock import MagicMock, patch

from ramses_rf.discovery_scan import DiscoveryScan, _extract_domain_id_from_000c
from ramses_rf.messages.base import Message
from ramses_rf.payloads.heating import Temperature2BPayload
from ramses_rf.routing import extract_context_value
from ramses_tx.const import SZ_ACTIVE_HGI, SZ_SIGNATURE, Code, Verb
from ramses_tx.dtos import PacketDTO
from ramses_tx.packet import Packet
from ramses_tx.transport.port import PortTransport

results = []


def check(name, condition, detail=""):
    status = "PASS" if condition else "FAIL"
    results.append({"name": name, "status": status, "detail": detail})


def test_ramses_rf_pr_1327():
    # PR 1327 drops PacketDTO.__post_init__ raw-string auto-population
    test_dtm = dt(2026, 10, 18, 12, 0, 0, tzinfo=UTC)
    probe = PacketDTO(
        timestamp=test_dtm,
        rssi="-45",
        verb=Verb.I_,
        seq="---",
        addr1="01:145038",
        addr2="--:------",
        addr3="01:145038",
        code=Code._30C9,
        length="003",
        raw_payload="0007D0",
    )
    if probe.payload is not None:
        return {"rf_skipped": True}

    # 1. Packet.from_raw_line leaves Packet.payload and PacketDTO.payload as None
    raw_frame = "045  I --- 01:145038 --:------ 01:145038 30C9 003 0007D0"
    pkt = Packet(test_dtm, raw_frame)
    dto = pkt.to_dto()
    check(
        "Packet.to_dto() keeps payload=None and raw_payload populated",
        dto.payload is None and dto.raw_payload == "0007D0" and pkt.payload is None,
        f"dto.payload={dto.payload!r} raw_payload={dto.raw_payload!r}",
    )

    # 2. Packet.payload setter accepts PayloadBase and preserves _frame raw_payload
    typed_payload = Temperature2BPayload.from_bytes(bytes.fromhex("0007D0"))
    pkt.payload = typed_payload
    check(
        "Packet.payload setter stores PayloadBase and preserves _frame hex",
        pkt.payload == typed_payload
        and pkt.raw_payload == "0007D0"
        and pkt._frame.endswith("30C9 003 0007D0"),
        f"_frame={pkt._frame!r}",
    )

    # 3. Packet(dto) sets _raw_line using raw_payload (not None)
    pkt_from_dto = Packet(probe)
    check(
        "Packet(PacketDTO) formats _raw_line with raw_payload",
        pkt_from_dto._frame.endswith("30C9 003 0007D0"),
        f"_frame={pkt_from_dto._frame!r}",
    )

    # 4. Message._format_frame and Message.__eq__ use raw_payload
    msg_a = Message(probe)
    probe_b = PacketDTO(
        timestamp=test_dtm,
        rssi="-45",
        verb=Verb.I_,
        seq="---",
        addr1="01:145038",
        addr2="--:------",
        addr3="01:145038",
        code=Code._30C9,
        length="003",
        raw_payload="000834",
    )
    msg_b = Message(probe_b)
    msg_a_copy = Message(probe)
    check(
        "Message.raw_frame uses raw_payload (not 'None')",
        msg_a.raw_frame.endswith("30C9 003 0007D0"),
        f"raw_frame={msg_a.raw_frame!r}",
    )
    check(
        "Message.__eq__ distinguishes different raw_payloads when dto.payload is None",
        msg_a == msg_a_copy and msg_a != msg_b,
    )

    # 5. extract_context_value preserves Code._3220 data_id slice when payload is None
    ctx_3220 = extract_context_value(
        None, raw_payload="0080190000", code=Code._3220
    )
    check(
        "extract_context_value extracts 3220 data_id from raw_payload (payload=None)",
        ctx_3220 == "19",
        f"ctx_3220={ctx_3220!r}",
    )

    # 6. DiscoveryScan extracts 000C authoritative domain_id from raw_payload
    gwy = MagicMock()
    gwy.device_registry.device_by_id = {}
    gwy._gwy_config.known_list = {}
    gwy._gwy_config.schema = {}
    gwy.hgi = None
    gwy._engine = None
    scanner = DiscoveryScan(gwy)
    dto_000c = PacketDTO(
        timestamp=test_dtm,
        rssi="-60",
        verb=Verb.RP,
        seq="---",
        addr1="01:145038",
        addr2="18:001234",
        addr3="--:------",
        code=Code._000C,
        length="006",
        raw_payload="000F003545C8",  # role 0F (APP) -> FC
    )
    scanner._process_packet(dto_000c)
    ctl_dev = scanner._devices.get("01:145038")
    check(
        "DiscoveryScan extracts 000C domain_id=FC when dto.payload is None",
        ctl_dev is not None
        and ctl_dev.domain_id == "FC"
        and ctl_dev.is_authoritative_domain is True
        and _extract_domain_id_from_000c("000F003545C8") == "FC"
        and _extract_domain_id_from_000c("000E003545C8") == "FA"
        and _extract_domain_id_from_000c("010E003545C8") == "F9",
        f"ctl_dev={ctl_dev}",
    )

    # 7. PortTransport._packet_read matches PUZZ signature against packet.raw_payload
    puzz_pkt = Packet(
        test_dtm, "000  I --- 18:001234 63:262142 --:------ 7FFF 005 0011223344"
    )
    dummy_self = PortTransport.__new__(PortTransport)
    dummy_self._init_fut = MagicMock()
    dummy_self._init_fut.done.return_value = False
    dummy_self._extra = {SZ_SIGNATURE: "0011223344"}
    with patch("ramses_tx.transport.base._FullTransport._packet_read"):
        PortTransport._packet_read(dummy_self, puzz_pkt)
    check(
        "PortTransport._packet_read resolves _init_fut via packet.raw_payload",
        dummy_self._extra.get(SZ_ACTIVE_HGI) == "18:001234"
        and dummy_self._init_fut.set_result.called,
    )

    return {"rf_skipped": False}


def test_ramses_cc_pr_1366():
    coord_path = pathlib.Path(
        "/config/custom_components/ramses_cc/coordinator.py"
    )
    if not coord_path.exists():
        return {"cc_skipped": True}
    src = coord_path.read_text(encoding="utf-8")
    if "_CLASS_BY_SLUG" in src:
        return {"cc_skipped": True}

    from custom_components.ramses_cc import coordinator as cc_coord
    from ramses_rf.devices import CLASS_BY_SLUG as rf_class_by_slug

    check(
        "ramses_cc.coordinator imports CLASS_BY_SLUG without _CLASS_BY_SLUG fallback",
        getattr(cc_coord, "CLASS_BY_SLUG", None) is rf_class_by_slug
        and "_CLASS_BY_SLUG" not in src,
    )
    return {"cc_skipped": False}


rf_info = test_ramses_rf_pr_1327()
cc_info = test_ramses_cc_pr_1366()
print(
    json.dumps(
        {
            "rf_skipped": rf_info["rf_skipped"],
            "cc_skipped": cc_info["cc_skipped"],
            "passed": sum(1 for r in results if r["status"] == "PASS"),
            "failed": sum(1 for r in results if r["status"] == "FAIL"),
            "results": results,
        }
    )
)
""",
            timeout=60,
        )

        if "error" in result:
            ctx.check("Recipe 156 executed", False, f"error: {result['error']}")
            return

        if result.get("rf_skipped"):
            ctx.check(
                "ramses_rf PR 1327 checks (skipped — not yet installed)",
                True,
            )
        if result.get("cc_skipped"):
            ctx.check(
                "ramses_cc PR 1366 checks (skipped — not yet installed)",
                True,
            )

        for chk in result.get("results", []):
            ctx.check(chk["name"], chk["status"] == "PASS", chk["detail"])
