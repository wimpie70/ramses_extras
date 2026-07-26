"""Recipe R59: Phase 4 — _cleanup_stale_known_list strips stale keys on startup.

Verifies that ``_cleanup_stale_known_list`` (called in ``async_setup_entry``)
strips stale ``known_list`` and ``enforce_known_list`` from the config entry
options if they are present after a v3 migration.

This can happen when:
- A user downgrades ramses_cc to v2 code (which writes known_list back),
  then upgrades again to v3 code.
- A backup restore brings back old options.
- A config flow edit re-introduces the keys.

The cleanup is idempotent and runs on every startup, ensuring the config
entry stays clean even if external tools modify it.

Test approach: stop ha-sim, inject stale keys into .storage/core.config_entries,
restart ha-sim (which triggers async_setup_entry → _cleanup_stale_known_list),
then verify the stale keys are gone.

See: https://github.com/ramses-rf/ramses_cc/pull/870
"""

from __future__ import annotations

import json
import subprocess

from ..base import Recipe, RecipeContext
from ..const import CTL
from ..helpers import get_schema_retry


class R59Phase4CleanupStaleKnownList(Recipe):
    id = "R59"
    seq = 590
    title = "Phase 4 — _cleanup_stale_known_list strips stale keys (PR 870)"

    async def run(self, ctx: RecipeContext) -> None:
        ctx.log_section("Recipe 59: _cleanup_stale_known_list strips stale keys")

        # Step 1: Read the current config entry
        result = subprocess.run(
            [
                "docker",
                "exec",
                "ha-sim",
                "cat",
                "/config/.storage/core.config_entries",
            ],
            capture_output=True,
            text=True,
        )
        ctx.check(
            "core.config_entries readable",
            result.returncode == 0,
            f"exit code {result.returncode}",
        )
        if result.returncode != 0:
            return

        data = json.loads(result.stdout)
        entries = data["data"]["entries"]
        cc_idx = None
        cc_entry = None
        for i, e in enumerate(entries):
            if e["domain"] == "ramses_cc":
                cc_idx = i
                cc_entry = e
                break

        ctx.check("ramses_cc config entry found", cc_entry is not None, "")
        if cc_entry is None:
            return

        # Step 2: Stop ha-sim so we can safely modify .storage
        ctx.log_monitor.capture_before_restart("R59 pre-restart")
        print("  Stopping ha-sim to inject stale keys...")
        subprocess.run(["docker", "stop", "ha-sim"], capture_output=True)
        ctx.wait(2, "for container to stop")

        # Step 3: Inject stale known_list + enforce_known_list into options
        options = dict(cc_entry.get("options", {}))
        stale_known_list = {
            CTL: {"class": "CTL"},
            "04:150003": {"class": "TRV"},
        }
        options["known_list"] = stale_known_list
        ramses_rf = dict(options.get("ramses_rf", {}))
        ramses_rf["enforce_known_list"] = False
        options["ramses_rf"] = ramses_rf

        cc_entry["options"] = options
        entries[cc_idx] = cc_entry
        data["data"]["entries"] = entries

        # Write back the modified config entry via docker cp (container is
        # stopped, so docker exec won't work; the bind-mounted file is owned
        # by root inside the container, so direct host writes may fail too).
        import os
        import tempfile

        tmp_path = tempfile.mktemp(suffix=".json")
        with open(tmp_path, "w") as f:
            json.dump(data, f)

        cp_result = subprocess.run(
            [
                "docker",
                "cp",
                tmp_path,
                "ha-sim:/config/.storage/core.config_entries",
            ],
            capture_output=True,
            text=True,
        )
        os.unlink(tmp_path)

        ctx.check(
            "injected stale known_list + enforce_known_list",
            cp_result.returncode == 0,
            f"docker cp exit code {cp_result.returncode}: {cp_result.stderr[:80]}",
        )
        if cp_result.returncode != 0:
            # Restart ha-sim to recover
            subprocess.run(["docker", "start", "ha-sim"], capture_output=True)
            ctx.wait(20, "for ha-sim to start up")
            return

        # Step 4: Start ha-sim — async_setup_entry will run and call
        # _cleanup_stale_known_list, which should strip the stale keys
        print("  Starting ha-sim (triggers _cleanup_stale_known_list)...")
        subprocess.run(["docker", "start", "ha-sim"], capture_output=True)
        ctx.wait(20, "for ha-sim to start up")
        ctx.log_monitor.reset_baseline()
        ctx.refresh_token()
        ctx.wait(10, "for ramses_cc to initialize + run cleanup")

        # Step 5: Read the config entry again and verify stale keys are gone
        result2 = subprocess.run(
            [
                "docker",
                "exec",
                "ha-sim",
                "cat",
                "/config/.storage/core.config_entries",
            ],
            capture_output=True,
            text=True,
        )
        ctx.check(
            "core.config_entries re-readable",
            result2.returncode == 0,
            f"exit code {result2.returncode}",
        )
        if result2.returncode != 0:
            return

        data2 = json.loads(result2.stdout)
        cc_entry2 = None
        for e in data2["data"]["entries"]:
            if e["domain"] == "ramses_cc":
                cc_entry2 = e
                break

        ctx.check("ramses_cc entry found after restart", cc_entry2 is not None, "")
        if cc_entry2 is None:
            return

        options2 = cc_entry2.get("options", {})

        stale_kl = list(options2.get("known_list", {}).keys())[:5]
        ctx.check(
            "stale known_list stripped by _cleanup_stale_known_list",
            "known_list" not in options2,
            f"known_list still present: {stale_kl}",
        )

        ramses_rf2 = options2.get("ramses_rf", {})
        ctx.check(
            "stale enforce_known_list stripped",
            "enforce_known_list" not in ramses_rf2,
            f"enforce_known_list still present: {ramses_rf2.get('enforce_known_list')}",
        )

        # Step 6: Verify schema is still intact (cleanup doesn't damage it)
        schema = get_schema_retry()
        ctx.check(
            "schema intact after cleanup",
            CTL in schema if schema else False,
            f"schema keys: {list(schema.keys())[:10] if schema else 'empty'}",
        )

        # Step 7: Verify the config entry version is still 3
        ctx.check(
            "config entry version still 3 after cleanup",
            cc_entry2.get("version") == 3,
            f"version={cc_entry2.get('version')}",
        )
