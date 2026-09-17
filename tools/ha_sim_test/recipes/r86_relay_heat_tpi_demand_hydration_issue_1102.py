"""Recipe R86: relay/heat/TPI demand hydration (issue 1102 / ramses_cc#1026).

Verifies that 0008 (relay demand), 3150 (heat demand), and 1100 (TPI params)
packets are ingested by the CQRS state projector and that the controller
climate entity's relay_demands, heat_demands, and tpi_params attributes
are populated (not null).

Before the fix, the TCS's _relay_demands/_heat_demands dicts were
initialized empty but never populated (the legacy _handle_msg was removed
in the CQRS migration), and tpi_params used the deprecated
entity_state.get_value(Code._1100) which was never hydrated.
"""

from __future__ import annotations

import time

from ..base import Recipe, RecipeContext
from ..const import CTL
from ..helpers import (
    call_service,
    clear_cached_state,
    get_entities,
    get_schema_retry,
    wait_for,
    wait_for_transport_ready,
    ws_send,
)


class R86RelayHeatTpiDemandHydrationIssue1102(Recipe):
    id = "R86"
    seq = 860
    title = "relay/heat/TPI demand hydration (issue 1102 / ramses_cc#1026)"
    tags = ("0008", "3150", "1100", "relay_demand", "heat_demand", "tpi_params")

    async def run(self, ctx: RecipeContext) -> None:
        ctx.log_section("Recipe 86: relay/heat/TPI demand hydration (issue 1102)")

        # 0. Restart ha-sim to clear duplicate entities from prior recipes.
        #    Under parallel load, profile reloads create _2/_3 suffix
        #    duplicate climate entities that don't receive CQRS state
        #    updates.  A clean restart eliminates them.
        print("  Stopping ha-sim and clearing cached state...")
        clear_cached_state(ctx.log_monitor, label="R86 pre-restart")
        ctx.wait_for_ha_ready(timeout=30)
        ctx.log_monitor.reset_baseline()
        ctx.refresh_token()
        ctx.wait_for_ramses_cc_loaded(timeout=30)

        # 1. Load mixed profile (CTL 01:150000 with zones 03-08)
        print("  Loading mixed profile (CTL + zones 03-08)...")
        try:
            await ws_send(
                ctx.token,
                {
                    "type": "ramses_extras/device_simulator/load_profile",
                    "profile": "mixed",
                    "speed": 0.01,
                    "preload_schema": True,
                    "reload_ramses_cc": True,
                    "enable_auto_answer": True,
                },
            )
            print("  mixed profile loaded")
        except RuntimeError as e:
            print(f"  Profile load failed: {e}")
        ctx.wait_for_ramses_cc_reload(timeout=20)
        ctx.refresh_token()
        wait_for_transport_ready(timeout=30)

        ctl = CTL  # 01:150000

        # Wait for schema to be populated
        wait_for(
            lambda: len(get_schema_retry(max_tries=3, delay=1)) >= 5,
            timeout=15,
            interval=1,
            msg="for schema to be populated",
        )

        def _inject_demands() -> None:
            """Inject the four demand/TPI packets (idempotent I broadcasts).

            Under parallel load the MQTT transport can still be mid-reconnect
            when this runs — packets published during the gap are dropped —
            so callers re-inject until the attributes land.
            """
            injects = [
                ("0008", "FCC8", "FC=100%"),  # relay demand, FC domain
                ("0008", "FA64", "FA=50%"),  # relay demand, FA (DHW) domain
                ("3150", "FC96", "FC=75%"),  # heat demand
                ("1100", "FC180404007FFF00", "TPI params"),  # 6cph, 1/1min
            ]
            for code, payload, label in injects:
                try:
                    call_service(
                        ctx.token,
                        "ramses_extras",
                        "device_simulator_inject_message",
                        {
                            "source_id": ctl,
                            "code": code,
                            "payload": payload,
                            "verb": "I",
                        },
                    )
                    print(f"    {code} injected ({label})")
                except RuntimeError as e:
                    print(f"    Inject failed: {str(e)[:80]}")
                ctx.wait(2, "between injects")

        print(f"  Injecting demand/TPI packets from CTL {ctl}...")
        _inject_demands()

        # 6. Find the controller climate entity
        #    Prefer the exact match (climate.ctl_01_150000) over duplicates
        #    (climate.ctl_01_150000_2) which can appear after profile reloads.
        def _find_ctl_climate() -> dict | None:
            entities = get_entities(ctx.token)
            ctl_suffix = ctl.replace(":", "_")
            ctl_prefix = f"climate.ctl_{ctl_suffix}"
            # First pass: look for exact match (no _N suffix)
            for e in entities:
                if e["entity_id"] == ctl_prefix:
                    return e
            # Second pass: match ctl_ prefix with _N suffix (duplicate entity)
            for e in entities:
                eid = e["entity_id"]
                if eid.startswith(ctl_prefix + "_"):
                    return e
            # Third pass: any ctl_ entity for this device (last resort)
            for e in entities:
                eid = e["entity_id"]
                if eid.startswith("climate.ctl_") and ctl_suffix in eid:
                    return e
            return None

        wait_for(
            _find_ctl_climate,
            timeout=15,
            interval=2,
            msg="for CTL climate entity",
        )

        # 7. Poll for attributes to become non-None.
        #    The relay_demands/heat_demands/tpi_params properties are async
        #    and go through resolve_async_attr which has a 30s cooldown.
        #    The race condition where SIGNAL_UPDATE fired before the CQRS
        #    state projector finished populating the dicts is now fixed
        #    in gateway.py (process_message_state is called BEFORE
        #    process_msg), so the attributes should be populated quickly.
        #    Call force_update to trigger entity state refresh after the
        #    injections — this is especially important when running after
        #    other recipes that may have created duplicate entities.
        try:
            call_service(ctx.token, "ramses_cc", "force_update")
        except RuntimeError:
            pass
        ctx.wait(10, "for force_update to refresh entity state", floor=5.0)

        def _poll_for_attrs(timeout_s: int = 90) -> dict:
            deadline = time.monotonic() + timeout_s
            last_inject = time.monotonic()
            while time.monotonic() < deadline:
                entity = _find_ctl_climate()
                if entity is not None:
                    attrs = entity.get("attributes", {})
                    if (
                        attrs.get("relay_demands") is not None
                        and attrs.get("heat_demands") is not None
                        and attrs.get("tpi_params") is not None
                    ):
                        return attrs
                # Re-inject if nothing landed — the first round may have
                # been published while the transport was mid-reconnect.
                if time.monotonic() - last_inject > 15:
                    print("    Attributes still null — re-injecting...")
                    _inject_demands()
                    try:
                        call_service(ctx.token, "ramses_cc", "force_update")
                    except RuntimeError:
                        pass
                    last_inject = time.monotonic()
                time.sleep(2)
            # Return whatever we have
            entity = _find_ctl_climate()
            return entity.get("attributes", {}) if entity else {}

        print("  Polling for demand/TPI attributes (60s timeout)...")
        attrs = _poll_for_attrs(timeout_s=60)

        entity = _find_ctl_climate()
        entity_id = entity["entity_id"] if entity else "?"
        print(f"  CTL climate entity: {entity_id}")

        relay_demands = attrs.get("relay_demands")
        heat_demands = attrs.get("heat_demands")
        tpi_params = attrs.get("tpi_params")

        print(f"    relay_demands: {relay_demands}")
        print(f"    heat_demands: {heat_demands}")
        print(f"    tpi_params: {tpi_params}")

        # 8. Assertions — before the fix, all three were null
        ctx.check(
            "relay_demands is not None (0008 ingested)",
            relay_demands is not None,
            f"got {relay_demands}",
        )
        ctx.check(
            "heat_demands is not None (3150 ingested)",
            heat_demands is not None,
            f"got {heat_demands}",
        )
        ctx.check(
            "tpi_params is not None (1100 ingested)",
            tpi_params is not None,
            f"got {tpi_params}",
        )
