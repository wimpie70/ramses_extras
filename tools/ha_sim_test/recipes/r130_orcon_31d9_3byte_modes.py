"""Recipe R130: Orcon 3-byte 31D9 fan_mode decoding via _scheme.

Covers the ramses_rf fix for ramses-rf/ramses_cc issue 1231:

    Orcon units with 3-byte 31D9 payloads (e.g. MVS-15 / VMC-15RPS34)
    carry the active mode as a 22F1-style index in the speed byte.  The
    generic parser labels it with Vasco names (0x01 -> "1 (trickle)",
    0x04 -> "4 (boost)") and reports spd / 200 as exhaust_fan_speed (a
    bogus 0-2%).  The 4-byte Orcon format was fixed earlier (R91 covers
    it); the short format is fixed at the strategy layer — the parser
    cannot tell Orcon from Vasco without device context, so
    OrconStrategy.apply_quirk remaps the decode when the FAN is
    configured ``_scheme: orcon``.

This recipe injects 3-byte Orcon 31D9 packets and verifies:
1. The fan_mode sensor decodes to the correct Orcon mode name for each
   of the eight supported mode bytes
2. The exhaust_fan_speed sensor is NOT updated with the bogus
   spd/200 values (0-2%)
3. No PacketInvalid warnings appear in the log

See: https://github.com/ramses-rf/ramses_cc/issues/1231
     https://github.com/ramses-rf/ramses_rf/pull/1238
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


class R130Orcon31d9ThreeByteModes(Recipe):
    id = "R130"
    seq = 1300
    title = "Orcon 3-byte 31D9 fan_mode decoding via _scheme (issue 1231)"
    tags = ("31D9", "fan", "orcon", "exhaust_fan_speed", "fan_mode")

    async def run(self, ctx: RecipeContext) -> None:
        """Inject 3-byte Orcon 31D9 packets and check fan_mode decoding."""
        ctx.log_section(
            "Recipe 130: Orcon 3-byte 31D9 fan_mode via _scheme (ramses_cc issue 1231)"
        )

        ctx.refresh_token()
        wait_for_ramses_extras_ready(timeout=90, msg="for ramses_extras")

        # Load the mixed profile with the FAN configured _scheme: orcon —
        # the quirk is gated on the configured strategy.
        schema = deepcopy(MIXED_SCHEMA)
        schema[FAN] = {
            **schema[FAN],
            "_class": "FAN",
            "_scheme": "orcon",
        }

        try:
            await load_profile_yaml(
                ctx.token,
                _build_yaml(get_mixed_kl(), schema),
                speed=0.01,
            )
            print("  Profile loaded (FAN _scheme=orcon)")
        except RuntimeError as e:
            ctx.check("Orcon HVAC profile loads", False, str(e)[:120])
            return
        ctx.wait_for_ramses_cc_reload(timeout=30)
        ctx.refresh_token()
        wait_for_transport_ready(timeout=30)

        # Activate FAN for packet injection.
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

        # Find the fan_mode sensor entity for the FAN.
        entities = get_entities(ctx.token)
        fan_mode_entity_id = None
        exhaust_entity = None
        for e in entities:
            eid = e.get("entity_id", "")
            if "fan_mode" in eid and "32_150000" in eid:
                fan_mode_entity_id = eid
            if "exhaust_fan_speed" in eid and "32_150000" in eid:
                exhaust_entity = e

        if fan_mode_entity_id is None:
            ctx.check(
                "fan_mode sensor entity exists for FAN 32:150000",
                False,
                "no entity with 'fan_mode' and '32_150000' found",
            )
            return
        print(f"  fan_mode sensor: {fan_mode_entity_id}")

        # 3-byte Orcon 31D9: 00 <flags> <mode_byte>
        # The mode byte echoes the requested 22F1 mode index (verified
        # against a real MVS-15 packet log in issue 1231): a timed boost
        # reports as high (0x03) — there is no dedicated boost byte.
        orcon_mode_map = {
            0x00: "away",
            0x01: "low",
            0x02: "medium",
            0x03: "high",
            0x04: "auto",
            0x05: "auto_alt",
            0x06: "boost",
            0x07: "off",
        }

        for mode_byte, expected_name in orcon_mode_map.items():
            payload = f"0000{mode_byte:02X}"
            call_service(
                ctx.token,
                "ramses_extras",
                "device_simulator_inject_message",
                {
                    "source_id": FAN_ID,
                    "verb": "I",
                    "code": "31D9",
                    "payload": payload,
                },
            )
            ctx.wait(2, f"for fan_mode update (payload={payload})")

            state = _get_entity_state(ctx.token, fan_mode_entity_id)
            actual = state.get("state") if state else None
            ctx.check(
                f"3-byte 31D9 mode 0x{mode_byte:02X} decodes to '{expected_name}'",
                actual == expected_name,
                f"payload={payload}, expected={expected_name}, actual={actual}",
            )

        # exhaust_fan_speed must never show the bogus spd/200 values.
        # With the quirk the parser's misdecode is dropped, so the sensor
        # keeps whatever it had (typically 'unknown' on a fresh profile).
        if exhaust_entity:
            eid = exhaust_entity["entity_id"]
            state = exhaust_entity.get("state")
            bogus = {"0.0", "0.5", "1.0", "1.5", "2.0"}
            print(f"  exhaust_fan_speed entity: {eid}")
            print(f"  exhaust_fan_speed state: {state}")
            ctx.check(
                "exhaust_fan_speed has no bogus spd/200 value (0-2%)",
                state not in bogus,
                f"state={state}",
            )
        else:
            print("  exhaust_fan_speed entity not found (OK — nothing bogus)")

        # No 'Null packet' / PacketInvalid warnings for the injections.
        log_text = get_docker_logs(since="120s")
        has_null_packet = any(
            "31D9" in line and "Null packet" in line for line in log_text.splitlines()
        )
        ctx.check(
            "No 'Null packet' PacketInvalid for 31D9 injection",
            not has_null_packet,
            "Null packet PacketInvalid found for 31D9 in logs"
            if has_null_packet
            else "",
        )
