"""Recipe R126: Phase 3 Zigbee pool — identity derivation and failure isolation.

Verifies the Phase 3 Zigbee transport contract inside the ha-sim
container (which has the dev ``ramses_tx`` and ``zigpy``, but no ZHA
instance):

- ``_hgi_id_from_ieee`` derives the ramses_esp gateway ID from a
  standard EUI-64 (MAC + ``ff:fe``) IEEE address, using vectors
  verified against real hardware.
- ``ZigbeeTransport._resolve_hgi_id`` precedence: explicit
  ``configured_hgi_id`` > IEEE-derived > ``18:000730`` sentinel.
- The Zigbee IEEE address is never used as the RAMSES HGI ID.
- ``pooled_transport_factory`` with a ``zigbee://`` port on a host
  without ZHA fails that child quickly (not after the 60s Zigbee
  timeout) and the pool continues with the remaining callback
  children — failure isolation.
"""

from __future__ import annotations

from ..base import Recipe, RecipeContext
from ..helpers import docker_exec_python


class R126Phase3ZigbeePool(Recipe):
    id = "R126"
    seq = 1260
    title = "Phase 3 Zigbee pool identity + failure isolation"
    tags = ("pooled", "multi-hgi", "phase3", "zigbee", "transport")

    async def run(self, ctx: RecipeContext) -> None:
        """Verify Zigbee identity derivation and pool failure isolation."""
        ctx.log_section("Recipe 126: Phase 3 Zigbee pool")

        result = docker_exec_python(
            """
import asyncio
import json
import time
from unittest.mock import AsyncMock, MagicMock, patch

from ramses_tx.const import SZ_ACTIVE_HGI
from ramses_tx.address import HGI_DEV_ADDR
from ramses_tx.transport.base import TransportConfig
from ramses_tx.transport.factory import pooled_transport_factory
from ramses_tx.transport.pooled import PooledTransport
from ramses_tx.transport.zigbee.transport import (
    ZigbeeTransport,
    _hgi_id_from_ieee,
)

results = []

def check(name, condition, detail=""):
    status = "PASS" if condition else "FAIL"
    results.append({"name": name, "status": status, "detail": detail})


C6_IEEE = "10:bd:a3:ff:fe:a7:e0:dc"
ZIGBEE_URL = (
    f"zigbee://{C6_IEEE}/0xfc00/0x0000/10/0xfc01/0x0000/10"
)


def make_zigbee_transport(url, configured_hgi_id=None):
    \"\"\"Construct a ZigbeeTransport with _async_init suppressed.\"\"\"
    mock_loop = MagicMock(spec=asyncio.AbstractEventLoop)

    def _close_coro(coro, **_kw):
        if hasattr(coro, "close"):
            coro.close()
        return MagicMock()

    mock_loop.create_task.side_effect = _close_coro
    t = ZigbeeTransport(
        url,
        MagicMock(),
        config=TransportConfig(configured_hgi_id=configured_hgi_id),
        loop=mock_loop,
    )
    t._loop.create_task = MagicMock(side_effect=_close_coro)
    return t


def make_mock_protocol():
    proto = MagicMock()
    proto.packet_received = MagicMock()
    proto.connection_lost = MagicMock()
    proto.send_cmd = AsyncMock(return_value=None)
    proto.set_regex_rules = MagicMock()
    return proto


async def run_tests():
    # ------------------------------------------------------------------
    # Test 1: _hgi_id_from_ieee vectors (verified on real hardware)
    # ------------------------------------------------------------------
    check("C6 IEEE derives 18:254172",
          _hgi_id_from_ieee(C6_IEEE) == "18:254172",
          f"got {_hgi_id_from_ieee(C6_IEEE)}")
    check("EUI-64 expansion of MAC cc:ba:97:09:fc:bc derives 18:130236",
          _hgi_id_from_ieee("cc:ba:97:ff:fe:09:fc:bc") == "18:130236")
    check("EUI-64 expansion of MAC cc:ba:97:0a:47:f0 derives 18:149488",
          _hgi_id_from_ieee("cc:ba:97:ff:fe:0a:47:f0") == "18:149488")

    # ------------------------------------------------------------------
    # Test 2: non-derivable / malformed IEEE returns None
    # ------------------------------------------------------------------
    check("non-ff:fe IEEE returns None",
          _hgi_id_from_ieee("00:11:22:33:44:55:66:77") is None)
    check("6-octet MAC returns None",
          _hgi_id_from_ieee("10:bd:a3:a7:e0:dc") is None)
    check("non-hex IEEE returns None",
          _hgi_id_from_ieee("zz:bd:a3:ff:fe:a7:e0:dc") is None)

    # ------------------------------------------------------------------
    # Test 3: _resolve_hgi_id precedence
    # ------------------------------------------------------------------
    t_cfg = make_zigbee_transport(ZIGBEE_URL, configured_hgi_id="18:099999")
    check("configured_hgi_id wins over derivation",
          t_cfg._resolve_hgi_id() == "18:099999",
          f"got {t_cfg._resolve_hgi_id()}")

    t_dev = make_zigbee_transport(ZIGBEE_URL)
    check("derived HGI when not configured",
          t_dev._resolve_hgi_id() == "18:254172",
          f"got {t_dev._resolve_hgi_id()}")

    t_none = make_zigbee_transport(
        "zigbee://00:11:22:33:44:55:66:77/0xfc00/0x0000/10/0xfc01/0x0000/10"
    )
    check("non-derivable IEEE falls back to sentinel",
          t_none._resolve_hgi_id() == HGI_DEV_ADDR.id,
          f"got {t_none._resolve_hgi_id()}")

    # ------------------------------------------------------------------
    # Test 4: IEEE is never used as the RAMSES HGI ID
    # ------------------------------------------------------------------
    for url in (ZIGBEE_URL,
                "zigbee://00:11:22:33:44:55:66:77/0xfc00/0x0000/10/"
                "0xfc01/0x0000/10"):
        t = make_zigbee_transport(url)
        hgi = t._resolve_hgi_id()
        check(f"IEEE never becomes HGI ID ({url[9:27]}...)",
              hgi != t._ieee and hgi.startswith("18:"),
              f"resolved={hgi}")

    # ------------------------------------------------------------------
    # Test 5: zigbee:// child fails fast without ZHA, pool survives
    # ------------------------------------------------------------------
    proto = make_mock_protocol()
    start = time.monotonic()
    with patch.object(
        PooledTransport, "_wait_for_any_connection", new_callable=AsyncMock
    ):
        pool = await pooled_transport_factory(
            proto,
            config=TransportConfig(),  # no app_context/hass -> no ZHA
            port_names=[ZIGBEE_URL],
            callback_port_names=["mqtt_ha://18:001111"],
            accepted_hgis={"18:001111"},
        )
    elapsed = time.monotonic() - start
    check("pool created despite zigbee child failure",
          len(pool._children) == 2,
          f"children={len(pool._children)}")
    check("zigbee child failed fast (not 60s timeout)",
          elapsed < 20,
          f"elapsed={elapsed:.1f}s")
    check("zigbee child not connected",
          not pool._children[0].is_connected)
    check("zigbee child not sendable",
          not pool._children[0].is_sendable)
    # callback_driven is set later by the bridge adapter; at factory
    # time the callback slot is just a reserved child with no transport.
    check("callback child slot reserved",
          pool._children[1].transport is None
          and pool._children[1].port_name == "mqtt_ha://18:001111",
          f"port_name={pool._children[1].port_name}")

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
            ctx.check("Recipe 126 executed", False, f"error: {result['error']}")
            return

        passed = result.get("passed", 0)
        failed = result.get("failed", 0)
        checks = result.get("results", [])

        for chk in checks:
            ctx.check(chk["name"], chk["status"] == "PASS", chk["detail"])

        ctx.check(
            "All Phase 3 Zigbee pool checks passed",
            failed == 0,
            f"{passed} passed, {failed} failed",
        )
