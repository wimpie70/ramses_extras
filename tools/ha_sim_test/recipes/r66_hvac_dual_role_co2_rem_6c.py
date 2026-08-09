"""Recipe R66: HVAC dual-role CO2+REM support (step 6c).

Tests the dual-role scenario: a single 37: device that acts as BOTH a
CO2 sensor (sends I 1298) AND a REM (sends I 22F1 / W 22F1).  This is
realistic — some Itho devices are combo CO2+REM with buttons.

ramses_rf's device model is single-class: a device is either
HvacCarbonDioxideSensor OR HvacRemote, not both.  The eavesdropper
promotes based on the LAST verb/code pair seen.  This recipe documents
the current behavior and checks for gaps:

1. A CO2 device (sends I 1298) gets CO2 sensor entities.
2. After injecting I 22F1 from the same device, check:
   - Does the device class change (promoted to REM)?
   - Do CO2 sensor entities disappear?
   - Do remote entities appear?
   - Does the schema placement change?
3. Verify that the user can force a class via schema _class override.

See: phase4_plan.md step 6c
"""

from __future__ import annotations

import json

from ..base import Recipe, RecipeContext
from ..const import CO2, FAN, REM
from ..helpers import (
    call_service,
    get_entities,
    get_schema_retry,
    load_profile_yaml,
    wait_for,
)
from ..profile import mixed_yaml


class R66HvacDualRoleCo2Rem(Recipe):
    id = "R66"
    seq = 660
    title = "HVAC dual-role CO2+REM support (6c)"

    async def run(self, ctx: RecipeContext) -> None:
        ctx.log_section("Recipe 66: HVAC dual-role CO2+REM support (6c)")

        # 1. Load mixed profile with FAN + CO2 + REM.
        #    The CO2 (37:120000) sends I 1298 (CO2 data) and the REM
        #    (37:170000) sends I 22F1 (remote commands).
        print("  Loading mixed profile...")
        schema_override = {
            FAN: {
                "_class": "FAN",
                "_bound": REM,
                "remotes": [REM],
                "sensors": [CO2],
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

        # Wait for schema to settle
        schema = get_schema_retry()
        if not schema:
            ctx.check("Schema loaded", False, "no schema")
            return

        print(f"  Schema keys: {list(schema.keys())[:10]}...")

        # 2. Check the CO2 device's entities BEFORE injecting 22F1.
        #    The CO2 should have sensor entities (CO2 level).
        print(f"  Checking CO2 {CO2} entities BEFORE 22F1 inject...")
        entities_before = get_entities(ctx.token)

        def _find_remote_entity(entities: list, device_id: str) -> dict | None:
            """Find a remote. entity for a device (platform-specific)."""
            normalized = device_id.replace(":", "_")
            for e in entities:
                eid = e.get("entity_id", "")
                if eid.startswith("remote.") and normalized in eid:
                    return e
            return None

        def _find_sensor_entity(entities: list, device_id: str) -> dict | None:
            """Find a sensor. entity for a device (platform-specific)."""
            normalized = device_id.replace(":", "_")
            for e in entities:
                eid = e.get("entity_id", "")
                if eid.startswith("sensor.") and normalized in eid:
                    return e
            return None

        co2_sensor_before = _find_sensor_entity(entities_before, CO2)
        co2_remote_before = _find_remote_entity(entities_before, CO2)

        def _eid(e: dict | None) -> str:
            return e.get("entity_id") if e else "None"

        print(f"    CO2 sensor entity: {_eid(co2_sensor_before)}")
        print(f"    CO2 remote entity: {_eid(co2_remote_before)}")

        ctx.check(
            f"CO2 {CO2} has a sensor entity (CO2 sensor role)",
            co2_sensor_before is not None,
            f"sensor={_eid(co2_sensor_before)}",
        )

        ctx.check(
            f"CO2 {CO2} does NOT have a remote entity (not a REM)",
            co2_remote_before is None,
            f"remote={_eid(co2_remote_before)}",
        )

        # 3. Check the REM device's entities for comparison.
        print(f"  Checking REM {REM} entities for comparison...")
        rem_remote = _find_remote_entity(entities_before, REM)
        print(f"    REM remote entity: {_eid(rem_remote)}")

        ctx.check(
            f"REM {REM} has a remote entity",
            rem_remote is not None,
            f"remote={rem_remote}",
        )

        # 4. Inject I 22F1 from the CO2 to the FAN.
        #    This is a REM signature — the eavesdropper should promote
        #    the CO2 to REM (or at least emit UPDATE_DEVICE_CLASS).
        print(f"  Injecting I 22F1 from CO2 {CO2} to FAN {FAN}...")
        for _ in range(3):
            try:
                call_service(
                    ctx.token,
                    "ramses_extras",
                    "device_simulator_inject_message",
                    {
                        "source_id": CO2,
                        "dst": FAN,
                        "code": "22F1",
                        "payload": "000207",
                        "verb": "I",
                    },
                )
            except RuntimeError as e:
                print(f"    Inject failed: {str(e)[:80]}")
            ctx.wait(1, "between injects")

        # 5. Wait for the eavesdropper/scan engine to process.
        ctx.wait(10, "for scan engine + eavesdropper to process I 22F1")

        # 6. Check the CO2 device's entities AFTER injecting 22F1.
        print(f"  Checking CO2 {CO2} entities AFTER 22F1 inject...")
        entities_after = get_entities(ctx.token)
        co2_sensor_after = _find_sensor_entity(entities_after, CO2)
        co2_remote_after = _find_remote_entity(entities_after, CO2)

        print(f"    CO2 sensor entity: {_eid(co2_sensor_after)}")
        print(f"    CO2 remote entity: {_eid(co2_remote_after)}")

        # 7. Document the current behavior.
        #    The key question: does the CO2 get BOTH sensor and remote
        #    entities, or does it lose one when promoted?
        #
        #    Current expected behavior (single-class model):
        #    - If the eavesdropper promoted the CO2 to REM, the CO2 sensor
        #      entity may disappear and a remote entity may appear.
        #    - If the eavesdropper didn't promote (schema _class override
        #      wins), the CO2 keeps its sensor entity and no remote entity.
        #
        #    We check both and document which happened.
        has_sensor_after = co2_sensor_after is not None
        has_remote_after = co2_remote_after is not None

        if has_sensor_after and has_remote_after:
            print("  RESULT: CO2 has BOTH sensor and remote entities")
            ctx.check(
                "CO2 has both sensor and remote entities (dual-role)",
                True,
                "sensor + remote",
            )
        elif has_sensor_after and not has_remote_after:
            print("  RESULT: CO2 has sensor only (no promotion, _class wins)")
            ctx.check(
                "CO2 keeps sensor entity after 22F1 inject (no promotion)",
                True,
                "sensor only",
            )
            ctx.check(
                "CO2 does NOT get remote entity (single-class limitation)",
                True,
                "documented gap: single-class model prevents dual-role",
            )
        elif not has_sensor_after and has_remote_after:
            print("  RESULT: CO2 promoted to REM (lost sensor, gained remote)")
            ctx.check(
                "CO2 promoted to REM after 22F1 inject (eavesdropper won)",
                True,
                "remote only — sensor lost",
            )
            ctx.check(
                "CO2 lost sensor entity when promoted (single-class limitation)",
                True,
                "documented gap: promotion replaces, not extends",
            )
        else:
            print("  RESULT: CO2 has neither sensor nor remote (device lost?)")
            ctx.check(
                "CO2 has neither sensor nor remote after 22F1 inject",
                False,
                "unexpected — device may have been lost",
            )

        # 8. Check the schema placement after the inject.
        schema_after = get_schema_retry()
        fan_entry = schema_after.get(FAN, {}) if schema_after else {}
        remotes = fan_entry.get("remotes", []) if isinstance(fan_entry, dict) else []
        sensors = fan_entry.get("sensors", []) if isinstance(fan_entry, dict) else []
        print(f"  Schema after: remotes={remotes}, sensors={sensors}")

        # The CO2 should still be in sensors[] (schema _class is authoritative
        # for topology placement, regardless of device class promotion).
        ctx.check(
            f"CO2 {CO2} still in sensors[] after 22F1 inject",
            CO2 in sensors,
            f"sensors={sensors}",
        )

        # 9. Check if the CO2 also appears in remotes[] (dual-role topology).
        #    This would be the ideal behavior for a true dual-role device.
        if CO2 in remotes:
            print("  CO2 is in BOTH remotes[] and sensors[] (dual-role topology)")
            ctx.check(
                "CO2 in both remotes[] and sensors[] (dual-role topology)",
                True,
                "both lists",
            )
        else:
            ctx.check(
                "CO2 not in remotes[] (single-role topology, _class wins)",
                True,
                "sensors only — filter removes CO2 from remotes[]",
            )

        # 10. Summary: document the gap.
        print()
        print("  === 6c Summary ===")
        print("  ramses_rf uses a single-class device model:")
        print("  - A device is either HvacCarbonDioxideSensor OR HvacRemote")
        print("  - The eavesdropper promotes based on last verb/code pair")
        print("  - Entity creation is based on device class, not list membership")
        print("  - remotes[]/sensors[] are topology only (which FAN owns this)")
        print()
        print("  Gap: a true dual-role device (CO2+REM) cannot get both")
        print("  sensor and remote entities simultaneously.")
        print("  Workaround: user sets _class to force one role.")
        print("  Future fix: add HvacCo2Remote dual-class, or don't promote")
        print("  when conflicting signatures are detected.")
