"""Recipe R167: startup repair drops invalid composite schema keys (issue 1435).

Users already corrupted by earlier versions (top-level keys such as
``01:150000_00: {"_skipped": true}``) cannot set up at all: ramses_rf
schema validation fails with "does not match the expected pattern".

Startup repair (ramses_cc) drops such keys with a warning, persists the
repaired schema, and lets the config entry load.

This recipe simulates the corrupted-user state by injecting the invalid
key directly into the config entry storage, then reloading:

- the config entry must load (pre-repair: setup_error),
- the composite key must be gone from the schema,
- the zone/controller entries must survive,
- a repair persistent notification must exist,
- the repair must persist in the config entry storage.
"""

from __future__ import annotations

import json
import subprocess

from ..base import Recipe, RecipeContext
from ..const import CTL, HGI, TRV
from ..helpers import (
    _get_ramses_cc_entry_id,
    call_service,
    get_current_instance,
    get_schema_retry,
    is_ramses_cc_loaded,
    load_profile_yaml,
    wait_for_ha_ready,
    wait_for_ramses_cc_loaded,
    wait_for_transport_ready,
    ws_send,
)
from ..profile import _build_yaml

_ZONE = "00"
_ZONE_CHILD = f"{CTL}_{_ZONE}"


def _profile_yaml() -> str:
    kl = {
        HGI: {"class": "HGI"},
        CTL: {"class": "CTL"},
        TRV: {"class": "TRV"},
    }
    schema = {
        "_owner": "me",
        "main_tcs": CTL,
        CTL: {
            "_class": "CTL",
            "_owner": "me",
            "zones": {
                _ZONE: {
                    "_name": "Woonkamer",
                    "class": "radiator_valve",
                    "actuators": [TRV],
                },
            },
        },
        TRV: {"_class": "TRV", "_owner": "me"},
    }
    return _build_yaml(kl, schema)


def _docker_cp_corrupt() -> None:
    """Inject an invalid composite key into the stored config entry.

    Uses ``docker cp`` (works on a stopped container) because the
    container's config files are root-owned on the host.  Must be
    called while the container is STOPPED — a running HA keeps config
    entries in memory and flushes them over the file on graceful
    shutdown, erasing the injection.
    """
    name = get_current_instance().name
    tmp = "/tmp/r167_core.config_entries.json"
    cp_out = subprocess.run(
        [
            "docker",
            "cp",
            f"{name}:/config/.storage/core.config_entries",
            tmp,
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if cp_out.returncode != 0:
        raise RuntimeError(f"docker cp out failed: {cp_out.stderr[:120]}")
    with open(tmp) as f:
        data = json.load(f)
    n = 0
    for entry in data["data"]["entries"]:
        if entry["domain"] == "ramses_cc":
            entry["options"].setdefault("schema", {})[_ZONE_CHILD] = {"_skipped": True}
            n += 1
    if n == 0:
        raise RuntimeError("no ramses_cc config entry found in storage")
    with open(tmp, "w") as f:
        json.dump(data, f)
    cp_in = subprocess.run(
        [
            "docker",
            "cp",
            tmp,
            f"{name}:/config/.storage/core.config_entries",
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if cp_in.returncode != 0:
        raise RuntimeError(f"docker cp in failed: {cp_in.stderr[:120]}")


def _stored_schema_keys() -> list[str]:
    """Return the sorted top-level keys of the stored config-entry schema."""
    name = get_current_instance().name
    tmp = "/tmp/r167_core.config_entries.keys.json"
    cp_out = subprocess.run(
        [
            "docker",
            "cp",
            f"{name}:/config/.storage/core.config_entries",
            tmp,
        ],
        capture_output=True,
        timeout=30,
    )
    if cp_out.returncode != 0:
        return []
    try:
        with open(tmp) as f:
            data = json.load(f)
    except OSError, ValueError:
        return []
    for entry in data["data"]["entries"]:
        if entry["domain"] == "ramses_cc":
            return sorted(entry["options"].get("schema", {}).keys())
    return []


async def _repair_notification_present(token: str) -> bool:
    """Query live persistent notifications for the schema_repair slug.

    Notifications are kept in memory and only flushed to .storage on
    shutdown, so this must go through the websocket API.
    """
    try:
        result = await ws_send(token, {"type": "persistent_notification/get"})
    except RuntimeError:
        return False
    # Shape varies by HA version (dict keyed by id, list, or nested) —
    # a serialised substring match is robust to all of them.
    return "schema_repair" in json.dumps(result)


class R167StartupRepairCompositeKeys(Recipe):
    id = "R167"
    seq = 1670
    title = "Startup repair drops invalid composite schema keys (issue 1435)"
    tags = ("schema", "startup", "issue-1435")

    async def run(self, ctx: RecipeContext) -> None:
        ctx.log_section("Recipe 167: startup repair of composite keys (issue 1435)")

        # 1. Load a clean profile.
        print("  Loading clean profile...")
        try:
            await load_profile_yaml(
                ctx.token,
                _profile_yaml(),
                speed=0.01,
                preload_schema=True,
                reload_ramses=True,
            )
        except RuntimeError as e:
            ctx.check("profile loaded", False, detail=str(e)[:200])
            return
        ctx.wait_for_ramses_cc_reload(timeout=30)
        ctx.refresh_token()
        wait_for_transport_ready(timeout=30)
        ctx.wait_for_schema_stable(timeout=15)

        schema = get_schema_retry()
        ctx.check(
            "precondition: clean schema loaded",
            CTL in schema and _ZONE_CHILD not in schema,
            f"keys={sorted(schema)[:8]}",
        )

        # 2. Simulate the already-corrupted user.  HA keeps config
        #    entries in memory and flushes them over the storage file on
        #    graceful shutdown, so the injection must happen while the
        #    container is STOPPED: stop -> corrupt -> start.  The start
        #    then re-reads .storage exactly like a cold boot of an
        #    already-corrupted user's system.  Pre-repair this fails
        #    ramses_rf schema validation and the entry ends in
        #    setup_error; post-repair it loads.
        print("  Stopping container, corrupting schema, starting again...")
        ctx.log_monitor.capture_before_restart("R167 pre-restart")
        name = get_current_instance().name
        subprocess.run(["docker", "stop", name], capture_output=True, timeout=120)
        try:
            _docker_cp_corrupt()
        except RuntimeError as e:
            subprocess.run(["docker", "start", name], capture_output=True)
            ctx.check("corruption injected", False, str(e)[:150])
            return

        keys = _stored_schema_keys()
        ctx.check(
            "precondition: corruption present in storage",
            _ZONE_CHILD in keys,
            f"stored keys={keys}",
        )

        print("  Starting container with corrupted schema...")
        subprocess.run(["docker", "start", name], capture_output=True, timeout=60)
        wait_for_ha_ready(timeout=90)
        ctx.refresh_token()
        wait_for_ramses_cc_loaded(timeout=60)

        ctx.check(
            "ramses_cc loads despite corrupted schema (startup repair)",
            is_ramses_cc_loaded(),
            "config entry not in loaded state",
        )

        # 4. The invalid key must be gone and valid content preserved.
        ctx.wait_for_schema_stable(timeout=15)
        schema = get_schema_retry()
        ctx.check(
            "composite key dropped from live schema",
            _ZONE_CHILD not in schema,
            f"keys with '_'={[k for k in schema if '_' in str(k)]}",
        )
        zone = schema.get(CTL, {}).get("zones", {}).get(_ZONE, {})
        ctx.check(
            "controller and zone survive the repair",
            CTL in schema and bool(zone),
            f"ctl present={CTL in schema} zone={zone}",
        )

        # 5. The repair must be persisted — storage no longer corrupted.
        keys = _stored_schema_keys()
        ctx.check(
            "repair persisted in config entry storage",
            _ZONE_CHILD not in keys and CTL in keys,
            f"stored keys={keys}",
        )

        # 6. The user is told via a persistent notification.
        ctx.check(
            "schema_repair persistent notification created",
            await _repair_notification_present(ctx.token),
            "schema_repair not in live persistent notifications",
        )

        # 7. A second reload must be a no-op: still loads, schema stable.
        print("  Reloading again (repair must be idempotent)...")
        entry_id = _get_ramses_cc_entry_id()
        if not entry_id:
            ctx.check("ramses_cc config entry found", False, "no entry_id")
            return
        try:
            call_service(
                ctx.token,
                "homeassistant",
                "reload_config_entry",
                {"entry_id": entry_id},
            )
        except RuntimeError:
            pass
        ctx.wait_for_ramses_cc_reload(timeout=30)
        ctx.refresh_token()
        ctx.check(
            "entry still loads after second reload (idempotent)",
            is_ramses_cc_loaded(),
            "config entry not in loaded state",
        )
