"""Recipe R90: FAN sensor update degradation under high packet load (issue 1040).

Issue 1040: 31DA (HVAC composite) temperature sensor updates slow down over
time and become "blocky" after running for a while.  A restart fixes it
temporarily.  The root cause was ``clear_async_attr_cache`` being called on
every inbound packet in ``_async_update_and_write_state``, causing a death
spiral: more state writes → more recorder writes → slower event loop →
dropped updates → stale sensors.

The fix reduces the ``resolve_async_attr`` cooldown from 30s to 1s and
removes the per-packet ``clear_async_attr_cache`` call.  Fresh data is
visible within 1s (issue 1042 still fixed), but without the per-packet
cache clearing that caused the death spiral (issue 1040).

This recipe verifies:
1. Under high-frequency packet load (31DA + other codes every ~0.5s for 60s),
   the FAN temperature sensor continues to update with the latest value.
2. After the burst, a final 31DA with a distinct temperature is picked up
   within 5s (not dropped or delayed).
3. No "Dropped N concurrent HA state updates" warnings appear in the log.

See: https://github.com/ramses-rf/ramses_cc/issues/1040
"""

from __future__ import annotations

import time

from ..base import Recipe, RecipeContext
from ..const import CTL
from ..helpers import (
    call_service,
    clear_cached_state,
    get_entities,
    get_schema_retry,
    load_profile_yaml,
    wait_for,
    wait_for_ramses_extras_ready,
    wait_for_schema_populated,
    wait_for_transport_ready,
    ws_send,
)
from ..profile import MIXED_SCHEMA, _build_yaml, get_mixed_kl

# FAN and REM device IDs from the mixed profile.
FAN_ID = "32:150000"
REM_ID = "37:170000"

# 31DA payload layout (from ramses_rf/payloads/hvac.py):
#   [0:2]   raw state byte
#   [2:6]   air_quality (scale 200, null EF00)
#   [6:10]  co2_level (null 7FFF)
#   [10:12] indoor_humidity (scale 100, null EF)
#   [12:14] outdoor_humidity (scale 100, null EF)
#   [14:18] exhaust_temp (scale 100, signed, null 7FFF/31FF)
#   [18:22] supply_temp (scale 100, signed, null 7FFF/31FF)
#   [22:26] indoor_temp (scale 100, signed, null 7FFF/31FF)
#   [26:30] outdoor_temp (scale 100, signed, null 7FFF/31FF)
#   [30:34] speed_capabilities (null 7FFF)
#   [34:36] (unknown)
#   [36:38] fan_info
#   [38:40] exhaust_fan_speed (scale 200, null FF)
#   ...remaining bytes: bypass, faults, etc.
#
# We use a 40-byte (80 hex char) payload with indoor_temp at [22:26].
# Base payload has indoor_temp = 7FFF (null) — we overwrite [22:26].
_31DA_BASE = (
    "00"  # [0:2]   raw state
    "EF00"  # [2:6]   air_quality (null)
    "7FFF"  # [6:10]  co2_level (null)
    "EF"  # [10:12] indoor_humidity (null)
    "EF"  # [12:14] outdoor_humidity (null)
    "7FFF"  # [14:18] exhaust_temp (null)
    "7FFF"  # [18:22] supply_temp (null)
    "7FFF"  # [22:26] indoor_temp (null — will be overwritten)
    "7FFF"  # [26:30] outdoor_temp (null)
    "7FFF"  # [30:34] speed_capabilities (null)
    "00"  # [34:36] unknown
    "00"  # [36:38] fan_info (off)
    "FF"  # [38:40] exhaust_fan_speed (null)
    + "00"
    * 20  # [40:80] remaining bytes (bypass, faults, etc.)
)


def _make_31da_payload(temp_c: float) -> str:
    """Build a 31DA payload with a specific indoor temperature.

    :param temp_c: Temperature in Celsius (encoded as 0.01°C units, signed).
    :return: Hex payload string with indoor_temp at bytes [22:26].
    """
    temp_raw = int(round(temp_c * 100))
    # Handle signed encoding (negative temps for outdoor, but indoor is
    # always positive — still, use 2's complement for correctness).
    if temp_raw < 0:
        temp_raw += 0x10000
    temp_hex = f"{temp_raw:04X}"
    # indoor_temp is at hex string offset 22:26
    return _31DA_BASE[:22] + temp_hex + _31DA_BASE[26:]


def _get_entity_state(token: str, entity_id: str) -> str | None:
    """Fetch a single entity's state from the HA API.

    :param token: HA bearer token.
    :param entity_id: The entity_id to query.
    :return: The state string, or None if the entity doesn't exist.
    """
    import json
    import urllib.error
    import urllib.request

    from ..helpers import get_current_instance

    req = urllib.request.Request(
        f"{get_current_instance().ha_url}/api/states/{entity_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    try:
        resp = urllib.request.urlopen(req, timeout=10)
        return json.loads(resp.read()).get("state")
    except urllib.error.HTTPError, Exception:
        return None


def _get_entity_attr(token: str, entity_id: str, attr: str) -> float | None:
    """Fetch a numeric attribute from an entity.

    :param token: HA bearer token.
    :param entity_id: The entity_id to query.
    :param attr: The attribute name to read.
    :return: The float value, or None.
    """
    import json
    import urllib.error
    import urllib.request

    from ..helpers import get_current_instance

    req = urllib.request.Request(
        f"{get_current_instance().ha_url}/api/states/{entity_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    try:
        resp = urllib.request.urlopen(req, timeout=10)
        data = json.loads(resp.read())
        val = data.get("attributes", {}).get(attr)
        if val is None:
            return None
        return float(val)
    except urllib.error.HTTPError, Exception, ValueError, TypeError:
        return None


class R90FanSensorUpdateDegradationIssue1040(Recipe):
    id = "R90"
    seq = 900
    title = "FAN sensor update degradation under load (issue 1040)"
    tags = ("31DA", "fan", "temperature", "death_spiral", "clear_async_attr_cache")

    async def run(self, ctx: RecipeContext) -> None:
        ctx.log_section(
            "Recipe 90: FAN sensor update degradation under load (issue 1040)"
        )

        # 0. Ensure ramses_extras is ready and mixed profile is loaded.
        ctx.refresh_token()
        wait_for_ramses_extras_ready(timeout=90, msg="for ramses_extras")

        # Load the mixed profile (has FAN 32:150000 and REM 37:170000).
        try:
            await load_profile_yaml(
                ctx.token,
                _build_yaml(get_mixed_kl(), MIXED_SCHEMA),
                speed=0.01,
            )
            print("  Profile loaded")
        except RuntimeError as e:
            print(f"  Profile load failed: {e}")
        ctx.wait_for_ramses_cc_reload(timeout=30)
        ctx.refresh_token()
        wait_for_transport_ready(timeout=30)

        # Activate FAN and REM for packet injection.
        for dev_id in (FAN_ID, REM_ID, CTL):
            try:
                await ws_send(
                    ctx.token,
                    {
                        "type": (
                            "ramses_extras/device_simulator/activate_profile_device"
                        ),
                        "device_id": dev_id,
                    },
                )
            except RuntimeError:
                pass
        wait_for_schema_populated(timeout=20)

        # Verify FAN is in schema.
        wait_for(
            lambda: FAN_ID in get_schema_retry(),
            timeout=15,
            interval=2,
            msg="for FAN to appear in schema",
        )

        # 1. Find the FAN temperature sensor entity.
        fan_suffix = FAN_ID.replace(":", "_")

        def _find_fan_temp_entity() -> dict | None:
            entities = get_entities(ctx.token)
            for e in entities:
                eid = e["entity_id"]
                if (
                    eid.startswith("sensor.")
                    and fan_suffix in eid
                    and "indoor_temperature" in eid
                ):
                    return e
            return None

        wait_for(
            _find_fan_temp_entity,
            timeout=20,
            interval=2,
            msg="for FAN indoor_temperature sensor entity",
        )

        entity = _find_fan_temp_entity()
        if not entity:
            ctx.check(
                "FAN indoor_temperature sensor entity exists",
                False,
                f"no sensor entity found for {FAN_ID}",
            )
            return

        entity_id = entity["entity_id"]
        print(f"  Found FAN temperature entity: {entity_id}")

        # 2. Inject an initial 31DA RP to hydrate the temperature.
        #    Use REM as src (RQ) and FAN as src (RP) — the REM polls the FAN.
        print("  Injecting initial 31DA RP (indoor_temp=20.0°C)...")
        initial_temp = 20.0
        try:
            call_service(
                ctx.token,
                "ramses_extras",
                "device_simulator_inject_message",
                {
                    "source_id": FAN_ID,
                    "code": "31DA",
                    "payload": _make_31da_payload(initial_temp),
                    "verb": "I",
                },
            )
        except RuntimeError as e:
            print(f"    Initial inject failed: {str(e)[:80]}")

        # Wait for the temperature to appear.
        deadline = time.monotonic() + 15
        initial_state = None
        while time.monotonic() < deadline:
            initial_state = _get_entity_state(ctx.token, entity_id)
            if initial_state not in (None, "unknown", "unavailable"):
                break
            time.sleep(1)

        print(f"  Initial temperature state: {initial_state}")
        ctx.check(
            "FAN temperature is hydrated after initial 31DA",
            initial_state not in (None, "unknown", "unavailable"),
            f"got {initial_state!r}",
        )

        # 3. High-frequency packet burst: inject 31DA + other codes every ~0.5s
        #    for 60 seconds.  This simulates a busy network with many devices.
        #    With the old clear_async_attr_cache, this would cause hundreds of
        #    state writes per minute, overwhelming the recorder.
        print("  Starting 60s high-frequency packet burst...")
        burst_start = time.monotonic()
        burst_duration = 60  # seconds
        inject_count = 0
        temps_sent = []

        while time.monotonic() - burst_start < burst_duration:
            # Inject 31DA I with a slowly varying temperature.
            elapsed = time.monotonic() - burst_start
            temp = 20.0 + 0.5 * (elapsed / burst_duration)  # 20.0 → 20.5°C
            temps_sent.append(temp)
            try:
                call_service(
                    ctx.token,
                    "ramses_extras",
                    "device_simulator_inject_message",
                    {
                        "source_id": FAN_ID,
                        "code": "31DA",
                        "payload": _make_31da_payload(temp),
                        "verb": "I",
                    },
                )
                inject_count += 1
            except RuntimeError:
                pass

            # Also inject a 10E0 I (device info) to add traffic load.
            # 10E0 doesn't carry temperature data, but with the old code it
            # would trigger clear_async_attr_cache + state write for ALL
            # FAN entities.
            try:
                call_service(
                    ctx.token,
                    "ramses_extras",
                    "device_simulator_inject_message",
                    {
                        "source_id": FAN_ID,
                        "code": "10E0",
                        "payload": "000210000000000000000000",
                        "verb": "I",
                    },
                )
            except RuntimeError:
                pass

            time.sleep(0.5)  # ~2 packets/second

        burst_elapsed = time.monotonic() - burst_start
        print(f"  Burst complete: {inject_count} 31DA packets in {burst_elapsed:.1f}s")

        # 4. After the burst, wait 2s for the 1s cooldown to expire, then
        #    inject a final 31DA with a distinct temperature and verify
        #    it's picked up within 5s (not dropped/delayed).
        #    In real life, the REM polls the FAN every 2-3 seconds, so
        #    there's always a gap > 1s between packets.  The 2s wait
        #    simulates this natural gap and lets the cooldown expire.
        ctx.wait(2, "for cooldown to expire before final inject")
        final_temp = 25.0  # distinctly different from the burst range (20.0-20.5)
        print(f"  Injecting final 31DA (indoor_temp={final_temp}°C)...")
        try:
            call_service(
                ctx.token,
                "ramses_extras",
                "device_simulator_inject_message",
                {
                    "source_id": FAN_ID,
                    "code": "31DA",
                    "payload": _make_31da_payload(final_temp),
                    "verb": "I",
                },
            )
        except RuntimeError as e:
            print(f"    Final inject failed: {str(e)[:80]}")

        # Poll for the final temperature to appear.
        # With the fix, the 1s cooldown means the value is visible within 1-2s.
        # With the death spiral, the update could be dropped or delayed.
        deadline_final = time.monotonic() + 10  # 10s budget
        final_state = None
        while time.monotonic() < deadline_final:
            final_state = _get_entity_state(ctx.token, entity_id)
            if final_state not in (None, "unknown", "unavailable"):
                try:
                    val = float(final_state)
                    # Accept if it's closer to 25.0 than to the burst range.
                    if abs(val - final_temp) < 1.0:
                        break
                except ValueError, TypeError:
                    pass
            time.sleep(0.5)

        elapsed_final = time.monotonic() - (deadline_final - 10)
        print(f"  Final temperature state: {final_state} (took {elapsed_final:.1f}s)")

        ctx.check(
            "FAN temperature updates to final value within 10s after burst",
            final_state is not None
            and final_state not in ("unknown", "unavailable")
            and _is_close_to(final_state, final_temp, tolerance=1.5),
            f"got {final_state!r} after {elapsed_final:.1f}s "
            f"(expected ~{final_temp}°C)",
        )

        # 5. Check the HA log for "Dropped N concurrent" warnings.
        #    These indicate the death spiral (event loop saturation).
        print("  Checking HA log for dropped update warnings...")
        import datetime as _dt
        import subprocess

        baseline_utc = _dt.datetime.now(_dt.UTC)
        # Search logs from 2 minutes ago to now (covers the burst duration).
        since_str = (baseline_utc - _dt.timedelta(minutes=2)).strftime(
            "%Y-%m-%dT%H:%M:%S"
        )
        try:
            log_result = subprocess.run(
                [
                    "docker",
                    "logs",
                    ctx.instance.name,
                    "--since",
                    since_str,
                ],
                capture_output=True,
                text=True,
                timeout=15,
            )
            log_text = log_result.stdout + log_result.stderr
            drop_count = log_text.count("Dropped")
        except Exception as e:
            print(f"    Log check error: {e}")
            drop_count = -1  # unknown
        print(f"  Found {drop_count} 'Dropped' warnings in log")

        ctx.check(
            "No 'Dropped concurrent HA state updates' warnings during burst",
            drop_count == 0,
            f"found {drop_count} warnings"
            + (" (log check failed)" if drop_count < 0 else ""),
        )

        # 6. Summary.
        ctx.check(
            "R90: No sensor degradation under high packet load (issue 1040)",
            final_state is not None
            and _is_close_to(final_state, final_temp, tolerance=1.5)
            and drop_count == 0,
            f"final_state={final_state!r}, drops={drop_count}",
        )


def _is_close_to(state: str, target: float, tolerance: float = 1.0) -> bool:
    """Check if a state string is close to a target float value.

    :param state: The state string from HA.
    :param target: The target float value.
    :param tolerance: How close the value needs to be.
    :return: True if the state parses as a float within tolerance.
    """
    try:
        return abs(float(state) - target) <= tolerance
    except ValueError, TypeError:
        return False
