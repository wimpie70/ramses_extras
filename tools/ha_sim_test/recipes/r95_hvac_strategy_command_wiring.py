"""Recipe R95: HVAC strategy command wiring."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, cast

from ..base import Recipe, RecipeContext
from ..const import CTL, FAN, REM
from ..helpers import (
    call_service,
    docker_exec_python,
    get_entities,
    load_profile_yaml,
    wait_for,
    wait_for_ramses_extras_ready,
    wait_for_schema_populated,
    wait_for_transport_ready,
    ws_send,
)
from ..profile import MIXED_SCHEMA, _build_yaml, get_mixed_kl


class R95HvacStrategyCommandWiring(Recipe):
    id = "R95"
    seq = 950
    title = "HVAC strategy command wiring"
    tags = ("22F1", "fan", "orcon", "strategy")

    async def run(self, ctx: RecipeContext) -> None:
        """Verify alias encoding and native fan-mode packet transmission."""
        ctx.log_section("Recipe 95: HVAC strategy command wiring")

        alias_result = docker_exec_python(
            """
import json
from ramses_rf.address import Address
from ramses_rf.commands.builders import build_dto
from ramses_rf.commands.core import Command
from ramses_rf.enums import Action
from ramses_rf.strategies import best_hvac_strategy

strategy = best_hvac_strategy("32:150000", scheme="orcon")
dto = build_dto(
    Command(
        src=Address("37:170000"),
        dst=Address("32:150000"),
        action=Action.SET_FAN_MODE,
        data={"fan_mode": "laag", "strategy": strategy},
    )
)
print(json.dumps({"payload": dto.payload}))
"""
        )
        ctx.check(
            "Orcon Dutch alias 'laag' builds 000107",
            alias_result.get("payload") == "000107",
            f"result={alias_result}",
        )

        ctx.refresh_token()
        wait_for_ramses_extras_ready(timeout=90, msg="for ramses_extras")

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

        fan_suffix = FAN.replace(":", "_")

        def _find_fan_climate() -> dict[str, Any] | None:
            for entity in get_entities(ctx.token):
                entity_id = entity.get("entity_id", "")
                if entity_id.startswith("climate.") and fan_suffix in entity_id:
                    return cast(dict[str, Any], entity)
            return None

        wait_for(
            _find_fan_climate,
            timeout=30,
            interval=2,
            msg="for FAN climate entity",
            floor=10.0,
        )
        fan_climate = _find_fan_climate()
        ctx.check(
            "FAN climate entity exists",
            fan_climate is not None,
            f"FAN={FAN}",
        )
        if fan_climate is None:
            return

        baseline = docker_exec_python(
            """
import json
from pathlib import Path
path = Path("/config/packet_log.log")
print(json.dumps({
    "line_count": len(path.read_text().splitlines()) if path.exists() else 0
}))
"""
        )
        line_count = int(baseline.get("line_count", 0))

        call_service(
            ctx.token,
            "climate",
            "set_fan_mode",
            {
                "entity_id": fan_climate["entity_id"],
                "fan_mode": "low",
            },
        )

        expected = f"{REM} {FAN} --:------ 22F1 003 000107"

        def _native_packet_sent() -> bool:
            result = docker_exec_python(
                f"""
import json
from pathlib import Path
path = Path("/config/packet_log.log")
lines = path.read_text().splitlines() if path.exists() else []
new_lines = lines[{line_count}:]
print(json.dumps({{"found": any({expected!r} in line for line in new_lines)}}))
"""
            )
            return result.get("found") is True

        sent = wait_for(
            _native_packet_sent,
            timeout=20,
            interval=2,
            msg="for native 22F1 command",
            floor=5.0,
        )
        ctx.check(
            "Native set_fan_mode emits Orcon 22F1 payload 000107",
            sent,
            f"expected packet fragment={expected}",
        )
