"""Recipe R26: Phase 3c — missing _class detection."""

from __future__ import annotations

import subprocess
import urllib.request

from ..base import Recipe, RecipeContext
from ..const import CTL
from ..helpers import (
    call_service,
    get_current_instance,
    get_schema_retry,
    load_profile_yaml,
    wait_for,
    ws_send,
)


class R26Phase3cMissingClassDetection(Recipe):
    id = "R26"
    seq = 260
    title = "Phase 3c — missing _class detection"

    async def run(self, ctx: RecipeContext) -> None:
        ctx.log_section("Recipe 26: Phase 3c — missing _class detection")

        # The missing_class check flags devices where the scan engine has a
        # likely_type but the schema entry has no _class.  We create this
        # precondition by loading a profile with a device that has a root
        # entry but no _class, then inject packets from that device so the
        # scan engine tracks it with a likely_type.
        #
        # We use a fresh device ID (04:200099) to avoid interference from
        # R19's accept_discovered_device (which sets _class via _merge).

        test_device = "04:200099"

        # Step 1: Load a minimal profile with test_device in the schema
        # but no _class.  The known_list must NOT include a class for
        # this device, otherwise _merge_known_list_into_schema would add
        # _class from the known_list.
        from ..profile import minimal_ctl_yaml

        # Minimal profile: CTL + test_device with empty schema entry
        r26_yaml = minimal_ctl_yaml(
            schema_override={test_device: {}},
        )

        print(f"  Loading minimal profile with {test_device} (no _class)...")
        await load_profile_yaml(ctx.token, r26_yaml, speed=0.01)
        ctx.wait_for_ramses_cc_reload(msg="for profile reload")
        ctx.refresh_token()

        # Activate CTL for heartbeats so the scan engine is active
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

        # Verify test_device is in schema without _class
        schema_r26 = get_schema_retry()
        entry_r26 = schema_r26.get(test_device, {})
        has_class = isinstance(entry_r26, dict) and bool(entry_r26.get("_class"))
        print(
            f"  {test_device} in schema: {test_device in schema_r26}, "
            f"has _class: {has_class}, entry: {entry_r26}"
        )

        if test_device not in schema_r26:
            ctx.check(
                f"Log contains missing _class detection for {test_device}",
                False,
                f"{test_device} not in schema after profile load",
            )
            return

        if has_class:
            ctx.check(
                f"Log contains missing _class detection for {test_device}",
                False,
                f"{test_device} has _class={entry_r26.get('_class')!r} "
                "(profile should not set _class for this device)",
            )
            return

        # Step 2: Inject packets from test_device to populate the scan engine.
        # 000A is a zone binding code — it gets the device into the scan
        # engine with high confidence and sets likely_type=TRV (via the
        # 04: prefix fallback in _classify).
        print(f"  Injecting 000A + 30C9 from {test_device} to populate scan engine...")
        try:
            call_service(
                ctx.token,
                "ramses_extras",
                "device_simulator_inject_message",
                {
                    "source_id": test_device,
                    "code": "000A",
                    "payload": "0200FF",
                    "verb": "I",
                },
            )
        except RuntimeError as e:
            print(f"    000A inject failed: {str(e)[:80]}")
        ctx.wait(2, "between injects")
        # Also inject 30C9 (temperature) for additional evidence
        try:
            call_service(
                ctx.token,
                "ramses_extras",
                "device_simulator_inject_message",
                {
                    "source_id": test_device,
                    "code": "30C9",
                    "payload": "020708",
                    "verb": "I",
                },
            )
        except RuntimeError as e:
            print(f"    30C9 inject failed: {str(e)[:80]}")
        ctx.wait(3, "for scan engine to process", floor=3.0)

        # Step 3: Trigger sync_topology to run check_missing_class.
        try:
            call_service(ctx.token, "ramses_cc", "sync_topology")
        except RuntimeError:
            pass
        ctx.wait(5, "for missing_class detection", floor=3.0)

        # Step 4: Check the log for the missing_class message.
        # We check the log instead of the persistent notification because
        # the periodic discovery checkpoint may dismiss the notification
        # between sync_topology and our check.
        log_url = get_current_instance().ha_url + "/api/error_log"
        req = urllib.request.Request(
            log_url,
            headers={"Authorization": f"Bearer {ctx.token}"},
        )
        log_text = urllib.request.urlopen(req).read().decode()

        # Also check docker logs for scan engine state
        docker_logs = subprocess.run(
            ["docker", "logs", get_current_instance().name, "--since", "60s"],
            capture_output=True,
            text=True,
        ).stdout
        scan_has_device = test_device in docker_logs
        print(f"  {test_device} in docker logs: {scan_has_device}")

        # The DEBUG message is "missing _class for <device>" but only
        # appears at DEBUG level.  The INFO message is "N device(s) in
        # schema have no _class but discovery has a suggestion: <device>".
        # Check for either format.
        has_missing_class_log = f"missing _class for {test_device}" in log_text or (
            "have no _class" in log_text and test_device in log_text
        )
        ctx.check(
            f"Log contains missing _class detection for {test_device}",
            has_missing_class_log,
            f"no missing _class log entry for {test_device}",
        )
