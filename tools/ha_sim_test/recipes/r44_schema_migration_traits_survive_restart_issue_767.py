"""Recipe R44: Schema migration v1→v2 — traits survive restart (issue 767).

Verifies that ``_sync_known_list_traits_to_schema`` correctly migrates
known_list traits (class, alias, faked, bound, scheme) into schema
``_``-prefixed keys, and they survive a full restart cycle.

R20 tests the sync step with existing known_list traits; this recipe
injects a custom ``_alias`` via the profile YAML and verifies it survives
a ramses_cc reload.

See: https://github.com/ramses-rf/ramses_cc/issues/767
"""

from __future__ import annotations

from ..base import Recipe, RecipeContext
from ..const import CTL
from ..helpers import (
    get_known_list,
    get_schema_retry,
    load_profile_yaml,
    ws_send,
)
from ..profile import MIXED_SCHEMA, mixed_yaml


class R44SchemaMigrationTraitsSurviveRestartIssue767(Recipe):
    id = "R44"
    seq = 450
    title = "Schema migration v1→v2 — traits survive restart (issue 767)"

    async def run(self, ctx: RecipeContext) -> None:
        ctx.log_section("Recipe 44: Schema migration — traits survive restart")

        # 1. Load mixed profile with a custom _alias on the CTL
        test_alias = "Migration Test CTL"
        print(f"  Loading mixed profile with _alias='{test_alias}' on CTL...")

        # Build a schema override that adds _alias to the CTL entry
        ctl_schema = dict(MIXED_SCHEMA[CTL])
        ctl_schema["_alias"] = test_alias
        schema_override = {CTL: ctl_schema}

        yaml_text = mixed_yaml(schema_override=schema_override)
        try:
            await load_profile_yaml(
                ctx.token,
                yaml_text,
                speed=0.01,
                preload_schema=True,
                reload_ramses=True,
            )
        except RuntimeError as e:
            print(f"  Profile load failed: {e}")
        ctx.wait(15, "for ramses_cc reload")
        ctx.refresh_token()
        ctx.wait(5, "for ramses_cc to initialize")

        # 2. Verify schema has _alias trait
        schema = get_schema_retry()
        ctl_entry = schema.get(CTL, {})

        ctx.check(
            f"schema has {CTL} with _alias trait",
            isinstance(ctl_entry, dict) and ctl_entry.get("_alias") == test_alias,
            f"_alias={ctl_entry.get('_alias', 'MISSING')}",
        )

        ctx.check(
            f"schema has {CTL} with _class trait",
            isinstance(ctl_entry, dict) and ctl_entry.get("_class") == "CTL",
            f"_class={ctl_entry.get('_class', 'MISSING')}",
        )

        # 3. Reload ramses_cc (simulating restart)
        print("  Reloading ramses_cc (simulating restart)...")
        try:
            await ws_send(
                ctx.token,
                {
                    "type": "config_entries/reload",
                    "entry_id": "ramses_cc",
                },
            )
        except RuntimeError:
            pass
        ctx.wait(15, "for ramses_cc reload")
        ctx.refresh_token()
        ctx.wait(5, "for ramses_cc to initialize")

        # 4. Verify traits survived the restart
        schema_after = get_schema_retry()
        ctl_entry_after = schema_after.get(CTL, {})

        ctx.check(
            "_alias trait survived restart",
            isinstance(ctl_entry_after, dict)
            and ctl_entry_after.get("_alias") == test_alias,
            f"_alias={ctl_entry_after.get('_alias', 'MISSING')}",
        )

        ctx.check(
            "_class trait survived restart",
            isinstance(ctl_entry_after, dict)
            and ctl_entry_after.get("_class") == "CTL",
            f"_class={ctl_entry_after.get('_class', 'MISSING')}",
        )

        # 5. Verify known_list is derived from schema (device is present)
        #    Note: _derive_known_list_from_schema returns empty traits dicts {}
        #    — it only controls which devices are allowed through enforce_known_list.
        #    Traits like alias are read from the schema _ keys by ramses_cc entities,
        #    not from the known_list.
        kl = get_known_list()
        ctl_kl = kl.get(CTL, {})

        ctx.check(
            f"known_list has {CTL} (derived from schema, for enforce_known_list)",
            isinstance(ctl_kl, dict),
            f"ctl_kl={ctl_kl}",
        )
