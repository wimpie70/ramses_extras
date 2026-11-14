"""Recipe R161: DHW relay demand must come from domain FA only (issue 1370).

Reproduces ramses_rf issue 1370 end-to-end:

A controller broadcasts ``0008`` relay-demand frames per domain every
~20 minutes: ``FA`` is the hot-water (DHW) valve, ``F9`` the heating
valve.  Both domains were routed to ``tcs.dhw`` and written into its
``demand_state.relay_demand`` with no domain check, so the "Stored HW
Relay demand" sensor (``sensor.<ctl>_hw_relay_demand``) showed the
heating valve's demand after every ``F9`` broadcast — e.g. 2% while the
DHW valve was closed, or 0% mid-reheat — breaking automations that use
it to detect a DHW call.

The fix routes only ``FA`` to the DhwZone; ``F9`` still lands in the
controller's per-domain ``relay_demands`` attribute via the CTL device
path.

The recipe injects the reporter's exact sequence:

1. ``0008|FA00`` (DHW valve closed)  → sensor 0%
2. ``0008|F904`` (heating valve 2%) → sensor must stay 0% (pre-fix: 2%)
3. ``0008|FAC8`` (DHW reheat 100%)  → sensor 100%
4. ``0008|F900`` (heating idle)     → sensor must stay 100%
   (pre-fix: 0%)
"""

from __future__ import annotations

import json
import urllib.request

import yaml

from ..base import Recipe, RecipeContext
from ..helpers import (
    call_service,
    clear_cached_state,
    get_current_instance,
    load_profile_yaml,
    wait_for_transport_ready,
)

CTL = "01:050858"  # reporter's evohome controller
DHW_ZONE_ID = f"{CTL}_HW"
HW_VALVE = "13:215029"  # reporter's DHW valve BDR
HTG_VALVE = "13:246213"  # reporter's heating valve BDR

TOL = 0.5  # %


def _get_dhw_relay_sensor(token: str) -> str | None:
    """Return the entity_id of the DHW zone's relay-demand sensor."""
    req = urllib.request.Request(
        f"{get_current_instance().ha_url}/api/states",
        headers={"Authorization": f"Bearer {token}"},
    )
    try:
        states = json.loads(urllib.request.urlopen(req, timeout=5).read())
    except Exception:
        return None
    for state in states:
        entity_id = state.get("entity_id", "")
        if not entity_id.startswith("sensor."):
            continue
        if "relay_demand" not in entity_id:
            continue
        if state.get("attributes", {}).get("id") == DHW_ZONE_ID:
            return entity_id
    return None


def _get_sensor_value(token: str, entity_id: str | None) -> float | None:
    """Return the numeric state of the relay-demand sensor (percent).

    The sensor only refreshes on its device-update signal, so it is
    force-refreshed via ``homeassistant.update_entity`` first (same as
    zone climates in R159).
    """
    if entity_id is None:
        return None
    call_service(
        token,
        "homeassistant",
        "update_entity",
        {"entity_id": entity_id},
    )
    req = urllib.request.Request(
        f"{get_current_instance().ha_url}/api/states/{entity_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    try:
        state = json.loads(urllib.request.urlopen(req, timeout=5).read())
    except Exception:
        return None
    try:
        return float(state.get("state"))
    except TypeError, ValueError:
        return None


class R161DhwRelayDemandFaOnlyIssue1370(Recipe):
    id = "R161"
    seq = 1610
    title = "DHW relay demand from domain FA only (issue 1370)"
    tags = ("demand", "0008", "dhw", "splan")

    async def run(self, ctx: RecipeContext) -> None:
        ctx.log_section("Recipe 161: DHW relay demand FA-only (issue 1370)")

        # Reporter's S-plan: DHW valve + heating valve BDRs.
        profile = {
            "known_list": {
                CTL: {"class": "CTL"},
                HW_VALVE: {"class": "BDR"},
                HTG_VALVE: {"class": "BDR"},
            },
            "_enforce_known_list": {"enabled": True},
            "_schema": {
                "main_tcs": CTL,
                CTL: {
                    "_class": "CTL",
                    "stored_hotwater": {
                        "hotwater_valve": HW_VALVE,
                        "heating_valve": HTG_VALVE,
                    },
                },
            },
        }

        clear_cached_state(ctx.log_monitor, label="R161 pre-restart")
        ctx.wait_for_ha_ready(timeout=30)
        ctx.log_monitor.reset_baseline()
        ctx.refresh_token()
        ctx.wait_for_ramses_cc_loaded(timeout=30)

        print("  Loading S-plan profile (DHW + heating valves)...")
        await load_profile_yaml(
            ctx.token,
            yaml.dump(profile, default_flow_style=False, sort_keys=False),
            speed=0.01,
        )
        ctx.wait_for_ramses_cc_reload(timeout=20)
        ctx.refresh_token()
        wait_for_transport_ready(timeout=30)

        sensor = None
        for _ in range(15):
            sensor = _get_dhw_relay_sensor(ctx.token)
            if sensor is not None:
                break
            ctx.wait(1, "for DHW relay_demand sensor")
        print(f"  DHW relay_demand sensor: {sensor}")
        ctx.check(
            "DHW relay_demand sensor exists",
            sensor is not None,
            f"entity={sensor}",
        )

        def _inject_0008(domain_payload: str) -> None:
            call_service(
                ctx.token,
                "ramses_extras",
                "device_simulator_inject_message",
                {
                    "source_id": CTL,
                    "dst": "--:------",
                    "code": "0008",
                    "payload": domain_payload,
                    "verb": "I",
                },
            )

        # Step 1: DHW valve closed — sensor reads 0%.
        print("  Step 1: CTL 0008|FA00 (DHW valve 0%)...")
        _inject_0008("FA00")
        ctx.wait(2, "after 0008|FA00")
        v1 = _get_sensor_value(ctx.token, sensor)
        print(f"    sensor: {v1}%")
        ctx.check(
            "0008|FA00 lands on DHW relay demand",
            v1 is not None and abs(v1 - 0.0) <= TOL,
            f"state={v1} (expected 0)",
        )

        # Step 2: heating valve 2% — must NOT touch the DHW sensor.
        print("  Step 2: CTL 0008|F904 (heating valve 2%)...")
        _inject_0008("F904")
        ctx.wait(2, "after 0008|F904")
        v2 = _get_sensor_value(ctx.token, sensor)
        print(f"    sensor: {v2}%")
        ctx.check(
            "0008|F904 ignored by DHW (pre-fix: 2%)",
            v2 is not None and abs(v2 - 0.0) <= TOL,
            f"state={v2} (expected 0, pre-fix showed ~2)",
        )

        # Step 3: DHW reheat — sensor reads 100%.
        print("  Step 3: CTL 0008|FAC8 (DHW reheat 100%)...")
        _inject_0008("FAC8")
        ctx.wait(2, "after 0008|FAC8")
        v3 = _get_sensor_value(ctx.token, sensor)
        print(f"    sensor: {v3}%")
        ctx.check(
            "0008|FAC8 lands on DHW relay demand",
            v3 is not None and abs(v3 - 100.0) <= TOL,
            f"state={v3} (expected 100)",
        )

        # Step 4: heating valve idle — must NOT clear the reheat.
        print("  Step 4: CTL 0008|F900 (heating valve idle)...")
        _inject_0008("F900")
        ctx.wait(2, "after 0008|F900")
        v4 = _get_sensor_value(ctx.token, sensor)
        print(f"    sensor: {v4}%")
        ctx.check(
            "0008|F900 ignored by DHW (pre-fix: 0%)",
            v4 is not None and abs(v4 - 100.0) <= TOL,
            f"state={v4} (expected 100, pre-fix showed 0)",
        )

        print()
        print("  === Summary ===")
        print(f"  after FA00: {v1}%   after F904: {v2}%")
        print(f"  after FAC8: {v3}%   after F900: {v4}%")
        if (
            v2 is not None
            and abs(v2) <= TOL
            and v4 is not None
            and abs(v4 - 100.0) <= TOL
        ):
            print("  CONFIRMED: heating-valve F9 broadcasts ignored by DHW")
