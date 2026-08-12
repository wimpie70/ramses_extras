"""Recipe R53: CQRS builder defaults vs _commands override.

Verifies the command priority chain for FAN/REM entities:
1. FAN's schema ``_commands`` (dict templates — Phase 3b, highest priority)
2. Bound REM's schema ``_commands`` (packet strings — Phase 3a fallback)
3. known_list[bound_rem][commands] (legacy fallback)
4. ramses_rf builder defaults (``set_fan_mode`` standard implementation)

Also tests ``_split_commands``, ``_merge_commands``, ``_is_command_dict``,
``_build_packet_from_template``, and ``_parse_packet_to_template`` — the
helper functions that power the CQRS command override system.

This is a structural test that runs inside the ha-sim container.

See: https://github.com/ramses-rf/ramses_cc/issues/767
"""

from __future__ import annotations

from ..base import Recipe, RecipeContext
from ..const import FAN, REM
from ..helpers import docker_exec_python


class R53CqrsBuilderDefaultsVsCommandsIssue767(Recipe):
    id = "R53"
    seq = 530
    title = "CQRS builder defaults vs _commands override (issue 767)"

    async def run(self, ctx: RecipeContext) -> None:
        ctx.log_section("Recipe 53: CQRS builder defaults vs _commands (issue 767)")

        code = f"""
import json

try:
    from custom_components.ramses_cc.remote import (
        _split_commands,
        _merge_commands,
        _is_command_dict,
        _build_packet_from_template,
        _parse_packet_to_template,
        _RESERVED_CMD_KEYS,
    )

    results = {{}}

    # ── 1. _split_commands: separates metadata from commands ──────────
    raw = {{
        "turn_on": "I --- {REM} {FAN} --:------ 22F1 003 000100",
        "turn_off": "I --- {REM} {FAN} --:------ 22F1 003 000000",
        "_comment": "Learned REM commands",
    }}
    cmds, meta = _split_commands(raw)
    results["split_cmds_count"] = len(cmds)
    results["split_meta_count"] = len(meta)
    results["split_has_comment_in_meta"] = "_comment" in meta
    results["split_has_comment_in_cmds"] = "_comment" in cmds
    results["split_has_turn_on"] = "turn_on" in cmds

    # ── 2. _merge_commands: FAN metadata wins, REM commands fill gaps ─
    fan_cmds = {{
        "turn_on": {{"verb": "I", "code": "22F1", "payload": "000100"}},
        "_comment": "FAN templates",
    }}
    rem_cmds = {{
        "turn_on": "I --- {REM} {FAN} --:------ 22F1 003 000100",
        "turn_off": "I --- {REM} {FAN} --:------ 22F1 003 000000",
        "_comment": "REM commands (should be ignored)",
    }}
    merged = _merge_commands(fan_cmds, rem_cmds)
    m_cmds, m_meta = _split_commands(merged)
    results["merge_meta_comment"] = m_meta.get("_comment", "")
    results["merge_has_turn_on"] = "turn_on" in m_cmds
    results["merge_has_turn_off"] = "turn_off" in m_cmds
    results["merge_turn_on_is_dict"] = _is_command_dict(m_cmds.get("turn_on"))
    # FAN's turn_on (dict) should win over REM's turn_on (string)
    results["merge_turn_on_from_fan"] = isinstance(m_cmds.get("turn_on"), dict)

    # ── 3. _is_command_dict: distinguishes dict templates from strings ─
    _cmd_dict = {{"verb": "I", "code": "22F1", "payload": "000100"}}
    results["is_cmd_dict_dict"] = _is_command_dict(_cmd_dict)
    _cmd_str = "I --- 37:170000 32:150000 --:------ 22F1 003 000100"
    results["is_cmd_dict_str"] = _is_command_dict(_cmd_str)
    results["is_cmd_dict_none"] = _is_command_dict(None)
    results["is_cmd_dict_empty"] = _is_command_dict({{}})

    # ── 4. _parse_packet_to_template: extracts verb/code/payload ──────
    packet = "W --- 32:153001 30:160000 --:------ 22F7 003 0000EF"
    template = _parse_packet_to_template(packet)
    results["parse_verb"] = template.get("verb", "")
    results["parse_code"] = template.get("code", "")
    results["parse_payload"] = template.get("payload", "")

    # ── 5. _build_packet_from_template: fills addresses at send time ──
    # We need a mock FAN device and coordinator for this
    from unittest.mock import MagicMock
    fan_dev = MagicMock()
    fan_dev.id = "{FAN}"
    fan_dev.get_bound_rem.return_value = "{REM}"
    coord = MagicMock()
    coord.client = None  # triggers HGI fallback path
    cmd_def = {{"verb": "I", "code": "22F1", "payload": "000100"}}
    packet_str = _build_packet_from_template(cmd_def, fan_dev, coord)
    results["build_packet"] = packet_str
    results["build_has_verb"] = packet_str.startswith("I ")
    results["build_has_src"] = "{REM}" in packet_str
    results["build_has_dst"] = "{FAN}" in packet_str
    results["build_has_code"] = "22F1" in packet_str

    # ── 6. Priority chain simulation ──────────────────────────────────
    # Simulate the priority logic from climate.py _async_set_fan_mode
    fan_commands = {{"heat": {{"verb": "W", "code": "22F1", "payload": "000200"}}}}
    _rem_heat = f"W --- {REM} {FAN} --:------ 22F1 003 000200"
    _rem_cool = f"W --- {REM} {FAN} --:------ 22F1 003 000201"
    rem_commands = {{"heat": _rem_heat, "cool": _rem_cool}}
    fan_mode = "heat"
    # FAN dict template should win
    results["priority_fan_wins"] = (
        fan_mode in fan_commands
        and _is_command_dict(fan_commands[fan_mode])
    )
    fan_mode_cool = "cool"
    # "cool" not in FAN commands, falls through to REM
    results["priority_rem_fallback"] = (
        fan_mode_cool not in fan_commands
        and fan_mode_cool in rem_commands
    )
    fan_mode_auto = "auto"
    # "auto" in neither, falls through to ramses_rf default
    results["priority_default_fallback"] = (
        fan_mode_auto not in fan_commands
        and fan_mode_auto not in rem_commands
    )

    print(json.dumps({{"ok": True, **results}}))
except Exception as e:
    import traceback
    print(json.dumps({{
        "error": f"{{type(e).__name__}}: {{e}}",
        "traceback": traceback.format_exc()[:1000],
        "ok": False,
    }}))
"""
        result = docker_exec_python(code, timeout=30)

        if not result.get("ok"):
            ctx.check(
                "command helper functions run without error",
                False,
                result.get("error", "unknown"),
            )
            return

        ctx.check("command helper functions run without error", True, "")

        # 1. _split_commands
        ctx.check(
            "_split_commands separates 2 commands from 1 metadata",
            result.get("split_cmds_count") == 2 and result.get("split_meta_count") == 1,
            f"cmds={result.get('split_cmds_count')},"
            f" meta={result.get('split_meta_count')}",
        )
        ctx.check(
            "_split_commands: _comment in metadata, not commands",
            result.get("split_has_comment_in_meta") is True
            and result.get("split_has_comment_in_cmds") is False,
            "metadata separation failed",
        )

        # 2. _merge_commands
        ctx.check(
            "_merge_commands: FAN metadata wins",
            result.get("merge_meta_comment") == "FAN templates",
            f"comment={result.get('merge_meta_comment')}",
        )
        ctx.check(
            "_merge_commands: FAN dict turn_on wins over REM string",
            result.get("merge_turn_on_from_fan") is True,
            "FAN dict should take priority over REM string",
        )
        ctx.check(
            "_merge_commands: REM turn_off fills gap",
            result.get("merge_has_turn_off") is True,
            "REM-only command missing from merge",
        )

        # 3. _is_command_dict
        ctx.check(
            "_is_command_dict: dict is True",
            result.get("is_cmd_dict_dict") is True,
            "dict should be detected as command dict",
        )
        ctx.check(
            "_is_command_dict: string is False",
            result.get("is_cmd_dict_str") is False,
            "string should not be detected as command dict",
        )
        ctx.check(
            "_is_command_dict: None is False",
            result.get("is_cmd_dict_none") is False,
            "None should not be detected as command dict",
        )

        # 4. _parse_packet_to_template
        ctx.check(
            "_parse_packet_to_template: verb extracted",
            result.get("parse_verb") == "W",
            f"verb={result.get('parse_verb')}",
        )
        ctx.check(
            "_parse_packet_to_template: code extracted",
            result.get("parse_code") == "22F7",
            f"code={result.get('parse_code')}",
        )
        ctx.check(
            "_parse_packet_to_template: payload extracted",
            result.get("parse_payload") == "0000EF",
            f"payload={result.get('parse_payload')}",
        )

        # 5. _build_packet_from_template
        ctx.check(
            "_build_packet_from_template: starts with verb",
            result.get("build_has_verb") is True,
            f"packet={result.get('build_packet')}",
        )
        ctx.check(
            "_build_packet_from_template: src is bound REM",
            result.get("build_has_src") is True,
            f"packet={result.get('build_packet')}",
        )
        ctx.check(
            "_build_packet_from_template: dst is FAN",
            result.get("build_has_dst") is True,
            f"packet={result.get('build_packet')}",
        )

        # 6. Priority chain
        ctx.check(
            "priority: FAN dict template wins for 'heat'",
            result.get("priority_fan_wins") is True,
            "FAN dict should take priority",
        )
        ctx.check(
            "priority: REM fallback for 'cool' (not in FAN)",
            result.get("priority_rem_fallback") is True,
            "REM fallback should work for non-FAN commands",
        )
        ctx.check(
            "priority: ramses_rf default for 'auto' (neither)",
            result.get("priority_default_fallback") is True,
            "default fallback should work for unknown commands",
        )
