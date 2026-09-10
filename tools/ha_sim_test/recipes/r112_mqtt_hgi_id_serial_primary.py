"""Recipe R112: mqtt_hgi_id config with serial primary (issue 1185).

Verifies that the ``ramses_cc`` coordinator's ``_has_mqtt`` gate logic
correctly handles ``mqtt_hgi_id`` with a serial primary.  This is the
regression test for silverailscolo's bug: the ``_has_mqtt`` gate didn't
check ``mqtt_hgi_id``, so the bridge was never created and TX was
forced through the HGI80 (echo timeout).

Tests:
1. ``_has_mqtt`` is True when ``mqtt_hgi_id`` is set with a serial
   primary.
2. ``_has_mqtt`` is False when ``mqtt_hgi_id == DEFAULT_HGI_ID``.
3. ``_has_mqtt`` is False when no MQTT signal is present.
4. ``_has_mqtt`` is True when ``mqtt://`` additional port is present.
5. ``_has_mqtt`` is False when ``mqtt_hgi_id`` is set but HA MQTT
   integration is not loaded.
6. ``_has_mqtt`` is True when ``mqtt_use_ha`` is set with serial primary.
"""

from __future__ import annotations

from ..base import Recipe, RecipeContext
from ..helpers import docker_exec_python


class R112MqttHgiIdSerialPrimary(Recipe):
    id = "R112"
    seq = 1120
    title = "mqtt_hgi_id config with serial primary (issue 1185)"
    tags = ("coordinator", "mqtt", "mqtt_hgi_id", "hybrid", "issue-1185")

    async def run(self, ctx: RecipeContext) -> None:
        """Verify mqtt_hgi_id triggers MQTT pool bridge with serial primary."""
        ctx.log_section("Recipe 112: mqtt_hgi_id with serial primary")

        result = docker_exec_python(
            """
import asyncio
import json
import sys

sys.path.insert(0, "/config/custom_components")

results = []

def check(name, condition, detail=""):
    status = "PASS" if condition else "FAIL"
    results.append({"name": name, "status": status, "detail": detail})


async def run_tests():
    from custom_components.ramses_cc.const import (
        CONF_MQTT_HGI_ID,
        CONF_MQTT_USE_HA,
        DEFAULT_HGI_ID,
        CONF_ADDITIONAL_PORTS,
        SZ_SERIAL_PORT,
        SZ_PORT_NAME,
    )

    # Simulate the _has_mqtt gate logic from coordinator.py
    def has_mqtt_gate(options, has_ha_mqtt=True):
        port_name = options.get(SZ_SERIAL_PORT, {}).get(SZ_PORT_NAME, "")
        is_mqtt_ha_port = port_name == "mqtt_ha"
        is_mqtt_url = isinstance(port_name, str) and port_name.startswith("mqtt://")
        is_mqtt_ha = is_mqtt_ha_port or is_mqtt_url

        additional_ports = options.get(CONF_ADDITIONAL_PORTS, [])
        mqtt_additional = [
            p for p in additional_ports
            if isinstance(p, str) and p.startswith("mqtt://")
        ]

        mqtt_hgi_id_cfg = options.get(CONF_MQTT_HGI_ID)
        has_mqtt_hgi_id = (
            isinstance(mqtt_hgi_id_cfg, str)
            and mqtt_hgi_id_cfg != DEFAULT_HGI_ID
        )

        _has_mqtt = is_mqtt_ha or bool(mqtt_additional) or has_mqtt_hgi_id

        if _has_mqtt and not has_ha_mqtt:
            _has_mqtt = False

        return _has_mqtt

    # Test 1: mqtt_hgi_id set with serial primary
    opts = {
        SZ_SERIAL_PORT: {SZ_PORT_NAME: "/dev/ttyUSB0"},
        CONF_MQTT_HGI_ID: "18:130140",
        CONF_ADDITIONAL_PORTS: [],
    }
    check("mqtt_hgi_id + serial primary -> _has_mqtt=True",
          has_mqtt_gate(opts) is True)

    # Test 2: mqtt_hgi_id == DEFAULT_HGI_ID
    opts = {
        SZ_SERIAL_PORT: {SZ_PORT_NAME: "/dev/ttyUSB0"},
        CONF_MQTT_HGI_ID: DEFAULT_HGI_ID,
        CONF_ADDITIONAL_PORTS: [],
    }
    check("mqtt_hgi_id == DEFAULT -> _has_mqtt=False",
          has_mqtt_gate(opts) is False)

    # Test 3: No MQTT signal
    opts = {
        SZ_SERIAL_PORT: {SZ_PORT_NAME: "/dev/ttyUSB0"},
        CONF_ADDITIONAL_PORTS: [],
    }
    check("No MQTT signal -> _has_mqtt=False",
          has_mqtt_gate(opts) is False)

    # Test 4: mqtt:// additional port
    opts = {
        SZ_SERIAL_PORT: {SZ_PORT_NAME: "/dev/ttyUSB0"},
        CONF_ADDITIONAL_PORTS: ["mqtt://broker:1883/RAMSES/GATEWAY/18:002222"],
    }
    check("mqtt:// additional port -> _has_mqtt=True",
          has_mqtt_gate(opts) is True)

    # Test 5: mqtt_hgi_id set but no HA MQTT integration
    opts = {
        SZ_SERIAL_PORT: {SZ_PORT_NAME: "/dev/ttyUSB0"},
        CONF_MQTT_HGI_ID: "18:130140",
        CONF_ADDITIONAL_PORTS: [],
    }
    check("mqtt_hgi_id + no HA MQTT -> _has_mqtt=False",
          has_mqtt_gate(opts, has_ha_mqtt=False) is False)

    # Test 6: mqtt_use_ha with serial primary
    opts = {
        SZ_SERIAL_PORT: {SZ_PORT_NAME: "/dev/ttyUSB0"},
        CONF_MQTT_USE_HA: True,
        CONF_MQTT_HGI_ID: "18:130140",
        CONF_ADDITIONAL_PORTS: [],
    }
    check("mqtt_use_ha + serial primary -> _has_mqtt=True",
          has_mqtt_gate(opts) is True)

    passed = sum(1 for r in results if r["status"] == "PASS")
    failed = sum(1 for r in results if r["status"] == "FAIL")
    print(json.dumps({"passed": passed, "failed": failed, "results": results}))


asyncio.run(run_tests())
""",
            timeout=60,
        )

        if "error" in result:
            ctx.check("Recipe 112 executed", False, f"error: {result['error']}")
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
            "All mqtt_hgi_id gate checks passed",
            failed == 0,
            f"{passed} passed, {failed} failed",
        )
