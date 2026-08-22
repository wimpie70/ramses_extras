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

        # 2. Inject 0008 (relay demand) from CTL with FC domain
        #    0008 I payload: domain_idx(2) + relay_demand(2)
        #    FC = 0xFC, demand = 0xC8 (100%)
        print(f"  Injecting 0008 from CTL {ctl} (FC domain, 100% demand)...")
        try:
            call_service(
                ctx.token,
                "ramses_extras",
                "device_simulator_inject_message",
                {
                    "source_id": ctl,
                    "code": "0008",
                    "payload": "FCC8",
                    "verb": "I",
                },
            )
            print("    0008 injected (FC=100%)")
        except RuntimeError as e:
            print(f"    Inject failed: {str(e)[:80]}")

        ctx.wait(2, "between injects")

        # 3. Inject 0008 with FA domain (DHW relay)
        print(f"  Injecting 0008 from CTL {ctl} (FA domain, 50% demand)...")
        try:
            call_service(
                ctx.token,
                "ramses_extras",
                "device_simulator_inject_message",
                {
                    "source_id": ctl,
                    "code": "0008",
                    "payload": "FA64",
                    "verb": "I",
                },
            )
            print("    0008 injected (FA=50%)")
        except RuntimeError as e:
            print(f"    Inject failed: {str(e)[:80]}")

        ctx.wait(2, "between injects")

        # 4. Inject 3150 (heat demand) from CTL with FC domain
        #    3150 I payload: domain_idx(2) + heat_demand(2)
        #    FC = 0xFC, demand = 0x96 (75%)
        print(f"  Injecting 3150 from CTL {ctl} (FC domain, 75% demand)...")
        try:
            call_service(
                ctx.token,
                "ramses_extras",
                "device_simulator_inject_message",
                {
                    "source_id": ctl,
                    "code": "3150",
                    "payload": "FC96",
                    "verb": "I",
                },
            )
            print("    3150 injected (FC=75%)")
        except RuntimeError as e:
            print(f"    Inject failed: {str(e)[:80]}")

        ctx.wait(2, "between injects")

        # 5. Inject 1100 (TPI params) from CTL with FC domain
        #    1100 I payload (8-byte): domain(2) + cycle_rate(2) +
        #    min_on(2) + min_off(2) + flags(2) + prop_band(4) + trailing(2)
        #    FC 18 04 04 00 7FFF 00 = FC, 6cph, 1min on, 1min off
        print(f"  Injecting 1100 from CTL {ctl} (FC domain, TPI params)...")
        try:
            call_service(
                ctx.token,
                "ramses_extras",
                "device_simulator_inject_message",
                {
                    "source_id": ctl,
                    "code": "1100",
                    "payload": "FC180404007FFF00",
                    "verb": "I",
                },
            )
            print("    1100 injected (TPI params)")
        except RuntimeError as e:
            print(f"    Inject failed: {str(e)[:80]}")

        # 6. Find the controller climate entity
        def _find_ctl_climate() -> dict | None:
            entities = get_entities(ctx.token)
            ctl_suffix = ctl.replace(":", "_")
            for e in entities:
                if not e["entity_id"].startswith("climate."):
                    continue
                if ctl_suffix in e["entity_id"]:
                    return e
            return None

        wait_for(
            _find_ctl_climate,
            timeout=15,
            interval=2,
            msg="for CTL climate entity",
        )

        # 7. Poll for attributes to become non-None (HA state refresh
        #    happens asynchronously after SIGNAL_UPDATE is dispatched)
        #    We also force a state refresh via homeassistant.update_entity
        #    to work around a race condition where SIGNAL_UPDATE fires
        #    before the CQRS state projector has finished populating the
        #    per-domain dicts, causing HA to cache None.
        def _poll_for_attrs(timeout_s: int = 60) -> dict:
            deadline = time.monotonic() + timeout_s
            refresh_attempted = False
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
                    # After 10s, force a state refresh to work around
                    # the SIGNAL_UPDATE race condition
                    if (
                        not refresh_attempted
                        and time.monotonic() > deadline - timeout_s + 10
                    ):
                        try:
                            call_service(
                                ctx.token,
                                "homeassistant",
                                "update_entity",
                                {"entity_id": entity["entity_id"]},
                            )
                            print(f"    Forced state refresh for {entity['entity_id']}")
                        except Exception:
                            pass
                        refresh_attempted = True
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
