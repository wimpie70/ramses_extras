"""Recipe R97: remote.send_command strategy fallback."""

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
    wait_for_schema_populated,
    wait_for_transport_ready,
    ws_send,
)
from ..profile import MIXED_SCHEMA, _build_yaml, get_mixed_kl


class R97RemoteSendCommandStrategyFallback(Recipe):
    id = "R97"
    seq = 970
    title = "remote.send_command strategy fallback"
    tags = ("22F1", "fan", "orcon", "strategy", "remote")

    async def run(self, ctx: RecipeContext) -> None:
        """Verify remote.send_command falls back to strategy for FAN entities.

        When a FAN entity has _scheme set but no matching _commands entry,
        remote.send_command should fall back to set_fan_mode() which uses
        the vendor strategy to translate the mode name.
        """
        ctx.log_section("Recipe 97: remote.send_command strategy fallback")

        ctx.refresh_token()

        # Load schema with FAN having _scheme but NO _commands
        schema = deepcopy(MIXED_SCHEMA)
        schema[FAN] = {
            **schema[FAN],
            "_bound": [REM],
            "_class": "FAN",
            "_scheme": "orcon",
            "remotes": [REM],
            # Deliberately no _commands — strategy fallback should kick in
        }
        schema[REM] = {
            **schema[REM],
            "_bound": FAN,
            "_class": "REM",
            "_faked": True,
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

        def _find_fan_remote() -> dict[str, Any] | None:
            for entity in get_entities(ctx.token):
                entity_id = entity.get("entity_id", "")
                if entity_id.startswith("remote.") and fan_suffix in entity_id:
                    return cast(dict[str, Any], entity)
            return None

        wait_for(
            _find_fan_remote,
            timeout=30,
            interval=2,
            msg="for FAN remote entity",
            floor=10.0,
        )
        fan_remote = _find_fan_remote()
        ctx.check(
            "FAN remote entity exists",
            fan_remote is not None,
            f"FAN={FAN}",
        )
        if fan_remote is None:
            return

        # Check that strategy_modes is exposed in attributes
        attrs_result = docker_exec_python(
            f"""
import json
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
# Use the REST API to get state attributes
import requests
url = "http://localhost:8124/api/states/{fan_remote["entity_id"]}"
headers = {{"Authorization": "Bearer {ctx.token}"}}
r = requests.get(url, headers=headers)
state = r.json()
attrs = state.get("attributes", {{}})
print(json.dumps({{
    "has_strategy_modes": "strategy_modes" in attrs,
    "strategy_scheme": attrs.get("strategy_scheme"),
    "strategy_modes": attrs.get("strategy_modes", []),
}}))
"""
        )
        ctx.check(
            "FAN remote exposes strategy_modes",
            attrs_result.get("has_strategy_modes", False),
            f"result={attrs_result}",
        )
        ctx.check(
            "FAN remote strategy_scheme is orcon",
            attrs_result.get("strategy_scheme") == "orcon",
            f"result={attrs_result}",
        )

        # Get baseline packet log line count
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

        # Send "high" via remote.send_command — not in _commands,
        # should fall back to strategy (Orcon high = 03, payload 000307)
        call_service(
            ctx.token,
            "remote",
            "send_command",
            {
                "entity_id": fan_remote["entity_id"],
                "command": "high",
            },
        )

        # Orcon high: index=00, mode=03, mode_max=07 → 000307
        expected = f"{REM} {FAN} --:------ 22F1 003 000307"

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
            return bool(result.get("found", False))

        wait_for(
            _native_packet_sent,
            timeout=15,
            interval=2,
            msg="for strategy fallback 22F1 packet",
            floor=5.0,
        )
        ctx.check(
            "remote.send_command('high') sent Orcon 000307 via strategy",
            _native_packet_sent(),
            f"expected={expected}",
        )

        # Also test a Dutch alias
        baseline2 = docker_exec_python(
            """
import json
from pathlib import Path
path = Path("/config/packet_log.log")
print(json.dumps({
    "line_count": len(path.read_text().splitlines()) if path.exists() else 0
}))
"""
        )
        line_count2 = int(baseline2.get("line_count", 0))

        call_service(
            ctx.token,
            "remote",
            "send_command",
            {
                "entity_id": fan_remote["entity_id"],
                "command": "hoog",
            },
        )

        # Orcon hoog (Dutch for high) = same as high: 000307
        expected_hoog = f"{REM} {FAN} --:------ 22F1 003 000307"

        def _hoog_packet_sent() -> bool:
            result = docker_exec_python(
                f"""
import json
from pathlib import Path
path = Path("/config/packet_log.log")
lines = path.read_text().splitlines() if path.exists() else []
new_lines = lines[{line_count2}:]
print(json.dumps({{"found": any({expected_hoog!r} in line for line in new_lines)}}))
"""
            )
            return bool(result.get("found", False))

        wait_for(
            _hoog_packet_sent,
            timeout=15,
            interval=2,
            msg="for Dutch alias 'hoog' packet",
            floor=5.0,
        )
        ctx.check(
            "remote.send_command('hoog') sent Orcon 000307 via alias",
            _hoog_packet_sent(),
            f"expected={expected_hoog}",
        )
