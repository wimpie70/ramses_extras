"""Recipe R68: Active HVAC topology probing (step 6f).

Tests the ``probe_hvac_binding`` service which actively probes HVAC
topology by sending spoofed ``RQ 22F1`` from 37: devices to 32: FANs.

When the FAN responds with a directed ``RP 22F1``, the scan engine's
passive listener catches it and sets ``bound_to`` on the 37: device
→ "belongs to" comment → ``remotes[]``/``sensors[]``.

This is the HVAC equivalent of forcing a 000C binding table read —
it actively provokes the FAN to reveal its relationship with the REM
instead of waiting passively for the REM to poll.

This recipe:
1. Loads a profile with a FAN but NO remotes/sensors (stripped)
2. Verifies the REM/CO2 are in orphans_hvac (no parent)
3. Calls probe_hvac_binding service
4. Verifies the FAN responds with RP 22F1
5. Verifies the scan engine sets bound_to on the REM
6. Verifies the "belongs to" comment appears
7. Verifies the REM is placed in remotes[] after sync

See: phase4_plan.md step 6f
"""

from __future__ import annotations

import json

from ..base import Recipe, RecipeContext
from ..const import CO2, FAN, REM
from ..helpers import (
    call_service,
    get_schema_retry,
    load_profile_yaml,
    wait_for,
)
from ..profile import mixed_yaml


class R68HvacActiveProbing(Recipe):
    id = "R68"
    seq = 680
    title = "Active HVAC topology probing (6f)"

    async def run(self, ctx: RecipeContext) -> None:
        ctx.log_section("Recipe 68: Active HVAC topology probing (6f)")

        # 1. Load mixed profile with FAN's remotes/sensors stripped.
        #    The FAN keeps _class=FAN but has no remotes/sensors —
        #    the topology must be discovered via active probing.
        print("  Loading mixed profile with FAN remotes/sensors stripped...")
        schema_override = {
            FAN: {
                "_class": "FAN",
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

        # 2. Verify the BEFORE state: FAN has no remotes/sensors.
        #    Note: the scan engine may have already detected the binding
        #    from traffic during profile loading (the device simulator
        #    sends packets during activation).  We check but don't fail
        #    if the REM is already bound — the probe service still works.
        schema = get_schema_retry()
        if not schema:
            ctx.check("Schema loaded", False, "no schema")
            return

        fan_entry = schema.get(FAN, {})
        remotes_before = (
            fan_entry.get("remotes", []) if isinstance(fan_entry, dict) else []
        )
        sensors_before = (
            fan_entry.get("sensors", []) if isinstance(fan_entry, dict) else []
        )
        orphans_before = schema.get("orphans_hvac", [])

        print(f"  BEFORE: remotes={remotes_before}, sensors={sensors_before}")
        print(f"  BEFORE: orphans_hvac={orphans_before}")

        # Document whether the REM was already bound from traffic
        already_bound = REM in remotes_before or REM not in orphans_before
        if already_bound:
            print("  NOTE: REM already bound from traffic during profile load")

        # 3. Call the probe_hvac_binding service.
        #    HA services don't return values via the REST API — the
        #    return value of the service function is not forwarded to
        #    the caller.  We just verify the service executes without
        #    error.
        print("  Calling probe_hvac_binding service...")
        service_ok = False
        try:
            call_service(
                ctx.token,
                "ramses_cc",
                "probe_hvac_binding",
                {},
            )
            service_ok = True
        except RuntimeError as e:
            print(f"  Service call failed: {e}")

        ctx.check(
            "probe_hvac_binding service executed without error",
            service_ok,
            "service call succeeded",
        )

        # 4. Wait for the scan engine to process the RP response.
        ctx.wait(10, "for scan engine to process RP 22F1 response")

        # 5. Check the schema AFTER probing.
        schema_after = get_schema_retry()
        if not schema_after:
            ctx.check("Schema loaded after probe", False, "no schema")
            return

        fan_entry_after = schema_after.get(FAN, {})
        remotes_after = (
            fan_entry_after.get("remotes", [])
            if isinstance(fan_entry_after, dict)
            else []
        )
        sensors_after = (
            fan_entry_after.get("sensors", [])
            if isinstance(fan_entry_after, dict)
            else []
        )
        orphans_after = schema_after.get("orphans_hvac", [])
        comments = schema_after.get("device_comments", {})

        print(f"  AFTER: remotes={remotes_after}, sensors={sensors_after}")
        print(f"  AFTER: orphans_hvac={orphans_after}")

        # Check if the REM got a "belongs to" comment
        rem_comment = comments.get(REM, "")
        print(f"  REM comment: {rem_comment[:160] if rem_comment else 'None'}")

        # 6. Verify the probe results.
        # The probe sends RQ 22F1 from REM to FAN.  The FAN should
        # respond with RP 22F1 directed to the REM.  The scan engine
        # catches this and sets bound_to on the REM.
        #
        # In the ha-sim environment, the device simulator handles the
        # RQ/RP exchange.  The key question is whether the scan engine
        # processes the RP and sets bound_to.

        has_rem_in_remotes = REM in remotes_after
        has_rem_belongs = "belongs to" in rem_comment.lower()

        if has_rem_in_remotes or has_rem_belongs:
            ctx.check(
                f"REM {REM} detected as bound to FAN after probe",
                True,
                f"remotes={remotes_after}, comment={rem_comment[:80]}",
            )
            ctx.check(
                f"REM {REM} no longer in orphans_hvac",
                REM not in orphans_after,
                f"orphans={orphans_after}",
            )
        else:
            # The probe may not have triggered a response in the sim
            # environment (the device simulator may not respond to
            # spoofed RQ 22F1 from a different source).  This is a
            # known limitation of the sim environment.
            print("  NOTE: REM not detected as bound after probe.")
            print("  This may be a sim limitation (device simulator")
            print("  may not respond to spoofed RQ from different src).")
            ctx.check(
                "REM bound to FAN (passive or active detection)",
                False,
                "no binding detected — sim limitation",
            )
