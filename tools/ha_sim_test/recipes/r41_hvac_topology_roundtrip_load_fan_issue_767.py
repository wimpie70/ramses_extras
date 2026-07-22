"""Recipe R41: HVAC topology roundtrip — load_fan (issue 767).

Tests the biggest gap in issue 767: ``load_fan`` is a stub.  When
implemented, a FAN with ``remotes: [...]`` and ``sensors: [...]`` in schema
should create bound child devices, and ``gateway.schema()`` should output the
HVAC structure (not flatten to ``orphans_hvac``).

Today ``load_fan`` creates the FAN device but ignores the remotes/sensors
(the ``fan._update_schema(**schema)`` call is commented out as TODO).  This
recipe SKIPs until that TODO is implemented.

See: https://github.com/ramses-rf/ramses_cc/issues/767
"""

from __future__ import annotations

from ..base import Recipe, RecipeContext
from ..const import CO2, FAN, REM
from ..helpers import (
    docker_exec_python,
    get_schema_retry,
    load_profile_yaml,
    ws_send,
)
from ..profile import MIXED_KL, mixed_yaml


class R41HvacTopologyRoundtripLoadFanIssue767(Recipe):
    id = "R41"
    seq = 420
    title = "HVAC topology roundtrip — load_fan (issue 767)"

    async def run(self, ctx: RecipeContext) -> None:
        ctx.log_section("Recipe 41: HVAC topology roundtrip — load_fan (issue 767)")

        # --- Feature gate: load_fan must process schema, not be a stub ---
        code = """
import inspect, json
try:
    from ramses_rf.schemas import load_fan
    src = inspect.getsource(load_fan)
    is_stub = "_update_schema" not in src or "# TODO" in src
    print(json.dumps({"is_stub": is_stub, "ok": True}))
except ImportError as e:
    print(json.dumps({"error": str(e), "ok": False}))
"""
        result = docker_exec_python(code)

        if not result.get("ok"):
            print(
                "  SKIP: ramses_rf.schemas.load_fan not importable — pending ramses_rf"
            )
            return

        if result.get("is_stub"):
            print(
                "  SKIP: load_fan is still a stub "
                "(fan._update_schema commented out) — "
                "pending ramses_rf Phase 3.75 / issue 639"
            )
            return

        print("  load_fan is implemented — running full test body")

        # --- Full test body (runs only when load_fan is live) ---

        # 1. Load mixed profile (has FAN 32:150000 with remotes/sensors)
        print("  Loading mixed profile (FAN + REM + CO2)...")
        yaml_text = mixed_yaml()
        try:
            await load_profile_yaml(
                ctx.token,
                yaml_text,
                speed=0.01,
                preload_schema=True,
                reload_ramses=True,
            )
        except RuntimeError as e:
            print(f"  Profile load failed: {e}")
        ctx.wait(15, "for ramses_cc reload")
        ctx.refresh_token()
        ctx.wait(5, "for ramses_cc to initialize")

        # 2. Verify the config entry schema has HVAC structure
        schema = get_schema_retry()
        fan_entry = schema.get(FAN, {})

        ctx.check(
            f"schema has FAN {FAN} with remotes",
            isinstance(fan_entry, dict)
            and "remotes" in fan_entry
            and REM in fan_entry.get("remotes", []),
            f"fan_entry={fan_entry}",
        )

        ctx.check(
            f"schema has FAN {FAN} with sensors",
            isinstance(fan_entry, dict)
            and "sensors" in fan_entry
            and CO2 in fan_entry.get("sensors", []),
            f"fan_entry={fan_entry}",
        )

        # 3. Verify gateway.schema() outputs HVAC structure (not orphans_hvac)
        #    The roundtrip bug: gateway.schema() flattens HVAC to orphans_hvac
        #    because load_fan doesn't process the schema.
        cached = get_schema_retry()
        orphans_hvac = cached.get("orphans_hvac", [])

        # When load_fan is fixed, the FAN/REM/CO2 should NOT be in
        # orphans_hvac — they should be under the FAN's structure
        ctx.check(
            f"FAN {FAN} not in orphans_hvac (roundtrip fixed)",
            FAN not in orphans_hvac,
            f"FAN found in orphans_hvac: {orphans_hvac}",
        )

        ctx.check(
            f"REM {REM} not in orphans_hvac (bound to FAN)",
            REM not in orphans_hvac,
            f"REM found in orphans_hvac: {orphans_hvac}",
        )

        ctx.check(
            f"CO2 {CO2} not in orphans_hvac (bound to FAN)",
            CO2 not in orphans_hvac,
            f"CO2 found in orphans_hvac: {orphans_hvac}",
        )
