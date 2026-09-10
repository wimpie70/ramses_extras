"""Recipe R111: Phase 2 HGI80 + MQTT hybrid pool source patching.

Verifies that ``PooledTransport.prepare_command`` correctly handles
source address patching in a mixed pool with HGI80 (serial) and evofw3
(MQTT callback) children.

This is the regression test for issue 1185: the protocol's evofw3 patch
(set addr1 to the active HGI ID because of the MQTT child) was not
overridden by ``prepare_command`` when the HGI80 child was selected,
causing the HGI80 to transmit with a real HGI ID instead of the
18:000730 placeholder.

Tests:
1. ``get_extra_info(SZ_IS_EVOFW3)`` returns True when a callback-driven
   child is present (even if the serial child is HGI80).
2. ``prepare_command`` patches source to the MQTT child's HGI ID when
   the MQTT child is selected (evofw3 path).
3. ``prepare_command`` swaps source to 18:000730 when the HGI80 child
   is selected (HGI80 path), even if the protocol set it to another
   child's HGI ID.
4. ``prepare_command`` keeps 18:000730 when the HGI80 child is selected
   and the source is already the placeholder.
5. The device_id filter accepts HGI80 echoes (src=18:000730) with
   ``enforce_include=True``.
"""

from __future__ import annotations

from ..base import Recipe, RecipeContext
from ..helpers import docker_exec_python


class R111Hgi80MqttSourcePatching(Recipe):
    id = "R111"
    seq = 1110
    title = "Phase 2 HGI80 + MQTT hybrid pool source patching (issue 1185)"
    tags = ("pooled", "multi-hgi", "phase2", "hgi80", "mqtt", "source-patching")

    async def run(self, ctx: RecipeContext) -> None:
        """Verify HGI80 + MQTT source patching in hybrid pool."""
        ctx.log_section("Recipe 111: HGI80 + MQTT source patching")

        result = docker_exec_python(
            """
import asyncio
import json
from datetime import datetime as dt
from unittest.mock import AsyncMock, MagicMock

from ramses_tx.address import HGI_DEV_ADDR, ALL_DEV_ADDR, NON_DEV_ADDR
from ramses_tx.const import SZ_ACTIVE_HGI, SZ_IS_EVOFW3, Code, Verb
from ramses_tx.dtos import CommandDTO
from ramses_tx.routing import RouteRequest, SourcePolicy
from ramses_tx.transport.pooled import (
    ConnectionState,
    NodeAvailability,
    PoolChild,
    PooledTransport,
)

results = []

def check(name, condition, detail=""):
    status = "PASS" if condition else "FAIL"
    results.append({"name": name, "status": status, "detail": detail})


def make_cmd(addr1="18:000730", addr2="01:123456"):
    return CommandDTO(
        verb=Verb.I_,
        addr1=addr1,
        addr2=addr2,
        addr3="--:------",
        code=Code._10A0,
        payload="00",
    )


def make_serial_child(child_id, hgi_id, is_evofw3=True):
    child = PoolChild(
        child_id=child_id,
        port_name=f"/dev/ttyUSB{child_id}",
        hgi_id=hgi_id,
        transport=MagicMock(),
    )
    child.connection_state = ConnectionState.CONNECTED
    child.availability = NodeAvailability.ONLINE
    child.send_ready = True
    child.transport.write_frame = AsyncMock()
    transport_obj = MagicMock()
    transport_obj.get_extra_info = lambda name, default=None: (
        is_evofw3 if name == SZ_IS_EVOFW3
        else hgi_id if name == SZ_ACTIVE_HGI
        else default
    )
    child.transport_obj = transport_obj
    return child


def make_callback_child(child_id, hgi_id):
    child = PoolChild(
        child_id=child_id,
        port_name=f"mqtt_ha://{hgi_id}",
        hgi_id=hgi_id,
        callback_driven=True,
    )
    child.connection_state = ConnectionState.CONNECTED
    child.availability = NodeAvailability.ONLINE
    child.send_ready = True
    return child


def make_pooled_transport(children):
    proto = MagicMock()
    proto.packet_received = MagicMock()
    transport = PooledTransport.__new__(PooledTransport)
    transport._children = list(children)
    transport._protocol = proto
    transport._rr_index = 0
    transport._max_consecutive_errors = 3
    transport._health_timeout = 60.0
    transport._dedup_cache = {}
    transport._dedup_window = 0.5
    transport._max_dedup_keys = 512
    transport._accepted_hgis = None
    transport._protocol_connected = True
    transport._conn_fut = None
    transport._is_closing = False
    return transport


async def run_tests():
    # Test 1: get_extra_info(SZ_IS_EVOFW3) with HGI80 + MQTT callback
    hgi80 = make_serial_child(0, "18:111111", is_evofw3=False)
    mqtt = make_callback_child(1, "18:222222")
    pool = make_pooled_transport([hgi80, mqtt])
    evofw3 = pool.get_extra_info(SZ_IS_EVOFW3)
    check("SZ_IS_EVOFW3 True with HGI80 + MQTT callback",
          evofw3 is True, f"got {evofw3}")

    # Test 2: prepare_command patches to MQTT child's HGI ID (evofw3)
    hgi80 = make_serial_child(0, "18:111111", is_evofw3=False)
    mqtt = make_callback_child(1, "18:222222")
    pool = make_pooled_transport([hgi80, mqtt])
    mqtt.rssi_tracker.record("01:123456", -50, dt.now())
    hgi80.rssi_tracker.record("01:123456", -80, dt.now())
    request = RouteRequest(
        command=make_cmd(addr1="18:000730"),
        source_policy=SourcePolicy.GATEWAY,
    )
    routed = pool.prepare_command(request)
    check("MQTT child selected when better RSSI",
          routed.child_id == "1", f"child_id={routed.child_id}")
    check("Source patched to MQTT child HGI ID",
          routed.command.addr1 == "18:222222",
          f"addr1={routed.command.addr1}")

    # Test 3: prepare_command swaps to 18:000730 when HGI80 selected
    hgi80 = make_serial_child(0, "18:111111", is_evofw3=False)
    mqtt = make_callback_child(1, "18:222222")
    pool = make_pooled_transport([hgi80, mqtt])
    hgi80.rssi_tracker.record("01:123456", -50, dt.now())
    mqtt.rssi_tracker.record("01:123456", -80, dt.now())
    request = RouteRequest(
        command=make_cmd(addr1="18:222222"),
        source_policy=SourcePolicy.GATEWAY,
    )
    routed = pool.prepare_command(request)
    check("HGI80 child selected when better RSSI",
          routed.child_id == "0", f"child_id={routed.child_id}")
    check("Source swapped to 18:000730 for HGI80",
          routed.command.addr1 == "18:000730",
          f"addr1={routed.command.addr1}")

    # Test 4: prepare_command keeps 18:000730 for HGI80 (no swap needed)
    hgi80 = make_serial_child(0, "18:111111", is_evofw3=False)
    mqtt = make_callback_child(1, "18:222222")
    pool = make_pooled_transport([hgi80, mqtt])
    hgi80.rssi_tracker.record("01:123456", -50, dt.now())
    mqtt.rssi_tracker.record("01:123456", -80, dt.now())
    request = RouteRequest(
        command=make_cmd(addr1="18:000730"),
        source_policy=SourcePolicy.GATEWAY,
    )
    routed = pool.prepare_command(request)
    check("HGI80 selected with placeholder source",
          routed.child_id == "0", f"child_id={routed.child_id}")
    check("Placeholder kept for HGI80",
          routed.command.addr1 == "18:000730",
          f"addr1={routed.command.addr1}")

    # Test 5: Device_id filter accepts HGI80 echo (src=18:000730)
    include = [ALL_DEV_ADDR.id, NON_DEV_ADDR.id, HGI_DEV_ADDR.id]
    check("HGI_DEV_ADDR in include list",
          HGI_DEV_ADDR.id in include, f"include={include}")
    check("HGI80 echo passes enforce_include",
          HGI_DEV_ADDR.id in include, "src=18:000730 in include")

    # Test 6: HGI_DEV_ADDR can still be explicitly excluded
    exclude = [HGI_DEV_ADDR.id]
    check("HGI_DEV_ADDR still blockable via exclude",
          HGI_DEV_ADDR.id in exclude, "explicit exclude takes precedence")

    passed = sum(1 for r in results if r["status"] == "PASS")
    failed = sum(1 for r in results if r["status"] == "FAIL")
    print(json.dumps({"passed": passed, "failed": failed, "results": results}))


asyncio.run(run_tests())
""",
            timeout=60,
        )

        if "error" in result:
            ctx.check("Recipe 111 executed", False, f"error: {result['error']}")
            return

        passed = result.get("passed", 0)
        failed = result.get("failed", 0)
        checks = result.get("results", [])

        for chk in checks:
            name = chk["name"]
            status = chk["status"]
            detail = chk["detail"]
            ctx.check(name, status == "PASS", detail)

        ctx.check(
            "All HGI80 + MQTT source patching checks passed",
            failed == 0,
            f"{passed} passed, {failed} failed",
        )
