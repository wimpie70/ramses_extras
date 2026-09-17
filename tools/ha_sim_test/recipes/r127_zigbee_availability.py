"""Recipe R127: Zigbee device availability tracking.

Verifies the Zigbee transport's online/offline tracking inside the
ha-sim container (dev ``ramses_tx`` is mounted; no ZHA is present, so
all device objects are mocked):

- ``_mark_device_offline`` disconnects the pool child without closing
  the transport (monitor keeps running).
- ``_check_online_health``: gateway loss, ZHA unavailable flag, and
  stale ``last_seen`` + failed ping all mark the child offline; fresh
  traffic or a successful ping keep it online.
- ``_try_reconnect``: fresh ``last_seen`` or a successful ping
  re-attaches and reconnects the pool child; attach failures keep it
  offline.
- ``subscribe_device_offline`` turns ZHA's ``device_offline`` event
  into a child disconnect.
- Pool-level contract: ``connection_lost`` excludes the child from
  routing; ``connection_made`` after recovery restores it.
"""

from __future__ import annotations

from ..base import Recipe, RecipeContext
from ..helpers import docker_exec_python


class R127ZigbeeAvailability(Recipe):
    id = "R127"
    seq = 1270
    title = "Zigbee device availability tracking (offline/reconnect)"
    tags = ("pooled", "multi-hgi", "phase3", "zigbee", "availability")

    async def run(self, ctx: RecipeContext) -> None:
        """Verify Zigbee availability tracking and pool reconnect."""
        ctx.log_section("Recipe 127: Zigbee availability tracking")

        result = docker_exec_python(
            """
import asyncio
import json
import time
from unittest.mock import AsyncMock, MagicMock, patch

from ramses_tx.transport.base import TransportConfig
from ramses_tx.transport.factory import pooled_transport_factory
from ramses_tx.transport.pooled import (
    PooledTransport,
    _ChildProtocolProxy,
)
from ramses_tx.transport.zigbee.transport import ZigbeeTransport
from ramses_tx.typing import DeviceIdT

results = []

def check(name, condition, detail=""):
    status = "PASS" if condition else "FAIL"
    results.append({"name": name, "status": status, "detail": detail})


C6_IEEE = "10:bd:a3:ff:fe:a7:e0:dc"
ZIGBEE_URL = f"zigbee://{C6_IEEE}/0xfc00/0x0000/10/0xfc01/0x0000/10"
C6_HGI = "18:254172"


def make_zigbee_transport(url, protocol):
    \"\"\"ZigbeeTransport with _async_init suppressed (mock loop).\"\"\"
    mock_loop = MagicMock(spec=asyncio.AbstractEventLoop)

    def _close_coro(coro, **_kw):
        if hasattr(coro, "close"):
            coro.close()
        return MagicMock()

    mock_loop.create_task.side_effect = _close_coro
    t = ZigbeeTransport(
        url, protocol, config=TransportConfig(), loop=mock_loop
    )
    t._loop.create_task = MagicMock(side_effect=_close_coro)
    return t


def make_hass_with_gateway(device):
    hass = MagicMock()
    zha_data = MagicMock()
    gateway = MagicMock()
    # resolve_device() may look up an EUI64-converted IEEE (zigpy is
    # present in the sim container) — route the lookup through the
    # application_controller path so the key type does not matter.
    gateway.devices = {}
    controller = MagicMock()
    controller.devices.get = lambda _k: device
    gateway.application_controller = controller
    zha_data.gateway_proxy.gateway = gateway
    hass.data = {"zha": zha_data}
    return hass, gateway


def make_mock_protocol():
    proto = MagicMock()
    proto.packet_received = MagicMock()
    proto.connection_lost = MagicMock()
    proto.send_cmd = AsyncMock(return_value=None)
    proto.set_regex_rules = MagicMock()
    return proto


async def run_tests():
    proto = make_mock_protocol()

    # --------------------------------------------------------------
    # Setup: pool with zigbee child (fails: no ZHA) + callback child
    # --------------------------------------------------------------
    with patch.object(
        PooledTransport, "_wait_for_any_connection", new_callable=AsyncMock
    ):
        pool = await pooled_transport_factory(
            proto,
            config=TransportConfig(),
            port_names=[ZIGBEE_URL],
            callback_port_names=["mqtt_ha://18:001111"],
            accepted_hgis={"18:001111", C6_HGI},
        )

    child0 = pool._children[0]
    check("zigbee child disconnected at startup (no ZHA)",
          not child0.is_connected)

    # Wire a real ZigbeeTransport to the child-0 proxy on the real loop
    proxy = _ChildProtocolProxy(pool, 0)
    t = make_zigbee_transport(ZIGBEE_URL, proxy)
    t._loop = asyncio.get_event_loop()
    t._protocol = proxy

    device = MagicMock()
    device.available = True
    device.on_network = True
    device.last_seen = time.time()
    hass, gateway = make_hass_with_gateway(device)
    t._hass = hass
    t._device = device
    t._zha_gateway = gateway

    # --------------------------------------------------------------
    # Test 1: connection_made marks the pool child connected
    # --------------------------------------------------------------
    t._device_online = True
    t._make_connection(gateway_id=DeviceIdT(C6_HGI))
    await asyncio.sleep(0.05)
    check("child connected via connection_made",
          child0.is_connected and child0.hgi_id == C6_HGI,
          f"hgi={child0.hgi_id} connected={child0.is_connected}")
    check("child sendable while online", child0.is_sendable)

    # --------------------------------------------------------------
    # Test 2: _mark_device_offline disconnects the child
    # --------------------------------------------------------------
    t._mark_device_offline("simulated device offline")
    await asyncio.sleep(0.05)
    check("child disconnected after device offline",
          not child0.is_connected)
    check("child excluded from routing while offline",
          not child0.is_sendable)

    # --------------------------------------------------------------
    # Test 3: health check — fresh traffic keeps it online
    # --------------------------------------------------------------
    t._device_online = True  # pretend still online for the check
    device.last_seen = time.time()
    await t._check_online_health()
    check("fresh last_seen stays online", t._device_online)

    # --------------------------------------------------------------
    # Test 4: health check — gateway gone marks offline
    # --------------------------------------------------------------
    t._device_online = True
    hass.data = {}
    await t._check_online_health()
    check("missing gateway marks offline", not t._device_online)
    hass.data = {"zha": MagicMock()}  # restore for later tests
    hass.data["zha"].gateway_proxy.gateway = gateway

    # --------------------------------------------------------------
    # Test 5: stale + failed ping marks offline; ping ok stays online
    # --------------------------------------------------------------
    t._device_online = True
    device.last_seen = time.time() - 9999
    t._connection_mgr.ping_device = AsyncMock(return_value=True)
    await t._check_online_health()
    check("stale but ping ok stays online", t._device_online)

    t._connection_mgr.ping_device = AsyncMock(return_value=False)
    await t._check_online_health()
    check("stale + ping fail marks offline", not t._device_online)

    # --------------------------------------------------------------
    # Test 6: ZHA unavailable flag marks offline (no fresh traffic)
    # --------------------------------------------------------------
    t._device_online = True
    device.available = False
    device.last_seen = time.time() - 9999
    await t._check_online_health()
    check("ZHA unavailable flag marks offline", not t._device_online)
    device.available = True

    # --------------------------------------------------------------
    # Test 7: reconnect — fresh last_seen re-attaches + connection_made
    # --------------------------------------------------------------
    t._attach_clusters = MagicMock()
    t._bind_and_configure = AsyncMock()
    device.last_seen = time.time()  # device came back
    await t._try_reconnect()
    await asyncio.sleep(0.05)
    check("reconnect re-attaches clusters",
          t._attach_clusters.called)
    check("child reconnected after recovery",
          child0.is_connected and child0.is_sendable,
          f"connected={child0.is_connected} sendable={child0.is_sendable}")

    # --------------------------------------------------------------
    # Test 8: reconnect refused while device still dead
    # --------------------------------------------------------------
    t._device_online = False
    child0.mark_disconnected()
    device.last_seen = time.time() - 9999
    t._connection_mgr.ping_device = AsyncMock(return_value=False)
    await t._try_reconnect()
    check("dead device does not reconnect", not child0.is_connected)

    # --------------------------------------------------------------
    # Test 9: attach failure keeps child offline
    # --------------------------------------------------------------
    t._device_online = False
    device.last_seen = time.time()
    t._attach_clusters = MagicMock(
        side_effect=Exception("cluster gone")
    )
    await t._try_reconnect()
    check("attach failure stays offline", not child0.is_connected)

    # --------------------------------------------------------------
    # Test 10: device_offline event disconnects the child
    # --------------------------------------------------------------
    t._attach_clusters = MagicMock()  # restore for reconnect
    device.last_seen = time.time()
    await t._try_reconnect()
    await asyncio.sleep(0.05)
    check("reconnected for event test", child0.is_connected)

    captured = []
    device.on_event = lambda _ev, cb: captured.append(cb) or MagicMock()
    t._availability_unsub = t._connection_mgr.subscribe_device_offline(
        t._handle_device_offline_event
    )
    check("zha_event listener registered", len(captured) == 1)

    offline_event = MagicMock()
    offline_event.data = {"device_event_type": "device_offline"}
    captured[0](offline_event)
    await asyncio.sleep(0.05)
    check("device_offline event disconnects child",
          not child0.is_connected and not t._device_online)

    other_event = MagicMock()
    other_event.data = {"device_event_type": "zha_trigger"}
    t._device_online = True  # reset to check the filter
    captured[0](other_event)
    await asyncio.sleep(0.05)
    check("non-offline events ignored", t._device_online)

    print(json.dumps({
        "passed": sum(1 for r in results if r["status"] == "PASS"),
        "failed": sum(1 for r in results if r["status"] == "FAIL"),
        "results": results,
    }))


asyncio.run(run_tests())
""",
            timeout=120,
        )

        if "error" in result:
            ctx.check("Recipe 127 executed", False, f"error: {result['error']}")
            return

        passed = result.get("passed", 0)
        failed = result.get("failed", 0)
        checks = result.get("results", [])

        for chk in checks:
            ctx.check(chk["name"], chk["status"] == "PASS", chk["detail"])

        ctx.check(
            "All Zigbee availability checks passed",
            failed == 0,
            f"{passed} passed, {failed} failed",
        )
