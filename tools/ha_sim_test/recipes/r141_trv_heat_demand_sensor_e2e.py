"""Recipe R141: TRV heat_demand sensor end-to-end (regression guard).

R72 verifies the 3150 *parser* output only.  This recipe closes the loop:
a TRV-sourced ``I --- 04:xxx ... 3150`` packet must end up as the state of
``sensor.trv_04_xxxxxx_heat_demand`` in Home Assistant, and the same packet
must hydrate the zone-level ``sensor.01_xxxxxx_NN_heat_demand``.

It also pins down the ``setpoint is False`` fallback in
``TrvActuator.heat_demand()``: a TRV that has reported setpoint ``7EFF``
(via 2309) but never sent a 3150 shows ``0`` — not ``unknown`` — and a real
3150 afterwards must override that fallback.  A TRV heat_demand sensor
stuck at 0 % therefore means its 3150 packets never reach/parse in
ramses_rf (schema/known_list filtering, RF coverage, or a decode drop),
not a broken sensor.

Note: zone heat_demand sensors update on a slower batched schedule than
TRV sensors (observed ~40 s lag on ha-sim), so zone assertions run last
with generous timeouts.
"""

from __future__ import annotations

import json
import urllib.request

from ..base import Recipe, RecipeContext
from ..const import CTL, TRV
from ..helpers import (
    call_service,
    get_current_instance,
    wait_for_entity_state,
    wait_for_schema_populated,
    wait_for_transport_ready,
    ws_send,
)

# Mixed profile: TRV 04:150003 is the zone 03 actuator,
# TRV 04:150004 is the zone 04 actuator.
TRV2 = "04:150004"

TRV_SENSOR = "sensor.trv_04_150003_heat_demand"
TRV2_SENSOR = "sensor.trv_04_150004_heat_demand"
ZONE03_SENSOR = "sensor.01_150000_03_heat_demand"
ZONE04_SENSOR = "sensor.01_150000_04_heat_demand"


def _entity_state(token: str, entity_id: str) -> str | None:
    """Return the current HA state string for an entity, or None."""
    req = urllib.request.Request(
        f"{get_current_instance().ha_url}/api/states/{entity_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    try:
        return json.loads(urllib.request.urlopen(req, timeout=10).read()).get("state")
    except Exception:  # noqa: BLE001
        return None


def _inject(
    token: str,
    source_id: str,
    code: str,
    payload: str,
    dst: str = CTL,
) -> None:
    """Inject an I frame addressed at the controller.

    Real TRV packets carry the controller in a dst position
    (``I --- 04:xxx --:------ 01:xxx``); the projector only treats a
    ``zone_index`` as a controller zone index when the TCS is in
    src or dst (state_projector step 4, issue 1208).
    """
    call_service(
        token,
        "ramses_extras",
        "device_simulator_inject_message",
        {
            "source_id": source_id,
            "dst": dst,
            "code": code,
            "payload": payload,
            "verb": "I",
        },
    )


class R141TrvHeatDemandSensorEndToEnd(Recipe):
    id = "R141"
    seq = 1410
    title = "TRV heat_demand sensor end-to-end (regression guard)"
    tags = ("sensor", "3150", "heat_demand", "trv")

    async def run(self, ctx: RecipeContext) -> None:
        ctx.log_section(
            "Recipe 141: TRV heat_demand sensor end-to-end (regression guard)"
        )

        print("  Loading mixed profile...")
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
        wait_for_schema_populated(min_keys=5, timeout=20)

        # --- A: non-zero demand updates the TRV sensor ---
        print(f"  Injecting 3150 I 0332 (zone 03, 25%) from TRV {TRV}...")
        _inject(ctx.token, TRV, "3150", "0332")
        ctx.check(
            f"{TRV_SENSOR} shows 25.0 after TRV-sourced 3150",
            wait_for_entity_state(ctx.token, TRV_SENSOR, expected="25.0", timeout=15),
            f"state={_entity_state(ctx.token, TRV_SENSOR)!r}",
        )

        # --- B: a genuine zero demand is distinguishable from unknown ---
        print(f"  Injecting 3150 I 0300 (zone 03, 0%) from TRV {TRV}...")
        _inject(ctx.token, TRV, "3150", "0300")
        ctx.check(
            f"{TRV_SENSOR} shows 0.0 for a real zero-demand 3150",
            wait_for_entity_state(ctx.token, TRV_SENSOR, expected="0.0", timeout=15),
            f"state={_entity_state(ctx.token, TRV_SENSOR)!r}",
        )

        # --- C: setpoint=False (2309 7EFF) with no 3150 -> 0 fallback ---
        print(
            f"  Injecting 2309 I 047EFF (zone 04, setpoint disabled) from TRV {TRV2}..."
        )
        _inject(ctx.token, TRV2, "2309", "047EFF")
        ctx.check(
            f"{TRV2_SENSOR} shows 0 via setpoint=False fallback (no 3150 yet)",
            ctx.wait_for(
                lambda: _entity_state(ctx.token, TRV2_SENSOR) in ("0", "0.0"),
                timeout=15,
                msg=f"for {TRV2_SENSOR} to read 0",
            ),
            f"state={_entity_state(ctx.token, TRV2_SENSOR)!r}",
        )

        # --- D: a real 3150 overrides the setpoint=False fallback ---
        print(f"  Injecting 3150 I 0464 (zone 04, 50%) from TRV {TRV2}...")
        _inject(ctx.token, TRV2, "3150", "0464")
        ctx.check(
            f"{TRV2_SENSOR} shows 50.0 once its 3150 arrives",
            wait_for_entity_state(ctx.token, TRV2_SENSOR, expected="50.0", timeout=15),
            f"state={_entity_state(ctx.token, TRV2_SENSOR)!r}",
        )

        # --- E: zone sensors hydrate from the same packets ---
        # Zone entities resolve on a slower batched schedule (observed
        # ~40 s lag), so assert the final expected values with a long
        # timeout rather than checking after each inject.
        ctx.check(
            f"{ZONE03_SENSOR} shows 0.0 from the last TRV-sourced 3150",
            ctx.wait_for(
                lambda: _entity_state(ctx.token, ZONE03_SENSOR) == "0.0",
                timeout=90,
                floor=60,
                msg=f"for {ZONE03_SENSOR} to read 0.0",
            ),
            f"state={_entity_state(ctx.token, ZONE03_SENSOR)!r}",
        )
        ctx.check(
            f"{ZONE04_SENSOR} shows 50.0 after TRV-sourced 3150",
            ctx.wait_for(
                lambda: _entity_state(ctx.token, ZONE04_SENSOR) == "50.0",
                timeout=90,
                floor=60,
                msg=f"for {ZONE04_SENSOR} to read 50.0",
            ),
            f"state={_entity_state(ctx.token, ZONE04_SENSOR)!r}",
        )
