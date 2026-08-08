"""Recipe R61: FAN 2411 parameter entities availability (issue 851).

Regression guard for the chicken-and-egg bug that left all FAN parameter
``number`` entities unavailable after ramses_rf 0.58.3+ removed the
``_setup_discovery_cmds`` daily 2411 poll.

The bug had two parts:

1. **ramses_rf** — ``_handle_initialized_callback`` only fired when
   ``supports_2411`` was True, but ``supports_2411`` is only set by
   ``_handle_2411_message``, which only runs when a 2411 RP/I arrives.
   Nobody sent the initial 2411 RQ (the old discovery poll was removed),
   so the callback never fired and ramses_cc never called
   ``get_all_fan_params``.  Fixed by firing the callback on any FAN
   message and dropping the ``supports_2411`` requirement.

2. **ramses_cc** — ``_async_param_updated`` compared param IDs with
   direct string equality (``"1" == "01"``), but ramses_rf strips
   leading zeros from param IDs while the entity description keeps the
   original format.  Fixed by normalizing both sides with
   ``lstrip("0")``.

This recipe is a structural test that verifies the code paths are
correct by inspecting ramses_rf/ramses_cc internals via
``docker_exec_python``.  It checks:

  a. ``_handle_initialized_callback`` does NOT require
     ``supports_2411`` (the guard was removed).
  b. ``process_state_updates`` calls ``_handle_initialized_callback``
     on any message from/to a FAN device.
  c. ``_async_param_updated`` normalizes param IDs with ``lstrip("0")``
     before comparing.
  d. ``fan_handler`` has periodic 2411 polling (``_start_param_polling``).

See:
  https://github.com/ramses-rf/ramses_rf/pull/1011
  https://github.com/ramses-rf/ramses_cc/pull/916
  https://github.com/ramses-rf/ramses_cc/issues/851
"""

from __future__ import annotations

from ..base import Recipe, RecipeContext
from ..const import FAN
from ..helpers import (
    docker_exec_python,
    get_schema_retry,
    load_profile_yaml,
)
from ..profile import mixed_yaml


class R61Fan2411ParamEntitiesIssue851(Recipe):
    id = "R61"
    seq = 610
    title = "FAN 2411 parameter entities availability (issue 851)"

    async def run(self, ctx: RecipeContext) -> None:
        ctx.log_section(
            "Recipe 61: FAN 2411 parameter entities availability (issue 851)"
        )

        # 1. Load the mixed profile (has FAN 32:150000 with REM + CO2)
        print("  Loading mixed profile (FAN + REM + CO2)...")
        yaml_text = mixed_yaml()
        try:
            await load_profile_yaml(
                ctx.token,
                yaml_text,
                speed=0.01,
                preload_schema=True,
                reload_ramses=True,
            )
        except RuntimeError as e:
            print(f"  Profile load failed: {e}")
        ctx.wait_for_ramses_cc_reload(timeout=20)
        ctx.refresh_token()

        # Verify FAN is in the schema
        schema = get_schema_retry()
        ctx.check(
            f"FAN {FAN} in schema",
            FAN in schema,
            f"schema keys={list(schema.keys())}",
        )

        # 2. Structural check: _handle_initialized_callback must NOT
        #    require supports_2411 (the guard was removed in the fix).
        #    We inspect the source code inside the container to verify.
        code_check_callback = """
import inspect, json
try:
    from ramses_rf.devices.hvac_ventilators import HvacVentilator
    src = inspect.getsource(HvacVentilator._handle_initialized_callback)
    # The fix removes the "supports_2411" guard.  The old code had:
    #   if self._initialized_callback is not None and self.supports_2411:
    # The new code has:
    #   if self._initialized_callback is not None:
    # Check the actual if-condition line, not the docstring.
    has_supports_2411_guard = "and self.supports_2411" in src
    print(json.dumps({
        "ok": True,
        "has_supports_2411_guard": has_supports_2411_guard,
    }))
except Exception as e:
    print(json.dumps({"ok": False, "error": str(e)}))
"""
        result = docker_exec_python(code_check_callback)
        ctx.check(
            "structural: _handle_initialized_callback source is importable",
            result.get("ok", False),
            f"result={result}",
        )
        if result.get("ok"):
            ctx.check(
                "fix: _handle_initialized_callback does NOT require supports_2411",
                not result.get("has_supports_2411_guard", True),
                "supports_2411 guard still present in _handle_initialized_callback",
            )

        # 3. Structural check: process_state_updates calls
        #    _handle_initialized_callback on FAN messages.
        code_check_projector = """
import inspect, json
try:
    from ramses_rf.state_projector import process_state_updates
    src = inspect.getsource(process_state_updates)
    has_fan_callback = "_handle_initialized_callback" in src
    has_hvac_check = "HvacVentilator" in src
    print(json.dumps({
        "ok": True,
        "has_fan_callback": has_fan_callback,
        "has_hvac_check": has_hvac_check,
    }))
except Exception as e:
    print(json.dumps({"ok": False, "error": str(e)}))
"""
        result = docker_exec_python(code_check_projector)
        ctx.check(
            "structural: process_state_updates source is importable",
            result.get("ok", False),
            f"result={result}",
        )
        if result.get("ok"):
            ctx.check(
                "fix: process_state_updates calls _handle_initialized_callback",
                result.get("has_fan_callback", False),
                "_handle_initialized_callback not called in process_state_updates",
            )
            ctx.check(
                "fix: process_state_updates checks for HvacVentilator",
                result.get("has_hvac_check", False),
                "HvacVentilator isinstance check missing in process_state_updates",
            )

        # 4. Structural check: _async_param_updated normalizes param IDs
        #    with lstrip("0") before comparing.
        code_check_number = """
import inspect, json
try:
    from custom_components.ramses_cc.number import RamsesNumberParam
    src = inspect.getsource(RamsesNumberParam._async_param_updated)
    has_lstrip = "lstrip" in src
    # The old code used direct string comparison:
    #   str(event_data.get("param_id", "")).lower() == str(our_param_id).lower()
    # The new code normalizes with lstrip("0"):
    #   event_param = str(...).upper().lstrip("0") or "0"
    print(json.dumps({
        "ok": True,
        "has_lstrip_normalization": has_lstrip,
    }))
except Exception as e:
    print(json.dumps({"ok": False, "error": str(e)}))
"""
        result = docker_exec_python(code_check_number)
        ctx.check(
            "structural: RamsesNumberParam._async_param_updated is importable",
            result.get("ok", False),
            f"result={result}",
        )
        if result.get("ok"):
            ctx.check(
                "fix: _async_param_updated normalizes param IDs with lstrip(0)",
                result.get("has_lstrip_normalization", False),
                "lstrip normalization missing in _async_param_updated",
            )

        # 5. Structural check: fan_handler has _start_param_polling.
        code_check_fan_handler = """
import inspect, json
try:
    from custom_components.ramses_cc.fan_handler import RamsesFanHandler
    has_start_poll = hasattr(RamsesFanHandler, "_start_param_polling")
    has_stop_poll = hasattr(RamsesFanHandler, "_stop_param_polling")
    has_poll_tasks = "_fan_param_poll_tasks" in inspect.getsource(
        RamsesFanHandler.__init__
    )
    print(json.dumps({
        "ok": True,
        "has_start_poll": has_start_poll,
        "has_stop_poll": has_stop_poll,
        "has_poll_tasks": has_poll_tasks,
    }))
except Exception as e:
    print(json.dumps({"ok": False, "error": str(e)}))
"""
        result = docker_exec_python(code_check_fan_handler)
        ctx.check(
            "structural: RamsesFanHandler is importable",
            result.get("ok", False),
            f"result={result}",
        )
        if result.get("ok"):
            ctx.check(
                "fix: fan_handler has _start_param_polling method",
                result.get("has_start_poll", False),
                "_start_param_polling missing from RamsesFanHandler",
            )
            ctx.check(
                "fix: fan_handler has _stop_param_polling method",
                result.get("has_stop_poll", False),
                "_stop_param_polling missing from RamsesFanHandler",
            )
            ctx.check(
                "fix: fan_handler tracks _fan_param_poll_tasks dict",
                result.get("has_poll_tasks", False),
                "_fan_param_poll_tasks dict missing from __init__",
            )

        # 6. Verify parameter entities exist for the FAN device.
        #    The number platform creates them during setup if the device
        #    has existing entities in the registry, or when the
        #    initialized callback fires.  The param entities use
        #    has_entity_name=True, so their entity_ids are derived from
        #    the parameter name (e.g. number.support, number.comfort_temperature)
        #    rather than containing the device ID.  We check the entity
        #    registry (.storage/core.entity_registry) for unique_ids
        #    matching "32:150000-param_*".
        code_check_registry = """
import json
with open("/config/.storage/core.entity_registry") as f:
    data = json.load(f)
entities = data.get("data", {}).get("entities", [])
fan_params = [
    e for e in entities
    if "param_" in (e.get("unique_id") or "")
    and "32:150000" in (e.get("unique_id") or "")
    and e.get("platform") == "ramses_cc"
]
print(json.dumps({
    "ok": True,
    "count": len(fan_params),
    "example_unique_ids": [e.get("unique_id") for e in fan_params[:3]],
    "example_entity_ids": [e.get("entity_id") for e in fan_params[:3]],
}))
"""
        result = docker_exec_python(code_check_registry)
        ctx.check(
            "entity registry is readable",
            result.get("ok", False),
            f"result={result}",
        )
        if result.get("ok"):
            count = result.get("count", 0)
            print(f"  Found {count} FAN parameter entities in registry")
            if result.get("example_unique_ids"):
                print(f"  Example unique_ids: {result['example_unique_ids']}")
            ctx.check(
                "FAN parameter number entities exist for 32:150000",
                count > 0,
                f"found {count} param entities for FAN in registry",
            )
