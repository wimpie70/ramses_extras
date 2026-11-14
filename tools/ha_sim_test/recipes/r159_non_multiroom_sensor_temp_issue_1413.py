"""Recipe R159: non-multiroom zone ignores bound sensor 30C9 (issue 1413).

Reproduces ramses_cc issue 1413 end-to-end:

A zone with a bound DT4R thermostat (THM, ``22:``) whose controller marks
the zone locally-sensed — ``multiroom_mode`` off in the 000A zone flags —
takes its temperature from the zone's actuators, echoed in the
controller's 30C9 zone syncs.  The bound sensor's own 30C9 broadcast is a
device-local reading, not the zone temperature — accepting it makes the
zone temperature oscillate between the sensor and controller values
(the reported "jumping/erratic temperature" graph).

The fix gates the temperature write on ``zone_state.multiroom_mode``: a
bound/declared sensor's broadcast must not overwrite a locally-sensed
zone's temperature — only controller syncs carry it.

The recipe covers both branches:

1. Zone 02 — ``000A`` flags 0x10 (multiroom off), sensor ``22:033088``,
   TRV actuators: a THM broadcast (12.30 °C) must NOT overwrite the
   controller-synced zone temperature (11.43 °C).
2. Zone 00 — ``000A`` flags 0x00 (multiroom on), sensor ``22:017762``:
   the THM broadcast (12.30 °C) MUST update the zone temperature (the
   multiroom behaviour is unchanged).
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

CTL = "01:147133"
THM_LOCAL = "22:033088"  # bound to zone 02 (multiroom off)
THM_REMOTE = "22:017762"  # bound to zone 00 (multiroom on)
TRV_02A = "04:197871"
TRV_02B = "04:237125"
TRV_00 = "04:197867"
HGI = "18:001234"

ZONE_LOCAL = "02"
ZONE_REMOTE = "00"

CTL_TEMP_LOCAL = 11.43  # 0x0477 — TRV-sensed, echoed in CTL syncs
CTL_TEMP_REMOTE = 12.40  # 0x04D8 — echoes the sensor's reading
SENSOR_TEMP = 12.30  # 0x04CE — the DT4R's own broadcast


def _get_climate_entity_id(token: str, zone_idx: str) -> str | None:
    """Return the entity_id of a zone climate entity by its stable
    ``id`` attribute (``<ctl_id>_<zone_idx>``)."""
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
        if state.get("attributes", {}).get("id") == f"{CTL}_{zone_idx}":
            return state["entity_id"]
    return None


def _get_climate_temp(token: str, entity_id: str | None) -> float | None:
    """Return ``current_temperature`` of a zone climate entity.

    Zone entities only refresh on ``SIGNAL_UPDATE_<zone_id>`` — packets
    routed to the zone emit signals for the *source* device, so the
    entity is force-refreshed via ``homeassistant.update_entity`` first.
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


class R159NonMultiroomSensorTempIssue1413(Recipe):
    id = "R159"
    seq = 1590
    title = "non-multiroom zone ignores bound sensor 30C9 (issue 1413)"

    async def run(self, ctx: RecipeContext) -> None:
        ctx.log_section("Recipe 159: non-multiroom sensor temp (issue 1413)")

        # Reporter's topology: zone 02 is locally-sensed (multiroom off)
        # with a bound DT4R; zone 00 is remote-sensed (multiroom on).
        schema = {
            "main_tcs": CTL,
            CTL: {
                "_class": "CTL",
                "zones": {
                    ZONE_LOCAL: {
                        "class": "radiator_valve",
                        "sensor": THM_LOCAL,
                        "actuators": [TRV_02A, TRV_02B],
                    },
                    ZONE_REMOTE: {
                        "class": "radiator_valve",
                        "sensor": THM_REMOTE,
                        "actuators": [TRV_00],
                    },
                },
            },
        }
        profile = {
            "known_list": {
                CTL: {"class": "CTL"},
                THM_LOCAL: {"class": "THM"},
                THM_REMOTE: {"class": "THM"},
                TRV_02A: {"class": "TRV"},
                TRV_02B: {"class": "TRV"},
                TRV_00: {"class": "TRV"},
            },
            "_enforce_known_list": {"enabled": True},
            "_schema": schema,
        }

        clear_cached_state(ctx.log_monitor, label="R159 pre-restart")
        ctx.wait_for_ha_ready(timeout=30)
        ctx.log_monitor.reset_baseline()
        ctx.refresh_token()
        ctx.wait_for_ramses_cc_loaded(timeout=30)

        print("  Loading two-zone profile (zone 02 + zone 00)...")
        await load_profile_yaml(
            ctx.token,
            yaml.dump(profile, default_flow_style=False, sort_keys=False),
            speed=0.01,
        )
        ctx.wait_for_ramses_cc_reload(timeout=20)
        ctx.refresh_token()
        wait_for_transport_ready(timeout=30)

        climates: dict[str, str | None] = {}
        for _ in range(10):
            for zone_idx in (ZONE_LOCAL, ZONE_REMOTE):
                if climates.get(zone_idx) is None:
                    climates[zone_idx] = _get_climate_entity_id(ctx.token, zone_idx)
            if all(climates.values()):
                break
            ctx.wait(1, "for zone climate entities")
        print(f"  Zone climate entities: {climates}")
        ctx.check(
            "zone climate entities exist",
            all(climates.values()),
            f"climates={climates}",
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

        # Step 1: CTL broadcasts the 000A zone flags — zone 02 flag 0x10
        # (multiroom off, locally-sensed), zone 00 flag 0x00 (multiroom).
        print("  Step 1: CTL 000A zone flags (zone 02 = multiroom OFF)...")
        _inject(CTL, "000A", f"{ZONE_LOCAL}1001F40DAC")
        _inject(CTL, "000A", f"{ZONE_REMOTE}0001F40DAC")
        ctx.wait(2, "after CTL 000A flags")

        # Step 2: CTL 30C9 syncs — zone 02 = 11.43C (TRV-sensed),
        # zone 00 = 12.40C (echoes the remote sensor).
        print("  Step 2: CTL 30C9 syncs (02=11.43C, 00=12.40C)...")
        _inject(CTL, "30C9", f"{ZONE_LOCAL}0477")
        _inject(CTL, "30C9", f"{ZONE_REMOTE}04D8")
        ctx.wait(1, "after CTL 30C9 syncs")

        # Step 3: bound DT4R broadcasts its own reading (12.30C) — for
        # zone 02 this must NOT overwrite the controller-synced temp.
        print("  Step 3: THM 22:033088 broadcasts 12.30C (zone 02)...")
        _inject(THM_LOCAL, "30C9", "0004CE")
        ctx.wait(1, "after THM broadcast to zone 02")

        local_temp = _get_climate_temp(ctx.token, climates[ZONE_LOCAL])
        print(f"  Zone 02 temp after sensor broadcast: {local_temp}")
        ctx.check(
            "multiroom-off zone ignores bound sensor broadcast",
            local_temp is not None and abs(local_temp - CTL_TEMP_LOCAL) < 0.2,
            f"temp={local_temp} (expected ~{CTL_TEMP_LOCAL}, not {SENSOR_TEMP})",
        )

        # Step 4: control — the multiroom zone still hydrates from its
        # bound sensor's broadcast.
        print("  Step 4: THM 22:017762 broadcasts 12.30C (zone 00)...")
        _inject(THM_REMOTE, "30C9", "0004CE")
        ctx.wait(1, "after THM broadcast to zone 00")

        remote_temp = _get_climate_temp(ctx.token, climates[ZONE_REMOTE])
        print(f"  Zone 00 temp after sensor broadcast: {remote_temp}")
        ctx.check(
            "multiroom zone still hydrates from bound sensor",
            remote_temp is not None and abs(remote_temp - SENSOR_TEMP) < 0.2,
            f"temp={remote_temp} (expected ~{SENSOR_TEMP})",
        )

        # Summary
        print()
        print("  === Summary ===")
        print(
            f"  Zone {ZONE_LOCAL} (multiroom off): {local_temp} "
            f"(expected ~{CTL_TEMP_LOCAL})"
        )
        print(
            f"  Zone {ZONE_REMOTE} (multiroom on):  {remote_temp} "
            f"(expected ~{SENSOR_TEMP})"
        )
        if local_temp is not None and abs(local_temp - CTL_TEMP_LOCAL) < 0.2:
            print("  CONFIRMED: non-multiroom zone keeps controller-synced temp")
