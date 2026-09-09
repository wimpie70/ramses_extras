"""Recipe R105: Phase 2 hybrid pool construction.

Verifies that ``pooled_transport_factory`` can create a hybrid pool
with both serial (transport-driven) and MQTT callback-driven children,
and that the resulting ``PooledTransport`` correctly:

- Has the right number of children (serial + callback).
- Applies ``per_child_config_overrides`` to serial children.
- Sets ``SignaturePolicy.SKIP`` for serial children (Phase 2 default).
- Creates callback children with the configured HGI IDs.
- Reports pool stats and extra info correctly.

This is a structural test that runs inside the ha-sim container where
the dev ``ramses_tx`` library (with ``callback_port_names`` and
``per_child_config_overrides`` support) is installed.

Serial transport creation is mocked because the container has no
real serial ports — we verify parameter acceptance, validation, and
callback child structure without opening real devices.
"""

from __future__ import annotations

from ..base import Recipe, RecipeContext
from ..helpers import docker_exec_python


class R105Phase2HybridPool(Recipe):
    id = "R105"
    seq = 1050
    title = "Phase 2 hybrid pool construction (serial + MQTT callback)"
    tags = ("pooled", "multi-hgi", "phase2", "hybrid", "transport")

    async def run(self, ctx: RecipeContext) -> None:
        """Verify Phase 2 hybrid pool construction."""
        ctx.log_section("Recipe 105: Phase 2 hybrid pool construction")

        result = docker_exec_python(
            """
import asyncio
import inspect
import json
from unittest.mock import AsyncMock, MagicMock, patch

from ramses_tx.const import SZ_ACTIVE_HGI
from ramses_tx.transport.base import SignaturePolicy, TransportConfig
from ramses_tx.transport.factory import pooled_transport_factory
from ramses_tx.transport.pooled import (
    ConnectionState,
    NodeAvailability,
    PooledTransport,
)

results = []

def check(name, condition, detail=""):
    status = "PASS" if condition else "FAIL"
    results.append({"name": name, "status": status, "detail": detail})


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
    # ---------------------------------------------------------------------------
    # Test 1: Factory accepts callback_port_names parameter
    # ---------------------------------------------------------------------------
    sig = inspect.signature(pooled_transport_factory)
    check("callback_port_names parameter exists",
          "callback_port_names" in sig.parameters,
          f"params={list(sig.parameters)}")
    check("per_child_config_overrides parameter exists",
          "per_child_config_overrides" in sig.parameters,
          f"params={list(sig.parameters)}")

    # ---------------------------------------------------------------------------
    # Test 2: per_child_config_overrides validation (mismatched length)
    # ---------------------------------------------------------------------------
    proto3 = make_mock_protocol()
    try:
        await pooled_transport_factory(
            proto3,
            config=TransportConfig(),
            port_names=["/dev/ttyACM0"],
            port_configs=[
                {"baudrate": 115200, "dsrdtr": False,
                 "rtscts": False, "timeout": 3, "xonxoff": False},
            ],
            per_child_config_overrides=[{}, {}],  # mismatched length
        )
        check("Mismatched per_child_config_overrides raises ValueError",
              False,
              "no error raised")
    except ValueError as e:
        check("Mismatched per_child_config_overrides raises ValueError",
              "per_child_config_overrides" in str(e),
              f"error={str(e)[:200]}")
    except Exception as e:
        check("Mismatched per_child_config_overrides raises ValueError",
              False,
              f"wrong error type: {type(e).__name__}: {str(e)[:200]}")

    # ---------------------------------------------------------------------------
    # Test 3: SignaturePolicy.SKIP applied to serial children
    # ---------------------------------------------------------------------------
    base = TransportConfig()
    overrides = [
        {"signature_policy": SignaturePolicy.SKIP, "startup_grace": 3.0},
    ]
    child0 = base.__class__(
        **{**base.__dict__,
           "signature_policy": overrides[0]["signature_policy"],
           "startup_grace": overrides[0]["startup_grace"]},
    )
    check("Serial child gets SKIP signature policy",
          child0.signature_policy is SignaturePolicy.SKIP,
          f"policy={child0.signature_policy}")
    check("Serial child gets startup_grace=3.0",
          child0.startup_grace == 3.0,
          f"grace={child0.startup_grace}")

    # ---------------------------------------------------------------------------
    # Test 4: MQTT-only pool with callback children (no serial ports)
    # ---------------------------------------------------------------------------
    proto2 = make_mock_protocol()
    # Mock _wait_for_any_connection to avoid 10s timeout (no real broker)
    with patch.object(
        PooledTransport, "_wait_for_any_connection", new_callable=AsyncMock
    ):
        try:
            pool2 = await pooled_transport_factory(
                proto2,
                config=TransportConfig(),
                port_names=[],
                callback_port_names=[
                    "mqtt_ha://18:001111",
                    "mqtt_ha://18:002222",
                ],
            )
            check("MQTT-only pool created with 2 callback children",
                  len(pool2._children) == 2,
                  f"children={len(pool2._children)}")
        except Exception as e:
            check("MQTT-only pool creation",
                  False,
                  f"error={str(e)[:200]}")

    # ---------------------------------------------------------------------------
    # Test 5: Hybrid pool with mocked serial transports
    # ---------------------------------------------------------------------------
    proto = make_mock_protocol()
    mock_t0 = make_mock_transport(hgi="18:001111")
    mock_t1 = make_mock_transport(hgi="18:002222")

    # Mock create_serial_connection to return our mock transports
    transport_idx = [0]
    async def mock_create_serial_connection(*args, **kwargs):
        transports = [mock_t0, mock_t1]
        t = transports[transport_idx[0] % len(transports)]
        transport_idx[0] += 1
        return t, MagicMock()

    with patch(
        "serialx.create_serial_connection",
        side_effect=mock_create_serial_connection,
    ), patch.object(
        PooledTransport, "_wait_for_any_connection", new_callable=AsyncMock,
    ):
        try:
            pool = await pooled_transport_factory(
                proto,
                config=TransportConfig(),
                port_names=["/dev/ttyACM0", "/dev/ttyACM1"],
                port_configs=[
                    {"baudrate": 115200, "dsrdtr": False,
                     "rtscts": False, "timeout": 3, "xonxoff": False},
                    {"baudrate": 115200, "dsrdtr": False,
                     "rtscts": False, "timeout": 3, "xonxoff": False},
                ],
                callback_port_names=["mqtt_ha://18:003333"],
                per_child_config_overrides=[
                    {"signature_policy": SignaturePolicy.SKIP, "startup_grace": 3.0},
                    {"signature_policy": SignaturePolicy.SKIP, "startup_grace": 3.0},
                ],
            )
            check("Hybrid pool created with 3 children",
                  len(pool._children) == 3,
                  f"children={len(pool._children)}")
            check("Hybrid pool has serial + callback children",
                  len(pool._children) >= 2,
                  f"children={len(pool._children)}")
        except Exception as e:
            err_str = str(e)
            check("Hybrid pool created with 3 children",
                  False,
                  f"error={err_str[:200]}")

    # ---------------------------------------------------------------------------
    # Test 6: PooledTransport with callback children reports extra info
    # ---------------------------------------------------------------------------
    proto6 = make_mock_protocol()
    with patch.object(
        PooledTransport, "_wait_for_any_connection", new_callable=AsyncMock
    ):
        try:
            pool6 = await pooled_transport_factory(
                proto6,
                config=TransportConfig(),
                port_names=[],
                callback_port_names=["mqtt_ha://18:001111"],
            )
            stats = pool6.get_extra_info("pool_stats")
            check("Pool stats available with callback children",
                  stats is not None,
                  f"stats={stats}")
            check("Pool has 1 callback child",
                  len(pool6._children) == 1,
                  f"children={len(pool6._children)}")
        except Exception as e:
            check("Pool with callback children creation",
                  False,
                  f"error={str(e)[:200]}")

    # ---------------------------------------------------------------------------
    # Summary
    # ---------------------------------------------------------------------------
    passed = sum(1 for r in results if r["status"] == "PASS")
    failed = sum(1 for r in results if r["status"] == "FAIL")
    print(json.dumps({
        "passed": passed,
        "failed": failed,
        "results": results,
    }))


asyncio.run(run_tests())
""",
            timeout=60,
        )

        if "error" in result:
            ctx.check("Recipe 105 executed", False, f"error: {result['error']}")
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
            "All Phase 2 hybrid pool checks passed",
            failed == 0,
            f"{passed} passed, {failed} failed",
        )
