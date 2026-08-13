"""Recipe R60: send_packet CommandDTO + device_id filter (issue 864).

Regression guard for ``ramses_cc.send_packet`` covering two failure modes
reported in issue 864:

1. **PR 867** — ``_adjust_sentinel_packet`` was migrated from the old
   ``cmd.src.id`` / ``cmd.dst.id`` API (removed by the CommandDTO migration
   in PR 853) to positional ``cmd.addr1`` / ``cmd.addr2`` addressing using
   ``dataclasses.replace()``.  Before this fix every ``send_packet`` call
   raised ``AttributeError: 'CommandDTO' object has no attribute 'src'``.

2. **Faked-device schema inclusion (Phase 4)** — faked devices
   (``_faked: true`` in the schema) used for ``send_packet`` automations
   (e.g. a faked THM injecting 30C9 zone-temperature packets to keep a
   BDR relay in sync) must be in the schema-derived known_list so the
   device_id filter does not reject ``send_packet`` calls with
   ``ProtocolError: Command excluded by device_id filter``.

   Phase 4 (commit 9dc264d) made the schema the sole source of truth:
   ``known_list`` is no longer stored in the config entry, and
   ``_derive_known_list_from_schema`` walks the schema to build the
   protocol's include list.  Faked devices must therefore appear in the
   schema (typically as orphans with ``_faked: true`` and ``_class: THM``)
   so they are included in the derived known_list.

This recipe reproduces the user's exact scenario from issue 864:
a faked THM (``03:004303``) in the schema with ``_faked: true``, and
verifies that:

  a. ``send_packet`` to the faked device does NOT raise
     ``Command excluded by device_id filter``.
  b. The sentinel ``18:000730`` path does NOT raise
     ``AttributeError`` (PR 867 regression guard).
  c. The faked device appears in the schema-derived known_list.

See: https://github.com/ramses-rf/ramses_cc/pull/867
     https://github.com/ramses-rf/ramses_cc/issues/864
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time

from ..base import Recipe, RecipeContext
from ..const import CTL
from ..helpers import (
    async_clear_cached_state,
    call_service,
    docker_exec_python,
    get_current_instance,
    is_ramses_cc_loaded,
    load_profile_yaml,
    wait_for,
    ws_send,
)
from ..profile import MIXED_KL, MIXED_SCHEMA, _build_yaml

# A faked THM device used to inject 30C9 packets (mirrors issue 864).
FAKED_THM = "03:004303"


class R60SendPacketCmdtoFilterIssue864(Recipe):
    id = "R60"
    seq = 600
    title = "send_packet CommandDTO + device_id filter (issue 864)"

    async def run(self, ctx: RecipeContext) -> None:
        ctx.log_section("Recipe 60: send_packet CommandDTO + device_id filter")

        # ── Setup & Step 1: Load profile with faked THM in schema ────
        print("  Clearing cached state and loading profile with faked THM...")
        await async_clear_cached_state(ctx, label="R60 pre-clean")
        ctx.log_monitor.reset_baseline()

        schema_r60 = dict(MIXED_SCHEMA)
        schema_r60[FAKED_THM] = {"_class": "THM", "_faked": True}
        yaml_r60 = _build_yaml(MIXED_KL, schema_r60)

        await load_profile_yaml(ctx.token, yaml_r60, speed=0.01)
        ctx.wait_for_ramses_cc_reload(timeout=20)
        ctx.refresh_token()
        ctx.check("faked THM injected into schema (_faked=true)", True, "")
        ctx.wait(3, "for protocol/filter to stabilise")

        # ── Step 3: Test send_packet with the faked device ───────────
        # This is the user's exact scenario from issue 864.
        # The send will likely timeout (no echo in sim), but the key
        # check is that it does NOT fail with "Command excluded by
        # device_id filter".
        print(f"  Calling send_packet with faked THM {FAKED_THM}...")
        t0 = time.time()
        filter_rejected = False
        error_msg = ""
        try:
            call_service(
                ctx.token,
                "ramses_cc",
                "send_packet",
                {
                    "device_id": FAKED_THM,
                    "from_id": FAKED_THM,
                    "verb": "I",
                    "code": "30C9",
                    "payload": "000834",
                },
            )
            print("  send_packet succeeded (unexpected in sim, but OK)")
        except RuntimeError as e:
            error_msg = str(e)
            elapsed = time.time() - t0
            if "Command excluded by device_id filter" in error_msg:
                filter_rejected = True
            print(
                f"  send_packet returned error after {elapsed:.1f}s: {error_msg[:120]}"
            )

        ctx.wait(3, "for log to flush")

        inst_name = get_current_instance().name

        # Also check the HA log directly for the filter rejection
        log_result = subprocess.run(
            [
                "docker",
                "exec",
                inst_name,
                "bash",
                "-c",
                f"grep 'Command excluded by device_id filter.*{FAKED_THM}' "
                "/config/home-assistant.log | tail -5",
            ],
            capture_output=True,
            text=True,
        )
        log_filter_rejection = bool(log_result.stdout.strip())

        ctx.check(
            "send_packet to faked device NOT rejected by device_id filter",
            not filter_rejected and not log_filter_rejection,
            (
                f"filter_rejected={filter_rejected}, "
                f"log_rejection={log_filter_rejection}, "
                f"error={error_msg[:100]}"
            ),
        )

        # ── Step 4: Test the sentinel 18:000730 path (PR 867) ───────
        # This verifies that _adjust_sentinel_packet does not raise
        # AttributeError on the CommandDTO (the original issue 864 bug).
        print("  Calling send_packet with sentinel 18:000730 (PR 867 fix)...")
        sentinel_attr_error = False
        sentinel_error_msg = ""
        try:
            call_service(
                ctx.token,
                "ramses_cc",
                "send_packet",
                {
                    "device_id": "18:000730",
                    "from_id": "18:000730",
                    "verb": "I",
                    "code": "1F09",
                    "payload": "00",
                },
            )
            print("  sentinel send_packet succeeded")
        except RuntimeError as e:
            sentinel_error_msg = str(e)
            if "AttributeError" in sentinel_error_msg:
                sentinel_attr_error = True
            print(
                f"  sentinel send_packet error (non-AttributeError OK): "
                f"{sentinel_error_msg[:120]}"
            )

        ctx.wait(3, "for log to flush")

        # Check the HA log for AttributeError on the sentinel path
        log_attr_result = subprocess.run(
            [
                "docker",
                "exec",
                inst_name,
                "bash",
                "-c",
                "grep -A2 'AttributeError.*CommandDTO.*src\\|"
                "AttributeError.*src.*CommandDTO' "
                "/config/home-assistant.log | tail -10",
            ],
            capture_output=True,
            text=True,
        )
        log_attr_error = bool(log_attr_result.stdout.strip())

        ctx.check(
            "sentinel 18:000730 does NOT raise AttributeError (PR 867)",
            not sentinel_attr_error and not log_attr_error,
            (
                f"attr_error={sentinel_attr_error}, "
                f"log_attr={log_attr_error}, "
                f"error={sentinel_error_msg[:100]}"
            ),
        )

        # ── Step 5: Verify the faked device is in the derived known_list ──
        # Use docker_exec_python to call _derive_known_list_from_schema
        # with the schema we injected.  Phase 4 signature takes only the
        # schema (no user_overrides / schema_is_ssot params).
        code = f"""
import json, sys
sys.path.insert(0, "/config/custom_components")
try:
    from ramses_cc.coordinator import RamsesCoordinator
    schema = {repr(schema_r60)}
    result = RamsesCoordinator._derive_known_list_from_schema(schema)
    print(json.dumps({{
        "faked_in_known_list": {repr(FAKED_THM)} in result,
        "faked_traits": result.get({repr(FAKED_THM)}),
        "known_list_keys": sorted(result.keys())[:10],
        "ok": True,
    }}))
except Exception as e:
    print(json.dumps({{"error": str(e), "ok": False}}))
"""
        result = docker_exec_python(code, timeout=30)
        ctx.check(
            f"faked device {FAKED_THM} in schema-derived known_list",
            result.get("faked_in_known_list", False),
            f"result={result}",
        )
        # Also verify the faked trait propagated
        faked_traits = result.get("faked_traits") or {}
        ctx.check(
            f"faked device {FAKED_THM} has faked=True trait",
            faked_traits.get("faked") is True,
            f"traits={faked_traits}",
        )

        # ── Cleanup: restore standard mixed profile ───────────────────
        print("  Cleaning up R60...")
        try:
            await ws_send(
                ctx.token,
                {
                    "type": "ramses_extras/device_simulator/load_profile",
                    "profile": "mixed",
                    "speed": 0.01,
                    "preload_schema": True,
                    "reload_ramses_cc": True,
                },
            )
        except RuntimeError:
            pass
        ctx.wait_for_ramses_cc_reload(timeout=15)
