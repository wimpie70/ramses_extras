"""Recipe R52: known_list derivation from schema (_derive_known_list_from_schema).

Verifies that ``RamsesCoordinator._derive_known_list_from_schema`` correctly:
- Extracts all device IDs from the schema topology (CTL, zones, DHW, FAN, REMs)
- Maps _-prefixed traits to native names (_class→class, _alias→alias, etc.)
- Excludes _skipped devices
- Includes _disabled devices (so ramses_rf doesn't reject their packets)
- Excludes foreign-owner devices (different _owner than root _owner)
- Applies user_overrides on top of derived traits
- In SSOT mode, drops known_list-only devices not in schema

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

    async def run(self, ctx: RecipeContext) -> None:
        ctx.log_section("Recipe 52: known_list derivation (issue 767)")

        code = f"""
import json

# Schema with various trait combinations and topology
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

# User overrides: add alias for TRV, add a known_list-only device
user_overrides = {{
    "{TRV}": {{"alias": "Override Name"}},
    "07:150099": {{"class": "DHW"}},  # not in schema
}}

try:
    from custom_components.ramses_cc.coordinator import RamsesCoordinator

    # Test 1: legacy mode (schema_is_ssot=False)
    kl_legacy = RamsesCoordinator._derive_known_list_from_schema(
        dict(test_schema),
        user_overrides=user_overrides,
        schema_is_ssot=False,
    )

    # Test 2: SSOT mode (schema_is_ssot=True)
    kl_ssot = RamsesCoordinator._derive_known_list_from_schema(
        dict(test_schema),
        user_overrides=user_overrides,
        schema_is_ssot=True,
    )

    def has(kl, dev_id):
        return dev_id in kl

    def get_traits(kl, dev_id):
        return kl.get(dev_id, {{}})

    print(json.dumps({{
        "ok": True,
        "legacy_keys": sorted(kl_legacy.keys()),
        "ssot_keys": sorted(kl_ssot.keys()),
        "legacy_has_ctl": has(kl_legacy, "{CTL}"),
        "legacy_ctl_class": get_traits(kl_legacy, "{CTL}").get("class", ""),
        "legacy_ctl_alias": get_traits(kl_legacy, "{CTL}").get("alias", ""),
        "legacy_has_trv": has(kl_legacy, "{TRV}"),
        "legacy_trv_class": get_traits(kl_legacy, "{TRV}").get("class", ""),
        "legacy_trv_alias": get_traits(kl_legacy, "{TRV}").get("alias", ""),
        "legacy_trv_disabled": has(kl_legacy, "{TRV}"),  # disabled = included
        "legacy_has_dhw": has(kl_legacy, "{DHW}"),
        "legacy_dhw_faked": get_traits(kl_legacy, "{DHW}").get("faked"),
        "legacy_has_fan": has(kl_legacy, "{FAN}"),
        "legacy_fan_class": get_traits(kl_legacy, "{FAN}").get("class", ""),
        "legacy_fan_bound": get_traits(kl_legacy, "{FAN}").get("bound", ""),
        "legacy_fan_scheme": get_traits(kl_legacy, "{FAN}").get("scheme", ""),
        "legacy_has_rem": has(kl_legacy, "{REM}"),
        "legacy_rem_class": get_traits(kl_legacy, "{REM}").get("class", ""),
        "legacy_has_skipped": has(kl_legacy, "04:150099"),
        "legacy_has_foreign": has(kl_legacy, "04:150088"),
        "legacy_has_override_only": has(kl_legacy, "07:150099"),
        "ssot_has_override_only": has(kl_ssot, "07:150099"),
        "legacy_has_sensor_01_150003": has(kl_legacy, "01:150003"),
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
            result.get("legacy_has_ctl") is True,
            "CTL missing",
        )
        ctx.check(
            "CTL class derived from _class",
            result.get("legacy_ctl_class") == "CTL",
            f"class={result.get('legacy_ctl_class')}",
        )
        ctx.check(
            "CTL alias derived from _alias",
            result.get("legacy_ctl_alias") == "Main Controller",
            f"alias={result.get('legacy_ctl_alias')}",
        )

        # 2. TRV is included even though _disabled (so ramses_rf doesn't reject)
        ctx.check(
            "TRV included despite _disabled",
            result.get("legacy_trv_disabled") is True,
            "TRV missing (should be included even when disabled)",
        )
        ctx.check(
            "TRV class derived from _class",
            result.get("legacy_trv_class") == "TRV",
            f"class={result.get('legacy_trv_class')}",
        )

        # 3. User override alias wins over schema _name
        ctx.check(
            "TRV alias from user override (not _name)",
            result.get("legacy_trv_alias") == "Override Name",
            f"alias={result.get('legacy_trv_alias')}",
        )

        # 4. DHW with _faked=True
        ctx.check(
            "DHW in known_list",
            result.get("legacy_has_dhw") is True,
            "DHW missing",
        )
        ctx.check(
            "DHW faked derived from _faked",
            result.get("legacy_dhw_faked") is True,
            f"faked={result.get('legacy_dhw_faked')}",
        )

        # 5. FAN with bound and scheme
        ctx.check(
            "FAN in known_list",
            result.get("legacy_has_fan") is True,
            "FAN missing",
        )
        ctx.check(
            "FAN class derived from _class",
            result.get("legacy_fan_class") == "FAN",
            f"class={result.get('legacy_fan_class')}",
        )
        ctx.check(
            "FAN bound derived from _bound",
            result.get("legacy_fan_bound") == REM,
            f"bound={result.get('legacy_fan_bound')}",
        )
        ctx.check(
            "FAN scheme derived from _scheme",
            result.get("legacy_fan_scheme") == "itho",
            f"scheme={result.get('legacy_fan_scheme')}",
        )

        # 6. REM (from FAN's remotes list)
        ctx.check(
            "REM in known_list (from FAN remotes)",
            result.get("legacy_has_rem") is True,
            "REM missing",
        )
        ctx.check(
            "REM class derived from _class",
            result.get("legacy_rem_class") == "REM",
            f"class={result.get('legacy_rem_class')}",
        )

        # 7. Zone sensor (01:150003) extracted from zone topology
        ctx.check(
            "zone sensor 01:150003 in known_list",
            result.get("legacy_has_sensor_01_150003") is True,
            "zone sensor missing",
        )

        # 8. _skipped device excluded
        ctx.check(
            "_skipped device excluded from known_list",
            result.get("legacy_has_skipped") is False,
            "skipped device found in known_list",
        )

        # 9. Foreign owner device excluded
        ctx.check(
            "foreign-owner device excluded from known_list",
            result.get("legacy_has_foreign") is False,
            "foreign device found in known_list",
        )

        # 10. Legacy mode: known_list-only device kept
        ctx.check(
            "legacy mode: known_list-only device kept",
            result.get("legacy_has_override_only") is True,
            "override-only device missing in legacy mode",
        )

        # 11. SSOT mode: known_list-only device dropped
        ctx.check(
            "SSOT mode: known_list-only device dropped",
            result.get("ssot_has_override_only") is False,
            "override-only device found in SSOT mode (should be dropped)",
        )
