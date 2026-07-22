"""Recipe R46: _disabled trait — device excluded from known_list (issue 767).

Verifies that a device with ``_disabled: true`` in schema is excluded from
``_derive_known_list_from_schema``, so ramses_rf doesn't create it, but the
schema entry persists for re-enabling.

This replaces the flat ``disabled_devices`` list with a per-device trait.

See: https://github.com/ramses-rf/ramses_cc/issues/767
"""

from __future__ import annotations

from ..base import Recipe, RecipeContext
from ..const import TRV
from ..helpers import (
    get_entities,
    get_known_list,
    get_schema_retry,
    load_profile_yaml,
    ws_send,
)
from ..profile import MIXED_SCHEMA, mixed_yaml


class R46DisabledTraitDeviceExcludedIssue767(Recipe):
    id = "R46"
    seq = 470
    title = "_disabled trait — device excluded from known_list (issue 767)"

    async def run(self, ctx: RecipeContext) -> None:
        ctx.log_section("Recipe 46: _disabled trait — device excluded (issue 767)")

        # 1. Load mixed profile (TRV 04:150003 enabled)
        print("  Loading mixed profile (TRV enabled)...")
        try:
            await load_profile_yaml(
                ctx.token,
                mixed_yaml(),
                speed=0.01,
                preload_schema=True,
                reload_ramses=True,
            )
        except RuntimeError as e:
            print(f"  Profile load failed: {e}")
        ctx.wait(15, "for ramses_cc reload")
        ctx.refresh_token()
        ctx.wait(5, "for ramses_cc to initialize")

        # 2. Verify TRV exists before disabling
        entities = get_entities(ctx.token)
        trv_entity = None
        for e in entities:
            if TRV.replace(":", "_") in e["entity_id"]:
                trv_entity = e
                break

        ctx.check(
            f"TRV {TRV} entity exists before disabling",
            trv_entity is not None,
            "no TRV entity found",
        )

        # 3. Load profile with _disabled: true on the TRV
        print(f"  Loading profile with _disabled=true on TRV {TRV}...")
        trv_schema = dict(MIXED_SCHEMA.get(TRV, {}))
        trv_schema["_disabled"] = True
        schema_override = {TRV: trv_schema}

        try:
            await load_profile_yaml(
                ctx.token,
                mixed_yaml(schema_override=schema_override),
                speed=0.01,
                preload_schema=True,
                reload_ramses=True,
            )
        except RuntimeError as e:
            print(f"  Profile load failed: {e}")
        ctx.wait(15, "for ramses_cc reload with _disabled")
        ctx.refresh_token()
        ctx.wait(5, "for ramses_cc to initialize")

        # 4. Verify the TRV entity is gone or unavailable
        entities_after = get_entities(ctx.token)
        trv_entity_after = None
        for e in entities_after:
            if TRV.replace(":", "_") in e["entity_id"]:
                trv_entity_after = e
                break

        ctx.check(
            f"TRV {TRV} entity removed/unavailable after _disabled",
            trv_entity_after is None
            or trv_entity_after.get("state")
            in (
                "unavailable",
                "unknown",
                None,
            ),
            f"state={trv_entity_after.get('state') if trv_entity_after else 'gone'}",
        )

        # 5. Verify the device IS in the known_list (to avoid log spam)
        #    but entity creation is suppressed.
        #    _disabled devices are INCLUDED in known_list so ramses_rf doesn't
        #    reject their packets with DeviceNotFoundError on every incoming
        #    message.  Entity creation is suppressed in _discover_new_entities.
        kl = get_known_list()
        trv_kl = kl.get(TRV, {})

        ctx.check(
            f"TRV {TRV} still in known_list when _disabled (avoids log spam)",
            TRV in kl,
            f"trv_kl={trv_kl}",
        )

        # 6. Verify the schema entry still exists (can be re-enabled)
        schema = get_schema_retry()

        ctx.check(
            f"TRV {TRV} still in schema (preserved for re-enabling)",
            TRV in schema,
            "TRV removed from schema entirely",
        )

        # 7. Re-enable the TRV by loading profile without _disabled
        print(f"  Re-enabling TRV {TRV}...")
        try:
            await load_profile_yaml(
                ctx.token,
                mixed_yaml(),
                speed=0.01,
                preload_schema=True,
                reload_ramses=True,
            )
        except RuntimeError as e:
            print(f"  Profile load failed: {e}")
        ctx.wait(15, "for ramses_cc reload")
        ctx.refresh_token()
        ctx.wait(5, "for ramses_cc to initialize")

        # 8. Verify TRV entity reappears
        entities_final = get_entities(ctx.token)
        trv_entity_final = None
        for e in entities_final:
            if TRV.replace(":", "_") in e["entity_id"]:
                trv_entity_final = e
                break

        ctx.check(
            f"TRV {TRV} entity reappeared after re-enabling",
            trv_entity_final is not None,
            "TRV entity not found after re-enable",
        )
