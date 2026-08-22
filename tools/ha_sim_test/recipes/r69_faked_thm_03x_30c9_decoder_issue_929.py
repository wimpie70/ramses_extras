"""Recipe R69: Faked 03: THM 30C9 decoder acceptance (issue 929).

Regression guard for the fix in ramses_rf that ensures 30C9 packets from
non-controller devices (03:/04:/12:) with a non-zero zone_idx are accepted
by the decoder.

Before the fix, the 0xAB guard in ``_pkt_idx`` rejected any non-zero idx
from non-controller devices.  Faked 03: THM sensors (introduced in 0.59.2
via commit 5b9abbe4) send 30C9 with the parent zone's idx, which triggered
the guard and caused ``PacketPayloadInvalid: Packet idx is 0X, but expecting
no idx (00) (0xAB)``.  The fake command failed entirely and all zones showed
"waiting for sync".

This recipe loads a profile with a 03: device configured as ``class: THM,
faked: true``, bound to a CTL zone, calls ``put_room_temp`` on the sensor
entity, and verifies the 30C9 packet is transmitted (not rejected by the
decoder).

See: https://github.com/ramses-rf/ramses_cc/issues/929
"""

from __future__ import annotations

import subprocess

from ..base import Recipe, RecipeContext
from ..const import CTL
from ..helpers import (
    call_service,
    clear_cached_state,
    get_current_instance,
    get_entities,
    load_profile_yaml,
    wait_for,
    wait_for_schema_populated,
    wait_for_transport_ready,
    ws_send,
)
from ..profile import minimal_ctl_zone_yaml


class R69FakedThm03x30c9DecoderIssue929(Recipe):
    id = "R69"
    seq = 690
    title = "Faked 03: THM 30C9 decoder acceptance (issue 929)"

    async def run(self, ctx: RecipeContext) -> None:
        ctx.log_section("Recipe 69: Faked 03: THM 30C9 decoder acceptance (issue 929)")

        # 0. Clear cached state from previous recipes.
        print("  Stopping ha-sim and clearing cached state...")
        clear_cached_state(ctx.log_monitor, label="R69 pre-clean")
        ctx.wait_for_ha_ready(timeout=30)
        ctx.log_monitor.reset_baseline()
        ctx.refresh_token()
        ctx.wait_for_ramses_cc_loaded(timeout=25)

        # 1. Load a minimal profile with a 03: device as faked THM sensor.
        #    Use 03:155003 — a 03: (analog_thermostat) device that is NOT
        #    a controller type, so _has_ctl is False and the 0xAB guard
        #    would fire before the fix.
        sensor_id = "03:155003"
        zone_idx = "03"
        fake_temp = 22.0

        # Minimal profile: CTL + faked THM as zone 03 sensor (3 devices
        # instead of the full 19-device mixed profile)
        yaml_text = minimal_ctl_zone_yaml(
            zone_idx=zone_idx,
            sensor_id=sensor_id,
        )
        # Add faked: True to the sensor's known_list entry
        import yaml as _yaml

        profile = _yaml.safe_load(yaml_text)
        profile["known_list"][sensor_id]["faked"] = True
        yaml_text = _yaml.dump(profile, default_flow_style=False)

        print(f"  Loading minimal profile with {sensor_id} faked (zone {zone_idx})...")
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
        # Wait for the MQTT transport to reconnect after the reload,
        # otherwise injected packets are silently dropped.
        wait_for_transport_ready(timeout=30)

        # Activate CTL for heartbeats
        try:
            await ws_send(
                ctx.token,
                {
                    "type": "ramses_extras/device_simulator/activate_profile_device",
                    "device_id": CTL,
                },
            )
        except RuntimeError:
            pass
        from ..helpers import get_schema_retry

        wait_for_schema_populated(timeout=15)

        # 2. Find the temperature sensor entity for 03:155003
        entities = get_entities(ctx.token)
        sensor_eid = None
        for e in entities:
            eid = e["entity_id"]
            if sensor_id.replace(":", "_") in eid and eid.startswith("sensor."):
                attrs = e.get("attributes", {})
                if attrs.get("device_class") == "temperature":
                    sensor_eid = eid
                    break

        ctx.check(
            f"temperature sensor entity found for {sensor_id}",
            sensor_eid is not None,
            "no temperature sensor entity found",
        )

        if not sensor_eid:
            return

        print(f"  Found sensor entity: {sensor_eid}")

        # 3. Call put_room_temp on the entity.
        #    Before the fix, this would raise PacketPayloadInvalid and the
        #    service call would fail with an HTTP 500 error mentioning
        #    "Packet idx is 03, but expecting no idx (00) (0xAB)".
        #    After the fix, the 30C9 packet is accepted and transmitted.
        #    In the simulator, no echo comes back so the service may time
        #    out, but the 30C9 packet IS transmitted and appears in the log.
        print(
            f"  Calling put_room_temp on {sensor_eid} "
            f"(zone {zone_idx}, {fake_temp}C)..."
        )
        import time as _time

        t0 = _time.time()
        try:
            call_service(
                ctx.token,
                "ramses_cc",
                "put_room_temp",
                {
                    "entity_id": sensor_eid,
                    "temperature": fake_temp,
                },
            )
            print("  put_room_temp service call succeeded")
        except RuntimeError as e:
            elapsed = _time.time() - t0
            err_str = str(e)
            # The key check: the error must NOT be PacketPayloadInvalid
            # (0xAB guard). A timeout is expected (no echo in simulator).
            ctx.check(
                "put_room_temp did not raise PacketPayloadInvalid (0xAB guard)",
                "0xAB" not in err_str and "expecting no idx" not in err_str,
                f"got 0xAB error: {err_str[:80]}",
            )
            print(
                f"  put_room_temp returned error after {elapsed:.1f}s "
                f"(expected timeout): {err_str[:60]}"
            )

        ctx.wait(5, "for 30C9 packet to appear in log", floor=2.0)

        # 4. Read the HA log for the 30C9 packet from our faked 03: device.
        #    Use "from ramses_rf" to match only the actual packet line,
        #    not the simulator's internal debug log (e.g. "Simulator
        #    received I frame: ...").
        def _30c9_in_log() -> bool:
            result = subprocess.run(
                [
                    "docker",
                    "exec",
                    get_current_instance().name,
                    "bash",
                    "-c",
                    f"grep 'Simulator received from ramses_rf.*{sensor_id}.*30C9' "
                    "/config/home-assistant.log | tail -10",
                ],
                capture_output=True,
                text=True,
            )
            return bool(result.stdout.strip())

        wait_for(
            _30c9_in_log,
            timeout=15,
            interval=2,
            msg="for 30C9 packet to appear in HA log",
            floor=3.0,
        )
        result = subprocess.run(
            [
                "docker",
                "exec",
                get_current_instance().name,
                "bash",
                "-c",
                f"grep 'Simulator received from ramses_rf.*{sensor_id}.*30C9' "
                "/config/home-assistant.log | tail -10",
            ],
            capture_output=True,
            text=True,
        )
        tx_lines: list[str] = [
            line.strip() for line in result.stdout.splitlines() if line.strip()
        ]

        ctx.check(
            "30C9 packet found in HA log (decoder accepted it)",
            len(tx_lines) > 0,
            "no 30C9 packets found — decoder likely rejected the packet (0xAB guard)",
        )

        if not tx_lines:
            return

        print(f"  Found {len(tx_lines)} 30C9 packet(s):")
        for line in tx_lines:
            print(f"    {line}")

        # 5. Verify the payload format.
        #    30C9 payload format: {zone_idx}{temperature_hex}
        #    For standard evohome CTL zones (RAD/ELE/MIX/VAL), the zone_idx
        #    must be "00" — only UFH zones use the parent's zone index.
        #    The old bug (commit 5b9abbe4) stamped the parent zone index for
        #    ALL zones, causing "Packet idx is 0X, but expecting no idx (00)"
        #    errors (issue 929).  The fix restricts the parent index to UFH
        #    zones only.
        last_tx = tx_lines[-1]
        parts = last_tx.split()
        payload = parts[-1] if parts else ""

        ctx.check(
            "30C9 payload starts with '00' (correct for CTL zone, issue 929 fix)",
            len(payload) >= 2 and payload[:2] == "00",
            f"payload was '{payload[:8]}' (expected '00' for CTL zone)",
        )
