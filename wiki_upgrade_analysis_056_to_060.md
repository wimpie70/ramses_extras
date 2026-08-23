# Wiki Analysis: Upgrading from 0.56.0 to 0.60.0

## What's covered well

1. **Page 2.1 (Schemas)** — Good coverage of the new schema system, the discovery flow, and the migration from known_list. It explains:
   - "Since release 0.58.0, Ramses RF supports discovering the Schema"
   - "Most of your set-up is migrated from the pre-0.58.x Known List to the System Schema by the tool"
   - "The Known List is no longer visible in the Config UI and only used inside the code"
   - The `_owner`, `_class`, `_alias`, `_faked`, `_bound`, `_scheme` trait system
   - The passive scan / discovery flow with Accept/Decline/Skip
   - Automatic YAML backups in `ramses_cc_backups/`

2. **Page 2 (Configuration steps 1-2)** — Serial port and gateway config are current and accurate.

3. **Page 1 (Installation)** — HACS install instructions are fine for new users.

## What's outdated or missing (7 issues)

### 1. No dedicated upgrade/migration guide

There is **no wiki page** that walks a 0.56.0 user through the upgrade process. The information is scattered across pages 2.1 and 2.2. A user upgrading from 0.56.0 faces:

- Config entry auto-migration v1→v2→v3 (automatic, but users should know it happens)
- `known_list` traits merged into `schema`, then `known_list` and `enforce_known_list` removed from options
- A v2 backup saved to `.storage/ramses_cc_migration_v2_backup`
- `enforce_known_list` is now hardcoded (always on)
- `disabled_devices` key removed (replaced by `_disabled` trait)
- Deprecated `packet_log.file_name` and `rotate_backups` translated

None of this is documented in the wiki.

### 2. Page 2.2 shows outdated v1 config entry JSON

The "A look behind the scenes" section shows a **version 1** config entry with `known_list` and `enforce_known_list`:

```json
"version": 1,
"options": {
  "ramses_rf": {
    "enforce_known_list": true,
    ...
  },
  "known_list": {
    "18:006402": { ...
```

After upgrading to 0.60.0, the config entry will be **version 3** with a `schema` key instead. This will confuse upgraders who look at their `.storage/core.config_entries`.

### 3. Page 2.2 "Clear Known Devices List" is obsolete

The cache management section still shows "Clear Known Devices List" as an option. In 0.60.0, the known_list is derived from the schema — there is no separate known list to clear. This option no longer exists in the UI.

### 4. Page 3.1 "I'm stuck" references Known List as a current feature

The troubleshooting page has a full section "Is your **Known List** configured correctly?" that tells users to configure `enforce_known_list` and add devices to the Known List. In 0.60.0:

- `enforce_known_list` is always-on (hardcoded, not configurable)
- The Known List is not visible in the Config UI
- Devices are managed via the Schema, not the Known List

This section should be rewritten or removed, pointing users to the Schema instead.

### 5. ramses_extras compatibility warning is absent

The 0.59.7 release notes say: **"WARNING: Ramses RF 0.59.7 DOES NOT RUN RAMSES_EXTRAS 0.21.1 AND EARLIER. INSTALL 0.21.2 FIRST"**. This is a critical breaking change for 0.56.0 users who also run ramses_extras, but it's not mentioned anywhere in the wiki. The "Ramses Extras integration" wiki page doesn't mention version requirements either.

### 6. No "what to expect after upgrade" guidance

A 0.56.0 user upgrading to 0.60.0 will experience:

- Their known_list will be gone (merged into schema) — this is alarming if unexpected
- Their config entry version bumps from 1 to 3
- Entity IDs may change (schema-based naming)
- They should verify their schema after upgrade via Config > System Schema
- They may need to use the discovery tool to complete an incomplete schema
- The "Known List" config tab is gone

None of this is communicated.

### 7. No troubleshooting for migration failures

There's no guidance for:

- What if the migration fails?
- What if devices are missing after upgrade?
- What if the schema is empty after upgrade?
- How to restore from the v2 backup in `.storage/ramses_cc_migration_v2_backup`
- How to restore from the YAML backups in `ramses_cc_backups/`

## Summary

| Wiki Page                         | Status for 0.56→0.60 upgraders                                                 |
| --------------------------------- | ------------------------------------------------------------------------------ |
| Home                              | OK                                                                             |
| 1. Installation                   | OK for new installs; **no upgrade section**                                    |
| 2. Configuration steps 1-2        | OK                                                                             |
| 2.1 Configuration step 3: Schemas | **Good** — covers schema/discovery/migration                                   |
| 2.2 Configuration steps 4-6       | **Outdated** — shows v1 config entry JSON, references Clear Known Devices List |
| 3. Troubleshooting & Logging      | OK                                                                             |
| 3.1 I'm stuck: Help me            | **Outdated** — references Known List as current feature                        |
| 9. FAQ                            | No migration FAQs                                                              |
| Ramses Extras integration         | **Missing** version compatibility warning                                      |

## Recommendations (in priority order)

1. **Add a new wiki page "Upgrading from 0.56.x to 0.60.0"** (or add a section to page 1) covering:
   - Backup before upgrading
   - ramses_extras must be updated to 0.21.2+ first
   - The automatic config entry migration (v1→v2→v3) and what it does
   - What changes to expect (known_list gone, schema is sole source, enforce_known_list always-on)
   - How to verify the schema after upgrade
   - How to use the discovery tool to complete an incomplete schema
   - How to restore from backups if something goes wrong

2. **Update page 2.2**: Replace the v1 config entry JSON with a v3 example showing the `schema` key. Remove "Clear Known Devices List" from the cache management section.

3. **Update page 3.1**: Rewrite the "Is your Known List configured correctly?" section to reference the Schema instead. Remove references to `enforce_known_list` as a configurable option.

4. **Update "Ramses Extras integration" page**: Add a note about minimum version requirements (ramses_extras 0.21.2+ for ramses_cc 0.59.7+).

5. **Add migration FAQs to page 9**: "Where did my Known List go?", "Why did my entity IDs change?", "How do I restore from the v2 backup?".
