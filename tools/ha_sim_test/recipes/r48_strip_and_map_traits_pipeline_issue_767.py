"""Recipe R48: strip_and_map_traits — schema pre-validation pipeline.

Verifies that ``strip_and_map_traits()`` correctly removes ``_``-prefixed
keys that ramses_rf doesn't need (``_commands``, ``_disabled``, ``_name``,
``_note``, ``_owner``, ``_comment``, ``_skipped``) and maps known ones to
their native names (``_bound``→``bound``, ``_scheme``→``scheme``,
``_alias``→``alias``, ``_faked``→``faked``, ``_class``→``class``).

This function shipped in ramses_rf 0.58.3 but is not yet called by
Gateway/CLI.  This recipe tests it directly inside the ha-sim container.

See: https://github.com/ramses-rf/ramses_cc/issues/767
"""

from __future__ import annotations

from ..base import Recipe, RecipeContext
from ..helpers import docker_exec_python


class R48StripAndMapTraitsPipelineIssue767(Recipe):
    id = "R48"
    seq = 490
    title = "strip_and_map_traits — schema pre-validation pipeline (issue 767)"

    async def run(self, ctx: RecipeContext) -> None:
        ctx.log_section("Recipe 48: strip_and_map_traits pipeline (issue 767)")

        # Run the test inside the container where strip_and_map_traits exists
        code = """
import json

# strip_and_map_traits works per-device trait dict, not on the whole schema.
# It maps _-prefixed keys to native names and strips unknown _ keys.
test_traits = {
    "01:150003": {
        "_class": "THM",
        "_alias": "Lounge Sensor",
        "_faked": True,
        "_bound": "01:150000",
        "_scheme": "itho",
        "_disabled": True,
        "_commands": {"off": {"code": "2309", "payload": "0000FF"}},
        "_name": "Lounge",
        "_note": "test device",
    },
    "04:150003": {
        "_class": "TRV",
        "_disabled": True,
        "_commands": {"off": {"code": "2309", "payload": "0000FF"}},
    },
    "01:150000": {
        "zones": {
            "03": {
                "sensor": "01:150003",
                "actuators": ["04:150003"],
                "_name": "Lounge",
            },
        },
        "stored_hotwater": {"sensor": "07:150000"},
    },
}

try:
    from ramses_rf.schemas import strip_and_map_traits
except ImportError:
    print(json.dumps({"error": "strip_and_map_traits not importable", "ok": False}))
    raise SystemExit

try:
    results = {}
    for dev_id, traits in test_traits.items():
        results[dev_id] = strip_and_map_traits(traits)

    # Check: _-prefixed keys are gone from all results
    def find_underscore_keys(obj, path=""):
        found = []
        if isinstance(obj, dict):
            for k, v in obj.items():
                if isinstance(k, str) and k.startswith("_"):
                    found.append(f"{path}.{k}" if path else k)
                found.extend(find_underscore_keys(v, f"{path}.{k}" if path else k))
        elif isinstance(obj, list):
            for i, v in enumerate(obj):
                found.extend(find_underscore_keys(v, f"{path}[{i}]"))
        return found

    all_underscore = []
    for dev_id, mapped in results.items():
        all_underscore.extend(find_underscore_keys(mapped, dev_id))

    # Check: known traits are mapped to native names
    thm = results.get("01:150003", {})
    trv = results.get("04:150003", {})
    ctl = results.get("01:150000", {})

    # CTL topology should be preserved (zones, DHW) but _name stripped
    zones = ctl.get("zones", {})
    zone_03 = zones.get("03", {})
    dhw = ctl.get("stored_hotwater", {})

    print(json.dumps({
        "ok": True,
        "underscore_keys": all_underscore,
        "thm_class": thm.get("class", ""),
        "thm_alias": thm.get("alias", ""),
        "thm_faked": thm.get("faked"),
        "thm_bound": thm.get("bound", ""),
        "thm_scheme": thm.get("scheme", ""),
        "thm_has_disabled": "disabled" in thm,
        "thm_has_commands": "commands" in thm,
        "thm_has_name": "name" in thm,
        "thm_has_note": "note" in thm,
        "trv_class": trv.get("class", ""),
        "trv_has_disabled": "disabled" in trv,
        "trv_has_commands": "commands" in trv,
        "ctl_has_zones": "03" in zones,
        "ctl_has_dhw": "sensor" in dhw if isinstance(dhw, dict) else False,
        "zone_03_has_name": (
            "name" in zone_03 if isinstance(zone_03, dict) else True
        ),
        "zone_03_has_sensor": (
            zone_03.get("sensor") == "01:150003"
            if isinstance(zone_03, dict) else False
        ),
    }))
except Exception as e:
    print(json.dumps({"error": f"{type(e).__name__}: {e}", "ok": False}))
"""
        result = docker_exec_python(code, timeout=30)

        if not result.get("ok"):
            ctx.check(
                "strip_and_map_traits runs without error",
                False,
                result.get("error", "unknown"),
            )
            return

        ctx.check(
            "strip_and_map_traits runs without error",
            True,
            "",
        )

        # 1. No _-prefixed keys remain in any result
        underscore_keys = result.get("underscore_keys", [])
        ctx.check(
            "no _-prefixed keys remain after strip_and_map_traits",
            len(underscore_keys) == 0,
            f"found _ keys: {underscore_keys[:5]}",
        )

        # 2. Known traits are mapped to native names
        ctx.check(
            "_class mapped to class (THM)",
            result.get("thm_class") == "THM",
            f"thm_class={result.get('thm_class')}",
        )

        ctx.check(
            "_alias mapped to alias",
            result.get("thm_alias") == "Lounge Sensor",
            f"thm_alias={result.get('thm_alias')}",
        )

        ctx.check(
            "_faked mapped to faked",
            result.get("thm_faked") is True,
            f"thm_faked={result.get('thm_faked')}",
        )

        ctx.check(
            "_bound mapped to bound",
            result.get("thm_bound") == "01:150000",
            f"thm_bound={result.get('thm_bound')}",
        )

        ctx.check(
            "_scheme mapped to scheme",
            result.get("thm_scheme") == "itho",
            f"thm_scheme={result.get('thm_scheme')}",
        )

        # 3. Unknown _ keys are stripped (not mapped)
        ctx.check(
            "_disabled stripped (not mapped to disabled)",
            not result.get("thm_has_disabled"),
            "disabled key found in result",
        )

        ctx.check(
            "_commands stripped (not mapped to commands)",
            not result.get("thm_has_commands"),
            "commands key found in result",
        )

        ctx.check(
            "_name stripped from device traits",
            not result.get("thm_has_name"),
            "name key found in device traits",
        )

        ctx.check(
            "_note stripped from device traits",
            not result.get("thm_has_note"),
            "note key found in device traits",
        )

        # 4. TRV: _class mapped, _disabled and _commands stripped
        ctx.check(
            "TRV _class mapped to class",
            result.get("trv_class") == "TRV",
            f"trv_class={result.get('trv_class')}",
        )

        ctx.check(
            "TRV _disabled stripped",
            not result.get("trv_has_disabled"),
            "disabled key found in TRV",
        )

        ctx.check(
            "TRV _commands stripped",
            not result.get("trv_has_commands"),
            "commands key found in TRV",
        )

        # 5. CTL topology preserved (zones, DHW) but zone _name stripped
        ctx.check(
            "CTL zones topology preserved",
            result.get("ctl_has_zones"),
            "zones missing from CTL",
        )

        ctx.check(
            "CTL DHW topology preserved",
            result.get("ctl_has_dhw"),
            "DHW missing from CTL",
        )

        ctx.check(
            "zone _name stripped from nested zone dict",
            not result.get("zone_03_has_name"),
            "name key found in zone 03",
        )

        ctx.check(
            "zone sensor preserved after stripping",
            result.get("zone_03_has_sensor"),
            "sensor missing from zone 03",
        )
