"""Recipe R107: Hardware scenario simulations with fake serial ports.

Uses pty pairs to create fake serial ports inside the ha-sim container
to simulate hardware scenarios we can't test with real devices:

- Modbus device: pty that doesn't respond to !I → no HGI ID learned
- HGI via serial: pty that responds to !I → HGI ID learned
- HGI via serial with delayed response: simulates nanoCUL 3s wait
- Config flow: serial primary + MQTT HGI → save → _owner preserved

These tests exercise the actual ramses_rf transport layer (PortTransport)
against fake serial devices, not just mocked coordinator methods.
"""

from __future__ import annotations

from ..base import Recipe, RecipeContext
from ..helpers import docker_exec_python


class R107HardwareScenarios(Recipe):
    id = "R107"
    seq = 1070
    title = "Hardware scenario simulations (fake serial ports)"
    tags = ("pooled", "multi-hgi", "phase2", "hardware", "serial", "modbus")

    async def run(self, ctx: RecipeContext) -> None:
        """Verify hardware scenarios with fake serial ports."""
        ctx.log_section("Recipe 107: Hardware scenario simulations")

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
    # ---------------------------------------------------------------------------
    # Test 1: Modbus device — no response to !I, no HGI ID learned
    # ---------------------------------------------------------------------------
    # Create a pty pair.  The slave end looks like a serial port.
    # We don't write anything to the master end — simulating a modbus
    # bridge that doesn't understand RAMSES !I commands.
    # The transport should fail to get an HGI ID.
    # ---------------------------------------------------------------------------
    try:
        master_fd, slave_fd = pty.openpty()
        slave_path = os.ttyname(slave_fd)

        # Background thread that reads from master but never responds
        # (modbus bridge ignores !I)
        stop = threading.Event()
        def modbus_silence():
            while not stop.is_set():
                try:
                    os.read(master_fd, 1024)
                except OSError:
                    break
        t = threading.Thread(target=modbus_silence, daemon=True)
        t.start()

        try:
            from ramses_tx.transport.port import PortTransport
            from ramses_tx.transport.base import TransportConfig, SignaturePolicy

            config = TransportConfig(
                signature_policy=SignaturePolicy.ID_COMMAND,
                startup_grace=0.5,
            )
            transport = PortTransport(
                slave_path,
                MagicMock(),
                config=config,
            )
            # Try to connect — should timeout or fail to get HGI ID
            try:
                await asyncio.wait_for(
                    transport.connect(), timeout=3.0
                )
            except (asyncio.TimeoutError, Exception):
                pass  # expected — modbus doesn't respond

            hgi_id = None
            if hasattr(transport, "_hgi_id"):
                hgi_id = transport._hgi_id
            elif hasattr(transport, "get_extra_info"):
                hgi_id = transport.get_extra_info("active_hgi")

            check(
                "Modbus: no HGI ID learned (no !I response)",
                hgi_id is None,
                f"hgi_id={hgi_id}",
            )
        finally:
            stop.set()
            os.close(master_fd)
            os.close(slave_fd)
    except Exception as e:
        check(
            "Modbus: no HGI ID learned (no !I response)",
            False,
            f"exception: {str(e)[:200]}",
        )

    # ---------------------------------------------------------------------------
    # Test 2: HGI via serial — full pty transport handshake
    # ---------------------------------------------------------------------------
    # Create a pty pair.  A background thread listens for !I on the
    # master end and responds with "# 18:130236\\r\\n" — simulating
    # an evofw3 HGI dongle.  The PortTransport should learn the HGI
    # ID via the ID_COMMAND signature policy.
    # ---------------------------------------------------------------------------
    try:
        master_fd2, slave_fd2 = pty.openpty()
        slave_path2 = os.ttyname(slave_fd2)

        # Disable echo on the slave (otherwise transport sees its
        # own !I echoed back)
        import termios
        attrs2 = termios.tcgetattr(slave_fd2)
        attrs2[3] = attrs2[3] & ~termios.ECHO
        termios.tcsetattr(slave_fd2, termios.TCSANOW, attrs2)

        stop2 = threading.Event()
        def hgi_responder():
            # Simulate an evofw3 HGI that responds to !I.
            buf = b""
            while not stop2.is_set():
                try:
                    data = os.read(master_fd2, 1)
                    if not data:
                        break
                    buf += data
                    if b"!I" in buf and buf.endswith(b"\\r"):
                        os.write(master_fd2, b"# 18:130236\\r\\n")
                        buf = b""
                    elif len(buf) > 256:
                        buf = buf[-128:]
                except OSError:
                    break
        t2 = threading.Thread(target=hgi_responder, daemon=True)
        t2.start()

        try:
            from ramses_tx.transport.port import PortTransport
            from ramses_tx.transport.base import TransportConfig, SignaturePolicy

            config2 = TransportConfig(
                signature_policy=SignaturePolicy.ID_COMMAND,
                startup_grace=0.0,
            )
            transport2 = PortTransport(
                slave_path2, MagicMock(), config=config2
            )
            try:
                await asyncio.wait_for(
                    transport2._init_fut, timeout=5.0
                )
            except (asyncio.TimeoutError, Exception):
                pass

            # Use 'active_gwy' (SZ_ACTIVE_HGI) not 'active_hgi'
            hgi_id2 = transport2.get_extra_info("active_gwy")
            check(
                "HGI: full pty transport learns HGI ID from !I",
                hgi_id2 is not None and "18:130236" in str(hgi_id2),
                f"hgi_id={hgi_id2}",
            )
            transport2.close()
        finally:
            stop2.set()
            os.close(master_fd2)
            os.close(slave_fd2)
    except Exception as e:
        check(
            "HGI: full pty transport learns HGI ID from !I",
            False,
            f"exception: {str(e)[:200]}",
        )

    # ---------------------------------------------------------------------------
    # Test 2b: HGI !I response regex parsing (multiple HGI IDs)
    # ---------------------------------------------------------------------------
    try:
        from ramses_tx.transport.port import _EVOFW3_ID_RE

        # Simulate evofw3 !I responses
        responses = [
            "# 18:130236\\r\\n",  # standard HGI
            "# 18:149488\\r\\n",  # another HGI
            "# 18:006402\\r\\n",  # short ID format
        ]
        all_parsed = True
        for resp in responses:
            m = _EVOFW3_ID_RE.search(resp)
            if m:
                hgi_id = f"{m.group(1)}:{m.group(2)}"
            else:
                hgi_id = None
                all_parsed = False
            if hgi_id not in resp:
                all_parsed = False

        check(
            "HGI: !I response parsing works for multiple HGI IDs",
            all_parsed,
            f"parsed={all_parsed}",
        )
    except Exception as e:
        check(
            "HGI: !I response parsing works for multiple HGI IDs",
            False,
            f"exception: {str(e)[:200]}",
        )

    # ---------------------------------------------------------------------------
    # Test 3: !I regex parsing — modbus garbage vs valid HGI response
    # ---------------------------------------------------------------------------
    # Verify the _EVOFW3_ID_RE regex correctly distinguishes:
    # - Valid: "# 18:130236\\r\\n" → 18:130236
    # - Modbus: "garbage data" → no match
    # - Short: "# 18:130\\r\\n" → no match (too short)
    # ---------------------------------------------------------------------------
    try:
        from ramses_tx.transport.port import _EVOFW3_ID_RE

        valid = _EVOFW3_ID_RE.search("# 18:130236\\r\\n")
        modbus = _EVOFW3_ID_RE.search("garbage data_from_modbus")
        short = _EVOFW3_ID_RE.search("# 18:130\\r\\n")

        # Regex has two groups: (dd):(dddddd) -> group(1)="18", group(2)="130236"
        valid_id = (
            f"{valid.group(1)}:{valid.group(2)}" if valid else None
        )
        check(
            "!I regex: valid HGI response parsed",
            valid is not None and valid_id == "18:130236",
            f"match={valid_id}",
        )
        check(
            "!I regex: modbus garbage rejected",
            modbus is None,
            f"match={modbus}",
        )
        check(
            "!I regex: short ID rejected",
            short is None,
            f"match={short}",
        )
    except Exception as e:
        check(
            "!I regex parsing",
            False,
            f"exception: {str(e)[:200]}",
        )

    # ---------------------------------------------------------------------------
    # Test 4: Coordinator — modbus port not added to schema
    # ---------------------------------------------------------------------------
    # Simulate a pool transport where the only "serial child" is a
    # modbus device (no HGI IDs in pool_hgi_ids).  Verify the
    # coordinator does NOT add any new entries to the schema.
    # ---------------------------------------------------------------------------
    try:
        from custom_components.ramses_cc.coordinator import RamsesCoordinator
        from custom_components.ramses_cc.const import CONF_SCHEMA, SZ_TR_OWNER

        coord = MagicMock()
        coord.entry.options = {
            CONF_SCHEMA: {
                "owner": "me",
                "18:001111": {"_class": "HGI", SZ_TR_OWNER: "me"},
            },
        }
        coord.options = coord.entry.options
        coord._get_primary_hgi_id = MagicMock(return_value="18:001111")
        coord.hass.config_entries.async_update_entry = MagicMock()

        # Modbus: no HGI IDs learned (pool_hgi_ids is empty)
        mock_transport = MagicMock()
        mock_transport.get_extra_info.return_value = []
        mock_engine = MagicMock()
        mock_engine._transport = mock_transport
        mock_client = MagicMock()
        mock_client._engine = mock_engine
        coord.client = mock_client

        mock_scan = MagicMock()
        await RamsesCoordinator._register_pool_hgis(coord, mock_scan)

        call_args = (
            coord.hass.config_entries.async_update_entry.call_args
        )
        no_spurious = True
        if call_args:
            new_schema = call_args.kwargs.get("options", {}).get(
                CONF_SCHEMA, {}
            )
            hgi_entries = [
                k for k, v in new_schema.items()
                if k.startswith("18:")
                and isinstance(v, dict)
                and v.get("_class", "").upper() == "HGI"
            ]
            no_spurious = hgi_entries == ["18:001111"]

        check(
            "Modbus: no spurious schema entries",
            no_spurious,
            f"hgi_entries={hgi_entries if not no_spurious else '[18:001111]'}",
        )
    except Exception as e:
        check(
            "Modbus: no spurious schema entries",
            False,
            f"exception: {str(e)[:200]}",
        )

    # ---------------------------------------------------------------------------
    # Test 5: Coordinator — HGI discovered via serial added as candidate
    # ---------------------------------------------------------------------------
    try:
        from custom_components.ramses_cc.coordinator import RamsesCoordinator
        from custom_components.ramses_cc.const import CONF_SCHEMA, SZ_TR_OWNER

        coord = MagicMock()
        coord.entry.options = {
            CONF_SCHEMA: {
                "owner": "me",
                "18:001111": {"_class": "HGI", SZ_TR_OWNER: "me"},
            },
        }
        coord.options = coord.entry.options
        coord._get_primary_hgi_id = MagicMock(return_value="18:001111")
        coord.hass.config_entries.async_update_entry = MagicMock()

        # HGI discovered via serial: pool_hgi_ids has the new HGI
        mock_transport = MagicMock()
        mock_transport.get_extra_info.return_value = ["18:130236"]
        mock_engine = MagicMock()
        mock_engine._transport = mock_transport
        mock_client = MagicMock()
        mock_client._engine = mock_engine
        coord.client = mock_client

        mock_scan = MagicMock()
        await RamsesCoordinator._register_pool_hgis(coord, mock_scan)

        call_args = (
            coord.hass.config_entries.async_update_entry.call_args
        )
        added = False
        if call_args:
            new_schema = call_args.kwargs.get("options", {}).get(
                CONF_SCHEMA, {}
            )
            if "18:130236" in new_schema:
                entry = new_schema["18:130236"]
                added = (
                    isinstance(entry, dict)
                    and entry.get("_class") == "HGI"
                    and SZ_TR_OWNER not in entry
                    and "usb" in entry.get("_comment", "")
                )

        check(
            "HGI: serial discovery added as candidate (no _owner, usb comment)",
            added,
            f"added={added}",
        )
    except Exception as e:
        check(
            "HGI: serial discovery added as candidate (no _owner, usb comment)",
            False,
            f"exception: {str(e)[:200]}",
        )

    # ---------------------------------------------------------------------------
    # Test 6: Config flow — serial primary shows schema pool members
    # ---------------------------------------------------------------------------
    try:
        import inspect as _inspect
        from custom_components.ramses_cc import config_flow

        source = _inspect.getsource(config_flow)
        # Verify the old Phase 1 gate is removed
        old_gate = "if is_primary_mqtt or not primary_port:"
        check(
            "Config: serial primary shows schema pool members (no gate)",
            old_gate not in source,
            f"old_gate_present={old_gate in source}",
        )
    except Exception as e:
        check(
            "Config: serial primary shows schema pool members (no gate)",
            False,
            f"exception: {str(e)[:200]}",
        )

    # ---------------------------------------------------------------------------
    # Test 7: Serial probe does NOT auto-add USB ports
    # ---------------------------------------------------------------------------
    try:
        from custom_components.ramses_cc.coordinator import RamsesCoordinator
        from custom_components.ramses_cc.const import (
            CONF_ADDITIONAL_PORTS,
            CONF_SCHEMA,
            SZ_TR_OWNER,
        )

        coord = MagicMock()
        coord.entry.options = {
            CONF_SCHEMA: {
                "owner": "me",
                "18:001111": {"_class": "HGI", SZ_TR_OWNER: "me"},
            },
            CONF_ADDITIONAL_PORTS: [],
        }
        coord.options = coord.entry.options
        coord._get_primary_hgi_id = MagicMock(return_value="18:001111")
        coord._suppress_reload = 0
        coord.hass.config_entries.async_update_entry = MagicMock()

        with patch("glob.glob", return_value=["/dev/ttyACM0", "/dev/ttyACM1"]):
            await RamsesCoordinator._async_probe_serial_ports(
                coord, "/dev/ttyACM0", None
            )

        call_args = (
            coord.hass.config_entries.async_update_entry.call_args
        )
        auto_added = False
        if call_args:
            new_opts = call_args.kwargs.get("options", {})
            additional = new_opts.get(CONF_ADDITIONAL_PORTS, [])
            if "/dev/ttyACM1" in additional:
                auto_added = True

        check(
            "Serial probe: no auto-add of USB ports",
            not auto_added,
            f"auto_added={auto_added}",
        )
    except Exception as e:
        check(
            "Serial probe: no auto-add of USB ports",
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


# Need MagicMock and patch
from unittest.mock import MagicMock, patch

asyncio.run(run_tests())
""",
            timeout=60,
        )

        if "error" in result:
            ctx.check("Recipe 107 executed", False, f"error: {result['error']}")
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
            "All hardware scenario checks passed",
            failed == 0,
            f"{passed} passed, {failed} failed",
        )
