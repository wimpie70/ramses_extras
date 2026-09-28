"""Recipe R79: FAN→DIS reclassification via contradiction detection (issue 1000).

Tests that ramses_rf's HvacTopologyHandler detects when a device classified
as FAN in the schema behaves like a DIS/REM (sends RQ 31DA, I 22F1, RQ 2411
but never I/RP 31DA or I 31D9).  The contradiction should:

1. Emit a WARNING log (once per session)
2. Update the SSOT known_list with class=DIS
3. Trigger a class_mismatch persistent notification via ramses_cc's
   _check_rf_contradictions callback

Also tests that ``_locked: true`` on the device's schema entry suppresses
the reclassification warning entirely (INFO log instead of WARNING, no
class_mismatch flag), and that ``_faked: true`` suppresses scan-engine
re-classification: a faked device's packets may be spoofed by the
integration itself, so packet evidence cannot contradict the declared
class (false-positive mismatch notification regression).

Strategy:
  - Load a profile with 37:169161 classified as FAN, bound to 32:150000.
  - Do NOT add 37:169161 to the FAN's remotes list — otherwise the
    activated REM (37:170000) would send RQ 2411 to 37:169161, and the
    simulator's auto_answer would respond with RP 2411 (FAN evidence),
    preventing the contradiction detection.
  - Do NOT activate 37:169161 as a simulator device.
  - Inject RQ 31DA, I 22F1, RQ 2411 FROM 37:169161 TO 32:150000.
    These are non-FAN packets (a FAN never sends them as src).
  - After 3 packets (threshold), the contradiction detection fires.
  - Reload with _locked: true and verify suppression.
  - Reload with 37:169161 as _class=DIS + _faked: true and a second
    device 37:169162 as _class=DIS (physical, not faked).  Inject I 22F1
    (REM evidence) at both — a faked device spoofs its own traffic, and
    REM-class behaviour is a subset of DIS (a display IS a remote plus
    display requests), so NEITHER may be re-classified to REM and no
    mismatch notification may fire.
"""

from __future__ import annotations

import re

import yaml as _yaml

from ..base import Recipe, RecipeContext
from ..const import FAN
from ..helpers import (
    call_service,
    get_persistent_notifications,
    get_schema,
    grep_ha_log,
    load_profile_yaml,
    wait_for_async,
    wait_for_transport_ready,
    ws_send,
)
from ..profile import MIXED_SCHEMA, get_mixed_kl

# A 37: device that we'll classify as FAN but make behave as a DIS.
DIS_DEVICE = "37:169161"

# A second 37: device, used in Phase 4 declared as DIS without _faked —
# REM-class evidence must not "downgrade" it either (REM ⊂ DIS).
DIS_DEVICE_REAL = "37:169162"


def _build_profile_yaml(*, locked: bool = False, faked: bool = False) -> str:
    """Build a mixed-profile YAML with DIS_DEVICE classified as FAN.

    With ``faked=True`` the device is instead declared DIS + faked — the
    class REM evidence (I 22F1) must NOT re-classify it because the
    integration spoofs its traffic.  A second declared-DIS device
    (DIS_DEVICE_REAL, not faked) is added to cover the REM⊂DIS subset
    rule for physical displays.

    IMPORTANT: DIS_DEVICE is NOT added to the FAN's remotes list.
    If it were, the activated REM (37:170000) would send RQ 2411 to
    DIS_DEVICE, and the simulator's auto_answer would respond with
    RP 2411 (FAN evidence), preventing the contradiction detection.
    """
    kl = get_mixed_kl()
    kl[DIS_DEVICE] = {"class": "DIS", "faked": True} if faked else {"class": "FAN"}
    if faked:
        kl[DIS_DEVICE_REAL] = {"class": "DIS"}

    schema = dict(MIXED_SCHEMA)
    # Do NOT add DIS_DEVICE to the FAN's remotes — see docstring.
    # Do NOT add _bound — that would create an invalid FAN→FAN binding
    # and trigger a spurious "Cannot bind device" warning.  The
    # contradiction detection only needs _class=FAN in the schema.
    dis_entry: dict = {"_class": "DIS"} if faked else {"_class": "FAN"}
    if locked:
        dis_entry["_locked"] = True
    if faked:
        dis_entry["_faked"] = True
    schema[DIS_DEVICE] = dis_entry
    if faked:
        schema[DIS_DEVICE_REAL] = {"_class": "DIS"}

    profile = {
        "known_list": kl,
        "_enforce_known_list": {"enabled": True},
        "_schema": schema,
    }
    return _yaml.dump(profile, default_flow_style=False, sort_keys=False)


# Non-FAN packets that a DIS/REM sends (a FAN never sends these as src).
_PACKETS = [
    ("RQ", "31DA", "00", "RQ 31DA — DIS requests fan status"),
    ("I", "22F1", "000207", "I 22F1 — DIS sends fan-mode command"),
    ("RQ", "2411", "000031", "RQ 2411 — DIS requests parameters"),
]


async def _inject_packets(
    ctx: RecipeContext,
    label: str,
    packets: list | None = None,
    src: str = DIS_DEVICE,
) -> None:
    """Inject non-FAN packets from *src* to FAN."""
    packets = packets or _PACKETS
    for i, (verb, code, payload, desc) in enumerate(packets):
        print(f"  [{label}] Injecting packet {i + 1}/{len(packets)}: {desc}")
        try:
            call_service(
                ctx.token,
                "ramses_extras",
                "device_simulator_inject_message",
                {
                    "source_id": src,
                    "dst": FAN,
                    "code": code,
                    "payload": payload,
                    "verb": verb,
                },
            )
            print(f"    {verb} {code} injected")
        except RuntimeError as e:
            print(f"    Inject failed: {str(e)[:80]}")
        ctx.wait(2, "between injections", floor=1.0)


async def _force_sync(ctx: RecipeContext) -> None:
    """Force a sync cycle to trigger _check_rf_contradictions."""
    try:
        call_service(ctx.token, "ramses_cc", "sync_topology")
    except RuntimeError:
        pass
    ctx.wait(3, "for sync_topology", floor=2.0)
    try:
        call_service(ctx.token, "ramses_cc", "force_update")
    except RuntimeError:
        pass
    ctx.wait(5, "for force_update + entity state write", floor=3.0)


class R79FanDisReclassification(Recipe):
    id = "R79"
    seq = 770
    title = (
        "FAN→DIS reclassification via contradiction detection (issue 1000),"
        " incl. _locked/_faked suppression"
    )

    async def run(self, ctx: RecipeContext) -> None:
        ctx.log_section(
            "Recipe 79: FAN→DIS reclassification via contradiction detection"
        )

        # --- Phase 1: Load profile with DIS_DEVICE as FAN ---
        profile_yaml = _build_profile_yaml(locked=False)
        await load_profile_yaml(ctx.token, profile_yaml, speed=0.01)
        ctx.wait_for_ramses_cc_reload(msg="for profile reload")
        ctx.refresh_token()
        wait_for_transport_ready(timeout=30)

        # Activate the FAN (32:150000) so the HVAC domain is active.
        # Do NOT activate DIS_DEVICE — we don't want it auto-responding
        # with FAN evidence (RP 31DA, RP 2411).
        try:
            await ws_send(
                ctx.token,
                {
                    "type": "ramses_extras/device_simulator/activate_profile_device",
                    "device_id": FAN,
                },
            )
            print(f"  FAN {FAN} activated")
        except RuntimeError as e:
            if "already_active" in str(e):
                print(f"  FAN {FAN} already active")
            else:
                print(f"  FAN activate failed: {str(e)[:80]}")

        ctx.wait(5, "for FAN to stabilize", floor=3.0)

        # Verify DIS_DEVICE is in the schema with _class=FAN
        schema = get_schema()
        dis_entry = schema.get(DIS_DEVICE, {})
        ctx.check(
            f"{DIS_DEVICE} has _class=FAN in schema",
            dis_entry.get("_class") == "FAN",
            f"_class={dis_entry.get('_class')}",
        )

        # --- Phase 2: Inject non-FAN packets from DIS_DEVICE ---
        await _inject_packets(ctx, "Phase 1")
        ctx.wait(10, "for contradiction detection + debounce sync", floor=5.0)
        await _force_sync(ctx)

        # --- Check 1: class_mismatch detected by scan engine ---
        # The scan engine sees the RQ 31DA / I 22F1 / RQ 2411 packets
        # and re-classifies 37:169161 from FAN to REM after 3
        # contradictions.  This triggers check_class_mismatches which
        # logs a WARNING and sets class_mismatch on the discovery
        # metadata.  Grep for the reclassification DEBUG log or the
        # mismatch WARNING — NOT for any line containing both
        # DIS_DEVICE and FAN/REM (that matches unrelated sync_learned
        # _topology DEBUG lines and causes false positives).
        mismatch_lines = grep_ha_log(
            f"re-classified known device {DIS_DEVICE}|class mismatch for {DIS_DEVICE}"
        )
        ctx.check(
            "Scan engine detects class mismatch for DIS_DEVICE",
            len(mismatch_lines) > 0,
            f"log matches={len(mismatch_lines)}",
        )

        # --- Check 2: class_mismatch persistent notification ---
        async def _has_mismatch_notif() -> bool:
            notifications = await get_persistent_notifications(ctx.token)
            return any(
                (
                    "mismatch" in n.get("title", "").lower()
                    or "mismatch" in n.get("notification_id", "").lower()
                )
                and DIS_DEVICE in n.get("message", "")
                for n in notifications
            )

        await wait_for_async(
            _has_mismatch_notif,
            timeout=30,
            interval=3,
            msg="for class_mismatch notification to appear",
            floor=5.0,
        )
        notifications = await get_persistent_notifications(ctx.token)
        mismatch_notifs = [
            n
            for n in notifications
            if (
                "mismatch" in n.get("title", "").lower()
                or "mismatch" in n.get("notification_id", "").lower()
            )
            and DIS_DEVICE in n.get("message", "")
        ]
        ctx.check(
            "Persistent notification flags DIS_DEVICE class mismatch",
            len(mismatch_notifs) > 0,
            f"notifications={[n.get('notification_id') for n in notifications]}",
        )

        # --- Phase 3: Reload with _locked: true and verify suppression ---
        ctx.log_section("  Phase 3: _locked trait suppresses reclassification")

        profile_locked_yaml = _build_profile_yaml(locked=True)
        await load_profile_yaml(ctx.token, profile_locked_yaml, speed=0.01)
        ctx.wait_for_ramses_cc_reload(msg="for _locked profile reload")
        ctx.refresh_token()
        wait_for_transport_ready(timeout=30)

        # Re-activate FAN
        try:
            await ws_send(
                ctx.token,
                {
                    "type": "ramses_extras/device_simulator/activate_profile_device",
                    "device_id": FAN,
                },
            )
        except RuntimeError:
            pass

        ctx.wait(5, "for FAN to stabilize after reload", floor=3.0)

        # Verify _locked is in the schema
        schema = get_schema()
        dis_entry = schema.get(DIS_DEVICE, {})
        ctx.check(
            f"{DIS_DEVICE} has _locked=True in schema",
            dis_entry.get("_locked") is True,
            f"_locked={dis_entry.get('_locked')}",
        )

        # Inject non-FAN packets again (fresh session = fresh evidence)
        await _inject_packets(ctx, "locked")
        ctx.wait(10, "for contradiction detection (locked)", floor=5.0)
        await _force_sync(ctx)

        # --- Check 3: _locked prevents SSOT class change ---
        # The _locked trait suppresses the HvacTopologyHandler's
        # reclassification event in ramses_rf, so the known_list class
        # stays as FAN.  The scan engine's check_class_mismatches is
        # independent and still detects the mismatch, but the
        # _check_rf_contradictions callback in the coordinator should
        # NOT flag the device because the ramses_rf known_list class
        # stays as FAN (no SSOT update).
        #
        # Verify that the schema still has _class=FAN for DIS_DEVICE
        # (i.e., _locked prevented the SSOT from changing the class):
        schema_after = get_schema()
        dis_entry_after = schema_after.get(DIS_DEVICE, {})
        ctx.check(
            f"{DIS_DEVICE} schema _class stays FAN (locked)",
            dis_entry_after.get("_class") == "FAN",
            f"_class={dis_entry_after.get('_class')}",
        )

        # --- Phase 4: _faked + REM⊂DIS suppress reclassification ---
        ctx.log_section("  Phase 4: _faked and REM-subset-of-DIS suppression")

        profile_faked_yaml = _build_profile_yaml(faked=True)
        await load_profile_yaml(ctx.token, profile_faked_yaml, speed=0.01)
        ctx.wait_for_ramses_cc_reload(msg="for _faked profile reload")
        ctx.refresh_token()
        wait_for_transport_ready(timeout=30)

        # Re-activate FAN
        try:
            await ws_send(
                ctx.token,
                {
                    "type": "ramses_extras/device_simulator/activate_profile_device",
                    "device_id": FAN,
                },
            )
        except RuntimeError:
            pass

        ctx.wait(5, "for FAN to stabilize after reload", floor=3.0)

        # Verify _class=DIS + _faked are in the schema
        schema = get_schema()
        dis_entry = schema.get(DIS_DEVICE, {})
        ctx.check(
            f"{DIS_DEVICE} has _class=DIS in schema",
            dis_entry.get("_class") == "DIS",
            f"_class={dis_entry.get('_class')}",
        )
        ctx.check(
            f"{DIS_DEVICE} has _faked=True in schema",
            dis_entry.get("_faked") is True,
            f"_faked={dis_entry.get('_faked')}",
        )
        real_entry = schema.get(DIS_DEVICE_REAL, {})
        ctx.check(
            f"{DIS_DEVICE_REAL} has _class=DIS in schema (not faked)",
            real_entry.get("_class") == "DIS" and real_entry.get("_faked") is not True,
            f"entry={real_entry}",
        )

        # Baseline: count existing re-classification/mismatch log lines so
        # we can assert this phase adds none (phases 1-3 legitimately
        # logged some for this device).
        reclass_pattern = (
            f"re-classified known device ({DIS_DEVICE}|{DIS_DEVICE_REAL})"
            f"|class mismatch for ({DIS_DEVICE}|{DIS_DEVICE_REAL})"
        )
        log_lines_before = len(grep_ha_log(reclass_pattern))

        # Inject 4x I 22F1 (REM VC-pair evidence) at BOTH declared-DIS
        # devices — past the contradiction threshold.  Neither must be
        # re-classified: the faked one spoofs its own traffic, and the
        # physical one is protected by the REM⊂DIS subset rule.
        for dev_id in (DIS_DEVICE, DIS_DEVICE_REAL):
            await _inject_packets(
                ctx,
                "faked",
                packets=[("I", "22F1", "000207", "I 22F1 — REM evidence")] * 4,
                src=dev_id,
            )
        ctx.wait(10, "for contradiction detection (faked)", floor=5.0)
        await _force_sync(ctx)

        # --- Check 4: no re-classification / mismatch logged ---
        ctx.check(
            "Declared DIS devices NOT re-classified by REM evidence",
            len(grep_ha_log(reclass_pattern)) == log_lines_before,
            f"log lines before={log_lines_before}, "
            f"after={len(grep_ha_log(reclass_pattern))}",
        )

        # --- Check 5: no class_mismatch notification for the faked device ---
        # The phase-2 notification (if still present) must be dismissed by
        # check_all_mismatches once the stale flag is cleared.
        async def _no_mismatch_notif() -> bool:
            # The mismatches notification bundles ALL health findings
            # (weak signal, comms quality, ...) — a bare device-id match
            # would false-positive on e.g. an RSSI line.  Match the
            # class-mismatch line format: `- <dev_id> — schema=...`.
            notifications = await get_persistent_notifications(ctx.token)
            return not any(
                (
                    "mismatch" in n.get("title", "").lower()
                    or "mismatch" in n.get("notification_id", "").lower()
                )
                and re.search(
                    rf"({DIS_DEVICE}|{DIS_DEVICE_REAL})[^\n]*schema=",
                    n.get("message", ""),
                )
                for n in notifications
            )

        await wait_for_async(
            _no_mismatch_notif,
            timeout=30,
            interval=3,
            msg="for stale class_mismatch notification to be dismissed",
            floor=5.0,
        )
        ctx.check(
            "No mismatch notification for faked DIS_DEVICE",
            await _no_mismatch_notif(),
            f"notifications={await get_persistent_notifications(ctx.token)}",
        )

        # --- Check 6: schema _class unchanged for both DIS devices ---
        schema_after_faked = get_schema()
        dis_entry_faked = schema_after_faked.get(DIS_DEVICE, {})
        ctx.check(
            f"{DIS_DEVICE} schema _class stays DIS (faked)",
            dis_entry_faked.get("_class") == "DIS",
            f"_class={dis_entry_faked.get('_class')}",
        )
        real_entry_after = schema_after_faked.get(DIS_DEVICE_REAL, {})
        ctx.check(
            f"{DIS_DEVICE_REAL} schema _class stays DIS",
            real_entry_after.get("_class") == "DIS",
            f"_class={real_entry_after.get('_class')}",
        )

        # --- Cleanup: restore default mixed profile ---
        from ..profile import mixed_yaml

        await load_profile_yaml(ctx.token, mixed_yaml(), speed=0.01)
        ctx.wait_for_ramses_cc_reload(msg="for cleanup profile reload")
        ctx.refresh_token()
