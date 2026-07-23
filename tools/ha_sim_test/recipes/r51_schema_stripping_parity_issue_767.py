"""Recipe R51: Schema stripping parity (config_flow vs gateway).

Verifies that the schema stripping used by config_flow validation
(``strip_traits_for_validation``) produces the same result as what
the gateway actually receives (``_strip_schema_extensions``).  Both
paths go through ``_strip_and_orchestrate``, so they must be identical.

This is a structural test that runs inside the ha-sim container,
calling both functions directly with a known schema and comparing
the output.

See: https://github.com/ramses-rf/ramses_cc/issues/767
"""

from __future__ import annotations

from ..base import Recipe, RecipeContext
from ..const import CTL, DHW, FAN, REM, TRV
from ..helpers import docker_exec_python


class R51SchemaStrippingParityIssue767(Recipe):
    id = "R51"
    seq = 510
    title = "Schema stripping parity: config_flow validation vs gateway (issue 767)"

    async def run(self, ctx: RecipeContext) -> None:
        ctx.log_section("Recipe 51: Schema stripping parity (issue 767)")

        code = f"""
import json

# Test schema with _-prefixed traits that should be stripped/mapped
# before reaching ramses_rf, plus extension keys and topology.
test_schema = {{
    "{CTL}": {{
        "zones": {{
            "03": {{
                "sensor": "01:150003",
                "actuators": ["{TRV}"],
                "_name": "Lounge",
            }},
        }},
        "stored_hotwater": {{"sensor": "{DHW}"}},
        "_class": "CTL",
        "_alias": "Main Controller",
        "_owner": "home",
    }},
    "{TRV}": {{
        "_class": "TRV",
        "_disabled": False,
        "_commands": {{"off": {{"code": "2309", "payload": "0000FF"}}}},
        "_name": "Lounge TRV",
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
        "_commands": {{"turn_on": {{"code": "22F1", "payload": "000100"}}}},
    }},
    "_owner": "home",
    "orphans_heat": [],
    "orphans_hvac": [],
}}

try:
    from custom_components.ramses_cc.schemas import strip_traits_for_validation
    from custom_components.ramses_cc.coordinator import RamsesCoordinator

    # Path 1: config_flow validation stripping
    validated = strip_traits_for_validation(dict(test_schema))

    # Path 2: gateway stripping (static method, no instance needed)
    gateway_stripped = RamsesCoordinator._strip_schema_extensions(dict(test_schema))

    # Compare — both should go through _strip_and_orchestrate and produce
    # identical results.
    def serialize(d):
        return json.dumps(d, sort_keys=True, default=str)

    equal = serialize(validated) == serialize(gateway_stripped)

    # Collect _-prefixed keys that leaked through either path
    def find_underscore_keys(obj, path=""):
        found = []
        if isinstance(obj, dict):
            for k, v in obj.items():
                if isinstance(k, str) and k.startswith("_"):
                    found.append(f"{{path}}.{{k}}" if path else k)
                found.extend(find_underscore_keys(v, f"{{path}}.{{k}}" if path else k))
        elif isinstance(obj, list):
            for i, v in enumerate(obj):
                found.extend(find_underscore_keys(v, f"{{path}}[{{i}}]"))
        return found

    validated_underscore = find_underscore_keys(validated, "validated")
    gateway_underscore = find_underscore_keys(gateway_stripped, "gateway")

    # Check key structural properties
    def has_device(schema, dev_id):
        return dev_id in schema

    def get_device(schema, dev_id):
        return schema.get(dev_id, {{}})

    print(json.dumps({{
        "ok": True,
        "equal": equal,
        "validated_json": serialize(validated),
        "gateway_json": serialize(gateway_stripped),
        "validated_underscore_keys": validated_underscore,
        "gateway_underscore_keys": gateway_underscore,
        "validated_has_ctl": has_device(validated, "{CTL}"),
        "gateway_has_ctl": has_device(gateway_stripped, "{CTL}"),
        "validated_has_trv": has_device(validated, "{TRV}"),
        "gateway_has_trv": has_device(gateway_stripped, "{TRV}"),
        "validated_has_fan": has_device(validated, "{FAN}"),
        "gateway_has_fan": has_device(gateway_stripped, "{FAN}"),
        "validated_has_rem": has_device(validated, "{REM}"),
        "gateway_has_rem": has_device(gateway_stripped, "{REM}"),
        "validated_ctl_has_zones": "zones" in get_device(validated, "{CTL}"),
        "gateway_ctl_has_zones": "zones" in get_device(gateway_stripped, "{CTL}"),
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
                "stripping functions run without error",
                False,
                result.get("error", "unknown"),
            )
            return

        ctx.check("stripping functions run without error", True, "")

        # 1. Both paths produce identical output
        ctx.check(
            "config_flow and gateway stripping produce identical schema",
            result.get("equal") is True,
            "validated != gateway (see JSON output)",
        )

        # 2. No _-prefixed keys leak through either path
        validated_under = result.get("validated_underscore_keys", [])
        gateway_under = result.get("gateway_underscore_keys", [])
        ctx.check(
            "no _-prefixed keys in validated schema",
            len(validated_under) == 0,
            f"found: {validated_under[:5]}",
        )
        ctx.check(
            "no _-prefixed keys in gateway schema",
            len(gateway_under) == 0,
            f"found: {gateway_under[:5]}",
        )

        # 3. Both paths preserve topology (CTL zones)
        ctx.check(
            "validated schema has CTL with zones",
            result.get("validated_ctl_has_zones") is True,
            "CTL zones missing from validated",
        )
        ctx.check(
            "gateway schema has CTL with zones",
            result.get("gateway_ctl_has_zones") is True,
            "CTL zones missing from gateway",
        )

        # 4. Both paths preserve device entries
        for dev, label in [
            ("validated_has_ctl", "CTL in validated"),
            ("gateway_has_ctl", "CTL in gateway"),
            ("validated_has_fan", "FAN in validated"),
            ("gateway_has_fan", "FAN in gateway"),
            ("validated_has_rem", "REM in validated"),
            ("gateway_has_rem", "REM in gateway"),
        ]:
            ctx.check(label, result.get(dev) is True, f"{dev} is False")
