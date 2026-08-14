"""Recipe R74: Manual placement preserved + comment staleness (issue 931)."""

from __future__ import annotations

import json

import yaml as _yaml

from ..base import Recipe, RecipeContext
from ..const import CTL, DHW
from ..helpers import (
    call_service,
    clear_cached_state,
    get_current_instance,
    get_schema_retry,
    load_profile_yaml,
    wait_for,
    wait_for_schema_populated,
    ws_send,
)
from ..profile import MIXED_SCHEMA, get_mixed_kl


class R74ManualPlacementPreservedCommentStalenessIssue931(Recipe):
    id = "R74"
    seq = 740
    title = "Manual placement preserved + comment staleness (issue 931)"

    async def run(self, ctx: RecipeContext) -> None:
        # Issue 931 has two fixes beyond the domain_id placement (R73):
        #
        # 1. Manual placement preservation: when the learned schema has
        #    valve=None (device not yet discovered by ramses_rf), the
        #    user's manual valve placement in the config schema is
        #    preserved.  Previously, sync_learned_topology would null
        #    the valve whenever the learned schema had valve=None, even
        #    when ramses_rf simply hadn't captured a 000C binding yet.
        #
        # 2. Comment staleness fix: when a 000C binding arrives
        #    (is_authoritative_domain=True), the device comment is
        #    rebuilt to show the confident domain classification instead
        #    of the hedged 3B00/3EF0 hint.
        #
        # This recipe tests both:
        #   Step 1: Manually place a BDR as hotwater_valve in the config
        #     schema.  Do NOT inject any 000C binding.  Trigger
        #     sync_learned_topology.  The manual placement must survive
        #     (the device is not placed elsewhere in the learned schema).
        #   Step 2: Inject 3B00/3EF0 (non-authoritative FC hint).  Check
        #     that the comment shows the hedged hint phrasing.
        #   Step 3: Inject 000C with FA domain (authoritative).  Check
        #     that the comment is rebuilt with authoritative phrasing.
        ctx.log_section(
            "Recipe 74: Manual placement preserved + comment staleness (issue 931)"
        )

        bdr_id = "13:093104"
        # hex_id = (13 << 18) + 93104 = 3500976 = 0x356BB0
        hex_id = "356BB0"

        # --- Clear cached state ---
        print("  Stopping ha-sim and clearing cached state...")
        clear_cached_state(ctx.log_monitor, label="R74 pre-restart")
        ctx.wait_for_ha_ready(timeout=30)
        ctx.log_monitor.reset_baseline()
        ctx.refresh_token()
        ctx.wait_for_ramses_cc_loaded(timeout=30)

        # --- Build a custom profile with manual hotwater_valve placement ---
        # The BDR is manually placed as hotwater_valve in the config schema.
        # No 000C binding will be injected in step 1, so the learned schema
        # will have valve=None.  The manual placement must survive sync.
        schema_r74 = dict(MIXED_SCHEMA)
        ctl_schema = dict(schema_r74.get(CTL, {}))
        # Clear system, set manual hotwater_valve placement
        ctl_schema["system"] = {}
        ctl_schema["stored_hotwater"] = {
            "sensor": DHW,
            "hotwater_valve": bdr_id,  # manual placement
        }
        schema_r74[CTL] = ctl_schema
        schema_r74[bdr_id] = {}

        kl_r74 = get_mixed_kl()
        kl_r74[bdr_id] = {"class": "BDR"}

        profile_r74 = {
            "known_list": kl_r74,
            "_enforce_known_list": {"enabled": True},
            "_schema": schema_r74,
        }
        yaml_text = _yaml.dump(profile_r74, default_flow_style=False, sort_keys=False)

        print("  Loading profile (BDR manually placed as hotwater_valve)...")
        try:
            await load_profile_yaml(ctx.token, yaml_text, speed=0.01)
            print("  Profile loaded")
        except RuntimeError as e:
            print(f"  Profile load failed: {e}")
        ctx.wait_for_ramses_cc_reload(timeout=30)
        ctx.refresh_token()

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
        wait_for_schema_populated(timeout=20)

        # --- Step 1: Trigger sync_topology without 000C binding ---
        # The learned schema will have valve=None (no 000C captured).
        # The manual placement must survive.
        print("  Step 1: Triggering sync_topology (no 000C binding yet)...")
        try:
            call_service(ctx.token, "ramses_cc", "sync_topology")
        except RuntimeError:
            pass

        # Wait for sync to complete
        wait_for(
            lambda: _schema_stable(get_schema_retry()),
            timeout=15,
            interval=2,
            msg="for schema to stabilise after sync",
        )

        schema_step1 = get_schema_retry()
        ctl_step1 = schema_step1.get(CTL, {})
        dhw_step1 = (
            ctl_step1.get("stored_hotwater", {}) if isinstance(ctl_step1, dict) else {}
        )

        print("  After sync (no 000C):")
        print(f"    stored_hotwater = {json.dumps(dhw_step1)[:120]}")

        # Check 1: Manual hotwater_valve placement preserved
        ctx.check(
            f"Manual hotwater_valve placement for {bdr_id} preserved "
            "(no 000C binding, device not placed elsewhere)",
            dhw_step1.get("hotwater_valve") == bdr_id,
            f"hotwater_valve={dhw_step1.get('hotwater_valve')}",
        )

        # --- Step 2: Inject 3B00/3EF0 (non-authoritative FC hint) ---
        # The BDR is in the known_list, so the scan engine tracks it as
        # a known device.  3B00/3EF0 gives a non-authoritative FC hint.
        print("  Step 2: Injecting 3B00/3EF0 (non-authoritative FC hint)...")
        for code in ("3B00", "3EF0"):
            try:
                call_service(
                    ctx.token,
                    "ramses_extras",
                    "device_simulator_inject_message",
                    {
                        "source_id": bdr_id,
                        "code": code,
                        "payload": "00C8",
                        "verb": "I",
                    },
                )
                print(f"    {code} I injected from {bdr_id}")
            except RuntimeError:
                pass

        # Wait for scan engine to process
        ctx.wait(5, "for scan engine to process 3B00/3EF0")

        try:
            call_service(ctx.token, "ramses_cc", "sync_topology")
        except RuntimeError:
            pass

        wait_for(
            lambda: _schema_stable(get_schema_retry()),
            timeout=15,
            interval=2,
            msg="for schema to stabilise after 3B00/3EF0",
        )

        schema_step2 = get_schema_retry()
        ctl_step2 = schema_step2.get(CTL, {})
        dhw_step2 = (
            ctl_step2.get("stored_hotwater", {}) if isinstance(ctl_step2, dict) else {}
        )
        comments_step2 = schema_step2.get("device_comments", {})
        comment_step2 = comments_step2.get(bdr_id, "")

        print("  After 3B00/3EF0 (non-authoritative hint):")
        print(f"    stored_hotwater = {json.dumps(dhw_step2)[:120]}")
        print(f"    comment = {comment_step2[:120]}")

        # Check 2: Manual placement still preserved (3B00/3EF0 is not
        # authoritative, so it must not override the manual placement)
        ctx.check(
            f"Manual hotwater_valve placement for {bdr_id} still preserved "
            "after 3B00/3EF0 (non-authoritative hint)",
            dhw_step2.get("hotwater_valve") == bdr_id,
            f"hotwater_valve={dhw_step2.get('hotwater_valve')}",
        )

        # Check 3: Comment shows hedged/non-authoritative phrasing
        # The comment should mention "domain FC" but with hedged language
        # (e.g. "hint" or "could be" or "awaiting 000C")
        # Note: the BDR is declared as hotwater_valve in the schema, so
        # the scan engine suppresses the FC hint (issue 834).  The comment
        # may not contain "domain FC" at all if the schema_role is
        # hotwater_valve.  In that case, we check that the comment does
        # NOT contain authoritative phrasing (no "domain FA" without
        # hedged language).
        has_fc_hint = "domain FC" in comment_step2
        has_hedged = any(
            w in comment_step2.lower() for w in ("hint", "could be", "awaiting")
        )
        has_authoritative_fa = (
            "domain FA" in comment_step2
            and "hint" not in comment_step2.lower()
            and "could be" not in comment_step2.lower()
        )
        ctx.check(
            f"Comment for {bdr_id} shows non-authoritative phrasing "
            "(hedged FC hint or no domain claim)",
            (has_fc_hint and has_hedged)
            or (not has_fc_hint and not has_authoritative_fa),
            f"comment={comment_step2[:120]}",
        )

        # --- Step 3: Inject 000C with FA domain (authoritative) ---
        # This confirms the BDR as hotwater_valve (FA domain, authoritative)
        # via the learned schema.  The 000C RP is sent from the CTL, so the
        # scan engine sets domain_id on the CTL (not on the BDR in the
        # payload).  The comment staleness fix (issue 931) rebuilds the
        # CTL's comment with authoritative phrasing.
        fa_payload = f"000E00{hex_id}"
        print(
            f"  Step 3: Injecting 000C RP (FA/hotwater_valve) from CTL for {bdr_id}..."
        )
        print(f"    payload: {fa_payload}")

        _retry_count = 0

        def _000c_processed() -> bool:
            nonlocal _retry_count
            try:
                call_service(
                    ctx.token,
                    "ramses_extras",
                    "device_simulator_inject_message",
                    {
                        "source_id": CTL,
                        "dst": get_current_instance().hgi_id,
                        "code": "000C",
                        "payload": fa_payload,
                        "verb": "RP",
                    },
                )
            except RuntimeError:
                pass
            _retry_count += 1
            if _retry_count % 2 == 0:
                try:
                    call_service(ctx.token, "ramses_cc", "sync_topology")
                except RuntimeError:
                    pass
            # Check if CTL comment has been rebuilt with authoritative
            # phrasing (the scan engine sets domain_id on the CTL, not
            # the BDR in the payload).
            schema = get_schema_retry()
            comments = schema.get("device_comments", {})
            ctl_comment = comments.get(CTL, "")
            return "domain FA" in ctl_comment and "hint" not in ctl_comment.lower()

        wait_for(
            _000c_processed,
            timeout=45,
            interval=3,
            msg="for 000C FA to update CTL comment (authoritative)",
            floor=10.0,
        )

        schema_step3 = get_schema_retry()
        ctl_step3 = schema_step3.get(CTL, {})
        dhw_step3 = (
            ctl_step3.get("stored_hotwater", {}) if isinstance(ctl_step3, dict) else {}
        )
        comments_step3 = schema_step3.get("device_comments", {})
        ctl_comment_step3 = comments_step3.get(CTL, "")

        print("  After 000C FA (authoritative):")
        print(f"    stored_hotwater = {json.dumps(dhw_step3)[:120]}")
        print(f"    CTL comment = {ctl_comment_step3[:120]}")

        # Check 4: BDR still hotwater_valve (000C FA confirms placement)
        ctx.check(
            f"BDR {bdr_id} is hotwater_valve (confirmed by 000C FA)",
            dhw_step3.get("hotwater_valve") == bdr_id,
            f"hotwater_valve={dhw_step3.get('hotwater_valve')}",
        )

        # Check 5: CTL comment rebuilt with authoritative FA phrasing
        # (issue 931 comment staleness fix — the 000C sets
        # is_authoritative_domain=True on the CTL, forcing a rebuild)
        ctx.check(
            "CTL comment rebuilt with authoritative FA phrasing "
            "(issue 931 comment staleness fix)",
            "domain FA" in ctl_comment_step3
            and "hint" not in ctl_comment_step3.lower(),
            f"comment={ctl_comment_step3[:120]}",
        )


def _schema_stable(schema: dict, min_keys: int = 5) -> bool:
    """Quick check that schema has enough keys."""
    return len(schema) >= min_keys
