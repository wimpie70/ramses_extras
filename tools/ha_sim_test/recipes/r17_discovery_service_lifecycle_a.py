"""Recipe R17: Discovery service lifecycle [A]."""

from __future__ import annotations

import json
import subprocess
import time
import urllib.request
from datetime import datetime as dt
from datetime import timedelta

from ..base import Recipe, RecipeContext
from ..const import CO2, CTL, DHW, FAN, HA_URL, HGI, REM, TRV
from ..helpers import (
    call_service,
    find_battery_entity,
    find_entity_for_device,
    get_cached_schema,
    get_entities,
    get_entity_attributes,
    get_known_list,
    get_persistent_notifications,
    get_ramses_storage,
    get_schema,
    get_schema_retry,
    load_profile_yaml,
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
            )
            print("  fresh_start profile loaded")
        except RuntimeError as e:
            print(f"  Profile load failed: {e}")
        ctx.wait(15, "for ramses_cc reload with fresh_start")
        ctx.refresh_token()
        ctx.wait(5, "for ramses_cc to initialize")

        # Inject heartbeat from a new device to trigger discovery
        disc_dev = "04:500001"
        print(f"  Injecting heartbeat from {disc_dev}...")
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
        except RuntimeError as e:
            print(f"  Inject failed: {e}")
        ctx.wait(10, "for discovery scan to detect the new device")

        # Test get_discovered_devices (fires a bus event)
        print("  Calling get_discovered_devices...")
        disc_devices = []
        try:
            # Subscribe to the event and call the service
            import aiohttp

            async def _get_disc():
                uri = "ws://localhost:8124/api/websocket"
                async with aiohttp.ClientSession() as session:
                    async with session.ws_connect(uri) as ws:
                        await ws.receive_json()
                        await ws.send_json({"type": "auth", "access_token": ctx.token})
                        await ws.receive_json()
                        # Subscribe to the discovered_devices event
                        await ws.send_json(
                            {
                                "id": 1,
                                "type": "subscribe_events",
                                "event_type": "ramses_cc_discovered_devices",
                            }
                        )
                        resp = await ws.receive_json()
                        if not resp.get("success"):
                            raise RuntimeError(f"subscribe failed: {resp}")
                        # Now call the service via REST
                        call_service(
                            ctx.token, "ramses_cc", "get_discovered_devices", {}
                        )
                        # Wait for the event
                        import asyncio as _aio

                        try:
                            event_msg = await _aio.wait_for(
                                ws.receive_json(), timeout=10
                            )
                            if event_msg.get("type") == "event":
                                disc_devices.extend(
                                    event_msg["event"]["data"].get("devices", [])
                                )
                        except TimeoutError:
                            pass

            await _get_disc()
        except Exception as e:
            print(f"  get_discovered_devices failed: {e}")

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
                ctx.wait(5, "for ramses_rf include list update")
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
