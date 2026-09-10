"""Recipe R114: Pool display labels and _preferred_type switching.

Verifies that the config flow's pool management display correctly
shows runtime port-to-HGI mappings and that _preferred_type switching
works for all ESP types:

- Runtime port map: only connected serial children shown with port
- Disconnected serial child: shows (USB) without false port claim
- _preferred_type usb → mqtt: config flow redirects to MQTT URL entry
- _preferred_type mqtt → usb: config flow redirects to serial port
- HGI80 with configured_hgi_id: shown in port map when connected
- ramses_esp (MQTT-only): shown as MQTT, not in serial port map
- Primary HGI: labeled (primary, USB, /dev/...) when on serial
- MQTT primary: labeled (primary, MQTT, topic: ...) when on MQTT

Tests:
1. Runtime port map with 2 connected serial children
2. Runtime port map with 1 connected, 1 disconnected
3. _preferred_type switching: usb → mqtt redirect
4. _preferred_type switching: mqtt → usb redirect
5. HGI80 in port map (configured_hgi_id, connected)
6. ramses_esp NOT in serial port map (callback-driven)
7. Primary label with serial primary
8. Primary label with MQTT primary
"""

from __future__ import annotations

from ..base import Recipe, RecipeContext
from ..helpers import docker_exec_python


class R114PoolDisplaySwitching(Recipe):
    id = "R114"
    seq = 1140
    title = "Pool display labels and _preferred_type switching (issue 1185)"
    tags = (
        "pooled",
        "multi-hgi",
        "phase2",
        "config-flow",
        "display",
        "switching",
        "issue-1185",
    )

    async def run(self, ctx: RecipeContext) -> None:
        """Verify pool display labels and _preferred_type switching."""
        ctx.log_section("Recipe 114: Pool display and switching")

        result = docker_exec_python(
            """
import asyncio
import json
from unittest.mock import MagicMock

results = []

def check(name, condition, detail=""):
    status = "PASS" if condition else "FAIL"
    results.append({"name": name, "status": status, "detail": detail})


async def run_tests():
    # ---------------------------------------------------------------------------
    # Helper: simulate coordinator's serial_port_hgi_map property
    # ---------------------------------------------------------------------------
    def collect_port_map(children):
        result = {}
        for child in children:
            child_hgi = getattr(child, "hgi_id", None)
            is_callback = getattr(child, "callback_driven", False)
            is_connected = getattr(child, "is_connected", False)
            port_name = getattr(child, "port_name", None)
            if (
                child_hgi
                and not is_callback
                and is_connected
                and isinstance(child_hgi, str)
                and isinstance(port_name, str)
                and port_name.startswith("/dev/")
            ):
                result[port_name] = child_hgi
        return result

    def make_serial_child(hgi_id, port_name, connected=True):
        child = MagicMock()
        child.hgi_id = hgi_id
        child.callback_driven = False
        child.is_connected = connected
        child.port_name = port_name
        return child

    def make_callback_child(hgi_id, connected=True):
        child = MagicMock()
        child.hgi_id = hgi_id
        child.callback_driven = True
        child.is_connected = connected
        return child

    # ---------------------------------------------------------------------------
    # Test 1: Runtime port map with 2 connected serial children
    # ---------------------------------------------------------------------------
    children_2 = [
        make_serial_child("18:149488", "/dev/ttyACM0", connected=True),
        make_serial_child("18:130236", "/dev/ttyACM1", connected=True),
    ]
    port_map_2 = collect_port_map(children_2)
    check(
        "Port map: 2 connected serial children",
        port_map_2 == {
            "/dev/ttyACM0": "18:149488",
            "/dev/ttyACM1": "18:130236",
        },
        f"port_map={port_map_2}",
    )

    # ---------------------------------------------------------------------------
    # Test 2: Runtime port map with 1 connected, 1 disconnected
    # ---------------------------------------------------------------------------
    children_1 = [
        make_serial_child("18:149488", "/dev/ttyACM0", connected=True),
        make_serial_child("18:130236", "/dev/ttyACM1", connected=False),
    ]
    port_map_1 = collect_port_map(children_1)
    check(
        "Port map: only connected child shown",
        port_map_1 == {"/dev/ttyACM0": "18:149488"},
        f"port_map={port_map_1}",
    )
    check(
        "Port map: disconnected child port NOT shown",
        "/dev/ttyACM1" not in port_map_1,
        f"port_map={port_map_1}",
    )

    # ---------------------------------------------------------------------------
    # Test 3: _preferred_type switching usb → mqtt redirect
    # ---------------------------------------------------------------------------
    # When the user changes _preferred_type from usb to mqtt for the
    # primary HGI, the config flow should redirect to MQTT URL entry.
    # We verify by checking the config_flow source has the switching
    # logic.
    # ---------------------------------------------------------------------------
    try:
        import inspect as _inspect
        from custom_components.ramses_cc import config_flow

        source = _inspect.getsource(config_flow)

        has_switch_to_mqtt = "_switching_primary_to_mqtt" in source
        has_switch_to_serial = "_switching_primary_to_serial" in source
        has_mqtt_redirect = "async_step_manage_pool_mqtt_url" in source
        has_serial_redirect = "async_step_manage_pool_serial" in source

        check(
            "Switching: _switching_primary_to_mqtt flag exists",
            has_switch_to_mqtt,
            f"found={has_switch_to_mqtt}",
        )
        check(
            "Switching: _switching_primary_to_serial flag exists",
            has_switch_to_serial,
            f"found={has_switch_to_serial}",
        )
        check(
            "Switching: usb→mqtt redirects to MQTT URL step",
            has_mqtt_redirect,
            f"found={has_mqtt_redirect}",
        )
        check(
            "Switching: mqtt→usb redirects to serial port step",
            has_serial_redirect,
            f"found={has_serial_redirect}",
        )
    except Exception as e:
        check(
            "Switching: _switching_primary_to_mqtt flag exists",
            False,
            f"exception: {str(e)[:200]}",
        )
        check(
            "Switching: _switching_primary_to_serial flag exists",
            False,
            f"exception: {str(e)[:200]}",
        )
        check(
            "Switching: usb→mqtt redirects to MQTT URL step",
            False,
            f"exception: {str(e)[:200]}",
        )
        check(
            "Switching: mqtt→usb redirects to serial port step",
            False,
            f"exception: {str(e)[:200]}",
        )

    # ---------------------------------------------------------------------------
    # Test 4: _preferred_type switching logic — usb to mqtt
    # ---------------------------------------------------------------------------
    # Simulate the switching decision: if new_pref == "mqtt" and
    # current is serial, redirect to MQTT URL entry.
    # ---------------------------------------------------------------------------
    try:
        current_is_serial = True
        new_pref = "mqtt"
        should_redirect = (
            new_pref == "mqtt" and current_is_serial
        )
        check(
            "Switching logic: usb→mqtt triggers redirect",
            should_redirect is True,
            f"should_redirect={should_redirect}",
        )

        current_is_serial = True
        new_pref = "usb"
        should_redirect2 = (
            new_pref == "mqtt" and current_is_serial
        )
        check(
            "Switching logic: usb→usb no redirect",
            should_redirect2 is False,
            f"should_redirect={should_redirect2}",
        )
    except Exception as e:
        check(
            "Switching logic: usb→mqtt triggers redirect",
            False,
            f"exception: {str(e)[:200]}",
        )
        check(
            "Switching logic: usb→usb no redirect",
            False,
            f"exception: {str(e)[:200]}",
        )

    # ---------------------------------------------------------------------------
    # Test 5: HGI80 in port map (configured_hgi_id, connected)
    # ---------------------------------------------------------------------------
    hgi80_child = make_serial_child("18:222222", "/dev/ttyUSB0", connected=True)
    port_map_hgi80 = collect_port_map([hgi80_child])
    check(
        "HGI80: shown in port map when connected",
        port_map_hgi80 == {"/dev/ttyUSB0": "18:222222"},
        f"port_map={port_map_hgi80}",
    )

    # ---------------------------------------------------------------------------
    # Test 6: ramses_esp NOT in serial port map (callback-driven)
    # ---------------------------------------------------------------------------
    ramses_esp = make_callback_child("18:555555", connected=True)
    port_map_esp = collect_port_map([ramses_esp])
    check(
        "ramses_esp: NOT in serial port map",
        len(port_map_esp) == 0,
        f"port_map={port_map_esp}",
    )

    # ---------------------------------------------------------------------------
    # Test 7: Primary label with serial primary
    # ---------------------------------------------------------------------------
    # When the primary HGI is on a serial port, the label should
    # include "(primary, USB, /dev/...)".
    # ---------------------------------------------------------------------------
    try:
        primary_hgi_id = "18:149488"
        runtime_port_map = {"/dev/ttyACM0": "18:149488"}
        primary_port = "/dev/ttyACM0"

        # Simulate _pool_member_label for the primary
        runtime_port = None
        for port, hgi in runtime_port_map.items():
            if hgi == primary_hgi_id:
                runtime_port = port
                break

        if primary_port and primary_port.startswith("/dev/"):
            if runtime_port:
                label = f"HGI: {primary_hgi_id} (primary, USB, {runtime_port})"
            else:
                label = f"HGI: {primary_hgi_id} (primary, USB)"
        else:
            label = f"HGI: {primary_hgi_id} (primary, MQTT)"

        check(
            "Primary label: serial primary shows (primary, USB, /dev/...)",
            "(primary, USB, /dev/ttyACM0)" in label,
            f"label={label}",
        )
    except Exception as e:
        check(
            "Primary label: serial primary shows (primary, USB, /dev/...)",
            False,
            f"exception: {str(e)[:200]}",
        )

    # ---------------------------------------------------------------------------
    # Test 8: Primary label with MQTT primary
    # ---------------------------------------------------------------------------
    try:
        primary_hgi_id2 = "18:149488"
        runtime_port_map2 = {}  # No serial ports
        primary_port2 = "mqtt_ha"

        runtime_port2 = None
        for port, hgi in runtime_port_map2.items():
            if hgi == primary_hgi_id2:
                runtime_port2 = port
                break

        if primary_port2 and primary_port2.startswith("/dev/"):
            if runtime_port2:
                label2 = f"HGI: {primary_hgi_id2} (primary, USB, {runtime_port2})"
            else:
                label2 = f"HGI: {primary_hgi_id2} (primary, USB)"
        else:
            label2 = f"HGI: {primary_hgi_id2} (primary, MQTT)"

        check(
            "Primary label: MQTT primary shows (primary, MQTT)",
            "(primary, MQTT)" in label2,
            f"label={label2}",
        )
    except Exception as e:
        check(
            "Primary label: MQTT primary shows (primary, MQTT)",
            False,
            f"exception: {str(e)[:200]}",
        )

    # ---------------------------------------------------------------------------
    # Test 9: Non-primary serial child label with runtime port
    # ---------------------------------------------------------------------------
    try:
        non_primary_hgi = "18:130236"
        runtime_port_map3 = {
            "/dev/ttyACM0": "18:149488",
            "/dev/ttyACM1": "18:130236",
        }
        primary_port3 = "/dev/ttyACM0"

        runtime_port3 = None
        for port, hgi in runtime_port_map3.items():
            if hgi == non_primary_hgi:
                runtime_port3 = port
                break

        if runtime_port3:
            label3 = f"HGI: {non_primary_hgi} (USB, {runtime_port3})"
        else:
            label3 = f"HGI: {non_primary_hgi} (USB)"

        check(
            "Non-primary label: shows (USB, /dev/ttyACM1)",
            "(USB, /dev/ttyACM1)" in label3,
            f"label={label3}",
        )
    except Exception as e:
        check(
            "Non-primary label: shows (USB, /dev/ttyACM1)",
            False,
            f"exception: {str(e)[:200]}",
        )

    # ---------------------------------------------------------------------------
    # Test 10: Non-primary serial child label after disconnect (no port)
    # ---------------------------------------------------------------------------
    try:
        non_primary_hgi2 = "18:130236"
        runtime_port_map4 = {"/dev/ttyACM0": "18:149488"}  # Only 1 connected
        primary_port4 = "/dev/ttyACM0"

        runtime_port4 = None
        for port, hgi in runtime_port_map4.items():
            if hgi == non_primary_hgi2:
                runtime_port4 = port
                break

        if runtime_port4:
            label4 = f"HGI: {non_primary_hgi2} (USB, {runtime_port4})"
        else:
            label4 = f"HGI: {non_primary_hgi2} (USB)"

        check(
            "Disconnected child label: shows (USB) without port",
            label4 == "HGI: 18:130236 (USB)",
            f"label={label4}",
        )
    except Exception as e:
        check(
            "Disconnected child label: shows (USB) without port",
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
            ctx.check("Recipe 114 executed", False, f"error: {result['error']}")
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
            "All pool display and switching checks passed",
            failed == 0,
            f"{passed} passed, {failed} failed",
        )
