"""Recipe R160: OTB 3EF0/3220 rel-modulation percent scale (issue 1414).

Reproduces ramses_cc issue 1414 end-to-end:

An OpenTherm bridge (``10:``) reports the boiler's Relative Modulation
Level in the ``3EF0``/``3EF1`` modulation byte in 1% steps (0x00-0x64),
while BDRs (``13:``) use the evohome 0-200 demand scale.  The ramses_rf
payload decoders applied the 0-200 scale to every sender, so an OTB
``3EF0`` broadcast wrote exactly half the true fraction — the HA sensor
sat at ~50% of the OTGW value except for periodic ~5-minute spikes when
a controller-driven ``3220|0x11`` poll overwrote it with the correct
value.

The fix decodes the modulation byte on the 1% scale for ``10:`` senders
only, so ``3EF0`` broadcasts and ``3220|0x11`` Read-Acks agree.

The recipe injects, for one OTB:

1. ``RP 3220`` Data-ID ``0x11`` value ``0x2E00`` (f8.8 = 46%) — the HA
   sensor must read 46%.
2. ``I 3EF0`` 9-byte with modulation byte ``0x2E`` (46%) and
   max-modulation byte ``0x64`` (100%) — the sensor must stay at 46%
   (pre-fix it dropped to 23%) and the max sensor must read 100%
   (pre-fix 50%).
"""

from __future__ import annotations

import json
import urllib.request

import yaml

from ..base import Recipe, RecipeContext
from ..const import HGI
from ..helpers import (
    call_service,
    clear_cached_state,
    get_current_instance,
    load_profile_yaml,
    wait_for_transport_ready,
)

OTB = "10:048456"  # the reporter's R8810A bridge
HGI_ID = HGI  # 18:001234

# RP 3220 frame 00 C0 11 2E00: Read-Ack, Data-ID 0x11 (RelModLevel),
# f8.8 value 0x2E00 = 46%.
PKT_3220_PAYLOAD = "00C0112E00"

# I 3EF0 9-byte: modulation byte 0x2E = 46%, byte 8 0x64 = 100% max.
PKT_3EF0_PAYLOAD = "002E100A00FF024164"

REL_MOD_PCT = 46.0
MAX_MOD_PCT = 100.0
TOL = 1.0  # %


def _get_otb_sensor(token: str, kind: str) -> str | None:
    """Return the entity_id of the OTB's rel-modulation sensor.

    ``kind`` is ``"rel"`` for ``rel_modulation_level`` or ``"max"`` for
    ``max_rel_modulation``.  Entities are matched on the ``id`` device
    attribute plus a substring of the entity_id.
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
        entity_id = state.get("entity_id", "")
        if not entity_id.startswith("sensor."):
            continue
        if state.get("attributes", {}).get("id") != OTB:
            continue
        if "modulation" not in entity_id:
            continue
        if (kind == "max") == ("max" in entity_id):
            return entity_id
    return None


def _get_sensor_value(token: str, entity_id: str | None) -> float | None:
    """Return the numeric state of a sensor entity (percent)."""
    if entity_id is None:
        return None
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


class R160OtbRelModPercentScaleIssue1414(Recipe):
    id = "R160"
    seq = 1600
    title = "OTB 3EF0/3220 rel-modulation percent scale (issue 1414)"
    tags = ("decoder", "3ef0", "3220", "otb")

    async def run(self, ctx: RecipeContext) -> None:
        ctx.log_section("Recipe 160: OTB rel-modulation scale (issue 1414)")

        # Reporter's OTB bridge; standalone known device is enough — the
        # OtbGateway sensors spawn from the known_list entry.
        profile = {
            "known_list": {
                OTB: {"class": "OTB"},
            },
            "_enforce_known_list": {"enabled": True},
        }

        clear_cached_state(ctx.log_monitor, label="R160 pre-restart")
        ctx.wait_for_ha_ready(timeout=30)
        ctx.log_monitor.reset_baseline()
        ctx.refresh_token()
        ctx.wait_for_ramses_cc_loaded(timeout=30)

        print("  Loading OTB profile...")
        await load_profile_yaml(
            ctx.token,
            yaml.dump(profile, default_flow_style=False, sort_keys=False),
            speed=0.01,
        )
        ctx.wait_for_ramses_cc_reload(timeout=20)
        ctx.refresh_token()
        wait_for_transport_ready(timeout=30)

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

        # Step 1: polled OpenTherm value — RP 3220 Data-ID 0x11 = 46%.
        print("  Step 1: OTB RP 3220|0x11 = 46% (polled value)...")
        _inject(OTB, "3220", PKT_3220_PAYLOAD, verb="RP", dst=HGI_ID)
        ctx.wait(2, "after 3220 Read-Ack")

        rel_sensor = None
        for _ in range(10):
            rel_sensor = _get_otb_sensor(ctx.token, "rel")
            if rel_sensor is not None:
                break
            ctx.wait(1, "for rel_modulation sensor")
        print(f"  rel_modulation sensor: {rel_sensor}")
        ctx.check(
            "OTB rel_modulation sensor exists",
            rel_sensor is not None,
            f"entity={rel_sensor}",
        )

        rel_after_3220 = _get_sensor_value(ctx.token, rel_sensor)
        print(f"  Sensor after 3220|0x11: {rel_after_3220}%")
        ctx.check(
            "3220|0x11 46% lands on the sensor",
            rel_after_3220 is not None and abs(rel_after_3220 - REL_MOD_PCT) <= TOL,
            f"state={rel_after_3220} (expected ~{REL_MOD_PCT})",
        )

        # Step 2: OTB 3EF0 broadcast with the SAME 46% — must not halve.
        print("  Step 2: OTB I 3EF0 9-byte (mod 0x2E=46%, max 0x64=100%)...")
        _inject(OTB, "3EF0", PKT_3EF0_PAYLOAD)
        ctx.wait(2, "after 3EF0 broadcast")

        rel_after_3ef0 = _get_sensor_value(ctx.token, rel_sensor)
        print(f"  Sensor after 3EF0 broadcast: {rel_after_3ef0}%")
        ctx.check(
            "3EF0 broadcast agrees with 3220 (no halving)",
            rel_after_3ef0 is not None and abs(rel_after_3ef0 - REL_MOD_PCT) <= TOL,
            f"state={rel_after_3ef0} (expected ~{REL_MOD_PCT}, "
            f"pre-fix showed ~{REL_MOD_PCT / 2})",
        )

        max_sensor = None
        for _ in range(10):
            max_sensor = _get_otb_sensor(ctx.token, "max")
            if max_sensor is not None:
                break
            ctx.wait(1, "for max_rel_modulation sensor")
        max_after = _get_sensor_value(ctx.token, max_sensor)
        print(f"  max_rel_modulation sensor {max_sensor}: {max_after}%")
        ctx.check(
            "OTB max_rel_modulation 0x64 = 100%",
            max_after is not None and abs(max_after - MAX_MOD_PCT) <= TOL,
            f"state={max_after} (expected ~{MAX_MOD_PCT}, "
            f"pre-fix showed ~{MAX_MOD_PCT / 2})",
        )

        print()
        print("  === Summary ===")
        print(f"  rel_modulation after 3220: {rel_after_3220}%")
        print(f"  rel_modulation after 3EF0: {rel_after_3ef0}%")
        print(f"  max_rel_modulation:        {max_after}%")
        if rel_after_3ef0 is not None and abs(rel_after_3ef0 - REL_MOD_PCT) <= TOL:
            print("  CONFIRMED: OTB 3EF0 and 3220 agree — no sawtooth")
