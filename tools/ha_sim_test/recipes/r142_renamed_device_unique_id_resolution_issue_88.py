"""Recipe R142: renamed-device entities resolve via unique_id (issue 88).

With ``has_entity_name=True``, ramses_cc entity_ids are derived from the
device + entity *names* — renaming the FAN (e.g. "Orcon HRC400 WTW")
yields ``sensor.orcon_hrc400_wtw_indoor_temperature`` and no
device-id-based template can match it.  Every resolution path
(entity-id fallbacks, sensor_control's internal mappings, abs-humidity
listeners) then points at an entity that does not exist: temp_control
sat in ``waiting_for_sensors`` while the FAN page showed live values.

This recipe reproduces that state by renaming the FAN's indoor-temp
sensor and param_75 number to name-derived entity_ids via
``config/entity_registry/update`` (the unique_id, e.g.
``32:150000-indoor_temp``, is untouched — exactly like a real rename),
then verifies:

1. ``ramses_extras/get_entity_mappings`` resolves ``indoor_temp`` /
   ``comfort_temp`` (and the sensor_control overlay key
   ``indoor_temperature``) to the renamed entity_ids.
2. temp_control leaves ``waiting_for_sensors``/``waiting_for_comfort_temp``
   and reaches a real mode (``idle``) with the switch on.

The extras config entry lives in ``core.config_entries``, which HA only
reads at startup and overwrites on shutdown — so the recipe edits it on
the host while the container is stopped, then starts it again.  The
original options and entity_ids are restored at the end the same way.
"""

from __future__ import annotations

import json
import subprocess
import time
import urllib.request
from copy import deepcopy

from ..base import Recipe, RecipeContext
from ..const import FAN, REM
from ..helpers import (
    call_service,
    get_current_instance,
    is_ha_running,
    load_profile_yaml,
    spawn_thread,
    wait_for,
    wait_for_ramses_cc_loaded,
    wait_for_ramses_extras_ready,
    wait_for_schema_populated,
    wait_for_transport_ready,
    ws_send,
)
from ..profile import MIXED_SCHEMA, _build_yaml, get_mixed_kl

_FEATURES = ("temp_control", "sensor_control")
_DEVICE_KEY = "32:150000"

_TEMP_UID = f"{FAN}-indoor_temp"
_PARAM75_UID = f"{FAN}-param_75"
_RENAMED_TEMP = "sensor.orcon_hrc400_wtw_indoor_temperature"
_RENAMED_PARAM75 = "number.orcon_hrc400_wtw_comfort_temperature_degc"
_TEMP_SWITCH = "switch.temp_control_32_150000"
_STATUS = "sensor.temp_control_status_32_150000"


def _set_entity_state(
    token: str, entity_id: str, state: str, attributes: dict | None = None
) -> None:
    """Create/overwrite a state via the REST API (sim-only fake sensors)."""
    url = f"{get_current_instance().ha_url}/api/states/{entity_id}"
    body = json.dumps({"state": state, "attributes": attributes or {}}).encode()
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    urllib.request.urlopen(req, timeout=15).read()


def _get_state(token: str, entity_id: str) -> dict | None:
    """GET /api/states/<entity_id> → {state, attributes} or None."""
    url = f"{get_current_instance().ha_url}/api/states/{entity_id}"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    try:
        return json.loads(urllib.request.urlopen(req, timeout=10).read())
    except Exception:
        return None


def _write_extras_options(enable: bool) -> None:
    """Write temp_control + sensor_control config into the sim's
    core.config_entries (container must be stopped — the storage file is
    root-owned, so go through ``docker cp`` instead of the bind mount)."""
    inst = get_current_instance()
    tmp_path = "/tmp/r142_core.config_entries.json"
    subprocess.run(
        [
            "docker",
            "cp",
            f"{inst.name}:/config/.storage/core.config_entries",
            tmp_path,
        ],
        check=True,
        timeout=30,
    )
    with open(tmp_path) as fh:
        doc = json.load(fh)
    for entry in doc["data"]["entries"]:
        if entry["domain"] != "ramses_extras":
            continue
        opts = entry.setdefault("options", {})
        data = entry.setdefault("data", {})
        for store in (opts, data):
            for feature in _FEATURES:
                store.setdefault("enabled_features", {})[feature] = enable
                store.setdefault("device_feature_matrix", {}).setdefault(
                    _DEVICE_KEY, {}
                )[feature] = enable
        root = opts.setdefault("ramses_extras", {})
        for feature in _FEATURES:
            root.setdefault("enabled_features", {})[feature] = enable
        if not enable:
            root.get("features", {}).get("sensor_control", {}).get("devices", {}).pop(
                _DEVICE_KEY, None
            )
    with open(tmp_path, "w") as fh:
        json.dump(doc, fh)
    subprocess.run(
        [
            "docker",
            "cp",
            tmp_path,
            f"{inst.name}:/config/.storage/core.config_entries",
        ],
        check=True,
        timeout=30,
    )


def _restart_container(ctx: RecipeContext, *, stop_first: bool = False) -> None:
    """Restart ha-sim and wait for HA + ramses_cc + extras to be ready."""
    inst = get_current_instance()
    ctx.log_monitor.capture_before_restart()
    if stop_first:
        subprocess.run(["docker", "stop", inst.name], check=True, timeout=60)
        _write_extras_options(enable=True)
        subprocess.run(["docker", "start", inst.name], check=True, timeout=60)
    else:
        subprocess.run(["docker", "restart", inst.name], check=True, timeout=60)
    ctx.log_monitor.reset_baseline()

    t0 = time.monotonic()
    while time.monotonic() - t0 < 150:
        try:
            ctx.refresh_token()
        except Exception:  # noqa: BLE001 — API still restarting
            pass
        if is_ha_running(ctx.token):
            break
        time.sleep(2)

    wait_for_ramses_cc_loaded(timeout=90, msg="for ramses_cc after restart")
    wait_for_ramses_extras_ready(timeout=120)


def _fire_and_forget(token: str, domain: str, service: str, data: dict) -> None:
    """Call a service without waiting for the response (update_fan_params
    blocks on the transport's TX echo; the registry is what matters)."""

    def _call() -> None:
        try:
            call_service(token, domain, service, data, timeout=15, retries=1)
        except Exception:  # noqa: BLE001 — packet/entity is the real check
            pass

    spawn_thread(_call)


async def _registry_entries(token: str) -> list[dict]:
    resp = await ws_send(token, {"type": "config/entity_registry/list"})
    return resp if isinstance(resp, list) else resp.get("entities", [])


async def _find_entity_id(token: str, unique_id: str) -> str | None:
    for entry in await _registry_entries(token):
        if entry.get("unique_id") == unique_id:
            return str(entry.get("entity_id"))
    return None


async def _restore(ctx: RecipeContext, renames: dict[str, str]) -> None:
    """Undo the entity renames, then restore the original extras options."""
    inst = get_current_instance()
    try:
        call_service(ctx.token, "switch", "turn_off", {"entity_id": _TEMP_SWITCH})
    except Exception:  # noqa: BLE001 — best-effort cleanup
        pass
    for new_id, old_id in renames.items():
        try:
            await ws_send(
                ctx.token,
                {
                    "type": "config/entity_registry/update",
                    "entity_id": new_id,
                    "new_entity_id": old_id,
                },
            )
        except Exception:  # noqa: BLE001 — best-effort cleanup
            pass
    ctx.log_monitor.capture_before_restart()
    subprocess.run(["docker", "stop", inst.name], check=True, timeout=60)
    _write_extras_options(enable=False)
    subprocess.run(["docker", "start", inst.name], check=True, timeout=60)
    ctx.log_monitor.reset_baseline()
    wait_for_ramses_cc_loaded(timeout=90, msg="for ramses_cc after restore")


class R142RenamedDeviceUniqueIdResolution(Recipe):
    id = "R142"
    seq = 1420
    title = "renamed FAN entities resolve via unique_id (issue 88)"
    tags = ("fan", "temp_control", "sensor_control", "entity_registry", "rename")

    async def run(self, ctx: RecipeContext) -> None:
        """Rename FAN entities to name-derived ids; verify resolution."""
        ctx.log_section("Recipe 142: renamed-device unique_id resolution")

        ctx.refresh_token()
        _restart_container(ctx, stop_first=True)
        ctx.refresh_token()

        # Orcon HVAC profile (FAN + bound faked REM, like R138) so the
        # sim FAN answers 31DA/2411 traffic and param entities appear.
        schema = deepcopy(MIXED_SCHEMA)
        schema[FAN] = {
            **schema[FAN],
            "_bound": [REM],
            "_class": "FAN",
            "_scheme": "orcon",
            "remotes": [REM],
        }
        schema[REM] = {
            **schema[REM],
            "_bound": FAN,
            "_class": "REM",
            "_faked": True,
            "_scheme": "orcon",
        }
        try:
            await load_profile_yaml(
                ctx.token,
                _build_yaml(get_mixed_kl(), schema),
                speed=0.01,
            )
        except RuntimeError as err:
            ctx.check("Orcon HVAC profile loads", False, str(err)[:120])
            await _restore(ctx, {})
            return
        ctx.wait_for_ramses_cc_reload(timeout=30)
        ctx.refresh_token()
        wait_for_transport_ready(timeout=30)

        for device_id in (FAN, REM):
            try:
                await ws_send(
                    ctx.token,
                    {
                        "type": (
                            "ramses_extras/device_simulator/activate_profile_device"
                        ),
                        "device_id": device_id,
                    },
                )
            except RuntimeError:
                pass
        wait_for_schema_populated(timeout=20)

        # Param entities are created on 2411 RP traffic — force a sweep
        # if param_75 is not in the registry yet.
        if not await _find_entity_id(ctx.token, _PARAM75_UID):
            _fire_and_forget(
                ctx.token,
                "ramses_cc",
                "update_fan_params",
                {"device_id": [FAN]},
            )

        t0 = time.monotonic()
        orig_temp: str | None = None
        orig_param75: str | None = None
        while time.monotonic() - t0 < 120 and not (orig_temp and orig_param75):
            orig_temp = orig_temp or await _find_entity_id(ctx.token, _TEMP_UID)
            orig_param75 = orig_param75 or await _find_entity_id(
                ctx.token, _PARAM75_UID
            )
            if not (orig_temp and orig_param75):
                time.sleep(3)

        ctx.check(
            "FAN entities present (indoor_temp + param_75 unique_ids)",
            bool(orig_temp) and bool(orig_param75),
            f"temp={orig_temp} param75={orig_param75}",
        )
        if not (orig_temp and orig_param75):
            await _restore(ctx, {})
            return

        renames: dict[str, str] = {}
        try:
            # Rename to name-derived entity_ids — mirrors a device rename:
            # entity_id changes, unique_id stays "32:150000-<key>".
            for old_id, new_id in (
                (orig_temp, _RENAMED_TEMP),
                (orig_param75, _RENAMED_PARAM75),
            ):
                if old_id == new_id:
                    continue
                await ws_send(
                    ctx.token,
                    {
                        "type": "config/entity_registry/update",
                        "entity_id": old_id,
                        "new_entity_id": new_id,
                    },
                )
                renames[new_id] = old_id

            # --- 1) entity_mappings resolve the renamed ids --------------
            resp = await ws_send(
                ctx.token,
                {
                    "type": "ramses_extras/get_entity_mappings",
                    "feature_id": "temp_control",
                    "device_id": FAN,
                },
            )
            mappings = resp.get("mappings", {}) if isinstance(resp, dict) else {}
            ctx.check(
                "get_entity_mappings: indoor_temp resolves via unique_id",
                mappings.get("indoor_temp") == _RENAMED_TEMP,
                f"got {mappings.get('indoor_temp')}",
            )
            ctx.check(
                "get_entity_mappings: comfort_temp resolves via unique_id",
                mappings.get("comfort_temp") == _RENAMED_PARAM75,
                f"got {mappings.get('comfort_temp')}",
            )
            # sensor_control overlay path (only when feature enabled)
            overlay_id = mappings.get("indoor_temperature")
            ctx.check(
                "get_entity_mappings: sensor_control overlay resolves renamed id",
                overlay_id in (None, _RENAMED_TEMP),
                f"got {overlay_id}",
            )

            # --- 2) temp_control evaluates with renamed entities ---------
            # Seed the renamed entities (the minimal/orcon profile may not
            # have produced values yet) then flip the switch — the
            # switch.* listener pattern triggers an evaluation.
            _set_entity_state(ctx.token, _RENAMED_TEMP, "21.0")
            _set_entity_state(ctx.token, _RENAMED_PARAM75, "21.0")

            switch_ready = wait_for(
                lambda: _get_state(ctx.token, _TEMP_SWITCH) is not None,
                timeout=60,
                interval=3,
                msg="for temp_control switch",
                floor=10.0,
            )
            ctx.check(
                "temp_control switch entity created",
                switch_ready,
                f"missing {_TEMP_SWITCH}",
            )
            if not switch_ready:
                return  # _restore runs via finally

            call_service(ctx.token, "switch", "turn_on", {"entity_id": _TEMP_SWITCH})

            healthy = wait_for(
                lambda: (
                    (_get_state(ctx.token, _STATUS) or {}).get("state")
                    in ("idle", "cooling", "heating_retention")
                ),
                timeout=120,
                interval=3,
                msg="for temp_control to leave waiting_for_sensors",
                floor=30.0,
            )
            ctx.check(
                "temp_control evaluates (status leaves waiting_*)",
                healthy,
                f"state={(_get_state(ctx.token, _STATUS) or {}).get('state')}",
            )
        finally:
            await _restore(ctx, renames)
