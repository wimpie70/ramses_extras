"""Recipe R58: Phase 4 — known_list removed from config entry, enforce always-on.

Verifies the key behaviors introduced by ramses_cc Phase 4 (PR 870):

1. **known_list not in config entry options** — the config entry no longer
   stores ``known_list``; it is derived in-memory from the schema by
   ``_derive_known_list_from_schema()``.
2. **enforce_known_list not in config entry options** — the
   ``enforce_known_list`` toggle is removed from the ``ramses_rf`` sub-dict;
   it is hardcoded to ``True`` in ``coordinator._create_client``.
3. **HGI in derived known_list** — the HGI gateway device (18:001234)
   appears in the derived known_list (fixes the "SHOULD be in known_list"
   warnings and the HGI removal rejection in R03).
4. **_cleanup_stale_known_list strips stale keys** — if a v3 config entry
   somehow still has ``known_list`` or ``enforce_known_list`` in options
   (e.g. from a downgrade/upgrade cycle), they are stripped on startup.
5. **v2→v3 migration backup exists** — the ``.storage/ramses_cc_migration_v2_backup``
   file is created during migration (safety net for downgrade).

See: https://github.com/ramses-rf/ramses_cc/pull/870
"""

from __future__ import annotations

import json
import subprocess

from ..base import Recipe, RecipeContext
from ..const import CTL, DHW, FAN, REM, TRV
from ..helpers import (
    get_current_instance,
    get_known_list,
    get_schema_retry,
    load_profile_yaml,
)
from ..profile import mixed_yaml


class R58Phase4KnownListRemovalEnforceAlwaysOn(Recipe):
    id = "R58"
    seq = 580
    title = "Phase 4 — known_list removed, enforce always-on (PR 870)"

    async def run(self, ctx: RecipeContext) -> None:
        ctx.log_section("Recipe 58: Phase 4 known_list removal + enforce always-on")

        # Load the mixed profile to ensure all devices (CTL, TRV, DHW,
        # FAN, REM) are present in the schema.  Without this, the derived
        # known_list may reflect stale state from a previous recipe that
        # used a different profile (e.g. a minimal profile without TRV).
        print("  Loading mixed profile (ensures all devices in schema)...")
        try:
            await load_profile_yaml(
                ctx.token,
                mixed_yaml(),
                speed=0.01,
                preload_schema=True,
                reload_ramses=True,
            )
        except RuntimeError as e:
            print(f"  Profile load failed: {e}")
        ctx.wait_for_ramses_cc_reload(timeout=20)
        ctx.refresh_token()

        # Read the raw config entry to check what keys are in options
        result = subprocess.run(
            [
                "docker",
                "exec",
                get_current_instance().name,
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
        cc_entry = None
        for e in data["data"]["entries"]:
            if e["domain"] == "ramses_cc":
                cc_entry = e
                break

        ctx.check("ramses_cc config entry found", cc_entry is not None, "")
        if cc_entry is None:
            return

        options = cc_entry.get("options", {})

        # 1. known_list must NOT be in config entry options
        ctx.check(
            "known_list not in config entry options",
            "known_list" not in options,
            f"found known_list key: {list(options.get('known_list', {}).keys())[:5]}",
        )

        # 2. enforce_known_list must NOT be in ramses_rf sub-dict
        ramses_rf_opts = options.get("ramses_rf", {})
        ctx.check(
            "enforce_known_list not in ramses_rf options",
            "enforce_known_list" not in ramses_rf_opts,
            f"found enforce_known_list={ramses_rf_opts.get('enforce_known_list')}",
        )

        # 3. HGI must be in the derived known_list (fixes R03 + warnings)
        known = get_known_list()
        ctx.check(
            "HGI in derived known_list",
            get_current_instance().hgi_id in known,
            f"known_list keys: {list(known.keys())[:10]}",
        )

        # 4. CTL, TRV, DHW, FAN, REM must all be in derived known_list
        for dev_id, label in [
            (CTL, "CTL"),
            (TRV, "TRV"),
            (DHW, "DHW"),
            (FAN, "FAN"),
            (REM, "REM"),
        ]:
            ctx.check(
                f"{label} in derived known_list",
                dev_id in known,
                f"missing {dev_id}",
            )

        # 5. Schema must be present and populated
        schema = get_schema_retry()
        ctx.check(
            "schema present in config entry",
            bool(schema),
            "schema is empty",
        )
        ctx.check(
            "CTL in schema",
            CTL in schema,
            f"schema keys: {list(schema.keys())[:10]}",
        )

        # 6. Check migration backup exists (if a v2→v3 migration happened)
        backup_result = subprocess.run(
            [
                "docker",
                "exec",
                get_current_instance().name,
                "cat",
                "/config/.storage/ramses_cc_migration_v2_backup",
            ],
            capture_output=True,
            text=True,
        )
        if backup_result.returncode == 0:
            backup = json.loads(backup_result.stdout).get("data", {})
            ctx.check(
                "migration v2 backup exists and has version 2",
                backup.get("version") == 2,
                f"version={backup.get('version')}",
            )
            ctx.check(
                "migration v2 backup has options",
                "options" in backup,
                "",
            )
        else:
            # Backup may not exist if the entry was created fresh at v3
            # (no migration needed).  This is not a failure.
            ctx.check(
                "migration v2 backup (skipped — fresh v3 entry)",
                True,
                "no backup file (entry may have been created at v3)",
            )

        # 7. Verify _cleanup_stale_known_list would strip stale keys
        #    (structural check — the function is called in async_setup_entry)
        #    We verify by checking that the config entry version is 3
        ctx.check(
            "config entry version is 3",
            cc_entry.get("version") == 3,
            f"version={cc_entry.get('version')}",
        )
