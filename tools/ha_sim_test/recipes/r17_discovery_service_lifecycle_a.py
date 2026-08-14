"""Recipe R17: Discovery service lifecycle [A]."""

from __future__ import annotations

import json
import subprocess
import time
import urllib.request
from datetime import datetime as dt
from datetime import timedelta

from ..base import Recipe, RecipeContext
from ..const import CO2, CTL, DHW, FAN, HGI, REM, TRV
from ..helpers import (
    call_service,
    find_battery_entity,
    find_entity_for_device,
    get_cached_schema,
    get_current_instance,
    get_entities,
    get_entity_attributes,
    get_known_list,
    get_persistent_notifications,
    get_ramses_storage,
    get_schema,
    get_schema_retry,
    grep_ha_log,
    is_ramses_cc_loaded,
    load_profile_yaml,
    wait_for,
    wait_for_transport_ready,
    write_ramses_storage,
    ws_send,
)
from ..profile import MIXED_KL, MIXED_SCHEMA, mixed_yaml


class R17DiscoveryServiceLifecycleA(Recipe):
    id = "R17"
    seq = 170
    title = "Discovery service lifecycle [A]"

    async def run(self, ctx: RecipeContext) -> None:
        ctx.log_section("Recipe 17: Discovery service lifecycle")

        # Load fresh_start profile to get a clean discovery state
        print("  Loading fresh_start_allow_unknown_devices_fast_heartbeat...")
        profile_loaded = False
        for attempt in range(3):
            try:
                await ws_send(
                    ctx.token,
                    {
                        "type": "ramses_extras/device_simulator/load_profile",
                        "profile": "fresh_start_allow_unknown_devices_fast_heartbeat",
                        "speed": 0.01,
                        "preload_schema": False,
                        "reload_ramses_cc": True,
                        "enable_auto_answer": True,
                    },
                    retries=3,
                )
                print("  fresh_start profile loaded")
                profile_loaded = True
                break
            except RuntimeError as e:
                print(f"  Profile load attempt {attempt + 1}/3 failed: {str(e)[:80]}")
                if attempt < 2:
                    ctx.wait(5, "before retry")
        if not profile_loaded:
            ctx.check(
                "get_discovered_devices returns results", False, "profile load failed"
            )
            ctx.check("04:500001 in discovered devices", False, "profile load failed")
            return
        ctx.wait_for_ramses_cc_reload(timeout=20)
        ctx.refresh_token()
        # Wait for the MQTT transport to reconnect after the reload,
        # otherwise injected packets are silently dropped.
        wait_for_transport_ready(timeout=30)

        # Wait for the DiscoveryManager to start before injecting heartbeats.
        # The fresh_start profile reload triggers a new DiscoveryScan that
        # replaces the old one.  If 1FC9 heartbeats are injected before the
        # new scan starts, they're detected by the old scan and lost when
        # the new scan starts (it only imports devices from the schema).
        #
        # Count the "started" lines before the reload and wait for the
        # count to increase — otherwise the wait_for would match stale
        # "started" lines from previous recipes in the docker logs.
        def _count_discovery_starts() -> int:
            inst = get_current_instance()
            result = subprocess.run(
                ["docker", "logs", inst.name],
                capture_output=True,
                text=True,
                timeout=15,
            )
            logs = (result.stderr or "") + (result.stdout or "")
            return logs.count("DiscoveryManager: started (passive scan running)")

        _discovery_count_before = _count_discovery_starts()

        def _discovery_started() -> bool:
            return _count_discovery_starts() > _discovery_count_before

        wait_for(
            _discovery_started,
            timeout=45,
            interval=2,
            msg="for DiscoveryManager to start",
            floor=20.0,
        )

        # Inject heartbeat from a new device to trigger discovery.
        # Retry up to 3 times — on cold containers the ramses_extras
        # services may not be registered yet after the reload (HTTP 400).
        disc_dev = "04:500001"
        print(f"  Injecting heartbeat from {disc_dev}...")
        inject_ok = False
        for attempt in range(3):
            try:
                call_service(
                    ctx.token,
                    "ramses_extras",
                    "device_simulator_inject_message",
                    {
                        "source_id": disc_dev,
                        "code": "1FC9",
                        "payload": "0030C912E294",
                        "verb": "I",
                    },
                )
                inject_ok = True
                break
            except RuntimeError as e:
                print(f"    Inject attempt {attempt + 1} failed: {str(e)[:60]}")
                if attempt < 2:
                    ctx.wait(3, "before retry")
        if not inject_ok:
            print("  WARN: all 1FC9 inject attempts failed")

        # Poll for the device appearing in discovery scan logs
        def _device_discovered() -> bool:
            return len(grep_ha_log(disc_dev.replace(":", "_"), since_lines=200)) > 0

        wait_for(
            _device_discovered,
            timeout=20,
            interval=2,
            msg="for discovery scan to detect the new device",
            floor=5.0,
        )

        # Test get_discovered_devices (fires a bus event)
        print("  Calling get_discovered_devices...")
        disc_devices: list[dict] = []
        try:
            # Subscribe to the event and call the service
            import aiohttp

            async def _get_disc():
                uri = get_current_instance().ws_url
                async with aiohttp.ClientSession() as session:
                    async with session.ws_connect(
                        uri, timeout=30, receive_timeout=30
                    ) as ws:
                        # Handle auth handshake with CLOSE frame awareness
                        auth_req = await ws.receive(timeout=30)
                        if auth_req.type == aiohttp.WSMsgType.CLOSE:
                            raise RuntimeError(
                                f"WebSocket closed during auth (code={auth_req.data})"
                            )
                        await ws.send_json({"type": "auth", "access_token": ctx.token})
                        auth_resp = await ws.receive(timeout=30)
                        if auth_resp.type == aiohttp.WSMsgType.CLOSE:
                            raise RuntimeError(
                                f"WebSocket closed during auth (code={auth_resp.data})"
                            )
                        # Subscribe to the discovered_devices event
                        await ws.send_json(
                            {
                                "id": 1,
                                "type": "subscribe_events",
                                "event_type": "ramses_cc_discovered_devices",
                            }
                        )
                        resp = await ws.receive(timeout=30)
                        if resp.type != aiohttp.WSMsgType.TEXT:
                            raise RuntimeError(
                                f"WebSocket closed during subscribe (type={resp.type})"
                            )
                        import json as _json

                        resp_data = _json.loads(resp.data)
                        if not resp_data.get("success"):
                            raise RuntimeError(f"subscribe failed: {resp_data}")
                        # Now call the service via REST
                        call_service(
                            ctx.token, "ramses_cc", "get_discovered_devices", {}
                        )
                        # Wait for the event
                        import asyncio as _aio

                        try:
                            event_resp = await _aio.wait_for(
                                ws.receive(timeout=30), timeout=15
                            )
                            if event_resp.type == aiohttp.WSMsgType.TEXT:
                                event_msg = _json.loads(event_resp.data)
                                if event_msg.get("type") == "event":
                                    disc_devices.extend(
                                        event_msg["event"]["data"].get("devices", [])
                                    )
                        except TimeoutError:
                            pass

            for _attempt in range(3):
                try:
                    await _get_disc()
                    if disc_devices:
                        break
                    print(
                        f"  get_discovered_devices returned empty"
                        f" (attempt {_attempt + 1}/3)"
                    )
                except Exception as e:
                    print(
                        f"  get_discovered_devices failed"
                        f" (attempt {_attempt + 1}/3): {str(e)[:60]}"
                    )
                if _attempt < 2 and not disc_devices:
                    import asyncio as _aio2

                    await _aio2.sleep(3)
        except Exception as e:
            print(f"  get_discovered_devices failed: {str(e)[:60]}")

        disc_ids = [d.get("device_id") for d in disc_devices]
        print(f"  Discovered devices: {disc_ids}")
        ctx.check(
            "get_discovered_devices returns results",
            len(disc_devices) > 0,
            f"devices={disc_ids}",
        )

        has_disc_dev = disc_dev in disc_ids
        ctx.check(
            f"{disc_dev} in discovered devices", has_disc_dev, f"discovered={disc_ids}"
        )

        # Test discard_discovered_device
        if has_disc_dev:
            print(f"  Discarding {disc_dev}...")
            try:
                call_service(
                    ctx.token,
                    "ramses_cc",
                    "discard_discovered_device",
                    {
                        "device_id": disc_dev,
                    },
                )
                print("  discard succeeded")
                ctx.wait(2, "for discard to process")
                ctx.check("discard_discovered_device succeeds", True, "")
            except RuntimeError as e:
                ctx.check("discard_discovered_device succeeds", False, str(e)[:80])

        # Test enable_discovered_device (re-enable a discarded device)
        if has_disc_dev:
            print(f"  Enabling {disc_dev}...")
            try:
                call_service(
                    ctx.token,
                    "ramses_cc",
                    "enable_discovered_device",
                    {
                        "device_id": disc_dev,
                    },
                )
                print("  enable succeeded")
                ctx.wait(2, "for enable to process")
                ctx.check("enable_discovered_device succeeds", True, "")
            except RuntimeError as e:
                ctx.check("enable_discovered_device succeeds", False, str(e)[:80])

        # Test accept_discovered_device
        if has_disc_dev:
            print(f"  Accepting {disc_dev}...")
            try:
                call_service(
                    ctx.token,
                    "ramses_cc",
                    "accept_discovered_device",
                    {
                        "device_id": disc_dev,
                    },
                )
                print("  accept succeeded")
                wait_for(
                    lambda: disc_dev in get_known_list(),
                    timeout=10,
                    interval=1,
                    msg="for ramses_rf include list update",
                    floor=2.0,
                )
                ctx.check("accept_discovered_device succeeds", True, "")
            except RuntimeError as e:
                ctx.check("accept_discovered_device succeeds", False, str(e)[:80])

        # Test disable_discovered_device (disable an accepted device)
        if has_disc_dev:
            print(f"  Disabling {disc_dev}...")
            try:
                call_service(
                    ctx.token,
                    "ramses_cc",
                    "disable_discovered_device",
                    {
                        "device_id": disc_dev,
                    },
                )
                print("  disable succeeded")
                ctx.wait(2, "for disable to process")
                ctx.check("disable_discovered_device succeeds", True, "")
            except RuntimeError as e:
                ctx.check("disable_discovered_device succeeds", False, str(e)[:80])

        # Test remove_discovered_device
        if has_disc_dev:
            print(f"  Removing discovered {disc_dev}...")
            try:
                call_service(
                    ctx.token,
                    "ramses_cc",
                    "remove_discovered_device",
                    {
                        "device_id": disc_dev,
                    },
                )
                print("  remove_discovered succeeded")
                ctx.wait(3, "for remove to process")
                ctx.check("remove_discovered_device succeeds", True, "")
            except RuntimeError as e:
                ctx.check("remove_discovered_device succeeds", False, str(e)[:80])
