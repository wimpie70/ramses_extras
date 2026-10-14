"""Recipe R149: zone demand veto drives valve to min position (issue 292).

Issue: a "veto" / inhibit signal must suppress a zone's ventilation while
active (e.g. an open window) — the zone is driven to its configured
``min_position`` even when positive demand is present, and normal demand
evaluation resumes when the veto clears.

Implementation (ramses_extras PR 298): ``ZoneDemandRegistry`` gained a
per-source veto store with ``set_veto``/``clear_veto``/``has_veto``; the
zone coordinator excludes vetoed zones from demand selection and drives
them to ``min_position``; ``set_zone_veto``/``clear_zone_veto`` services
expose the primitive.

This recipe exercises the full path end-to-end in ha-sim:

  1. A template cover (position backed by an input_number) is dropped
     into ``/config/packages/`` as the simulated zone valve, a
     ``custom_valve`` zone is injected into the extras config entry's
     ``features.zones`` section, and the worktree's veto code is synced
     into the container's ramses_extras if it predates the feature
  2. After a container restart: positive demand drives the valve to
     ``max_position``; an active veto drives it to ``min_position``
     *despite* the demand; clearing the veto returns it to the
     demand-derived target; a veto with no demands still suppresses the
     "open all" fallback; the coordinator reports the vetoed state
  3. Teardown restores the container's extras files, removes the
     package, and reverts the config entry

See: https://github.com/ramses-rf/ramses_extras/issues/292
     https://github.com/wimpie70/ramses_extras/pull/298
"""

from __future__ import annotations

import json
import shutil
import subprocess
import time
import urllib.request
from pathlib import Path
from typing import Any

from ..base import Recipe, RecipeContext
from ..helpers import (
    call_service,
    get_current_instance,
    wait_for,
    wait_for_entity_state,
    wait_for_ha_ready,
    wait_for_ramses_extras_ready,
    ws_send,
)

FAN_ID = "32:150000"
ZONE_ID = "sim_zone"
COVER_ENTITY = "cover.sim_zone_valve"
VETO_REASON = "vetoed"

_REPO = Path(__file__).resolve().parents[3]
_EXTRAS_SRC = _REPO / "custom_components" / "ramses_extras"
_PACKAGE_SRC = _REPO / "tools" / "ha_sim_test" / "ha_configs" / "zone_veto_package.yaml"
_PACKAGE_NAME = "zone_veto_testing.yaml"

# Files carrying the veto feature — synced into the container when the
# deployed extras predates it, restored again on teardown.
_PATCH_FILES = [
    "framework/helpers/zone_demand.py",
    "framework/helpers/zone_coordinator.py",
    "features/default/services.py",
    "services.yaml",
]


def _cover_position(token: str) -> int | None:
    """Return the sim valve's current_position attribute, or None."""
    req = urllib.request.Request(
        f"{get_current_instance().ha_url}/api/states/{COVER_ENTITY}",
        headers={"Authorization": f"Bearer {token}"},
    )
    try:
        state = json.loads(urllib.request.urlopen(req, timeout=5).read())
        pos = state.get("attributes", {}).get("current_position")
        return int(pos) if pos is not None else None
    except Exception:
        return None


def _wait_cover_position(token: str, expected: int, timeout: int = 45) -> bool:
    """Wait until the sim valve reports *expected* position.

    The actuation cycle is debounced (~1 s) but the sim runs a 100x
    profile — event-loop congestion can delay the timer well past that,
    so this needs a generous real-time floor.
    """
    return wait_for(
        lambda: _cover_position(token) == expected,
        timeout=timeout,
        interval=1,
        msg=f"for {COVER_ENTITY} position == {expected}",
        floor=45.0,
    )


def _docker(name: str, *args: str) -> None:
    """Run a docker command against the instance container."""
    subprocess.run(
        ["docker", *args, name],
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    )


def _cp_to_container(name: str, content: bytes, dst: str) -> None:
    """Copy bytes into the container (works while stopped, root-owned)."""
    import tempfile

    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        tmp.write(content)
        tmp_path = tmp.name
    try:
        subprocess.run(
            ["docker", "cp", tmp_path, f"{name}:{dst}"],
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
    finally:
        Path(tmp_path).unlink(missing_ok=True)


class R149ZoneDemandVetoIssue292(Recipe):
    id = "R149"
    seq = 1490
    title = "Zone demand veto drives valve to min (issue 292)"
    tags = ("292", "zones", "veto", "services")

    async def run(self, ctx: RecipeContext) -> None:
        ctx.log_section("Recipe 149: zone demand veto (issue 292)")

        inst = get_current_instance()
        config_dir = Path(inst.config_dir)
        extras_dst = config_dir / "custom_components" / "ramses_extras"
        package_dst = config_dir / "packages" / _PACKAGE_NAME
        entries_path = config_dir / ".storage" / "core.config_entries"

        if (
            not (_EXTRAS_SRC / "framework/helpers/zone_demand.py")
            .read_text()
            .count("def set_veto")
        ):
            ctx.check(
                "worktree carries the veto implementation",
                False,
                "zone_demand.py has no set_veto — run on feat/zone-demand-veto "
                "or a branch that includes it",
            )
            return

        file_backups: dict[Path, bytes] = {}
        entries_backup: bytes | None = None
        package_written = False
        container_name = inst.name
        container_stopped = False
        setup_ok = False

        # ── Setup: sync veto code, install sim valve, configure zone ──
        try:
            print(f"  Patching {container_name} for the veto test...")
            _docker(container_name, "stop")
            container_stopped = True

            for rel in _PATCH_FILES:
                src = _EXTRAS_SRC / rel
                dst = extras_dst / rel
                if dst.exists() and dst.read_bytes() == src.read_bytes():
                    continue  # already running this code
                if dst.exists():
                    file_backups[dst] = dst.read_bytes()
                shutil.copyfile(src, dst)
                print(f"    synced {rel}")

            shutil.copyfile(_PACKAGE_SRC, package_dst)
            package_written = True

            # .storage is root-owned — read on the host, write via
            # docker cp (which works on a stopped container).
            entries_backup = entries_path.read_bytes()
            entries = json.loads(entries_backup)
            zone_cfg = {
                "zone_id": ZONE_ID,
                "type": "custom_valve",
                "position_entity": COVER_ENTITY,
                # configure_zones_from_yaml requires inlet/outlet fields
                # even for custom_valve; they are unused by the adapter.
                "inlet_valve_entity": COVER_ENTITY,
                "outlet_valve_entity": COVER_ENTITY,
                "min_position": 0,
                "max_position": 100,
                "enabled": True,
            }
            patched_entry = False
            for entry in entries["data"]["entries"]:
                if entry.get("domain") != "ramses_extras":
                    continue
                options = entry.setdefault("options", {})
                features = options.setdefault("ramses_extras", {}).setdefault(
                    "features", {}
                )
                zones = features.setdefault("zones", {})
                fans = zones.setdefault("FANs", {})
                fans[FAN_ID] = [zone_cfg]
                patched_entry = True
            if not patched_entry:
                raise RuntimeError("no ramses_extras entry in core.config_entries")
            _cp_to_container(
                container_name,
                json.dumps(entries, indent=2).encode(),
                "/config/.storage/core.config_entries",
            )
            print(f"    zone '{ZONE_ID}' configured under FAN {FAN_ID}")

            _docker(container_name, "start")
            container_stopped = False
            setup_ok = True
        except Exception as err:  # noqa: BLE001 — surface as a check failure
            ctx.check("container patched for veto test", False, str(err))
            if container_stopped:
                try:
                    _docker(container_name, "start")
                except Exception:  # noqa: BLE001
                    pass

        # Teardown runs regardless of check outcomes — including a
        # partial setup, which must also restore the container.
        try:
            if not setup_ok:
                return
            if not ctx.wait_for_ha_ready(timeout=60):
                ctx.check("ha-sim back up after patch restart", False, "")
                return
            if not wait_for_ramses_extras_ready(timeout=60):
                ctx.check("ramses_extras ready after patch restart", False, "")
                return
            ctx.refresh_token()

            if not wait_for(
                lambda: _cover_position(ctx.token) is not None,
                timeout=30,
                interval=1,
                msg=f"for {COVER_ENTITY} to appear",
                floor=30.0,
            ):
                ctx.check(
                    "simulated zone valve cover created",
                    False,
                    f"{COVER_ENTITY} missing — package load failed?",
                )
                return
            ctx.check("simulated zone valve cover created", True)

            def _pos() -> int | None:
                return _cover_position(ctx.token)

            def _expect(expected: int, label: str) -> bool:
                ok = _wait_cover_position(ctx.token, expected)
                ctx.check(label, ok, f"position={_pos()}, expected={expected}")
                return ok

            # ── 1. Positive demand drives the valve to max_position ──
            call_service(
                ctx.token,
                "ramses_extras",
                "set_zone_demand",
                {"device_id": FAN_ID, "zone_id": ZONE_ID, "has_demand": True},
            )
            _expect(100, "positive demand drives valve to max_position")

            # ── 2. Veto overrides the demand → min_position ───────────
            call_service(
                ctx.token,
                "ramses_extras",
                "set_zone_veto",
                {"device_id": FAN_ID, "zone_id": ZONE_ID, "vetoed": True},
            )
            if _expect(0, "veto overrides demand, valve driven to min_position"):
                state = await ws_send(
                    ctx.token,
                    {
                        "type": "ramses_extras/get_zone_coordinator_state",
                        "fan_id": FAN_ID,
                    },
                )
                commands = (state.get("diagnostics") or {}).get(
                    "last_actuator_commands", {}
                )
                cmd = commands.get(ZONE_ID) or {}
                ctx.check(
                    "coordinator reports vetoed actuation command",
                    cmd.get("has_veto") is True
                    and VETO_REASON in str(cmd.get("reason", "")).lower(),
                    f"last_actuator_commands[{ZONE_ID}]={cmd!r}",
                )

            # ── 3. Clearing the veto resumes the demand-derived target ─
            call_service(
                ctx.token,
                "ramses_extras",
                "clear_zone_veto",
                {"device_id": FAN_ID, "zone_id": ZONE_ID},
            )
            _expect(100, "clearing veto restores demand target")

            # ── 4. Veto with no demand still suppresses open-all ──────
            call_service(
                ctx.token,
                "ramses_extras",
                "clear_zone_demand",
                {"device_id": FAN_ID, "zone_id": ZONE_ID},
            )
            call_service(
                ctx.token,
                "ramses_extras",
                "set_zone_veto",
                {"device_id": FAN_ID, "zone_id": ZONE_ID, "vetoed": True},
            )
            _expect(0, "veto suppresses the no-demand open-all fallback")

            # ── 5. Veto release returns to open-all ───────────────────
            call_service(
                ctx.token,
                "ramses_extras",
                "clear_zone_veto",
                {"device_id": FAN_ID, "zone_id": ZONE_ID},
            )
            _expect(100, "veto release returns to open-all position")

        finally:
            # ── Teardown: restore container to its pre-test state ──────
            print(f"  Restoring {container_name}...")
            try:
                _docker(container_name, "stop")
                for dst, content in file_backups.items():
                    dst.write_bytes(content)
                if package_written:
                    package_dst.unlink(missing_ok=True)
                if entries_backup is not None:
                    _cp_to_container(
                        container_name,
                        entries_backup,
                        "/config/.storage/core.config_entries",
                    )
                _docker(container_name, "start")
                wait_for_ha_ready(timeout=60)
                wait_for_ramses_extras_ready(timeout=60)
                print("  Container restored")
            except Exception as err:  # noqa: BLE001
                print(f"  WARNING: container restore failed: {err}")
