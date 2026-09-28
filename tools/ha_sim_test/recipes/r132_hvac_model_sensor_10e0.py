"""Recipe R132: HVAC model sensor populated from 10E0 device info.

Covers the ramses_cc model-entity feature for ramses-rf/ramses_cc issue
1236:

    Every HVAC device (DeviceHvac: FAN, REM, CO2, HUM, ...) gets a
    diagnostic ``model`` sensor whose state is the 10E0 ``description``
    (e.g. ``"VMC-15RPS34"``), or ``unknown`` until a 10E0 packet is
    received.  The remaining 10E0 fields (oem_code, manufacturer_sub_id,
    product_id, dates) are exposed as attributes.

    The device-registry ``model`` is also refreshed when the 10E0 first
    arrives — previously it was frozen at the _SLUG fallback set at
    discovery time.

This recipe injects the real 10E0 packet captured from an Orcon MVS-15
(``VMC-15RPS34``) in ramses-rf/ramses_cc issue 1231 and verifies:
1. The model sensor starts as ``unknown``
2. A faked device reports ``faked`` (it never sends a 10E0)
3. After the 10E0, the sensor state is ``"VMC-15RPS34"`` and the raw
   10E0 fields are present as attributes
4. The HA device-registry ``model`` is updated to the same string
5. HGIs get no model sensor (serial gateways cannot provide reliable
   device-originated 10E0 info)
6. No PacketInvalid warnings appear in the log

See: https://github.com/ramses-rf/ramses_cc/issues/1236
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from copy import deepcopy

from ..base import Recipe, RecipeContext
from ..const import CTL, FAN
from ..helpers import (
    call_service,
    get_docker_logs,
    get_entities,
    load_profile_yaml,
    wait_for_ramses_extras_ready,
    wait_for_schema_populated,
    wait_for_transport_ready,
    ws_send,
)
from ..profile import MIXED_SCHEMA, _build_yaml, get_mixed_kl

FAN_ID = "32:150000"
FAKED_REM_ID = "37:999999"  # faked REM: model sensor must report 'faked'
MODEL_SENSOR_KEY = "model"

# Real 10E0 packet from an Orcon MVS-15 (32:231021) — description decodes
# to "VMC-15RPS34" (issue 1231 packet log).
TEN_E0_PAYLOAD = "000001C85F0E0267FFFFFFFFFFFFFFFFFFFF564D432D3135525053333400"
EXPECTED_MODEL = "VMC-15RPS34"


def _get_entity_state(token: str, entity_id: str) -> dict | None:
    """Fetch an entity's full state dict from the HA API.

    :param token: HA bearer token.
    :param entity_id: The entity_id to query.
    :return: The state dict, or None if the entity doesn't exist.
    """
    from ..helpers import get_current_instance

    req = urllib.request.Request(
        f"{get_current_instance().ha_url}/api/states/{entity_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    try:
        resp = urllib.request.urlopen(req, timeout=10)
        return json.loads(resp.read())
    except urllib.error.HTTPError:
        return None


class R132HvacModelSensor10e0(Recipe):
    id = "R132"
    seq = 1320
    title = "HVAC model sensor populated from 10E0 (issue 1236)"
    tags = ("10E0", "fan", "model", "diagnostic")

    async def run(self, ctx: RecipeContext) -> None:
        """Inject a 10E0 for the FAN and check the model sensor."""
        ctx.log_section(
            "Recipe 132: HVAC model sensor from 10E0 (ramses_cc issue 1236)"
        )

        ctx.refresh_token()
        wait_for_ramses_extras_ready(timeout=90, msg="for ramses_extras")

        # Load the mixed profile plus a faked REM: faked devices never
        # send a 10E0, so their model sensor should report 'faked'.
        schema = deepcopy(MIXED_SCHEMA)
        schema[FAKED_REM_ID] = {
            "_class": "REM",
            "_faked": True,
            "_bound": FAN_ID,
        }

        try:
            await load_profile_yaml(
                ctx.token,
                _build_yaml(get_mixed_kl(), schema),
                speed=0.01,
            )
            print("  Profile loaded (with faked REM 37:999999)")
        except RuntimeError as e:
            ctx.check("HVAC profile loads", False, str(e)[:120])
            return
        ctx.wait_for_ramses_cc_reload(timeout=30)
        ctx.refresh_token()
        wait_for_transport_ready(timeout=30)

        # Activate FAN and CTL for packet injection.
        for dev_id in (FAN_ID, CTL):
            try:
                await ws_send(
                    ctx.token,
                    {
                        "type": (
                            "ramses_extras/device_simulator/activate_profile_device"
                        ),
                        "device_id": dev_id,
                    },
                )
            except RuntimeError as e:
                print(f"  Activate {dev_id} failed: {e}")
        ctx.wait(5, "for devices to activate")
        wait_for_schema_populated(timeout=20)

        # Find the model sensor entities for the FAN and the faked REM.
        # The gateway HGI must NOT have one: a serial gateway cannot
        # provide reliable device-originated 10E0 info.
        entities = get_entities(ctx.token)
        model_entity_id = None
        faked_entity_id = None
        hgi_entity_id = None
        for e in entities:
            eid = e.get("entity_id", "")
            if eid.endswith(f"_{MODEL_SENSOR_KEY}") and "32_150000" in eid:
                model_entity_id = eid
            if eid.endswith(f"_{MODEL_SENSOR_KEY}") and "37_999999" in eid:
                faked_entity_id = eid
            if eid.endswith(f"_{MODEL_SENSOR_KEY}") and "18_001234" in eid:
                hgi_entity_id = eid

        if model_entity_id is None:
            ctx.check(
                "model sensor entity exists for FAN 32:150000",
                False,
                "no entity ending '_model' with '32_150000' found",
            )
            return
        print(f"  model sensor: {model_entity_id}")

        # The faked REM never sends a 10E0: its sensor reports 'faked'.
        if faked_entity_id is None:
            ctx.check(
                "model sensor entity exists for faked REM 37:999999",
                False,
                "no entity ending '_model' with '37_999999' found",
            )
        else:
            faked_state = _get_entity_state(ctx.token, faked_entity_id)
            faked_val = faked_state.get("state") if faked_state else None
            print(f"  faked REM model state: {faked_val}")
            ctx.check(
                "faked device model sensor reports 'faked'",
                faked_val == "faked",
                f"state={faked_val}",
            )

        # HGIs get no model sensor: a serial gateway cannot provide
        # reliable device-originated 10E0 info, so the entity would
        # just sit at 'unknown' forever (or worse, show a polled
        # device's reply — the bogus 'VMS-15C16' seen in the field).
        ctx.check(
            "no model sensor for HGI 18:001234",
            hgi_entity_id is None,
            f"hgi_entity_id={hgi_entity_id}",
        )

        # Before any 10E0 the sensor should be unknown.
        state = _get_entity_state(ctx.token, model_entity_id)
        initial = state.get("state") if state else None
        print(f"  initial model state: {initial}")
        ctx.check(
            "model sensor is 'unknown' before any 10E0",
            initial == "unknown",
            f"state={initial}",
        )

        # Inject the real MVS-15 10E0 packet from the FAN.
        call_service(
            ctx.token,
            "ramses_extras",
            "device_simulator_inject_message",
            {
                "source_id": FAN_ID,
                "verb": "I",
                "code": "10E0",
                "payload": TEN_E0_PAYLOAD,
            },
        )
        ctx.wait(3, "for model sensor update")

        state = _get_entity_state(ctx.token, model_entity_id)
        actual = state.get("state") if state else None
        ctx.check(
            f"model sensor decodes 10E0 description '{EXPECTED_MODEL}'",
            actual == EXPECTED_MODEL,
            f"expected={EXPECTED_MODEL}, actual={actual}",
        )

        attrs = state.get("attributes", {}) if state else {}
        ctx.check(
            "model sensor exposes raw 10E0 fields as attributes",
            attrs.get("product_id") == "5F"
            and attrs.get("manufacturer_sub_id") == "C8"
            and attrs.get("oem_code") == "67",
            "attrs="
            + str(
                {
                    k: attrs.get(k)
                    for k in ("oem_code", "manufacturer_sub_id", "product_id")
                }
            ),
        )

        # A 10E0 RP *addressed to* the HGI (a reply to its RQ poll)
        # describes the sender, not the gateway.  ramses_rf filters
        # 10E0 by source so the reply cannot pollute the HGI's model
        # (the bogus 'VMS-15C16' seen in the field) — covered by unit
        # tests there.  The FAN's model is unaffected either way.
        call_service(
            ctx.token,
            "ramses_extras",
            "device_simulator_inject_message",
            {
                "source_id": FAN_ID,
                "dst": "18:001234",
                "verb": "RP",
                "code": "10E0",
                "payload": TEN_E0_PAYLOAD,
            },
        )
        ctx.wait(2, "for addressed 10E0 reply")
        state = _get_entity_state(ctx.token, model_entity_id)
        actual = state.get("state") if state else None
        ctx.check(
            "FAN model unaffected by its own addressed 10E0 reply",
            actual == EXPECTED_MODEL,
            f"state={actual}",
        )

        # The device-registry model should have been refreshed too.  The
        # coordinator only rebuilds DeviceInfo on its scan-interval timer,
        # so poll until it catches up.
        registry_model = None
        for _ in range(30):
            try:
                result = await ws_send(
                    ctx.token, {"type": "config/device_registry/list"}
                )
                devices = (
                    result if isinstance(result, list) else result.get("devices", [])
                )
                fan_entry = next(
                    (
                        d
                        for d in devices
                        if any(
                            isinstance(ident, list)
                            and len(ident) == 2
                            and ident[0] == "ramses_cc"
                            and ident[1] == FAN_ID
                            for ident in d.get("identifiers", [])
                        )
                    ),
                    None,
                )
                registry_model = fan_entry.get("model") if fan_entry else None
            except RuntimeError as e:
                print(f"  device-registry lookup failed: {e}")
            if registry_model == EXPECTED_MODEL:
                break
            ctx.wait(3, "for device-registry refresh")
        ctx.check(
            "device-registry model updated to 10E0 description",
            registry_model == EXPECTED_MODEL,
            f"registry model={registry_model}",
        )

        # No 'Null packet' / PacketInvalid warnings for the injection.
        log_text = get_docker_logs(since="120s")
        has_null_packet = any(
            "10E0" in line and "Null packet" in line for line in log_text.splitlines()
        )
        ctx.check(
            "No 'Null packet' PacketInvalid for 10E0 injection",
            not has_null_packet,
            "Null packet PacketInvalid found for 10E0 in logs"
            if has_null_packet
            else "",
        )
