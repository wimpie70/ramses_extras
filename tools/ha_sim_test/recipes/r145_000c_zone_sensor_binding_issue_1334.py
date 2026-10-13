"""Recipe R145: 000C zone-sensor binding defeats sole-actuator fallback.

Reproduces ramses_cc issue 1334 / issue 1344 end-to-end:

A zone has a dedicated but broadcast-only temperature sensor (Round
Thermostat / RND, ``34:``) that never sends zone-indexed traffic of its
own.  Discovery cannot attribute it to a zone, so it lands in
``orphans_heat`` and the zone stays sensorless — the sole-actuator
fallback then routes the zone's only TRV broadcast 30C9 to
``zone.temperature``, producing the observed temperature dip until the
next controller sync restores the real value.

The fix: the controller's 000C binding table (role ``04`` =
``zone_sensor``) is authoritative — polling it per sensorless zone
yields an ``RP 000C`` naming the real sensor, ``BindTopologyHandler``
binds it to the zone, and the TRV broadcast is no longer routed.

This recipe replays that exchange against the live integration:

1. CTL 30C9 zone array (zone 01 = 19.81 °C)
2. THM broadcast 30C9 (19.8 °C) — orphan, must not affect the zone
3. TRV broadcast 30C9 (18.7 °C) — sole-actuator fallback dips the zone
4. RQ/RP 000C role-04 binding the THM to zone 01
5. sync_topology — schema must show ``sensor: 34:218857``, orphan gone
6. TRV broadcast again — zone temperature must stay at the sensor value
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
    get_schema_retry,
    load_profile_yaml,
    wait_for_transport_ready,
)

CTL = "01:147133"
TRV = "04:005247"  # sole actuator of zone 01
THM = "34:218857"  # broadcast-only zone sensor (orphan)
HGI = "18:001234"

THM_HEX = "8B56E9"  # 34:218857
ZONE_IDX = "01"


def _get_climate_entity_id(token: str) -> str | None:
    """Return the entity_id of the zone-01 climate entity.

    Climate entity ids are slugs of the zone name (e.g.
    ``climate.zone_1``), so match on the stable ``id`` attribute
    (``<ctl_id>_<zone_idx>``) instead.
    """
    req = urllib.request.Request(
        f"{get_current_instance().ha_url}/api/states",
        headers={"Authorization": f"Bearer {token}"},
    )
    try:
        states = json.loads(urllib.request.urlopen(req, timeout=5).read())
    except Exception:
        return None
    for state in states:
        if not state.get("entity_id", "").startswith("climate."):
            continue
        if state.get("attributes", {}).get("id") == f"{CTL}_{ZONE_IDX}":
            return state["entity_id"]
    return None


def _get_climate_temp(token: str, entity_id: str | None) -> float | None:
    """Return ``current_temperature`` of the zone climate entity.

    Zone entities only refresh on ``SIGNAL_UPDATE_<zone_id>`` — packets
    routed to the zone (e.g. an actuator's broadcast) emit signals for
    the *source* device, so the entity is force-refreshed via
    ``homeassistant.update_entity`` before reading.
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
    temp = state.get("attributes", {}).get("current_temperature")
    return float(temp) if temp is not None else None


class R145ZoneSensorBindingIssue1334(Recipe):
    id = "R145"
    seq = 1450
    title = "000C zone-sensor binding defeats actuator fallback (issue 1334)"

    async def run(self, ctx: RecipeContext) -> None:
        ctx.log_section("Recipe 145: 000C zone-sensor binding (issue 1334)")

        # Reporter's topology: zone 01 has only the TRV actuator; the
        # broadcast-only THM sits in orphans_heat — the zone looks
        # sensorless.
        schema = {
            "main_tcs": CTL,
            CTL: {
                "_class": "CTL",
                "zones": {
                    ZONE_IDX: {
                        "class": "radiator_valve",
                        "actuators": [TRV],
                    },
                },
            },
            "orphans_heat": [THM],
        }
        profile = {
            "known_list": {
                CTL: {"class": "CTL"},
                TRV: {"class": "TRV"},
                THM: {"class": "RND"},
            },
            "_enforce_known_list": {"enabled": True},
            "_schema": schema,
        }

        clear_cached_state(ctx.log_monitor, label="R145 pre-restart")
        ctx.wait_for_ha_ready(timeout=30)
        ctx.log_monitor.reset_baseline()
        ctx.refresh_token()
        ctx.wait_for_ramses_cc_loaded(timeout=30)

        print("  Loading zone-01 profile (TRV actuator only, THM orphan)...")
        await load_profile_yaml(
            ctx.token,
            yaml.dump(profile, default_flow_style=False, sort_keys=False),
            speed=0.01,
        )
        ctx.wait_for_ramses_cc_reload(timeout=20)
        ctx.refresh_token()
        wait_for_transport_ready(timeout=30)

        # Resolve the zone-01 climate entity (may take a moment to be
        # registered after the reload).
        climate_id: str | None = None
        for _ in range(10):
            climate_id = _get_climate_entity_id(ctx.token)
            if climate_id is not None:
                break
            ctx.wait(1, "for zone climate entity")
        print(f"  Zone climate entity: {climate_id}")
        ctx.check(
            "zone 01 climate entity exists",
            climate_id is not None,
            "",
        )

        def _inject(
            source_id: str,
            code: str,
            payload: str,
            verb: str = "I",
            dst: str = "--:------",
        ) -> None:
            call_service(
                ctx.token,
                "ramses_extras",
                "device_simulator_inject_message",
                {
                    "source_id": source_id,
                    "dst": dst,
                    "code": code,
                    "payload": payload,
                    "verb": verb,
                },
            )

        # Step 1: CTL syncs the zone temperature (19.81 °C)
        print("  Step 1: CTL 30C9 zone array (zone 01 = 19.81C)...")
        _inject(CTL, "30C9", f"{ZONE_IDX}07BD")
        ctx.wait(1, "after CTL 30C9 sync")

        # Step 2: THM broadcasts its own temperature — it is an orphan,
        # so it must not touch the zone.
        print("  Step 2: THM broadcast 30C9 (19.8C, orphan)...")
        _inject(THM, "30C9", "0007BC")
        ctx.wait(1, "after THM 30C9")

        # Step 3: TRV broadcast — sole-actuator fallback dips the zone
        # (the reported bug).  Read the climate entity immediately —
        # the 000C binding below rehydrates the zone from the sensor's
        # cached broadcast, so this check must run before step 4.
        print("  Step 3: TRV broadcast 30C9 (18.7C) — fallback dip...")
        _inject(TRV, "30C9", "00074E")
        ctx.wait(1, "after TRV 30C9")

        dipped = _get_climate_temp(ctx.token, climate_id)
        print(f"  Zone temp after TRV broadcast: {dipped}")
        ctx.check(
            "zone temp dips to TRV temp before binding (bug repro)",
            dipped is not None and abs(dipped - 18.7) < 0.2,
            f"temp={dipped}",
        )

        # Step 4: The new per-zone 000C role-04 probe — replay the
        # RQ/RP exchange the polling task performs.
        print("  Step 4: RQ/RP 000C role-04 (zone 01 sensor binding)...")
        _inject(HGI, "000C", f"{ZONE_IDX}04", verb="RQ", dst=CTL)
        ctx.wait(0.5, "after RQ 000C")
        _inject(CTL, "000C", f"{ZONE_IDX}0400{THM_HEX}", verb="RP", dst=HGI)
        ctx.wait(2, "after RP 000C")

        # Step 5: sync_topology to persist the learned binding.
        print("  Step 5: sync_topology...")
        call_service(ctx.token, "ramses_cc", "sync_topology")
        ctx.wait(3, "for topology sync")

        schema_after = get_schema_retry(max_tries=3, delay=1)
        zone_schema = schema_after.get(CTL, {}).get("zones", {}).get(ZONE_IDX, {})
        orphans_heat = schema_after.get("orphans_heat", [])
        print(f"  Zone {ZONE_IDX} schema: {zone_schema}")
        print(f"  orphans_heat: {orphans_heat}")

        ctx.check(
            "THM bound as zone 01 sensor via 000C",
            zone_schema.get("sensor") == THM,
            f"zone={zone_schema}",
        )
        ctx.check(
            "TRV remains zone 01 actuator",
            TRV in zone_schema.get("actuators", []),
            f"zone={zone_schema}",
        )
        ctx.check(
            "THM removed from orphans_heat",
            THM not in orphans_heat,
            f"orphans_heat={orphans_heat}",
        )

        # Step 6: THM broadcast hydrates the zone as its bound sensor.
        print("  Step 6: THM broadcast again (zone takes 19.8C)...")
        _inject(THM, "30C9", "0007BC")
        ctx.wait(3, "after THM 30C9")

        # Step 7: TRV broadcast must now be ignored — the zone has a
        # real sensor, so the sole-actuator fallback no longer applies.
        # Use a distinct temperature (16.5C = 0x0672) so a routed packet
        # would be clearly visible.
        print("  Step 7: TRV broadcast 16.5C (must NOT dip)...")
        _inject(TRV, "30C9", "000672")
        ctx.wait(1, "after second TRV 30C9")

        final_temp = _get_climate_temp(ctx.token, climate_id)
        print(f"  Zone temp after bound TRV broadcast: {final_temp}")
        ctx.check(
            "zone temp ignores TRV broadcast once sensor bound",
            final_temp is not None and abs(final_temp - 19.8) < 0.2,
            f"temp={final_temp}",
        )

        # Summary
        print()
        print("  === Summary ===")
        print(
            f"  Zone {ZONE_IDX}: sensor={zone_schema.get('sensor')}, "
            f"actuators={zone_schema.get('actuators')}"
        )
        print(f"  Pre-binding dip: {dipped}  Post-binding temp: {final_temp}")
        if zone_schema.get("sensor") == THM and (
            final_temp is not None and abs(final_temp - 19.8) < 0.2
        ):
            print("  CONFIRMED: 000C binding fixed the sole-actuator dip")
