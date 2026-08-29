"""Recipe R81: Config entry migration v2→v3 (known_list to schema).

Tests the ``async_migrate_entry`` path from config entry version 2
to version 3.  A v2 entry has already had deprecated packet_log/ramses_rf
keys cleaned up (v1→v2), but still has:

- ``known_list`` with legacy trait keys (``class``, ``alias``, ``faked``,
  ``bound``, ``scheme`` — no ``_`` prefix)
- ``enforce_known_list: true`` in the ``ramses_rf`` sub-dict
- Schema may have some entries but without ``_``-prefixed traits

The v2→v3 migration should:
- Merge ``known_list`` traits into schema as ``_``-prefixed keys
- Drop ``known_list`` and ``enforce_known_list``
- Save a v2 backup to ``.storage/ramses_cc_migration_v2_backup``
- Bump version to 3

This recipe also tests the edge case where a device is in ``known_list``
but NOT in the schema — the migration should create a schema entry for it.
And the edge case where a device is in both with conflicting traits —
schema traits should win (not be overwritten by known_list).
"""

from __future__ import annotations

import json
import os
import subprocess

from ..base import Recipe, RecipeContext
from ..const import CO2, CTL, DHW, FAN, HGI, REM
from ..helpers import (
    get_current_instance,
    get_entities,
    get_schema_retry,
    is_ramses_cc_loaded,
    wait_for_ha_ready,
    wait_for_ramses_cc_loaded,
    wait_for_transport_ready,
)


def _build_v2_options(hgi_id: str) -> dict:
    """Build a v2-era config entry options dict.

    v2 has already cleaned up deprecated packet_log/ramses_rf keys,
    but still has known_list with legacy trait keys and enforce_known_list.
    The schema has some entries (without _ traits) to test the merge.
    """
    return {
        "advanced_features": {
            "auto_notify": True,
            "passive_scan": True,
            "send_packet": True,
        },
        "packet_log": {
            "packet_log_retention_days": 5,
            "rotate_bytes": 10000,
        },
        "ramses_rf": {
            "enable_eavesdrop": False,
            "enforce_known_list": True,
            "log_all_mqtt": True,
        },
        "scan_interval": 60,
        # Schema has some entries but WITHOUT _ traits.
        # The migration should merge traits from known_list into these.
        # CTL already has a zone structure — traits should be added.
        # FAN is NOT in schema — migration should create it from known_list.
        # TRV is in schema with _alias — known_list alias should NOT overwrite.
        "schema": {
            CTL: {
                "zones": {
                    "00": {"sensor": "01:150000", "actuators": ["04:150000"]},
                },
                "stored_hotwater": {"sensor": DHW},
            },
            "04:150000": {"_alias": "My TRV"},  # schema alias should win
        },
        "known_list": {
            hgi_id: {"class": "HGI"},
            FAN: {"class": "FAN", "bound": REM, "scheme": "itho"},
            REM: {"class": "REM"},
            CO2: {"class": "CO2"},
            CTL: {"class": "CTL", "alias": "Living Room"},
            DHW: {"class": "DHW", "faked": True},
            "04:150000": {"class": "TRV", "alias": "Kitchen"},
        },
        "serial_port": {
            "port_name": f"mqtt://localhost:1884/RAMSES/GATEWAY_SIM/{hgi_id}",
        },
    }


class R81ConfigEntryMigrationV2ToV3(Recipe):
    id = "R81"
    seq = 810
    title = "Config entry migration v2→v3 (known_list to schema)"

    async def run(self, ctx: RecipeContext) -> None:
        ctx.log_section("Recipe 81: Config entry migration v2→v3")

        inst = get_current_instance()
        hgi_id = inst.hgi_id

        # ── Step 1: Stop HA and inject a v2 config entry ────────────
        print(f"  Stopping {inst.name} to inject v2 config entry...")
        subprocess.run(["docker", "stop", inst.name], capture_output=True)
        ctx.wait(2, "for container to stop")

        host_path = f"{inst.config_dir}/.storage/core.config_entries"
        try:
            with open(host_path) as f:
                raw = f.read()
        except OSError as e:
            ctx.check(
                "core.config_entries readable (host mount)",
                False,
                f"could not read {host_path}: {e}",
            )
            subprocess.run(["docker", "start", inst.name], capture_output=True)
            ctx.wait_for_ha_ready(timeout=30)
            return

        ctx.check("core.config_entries readable", bool(raw), "")
        if not raw:
            subprocess.run(["docker", "start", inst.name], capture_output=True)
            ctx.wait_for_ha_ready(timeout=30)
            return

        data = json.loads(raw)
        cc_entry = None
        cc_idx = None
        for i, e in enumerate(data["data"]["entries"]):
            if e["domain"] == "ramses_cc":
                cc_entry = e
                cc_idx = i
                break

        ctx.check("ramses_cc config entry found", cc_entry is not None, "")
        if cc_entry is None:
            subprocess.run(["docker", "start", inst.name], capture_output=True)
            ctx.wait_for_ha_ready(timeout=30)
            return

        # Save the original v3 options so we can restore them after the test
        original_options = json.loads(json.dumps(cc_entry.get("options", {})))
        original_version = cc_entry.get("version", 3)

        # Replace with v2-era options
        cc_entry["options"] = _build_v2_options(hgi_id)
        cc_entry["version"] = 2
        data["data"]["entries"][cc_idx] = cc_entry

        # Delete .storage/ramses_cc (client state cache)
        storage_path = f"{inst.storage_path}/ramses_cc"
        if os.path.exists(storage_path):
            os.remove(storage_path)

        # Delete any existing v2 backup
        backup_path = f"{inst.storage_path}/ramses_cc_migration_v2_backup"
        if os.path.exists(backup_path):
            os.remove(backup_path)

        # Write via a temporary container with the config volume mounted.
        # The .storage dir is root-owned (from the container), so we can't
        # write directly to the host path.  docker cp to a stopped container
        # writes to the overlay (shadowed by bind mount on start).
        # A temporary container with the volume mount can write as root.
        import tempfile as _tf

        with _tf.NamedTemporaryFile(suffix=".json", mode="w", delete=False) as f:
            json.dump(data, f)
            tmp_path = f.name
        write_result = subprocess.run(
            [
                "docker",
                "run",
                "--rm",
                "-v",
                f"{inst.config_dir}:/config",
                "-v",
                f"{tmp_path}:/tmp/ce.json:ro",
                "python:3.12-slim",
                "python3",
                "-c",
                "import shutil, os; shutil.copyfile('/tmp/ce.json', "
                "'/config/.storage/core.config_entries'); "
                "os.chmod('/config/.storage/core.config_entries', 0o644)",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        os.unlink(tmp_path)

        ctx.check(
            "v2 config entry injected (version=2, known_list, enforce_known_list)",
            write_result.returncode == 0,
            f"exit {write_result.returncode}: {write_result.stderr[:80]}",
        )
        if write_result.returncode != 0:
            subprocess.run(["docker", "start", inst.name], capture_output=True)
            ctx.wait_for_ha_ready(timeout=30)
            return

        # ── Step 2: Start HA and wait for migration ─────────────────
        print(f"  Starting {inst.name} (migration should run on startup)...")
        subprocess.run(["docker", "start", inst.name], capture_output=True)
        ctx.wait_for_ha_ready(timeout=60, msg="for HA to start after migration")
        ctx.wait_for_ramses_cc_loaded(
            timeout=30, msg="for ramses_cc to load after migration"
        )
        wait_for_transport_ready(timeout=30)
        # Token may be invalid after HA restart — refresh it
        ctx.refresh_token()

        # Wait for HA to flush the migrated config entry to disk.
        # async_migrate_entry updates the entry in memory and schedules an
        # async write to core.config_entries.  The file may not be updated
        # immediately when the transport is ready.
        def _version_is_3() -> bool:
            r = subprocess.run(
                [
                    "docker",
                    "exec",
                    inst.name,
                    "cat",
                    "/config/.storage/core.config_entries",
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if r.returncode != 0:
                return False
            try:
                d = json.loads(r.stdout)
                for e in d["data"]["entries"]:
                    if e["domain"] == "ramses_cc":
                        return e.get("version") == 3
            except Exception:  # noqa: BLE001
                pass
            return False

        from ..helpers import wait_for

        wait_for(
            _version_is_3,
            timeout=30,
            interval=1,
            floor=10,
            msg="for config entry version=3 to flush to disk",
        )

        # ── Step 3: Verify migration results ────────────────────────
        result = subprocess.run(
            [
                "docker",
                "exec",
                inst.name,
                "cat",
                "/config/.storage/core.config_entries",
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            ctx.check("core.config_entries readable after migration", False, "")
            return

        migrated_data = json.loads(result.stdout)
        migrated_entry = None
        for e in migrated_data["data"]["entries"]:
            if e["domain"] == "ramses_cc":
                migrated_entry = e
                break

        ctx.check(
            "ramses_cc entry found after migration", migrated_entry is not None, ""
        )
        if migrated_entry is None:
            return

        # Check 1: version bumped to 3
        ctx.check(
            "Config entry version is 3",
            migrated_entry.get("version") == 3,
            f"version={migrated_entry.get('version')}",
        )

        options = migrated_entry.get("options", {})

        # Check 2: known_list is gone
        ctx.check(
            "known_list removed from options",
            "known_list" not in options,
            f"keys={list(options.keys())}",
        )

        # Check 3: enforce_known_list is gone from ramses_rf
        ramses_rf = options.get("ramses_rf", {})
        ctx.check(
            "enforce_known_list removed from ramses_rf",
            "enforce_known_list" not in ramses_rf,
            f"ramses_rf keys={list(ramses_rf.keys())}",
        )

        # Check 4: schema has merged traits
        schema = options.get("schema", {})

        # FAN was NOT in schema — migration should have created it from known_list
        ctx.check(
            "FAN created in schema from known_list (was not in schema before)",
            isinstance(schema.get(FAN), dict) and schema[FAN].get("_class") == "FAN",
            f"FAN entry={schema.get(FAN)}",
        )
        ctx.check(
            "FAN _bound merged from known_list",
            isinstance(schema.get(FAN), dict) and schema[FAN].get("_bound") == REM,
            f"_bound={schema.get(FAN, {}).get('_bound')}",
        )
        ctx.check(
            "FAN _scheme merged from known_list",
            isinstance(schema.get(FAN), dict) and schema[FAN].get("_scheme") == "itho",
            f"_scheme={schema.get(FAN, {}).get('_scheme')}",
        )

        # DHW was NOT in schema — migration should have created it
        ctx.check(
            "DHW created in schema from known_list",
            isinstance(schema.get(DHW), dict) and schema[DHW].get("_class") == "DHW",
            f"DHW entry={schema.get(DHW)}",
        )
        ctx.check(
            "DHW _faked merged from known_list",
            isinstance(schema.get(DHW), dict) and schema[DHW].get("_faked") is True,
            f"_faked={schema.get(DHW, {}).get('_faked')}",
        )

        # CTL was in schema (with zones) — traits should be merged in
        ctx.check(
            "CTL _class merged from known_list (schema had no _class)",
            isinstance(schema.get(CTL), dict) and schema[CTL].get("_class") == "CTL",
            f"_class={schema.get(CTL, {}).get('_class')}",
        )
        # CTL zones should be preserved (not destroyed by migration)
        ctl_zones = schema.get(CTL, {}).get("zones", {})
        zones_info = (
            list(ctl_zones.keys()) if isinstance(ctl_zones, dict) else ctl_zones
        )
        ctx.check(
            "CTL zones preserved after migration",
            isinstance(ctl_zones, dict) and "00" in ctl_zones,
            f"zones={zones_info}",
        )

        # TRV was in schema with _alias="My TRV" — known_list alias="Kitchen"
        # should NOT overwrite (schema wins)
        trv_entry = schema.get("04:150000", {})
        ctx.check(
            "TRV _alias preserved from schema (known_list alias does NOT overwrite)",
            trv_entry.get("_alias") == "My TRV",
            f"_alias={trv_entry.get('_alias')}",
        )
        # But _class should be merged from known_list (schema didn't have it)
        ctx.check(
            "TRV _class merged from known_list",
            trv_entry.get("_class") == "TRV",
            f"_class={trv_entry.get('_class')}",
        )

        # HGI should be in schema with _class=HGI
        ctx.check(
            "HGI created in schema from known_list",
            isinstance(schema.get(hgi_id), dict)
            and schema[hgi_id].get("_class") == "HGI",
            f"HGI entry={schema.get(hgi_id)}",
        )

        # Check 4b: passive_scan should be enabled after migration.
        # The v2→v3 migration enables passive_scan by default because
        # enforce_known_list becomes always-on (PR 1033).
        advanced = options.get("advanced_features", {})
        ctx.check(
            "passive_scan is True after v2→v3 migration",
            advanced.get("passive_scan") is True,
            f"advanced_features={advanced}",
        )

        # Check 5: v2 backup was saved
        backup_result = subprocess.run(
            [
                "docker",
                "exec",
                inst.name,
                "cat",
                "/config/.storage/ramses_cc_migration_v2_backup",
            ],
            capture_output=True,
            text=True,
        )
        ctx.check(
            "v2 backup saved to .storage/ramses_cc_migration_v2_backup",
            backup_result.returncode == 0,
            f"exit={backup_result.returncode}",
        )
        if backup_result.returncode == 0:
            backup = json.loads(backup_result.stdout)
            # HA Store wraps data in an envelope: {version, minor_version, key, data}
            backup_data = backup.get("data", backup)
            ctx.check(
                "v2 backup has version=2",
                backup_data.get("version") == 2,
                f"version={backup_data.get('version')}",
            )
            backup_opts = backup_data.get("options", {})
            ctx.check(
                "v2 backup contains original known_list",
                "known_list" in backup_opts,
                f"keys={list(backup_opts.keys())}",
            )

        # Check 6: ramses_cc loaded and entities exist
        ctx.check(
            "ramses_cc loaded after migration",
            is_ramses_cc_loaded(),
            "",
        )

        schema_after = get_schema_retry(max_tries=3, delay=3)
        ctx.check(
            "Schema populated after migration",
            bool(schema_after),
            f"keys={list(schema_after.keys())[:5] if schema_after else 'empty'}",
        )

        # Check entities (non-critical — depends on transport being ready,
        # which may time out under parallel load)
        entities = get_entities(ctx.token)
        ramses_entities = [
            e
            for e in entities
            if e.get("entity_id", "").startswith(
                ("climate.", "number.", "sensor.", "switch.", "fan.")
            )
            and "ramses" in str(e.get("attributes", {}).get("attribution", "")).lower()
        ]
        if not ramses_entities:
            import re

            ramses_entities = [
                e for e in entities if re.search(r"\d{2}_\d{6}", e.get("entity_id", ""))
            ]
        if ramses_entities:
            ctx.check(
                "ramses_cc entities created after migration",
                True,
                f"found {len(ramses_entities)} entities",
            )
        else:
            print(
                "  WARN: no ramses_cc entities found"
                " (transport may not be ready — not a migration issue)"
            )

        # ── Step 4: Restore original config entry ───────────────────
        print("  Restoring original v3 config entry...")
        subprocess.run(["docker", "stop", inst.name], capture_output=True)
        ctx.wait(2, "for container to stop")

        # Read current config entry via docker exec (file is root-owned)
        r = subprocess.run(
            [
                "docker",
                "exec",
                inst.name,
                "cat",
                "/config/.storage/core.config_entries",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if r.returncode != 0:
            # Container might be stopped — read from host path
            try:
                with open(host_path) as f:
                    raw = f.read()
            except OSError:
                subprocess.run(["docker", "start", inst.name], capture_output=True)
                ctx.wait_for_ha_ready(timeout=30)
                return
        else:
            raw = r.stdout
        data = json.loads(raw)
        for i, e in enumerate(data["data"]["entries"]):
            if e["domain"] == "ramses_cc":
                e["options"] = original_options
                e["version"] = original_version
                data["data"]["entries"][i] = e
                break

        # Write via temporary container (root-owned .storage dir)
        import tempfile as _tf

        with _tf.NamedTemporaryFile(suffix=".json", mode="w", delete=False) as f:
            json.dump(data, f)
            tmp_path = f.name
        subprocess.run(
            [
                "docker",
                "run",
                "--rm",
                "-v",
                f"{inst.config_dir}:/config",
                "-v",
                f"{tmp_path}:/tmp/ce.json:ro",
                "python:3.12-slim",
                "python3",
                "-c",
                "import shutil, os; shutil.copyfile('/tmp/ce.json', "
                "'/config/.storage/core.config_entries'); "
                "os.chmod('/config/.storage/core.config_entries', 0o644)",
            ],
            capture_output=True,
            timeout=30,
        )
        os.unlink(tmp_path)

        subprocess.run(["docker", "start", inst.name], capture_output=True)
        ctx.wait_for_ha_ready(timeout=30, msg="for HA to restart after restore")
        ctx.wait_for_ramses_cc_loaded(
            timeout=30, msg="for ramses_cc to reload after restore"
        )
        wait_for_transport_ready(timeout=30)

        print("  Migration test complete, original config restored.")
