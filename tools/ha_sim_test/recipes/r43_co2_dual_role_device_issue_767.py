"""Recipe R43: CO2 dual-role device — 1298 + 22F1 from same 37: (issue 767).

A 37: prefix device can be both a CO2 sensor (sends I|1298) and a REM
(sends I|22F1).  Today ramses_rf forces one class per device.  Phase 3.75
"init and go" should allow the device to be classified from schema ``_class``
and support both roles.

This recipe SKIPs until dual-role support is implemented.

See: https://github.com/ramses-rf/ramses_cc/issues/767
"""

from __future__ import annotations

from ..base import Recipe, RecipeContext
from ..const import FAN
from ..helpers import (
    call_service,
    docker_exec_python,
    get_entities,
    ws_send,
)


class R43Co2DualRoleDeviceIssue767(Recipe):
    id = "R43"
    seq = 440
    title = "CO2 dual-role device — 1298 + 22F1 from same 37: (issue 767)"

    async def run(self, ctx: RecipeContext) -> None:
        ctx.log_section("Recipe 43: CO2 dual-role device (issue 767)")

        # --- Feature gate: check if dual-role is supported ---
        # The "init and go" pattern would show up as schema-driven class
        # selection.  We check if HvacCarbonDioxideSensor has any REM
        # capability (multi-inheritance or method delegation).
        code = """
import inspect, json
try:
    from ramses_rf.devices.hvac_sensors import HvacCarbonDioxideSensor
    src = inspect.getsource(HvacCarbonDioxideSensor)
    has_remote = (
        "HvacRemote" in src
        or "Remote" in src
        or "send_command" in src
        or "learn_command" in src
    )
    print(json.dumps({"has_remote": has_remote, "ok": True}))
except ImportError as e:
    print(json.dumps({"error": str(e), "ok": False}))
"""
        result = docker_exec_python(code)

        if not result.get("ok"):
            print("  SKIP: HvacCarbonDioxideSensor not importable — pending ramses_rf")
            return

        if not result.get("has_remote"):
            print(
                "  SKIP: dual-role CO2+REM not supported — "
                "pending ramses_rf Phase 3.75 'init and go'"
            )
            return

        print("  Dual-role support detected — running full test body")

        # --- Full test body (runs only when dual-role is supported) ---

        # 1. Load fresh_start
        print("  Loading fresh_start profile...")
        try:
            await ws_send(
                ctx.token,
                {
                    "type": "ramses_extras/device_simulator/load_profile",
                    "profile": "fresh_start",
                    "speed": 0.01,
                    "preload_schema": False,
                    "reload_ramses_cc": True,
                    "enable_auto_answer": True,
                },
            )
        except RuntimeError as e:
            print(f"  Profile load failed: {e}")
        ctx.wait(15, "for ramses_cc reload")
        ctx.refresh_token()
        ctx.wait(5, "for ramses_cc to initialize")

        dual_role_id = "37:153002"

        # 2. Inject 1298 I from 37:153002 to FAN (CO2 reading)
        print(f"  Injecting 1298 I from {dual_role_id} to {FAN} (CO2 reading)...")
        try:
            call_service(
                ctx.token,
                "ramses_extras",
                "device_simulator_inject_message",
                {
                    "source_id": dual_role_id,
                    "dest_id": FAN,
                    "code": "1298",
                    "payload": "00C80300",
                    "verb": "I",
                },
            )
            print("    1298 I injected")
        except RuntimeError as e:
            print(f"    Inject failed: {str(e)[:80]}")
        ctx.wait(5, "for CO2 classification")

        # 3. Inject 22F1 I from 37:153002 to FAN (REM command)
        print(f"  Injecting 22F1 I from {dual_role_id} to {FAN} (REM command)...")
        try:
            call_service(
                ctx.token,
                "ramses_extras",
                "device_simulator_inject_message",
                {
                    "source_id": dual_role_id,
                    "dest_id": FAN,
                    "code": "22F1",
                    "payload": "000307",
                    "verb": "I",
                },
            )
            print("    22F1 I injected")
        except RuntimeError as e:
            print(f"    Inject failed: {str(e)[:80]}")
        ctx.wait(10, "for dual-role classification")

        # 4. Verify the device has both sensor and remote entities
        entities = get_entities(ctx.token)
        normalized = dual_role_id.replace(":", "_")

        sensor_entity = None
        remote_entity = None
        for e in entities:
            eid = e["entity_id"]
            if normalized not in eid:
                continue
            if eid.startswith(("sensor.", "co2_")):
                sensor_entity = e
            elif eid.startswith(("remote.", "rem_")):
                remote_entity = e

        ctx.check(
            f"dual-role device {dual_role_id} has sensor entity",
            sensor_entity is not None,
            "no sensor entity found",
        )

        ctx.check(
            f"dual-role device {dual_role_id} has remote entity",
            remote_entity is not None,
            "no remote entity found",
        )
