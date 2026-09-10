"""Recipe R106: Phase 2 unified review flow for USB and MQTT HGIs.

Verifies that the ramses_cc coordinator and config flow correctly:

- Do NOT auto-add USB serial ports to additional_ports (modbus bug fix).
- Add discovered serial child HGI IDs to the schema as discovery
  candidates (no _owner) — same as MQTT HGIs.
- Show schema pool members regardless of primary transport type
  (Phase 2 hybrid pool support).

This recipe runs inside the ha-sim container where the updated
ramses_cc custom component is installed.  It tests the coordinator
methods directly with mock objects, verifying the installed code
matches the Phase 2 review flow design.
"""

from __future__ import annotations

from ..base import Recipe, RecipeContext
from ..helpers import docker_exec_python


class R106Phase2ReviewFlow(Recipe):
    id = "R106"
    seq = 1060
    title = "Phase 2 unified review flow (USB + MQTT HGIs)"
    tags = ("pooled", "multi-hgi", "phase2", "review", "coordinator")

    async def run(self, ctx: RecipeContext) -> None:
        """Verify Phase 2 unified review flow behavior."""
        ctx.log_section("Recipe 106: Phase 2 unified review flow")

        result = docker_exec_python(
            """
import asyncio
import inspect
import json
from unittest.mock import AsyncMock, MagicMock, patch

results = []

def check(name, condition, detail=""):
    status = "PASS" if condition else "FAIL"
    results.append({"name": name, "status": status, "detail": detail})


async def run_tests():
    # ---------------------------------------------------------------------------
    # Test 1: _async_probe_serial_ports does NOT auto-add USB ports
    # ---------------------------------------------------------------------------
    # The old code auto-added all USB serial ports to additional_ports.
    # This added non-HGI devices (e.g. modbus bridges) to the pool.
    # The fix removes the auto-add — the user must manually add serial
    # ports via Manage Pool.
    # ---------------------------------------------------------------------------
    try:
        from custom_components.ramses_cc.coordinator import RamsesCoordinator
        from custom_components.ramses_cc.const import (
            CONF_ADDITIONAL_PORTS,
            CONF_SCHEMA,
            SZ_TR_OWNER,
        )
        from ramses_tx.schemas import SZ_PORT_NAME, SZ_SERIAL_PORT
        from ramses_rf.schemas import SZ_SCHEMA

        # Create a mock coordinator
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

        # Simulate 2 USB ports found
        with patch("glob.glob", return_value=["/dev/ttyACM0", "/dev/ttyACM1"]):
            await RamsesCoordinator._async_probe_serial_ports(
                coord, "/dev/ttyACM0", None
            )

        # Check if additional_ports was modified
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
            "No auto-add of USB ports to additional_ports",
            not auto_added,
            f"auto_added={auto_added}, "
            f"additional={additional if auto_added else '(unchanged)'}",
        )
    except Exception as e:
        check(
            "No auto-add of USB ports to additional_ports",
            False,
            f"exception: {str(e)[:200]}",
        )

    # ---------------------------------------------------------------------------
    # Test 2: _register_pool_hgis adds serial child HGI as candidate
    # ---------------------------------------------------------------------------
    # When a serial port is manually added and the transport probes it
    # with !I, the HGI ID is learned.  _register_pool_hgis should add
    # it to the schema as a discovery candidate (no _owner).
    # ---------------------------------------------------------------------------
    try:
        from custom_components.ramses_cc.coordinator import RamsesCoordinator
        from custom_components.ramses_cc.const import (
            CONF_SCHEMA,
            SZ_TR_OWNER,
        )

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

        # Simulate a pool transport with a discovered child HGI
        mock_transport = MagicMock()
        mock_transport.get_extra_info.return_value = ["18:002222"]
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
        added_as_candidate = False
        if call_args:
            new_schema = call_args.kwargs.get("options", {}).get(
                CONF_SCHEMA, {}
            )
            if "18:002222" in new_schema:
                entry = new_schema["18:002222"]
                added_as_candidate = (
                    isinstance(entry, dict)
                    and entry.get("_class") == "HGI"
                    and SZ_TR_OWNER not in entry
                )

        check(
            "Serial child HGI added as discovery candidate (no _owner)",
            added_as_candidate,
            f"added_as_candidate={added_as_candidate}",
        )
    except Exception as e:
        check(
            "Serial child HGI added as discovery candidate (no _owner)",
            False,
            f"exception: {str(e)[:200]}",
        )

    # ---------------------------------------------------------------------------
    # Test 3: _register_pool_hgis does NOT add non-HGI devices
    # ---------------------------------------------------------------------------
    # A modbus bridge won't respond to !I, so no HGI ID is learned.
    # The pool_hgi_ids list should be empty, and no new schema entries
    # should be added.
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

        # Simulate a pool transport with NO HGI IDs (modbus doesn't
        # respond to !I)
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
            "Non-HGI USB device not added to schema",
            no_spurious,
            f"no_spurious={no_spurious}",
        )
    except Exception as e:
        check(
            "Non-HGI USB device not added to schema",
            False,
            f"exception: {str(e)[:200]}",
        )

    # ---------------------------------------------------------------------------
    # Test 4: Config flow shows schema pool members with serial primary
    # ---------------------------------------------------------------------------
    # The old Phase 1 code only showed schema pool members when the
    # primary was MQTT.  Phase 2 shows them regardless of primary
    # transport type, so the user can manage HGIs in a hybrid pool.
    # We verify this by inspecting the source code — the
    # is_primary_mqtt gate should be removed from the
    # schema_pool_members loop.
    # ---------------------------------------------------------------------------
    try:
        import inspect as _inspect
        from custom_components.ramses_cc import config_flow

        source = _inspect.getsource(config_flow)
        # The old code had:
        #   if is_primary_mqtt or not primary_port:
        #       for dev_id, entry in schema.items():
        # The new code should NOT have this gate.
        old_gate = "if is_primary_mqtt or not primary_port:"
        check(
            "Config flow: no is_primary_mqtt gate on schema_pool_members",
            old_gate not in source,
            f"old_gate_present={old_gate in source}",
        )

        # The new code should have the ungated loop:
        #   for dev_id, entry in schema.items():
        #       if (dev_id.startswith(HGI_PREFIX) ...
        new_pattern = "schema_pool_members: list[str] = []"
        check(
            "Config flow: schema_pool_members list exists",
            new_pattern in source,
            f"pattern_present={new_pattern in source}",
        )
    except Exception as e:
        check(
            "Config flow: schema pool members with serial primary",
            False,
            f"exception: {str(e)[:200]}",
        )

    # ---------------------------------------------------------------------------
    # Test 5: Config flow masks MQTT URLs in current ports
    # ---------------------------------------------------------------------------
    try:
        import inspect as _inspect
        from custom_components.ramses_cc import config_flow

        source = _inspect.getsource(config_flow)
        # The old code had: label = f"MQTT: {port}"
        # The new code should have: label = f"MQTT: {_mask_mqtt_url(port)}"
        old_unmasked = 'label = f"MQTT: {port}"'
        new_masked = 'label = f"MQTT: {_mask_mqtt_url(port)}"'
        check(
            "Config flow: MQTT URLs masked in current ports",
            old_unmasked not in source and new_masked in source,
            f"old_present={old_unmasked in source}, "
            f"new_present={new_masked in source}",
        )
    except Exception as e:
        check(
            "Config flow: MQTT URLs masked in current ports",
            False,
            f"exception: {str(e)[:200]}",
        )

    # ---------------------------------------------------------------------------
    # Test 6: Serial port dropdown uses async_get_usb_ports
    # ---------------------------------------------------------------------------
    try:
        import inspect as _inspect
        from custom_components.ramses_cc import config_flow

        source = _inspect.getsource(config_flow)
        # The old code used serialx.list_serial_ports directly.
        # The new code uses async_get_usb_ports for by-id paths.
        # Check that async_step_manage_pool_serial uses
        # async_get_usb_ports.
        # Find the method source
        sig = _inspect.signature(
            config_flow.RamsesOptionsFlowHandler
            .async_step_manage_pool_serial
        )
        method_source = _inspect.getsource(
            config_flow.RamsesOptionsFlowHandler
            .async_step_manage_pool_serial
        )
        uses_async_get_usb = "async_get_usb_ports" in method_source
        uses_raw_serialx = (
            "from serialx import list_serial_ports" in method_source
        )
        check(
            "Serial port dropdown uses async_get_usb_ports (by-id paths)",
            uses_async_get_usb,
            f"uses_async_get_usb={uses_async_get_usb}, "
            f"uses_raw_serialx={uses_raw_serialx}",
        )
    except Exception as e:
        check(
            "Serial port dropdown uses async_get_usb_ports (by-id paths)",
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
            ctx.check("Recipe 106 executed", False, f"error: {result['error']}")
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
            "All Phase 2 review flow checks passed",
            failed == 0,
            f"{passed} passed, {failed} failed",
        )
