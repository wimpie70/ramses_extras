"""Recipe R42: HVAC topology learned from traffic — binding rules (issue 767).

Tests that TopologyBuilder's ``_evaluate_hvac_rules`` emits ``BIND_DEVICE``
events for HVAC, linking REM/CO2 to their parent FAN.

Today ``_evaluate_hvac_rules`` only does class promotion — there is no
``BIND_DEVICE`` for HVAC.  This recipe SKIPs until binding rules are added.

See: https://github.com/ramses-rf/ramses_cc/issues/767
"""

from __future__ import annotations

from ..base import Recipe, RecipeContext
from ..const import CO2, FAN, REM
from ..helpers import (
    call_service,
    docker_exec_python,
    get_schema_retry,
    ws_send,
)


class R42HvacTopologyBindingRulesIssue767(Recipe):
    id = "R42"
    seq = 430
    title = "HVAC topology learned from traffic — binding rules (issue 767)"

    async def run(self, ctx: RecipeContext) -> None:
        ctx.log_section("Recipe 42: HVAC topology binding rules (issue 767)")

        # --- Feature gate: _evaluate_hvac_rules must emit BIND_DEVICE ---
        code = """
import inspect, json
try:
    from ramses_rf.pipeline.topology_builder import TopologyBuilder
    src = inspect.getsource(TopologyBuilder._evaluate_hvac_rules)
    has_bind = "BIND_DEVICE" in src
    print(json.dumps({"has_bind": has_bind, "ok": True}))
except (ImportError, AttributeError) as e:
    print(json.dumps({"error": str(e), "ok": False}))
"""
        result = docker_exec_python(code)

        if not result.get("ok"):
            print(
                "  SKIP: TopologyBuilder._evaluate_hvac_rules not "
                "importable — pending ramses_rf"
            )
            return

        if not result.get("has_bind"):
            print(
                "  SKIP: TopologyBuilder._evaluate_hvac_rules has no "
                "BIND_DEVICE rules — pending ramses_rf HVAC topology PR"
            )
            return

        print("  HVAC BIND_DEVICE rules detected — running full test body")

        # --- Full test body (runs only when HVAC binding rules exist) ---

        # 1. Load fresh_start_allow_unknown_devices (no enforce_known_list)
        #    We need unknown devices to be accepted so TopologyBuilder can
        #    learn HVAC bindings from traffic.  With enforce_known_list=True
        #    (plain fresh_start), packets from unknown FAN/REM/CO2 would be
        #    filtered out before TopologyBuilder sees them.
        print(
            "  Loading fresh_start_allow_unknown_devices profile "
            "(enforce_known_list disabled)..."
        )
        try:
            await ws_send(
                ctx.token,
                {
                    "type": "ramses_extras/device_simulator/load_profile",
                    "profile": "fresh_start_allow_unknown_devices",
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

        # 2. Inject 31D9 I from FAN (32:150000) — FAN announces itself
        print(f"  Injecting 31D9 I from FAN {FAN}...")
        try:
            call_service(
                ctx.token,
                "ramses_extras",
                "device_simulator_inject_message",
                {
                    "source_id": FAN,
                    "code": "31D9",
                    "payload": "000A040020202020202020202020202008",
                    "verb": "I",
                },
            )
            print("    31D9 I injected")
        except RuntimeError as e:
            print(f"    Inject failed: {str(e)[:80]}")
        ctx.wait(5, "for FAN class promotion")

        # 3. Inject 22F1 I from REM (37:170000) to FAN (32:150000)
        #    This should create a BIND_DEVICE event linking REM to FAN
        print(f"  Injecting 22F1 I from REM {REM} to FAN {FAN}...")
        try:
            call_service(
                ctx.token,
                "ramses_extras",
                "device_simulator_inject_message",
                {
                    "source_id": REM,
                    "dest_id": FAN,
                    "code": "22F1",
                    "payload": "000307",
                    "verb": "I",
                },
            )
            print("    22F1 I injected")
        except RuntimeError as e:
            print(f"    Inject failed: {str(e)[:80]}")
        ctx.wait(5, "for REM binding")

        # 4. Inject 1298 I from CO2 (37:120000) to FAN (32:150000)
        #    This should create a BIND_DEVICE event linking CO2 to FAN
        print(f"  Injecting 1298 I from CO2 {CO2} to FAN {FAN}...")
        try:
            call_service(
                ctx.token,
                "ramses_extras",
                "device_simulator_inject_message",
                {
                    "source_id": CO2,
                    "dest_id": FAN,
                    "code": "1298",
                    "payload": "00C80300",
                    "verb": "I",
                },
            )
            print("    1298 I injected")
        except RuntimeError as e:
            print(f"    Inject failed: {str(e)[:80]}")
        ctx.wait(10, "for topology to settle")

        # 5. Verify schema shows HVAC structure (not orphans_hvac)
        schema = get_schema_retry()
        fan_entry = schema.get(FAN, {})
        orphans_hvac = schema.get("orphans_hvac", [])

        ctx.check(
            f"schema has FAN {FAN} with remotes after binding",
            isinstance(fan_entry, dict) and REM in fan_entry.get("remotes", []),
            f"fan_entry={fan_entry}, orphans_hvac={orphans_hvac}",
        )

        ctx.check(
            f"schema has FAN {FAN} with sensors after binding",
            isinstance(fan_entry, dict) and CO2 in fan_entry.get("sensors", []),
            f"fan_entry={fan_entry}, orphans_hvac={orphans_hvac}",
        )

        ctx.check(
            f"REM {REM} not in orphans_hvac (bound to FAN)",
            REM not in orphans_hvac,
            f"orphans_hvac={orphans_hvac}",
        )

        ctx.check(
            f"CO2 {CO2} not in orphans_hvac (bound to FAN)",
            CO2 not in orphans_hvac,
            f"orphans_hvac={orphans_hvac}",
        )
