"""Recipe R146: Orcon 22F3 boost dialects — structural build+match (issue 1332).

Issue: an Orcon VMN-15LF01 remote sends timed boosts in a different
dialect than the classic table — ``00020F03040000`` (flags 0x02, tail
04 00 00) instead of ``00120F03040404`` (flags 0x12, tail 04 04 04).
Such frames parsed but could not be attributed to a canonical command
name, and the send path could only emit the 0x12 dialect.

Fix (ramses_rf): the 22F3 boost table is generated structurally from
speed/duration building blocks, and ``OrconStrategy`` gains
``boost_command_name()`` (inbound structural matcher — both dialects,
arbitrary durations → canonical ``<speed>_<minutes>``) and
``boost_timer_payload()`` (send-side builder for either dialect).

This recipe verifies end-to-end:

  1. ``remote.send_command("high_15")`` on an Orcon FAN emits the
     canonical ``I|22F3|00120F03040404`` — the generated builtin table
     resolves through the strategy fallback
  2. The Dutch boost alias ``hoog_15`` resolves to the same payload
  3. The loaded strategy attributes BOTH dialects to ``high_15``
     (canonical 0x12 and the observed 0x02 variant), and rejects
     malformed payloads — exercised inside the container against the
     bind-mounted ramses_rf
  4. An injected ``I|22F3|00020F03040000`` from the bound REM is
     ingested without errors (the variant dialect reaches the parser)

See: https://github.com/ramses-rf/ramses_cc/issues/1332
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, cast

from ..base import Recipe, RecipeContext
from ..const import CTL, FAN, REM
from ..helpers import (
    call_service,
    container_log_timestamp,
    docker_exec_python,
    get_entities,
    load_profile_yaml,
    log_lines_since,
    wait_for,
    wait_for_schema_populated,
    wait_for_transport_ready,
    ws_send,
)
from ..profile import MIXED_SCHEMA, _build_yaml, get_mixed_kl

_CANONICAL_PAYLOAD = "00120F03040404"  # flags 0x12, high, 15 min
_VARIANT_PAYLOAD = "00020F03040000"  # flags 0x02, high, 15 min (VMN-15LF01)


class R146OrconBoostDialectIssue1332(Recipe):
    id = "R146"
    seq = 1460
    title = "Orcon 22F3 boost dialects — structural build+match (issue 1332)"
    tags = ("22F3", "fan", "orcon", "strategy", "boost", "issue1332")

    async def run(self, ctx: RecipeContext) -> None:
        ctx.log_section("Recipe 146: Orcon 22F3 boost dialects (issue 1332)")

        ctx.refresh_token()

        # Orcon FAN with bound REM, no _commands — send path resolves
        # through the strategy builtin_commands table.
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

        def _send_and_expect(command: str, expected: str) -> bool:
            """send_command + look for the expected packet fragment."""
            baseline = container_log_timestamp()
            try:
                call_service(
                    ctx.token,
                    "remote",
                    "send_command",
                    {
                        "entity_id": fan_remote["entity_id"],
                        "command": command,
                    },
                )
            except RuntimeError as err:
                print(f"    send_command({command!r}) failed: {err}")
                return False
            wait_for(
                lambda: any(
                    expected in line
                    for line in log_lines_since("packet_log.log*", baseline)
                ),
                timeout=30,
                interval=2,
                msg=f"for 22F3 packet after send_command({command!r})",
                floor=10.0,
            )
            return any(
                expected in line
                for line in log_lines_since("packet_log.log*", baseline)
            )

        # ── 1. Canonical boost via builtin_commands table ───────────
        expected = f"{REM} {FAN} --:------ 22F3 007 {_CANONICAL_PAYLOAD}"
        ctx.check(
            "send_command('high_15') emits canonical I|22F3|00120F03040404",
            _send_and_expect("high_15", expected),
            f"expected={expected}",
        )

        # ── 2. Dutch boost alias resolves to the same payload ───────
        ctx.check(
            "send_command('hoog_15') alias emits I|22F3|00120F03040404",
            _send_and_expect("hoog_15", expected),
            f"expected={expected}",
        )

        # ── 3. Structural matcher attributes both dialects ──────────
        #    Runs inside the container against the bind-mounted
        #    ramses_rf — proves the deployed build carries the matcher
        #    and attributes the observed 0x02 variant correctly.
        match_result = docker_exec_python(
            """
import json, sys
sys.path.insert(0, "/config/ramses_rf/src")  # bind-mounted worktree first
from ramses_rf.strategies.orcon import OrconStrategy
s = OrconStrategy()
print(json.dumps({
    "canonical": s.boost_command_name("22F3", "00120F03040404"),
    "variant": s.boost_command_name("22F3", "00020F03040000"),
    "arbitrary": s.boost_command_name("22F3", "00120A02040404"),
    "bad_speed": s.boost_command_name("22F3", "00120F09040404"),
}))
"""
        )
        ctx.check(
            "strategy attributes canonical + 0x02-variant to high_15",
            match_result.get("canonical") == "high_15"
            and match_result.get("variant") == "high_15",
            f"result={match_result}",
        )
        ctx.check(
            "matcher: arbitrary duration named, bad speed rejected",
            match_result.get("arbitrary") == "medium_10"
            and match_result.get("bad_speed") is None,
            f"result={match_result}",
        )

        # ── 4. Variant-dialect boost is ingested without errors ─────
        #    The REM is in known_list so the packet passes the device
        #    filter; the log report flags any parser/dispatch errors.
        baseline = container_log_timestamp()
        try:
            call_service(
                ctx.token,
                "ramses_extras",
                "device_simulator_inject_message",
                {
                    "source_id": REM,
                    "dst": FAN,
                    "code": "22F3",
                    "payload": _VARIANT_PAYLOAD,
                    "verb": "I",
                },
            )
        except RuntimeError as err:
            print(f"    inject_message failed: {err}")
        wait_for(
            lambda: any(
                "22F3" in line and _VARIANT_PAYLOAD in line
                for line in log_lines_since("packet_log.log*", baseline)
            ),
            timeout=20,
            interval=2,
            msg="for injected 0x02-dialect 22F3 in packet log",
            floor=5.0,
        )
        seen = any(
            "22F3" in line and _VARIANT_PAYLOAD in line
            for line in log_lines_since("packet_log.log*", baseline)
        )
        ctx.check(
            "injected 0x02-dialect 22F3 ingested (packet log)",
            seen,
            f"expected {REM} -> {FAN} 22F3 {_VARIANT_PAYLOAD}",
        )
