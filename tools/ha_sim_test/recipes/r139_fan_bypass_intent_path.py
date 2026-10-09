"""Recipe R139: fan bypass commands via the SET_BYPASS_POSITION intent path.

ramses_extras routes ``fan_bypass_*`` commands through the ramses_rf
intent/dispatcher layer (``Action.SET_BYPASS_POSITION``) instead of raw
``create_cmd`` packets when the upstream builder emits a valid 3-byte 22F7
payload (ramses_rf >= 0.60.10 — see ramses-rf/ramses_cc issue 1298 and
wimpie70/ramses_extras issue 241 item 3.12).

This recipe verifies the emitted wire frame: sourced from the FAN's bound
REM, addressed to the FAN, with the expected 3-byte payload.
"""

from __future__ import annotations

from copy import deepcopy

from ..base import Recipe, RecipeContext
from ..const import CTL, FAN, REM
from ..helpers import (
    call_service,
    container_log_timestamp,
    load_profile_yaml,
    log_lines_since,
    wait_for,
    wait_for_schema_populated,
    wait_for_transport_ready,
    ws_send,
)
from ..profile import MIXED_SCHEMA, _build_yaml, get_mixed_kl


class R139FanBypassIntentPath(Recipe):
    id = "R139"
    seq = 1390
    title = "fan_bypass_* via SET_BYPASS_POSITION intent (issue 241/3.12)"
    tags = ("22F7", "fan", "bypass", "intent", "orcon")

    async def run(self, ctx: RecipeContext) -> None:
        """Verify fan_bypass_* emits REM->FAN 22F7 W frames via intents."""
        ctx.log_section("Recipe 139: fan bypass SET_BYPASS_POSITION intent")

        ctx.refresh_token()

        schema = deepcopy(MIXED_SCHEMA)
        schema[FAN] = {
            **schema[FAN],
            "_bound": [REM],
            "_class": "FAN",
            "_scheme": "orcon",
            "remotes": [REM],
        }
        schema[REM] = {
            **schema[REM],
            "_bound": FAN,
            "_class": "REM",
            "_faked": True,
            "_scheme": "orcon",
        }

        try:
            await load_profile_yaml(
                ctx.token,
                _build_yaml(get_mixed_kl(), schema),
                speed=0.01,
            )
        except RuntimeError as err:
            ctx.check("Orcon HVAC profile loads", False, str(err)[:120])
            return
        ctx.wait_for_ramses_cc_reload(timeout=30)
        ctx.refresh_token()
        wait_for_transport_ready(timeout=30)

        for device_id in (FAN, REM, CTL):
            try:
                await ws_send(
                    ctx.token,
                    {
                        "type": (
                            "ramses_extras/device_simulator/activate_profile_device"
                        ),
                        "device_id": device_id,
                    },
                )
            except RuntimeError:
                pass
        wait_for_schema_populated(timeout=20)

        # bypass open: mode "on" -> C8 -> payload 00C8EF
        for command, expected in (
            ("fan_bypass_open", f"W --- {REM} {FAN} --:------ 22F7 003 00C8EF"),
            ("fan_bypass_auto", f"W --- {REM} {FAN} --:------ 22F7 003 00FFEF"),
        ):
            baseline = container_log_timestamp()
            try:
                call_service(
                    ctx.token,
                    "ramses_extras",
                    "send_fan_command",
                    {"device_id": FAN, "command": command},
                    timeout=15,
                )
            except RuntimeError as err:
                print(f"    send_fan_command({command}) raised: {err}")

            sent = wait_for(
                lambda expected=expected, baseline=baseline: any(
                    expected in line
                    for line in log_lines_since("packet_log.log*", baseline)
                ),
                timeout=30,
                interval=2,
                msg=f"for {command} 22F7 packet",
                floor=10.0,
            )
            ctx.check(
                f"{command} emits REM->FAN 22F7 via intent path",
                sent,
                f"expected fragment={expected}",
            )
