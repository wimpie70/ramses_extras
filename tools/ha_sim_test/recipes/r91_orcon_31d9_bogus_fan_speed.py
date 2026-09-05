"""Recipe R91: Orcon 4-byte 31D9 fan_mode decoding + bogus exhaust_fan_speed.

Covers two ramses_rf parser fixes for 4-byte Orcon 31D9 payloads:

PR 1133 — bogus exhaust_fan_speed:
    4-byte 31D9 payloads (Orcon-style) have a semantic fan mode (0-7) in
    the speed_byte, not a raw RPM value.  The old code divided it by 200,
    producing a meaningless 1-2% reading (e.g. mode 2 -> 0.01 = 1%) that
    showed up as the fan speed in HA.

PR 1193 — fan_mode decoded with the vendor mode map:
    The 4-byte Orcon 31D9 parser used a minimal ``{0: "off", 5: "auto"}``
    map, so mode 0x00 was labelled "off" (should be "away"), mode 0x07
    was raw hex "07" (should be "off"), and modes 0x01-0x06 were raw hex.
    The fix uses the existing ``_22F1_MODE_ORCON`` table so all eight
    modes decode to their semantic names.

This recipe injects 4-byte Orcon 31D9 packets and verifies:
1. The exhaust_fan_speed sensor does NOT show 1.0% (the bogus value)
2. The fan_mode sensor decodes to the correct Orcon mode name for each
   of the eight supported mode bytes plus an unknown boundary value
3. No PacketInvalid warnings appear in the log

See: https://github.com/ramses-rf/ramses_rf/pull/1133
     https://github.com/ramses-rf/ramses_rf/pull/1193
     https://gathering.tweakers.net/forum/view_message/86013804
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

from ..base import Recipe, RecipeContext
from ..const import CTL, FAN
from ..helpers import (
    call_service,
    get_entities,
    load_profile_yaml,
    wait_for,
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
    except urllib.error.HTTPError, Exception:
        return None


class R91Orcon31d9BogusFanSpeed(Recipe):
    id = "R91"
    seq = 910
    title = (
        "Orcon 4-byte 31D9 fan_mode decoding + bogus exhaust_fan_speed (PR 1133, 1193)"
    )
    tags = ("31D9", "fan", "orcon", "exhaust_fan_speed", "fan_mode")

    async def run(self, ctx: RecipeContext) -> None:
        """Inject 4-byte Orcon 31D9 packets and check fan_mode + exhaust_fan_speed."""
        ctx.log_section(
            "Recipe 91: Orcon 4-byte 31D9 fan_mode + exhaust_fan_speed (PR 1133, 1193)"
        )

        ctx.refresh_token()
        wait_for_ramses_extras_ready(timeout=90, msg="for ramses_extras")

        # Load the mixed profile (has FAN 32:150000).
        try:
            await load_profile_yaml(
                ctx.token,
                _build_yaml(get_mixed_kl(), MIXED_SCHEMA),
                speed=0.01,
            )
            print("  Profile loaded")
        except RuntimeError as e:
            print(f"  Profile load failed: {e}")
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

        # 1. Inject a 4-byte Orcon 31D9 packet with speed_byte=0x02
        #    Payload: 00 20 02 00
        #    - header=0x00, flags=0x20, speed_byte=0x02 (mode 2=medium)
        #    - The old code would compute exhaust_fan_speed = 2/200 = 0.01 (1%)
        #    - The fix suppresses exhaust_fan_speed for 4-byte payloads
        #    - No dst = broadcast (--:------), matching real FAN behaviour
        print("  Injecting 4-byte Orcon 31D9: payload=00200200")
        call_service(
            ctx.token,
            "ramses_extras",
            "device_simulator_inject_message",
            {
                "source_id": "32:150000",
                "verb": "I",
                "code": "31D9",
                "payload": "00200200",
            },
        )
        ctx.wait(3, "for state update")

        # 2. Check the exhaust_fan_speed sensor
        entities = get_entities(ctx.token)
        exhaust_entity = None
        for e in entities:
            eid = e.get("entity_id", "")
            if "exhaust_fan_speed" in eid and "32_150000" in eid:
                exhaust_entity = e
                break

        if exhaust_entity:
            eid = exhaust_entity["entity_id"]
            state = exhaust_entity.get("state")
            print(f"  exhaust_fan_speed entity: {eid}")
            print(f"  exhaust_fan_speed state: {state}")

            # The bogus value would be "1.0" (1%).
            # With the fix, the sensor should not be updated to 1.0%
            # from this 4-byte packet.
            ctx.check(
                "exhaust_fan_speed is NOT 1.0% (bogus Orcon value)",
                state != "1.0",
                f"state={state}",
            )
        else:
            print("  exhaust_fan_speed entity not found")
            ctx.check(
                "exhaust_fan_speed entity exists",
                False,
                "no entity with 'exhaust_fan_speed' and '32_150000' found",
            )

        # 3. Fan mode decoding (PR 1193)
        #    The 4-byte Orcon 31D9 speed_byte is a semantic mode index, not
        #    a raw RPM.  PR 1193 maps it via _22F1_MODE_ORCON so all eight
        #    supported modes decode to their vendor names.  Before the fix,
        #    mode 0x00 was "off" (should be "away"), 0x07 was raw "07"
        #    (should be "off"), and 0x01-0x06 were raw hex.
        #
        #    Payload format: 00 20 SS 00  (header, flags, mode_byte, pad)
        #    We use flags=0x20 (filter_dirty) to match the PR test fixtures.
        from ..helpers import get_current_instance

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

        # Find the fan_mode sensor entity for FAN 32:150000.
        entities = get_entities(ctx.token)
        fan_mode_entity_id = None
        for e in entities:
            eid = e.get("entity_id", "")
            if "fan_mode" in eid and "32_150000" in eid:
                fan_mode_entity_id = eid
                break

        if fan_mode_entity_id is None:
            print("  fan_mode sensor entity not found")
            ctx.check(
                "fan_mode sensor entity exists for FAN 32:150000",
                False,
                "no entity with 'fan_mode' and '32_150000' found",
            )
        else:
            print(f"  fan_mode sensor: {fan_mode_entity_id}")

            # Test each supported mode byte via the fan_mode sensor.
            # The sensor retains its last state for unknown modes (a
            # sensor-level caching behaviour), so we only assert on the
            # 8 known modes here and verify the unknown boundary (0x08)
            # via the log below.
            for mode_byte, expected_name in orcon_mode_map.items():
                payload = f"0020{mode_byte:02X}00"
                call_service(
                    ctx.token,
                    "ramses_extras",
                    "device_simulator_inject_message",
                    {
                        "source_id": "32:150000",
                        "verb": "I",
                        "code": "31D9",
                        "payload": payload,
                    },
                )
                ctx.wait(2, f"for fan_mode update (payload={payload})")

                state = _get_entity_state(ctx.token, fan_mode_entity_id)
                actual = state.get("state") if state else None
                ctx.check(
                    f"31D9 mode 0x{mode_byte:02X} decodes to '{expected_name}'",
                    actual == expected_name,
                    f"payload={payload}, expected={expected_name}, actual={actual}",
                )

            # Unknown boundary: inject mode 0x08 and verify the parser
            # returns raw hex "08" (not a wrong semantic name).  The
            # sensor may retain its previous state, so we check the log
            # for the decoded payload instead.
            call_service(
                ctx.token,
                "ramses_extras",
                "device_simulator_inject_message",
                {
                    "source_id": "32:150000",
                    "verb": "I",
                    "code": "31D9",
                    "payload": "00200800",
                },
            )
            ctx.wait(2, "for 31D9 0x08 to be processed")

        # 4. Verify the 31D9 packets were processed correctly
        #    We inject as broadcast (no dst) to avoid the "Bad frame: Invalid
        #    address set" warning that self-addressed packets (src==dst) get.
        #    We check:
        #    a) no "Null packet" errors (PR 1132 regression)
        #    b) the unknown mode 0x08 was decoded as raw hex "08" by the
        #       parser (visible in the handle_event log payload)
        import subprocess

        raw_log = subprocess.run(
            ["docker", "logs", "--since", "120s", get_current_instance().name],
            capture_output=True,
            text=True,
            timeout=10,
        )
        log_text = raw_log.stderr or raw_log.stdout
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

        # The handle_event log line for 00200800 should show
        # 'fan_mode': '08' (raw hex, not a wrong semantic name).
        has_raw_08 = any(
            "00200800" in line and "'fan_mode': '08'" in line
            for line in log_text.splitlines()
        )
        ctx.check(
            "31D9 unknown mode 0x08 parsed as raw hex '08' (not misinterpreted)",
            has_raw_08,
            "expected 'fan_mode': '08' in log for payload 00200800"
            if not has_raw_08
            else "",
        )
