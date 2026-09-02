"""Recipe R96: non-faked 2411 requester is classified as DIS."""

from __future__ import annotations

from copy import deepcopy

import yaml

from ..base import Recipe, RecipeContext
from ..const import FAN
from ..helpers import (
    call_service,
    docker_exec_python,
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
            timeout=30,
            interval=2,
            msg="for DIS/REM candidates in schema",
            floor=10.0,
        )

        def _log_line_count() -> int:
            result = docker_exec_python(
                """
import json
from pathlib import Path
path = Path("/config/home-assistant.log")
print(json.dumps({"count": len(path.read_text().splitlines())}))
"""
            )
            return int(result.get("count", 0))

        def _has_detection_since(line_count: int, device_id: str) -> bool:
            result = docker_exec_python(
                f"""
import json
from pathlib import Path
lines = Path("/config/home-assistant.log").read_text().splitlines()
new_lines = lines[{line_count}:]
found = any(
    {device_id!r} in line
    and "Rule_HVAC_2411_Request_Source_to_DIS" in line
    for line in new_lines
)
print(json.dumps({{"found": found}}))
"""
            )
            return result.get("found") is True

        physical_baseline = _log_line_count()
        _inject_2411(ctx, PHYSICAL_DISPLAY)
        detected = wait_for(
            lambda: _has_detection_since(physical_baseline, PHYSICAL_DISPLAY),
            timeout=30,
            interval=2,
            msg="for physical REM DIS evidence event",
            floor=10.0,
        )
        ctx.check(
            "Non-faked REM requesting 2411 emits DIS evidence",
            detected,
            f"device_id={PHYSICAL_DISPLAY}",
        )

        faked_baseline = _log_line_count()
        for _ in range(3):
            _inject_2411(ctx, FAKED_REMOTE)
        ctx.wait(5, "for faked REM requests to be evaluated", floor=3.0)

        faked_entry = get_schema_retry().get(FAKED_REMOTE, {})
        faked_detected = _has_detection_since(faked_baseline, FAKED_REMOTE)
        ctx.check(
            "Faked REM requesting 2411 remains REM",
            faked_entry.get("_class") == "REM" and not faked_detected,
            f"entry={faked_entry}, detection_event={faked_detected}",
        )
