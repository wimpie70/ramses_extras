"""Recipe R138: fan parameter service delegation (issue 229)."""

from __future__ import annotations

import threading
from copy import deepcopy

from ..base import Recipe, RecipeContext
from ..const import CTL, FAN, REM
from ..helpers import (
    call_service,
    container_log_timestamp,
    load_profile_yaml,
    log_lines_since,
    wait,
    wait_for,
    wait_for_schema_populated,
    wait_for_transport_ready,
    ws_send,
)
from ..profile import MIXED_SCHEMA, _build_yaml, get_mixed_kl


def _fire_and_forget(
    token: str, domain: str, service: str, data: dict
) -> threading.Thread:
    """Call a service without waiting for the response.

    ``set_fan_param``-style services block on the transport's TX echo
    (~80s on stacks where the echo path is missing).  The packet is
    emitted within a second — asserting on the packet log is the real
    verification, so the REST call runs in a daemon thread.
    """
    thread = threading.Thread(
        target=lambda: _call_swallowing_errors(token, domain, service, data),
        daemon=True,
    )
    thread.start()
    return thread


def _call_swallowing_errors(token: str, domain: str, service: str, data: dict) -> None:
    try:
        call_service(token, domain, service, data, timeout=15, retries=1)
    except Exception:  # noqa: BLE001 - fire-and-forget: packet log is the check
        pass


def _packet_count(lines: list[str], fragment: str) -> int:
    return sum(1 for line in lines if fragment in line)


class R138FanParamServiceDelegation(Recipe):
    id = "R138"
    seq = 1380
    title = "Fan parameter service delegation (issue 229)"
    tags = ("2411", "fan", "services", "fan_param")

    async def run(self, ctx: RecipeContext) -> None:
        """Verify extras compat services and ramses_cc services emit 2411."""
        ctx.log_section("Recipe 138: fan parameter service delegation")

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

        w_fragment = f"{REM} {FAN} --:------ 2411 023 000031"
        rq_fragment = f"{REM} {FAN} --:------ 2411 003 0000"

        # --- set_fan_parameter: extras compat alias -> ramses_cc service ---
        baseline = container_log_timestamp()
        _fire_and_forget(
            ctx.token,
            "ramses_extras",
            "set_fan_parameter",
            {"device_id": FAN, "param_id": "31", "value": "5"},
        )
        sent = wait_for(
            lambda: (
                _packet_count(log_lines_since("packet_log.log*", baseline), w_fragment)
                >= 1
            ),
            timeout=30,
            interval=2,
            msg="for 2411 W from extras set_fan_parameter",
            floor=5.0,
        )
        ctx.check(
            "extras set_fan_parameter emits 2411 W (delegates to ramses_cc)",
            sent,
            f"expected fragment={w_fragment}",
        )

        # --- set_fan_param: direct upstream call (what the card uses) ---
        baseline = container_log_timestamp()
        _fire_and_forget(
            ctx.token,
            "ramses_cc",
            "set_fan_param",
            {"device_id": [FAN], "param_id": "31", "value": "6"},
        )
        sent = wait_for(
            lambda: (
                _packet_count(log_lines_since("packet_log.log*", baseline), w_fragment)
                >= 1
            ),
            timeout=30,
            interval=2,
            msg="for 2411 W from ramses_cc set_fan_param",
            floor=5.0,
        )
        ctx.check(
            "ramses_cc set_fan_param emits 2411 W (card calls this directly)",
            sent,
            f"expected fragment={w_fragment}",
        )

        # --- update_fan_params: extras compat alias -> upstream sweep ---
        baseline = container_log_timestamp()
        _fire_and_forget(
            ctx.token, "ramses_extras", "update_fan_params", {"device_id": FAN}
        )
        swept = wait_for(
            lambda: (
                _packet_count(log_lines_since("packet_log.log*", baseline), rq_fragment)
                >= 3
            ),
            timeout=45,
            interval=2,
            msg="for 2411 RQ sweep from extras update_fan_params",
            floor=10.0,
        )
        ctx.check(
            "extras update_fan_params emits 2411 RQ sweep (>=3 params)",
            swept,
            f"expected fragment={rq_fragment}",
        )

        # Let the first sweep finish — upstream dedupes overlapping sweeps
        # per device, so a second call while one runs may be merged away.
        wait(15, "for the first param sweep to complete")

        # --- update_fan_params: direct upstream call ---
        baseline = container_log_timestamp()
        _fire_and_forget(
            ctx.token, "ramses_cc", "update_fan_params", {"device_id": [FAN]}
        )
        swept = wait_for(
            lambda: (
                _packet_count(log_lines_since("packet_log.log*", baseline), rq_fragment)
                >= 3
            ),
            timeout=45,
            interval=2,
            msg="for 2411 RQ sweep from ramses_cc update_fan_params",
            floor=10.0,
        )
        ctx.check(
            "ramses_cc update_fan_params emits 2411 RQ sweep (>=3 params)",
            swept,
            f"expected fragment={rq_fragment}",
        )
