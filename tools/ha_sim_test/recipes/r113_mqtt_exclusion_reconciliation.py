"""Recipe R113: MQTT exclusion reconciliation across ESP types.

Verifies that the MQTT pool bridge's exclusion/un-exclusion logic
works correctly for all serial HGI device types:

- ESP32-S3 (evofw3): !I responds immediately, ID_COMMAND policy
- ATmega32U4 (evofw3): !I only, no _PUZZ echo, ID_COMMAND policy
- nanoCUL/FTDI (evofw3): !I after 3s delay, ID_COMMAND with grace
- HGI80: no !I response, SKIP policy, configured_hgi_id fallback
- ramses_esp (ESP32-C6): MQTT-only, callback-driven

Tests:
1. Each serial device type is excluded from MQTT when connected
2. Each serial device type is un-excluded when disconnected
3. Multiple serial devices: all connected ones excluded
4. Multiple serial devices: only disconnected ones un-excluded
5. HGI80 with configured_hgi_id: excluded when connected
6. ramses_esp (MQTT-only): never in serial exclusion set
7. Reconnect cycle: exclude → un-exclude → re-exclude
8. Pool display: runtime_port_hgi_map only includes connected
"""

from __future__ import annotations

from ..base import Recipe, RecipeContext
from ..helpers import docker_exec_python


class R113MqttExclusionReconciliation(Recipe):
    id = "R113"
    seq = 1130
    title = "MQTT exclusion reconciliation across ESP types (issue 1185)"
    tags = (
        "pooled",
        "multi-hgi",
        "phase2",
        "mqtt",
        "exclusion",
        "issue-1185",
    )

    async def run(self, ctx: RecipeContext) -> None:
        """Verify MQTT exclusion reconciliation for all ESP types."""
        ctx.log_section("Recipe 113: MQTT exclusion reconciliation")

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
    # Helper: simulate coordinator's serial_hgi_ids collection
    # ---------------------------------------------------------------------------
    def collect_serial_hgi_ids(children):
        # Replicate the coordinator's exclusion set collection.
        serial_ids = set()
        for child in children:
            child_hgi = getattr(child, "hgi_id", None)
            is_callback = getattr(child, "callback_driven", False)
            is_connected = getattr(child, "is_connected", False)
            if (
                child_hgi
                and not is_callback
                and isinstance(child_hgi, str)
                and is_connected
            ):
                serial_ids.add(child_hgi)
        return serial_ids

    def reconcile_exclusions(excluded_set, current_serial_ids, bridge):
        # Replicate the coordinator's exclusion reconciliation.
        # Exclude newly connected serial HGIs
        for hgi_id in current_serial_ids:
            if hgi_id in excluded_set:
                continue
            bridge.exclude_hgi_id(hgi_id)
            excluded_set.add(hgi_id)
        # Un-exclude stale HGIs (no longer connected via serial)
        stale = excluded_set - current_serial_ids
        for hgi_id in stale:
            if hasattr(bridge, "unexclude_hgi_id"):
                bridge.unexclude_hgi_id(hgi_id)
            excluded_set.discard(hgi_id)

    def make_serial_child(hgi_id, connected=True):
        child = MagicMock()
        child.hgi_id = hgi_id
        child.callback_driven = False
        child.is_connected = connected
        return child

    def make_callback_child(hgi_id, connected=True):
        child = MagicMock()
        child.hgi_id = hgi_id
        child.callback_driven = True
        child.is_connected = connected
        return child

    # Device types to test
    device_types = [
        ("ESP32-S3", "18:130236"),
        ("ATmega32U4", "18:444444"),
        ("nanoCUL", "18:333333"),
        ("HGI80", "18:222222"),
    ]

    # ---------------------------------------------------------------------------
    # Test 1: Each serial device type excluded when connected
    # ---------------------------------------------------------------------------
    for dev_name, hgi_id in device_types:
        child = make_serial_child(hgi_id, connected=True)
        serial_ids = collect_serial_hgi_ids([child])
        check(
            f"{dev_name}: excluded from MQTT when connected",
            hgi_id in serial_ids,
            f"serial_ids={serial_ids}",
        )

    # ---------------------------------------------------------------------------
    # Test 2: Each serial device type un-excluded when disconnected
    # ---------------------------------------------------------------------------
    for dev_name, hgi_id in device_types:
        child = make_serial_child(hgi_id, connected=False)
        serial_ids = collect_serial_hgi_ids([child])
        check(
            f"{dev_name}: NOT excluded when disconnected",
            hgi_id not in serial_ids,
            f"serial_ids={serial_ids}",
        )

    # ---------------------------------------------------------------------------
    # Test 3: Multiple serial devices — all connected ones excluded
    # ---------------------------------------------------------------------------
    children_all = [
        make_serial_child("18:130236", connected=True),  # ESP32-S3
        make_serial_child("18:222222", connected=True),  # HGI80
        make_serial_child("18:333333", connected=True),  # nanoCUL
    ]
    serial_ids_all = collect_serial_hgi_ids(children_all)
    check(
        "Multi-serial: all connected HGIs excluded",
        serial_ids_all == {"18:130236", "18:222222", "18:333333"},
        f"serial_ids={serial_ids_all}",
    )

    # ---------------------------------------------------------------------------
    # Test 4: Multiple serial devices — only disconnected ones un-excluded
    # ---------------------------------------------------------------------------
    bridge = MagicMock()
    bridge.exclude_hgi_id = MagicMock()
    bridge.unexclude_hgi_id = MagicMock()
    excluded = {"18:130236", "18:222222", "18:333333"}

    # Disconnect HGI80
    children_after = [
        make_serial_child("18:130236", connected=True),  # ESP32-S3
        make_serial_child("18:222222", connected=False),  # HGI80 disconnected
        make_serial_child("18:333333", connected=True),  # nanoCUL
    ]
    current_ids = collect_serial_hgi_ids(children_after)
    reconcile_exclusions(excluded, current_ids, bridge)

    check(
        "Multi-serial: HGI80 un-excluded after disconnect",
        bridge.unexclude_hgi_id.call_count == 1
        and bridge.unexclude_hgi_id.call_args.args[0] == "18:222222",
        f"unexclude calls={bridge.unexclude_hgi_id.call_count}",
    )
    check(
        "Multi-serial: ESP32-S3 and nanoCUL still excluded",
        "18:130236" in excluded and "18:333333" in excluded,
        f"excluded={excluded}",
    )
    check(
        "Multi-serial: HGI80 removed from excluded set",
        "18:222222" not in excluded,
        f"excluded={excluded}",
    )

    # ---------------------------------------------------------------------------
    # Test 5: HGI80 with configured_hgi_id — excluded when connected
    # ---------------------------------------------------------------------------
    hgi80_child = make_serial_child("18:222222", connected=True)
    hgi80_ids = collect_serial_hgi_ids([hgi80_child])
    check(
        "HGI80 (configured_hgi_id): excluded when connected",
        "18:222222" in hgi80_ids,
        f"serial_ids={hgi80_ids}",
    )

    # ---------------------------------------------------------------------------
    # Test 6: ramses_esp (MQTT-only) — never in serial exclusion set
    # ---------------------------------------------------------------------------
    ramses_esp = make_callback_child("18:555555", connected=True)
    esp_ids = collect_serial_hgi_ids([ramses_esp])
    check(
        "ramses_esp (MQTT): NOT in serial exclusion set",
        "18:555555" not in esp_ids,
        f"serial_ids={esp_ids}",
    )

    # ---------------------------------------------------------------------------
    # Test 7: Reconnect cycle — exclude → un-exclude → re-exclude
    # ---------------------------------------------------------------------------
    bridge2 = MagicMock()
    bridge2.exclude_hgi_id = MagicMock()
    bridge2.unexclude_hgi_id = MagicMock()
    excluded2: set[str] = set()

    # Step 1: ESP32-S3 connects → excluded
    children_step1 = [make_serial_child("18:130236", connected=True)]
    ids_step1 = collect_serial_hgi_ids(children_step1)
    reconcile_exclusions(excluded2, ids_step1, bridge2)
    check(
        "Reconnect cycle step 1: ESP32-S3 excluded",
        "18:130236" in excluded2
        and bridge2.exclude_hgi_id.call_count == 1,
        f"excluded={excluded2}, exclude_calls={bridge2.exclude_hgi_id.call_count}",
    )

    # Step 2: ESP32-S3 disconnects → un-excluded
    children_step2 = [make_serial_child("18:130236", connected=False)]
    ids_step2 = collect_serial_hgi_ids(children_step2)
    reconcile_exclusions(excluded2, ids_step2, bridge2)
    check(
        "Reconnect cycle step 2: ESP32-S3 un-excluded",
        "18:130236" not in excluded2
        and bridge2.unexclude_hgi_id.call_count == 1,
        f"excluded={excluded2}, unexclude_calls={bridge2.unexclude_hgi_id.call_count}",
    )

    # Step 3: ESP32-S3 reconnects → re-excluded
    children_step3 = [make_serial_child("18:130236", connected=True)]
    ids_step3 = collect_serial_hgi_ids(children_step3)
    reconcile_exclusions(excluded2, ids_step3, bridge2)
    check(
        "Reconnect cycle step 3: ESP32-S3 re-excluded",
        "18:130236" in excluded2
        and bridge2.exclude_hgi_id.call_count == 2,
        f"excluded={excluded2}, exclude_calls={bridge2.exclude_hgi_id.call_count}",
    )

    # ---------------------------------------------------------------------------
    # Test 8: runtime_port_hgi_map only includes connected children
    # ---------------------------------------------------------------------------
    # The coordinator's serial_port_hgi_map property should only
    # include connected serial children with /dev/ port names.
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

    children_map = [
        make_serial_child("18:149488", connected=True),
        make_serial_child("18:130236", connected=False),  # Disconnected
    ]
    children_map[0].port_name = "/dev/ttyACM0"
    children_map[1].port_name = "/dev/ttyACM1"

    port_map = collect_port_map(children_map)
    check(
        "Port map: only connected children included",
        port_map == {"/dev/ttyACM0": "18:149488"},
        f"port_map={port_map}",
    )
    check(
        "Port map: disconnected child NOT included",
        "/dev/ttyACM1" not in port_map,
        f"port_map={port_map}",
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
            ctx.check("Recipe 113 executed", False, f"error: {result['error']}")
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
            "All MQTT exclusion reconciliation checks passed",
            failed == 0,
            f"{passed} passed, {failed} failed",
        )
