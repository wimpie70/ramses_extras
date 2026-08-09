"""Recipe R65: HVAC 'belongs to' FAN detected from traffic.

Tests the traffic-based HVAC parent detection: when a FAN (32:) sends a
directed I/RP packet to a 37: device (REM/CO2), the scan engine sets
``bound_to`` on the 37: device.  ``refresh_device_comments`` writes
"belongs to 32:XXXXXX" in the device comment (distinct from "bound to"
which is the heat-domain TCS binding, and from ``_bound`` which is the
hardware handshake for 2411 routing).

``sync_learned_topology`` then parses the "belongs to" comment and
places the device under the FAN's ``remotes[]`` or ``sensors[]`` list:
  - CO2/HUM → sensors[]
  - REM/DIS/other → remotes[]

This recipe loads the mixed profile with a schema override that strips
the FAN's remotes/sensors, so the binding must be learned from traffic.

See: https://github.com/ramses-rf/ramses_cc/issues/767
"""

from __future__ import annotations

from ..base import Recipe, RecipeContext
from ..const import CO2, FAN, REM
from ..helpers import (
    get_schema_retry,
    load_profile_yaml,
    wait_for,
)
from ..profile import mixed_yaml


class R65HvacBelongsToFromTraffic(Recipe):
    id = "R65"
    seq = 650
    title = "HVAC 'belongs to' FAN detected from traffic"

    async def run(self, ctx: RecipeContext) -> None:
        ctx.log_section("Recipe 65: HVAC 'belongs to' FAN detected from traffic")

        # 1. Load mixed profile with FAN's remotes/sensors stripped.
        #    The FAN keeps _class=FAN and _bound (for 2411 routing) but
        #    has no remotes[]/sensors[] — the topology must be learned
        #    from traffic via the scan engine's bound_to detection.
        print("  Loading mixed profile with FAN remotes/sensors stripped...")
        schema_override = {
            FAN: {
                "_class": "FAN",
                "_bound": REM,  # keep _bound for 2411 routing
            },
        }
        yaml_text = mixed_yaml(schema_override=schema_override)
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
        ctx.wait_for_ramses_cc_reload(timeout=20)
        ctx.refresh_token()

        # Verify the FAN starts with no remotes/sensors
        schema = get_schema_retry()
        fan_entry = schema.get(FAN, {})
        if isinstance(fan_entry, dict):
            print(
                f"  FAN starts with: remotes={fan_entry.get('remotes', [])}, "
                f"sensors={fan_entry.get('sensors', [])}"
            )

        # 2. Wait for the scan engine to detect FAN→REM/CO2 traffic.
        #    The mixed profile's auto_answer generates 2411 RQ from REM→FAN,
        #    which triggers FAN RP→REM (directed).  The scan engine sets
        #    bound_to on the 37: device.  Then refresh_device_comments writes
        #    "belongs to 32:150000" and sync_learned_topology places them
        #    under the FAN.
        #    The coordinator runs save_state every ~30s, which triggers
        #    refresh_device_comments + sync_learned_topology.
        print("  Waiting for scan engine + sync_learned_topology to detect traffic...")
        schema = None
        for attempt in range(10):
            ctx.wait(5, f"for sync cycle (attempt {attempt + 1}/10)")
            schema = get_schema_retry()
            fan_entry = schema.get(FAN, {}) if schema else {}
            if isinstance(fan_entry, dict) and (
                REM in fan_entry.get("remotes", [])
                or CO2 in fan_entry.get("sensors", [])
            ):
                print("    FAN has remotes/sensors from traffic — sync done")
                break
        else:
            print("    WARNING: FAN still has no remotes/sensors after 50s")

        # 3. Verify the schema shows HVAC structure from traffic
        fan_entry = schema.get(FAN, {}) if schema else {}
        remotes = fan_entry.get("remotes", []) if isinstance(fan_entry, dict) else []
        sensors = fan_entry.get("sensors", []) if isinstance(fan_entry, dict) else []
        orphans_hvac = schema.get("orphans_hvac", []) if schema else []

        ctx.check(
            f"REM {REM} in FAN's remotes[] (from traffic 'belongs to')",
            REM in remotes,
            f"remotes={remotes}, orphans_hvac={orphans_hvac}",
        )

        ctx.check(
            f"CO2 {CO2} in FAN's sensors[] (from traffic 'belongs to')",
            CO2 in sensors,
            f"sensors={sensors}, orphans_hvac={orphans_hvac}",
        )

        ctx.check(
            f"REM {REM} not in orphans_hvac (placed under FAN)",
            REM not in orphans_hvac,
            f"orphans_hvac={orphans_hvac}",
        )

        ctx.check(
            f"CO2 {CO2} not in orphans_hvac (placed under FAN)",
            CO2 not in orphans_hvac,
            f"orphans_hvac={orphans_hvac}",
        )

        # 4. Wait for the "belongs to" comment to appear in device_comments.
        #    The scan engine sets bound_to when it sees a FAN (32:) sending a
        #    directed I/RP to a 37: device (e.g. 2411 RP from FAN→REM).
        #    refresh_device_comments writes "belongs to 32:XXXXXX" in the
        #    comment.  This may take a full save_state cycle (~30s).
        print("  Waiting for 'belongs to' comment to appear...")
        rem_comment = ""
        co2_comment = ""
        for attempt in range(8):
            ctx.wait(5, f"for comment refresh (attempt {attempt + 1}/8)")
            schema = get_schema_retry()
            comments = schema.get("device_comments", {}) if schema else {}
            rem_comment = comments.get(REM, "")
            co2_comment = comments.get(CO2, "")
            if f"belongs to {FAN}" in rem_comment or f"belongs to {FAN}" in co2_comment:
                print("    'belongs to' comment found — refresh done")
                break
        else:
            print("    INFO: 'belongs to' comment not yet present after 40s")

        if rem_comment:
            print(f"  REM comment: {rem_comment[:140]}")
        if co2_comment:
            print(f"  CO2 comment: {co2_comment[:140]}")

        ctx.check(
            f"REM {REM} comment has 'belongs to {FAN}'",
            f"belongs to {FAN}" in rem_comment,
            f"comment={rem_comment[:140]}",
        )

        ctx.check(
            f"REM comment does NOT use 'bound to {FAN}' (reserved for heat)",
            f"bound to {FAN}" not in rem_comment,
            f"comment={rem_comment[:140]}",
        )
