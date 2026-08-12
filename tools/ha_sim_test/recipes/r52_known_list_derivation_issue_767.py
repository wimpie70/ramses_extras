"""Recipe R52: known_list derivation from schema (_derive_known_list_from_schema).

Verifies that ``RamsesCoordinator._derive_known_list_from_schema`` correctly:
- Extracts all device IDs from the schema topology (CTL, zones, DHW, FAN, REMs)
- Maps _-prefixed traits to native names (_class→class, _alias→alias, etc.)
- Excludes _skipped devices
- Includes _disabled devices (so ramses_rf doesn't reject their packets)
- Excludes foreign-owner devices (different _owner than root _owner)

Phase 4: user_overrides and schema_is_ssot parameters have been removed.
The schema is the sole source of truth — traits live directly in the schema.

This is a structural test that runs inside the ha-sim container.

See: https://github.com/ramses-rf/ramses_cc/issues/767
"""

from __future__ import annotations

from ..base import Recipe, RecipeContext
from ..const import CTL, DHW, FAN, REM, TRV
from ..helpers import docker_exec_python


class R52KnownListDerivationIssue767(Recipe):
    id = "R52"
    seq = 520
    title = "known_list derivation from schema (issue 767)"
    tags = ("structural",)

    async def run(self, ctx: RecipeContext) -> None:
        ctx.log_section("Recipe 52: known_list derivation (issue 767)")

        code = f"""
import json

# Schema with various trait combinations and topology
# Phase 4: traits live directly in the schema (no user_overrides)
test_schema = {{
    "{CTL}": {{
        "zones": {{
            "03": {{
                "sensor": "01:150003",
                "actuators": ["{TRV}"],
            }},
        }},
        "stored_hotwater": {{"sensor": "{DHW}"}},
        "_class": "CTL",
        "_alias": "Main Controller",
        "_owner": "home",
    }},
    "{TRV}": {{
        "_class": "TRV",
        "_name": "Lounge TRV",
        "_alias": "Override Name",
        "_disabled": True,
    }},
    "{DHW}": {{
        "_class": "DHW",
        "_faked": True,
    }},
    "{FAN}": {{
        "remotes": ["{REM}"],
        "_class": "FAN",
        "_bound": "{REM}",
        "_scheme": "itho",
    }},
    "{REM}": {{
        "_class": "REM",
    }},
    # _skipped device — should be excluded from known_list
    "04:150099": {{
        "_class": "TRV",
        "_skipped": True,
    }},
    # Foreign owner device — should be excluded
    "04:150088": {{
        "_class": "TRV",
        "_owner": "neighbour",
    }},
    "_owner": "home",
    "orphans_heat": [],
    "orphans_hvac": [],
}}

try:
    from custom_components.ramses_cc.coordinator import RamsesCoordinator

    # Phase 4: _derive_known_list_from_schema takes only schema (no overrides)
    kl = RamsesCoordinator._derive_known_list_from_schema(dict(test_schema))

    def has(kl, dev_id):
        return dev_id in kl

    def get_traits(kl, dev_id):
        return kl.get(dev_id, {{}})

    print(json.dumps({{
        "ok": True,
        "kl_keys": sorted(kl.keys()),
        "has_ctl": has(kl, "{CTL}"),
        "ctl_class": get_traits(kl, "{CTL}").get("class", ""),
        "ctl_alias": get_traits(kl, "{CTL}").get("alias", ""),
        "has_trv": has(kl, "{TRV}"),
        "trv_class": get_traits(kl, "{TRV}").get("class", ""),
        "trv_alias": get_traits(kl, "{TRV}").get("alias", ""),
        "trv_disabled": has(kl, "{TRV}"),  # disabled = included
        "has_dhw": has(kl, "{DHW}"),
        "dhw_faked": get_traits(kl, "{DHW}").get("faked"),
        "has_fan": has(kl, "{FAN}"),
        "fan_class": get_traits(kl, "{FAN}").get("class", ""),
        "fan_bound": get_traits(kl, "{FAN}").get("bound", ""),
        "fan_scheme": get_traits(kl, "{FAN}").get("scheme", ""),
        "has_rem": has(kl, "{REM}"),
        "rem_class": get_traits(kl, "{REM}").get("class", ""),
        "has_skipped": has(kl, "04:150099"),
        "has_foreign": has(kl, "04:150088"),
        "has_sensor_01_150003": has(kl, "01:150003"),
    }}))
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
                "_derive_known_list_from_schema runs without error",
                False,
                result.get("error", "unknown"),
            )
            return

        ctx.check("_derive_known_list_from_schema runs without error", True, "")

        # 1. CTL is in known_list with class and alias
        ctx.check(
            "CTL in known_list",
            result.get("has_ctl") is True,
            "CTL missing",
        )
        ctx.check(
            "CTL class derived from _class",
            result.get("ctl_class") == "CTL",
            f"class={result.get('ctl_class')}",
        )
        ctx.check(
            "CTL alias derived from _alias",
            result.get("ctl_alias") == "Main Controller",
            f"alias={result.get('ctl_alias')}",
        )

        # 2. TRV is included even though _disabled (so ramses_rf doesn't reject)
        ctx.check(
            "TRV included despite _disabled",
            result.get("trv_disabled") is True,
            "TRV missing (should be included even when disabled)",
        )
        ctx.check(
            "TRV class derived from _class",
            result.get("trv_class") == "TRV",
            f"class={result.get('trv_class')}",
        )

        # 3. TRV alias from schema _alias (Phase 4: no user overrides)
        ctx.check(
            "TRV alias from schema _alias",
            result.get("trv_alias") == "Override Name",
            f"alias={result.get('trv_alias')}",
        )

        # 4. DHW with _faked=True
        ctx.check(
            "DHW in known_list",
            result.get("has_dhw") is True,
            "DHW missing",
        )
        ctx.check(
            "DHW faked derived from _faked",
            result.get("dhw_faked") is True,
            f"faked={result.get('dhw_faked')}",
        )

        # 5. FAN with bound and scheme
        ctx.check(
            "FAN in known_list",
            result.get("has_fan") is True,
            "FAN missing",
        )
        ctx.check(
            "FAN class derived from _class",
            result.get("fan_class") == "FAN",
            f"class={result.get('fan_class')}",
        )
        ctx.check(
            "FAN bound derived from _bound",
            result.get("fan_bound") == REM,
            f"bound={result.get('fan_bound')}",
        )
        ctx.check(
            "FAN scheme derived from _scheme",
            result.get("fan_scheme") == "itho",
            f"scheme={result.get('fan_scheme')}",
        )

        # 6. REM (from FAN's remotes list)
        ctx.check(
            "REM in known_list (from FAN remotes)",
            result.get("has_rem") is True,
            "REM missing",
        )
        ctx.check(
            "REM class derived from _class",
            result.get("rem_class") == "REM",
            f"class={result.get('rem_class')}",
        )

        # 7. Zone sensor (01:150003) extracted from zone topology
        ctx.check(
            "zone sensor 01:150003 in known_list",
            result.get("has_sensor_01_150003") is True,
            "zone sensor missing",
        )

        # 8. _skipped device excluded
        ctx.check(
            "_skipped device excluded from known_list",
            result.get("has_skipped") is False,
            "skipped device found in known_list",
        )

        # 9. Foreign owner device excluded
        ctx.check(
            "foreign-owner device excluded from known_list",
            result.get("has_foreign") is False,
            "foreign device found in known_list",
        )
