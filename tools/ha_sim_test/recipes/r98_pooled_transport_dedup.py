"""Recipe R98: PooledTransport inbound deduplication.

Verifies that the :class:`PooledTransport` (Roadmap Item 9, PR 2)
correctly deduplicates packets arriving from multiple child transports
within the sliding time window, and forwards distinct packets without
loss.  This is a structural test that runs inside the ha-sim container
where the updated ``ramses_tx`` library is installed.

The ha-sim container uses a single MQTT transport, so this recipe
cannot test real multi-HGI pooling end-to-end.  Instead it creates
mock child transports and verifies the pool's dedup logic, outbound
round-robin routing, and connection lifecycle handling.
"""

from __future__ import annotations

from ..base import Recipe, RecipeContext
from ..helpers import docker_exec_python


class R98PooledTransportDedup(Recipe):
    id = "R98"
    seq = 980
    title = "PooledTransport inbound dedup & outbound routing"
    tags = ("pooled", "multi-hgi", "transport", "dedup")

    async def run(self, ctx: RecipeContext) -> None:
        """Verify PooledTransport dedup, routing, and lifecycle."""
        ctx.log_section("Recipe 98: PooledTransport dedup & routing")

        result = docker_exec_python(
            """
import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

from ramses_tx.const import Code, I_, SZ_ACTIVE_HGI
from ramses_tx.transport.base import TransportConfig
from ramses_tx.transport.pooled import PooledTransport, _ChildProtocolProxy


def make_packet(verb=I_, code=Code._30C9, src="01:123456",
                dst="18:000730", addr3="--:------", payload="00"):
    dto = MagicMock()
    dto.verb = verb
    dto.code = code
    dto.addr1 = src
    dto.addr2 = dst
    dto.addr3 = addr3
    dto.raw_payload = payload
    dto.rssi = "000"
    pkt = MagicMock()
    pkt._dto = dto
    return pkt


def make_mock_transport(hgi=None, connected=True):
    t = MagicMock()
    t.get_extra_info = lambda name, default=None: (
        hgi if name == SZ_ACTIVE_HGI else default
    )
    t.write_frame = AsyncMock()
    t.send_frame = AsyncMock()
    t.close = MagicMock()
    t.is_closing = False
    return t


def make_mock_protocol():
    proto = MagicMock()
    proto.packet_received = MagicMock()
    proto.connection_lost = MagicMock()
    proto.send_cmd = AsyncMock(return_value=None)
    proto.set_regex_rules = MagicMock()
    return proto


async def run_tests():
    results = {}

    # Test 1: Dedup — same packet from 2 children → 1 upstream
    proto = make_mock_protocol()
    t0 = make_mock_transport(hgi="18:001111")
    t1 = make_mock_transport(hgi="18:002222")
    pool = PooledTransport(
        proto, [t0, t1], config=TransportConfig(),
        dedup_window=1.0,
    )
    pool._child_connected = [True, True]
    pool._child_hgi = ["18:001111", "18:002222"]

    pkt = make_packet()
    pool._on_child_packet(0, pkt)
    pool._on_child_packet(1, pkt)  # duplicate
    await asyncio.sleep(0.01)

    results["dedup_forwarded_once"] = (
        proto.packet_received.call_count == 1
    )
    stats = pool.get_extra_info("pool_stats")
    results["dedup_count"] = stats["deduped"]

    # Test 2: Distinct packets → both forwarded
    proto2 = make_mock_protocol()
    pool2 = PooledTransport(
        proto2, [t0, t1], config=TransportConfig(),
    )
    pool2._child_connected = [True, True]
    pool2._child_hgi = ["18:001111", "18:002222"]

    pkt_a = make_packet(src="01:111111")
    pkt_b = make_packet(src="01:222222")
    pool2._on_child_packet(0, pkt_a)
    pool2._on_child_packet(1, pkt_b)
    await asyncio.sleep(0.01)

    results["distinct_both_forwarded"] = (
        proto2.packet_received.call_count == 2
    )

    # Test 3: Outbound routes to connected child only
    proto3 = make_mock_protocol()
    t3a = make_mock_transport(hgi="18:001111", connected=False)
    t3b = make_mock_transport(hgi="18:002222", connected=True)
    pool3 = PooledTransport(
        proto3, [t3a, t3b], config=TransportConfig(),
    )
    pool3._child_connected = [False, True]

    await pool3.write_frame(" 000 I --- 01:123456 18:000730 --:------ 30C9 000 00")
    results["outbound_skips_disconnected"] = (
        not t3a.write_frame.called
    )
    results["outbound_uses_connected"] = (
        t3b.write_frame.called
    )

    # Test 4: get_extra_info(SZ_ACTIVE_HGI) returns first connected
    proto4 = make_mock_protocol()
    pool4 = PooledTransport(
        proto4, [t0, t1], config=TransportConfig(),
    )
    pool4._child_connected = [True, True]
    pool4._child_hgi = ["18:001111", "18:002222"]
    results["extra_info_hgi"] = pool4.get_extra_info(SZ_ACTIVE_HGI)

    # Test 5: Close propagates to all children
    proto5 = make_mock_protocol()
    t5a = make_mock_transport(hgi="18:001111")
    t5b = make_mock_transport(hgi="18:002222")
    pool5 = PooledTransport(
        proto5, [t5a, t5b], config=TransportConfig(),
    )
    pool5.close()
    results["close_all_children"] = (
        t5a.close.called and t5b.close.called
    )
    results["close_is_closing"] = pool5.is_closing

    # Test 6: _ChildProtocolProxy routes to pool
    pool6 = MagicMock()
    proxy = _ChildProtocolProxy(pool6, 0)
    proxy.packet_received(make_packet())
    results["proxy_routes_packet"] = (
        pool6._on_child_packet.called
    )

    print(json.dumps(results))


asyncio.run(run_tests())
"""
        )

        ctx.check(
            "PooledTransport is importable",
            "error" not in result,
            f"result={result}",
        )
        if "error" in result:
            return

        ctx.check(
            "Duplicate packet from second child is deduped (1 forward)",
            result.get("dedup_forwarded_once") is True
            and result.get("dedup_count") == 1,
            f"result={result}",
        )
        ctx.check(
            "Distinct packets from different children are both forwarded",
            result.get("distinct_both_forwarded") is True,
            f"result={result}",
        )
        ctx.check(
            "Outbound write_frame skips disconnected children",
            result.get("outbound_skips_disconnected") is True,
            f"result={result}",
        )
        ctx.check(
            "Outbound write_frame uses connected child",
            result.get("outbound_uses_connected") is True,
            f"result={result}",
        )
        ctx.check(
            "get_extra_info(SZ_ACTIVE_HGI) returns first connected child's HGI",
            result.get("extra_info_hgi") == "18:001111",
            f"result={result}",
        )
        ctx.check(
            "close() propagates to all child transports",
            result.get("close_all_children") is True,
            f"result={result}",
        )
        ctx.check(
            "close() sets is_closing flag",
            result.get("close_is_closing") is True,
            f"result={result}",
        )
        ctx.check(
            "_ChildProtocolProxy routes packets to pool",
            result.get("proxy_routes_packet") is True,
            f"result={result}",
        )
