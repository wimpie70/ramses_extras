"""Recipe R140: sensor_control multi-sensor humidity aggregation (issue 276).

sensor_control supports a device-level ``aggregation`` strategy
(``first_valid``/``max``/``avg``/``weighted``) plus per-area ``weight``, and
area sensors with ``trigger_on_high_humidity`` produce a static high-RH
demand (no spike history needed).

This recipe wires two fake temperature+humidity pairs (bathroom +
kitchen) into the FAN's sensor_control config, enables
``humidity_control``, and verifies:

1. Dehumidifying stays off while all areas are below max RH.
2. Raising the bathroom RH above ``max_humidity`` turns dehumidifying on
   and attributes the trigger to the bathroom area
   (``active_trigger_source_ids``).
3. Dropping back below max clears the demand.
4. Raising the kitchen RH (with bathroom at baseline) triggers
   dehumidify again, attributed to the kitchen area — proving each
   configured source drives the decision independently.

The extras config entry lives in ``core.config_entries``, which HA only
reads at startup and overwrites on shutdown — so the recipe edits it on
the host while the container is stopped, then starts it again.  The
original options are restored at the end the same way.
"""

from __future__ import annotations

import json
import subprocess
import time
import urllib.request

from ..base import Recipe, RecipeContext
from ..const import FAN
from ..helpers import (
    call_service,
    container_log_timestamp,
    get_current_instance,
    is_ha_running,
    load_profile_yaml,
    log_lines_since,
    wait_for,
    wait_for_ramses_cc_loaded,
    wait_for_ramses_extras_ready,
    wait_for_schema_populated,
    wait_for_transport_ready,
    ws_send,
)
from ..profile import minimal_hvac_yaml

_BATH_TEMP = "sensor.sim_bathroom_temperature"
_BATH_HUM = "sensor.sim_bathroom_humidity"
_KITCH_TEMP = "sensor.sim_kitchen_temperature"
_KITCH_HUM = "sensor.sim_kitchen_humidity"
# Real FAN sensors — posted to so indoor/outdoor absolute humidity can be
# computed (the minimal HVAC profile does not generate temp/hum packets).
_FAN_IN_TEMP = "sensor.fan_32_150000_indoor_temperature"
_FAN_IN_HUM = "sensor.fan_32_150000_indoor_humidity"
_FAN_OUT_TEMP = "sensor.fan_32_150000_outdoor_temperature"
_FAN_OUT_HUM = "sensor.fan_32_150000_outdoor_humidity"
_DEHUMIDIFY_SWITCH = "switch.dehumidify_32_150000"
_DEHUMIDIFYING = "binary_sensor.dehumidifying_active_32_150000"


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
    """Write humidity_control + sensor_control config into the sim's
    core.config_entries (container must be stopped — the storage file is
    root-owned, so go through ``docker cp`` instead of the bind mount)."""
    inst = get_current_instance()
    tmp_path = "/tmp/r140_core.config_entries.json"
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
            store.setdefault("enabled_features", {})["humidity_control"] = enable
            store.setdefault("device_feature_matrix", {}).setdefault("32:150000", {})[
                "humidity_control"
            ] = enable
        root = opts.setdefault("ramses_extras", {})
        root.setdefault("enabled_features", {})["humidity_control"] = enable
        devices = (
            root.setdefault("features", {})
            .setdefault("sensor_control", {})
            .setdefault("devices", {})
        )
        if enable:
            devices["32:150000"] = {
                "sources": {},
                "aggregation": "max",
                "area_sensors": [
                    {
                        "area_id": "bathroom",
                        "enabled": True,
                        "temperature_entity": _BATH_TEMP,
                        "humidity_entity": _BATH_HUM,
                        "trigger_on_high_humidity": True,
                        "spike_rise_percent": 90.0,
                        "spike_window_minutes": 5,
                        "check_interval_minutes": 1,
                    },
                    {
                        "area_id": "kitchen",
                        "enabled": True,
                        "temperature_entity": _KITCH_TEMP,
                        "humidity_entity": _KITCH_HUM,
                        "trigger_on_high_humidity": True,
                        "spike_rise_percent": 90.0,
                        "spike_window_minutes": 5,
                        "check_interval_minutes": 1,
                    },
                ],
            }
        else:
            devices.pop("32:150000", None)
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


def _restore(ctx: RecipeContext) -> None:
    """Restore the original extras options (stop → revert → start)."""
    inst = get_current_instance()
    try:
        call_service(
            ctx.token,
            "switch",
            "turn_off",
            {"entity_id": _DEHUMIDIFY_SWITCH},
        )
    except Exception:  # noqa: BLE001 — best-effort cleanup
        pass
    ctx.log_monitor.capture_before_restart()
    subprocess.run(["docker", "stop", inst.name], check=True, timeout=60)
    _write_extras_options(enable=False)
    subprocess.run(["docker", "start", inst.name], check=True, timeout=60)
    ctx.log_monitor.reset_baseline()
    wait_for_ramses_cc_loaded(timeout=90, msg="for ramses_cc after restore")


class R140MultiSensorHumidityAggregation(Recipe):
    id = "R140"
    seq = 1400
    title = "sensor_control multi-sensor aggregation + static RH trigger (276)"
    tags = ("humidity", "sensor_control", "area_sensors", "aggregation")

    async def run(self, ctx: RecipeContext) -> None:
        """Verify multi-sensor aggregation and static high-RH triggers."""
        ctx.log_section("Recipe 140: multi-sensor humidity aggregation")

        ctx.refresh_token()
        _restart_container(ctx, stop_first=True)
        ctx.refresh_token()

        # Load a minimal HVAC profile so the FAN device is present
        try:
            await load_profile_yaml(ctx.token, minimal_hvac_yaml(), speed=0.01)
        except RuntimeError as err:
            ctx.check("HVAC profile loads", False, str(err)[:120])
            _restore(ctx)
            return
        ctx.wait_for_ramses_cc_reload(timeout=30)
        ctx.refresh_token()
        wait_for_transport_ready(timeout=30)

        # Activate the FAN so it answers the fan_high command that
        # dehumidify activation sends — otherwise the command round-trip
        # stalls and the demand never reaches the binary sensor.
        try:
            await ws_send(
                ctx.token,
                {
                    "type": ("ramses_extras/device_simulator/activate_profile_device"),
                    "device_id": FAN,
                },
            )
        except RuntimeError:
            pass
        wait_for_schema_populated(timeout=20)

        wait_for(
            lambda: (
                _get_state(ctx.token, _DEHUMIDIFY_SWITCH) is not None
                and _get_state(ctx.token, _DEHUMIDIFYING) is not None
            ),
            timeout=90,
            interval=3,
            msg="for humidity_control entities",
            floor=20.0,
        )
        entities_ready = (
            _get_state(ctx.token, _DEHUMIDIFY_SWITCH) is not None
            and _get_state(ctx.token, _DEHUMIDIFYING) is not None
        )
        ctx.check(
            "humidity_control entities created",
            entities_ready,
            f"missing {_DEHUMIDIFY_SWITCH}/{_DEHUMIDIFYING}",
        )
        if not entities_ready:
            _restore(ctx)
            return

        try:
            # --- baseline states -----------------------------------------
            # The minimal profile generates no temp/humidity packets for the
            # FAN, so the real ramses_cc sensors have no state.  Seed them so
            # the absolute-humidity sensors can compute (indoor ~9.4 g/m³,
            # outdoor ~5.6 g/m³).
            _set_entity_state(ctx.token, _FAN_IN_TEMP, "21.0")
            _set_entity_state(ctx.token, _FAN_IN_HUM, "50.0")
            _set_entity_state(ctx.token, _FAN_OUT_TEMP, "10.0")
            _set_entity_state(ctx.token, _FAN_OUT_HUM, "60.0")
            _set_entity_state(
                ctx.token,
                _BATH_TEMP,
                "22.0",
                {"device_class": "temperature", "unit_of_measurement": "°C"},
            )
            _set_entity_state(
                ctx.token,
                _BATH_HUM,
                "50.0",
                {"device_class": "humidity", "unit_of_measurement": "%"},
            )
            _set_entity_state(
                ctx.token,
                _KITCH_TEMP,
                "21.0",
                {"device_class": "temperature", "unit_of_measurement": "°C"},
            )
            _set_entity_state(
                ctx.token,
                _KITCH_HUM,
                "50.0",
                {"device_class": "humidity", "unit_of_measurement": "%"},
            )

            # Let the derived absolute-humidity sensors settle
            wait_for(
                lambda: (
                    (
                        _get_state(
                            ctx.token, "sensor.indoor_absolute_humidity_32_150000"
                        )
                        or {}
                    ).get("state")
                    not in (None, "unavailable", "unknown")
                ),
                timeout=30,
                interval=2,
                msg="for indoor_abs to compute",
                floor=5.0,
            )

            call_service(
                ctx.token,
                "switch",
                "turn_on",
                {"entity_id": _DEHUMIDIFY_SWITCH},
            )

            # Baseline: area below max RH → demand stays off
            off = wait_for(
                lambda: (
                    (_get_state(ctx.token, _DEHUMIDIFYING) or {}).get("state") == "off"
                ),
                timeout=45,
                interval=3,
                msg="for dehumidifying to stay off at baseline",
                floor=10.0,
            )
            ctx.check(
                "dehumidifying off while area RH <= max",
                off,
                f"state={(_get_state(ctx.token, _DEHUMIDIFYING) or {}).get('state')}",
            )

            # The humidity automation debounces device processing with a 2s
            # cooldown — let it expire so the RH state change below triggers
            # a fresh evaluation rather than being dropped.
            time.sleep(3)

            # --- raise the area humidity ---------------------------------
            _set_entity_state(
                ctx.token,
                _BATH_HUM,
                "75.0",
                {"device_class": "humidity", "unit_of_measurement": "%"},
            )
            # The sim_bathroom_* entities are POST-only (no entity-registry
            # entry), so the automation never registered a listener for them
            # and their state changes do not trigger an evaluation.  Nudge
            # the registered indoor humidity sensor to force one; the value
            # stays well below the configured maximum.
            _set_entity_state(ctx.token, _FAN_IN_HUM, "50.5")

            # The dehumidify demand queues a 22F1 set_fan_mode 'high'
            # command; in the sim the TX can sit behind queued parameter
            # polls for tens of seconds, so both waits need large floors.
            tx_baseline = container_log_timestamp()
            on = wait_for(
                lambda: (
                    (_get_state(ctx.token, _DEHUMIDIFYING) or {}).get("state") == "on"
                ),
                timeout=120,
                interval=3,
                msg="for dehumidifying on high area RH",
                floor=90.0,
            )
            ctx.check(
                "area RH > max triggers dehumidify (max aggregation / static trigger)",
                on,
                f"state={(_get_state(ctx.token, _DEHUMIDIFYING) or {}).get('state')}",
            )

            sent = wait_for(
                lambda: any(
                    " I --- 18:001234 32:150000 --:------ 22F1 003 000307" in line
                    for line in log_lines_since("packet_log.log*", tx_baseline)
                ),
                timeout=120,
                interval=3,
                msg="for 22F1 fan_high command",
                floor=45.0,
            )
            ctx.check(
                "area RH > max emits 22F1 fan_high demand",
                sent,
                "22F1 000307 packet not in packet log",
            )

            attrs = (_get_state(ctx.token, _DEHUMIDIFYING) or {}).get("attributes", {})
            ctx.check(
                "trigger attributed to bathroom area",
                "bathroom" in str(attrs.get("active_trigger_source_ids") or "")
                or "bathroom" in str(attrs.get("active_triggers") or "").lower(),
                f"attrs={attrs}",
            )

            # --- recovery -------------------------------------------------
            _set_entity_state(
                ctx.token,
                _BATH_HUM,
                "50.0",
                {"device_class": "humidity", "unit_of_measurement": "%"},
            )
            time.sleep(3)

            # Re-nudge the registered indoor humidity sensor on every poll:
            # the recovery eval may be dropped while a previous activation
            # run still holds the re-entrancy lock or the 2s cooldown, and
            # fake-entity state changes never trigger an eval on their own.
            nudge = {"v": 50.0}

            def _recovered() -> bool:
                nudge["v"] = 50.1 if nudge["v"] == 50.0 else 50.0
                _set_entity_state(ctx.token, _FAN_IN_HUM, str(nudge["v"]))
                return (_get_state(ctx.token, _DEHUMIDIFYING) or {}).get(
                    "state"
                ) == "off"

            cleared = wait_for(
                _recovered,
                timeout=120,
                interval=3,
                msg="for dehumidifying to clear after recovery",
                floor=60.0,
            )
            ctx.check(
                "dehumidifying clears when area RH recovers",
                cleared,
                f"state={(_get_state(ctx.token, _DEHUMIDIFYING) or {}).get('state')}",
            )

            # --- second source: kitchen triggers independently ---------
            # With bathroom back at baseline, raising the kitchen RH must
            # produce a new demand attributed to the kitchen area — the
            # "any zone spikes -> ventilate" behaviour from issue 276.
            _set_entity_state(
                ctx.token,
                _KITCH_HUM,
                "80.0",
                {"device_class": "humidity", "unit_of_measurement": "%"},
            )
            time.sleep(3)

            nudge_k = {"v": 50.0}

            def _kitchen_on() -> bool:
                nudge_k["v"] = 50.1 if nudge_k["v"] == 50.0 else 50.0
                _set_entity_state(ctx.token, _FAN_IN_HUM, str(nudge_k["v"]))
                return (_get_state(ctx.token, _DEHUMIDIFYING) or {}).get(
                    "state"
                ) == "on"

            on_kitchen = wait_for(
                _kitchen_on,
                timeout=120,
                interval=3,
                msg="for dehumidifying on high kitchen RH",
                floor=60.0,
            )
            ctx.check(
                "second area sensor (kitchen) triggers dehumidify",
                on_kitchen,
                f"state={(_get_state(ctx.token, _DEHUMIDIFYING) or {}).get('state')}",
            )

            attrs = (_get_state(ctx.token, _DEHUMIDIFYING) or {}).get("attributes", {})
            ctx.check(
                "trigger attributed to kitchen area",
                "kitchen" in str(attrs.get("active_trigger_source_ids") or "")
                or "kitchen" in str(attrs.get("active_triggers") or "").lower(),
                f"attrs={attrs}",
            )

            # --- final recovery ------------------------------------------
            _set_entity_state(
                ctx.token,
                _KITCH_HUM,
                "50.0",
                {"device_class": "humidity", "unit_of_measurement": "%"},
            )
            time.sleep(3)

            cleared2 = wait_for(
                _recovered,
                timeout=120,
                interval=3,
                msg="for dehumidifying to clear after kitchen recovery",
                floor=60.0,
            )
            ctx.check(
                "dehumidifying clears when kitchen RH recovers",
                cleared2,
                f"state={(_get_state(ctx.token, _DEHUMIDIFYING) or {}).get('state')}",
            )
        finally:
            _restore(ctx)
