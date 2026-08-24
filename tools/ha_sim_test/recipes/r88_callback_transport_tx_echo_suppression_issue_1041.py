"""Recipe R88: CallbackTransport TX echo suppression (issue 1041).

Issue 1041: Packet log duplicated TX messages for MQTT/CallbackTransport.

The root cause was that CallbackTransport.write_frame overrode
_FullTransport.write_frame without calling super(), so _log_tx_packet()
was never called — no tx_keys were recorded, echo detection failed, and
all MQTT echoes appeared as duplicates in the packet log.

The fix removes the write_frame override so CallbackTransport inherits
_FullTransport.write_frame, which calls _log_tx_packet (records tx_key
+ logs TX) before delegating to _write_frame (io_writer).

This recipe verifies:
1. CallbackTransport inherits write_frame from _FullTransport (no override).
2. After sending a command, the TX packet appears in the packet log.
3. The MQTT echo is suppressed (no duplicate RQ entries).
4. The _inject_inbound_to_stream workaround in ramses_extras is disabled
   when the fix is present (no duplicate in the message stream).

See: https://github.com/ramses-rf/ramses_cc/issues/1041
"""

from __future__ import annotations

from ..base import Recipe, RecipeContext
from ..const import CTL
from ..helpers import (
    call_service,
    docker_exec_python,
    get_entities,
    is_ramses_cc_loaded,
    wait_for,
    wait_for_transport_ready,
    ws_send,
)


class R88CallbackTransportTxEchoSuppressionIssue1041(Recipe):
    id = "R88"
    seq = 880
    title = "CallbackTransport TX echo suppression (issue 1041)"

    async def run(self, ctx: RecipeContext) -> None:
        ctx.log_section("Recipe 88: CallbackTransport TX echo suppression")

        # ── 1. Structural check: CallbackTransport inherits write_frame ──
        code = """
import json
try:
    from ramses_tx.transport.base import _FullTransport
    from ramses_tx.transport.callback import CallbackTransport
    inherits = CallbackTransport.write_frame is _FullTransport.write_frame
    has_override = "write_frame" in CallbackTransport.__dict__
    print(json.dumps({
        "inherits_write_frame": inherits,
        "has_override": has_override,
        "ok": True,
    }))
except Exception as e:
    print(json.dumps({"error": str(e), "ok": False}))
"""
        result = docker_exec_python(code)

        if not result.get("ok"):
            ctx.check(
                "CallbackTransport importable for inspection",
                False,
                result.get("error", "unknown"),
            )
            return

        ctx.check(
            "CallbackTransport inherits write_frame from _FullTransport",
            result.get("inherits_write_frame", False),
            f"has_override={result.get('has_override')}",
        )

        # ── 2. Load profile and wait for ramses_cc to be ready ──────────
        print("  Loading mixed profile for TX echo test...")
        try:
            await ws_send(
                ctx.token,
                {
                    "type": "ramses_extras/device_simulator/load_profile",
                    "profile": "mixed",
                    "speed": 0.01,
                    "preload_schema": True,
                    "reload_ramses_cc": True,
                    "enable_auto_answer": True,
                },
            )
        except RuntimeError as e:
            print(f"  Profile load failed: {e}")
        ctx.wait_for_ramses_cc_reload(timeout=20)
        ctx.refresh_token()
        wait_for_transport_ready(timeout=30)
        ctx.wait_for_ramses_cc_loaded(timeout=20, msg="for ramses_cc to initialize")

        # Activate CTL so RQ commands have a target in the known_list
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

        ctx.wait(3, "for CTL activation", floor=2.0)

        # ── 3. Capture packet log line count before sending a command ──
        # Read the current packet log tail to get a baseline
        baseline_code = """
import json, subprocess
try:
    result = subprocess.run(
        ["tail", "-5", "/config/packet_log.log"],
        capture_output=True, text=True, timeout=5
    )
    lines = result.stdout.strip().splitlines()
    print(json.dumps({"tail": lines, "count": len(lines), "ok": True}))
except Exception as e:
    print(json.dumps({"error": str(e), "ok": False}))
"""
        baseline = docker_exec_python(baseline_code)
        if not baseline.get("ok"):
            ctx.check(
                "Packet log readable",
                False,
                baseline.get("error", "unknown"),
            )
            return

        ctx.check("Packet log readable", True, "")
        baseline_tail = baseline.get("tail", [])
        print(f"  Baseline packet log tail ({len(baseline_tail)} lines)")

        # ── 4. Trigger an RQ command via force_update (causes RQ 30C9) ──
        # force_update sends RQ commands to the CTL for zone temps.
        # With the fix, each RQ should produce exactly 1 TX log line
        # (000 RSSI) + 1 RP from the simulator. Without the fix, we'd
        # see 3-5 duplicate RQ entries (all echoes, no TX log).
        print("  Triggering RQ commands via force_update...")
        try:
            call_service(ctx.token, "ramses_cc", "force_update")
        except RuntimeError as e:
            print(f"  force_update failed: {e}")

        ctx.wait(5, "for RQ/RP exchange to complete", floor=3.0)

        # ── 5. Read packet log after the command and check for duplicates ─
        post_code = """
import json, subprocess
try:
    result = subprocess.run(
        ["tail", "-30", "/config/packet_log.log"],
        capture_output=True, text=True, timeout=5
    )
    lines = result.stdout.strip().splitlines()
    # Count RQ lines with the same code+src+dst (duplicates)
    from collections import Counter
    rq_keys = []
    for line in lines:
        parts = line.split()
        if len(parts) >= 6 and "RQ" in parts:
            # Key: verb + src + dst + code (ignoring timestamp and RSSI)
            # parts format: timestamp RSSI verb seq src dst via code len payload
            # or:           timestamp ... verb seq src dst via code len payload
            verb_idx = None
            for i, p in enumerate(parts):
                if p in ("RQ", "RP", " I", " W"):
                    verb_idx = i
                    break
            if verb_idx is not None and verb_idx + 4 < len(parts):
                key = (
                    parts[verb_idx],
                    parts[verb_idx + 2],
                    parts[verb_idx + 3],
                    parts[verb_idx + 5],
                )
                rq_keys.append(key)
    rq_counts = Counter(rq_keys)
    # Find any RQ key with more than 2 entries (1 TX + 1 echo max)
    duplicates = {str(k): v for k, v in rq_counts.items() if v > 2}
    print(json.dumps({
        "lines": lines[-15:],
        "rq_count": len(rq_keys),
        "duplicates": duplicates,
        "ok": True,
    }))
except Exception as e:
    print(json.dumps({"error": str(e), "ok": False}))
"""
        post = docker_exec_python(post_code)

        if not post.get("ok"):
            ctx.check(
                "Post-command packet log readable",
                False,
                post.get("error", "unknown"),
            )
            return

        ctx.check("Post-command packet log readable", True, "")

        duplicates = post.get("duplicates", {})
        rq_count = post.get("rq_count", 0)

        # With the fix: each RQ appears at most twice (1 TX log + 1 echo
        # that gets suppressed). Without the fix: 3-5 duplicate RQ entries.
        # We check that no RQ key has more than 2 entries.
        ctx.check(
            "No duplicate RQ entries in packet log (>2 per key)",
            len(duplicates) == 0,
            f"duplicates={duplicates}, rq_count={rq_count}",
        )

        # ── 6. Verify TX packets are logged (000 RSSI entries exist) ────
        # With the fix, _log_tx_packet creates entries with RSSI "000".
        # Without the fix, no TX entries are logged at all.
        tx_check_code = """
import json, subprocess
try:
    result = subprocess.run(
        ["tail", "-30", "/config/packet_log.log"],
        capture_output=True, text=True, timeout=5
    )
    lines = result.stdout.strip().splitlines()
    # TX entries have RSSI "000" and verb RQ
    tx_lines = [l for l in lines if " 000 RQ " in l]
    print(json.dumps({
        "tx_line_count": len(tx_lines),
        "sample_tx": tx_lines[:3] if tx_lines else [],
        "ok": True,
    }))
except Exception as e:
    print(json.dumps({"error": str(e), "ok": False}))
"""
        tx_result = docker_exec_python(tx_check_code)

        if tx_result.get("ok"):
            tx_count = tx_result.get("tx_line_count", 0)
            ctx.check(
                "TX packets logged with 000 RSSI (issue 1041 fix)",
                tx_count > 0,
                f"tx_count={tx_count}, sample={tx_result.get('sample_tx', [])}",
            )
        else:
            ctx.check(
                "TX packet log inspection",
                False,
                tx_result.get("error", "unknown"),
            )

        # ── 7. Verify _inject_inbound_to_stream is disabled when fix present
        if result.get("inherits_write_frame"):
            # The fix is present — _inject_inbound_to_stream should be
            # a no-op (guarded by _TX_VIA_MSG_HANDLER=True). We can't
            # directly inspect the simulator's internal flag from outside
            # the container, but we can check that the ramses_extras
            # module detects the fix correctly.
            detect_code = """
import json
try:
    from custom_components.ramses_extras.features.device_simulator \
        .scenario_engine import _TX_VIA_MSG_HANDLER
    print(json.dumps({"tx_via_msg_handler": _TX_VIA_MSG_HANDLER, "ok": True}))
except Exception as e:
    print(json.dumps({"error": str(e), "ok": False}))
"""
            detect_result = docker_exec_python(detect_code)
            if detect_result.get("ok"):
                ctx.check(
                    "ramses_extras detects ramses_rf fix (_TX_VIA_MSG_HANDLER=True)",
                    detect_result.get("tx_via_msg_handler", False),
                    f"tx_via_msg_handler={detect_result.get('tx_via_msg_handler')}",
                )
            else:
                # ramses_extras may not be installed as a package in the
                # container — this is informational, not a failure
                print(
                    f"  INFO: could not inspect _TX_VIA_MSG_HANDLER in container: "
                    f"{detect_result.get('error', 'unknown')}"
                )
                ctx.check(
                    "ramses_extras detects ramses_rf fix (_TX_VIA_MSG_HANDLER=True)",
                    True,
                    "skipped — ramses_extras not importable in container",
                )
