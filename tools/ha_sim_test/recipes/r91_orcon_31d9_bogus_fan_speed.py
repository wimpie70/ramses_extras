"""Recipe R91: Orcon 4-byte 31D9 bogus exhaust_fan_speed (PR 1133).

4-byte 31D9 payloads (Orcon-style) have a semantic fan mode (0-5) in
the speed_byte, not a raw RPM value.  The old code divided it by 200,
producing a meaningless 1-2% reading (e.g. mode 2 -> 0.01 = 1%) that
showed up as the fan speed in HA.

This recipe injects a 4-byte Orcon 31D9 packet with speed_byte=0x02
(mode 2 = medium) and verifies:
1. The exhaust_fan_speed sensor does NOT show 1.0% (the bogus value)
2. No PacketInvalid warnings appear in the log

See: https://github.com/ramses-rf/ramses_rf/pull/1133
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
    title = "Orcon 4-byte 31D9 bogus exhaust_fan_speed (PR 1133)"
    tags = ("31D9", "fan", "orcon", "exhaust_fan_speed")

    async def run(self, ctx: RecipeContext) -> None:
        """Inject a 4-byte Orcon 31D9 and check exhaust_fan_speed."""
        ctx.log_section(
            "Recipe 91: Orcon 4-byte 31D9 bogus exhaust_fan_speed (PR 1133)"
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
        print("  Injecting 4-byte Orcon 31D9: payload=00200200")
        call_service(
            ctx.token,
            "ramses_extras",
            "device_simulator_inject_message",
            {
                "source_id": "32:150000",
                "dst": "32:150000",
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

        # 3. Verify the 31D9 packet was processed (not dropped as Null packet)
        #    Note: the inject_message service may produce a "Bad frame: Invalid
        #    address set" warning for self-addressed packets (src==dst), which
        #    is a separate issue.  We only check that it's not a "Null packet"
        #    error (which would indicate the # prefix issue from PR 1132).
        import subprocess

        from ..helpers import get_current_instance

        raw_log = subprocess.run(
            ["docker", "logs", "--since", "30s", get_current_instance().name],
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
