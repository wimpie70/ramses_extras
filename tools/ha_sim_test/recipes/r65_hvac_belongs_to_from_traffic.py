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
It then verifies:
  1. The schema BEFORE: FAN has empty remotes/sensors, devices in orphans
  2. The schema AFTER: REM in remotes[], CO2 in sensors[], not in orphans
  3. The "belongs to" comment appears in device_comments
  4. The comment does NOT use "bound to" (reserved for heat domain)
  5. The schema persists across a coordinator reload (roundtrip)

See: https://github.com/ramses-rf/ramses_cc/issues/767
"""

from __future__ import annotations

import json

from ..base import Recipe, RecipeContext
from ..const import CO2, FAN, REM
from ..helpers import (
    get_schema_retry,
    load_profile_yaml,
    wait_for,
)
from ..profile import mixed_yaml


def _dump_fan_schema(schema: dict, label: str) -> None:
    """Print the FAN entry and orphans_hvac for debugging."""
    fan_entry = schema.get(FAN, {})
    orphans = schema.get("orphans_hvac", [])
    comments = schema.get("device_comments", {})
    print(f"  --- {label} ---")
    print(f"  FAN {FAN}: {json.dumps(fan_entry, sort_keys=True)}")
    print(f"  orphans_hvac: {orphans}")
    for dev in (REM, CO2):
        c = comments.get(dev, "")
        if c:
            print(f"  {dev} comment: {c[:160]}")
    print()


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

        # 2. Capture the BEFORE state: FAN has no remotes/sensors,
        #    REM/CO2 should be in orphans_hvac.
        schema = get_schema_retry()
        fan_entry = schema.get(FAN, {}) if schema else {}
        remotes_before = (
            fan_entry.get("remotes", []) if isinstance(fan_entry, dict) else []
        )
        sensors_before = (
            fan_entry.get("sensors", []) if isinstance(fan_entry, dict) else []
        )
        orphans_before = schema.get("orphans_hvac", []) if schema else []

        _dump_fan_schema(
            schema if schema else {}, "BEFORE (schema loaded, no traffic yet)"
        )

        ctx.check(
            "FAN starts with empty remotes[]",
            remotes_before == [],
            f"remotes={remotes_before}",
        )
        ctx.check(
            "FAN starts with empty sensors[]",
            sensors_before == [],
            f"sensors={sensors_before}",
        )

        # 3. Wait for the scan engine to detect FAN→REM/CO2 traffic.
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

        # 4. Capture the AFTER state: REM in remotes[], CO2 in sensors[].
        fan_entry = schema.get(FAN, {}) if schema else {}
        remotes_after = (
            fan_entry.get("remotes", []) if isinstance(fan_entry, dict) else []
        )
        sensors_after = (
            fan_entry.get("sensors", []) if isinstance(fan_entry, dict) else []
        )
        orphans_after = schema.get("orphans_hvac", []) if schema else []

        _dump_fan_schema(
            schema if schema else {},
            "AFTER (traffic detected + sync_learned_topology)",
        )

        ctx.check(
            f"REM {REM} in FAN's remotes[] (from traffic 'belongs to')",
            REM in remotes_after,
            f"remotes={remotes_after}, orphans_hvac={orphans_after}",
        )

        ctx.check(
            f"CO2 {CO2} in FAN's sensors[] (from traffic 'belongs to')",
            CO2 in sensors_after,
            f"sensors={sensors_after}, orphans_hvac={orphans_after}",
        )

        ctx.check(
            f"REM {REM} not in orphans_hvac (placed under FAN)",
            REM not in orphans_after,
            f"orphans_hvac={orphans_after}",
        )

        ctx.check(
            f"CO2 {CO2} not in orphans_hvac (placed under FAN)",
            CO2 not in orphans_after,
            f"orphans_hvac={orphans_after}",
        )

        # orphans_hvac may already be empty before (schema preload doesn't
        # put REM/CO2 in orphans), so only check it shrank if it was non-empty.
        if orphans_before:
            ctx.check(
                "orphans_hvac shrank (REM/CO2 moved out)",
                len(orphans_after) < len(orphans_before),
                f"before={orphans_before}, after={orphans_after}",
            )

        # 5. Wait for the "belongs to" comment to appear in device_comments.
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
            print(f"  REM comment: {rem_comment[:160]}")
        if co2_comment:
            print(f"  CO2 comment: {co2_comment[:160]}")

        ctx.check(
            f"REM {REM} comment has 'belongs to {FAN}'",
            f"belongs to {FAN}" in rem_comment,
            f"comment={rem_comment[:160]}",
        )

        ctx.check(
            f"REM comment does NOT use 'bound to {FAN}' (reserved for heat)",
            f"bound to {FAN}" not in rem_comment,
            f"comment={rem_comment[:160]}",
        )

        # 6. Roundtrip: reload ramses_cc and verify the schema persists.
        #    The "belongs to" comment + remotes[]/sensors[] should survive
        #    a coordinator restart via gateway.schema() → save_state → reload.
        print("  Roundtrip: reloading ramses_cc to verify schema persists...")
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
            print(f"  Profile reload failed: {e}")
        ctx.wait_for_ramses_cc_reload(timeout=20)
        ctx.refresh_token()
        ctx.wait(5, "for schema to settle after reload")

        schema_rt = get_schema_retry()
        fan_entry_rt = schema_rt.get(FAN, {}) if schema_rt else {}
        remotes_rt = (
            fan_entry_rt.get("remotes", []) if isinstance(fan_entry_rt, dict) else []
        )
        sensors_rt = (
            fan_entry_rt.get("sensors", []) if isinstance(fan_entry_rt, dict) else []
        )
        orphans_rt = schema_rt.get("orphans_hvac", []) if schema_rt else []

        _dump_fan_schema(
            schema_rt if schema_rt else {},
            "AFTER RELOAD (roundtrip persistence)",
        )

        ctx.check(
            f"REM {REM} still in remotes[] after reload",
            REM in remotes_rt,
            f"remotes={remotes_rt}",
        )

        ctx.check(
            f"CO2 {CO2} still in sensors[] after reload",
            CO2 in sensors_rt,
            f"sensors={sensors_rt}",
        )

        ctx.check(
            f"REM {REM} still not in orphans_hvac after reload",
            REM not in orphans_rt,
            f"orphans_hvac={orphans_rt}",
        )

        # The "belongs to" comment is NOT persisted — it's regenerated by
        # refresh_device_comments from the scan engine's bound_to, which
        # needs to see traffic again after the reload.  Wait for it.
        print("  Waiting for 'belongs to' comment to reappear after reload...")
        rem_comment_rt = ""
        for attempt in range(8):
            ctx.wait(5, f"for comment re-refresh (attempt {attempt + 1}/8)")
            schema_rt = get_schema_retry()
            comments_rt = schema_rt.get("device_comments", {}) if schema_rt else {}
            rem_comment_rt = comments_rt.get(REM, "")
            if f"belongs to {FAN}" in rem_comment_rt:
                print("    'belongs to' comment reappeared after reload")
                break
        else:
            print("    INFO: 'belongs to' comment not yet present after 40s")

        if rem_comment_rt:
            print(f"  REM comment after reload: {rem_comment_rt[:160]}")

        ctx.check(
            f"REM comment has 'belongs to {FAN}' after reload",
            f"belongs to {FAN}" in rem_comment_rt,
            f"comment={rem_comment_rt[:160]}",
        )
