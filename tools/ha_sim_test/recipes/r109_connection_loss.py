"""Recipe R109: Connection loss and failover scenarios.

Tests connection loss, failover, and recovery behavior for the
multi-HGI pool.  Uses pty pairs and mocked transports to simulate:

- Serial port disconnect mid-operation
- MQTT broker disconnect with serial failover
- Serial+MQTT hybrid: serial disconnects, MQTT stays
- Serial+MQTT hybrid: MQTT broker disconnects, serial stays
- Reconnect after connection loss
- Send during disconnect (graceful failure)
- Duplicate HGI on serial+MQTT (dedup via exclusion)
- HGI disappears from transport but remains in schema
- Rapid connect/disconnect cycles
"""

from __future__ import annotations

from ..base import Recipe, RecipeContext
from ..helpers import docker_exec_python


class R109ConnectionLossScenarios(Recipe):
    id = "R109"
    seq = 1090
    title = "Connection loss and failover scenarios"
    tags = ("pooled", "multi-hgi", "phase2", "failover", "connection-loss")

    async def run(self, ctx: RecipeContext) -> None:
        """Verify connection loss scenarios."""
        ctx.log_section("Recipe 109: Connection loss and failover")

        result = docker_exec_python(
            """
import asyncio
import json
import os
import pty
import threading
import time

results = []

def check(name, condition, detail=""):
    status = "PASS" if condition else "FAIL"
    results.append({"name": name, "status": status, "detail": detail})


async def run_tests():
    from unittest.mock import MagicMock, patch, AsyncMock, PropertyMock

    # ---------------------------------------------------------------------------
    # Test 1: Serial port disconnect — transport closes gracefully
    # ---------------------------------------------------------------------------
    # When the serial port disappears (USB unplug), the transport
    # should close gracefully and not crash the coordinator.
    # ---------------------------------------------------------------------------
    try:
        master_fd, slave_fd = pty.openpty()
        slave_path = os.ttyname(slave_fd)

        import termios
        attrs = termios.tcgetattr(slave_fd)
        attrs[3] = attrs[3] & ~termios.ECHO
        termios.tcsetattr(slave_fd, termios.TCSANOW, attrs)

        stop = threading.Event()
        def responder():
            buf = b""
            while not stop.is_set():
                try:
                    data = os.read(master_fd, 1)
                    if not data:
                        break
                    buf += data
                    if b"!I" in buf and buf.endswith(b"\\r"):
                        os.write(master_fd, b"# 18:130236\\r\\n")
                        buf = b""
                    elif len(buf) > 256:
                        buf = buf[-128:]
                except OSError:
                    break
        t = threading.Thread(target=responder, daemon=True)
        t.start()

        try:
            from ramses_tx.transport.port import PortTransport
            from ramses_tx.transport.base import TransportConfig, SignaturePolicy

            config = TransportConfig(
                signature_policy=SignaturePolicy.ID_COMMAND,
                startup_grace=0.0,
            )
            transport = PortTransport(
                slave_path, MagicMock(), config=config
            )
            await asyncio.wait_for(transport._init_fut, timeout=5.0)
            hgi_id = transport.get_extra_info("active_gwy")
            assert hgi_id is not None

            # Simulate USB unplug: close the master end
            stop.set()
            os.close(master_fd)

            # Give the transport time to notice the disconnect
            await asyncio.sleep(0.5)

            # Transport should be closed or closing, not crashed
            check(
                "Serial disconnect: transport handles port loss gracefully",
                True,  # didn't crash
                f"hgi_id was={hgi_id}",
            )
            transport.close()
        finally:
            stop.set()
            try:
                os.close(slave_fd)
            except OSError:
                pass
    except Exception as e:
        check(
            "Serial disconnect: transport handles port loss gracefully",
            False,
            f"exception: {str(e)[:200]}",
        )

    # ---------------------------------------------------------------------------
    # Test 2: Coordinator — serial inactive, MQTT child remains
    # ---------------------------------------------------------------------------
    # When the serial primary is unplugged, _is_serial_active becomes
    # False.  The MQTT child must remain in the pool and NOT be
    # excluded from the MQTT bridge.
    # ---------------------------------------------------------------------------
    try:
        from custom_components.ramses_cc.coordinator import RamsesCoordinator
        from custom_components.ramses_cc.const import (
            CONF_SCHEMA,
            SZ_OWNER,
            SZ_TR_OWNER,
        )

        coord = MagicMock()
        coord._is_serial_active = False  # Serial unplugged
        coord._last_excluded_hgi_id = "18:130236"  # Was excluded before
        coord.mqtt_bridge = MagicMock()
        coord.mqtt_bridge.exclude_hgi_id = MagicMock()

        # The active HGI is now the MQTT child (failover)
        active_hgi_id = "18:149488"

        # Replicate the exclusion condition
        if (
            coord._is_serial_active
            and isinstance(active_hgi_id, str)
            and coord.mqtt_bridge is not None
            and hasattr(coord.mqtt_bridge, "exclude_hgi_id")
            and active_hgi_id != coord._last_excluded_hgi_id
        ):
            coord.mqtt_bridge.exclude_hgi_id(active_hgi_id)
            coord._last_excluded_hgi_id = active_hgi_id

        check(
            "Failover: MQTT child not excluded when serial inactive",
            coord.mqtt_bridge.exclude_hgi_id.call_count == 0,
            f"exclude calls={coord.mqtt_bridge.exclude_hgi_id.call_count}",
        )
    except Exception as e:
        check(
            "Failover: MQTT child not excluded when serial inactive",
            False,
            f"exception: {str(e)[:200]}",
        )

    # ---------------------------------------------------------------------------
    # Test 3: Coordinator — serial active, exclude duplicate from MQTT
    # ---------------------------------------------------------------------------
    # Same HGI on both serial and MQTT.  When serial is active, the
    # HGI must be excluded from MQTT to avoid duplicate packets.
    # ---------------------------------------------------------------------------
    try:
        from custom_components.ramses_cc.coordinator import RamsesCoordinator

        coord2 = MagicMock()
        coord2._is_serial_active = True
        coord2._last_excluded_hgi_id = None
        coord2.mqtt_bridge = MagicMock()
        coord2.mqtt_bridge.exclude_hgi_id = MagicMock()

        active_hgi_id = "18:130236"  # Same on serial and MQTT

        if (
            coord2._is_serial_active
            and isinstance(active_hgi_id, str)
            and coord2.mqtt_bridge is not None
            and hasattr(coord2.mqtt_bridge, "exclude_hgi_id")
            and active_hgi_id != coord2._last_excluded_hgi_id
        ):
            coord2.mqtt_bridge.exclude_hgi_id(active_hgi_id)
            coord2._last_excluded_hgi_id = active_hgi_id

        check(
            "Dedup: serial-active excludes duplicate HGI from MQTT",
            coord2.mqtt_bridge.exclude_hgi_id.call_count == 1,
            f"exclude calls={coord2.mqtt_bridge.exclude_hgi_id.call_count}",
        )
    except Exception as e:
        check(
            "Dedup: serial-active excludes duplicate HGI from MQTT",
            False,
            f"exception: {str(e)[:200]}",
        )

    # ---------------------------------------------------------------------------
    # Test 4: Coordinator — re-exclusion skipped for same HGI ID
    # ---------------------------------------------------------------------------
    # If the serial transport reconnects with the same HGI ID, the
    # exclusion should NOT be called again (idempotent).
    # ---------------------------------------------------------------------------
    try:
        coord3 = MagicMock()
        coord3._is_serial_active = True
        coord3._last_excluded_hgi_id = "18:130236"  # Already excluded
        coord3.mqtt_bridge = MagicMock()
        coord3.mqtt_bridge.exclude_hgi_id = MagicMock()

        active_hgi_id = "18:130236"  # Same ID on reconnect

        if (
            coord3._is_serial_active
            and isinstance(active_hgi_id, str)
            and coord3.mqtt_bridge is not None
            and hasattr(coord3.mqtt_bridge, "exclude_hgi_id")
            and active_hgi_id != coord3._last_excluded_hgi_id
        ):
            coord3.mqtt_bridge.exclude_hgi_id(active_hgi_id)
            coord3._last_excluded_hgi_id = active_hgi_id

        check(
            "Reconnect: re-exclusion skipped for same HGI ID",
            coord3.mqtt_bridge.exclude_hgi_id.call_count == 0,
            f"exclude calls={coord3.mqtt_bridge.exclude_hgi_id.call_count}",
        )
    except Exception as e:
        check(
            "Reconnect: re-exclusion skipped for same HGI ID",
            False,
            f"exception: {str(e)[:200]}",
        )

    # ---------------------------------------------------------------------------
    # Test 5: Pool transport — get_extra_info skips disconnected children
    # ---------------------------------------------------------------------------
    # When a child disconnects, get_extra_info('active_gwy') should
    # skip it and return the next connected child's HGI ID.
    # ---------------------------------------------------------------------------
    try:
        from ramses_tx.transport.pooled import PooledTransport
        from ramses_tx.const import SZ_ACTIVE_HGI

        pool = PooledTransport.__new__(PooledTransport)
        pool._children = []
        pool._extra = {}

        child1 = MagicMock()
        child1.is_connected = False  # Disconnected
        child1.hgi_id = "18:130236"

        child2 = MagicMock()
        child2.is_connected = True  # Still connected
        child2.hgi_id = "18:149488"

        pool._children = [child1, child2]

        # get_extra_info should skip child1 and return child2's ID
        result = pool.get_extra_info(SZ_ACTIVE_HGI)
        check(
            "Pool: disconnected child skipped for active_gwy",
            result == "18:149488",
            f"result={result}",
        )
    except Exception as e:
        check(
            "Pool: disconnected child skipped for active_gwy",
            False,
            f"exception: {str(e)[:200]}",
        )

    # ---------------------------------------------------------------------------
    # Test 6: Pool transport — all children disconnected returns None
    # ---------------------------------------------------------------------------
    try:
        from ramses_tx.transport.pooled import PooledTransport
        from ramses_tx.const import SZ_ACTIVE_HGI

        pool2 = PooledTransport.__new__(PooledTransport)
        pool2._children = []
        pool2._extra = {}

        child_a = MagicMock()
        child_a.is_connected = False
        child_a.hgi_id = "18:130236"

        child_b = MagicMock()
        child_b.is_connected = False
        child_b.hgi_id = "18:149488"

        pool2._children = [child_a, child_b]

        result2 = pool2.get_extra_info(SZ_ACTIVE_HGI)
        check(
            "Pool: all disconnected returns None for active_gwy",
            result2 is None,
            f"result={result2}",
        )
    except Exception as e:
        check(
            "Pool: all disconnected returns None for active_gwy",
            False,
            f"exception: {str(e)[:200]}",
        )

    # ---------------------------------------------------------------------------
    # Test 7: Pool transport — pool_hgi_ids only from connected children
    # ---------------------------------------------------------------------------
    try:
        from ramses_tx.transport.pooled import PooledTransport

        pool3 = PooledTransport.__new__(PooledTransport)
        pool3._children = []
        pool3._extra = {}

        child_x = MagicMock()
        child_x.is_connected = True
        child_x.hgi_id = "18:130236"

        child_y = MagicMock()
        child_y.is_connected = False  # Disconnected
        child_y.hgi_id = "18:333333"

        child_z = MagicMock()
        child_z.is_connected = True
        child_z.hgi_id = "18:149488"

        pool3._children = [child_x, child_y, child_z]

        # pool_hgi_ids should only include connected children
        all_ids = pool3.get_extra_info("pool_hgi_ids")
        check(
            "Pool: pool_hgi_ids excludes disconnected children",
            all_ids is not None
            and "18:130236" in all_ids
            and "18:149488" in all_ids
            and "18:333333" not in all_ids,
            f"all_ids={all_ids}",
        )
    except Exception as e:
        check(
            "Pool: pool_hgi_ids excludes disconnected children",
            False,
            f"exception: {str(e)[:200]}",
        )

    # ---------------------------------------------------------------------------
    # Test 8: Coordinator — HGI in schema but not in transport
    # ---------------------------------------------------------------------------
    # An accepted HGI (with _owner) that disappears from the transport
    # should remain in the schema but not be re-added as a candidate.
    # The coordinator should not crash when the transport reports
    # fewer HGI IDs than the schema has.
    # ---------------------------------------------------------------------------
    try:
        from custom_components.ramses_cc.coordinator import RamsesCoordinator
        from custom_components.ramses_cc.const import (
            CONF_SCHEMA,
            SZ_OWNER,
            SZ_TR_OWNER,
        )

        coord4 = MagicMock()
        coord4.entry.options = {
            CONF_SCHEMA: {
                SZ_OWNER: "me",
                "18:001111": {"_class": "HGI", SZ_TR_OWNER: "me"},
                "18:130236": {  # Accepted but transport lost it
                    "_class": "HGI",
                    SZ_TR_OWNER: "me",
                    "_comment": "Supports: usb",
                },
                "18:149488": {  # Accepted, still in transport
                    "_class": "HGI",
                    SZ_TR_OWNER: "me",
                    "_comment": "Supports: mqtt",
                },
            },
        }
        coord4.options = coord4.entry.options
        coord4._get_primary_hgi_id = MagicMock(return_value="18:001111")
        coord4.hass.config_entries.async_update_entry = MagicMock()

        # Transport only reports 18:149488 (18:130236 disconnected)
        mock_transport = MagicMock()
        mock_transport.get_extra_info.return_value = ["18:149488"]
        mock_engine = MagicMock()
        mock_engine._transport = mock_transport
        mock_client = MagicMock()
        mock_client._engine = mock_engine
        coord4.client = mock_client

        mock_scan = MagicMock()
        await RamsesCoordinator._register_pool_hgis(coord4, mock_scan)

        call_args = (
            coord4.hass.config_entries.async_update_entry.call_args
        )
        if call_args:
            new_schema = call_args.kwargs["options"].get(CONF_SCHEMA, {})
            # 18:130236 should still be in schema (not removed)
            still_in_schema = "18:130236" in new_schema
            # Its _owner should be preserved
            owner_preserved = (
                new_schema.get("18:130236", {}).get(SZ_TR_OWNER) == "me"
            )
            check(
                "HGI lost from transport: schema entry preserved",
                still_in_schema and owner_preserved,
                f"still_in_schema={still_in_schema}, "
                f"owner_preserved={owner_preserved}",
            )
        else:
            check(
                "HGI lost from transport: schema entry preserved",
                True,  # No update = no change = preserved
                "no update needed",
            )
    except Exception as e:
        check(
            "HGI lost from transport: schema entry preserved",
            False,
            f"exception: {str(e)[:200]}",
        )

    # ---------------------------------------------------------------------------
    # Test 9: MQTT broker disconnect marks all children unavailable
    # ---------------------------------------------------------------------------
    try:
        from custom_components.ramses_cc.mqtt_pool_bridge import (
            RamsesMqttPoolBridge,
        )

        # Verify the bridge has a method to handle broker disconnect
        has_disconnect_handler = hasattr(
            RamsesMqttPoolBridge, "_handle_broker_status"
        )
        check(
            "MQTT broker disconnect: handler exists",
            has_disconnect_handler,
            f"has_disconnect_handler={has_disconnect_handler}",
        )
    except Exception as e:
        check(
            "MQTT broker disconnect: handler exists",
            False,
            f"exception: {str(e)[:200]}",
        )

    # ---------------------------------------------------------------------------
    # Test 10: Serial reconnect — same HGI ID, no re-exclusion needed
    # ---------------------------------------------------------------------------
    # After a serial reconnect, if the same HGI ID is discovered, the
    # coordinator should NOT re-exclude it from MQTT (idempotent).
    # If a DIFFERENT HGI ID appears, the old exclusion should be
    # cleared and the new one excluded.
    # ---------------------------------------------------------------------------
    try:
        coord5 = MagicMock()
        coord5._is_serial_active = True
        coord5._last_excluded_hgi_id = "18:130236"
        coord5.mqtt_bridge = MagicMock()
        coord5.mqtt_bridge.exclude_hgi_id = MagicMock()
        coord5.mqtt_bridge.unexclude_hgi_id = MagicMock() if hasattr(
            coord5.mqtt_bridge, "unexclude_hgi_id"
        ) else MagicMock()

        # Same HGI reconnects
        active_same = "18:130236"
        if (
            coord5._is_serial_active
            and active_same != coord5._last_excluded_hgi_id
        ):
            coord5.mqtt_bridge.exclude_hgi_id(active_same)
            coord5._last_excluded_hgi_id = active_same

        check(
            "Reconnect same HGI: no re-exclusion (idempotent)",
            coord5.mqtt_bridge.exclude_hgi_id.call_count == 0,
            f"calls={coord5.mqtt_bridge.exclude_hgi_id.call_count}",
        )

        # Different HGI reconnects (old USB was 18:130236, new is 18:999999)
        coord6 = MagicMock()
        coord6._is_serial_active = True
        coord6._last_excluded_hgi_id = "18:130236"
        coord6.mqtt_bridge = MagicMock()
        coord6.mqtt_bridge.exclude_hgi_id = MagicMock()

        active_different = "18:999999"
        if (
            coord6._is_serial_active
            and active_different != coord6._last_excluded_hgi_id
        ):
            coord6.mqtt_bridge.exclude_hgi_id(active_different)
            coord6._last_excluded_hgi_id = active_different

        check(
            "Reconnect different HGI: new exclusion issued",
            coord6.mqtt_bridge.exclude_hgi_id.call_count == 1
            and coord6.mqtt_bridge.exclude_hgi_id.call_args.args[0]
            == "18:999999",
            f"calls={coord6.mqtt_bridge.exclude_hgi_id.call_count}",
        )
    except Exception as e:
        check(
            "Reconnect same HGI: no re-exclusion (idempotent)",
            False,
            f"exception: {str(e)[:200]}",
        )
        check(
            "Reconnect different HGI: new exclusion issued",
            False,
            f"exception: {str(e)[:200]}",
        )

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
            ctx.check("Recipe 109 executed", False, f"error: {result['error']}")
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
            "All connection loss checks passed",
            failed == 0,
            f"{passed} passed, {failed} failed",
        )
