"""Recipe R47: eavesdrop=False — unknown devices tracked by DiscoveryScan.

With ``enforce_known_list: true``, unknown devices are still tracked by the
DiscoveryScan observer (for classification), but not created as entities.
The observer path should always run; enforcement only controls entity
creation.

This recipe loads fresh_start (no preloaded schema), injects a packet from
an unknown device, and verifies:
1. No entities are created for the unknown device.
2. The device appears in the HA log (discovery scan tracking).
3. The ``get_discovered_devices`` service returns the device.

See: https://github.com/ramses-rf/ramses_cc/issues/767
"""

from __future__ import annotations

from ..base import Recipe, RecipeContext
from ..helpers import (
    call_service,
    get_entities,
    grep_ha_log,
    ws_send,
)


class R47EavesdropFalseUnknownDevicesTrackedIssue767(Recipe):
    id = "R47"
    seq = 480
    title = "eavesdrop=False — unknown devices tracked by DiscoveryScan (issue 767)"

    async def run(self, ctx: RecipeContext) -> None:
        ctx.log_section("Recipe 47: eavesdrop=False — unknown devices tracked")

        # 1. Load fresh_start (no schema, no known devices)
        print("  Loading fresh_start profile (no preloaded schema)...")
        try:
            await ws_send(
                ctx.token,
                {
                    "type": "ramses_extras/device_simulator/load_profile",
                    "profile": "fresh_start",
                    "speed": 0.01,
                    "preload_schema": False,
                    "reload_ramses_cc": True,
                    "enable_auto_answer": True,
                },
            )
        except RuntimeError as e:
            print(f"  Profile load failed: {e}")
        ctx.wait(15, "for ramses_cc reload")
        ctx.refresh_token()
        ctx.wait(5, "for ramses_cc to initialize")

        # 2. Inject a packet from an unknown device
        #    04:999999 is not in any known_list or schema
        unknown_device = "04:999999"
        print(f"  Injecting 3150 I from unknown device {unknown_device}...")
        try:
            call_service(
                ctx.token,
                "ramses_extras",
                "device_simulator_inject_message",
                {
                    "source_id": unknown_device,
                    "code": "3150",
                    "payload": "00C8",
                    "verb": "I",
                },
            )
            print("    3150 I injected")
        except RuntimeError as e:
            print(f"    Inject failed: {str(e)[:80]}")
        ctx.wait(10, "for DiscoveryScan to process")

        # 3. Verify no entities are created for the unknown device
        entities = get_entities(ctx.token)
        unknown_normalized = unknown_device.replace(":", "_")
        unknown_entities = [e for e in entities if unknown_normalized in e["entity_id"]]

        ctx.check(
            f"no entities created for unknown device {unknown_device}",
            len(unknown_entities) == 0,
            f"found {len(unknown_entities)} entities: "
            f"{[e['entity_id'] for e in unknown_entities]}",
        )

        # 4. Check the HA log for discovery scan entries about this device
        #    The device ID in the log may use : or . separators
        log_lines = grep_ha_log(unknown_device.replace(":", "."))
        ctx.check(
            f"unknown device {unknown_device} appears in HA log "
            f"(discovery scan tracking)",
            len(log_lines) > 0,
            "no log entries for unknown device",
        )

        # 5. Check get_discovered_devices service
        #    This service fires a ramses_cc_discovered_devices event rather
        #    than returning data directly.  We call it and check the HA log
        #    for the service's log output showing the discovered device.
        try:
            call_service(
                ctx.token,
                "ramses_cc",
                "get_discovered_devices",
                {},
            )
            ctx.wait(2, "for event to fire")

            # Check the HA log for the service's log output
            svc_log = grep_ha_log(
                f"get_discovered_devices.*{unknown_device.replace(':', '.')}"
                f"|{unknown_device.replace(':', '.')}.*type=.*confidence=.*status=",
                since_lines=200,
            )
            ctx.check(
                f"unknown device {unknown_device} in get_discovered_devices "
                f"(log output)",
                len(svc_log) > 0,
                "device not found in get_discovered_devices log output",
            )
        except RuntimeError as e:
            ctx.check(
                "get_discovered_devices service call succeeds",
                False,
                str(e)[:80],
            )
