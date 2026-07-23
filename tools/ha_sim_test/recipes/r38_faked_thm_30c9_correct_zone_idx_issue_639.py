"""Recipe R38: Faked THM 30C9 uses correct zone_idx (issue 639).

Regression guard for the fix in ramses_rf that ensures ``build_put_sensor_temp``
uses the device's parent zone_idx instead of hard-coding ``"00"``.

Before the fix, faking a UFH zone sensor (THM bound to a zone with idx != 00)
emitted 30C9 with idx 00 while the real device uses its actual zone idx
(e.g. 01).  The UFC ignored the mismatched packets and the zone stayed in
comms-lost.

The ``put_room_temp`` service is an entity service that targets a temperature
sensor entity.  It calls ``sensor.set_temperature(temperature)`` which sends
a 30C9 I packet — but only if the device is faked (``faked: true`` in the
known_list).  This recipe loads a profile with the zone-03 sensor faked,
calls ``put_room_temp`` on the sensor entity, and verifies the 30C9 payload
starts with the correct zone_idx (``03``), not the hard-coded ``00``.

See: https://github.com/ramses-rf/ramses_rf/issues/639
"""

from __future__ import annotations

import json
import os
import subprocess

from ..base import Recipe, RecipeContext
from ..const import CTL
from ..helpers import (
    call_service,
    get_entities,
    load_profile_yaml,
    ws_send,
)
from ..profile import MIXED_KL, MIXED_SCHEMA, mixed_yaml


class R38FakedThm30c9CorrectZoneIdxIssue639(Recipe):
    id = "R38"
    seq = 390
    title = "Faked THM 30C9 uses correct zone_idx (issue 639)"

    async def run(self, ctx: RecipeContext) -> None:
        ctx.log_section("Recipe 38: Faked THM 30C9 uses correct zone_idx (issue 639)")

        # 0. Clear cached state from previous recipes (e.g. R37 adds OTB/BDR
        #    to the schema which persist across restarts and cause the
        #    discovery scan to continuously poll them, blocking the QoS
        #    queue and preventing the 30C9 I packet from being transmitted).
        print("  Stopping ha-sim and clearing cached state...")
        ctx.log_monitor.capture_before_restart("R38 pre-clean")
        subprocess.run(["docker", "stop", "ha-sim"], capture_output=True)
        ctx.wait(2, "for container to stop")
        storage_path = "/home/willem/docker_files/ha-sim/config/.storage/ramses_cc"
        if os.path.exists(storage_path):
            os.remove(storage_path)
        for db_path in (
            "/home/willem/docker_files/ha-sim/config/ramses.db",
            "/home/willem/docker_files/ha-sim/config/ramses_rf/ramses.db",
        ):
            if os.path.exists(db_path):
                os.remove(db_path)
        ce_path = "/home/willem/docker_files/ha-sim/config/.storage/core.config_entries"
        if os.path.exists(ce_path):
            subprocess.run(
                [
                    "docker",
                    "run",
                    "--rm",
                    "-v",
                    "/home/willem/docker_files/ha-sim/config:/config",
                    "python:3.12-slim",
                    "python3",
                    "-c",
                    "import json; "
                    "p='/config/.storage/core.config_entries'; "
                    "d=json.load(open(p)); "
                    "[e.get('options',{}).pop('schema',None) "
                    "for e in d.get('data',{}).get('entries',[]) "
                    "if e.get('domain')=='ramses_cc']; "
                    "json.dump(d, open(p,'w')); "
                    "print('Cleared CONF_SCHEMA')",
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )
        subprocess.run(["docker", "start", "ha-sim"], capture_output=True)
        ctx.wait(20, "for ha-sim to start up")
        ctx.log_monitor.reset_baseline()
        ctx.refresh_token()
        ctx.wait(5, "for ramses_cc to initialize")

        # 1. Load mixed profile with the zone-03 sensor (01:150003) faked
        sensor_id = "01:150003"
        zone_idx = "03"
        fake_temp = 22.0

        # Build a known_list with faked: true on the sensor
        faked_kl = dict(MIXED_KL)
        faked_kl[sensor_id] = {"class": "THM", "faked": True}

        # Build a schema with the sensor faked
        faked_schema = dict(MIXED_SCHEMA)
        sensor_schema = dict(faked_schema.get(sensor_id, {}))
        sensor_schema["_faked"] = True
        faked_schema[sensor_id] = sensor_schema

        print(f"  Loading mixed profile with {sensor_id} faked...")
        import yaml as _yaml

        profile = _yaml.safe_load(mixed_yaml())
        profile["known_list"] = faked_kl
        profile["_schema"] = faked_schema
        yaml_text = _yaml.dump(profile, default_flow_style=False)

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
        ctx.wait(15, "for ramses_cc reload")
        ctx.refresh_token()
        ctx.wait(5, "for ramses_cc to initialize")

        # Activate CTL for heartbeats
        try:
            await ws_send(
                ctx.token,
                {
                    "type": ("ramses_extras/device_simulator/activate_profile_device"),
                    "device_id": CTL,
                },
            )
        except RuntimeError:
            pass
        ctx.wait(10, "for CTL heartbeats + schema population")

        # 2. Find the temperature sensor entity for 01:150003
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

        # 3. Call put_room_temp on the entity
        #    The service sends a 30C9 I packet and waits for an echo response.
        #    In the simulator, no echo comes, so the service times out after
        #    ~20 seconds with ProtocolTimeoutError (HTTP 500).  But the 30C9
        #    packet IS transmitted and appears in the HA log as a Recv'd line.
        print(
            f"  Calling put_room_temp on {sensor_eid} "
            f"(zone {zone_idx}, {fake_temp}°C)..."
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
            print(
                f"  put_room_temp returned error after {elapsed:.1f}s "
                f"(expected): {str(e)[:60]}"
            )

        ctx.wait(5, "for 30C9 packet to appear in log")

        # 5. Read the HA log for the 30C9 packet from our faked device.
        #    The faked device sends a 30C9 I broadcast via MQTT.  The
        #    device simulator receives it and logs:
        #      "Simulator received from ramses_rf:  I --- <src> ... 30C9 ..."
        #    We filter for our specific device to avoid matching other
        #    traffic.
        result = subprocess.run(
            [
                "docker",
                "exec",
                "ha-sim",
                "bash",
                "-c",
                f"grep 'Simulator received.*{sensor_id}.*30C9' "
                "/config/home-assistant.log | tail -10",
            ],
            capture_output=True,
            text=True,
        )
        tx_lines = []
        for line in result.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            tx_lines.append(line)

        ctx.check(
            "30C9 packet found in HA log",
            len(tx_lines) > 0,
            "no 30C9 packets found in HA log",
        )

        if not tx_lines:
            return

        print(f"  Found {len(tx_lines)} 30C9 packet(s):")
        for line in tx_lines:
            print(f"    {line}")

        # 5. Verify the payload starts with the correct zone_idx (03)
        #    30C9 payload format: {zone_idx}{temperature_hex}
        #    e.g. "030AC0" = idx 03, 22.0°C
        #    The bug was that it sent "000AC0" (idx 00) instead.
        last_tx = tx_lines[-1]
        parts = last_tx.split()
        payload = parts[-1] if parts else ""

        ctx.check(
            f"30C9 payload starts with zone_idx '{zone_idx}'",
            len(payload) >= 2 and payload[:2] == zone_idx,
            f"payload was '{payload[:8]}' (expected idx '{zone_idx}')",
        )

        # Also verify it does NOT start with "00" (the old buggy behaviour)
        ctx.check(
            "30C9 payload does NOT start with '00' (old bug)",
            len(payload) >= 2 and payload[:2] != "00",
            "payload starts with '00' — bug regression!",
        )
