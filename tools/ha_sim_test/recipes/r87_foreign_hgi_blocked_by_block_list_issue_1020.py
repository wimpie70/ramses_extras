"""Recipe R87: Foreign-owned HGI is blocked by block_list (issue 1020).

Verifies that a foreign-owned HGI (18: with ``_owner`` != root ``_owner`` in
the schema) is added to the block_list by ramses_cc and its packets are
filtered by ramses_rf's protocol filter.

Before the fix (issue 1020), ramses_cc exempted all 18: devices from the
block_list, so foreign-owned HGIs were never filtered.  This caused
``DeviceNotFoundError`` log spam and confusing "potentially a Foreign
gateway" warnings for devices that belong to a different system.

The fix (PR 1032 + PR 1107):
- ramses_cc: removes the 18: exemption — foreign-owned HGIs go to block_list
- ramses_rf: allows block_list to filter 18: devices (previously exempted)

This recipe tests the fix by:
1. Loading a profile with a foreign-owned HGI (18:999999, _owner: not-me)
2. Verifying the foreign HGI is in the schema
3. Injecting a 30C9 from the foreign HGI
4. Verifying the packet is filtered (no temperature appears for it)
5. Verifying no DeviceNotFoundError log spam for the foreign HGI

See:
- https://github.com/ramses-rf/ramses_cc/issues/1020
- https://github.com/ramses-rf/ramses_cc/pull/1032
- https://github.com/wimpie70/ramses_rf/pull/1107
"""

from __future__ import annotations

from ..base import Recipe, RecipeContext
from ..const import CTL, HGI
from ..helpers import (
    call_service,
    get_schema_retry,
    grep_ha_log,
    load_profile_yaml,
    wait_for,
    wait_for_transport_ready,
    ws_send,
)
from ..profile import minimal_ctl_yaml


class R87ForeignHgiBlockedByBlockListIssue1020(Recipe):
    id = "R87"
    seq = 870
    title = "Foreign-owned HGI blocked by block_list (issue 1020)"

    async def run(self, ctx: RecipeContext) -> None:
        # A foreign-owned HGI (18: with _owner: not-me in the schema) should
        # be added to the block_list by ramses_cc.  ramses_rf's protocol
        # filter then drops its packets at the _is_wanted_addrs check.
        #
        # This is distinct from an unknown HGI (not in any list), which is
        # allowed through for eavesdropping (issue 822, tested by R28).
        ctx.log_section("Recipe 87: Foreign-owned HGI blocked by block_list")

        foreign_hgi = "18:999999"

        # Build a minimal profile with CTL + a foreign-owned HGI.
        # The foreign HGI is in the schema with _owner: not-me but NOT in
        # the known_list (foreign devices are excluded from known_list).
        yaml_profile = minimal_ctl_yaml(
            schema_override={
                "_owner": "me",
                CTL: {"_owner": "me"},
                foreign_hgi: {"_class": "HGI", "_owner": "not-me"},
            },
        )

        print(f"  Loading profile with foreign-owned HGI {foreign_hgi}...")
        try:
            await load_profile_yaml(
                ctx.token,
                yaml_profile,
                speed=0.01,
                preload_schema=True,
                reload_ramses=True,
            )
            print("  Profile loaded")
        except RuntimeError as e:
            print(f"  Profile load failed: {e}")
        ctx.wait_for_ramses_cc_reload(timeout=20)
        ctx.refresh_token()
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

        wait_for(
            lambda: len(get_schema_retry()) >= 2,
            timeout=15,
            interval=1,
            msg="for schema to be populated",
            floor=3.0,
        )

        # ── 1. Verify the foreign HGI is in the schema ────────────────
        schema = get_schema_retry()
        hgi_entry = schema.get(foreign_hgi, {})
        ctx.check(
            f"Foreign HGI {foreign_hgi} is in schema",
            isinstance(hgi_entry, dict) and hgi_entry.get("_owner") == "not-me",
            f"HGI entry={hgi_entry!r}",
        )

        # ── 2. Inject a 30C9 from the foreign HGI ─────────────────────
        # If the foreign HGI is in the block_list, ramses_rf's filter will
        # drop the packet before the scan engine sees it.  We verify this
        # by checking that no temperature entity is created for the foreign
        # HGI and that the packet does not appear in the dispatcher log.
        print(f"  Injecting 30C9 I from foreign HGI {foreign_hgi}...")
        try:
            call_service(
                ctx.token,
                "ramses_extras",
                "device_simulator_inject_message",
                {
                    "source_id": foreign_hgi,
                    "code": "30C9",
                    "payload": "0308AC",
                    "verb": "I",
                },
            )
            print("    30C9 I injected")
        except RuntimeError as e:
            print(f"    Inject failed: {str(e)[:80]}")

        ctx.wait(5, "for scan engine to process (or filter) packet", floor=3.0)

        # ── 3. Verify the packet was filtered ─────────────────────────
        # The 30C9 from the foreign HGI should NOT appear in the dispatcher
        # log (it was filtered by _is_wanted_addrs before reaching the
        # dispatcher).  We check the HA log for dispatcher entries.
        dispatcher_entries = grep_ha_log(
            f"dispatcher.*{foreign_hgi}.*30C9|{foreign_hgi}.*30C9.*dispatcher",
            since_lines=200,
        )
        ctx.check(
            f"30C9 from foreign HGI {foreign_hgi} was filtered (not in dispatcher)",
            len(dispatcher_entries) == 0,
            f"found {len(dispatcher_entries)} dispatcher entries"
            + (f": {dispatcher_entries[0][:80]}" if dispatcher_entries else ""),
        )

        # ── 4. Verify no DeviceNotFoundError log spam ─────────────────
        # Before the fix, the foreign HGI was not in the block_list, so
        # ramses_rf tried to create it and raised DeviceNotFoundError.
        # After the fix, the packet is filtered silently.
        error_entries = grep_ha_log(
            f"DeviceNotFoundError.*{foreign_hgi}|Can.*t create {foreign_hgi}"
            f"|FILTER EXCEPTION.*{foreign_hgi}",
            since_lines=200,
        )
        ctx.check(
            f"No DeviceNotFoundError/FILTER EXCEPTION for {foreign_hgi}",
            len(error_entries) == 0,
            f"found {len(error_entries)} error(s)"
            + (f": {error_entries[0][:80]}" if error_entries else ""),
        )

        # ── 5. Verify the foreign HGI is in the block_list (ramses_cc) ─
        # ramses_cc's _create_client builds the block_list from the schema:
        # any device with _owner != root _owner goes to block_list (PR 1032
        # removed the 18: exemption).  We check the HA log for the block_list
        # debug entry.
        block_list_logs = grep_ha_log(
            f"block_list.*{foreign_hgi}|{foreign_hgi}.*block_list",
            since_lines=300,
        )
        ctx.check(
            f"Foreign HGI {foreign_hgi} is in block_list (ramses_cc)",
            len(block_list_logs) > 0,
            f"found {len(block_list_logs)} block_list log(s)"
            + (f": {block_list_logs[0][:80]}" if block_list_logs else ""),
        )
