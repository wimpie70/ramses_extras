"""Recipe R147: Orcon model selects 31E0 demand domain (PR 1293).

The Orcon HRC-350 (VMD-15RMS64/VMD-15RMS86) encodes ventilation demand
in the *first* domain of the 31E0 payload at high resolution
(``0000{demand*200:02X}0001000000``), while generic Orcon VMD units —
including the distinct ``VMD-15RMS86-2`` — use the *second* domain at
percentage resolution (``000000000100{demand*100:02X}00``).  PR 1293
extends the model-based strategy selection so the exact 10E0 model
``VMD-15RMS86`` (without ``-2`` suffix) gets HRC-350 behaviour.

This recipe verifies end-to-end via a faked CO2 sensor bound to an
Orcon FAN:

  1. Before any 10E0, ``put_ventilation_demand`` emits the generic
     second-domain payload (model unknown → ``OrconStrategy``)
  2. After an injected ``I|10E0`` reporting ``VMD-15RMS86``, the same
     service emits the HRC-350 first-domain payload
  3. After an injected ``I|10E0`` reporting ``VMD-15RMS86-2``, it
     returns to the generic second-domain payload — the exact-match
     set deliberately excludes the ``-2`` variant

Distinct demand values per phase keep the expected payloads unique in
the packet log.

See: https://github.com/ramses-rf/ramses_rf/pull/1293
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, cast

from ..base import Recipe, RecipeContext
from ..const import CO2, FAN
from ..helpers import (
    call_service,
    container_log_timestamp,
    get_entities,
    load_profile_yaml,
    log_lines_since,
    wait_for,
    wait_for_schema_populated,
    wait_for_transport_ready,
    ws_send,
)
from ..profile import MIXED_SCHEMA, _build_yaml, get_mixed_kl

# 10E0 device-info payloads differing only in the description field
# (same layout as R132's real Orcon capture).
_TEN_E0_PREFIX = "000001C85F0E0267FFFFFFFFFFFFFFFFFFFF"
TEN_E0_VMD_15RMS86 = _TEN_E0_PREFIX + "564D442D3135524D53383600"  # VMD-15RMS86
TEN_E0_VMD_15RMS86_2 = _TEN_E0_PREFIX + "564D442D3135524D5338362D3200"  # VMD-15RMS86-2

# Demand payloads per phase — distinct values keep each unique.
# 25% generic:    0.25*100=25  -> 0x19 ; 50% HRC-350:  0.50*200=100 -> 0x64
# 75% generic(-2): 0.75*100=75 -> 0x4B
GENERIC_25 = "0000000001001900"
HRC350_50 = "0000640001000000"
GENERIC_75 = "0000000001004B00"


class R147OrconModelSelects31e0DemandDomain(Recipe):
    id = "R147"
    seq = 1470
    title = "Orcon model selects 31E0 demand domain (PR 1293)"
    tags = ("31E0", "10E0", "fan", "co2", "orcon", "strategy", "model")

    async def run(self, ctx: RecipeContext) -> None:
        ctx.log_section("Recipe 147: Orcon model -> 31E0 domain (PR 1293)")

        ctx.refresh_token()

        # Orcon FAN with a faked CO2 sensor bound to it.  The faked/bound
        # traits must sit in the profile known_list — the minimal-schema
        # builder reads them from there into the internal schema.  The CO2
        # device is suppressed so the simulator registers it (ramses_rf
        # sees the traits) without emitting or answering any RF traffic.
        known_list = get_mixed_kl()
        known_list[FAN] = {"class": "FAN", "scheme": "orcon"}
        known_list[CO2] = {
            "class": "CO2",
            "faked": True,
            "bound": FAN,
            "suppress_autonomous": True,
            "suppress_responses": True,
        }

        schema = deepcopy(MIXED_SCHEMA)
        schema[FAN] = {
            **schema[FAN],
            "_class": "FAN",
            "_scheme": "orcon",
        }
        schema[CO2] = {
            "_class": "CO2",
            "_faked": True,
            "_bound": FAN,
        }

        try:
            await load_profile_yaml(
                ctx.token,
                _build_yaml(known_list, schema),
                speed=0.01,
            )
        except RuntimeError as err:
            ctx.check("Orcon CO2 profile loads", False, str(err)[:120])
            return
        ctx.wait_for_ramses_cc_reload(timeout=30)
        ctx.refresh_token()
        wait_for_transport_ready(timeout=30)

        try:
            await ws_send(
                ctx.token,
                {
                    "type": ("ramses_extras/device_simulator/activate_profile_device"),
                    "device_id": FAN,
                },
            )
        except RuntimeError:
            pass
        wait_for_schema_populated(timeout=20)

        # ── Find the CO2 sensor entity ──────────────────────────────
        # Must be the carbon_dioxide sensor specifically (entity id
        # uses the description label, not the co2_level key) — the
        # device also exposes a *_model diagnostic whose id contains
        # 'co2' too (sensor.co2_37_120000_model), and the entity
        # service asserts device_class == CO2 / unit == ppm.
        co2_suffix = CO2.replace(":", "_")

        def _find_co2_sensor() -> dict[str, Any] | None:
            for entity in get_entities(ctx.token):
                entity_id = entity.get("entity_id", "")
                if (
                    entity_id.startswith("sensor.")
                    and co2_suffix in entity_id
                    and entity_id.endswith("_carbon_dioxide")
                    and entity.get("state") != "unavailable"
                ):
                    return cast(dict[str, Any], entity)
            return None

        wait_for(
            _find_co2_sensor,
            timeout=30,
            interval=2,
            msg="for CO2 sensor entity",
            floor=10.0,
        )
        co2_sensor = _find_co2_sensor()
        ctx.check(
            "faked CO2 sensor entity exists",
            co2_sensor is not None,
            f"CO2={CO2}",
        )
        if co2_sensor is None:
            return

        def _inject_frame(dst: str | None, code: str, payload: str) -> None:
            """Replay an expected TX frame on the RX path to satisfy the
            gateway's TX echo wait.  This single-HGI sim never echoes TX
            frames, so without it sends retry every ~20s and back up the
            dispatcher queue for minutes.  Omit ``dst`` for announce
            frames (``I --- src --:------ src``)."""
            data: dict[str, Any] = {
                "source_id": CO2,
                "code": code,
                "payload": payload,
                "verb": "I",
            }
            if dst:
                data["dst"] = dst
            try:
                call_service(
                    ctx.token,
                    "ramses_extras",
                    "device_simulator_inject_message",
                    data,
                )
            except RuntimeError as err:
                print(f"    echo inject failed: {err}")

        def _prime_call() -> bool:
            """put_co2_level — the service may time out on the TX echo
            wait (transport artifact); the echo inject releases it."""
            for attempt in range(3):
                try:
                    call_service(
                        ctx.token,
                        "ramses_cc",
                        "put_co2_level",
                        {
                            "entity_id": co2_sensor["entity_id"],
                            "co2_level": 900,
                        },
                        timeout=8,
                        retries=1,
                    )
                except RuntimeError as err:
                    if "timed out" not in str(err):
                        print(f"    put_co2_level: {err}")
                        if attempt == 2:
                            return False
                        ctx.wait(3, "for put_co2_level retry", floor=2.0)
                        continue
                # 900 ppm -> 1298 payload 00 0384 (announce to self)
                _inject_frame(None, "1298", "000384")
                return True
            return False

        # Give the faked sensor a CO2 level — proves the entity is live
        # and targetable before the demand calls below.
        ctx.check(
            "put_co2_level primes the faked CO2 sensor",
            _prime_call(),
            f"entity={co2_sensor['entity_id']}",
        )

        def _inject_model(payload: str) -> None:
            call_service(
                ctx.token,
                "ramses_extras",
                "device_simulator_inject_message",
                {
                    "source_id": FAN,
                    "code": "10E0",
                    "payload": payload,
                    "verb": "I",
                },
            )

        def _model_state() -> str | None:
            for entity in get_entities(ctx.token):
                entity_id = entity.get("entity_id", "")
                if (
                    entity_id.startswith("sensor.")
                    and entity_id.endswith("_model")
                    and FAN.replace(":", "_") in entity_id
                ):
                    return cast(str | None, entity.get("state"))
            return None

        def _demand_and_expect(demand: int, payload: str) -> bool:
            """Fire put_ventilation_demand and check the HA log for the
            MQTT TX frame.  The dispatcher publishes the packet then
            blocks on a TX echo; the REST call may time out — that is a
            transport artifact, not a demand-path failure.  The injected
            echo releases the pending send so the queue stays drained."""
            expected = f"{CO2} {FAN} --:------ 31E0 008 {payload}"
            baseline = container_log_timestamp()
            for attempt in range(3):
                try:
                    call_service(
                        ctx.token,
                        "ramses_cc",
                        "put_ventilation_demand",
                        {
                            "entity_id": co2_sensor["entity_id"],
                            "ventilation_demand": demand,
                        },
                        timeout=8,
                        retries=1,
                    )
                except RuntimeError as err:
                    # Expected: echo-less transport -> the call blocks on
                    # 20s echo retries.  A validation/entity error would
                    # return fast with HTTP 4xx/500 instead of timing out.
                    if "timed out" not in str(err):
                        print(f"    put_ventilation_demand({demand}): {err}")
                        return False
                _inject_frame(FAN, "31E0", payload)
                wait_for(
                    lambda: any(
                        expected in line
                        for line in log_lines_since("home-assistant.log*", baseline)
                    ),
                    timeout=15,
                    interval=2,
                    msg=f"for 31E0 TX after demand {demand}",
                    floor=5.0,
                )
                if any(
                    expected in line
                    for line in log_lines_since("home-assistant.log*", baseline)
                ):
                    return True
                print(f"    demand {demand} attempt {attempt + 1}/3: no TX yet")
            return False

        # ── 1. No 10E0 yet: generic second-domain encoding ──────────
        ctx.check(
            "demand w/o model emits generic second-domain 31E0 (25%)",
            _demand_and_expect(25, GENERIC_25),
            f"expected={GENERIC_25}",
        )

        # ── 2. Model VMD-15RMS86: HRC-350 first-domain encoding ─────
        _inject_model(TEN_E0_VMD_15RMS86)
        model_ok = wait_for(
            lambda: _model_state() == "VMD-15RMS86",
            timeout=20,
            interval=2,
            msg="for FAN model sensor = VMD-15RMS86",
            floor=5.0,
        )
        ctx.check(
            "FAN model sensor reports VMD-15RMS86 after 10E0",
            model_ok,
            f"state={_model_state()}",
        )

        ctx.check(
            "VMD-15RMS86 selects HRC-350 first-domain 31E0 (50%)",
            _demand_and_expect(50, HRC350_50),
            f"expected={HRC350_50}",
        )

        # ── 3. Model VMD-15RMS86-2: back to generic second domain ───
        _inject_model(TEN_E0_VMD_15RMS86_2)
        wait_for(
            lambda: _model_state() == "VMD-15RMS86-2",
            timeout=20,
            interval=2,
            msg="for FAN model sensor = VMD-15RMS86-2",
            floor=5.0,
        )

        ctx.check(
            "VMD-15RMS86-2 keeps generic second-domain 31E0 (75%)",
            _demand_and_expect(75, GENERIC_75),
            f"expected={GENERIC_75}",
        )
