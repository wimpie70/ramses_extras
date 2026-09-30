"""Recipe R135: bind_device service — supplicant handshake.

Exercises ``ramses_cc.bind_device`` end-to-end: the service initiates the
binding FSM for a faked device (supplicant), an injected ``W 1FC9`` Accept
acts as the respondent, and an injected ``I 1FC9`` stands in for the
Confirm echo if the TX path does not loop back.

Covers ramses-rf/ramses_cc issue 1232 — the parameterized binding path
(``Fakeable.initiate_binding_process_with``) used by the service.
"""

from __future__ import annotations

import json
import threading
import time
import urllib.request

from ..base import Recipe, RecipeContext
from ..const import FAN, REM
from ..helpers import (
    call_service,
    get_current_instance,
    get_docker_logs,
    get_schema_retry,
    load_profile_yaml,
    wait_for,
    wait_for_transport_ready,
)
from ..profile import minimal_hvac_yaml

# REM 37:170000 (HvacRemote, Fakeable) binds to FAN 32:150000.
# 1FC9 payload tuples are <zone_idx><code><devid-hex>; the devid is the
# 18-bit device number OR-ed with the device type bits:
#   FAN 32:150000 -> 0x8249F0, REM 37:170000 -> 0x969770
_ACCEPT_PAYLOAD = "0022F18249F00022F38249F0"  # FAN accepts 22F1 + 22F3
_CONFIRM_PAYLOAD = "0022F1969770"  # REM confirms 22F1


class R135BindDeviceSupplicantHandshake(Recipe):
    id = "R135"
    seq = 1350
    title = "bind_device service — supplicant handshake completes"
    tags = ("1FC9", "binding", "bind_device", "supplicant")

    async def run(self, ctx: RecipeContext) -> None:
        """Run the bind_device handshake scenario."""
        ctx.log_section("Recipe 135: bind_device service handshake")

        # bind_device needs a Fakeable device — load the minimal HVAC
        # profile (FAN + REM + CO2 + HGI) so REM 37:170000 exists
        # regardless of which profile the previous recipe left behind.
        print("  Loading minimal_hvac profile (FAN + REM + CO2 + HGI)...")
        try:
            await load_profile_yaml(ctx.token, minimal_hvac_yaml())
            print("  minimal_hvac profile loaded")
        except RuntimeError as e:
            print(f"  Profile load failed: {e}")
        ctx.wait_for_ramses_cc_reload(timeout=20)
        ctx.refresh_token()

        wait_for(
            lambda: REM in get_schema_retry(),
            timeout=15,
            interval=1,
            msg=f"for {REM} in schema",
            floor=2.0,
        )

        # Ensure the bind_device service is registered (mirrors R18 —
        # services can be unregistered by a preceding profile reload).
        def _bind_service_ready() -> bool:
            ha_url = get_current_instance().ha_url
            url = f"{ha_url}/api/services"
            req = urllib.request.Request(
                url,
                headers={"Authorization": f"Bearer {ctx.token}"},
            )
            try:
                resp = urllib.request.urlopen(req, timeout=10)
                services = json.loads(resp.read())
                return any(
                    s.get("domain") == "ramses_cc"
                    and "bind_device" in s.get("services", {})
                    for s in services
                )
            except Exception:
                return False

        wait_for(
            _bind_service_ready,
            timeout=45,
            interval=3,
            msg="for ramses_cc bind_device service",
            floor=15.0,
        )

        # Wait for the MQTT transport to reconnect after the reload,
        # otherwise injected packets are silently dropped.
        wait_for_transport_ready(timeout=30)

        supplicant = REM
        respondent = FAN

        def _inject_peer_packets() -> None:
            # The sim has no respondent that auto-accepts binding offers,
            # so play the respondent: send the Accept once the Offer is
            # on the wire, then imitate the Confirm echo (harmless if the
            # TX loopback already delivered the real Confirm).
            time.sleep(1.5)
            try:
                call_service(
                    ctx.token,
                    "ramses_extras",
                    "device_simulator_inject_message",
                    {
                        "source_id": respondent,
                        "dst": supplicant,
                        "code": "1FC9",
                        "payload": _ACCEPT_PAYLOAD,
                        "verb": "W",
                    },
                )
            except RuntimeError as e:
                print(f"  Accept inject failed: {e}")

            time.sleep(1.5)
            try:
                call_service(
                    ctx.token,
                    "ramses_extras",
                    "device_simulator_inject_message",
                    {
                        "source_id": supplicant,
                        "dst": respondent,
                        "code": "1FC9",
                        "payload": _CONFIRM_PAYLOAD,
                        "verb": "I",
                    },
                )
            except RuntimeError as e:
                print(f"  Confirm-echo inject failed: {e}")

        threading.Thread(target=_inject_peer_packets, daemon=True).start()

        log_since = ctx.log_monitor.snapshot()
        bound = False
        try:
            call_service(
                ctx.token,
                "ramses_cc",
                "bind_device",
                {
                    "device_id": supplicant,
                    "offer": {"22F1": "00", "22F3": "00"},
                },
            )
            bound = True
        except RuntimeError as e:
            print(f"  bind_device failed: {str(e)[:120]}")

        ctx.check(
            f"bind_device completes handshake for {supplicant}",
            bound,
            "",
        )

        # The service logs "Success! Binding process completed for
        # device <id>" at WARNING level on success.  Read the raw log —
        # the line is in log_monitor's EXPECTED_WARNINGS, so collect()
        # filters it out.
        raw_logs = get_docker_logs(since=log_since)
        completed = [
            line
            for line in raw_logs.splitlines()
            if "Binding process completed" in line and supplicant in line
        ]
        ctx.check(
            f"log confirms binding completed for {supplicant}",
            len(completed) > 0,
            f"raw log tail={raw_logs.splitlines()[-5:]}",
        )

        # Any error mentioning the supplicant or the binding method
        # indicates a broken call path.
        log_data = ctx.log_monitor.collect()
        bind_errors = [
            line
            for line in log_data.get("errors", [])
            if supplicant in line or "initiate_binding_process" in line
        ]
        ctx.check(
            "no binding errors in ha-sim log",
            len(bind_errors) == 0,
            f"{bind_errors[:3]}",
        )
