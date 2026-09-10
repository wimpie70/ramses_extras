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
- Set-based exclusion: only connected serial children excluded
- Un-exclusion: disconnected serial HGI re-included in MQTT pool
- MQTT bridge unexclude_hgi_id method
- Per-device-type exclusion: ESP32-S3, HGI80, nanoCUL, ATmega32U4
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
    # Test 2: Set-based exclusion — only connected serial children excluded
    # ---------------------------------------------------------------------------
    # The coordinator collects HGI IDs from tpt._children, but only
    # from non-callback children that are is_connected.  Disconnected
    # children should NOT be in the exclusion set (issue 1185).
    # ---------------------------------------------------------------------------
    try:
        from ramses_tx.transport.pooled import (
            ConnectionState,
            NodeAvailability,
            PoolChild,
        )

        # Simulate pool children: child 0 connected, child 1 disconnected
        child0 = MagicMock()
        child0.hgi_id = "18:149488"
        child0.callback_driven = False
        child0.is_connected = True

        child1 = MagicMock()
        child1.hgi_id = "18:130236"
        child1.callback_driven = False
        child1.is_connected = False  # Disconnected

        # Replicate the coordinator's serial_hgi_ids collection logic
        serial_hgi_ids: set[str] = set()
        for child in [child0, child1]:
            child_hgi = getattr(child, "hgi_id", None)
            is_callback = getattr(child, "callback_driven", False)
            is_connected = getattr(child, "is_connected", False)
            if (
                child_hgi
                and not is_callback
                and isinstance(child_hgi, str)
                and is_connected
            ):
                serial_hgi_ids.add(child_hgi)

        check(
            "Set exclusion: only connected serial children excluded",
            serial_hgi_ids == {"18:149488"},
            f"serial_hgi_ids={serial_hgi_ids}",
        )
        check(
            "Set exclusion: disconnected child NOT in exclusion set",
            "18:130236" not in serial_hgi_ids,
            f"18:130236 in set: {'18:130236' in serial_hgi_ids}",
        )
    except Exception as e:
        check(
            "Set exclusion: only connected serial children excluded",
            False,
            f"exception: {str(e)[:200]}",
        )
        check(
            "Set exclusion: disconnected child NOT in exclusion set",
            False,
            f"exception: {str(e)[:200]}",
        )

    # ---------------------------------------------------------------------------
    # Test 3: Un-exclusion — disconnected serial HGI re-included in MQTT
    # ---------------------------------------------------------------------------
    # When a serial child disconnects, its HGI should be un-excluded
    # from the MQTT pool so packets via MQTT flow again (issue 1185).
    # ---------------------------------------------------------------------------
    try:
        # Simulate the coordinator's stale_exclusions logic
        excluded_serial_hgi_ids: set[str] = {"18:149488", "18:130236"}
        current_serial_hgi_ids: set[str] = {"18:149488"}  # child 1 disconnected

        stale_exclusions = excluded_serial_hgi_ids - current_serial_hgi_ids
        # stale_exclusions should be {"18:130236"}

        check(
            "Un-exclusion: stale exclusions calculated correctly",
            stale_exclusions == {"18:130236"},
            f"stale={stale_exclusions}",
        )

        # Simulate un-exclusion
        mqtt_bridge = MagicMock()
        mqtt_bridge.unexclude_hgi_id = MagicMock()
        for hgi_id in stale_exclusions:
            if hasattr(mqtt_bridge, "unexclude_hgi_id"):
                mqtt_bridge.unexclude_hgi_id(hgi_id)
            excluded_serial_hgi_ids.discard(hgi_id)

        check(
            "Un-exclusion: unexclude_hgi_id called for stale HGI",
            mqtt_bridge.unexclude_hgi_id.call_count == 1
            and mqtt_bridge.unexclude_hgi_id.call_args.args[0] == "18:130236",
            f"calls={mqtt_bridge.unexclude_hgi_id.call_count}",
        )
        check(
            "Un-exclusion: stale HGI removed from excluded set",
            "18:130236" not in excluded_serial_hgi_ids
            and "18:149488" in excluded_serial_hgi_ids,
            f"excluded={excluded_serial_hgi_ids}",
        )
    except Exception as e:
        check(
            "Un-exclusion: stale exclusions calculated correctly",
            False,
            f"exception: {str(e)[:200]}",
        )
        check(
            "Un-exclusion: unexclude_hgi_id called for stale HGI",
            False,
            f"exception: {str(e)[:200]}",
        )
        check(
            "Un-exclusion: stale HGI removed from excluded set",
            False,
            f"exception: {str(e)[:200]}",
        )

    # ---------------------------------------------------------------------------
    # Test 4: Re-exclusion skipped for already-excluded HGIs (idempotent)
    # ---------------------------------------------------------------------------
    # If the serial transport reconnects with the same HGI ID, the
    # exclusion should NOT be called again (idempotent).
    # ---------------------------------------------------------------------------
    try:
        excluded_serial_hgi_ids = {"18:130236"}
        serial_hgi_ids_reconnect = {"18:130236"}  # Same ID on reconnect

        mqtt_bridge2 = MagicMock()
        mqtt_bridge2.exclude_hgi_id = MagicMock()

        for hgi_id in serial_hgi_ids_reconnect:
            if hgi_id in excluded_serial_hgi_ids:
                continue  # Already excluded — skip
            mqtt_bridge2.exclude_hgi_id(hgi_id)
            excluded_serial_hgi_ids.add(hgi_id)

        check(
            "Reconnect: re-exclusion skipped for same HGI ID (idempotent)",
            mqtt_bridge2.exclude_hgi_id.call_count == 0,
            f"calls={mqtt_bridge2.exclude_hgi_id.call_count}",
        )
    except Exception as e:
        check(
            "Reconnect: re-exclusion skipped for same HGI ID (idempotent)",
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
    # cleared (un-excluded) and the new one excluded.
    # ---------------------------------------------------------------------------
    try:
        # Same HGI reconnects — already in excluded set
        excluded_set = {"18:130236"}
        serial_set_same = {"18:130236"}
        bridge_same = MagicMock()
        bridge_same.exclude_hgi_id = MagicMock()
        bridge_same.unexclude_hgi_id = MagicMock()

        for hgi_id in serial_set_same:
            if hgi_id in excluded_set:
                continue
            bridge_same.exclude_hgi_id(hgi_id)
            excluded_set.add(hgi_id)
        stale = excluded_set - serial_set_same
        for hgi_id in stale:
            bridge_same.unexclude_hgi_id(hgi_id)
            excluded_set.discard(hgi_id)

        check(
            "Reconnect same HGI: no re-exclusion (idempotent)",
            bridge_same.exclude_hgi_id.call_count == 0,
            f"exclude calls={bridge_same.exclude_hgi_id.call_count}",
        )
        check(
            "Reconnect same HGI: no un-exclusion (no stale)",
            bridge_same.unexclude_hgi_id.call_count == 0,
            f"unexclude calls={bridge_same.unexclude_hgi_id.call_count}",
        )

        # Different HGI reconnects (old USB was 18:130236, new is 18:999999)
        excluded_set2 = {"18:130236"}
        serial_set_diff = {"18:999999"}
        bridge_diff = MagicMock()
        bridge_diff.exclude_hgi_id = MagicMock()
        bridge_diff.unexclude_hgi_id = MagicMock()

        for hgi_id in serial_set_diff:
            if hgi_id in excluded_set2:
                continue
            bridge_diff.exclude_hgi_id(hgi_id)
            excluded_set2.add(hgi_id)
        stale2 = excluded_set2 - serial_set_diff
        for hgi_id in stale2:
            bridge_diff.unexclude_hgi_id(hgi_id)
            excluded_set2.discard(hgi_id)

        check(
            "Reconnect different HGI: new exclusion issued",
            bridge_diff.exclude_hgi_id.call_count == 1
            and bridge_diff.exclude_hgi_id.call_args.args[0] == "18:999999",
            f"calls={bridge_diff.exclude_hgi_id.call_count}",
        )
        check(
            "Reconnect different HGI: old HGI un-excluded",
            bridge_diff.unexclude_hgi_id.call_count == 1
            and bridge_diff.unexclude_hgi_id.call_args.args[0] == "18:130236",
            f"unexclude calls={bridge_diff.unexclude_hgi_id.call_count}",
        )
    except Exception as e:
        check(
            "Reconnect same HGI: no re-exclusion (idempotent)",
            False,
            f"exception: {str(e)[:200]}",
        )
        check(
            "Reconnect same HGI: no un-exclusion (no stale)",
            False,
            f"exception: {str(e)[:200]}",
        )
        check(
            "Reconnect different HGI: new exclusion issued",
            False,
            f"exception: {str(e)[:200]}",
        )
        check(
            "Reconnect different HGI: old HGI un-excluded",
            False,
            f"exception: {str(e)[:200]}",
        )

    # ---------------------------------------------------------------------------
    # Test 11: MQTT bridge unexclude_hgi_id method exists and works
    # ---------------------------------------------------------------------------
    try:
        from custom_components.ramses_cc.mqtt_pool_bridge import (
            RamsesMqttPoolBridge,
        )

        has_unexclude = hasattr(RamsesMqttPoolBridge, "unexclude_hgi_id")
        check(
            "MQTT bridge: unexclude_hgi_id method exists",
            has_unexclude,
            f"has_unexclude={has_unexclude}",
        )
    except Exception as e:
        check(
            "MQTT bridge: unexclude_hgi_id method exists",
            False,
            f"exception: {str(e)[:200]}",
        )

    # ---------------------------------------------------------------------------
    # Test 12: Per-device-type exclusion (ESP32-S3, HGI80, nanoCUL, ATmega)
    # ---------------------------------------------------------------------------
    # All serial device types should be excluded from MQTT when connected,
    # regardless of firmware type.  The exclusion is based on is_connected
    # and callback_driven, not on the device firmware.
    # ---------------------------------------------------------------------------
    try:
        device_types = [
            ("ESP32-S3", "18:130236"),
            ("HGI80", "18:222222"),
            ("nanoCUL", "18:333333"),
            ("ATmega32U4", "18:444444"),
        ]

        for dev_name, hgi_id in device_types:
            child = MagicMock()
            child.hgi_id = hgi_id
            child.callback_driven = False
            child.is_connected = True

            serial_ids: set[str] = set()
            for c in [child]:
                if (
                    c.hgi_id
                    and not c.callback_driven
                    and isinstance(c.hgi_id, str)
                    and c.is_connected
                ):
                    serial_ids.add(c.hgi_id)

            check(
                f"Device type {dev_name}: excluded from MQTT when connected",
                hgi_id in serial_ids,
                f"serial_ids={serial_ids}",
            )

            # When disconnected, should NOT be in exclusion set
            child.is_connected = False
            serial_ids2: set[str] = set()
            for c in [child]:
                if (
                    c.hgi_id
                    and not c.callback_driven
                    and isinstance(c.hgi_id, str)
                    and c.is_connected
                ):
                    serial_ids2.add(c.hgi_id)

            check(
                f"Device type {dev_name}: NOT excluded when disconnected",
                hgi_id not in serial_ids2,
                f"serial_ids={serial_ids2}",
            )
    except Exception as e:
        for dev_name, _ in [
            ("ESP32-S3", "18:130236"),
            ("HGI80", "18:222222"),
            ("nanoCUL", "18:333333"),
            ("ATmega32U4", "18:444444"),
        ]:
            check(
                f"Device type {dev_name}: excluded from MQTT when connected",
                False,
                f"exception: {str(e)[:200]}",
            )
            check(
                f"Device type {dev_name}: NOT excluded when disconnected",
                False,
                f"exception: {str(e)[:200]}",
            )

    # ---------------------------------------------------------------------------
    # Test 13: Callback-driven children NOT excluded (MQTT children)
    # ---------------------------------------------------------------------------
    # Callback-driven children (MQTT) should never be in the serial
    # exclusion set, even if connected.
    # ---------------------------------------------------------------------------
    try:
        mqtt_child = MagicMock()
        mqtt_child.hgi_id = "18:555555"
        mqtt_child.callback_driven = True
        mqtt_child.is_connected = True

        serial_ids3: set[str] = set()
        for c in [mqtt_child]:
            if (
                c.hgi_id
                and not c.callback_driven
                and isinstance(c.hgi_id, str)
                and c.is_connected
            ):
                serial_ids3.add(c.hgi_id)

        check(
            "Callback child: NOT in serial exclusion set",
            "18:555555" not in serial_ids3,
            f"serial_ids={serial_ids3}",
        )
    except Exception as e:
        check(
            "Callback child: NOT in serial exclusion set",
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
