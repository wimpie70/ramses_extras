"""Recipe R96: non-faked 2411 requester is classified as DIS."""

from __future__ import annotations

from copy import deepcopy

import yaml

from ..base import Recipe, RecipeContext
from ..const import FAN
from ..helpers import (
    call_service,
    get_schema_retry,
    load_profile_yaml,
    wait_for,
    wait_for_transport_ready,
    ws_send,
)
from ..profile import MIXED_SCHEMA, get_mixed_kl

PHYSICAL_DISPLAY = "37:169161"
FAKED_REMOTE = "37:169162"


def _profile_yaml() -> str:
    """Build a profile containing physical and faked REM candidates."""
    known_list = get_mixed_kl()
    known_list[PHYSICAL_DISPLAY] = {"class": "REM"}
    known_list[FAKED_REMOTE] = {"class": "REM", "faked": True}

    schema = deepcopy(MIXED_SCHEMA)
    schema[FAN] = {
        **schema[FAN],
        "remotes": [PHYSICAL_DISPLAY, FAKED_REMOTE],
    }
    schema[PHYSICAL_DISPLAY] = {
        "_bound": FAN,
        "_class": "REM",
    }
    schema[FAKED_REMOTE] = {
        "_bound": FAN,
        "_class": "REM",
        "_faked": True,
    }
    return yaml.dump(
        {
            "known_list": known_list,
            "_enforce_known_list": {"enabled": True},
            "_schema": schema,
        },
        default_flow_style=False,
        sort_keys=False,
    )


def _inject_2411(ctx: RecipeContext, source_id: str) -> None:
    """Inject a directed 2411 parameter request to the FAN."""
    call_service(
        ctx.token,
        "ramses_extras",
        "device_simulator_inject_message",
        {
            "source_id": source_id,
            "dst": FAN,
            "code": "2411",
            "payload": "000031",
            "verb": "RQ",
        },
    )


class R96NonFaked2411DisplayDetection(Recipe):
    id = "R96"
    seq = 960
    title = "Non-faked 2411 requester is classified as DIS"
    tags = ("2411", "dis", "discovery", "rem")

    async def run(self, ctx: RecipeContext) -> None:
        """Verify physical DIS detection without reclassifying faked REMs."""
        ctx.log_section("Recipe 96: non-faked 2411 display detection")

        await load_profile_yaml(ctx.token, _profile_yaml(), speed=0.01)
        ctx.wait_for_ramses_cc_reload(msg="for DIS/REM profile reload")
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

        wait_for(
            lambda: (
                PHYSICAL_DISPLAY in get_schema_retry()
                and FAKED_REMOTE in get_schema_retry()
            ),
            timeout=20,
            interval=2,
            msg="for DIS/REM candidates in schema",
            floor=5.0,
        )

        _inject_2411(ctx, PHYSICAL_DISPLAY)
        detected = wait_for(
            lambda: get_schema_retry().get(PHYSICAL_DISPLAY, {}).get("_class") == "DIS",
            timeout=20,
            interval=2,
            msg="for physical REM to be classified as DIS",
            floor=5.0,
        )
        ctx.check(
            "Non-faked REM requesting 2411 is classified as DIS",
            detected,
            f"entry={get_schema_retry().get(PHYSICAL_DISPLAY)}",
        )

        for _ in range(3):
            _inject_2411(ctx, FAKED_REMOTE)
        ctx.wait(5, "for faked REM requests to be evaluated", floor=3.0)

        faked_entry = get_schema_retry().get(FAKED_REMOTE, {})
        ctx.check(
            "Faked REM requesting 2411 remains REM",
            faked_entry.get("_class") == "REM",
            f"entry={faked_entry}",
        )
