"""Recipe R57: Schema polling traits — polling_interval + is_battery (Phase 4c.1).

Verifies that the schema accepts the new polling-related traits introduced
in Phase 4c.1:

1. **Schema validation** — ``polling_interval`` (dict) and ``is_battery``
   (bool) are accepted in device traits
2. **Trait key mapping** — ``_polling_interval`` and ``_is_battery`` are
   mapped by ``strip_and_map_schema`` to their non-underscore equivalents
3. **DeviceBase properties** — ``polling_interval`` and ``is_battery``
   properties exist on device objects
4. **Config rename** — ``disable_discovery`` is deprecated in favour of
   ``disable_polling`` in the gateway config schema
5. **strip_and_map_schema** — the new traits are stripped (internal-only,
   not passed to the gateway)

This is a structural test that runs inside the ha-sim container.

See: https://github.com/ramses-rf/ramses_rf/pull/924 (Phase 4c.1)
"""

from __future__ import annotations

from ..base import Recipe, RecipeContext
from ..helpers import docker_exec_python


class R57SchemaPollingTraitsIssue924(Recipe):
    id = "R57"
    seq = 570
    title = "Schema polling traits — polling_interval + is_battery (PR 924)"

    async def run(self, ctx: RecipeContext) -> None:
        ctx.log_section("Recipe 57: Schema polling traits (PR 924)")

        code = """
import json

try:
    from ramses_rf.config import (
        strip_and_map_schema,
        sch_global_traits_dict_factory,
        SCH_POLLING_INTERVAL,
    )
    from ramses_rf.const import SZ_POLLING_INTERVAL, SZ_IS_BATTERY
    from ramses_rf.devices.dev_base import DeviceBase
    from ramses_rf.schemas import SCH_GATEWAY_DICT
    import voluptuous as vol
    import inspect

    results = {}

    # ── 1. Constants exist ────────────────────────────────────────────
    results["sz_polling_interval_exists"] = SZ_POLLING_INTERVAL == "polling_interval"
    results["sz_is_battery_exists"] = SZ_IS_BATTERY == "is_battery"

    # ── 2. Schema accepts polling traits ──────────────────────────────
    _heat_traits, _ = sch_global_traits_dict_factory()
    # Build a test schema with polling traits
    test_schema = {
        "01:150000": {
            "_class": "CTL",
            "_alias": "Test CTL",
            "_polling_interval": {"10E0": 7200},
            "_is_battery": False,
        },
    }

    stripped = strip_and_map_schema(test_schema)
    ctl_entry = stripped.get("01:150000", {})

    results["strip_runs_without_error"] = True
    results["polling_interval_mapped"] = (
        SZ_POLLING_INTERVAL in ctl_entry
    )
    results["is_battery_mapped"] = SZ_IS_BATTERY in ctl_entry
    results["polling_interval_value"] = ctl_entry.get(SZ_POLLING_INTERVAL)
    results["is_battery_value"] = ctl_entry.get(SZ_IS_BATTERY)

    # _-prefixed keys should be stripped (not passed to gateway)
    results["polling_interval_stripped"] = (
        "_polling_interval" not in ctl_entry
    )
    results["is_battery_stripped"] = (
        "_is_battery" not in ctl_entry
    )

    # ── 3. DeviceBase has properties ──────────────────────────────────
    results["device_has_polling_interval_prop"] = hasattr(
        DeviceBase, "polling_interval"
    )
    results["device_has_is_battery_prop"] = hasattr(
        DeviceBase, "is_battery"
    )

    # ── 4. Gateway config schema has disable_polling ──────────────────
    gw_keys = [str(k) for k in SCH_GATEWAY_DICT.keys()]
    results["config_has_disable_polling"] = any(
        "disable_polling" in k for k in gw_keys
    )
    # disable_discovery should still exist as deprecated alias
    results["config_has_disable_discovery"] = any(
        "disable_discovery" in k for k in gw_keys
    )

    # ── 5. SCH_POLLING_INTERVAL validates dict[str, int] ──────────────
    try:
        validated = SCH_POLLING_INTERVAL({"10E0": 3600, "1F41": 1800})
        results["polling_interval_validates_dict"] = True
        results["polling_interval_validated"] = validated
    except Exception:
        results["polling_interval_validates_dict"] = False

    # Should reject negative intervals
    try:
        SCH_POLLING_INTERVAL({"10E0": -1})
        results["polling_interval_rejects_negative"] = False
    except Exception:
        results["polling_interval_rejects_negative"] = True

    print(json.dumps({"ok": True, **results}))
except Exception as e:
    import traceback
    print(json.dumps({
        "error": f"{type(e).__name__}: {e}",
        "traceback": traceback.format_exc()[:2000],
        "ok": False,
    }))
"""
        result = docker_exec_python(code, timeout=30)

        if not result.get("ok"):
            ctx.check(
                "Schema polling traits run without error",
                False,
                result.get("error", "unknown"),
            )
            return

        ctx.check("Schema polling traits run without error", True, "")

        # 1. Constants
        ctx.check(
            "SZ_POLLING_INTERVAL constant is 'polling_interval'",
            result.get("sz_polling_interval_exists") is True,
            f"value={result.get('sz_polling_interval_exists')}",
        )
        ctx.check(
            "SZ_IS_BATTERY constant is 'is_battery'",
            result.get("sz_is_battery_exists") is True,
            f"value={result.get('sz_is_battery_exists')}",
        )

        # 2. Schema validation + mapping
        ctx.check(
            "strip_and_map_schema maps _polling_interval",
            result.get("polling_interval_mapped") is True,
            "polling_interval not mapped",
        )
        ctx.check(
            "strip_and_map_schema maps _is_battery",
            result.get("is_battery_mapped") is True,
            "is_battery not mapped",
        )
        ctx.check(
            "polling_interval value is the dict",
            result.get("polling_interval_value") == {"10E0": 7200},
            f"value={result.get('polling_interval_value')}",
        )
        ctx.check(
            "is_battery value is False",
            result.get("is_battery_value") is False,
            f"value={result.get('is_battery_value')}",
        )
        ctx.check(
            "_polling_interval stripped from gateway schema",
            result.get("polling_interval_stripped") is True,
            "_polling_interval not stripped",
        )
        ctx.check(
            "_is_battery stripped from gateway schema",
            result.get("is_battery_stripped") is True,
            "_is_battery not stripped",
        )

        # 3. DeviceBase properties
        ctx.check(
            "DeviceBase has polling_interval property",
            result.get("device_has_polling_interval_prop") is True,
            "property missing",
        )
        ctx.check(
            "DeviceBase has is_battery property",
            result.get("device_has_is_battery_prop") is True,
            "property missing",
        )

        # 4. Gateway config
        ctx.check(
            "Gateway config has disable_polling option",
            result.get("config_has_disable_polling") is True,
            "disable_polling not in config schema",
        )
        ctx.check(
            "Gateway config retains disable_discovery (deprecated alias)",
            result.get("config_has_disable_discovery") is True,
            "disable_discovery alias missing",
        )

        # 5. SCH_POLLING_INTERVAL validation
        ctx.check(
            "SCH_POLLING_INTERVAL validates dict[str, int]",
            result.get("polling_interval_validates_dict") is True,
            "validation failed",
        )
        ctx.check(
            "SCH_POLLING_INTERVAL rejects negative intervals",
            result.get("polling_interval_rejects_negative") is True,
            "negative interval accepted",
        )
