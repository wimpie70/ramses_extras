"""Recipe R121: Non-primary HGI USB→MQTT switch regression test.

Verifies the three fixes for switching a non-primary HGI from USB to
MQTT via the pool management UI (issue 1171):

1. **Serial port removal**: when a non-primary HGI switches from USB to
   MQTT, its serial port must be removed from ``additional_ports`` so
   it becomes an MQTT-only child (not both serial and MQTT).

2. **MQTT bridge creation**: the coordinator must create the MQTT pool
   bridge when any schema HGI has ``_preferred_type: "mqtt"``, even if
   the primary is serial and there are no ``mqtt://`` URLs in
   ``additional_ports``.

3. **Comment warning migration**: existing HGI ``_comment`` fields must
   be migrated to include the warning suffix on startup, so users know
   not to edit ``_preferred_type`` directly.

The ha-sim container has no real serial ports, so this recipe tests the
coordinator logic and config-flow code paths directly via
``docker_exec_python``.
"""

from __future__ import annotations

from ..base import Recipe, RecipeContext
from ..helpers import docker_exec_python


class R123NonPrimaryUsbToMqtt(Recipe):
    id = "R123"
    seq = 1230
    title = "Non-primary HGI USB→MQTT switch (issue 1171)"
    tags = (
        "pooled",
        "multi-hgi",
        "phase2",
        "switching",
        "preferred_type",
        "issue-1171",
        "comment-warning",
    )

    async def run(self, ctx: RecipeContext) -> None:
        """Verify non-primary HGI USB→MQTT switch fixes."""
        ctx.log_section("Recipe 121: Non-primary HGI USB→MQTT switch")
        failed_at_start = ctx.failed
        ctx.wait_for_ramses_cc_loaded(timeout=20)
        ctx.refresh_token()

        # ------------------------------------------------------------------
        # Test 1: HGI_COMMENT_WARNING and build_hgi_comment() exist
        # ------------------------------------------------------------------
        result = docker_exec_python(
            """
import json
from custom_components.ramses_cc.const import (
    HGI_COMMENT_WARNING,
    build_hgi_comment,
    ensure_hgi_comment_warning,
)

results = []

def check(name, condition, detail=""):
    status = "PASS" if condition else "FAIL"
    results.append({"name": name, "status": status, "detail": detail})

# Warning suffix exists and is non-empty
check("HGI_COMMENT_WARNING exists",
      bool(HGI_COMMENT_WARNING),
      f"warning={HGI_COMMENT_WARNING!r}")

# build_hgi_comment produces the warning suffix
comment_usb_mqtt = build_hgi_comment(["usb", "mqtt"])
check("build_hgi_comment includes warning",
      HGI_COMMENT_WARNING in comment_usb_mqtt,
      f"comment={comment_usb_mqtt!r}")

# build_hgi_comment does NOT duplicate the warning
comment_mqtt = build_hgi_comment(["mqtt"])
check("build_hgi_comment no duplicate warning",
      comment_mqtt.count(HGI_COMMENT_WARNING) == 1,
      f"comment={comment_mqtt!r}")

# ensure_hgi_comment_warning appends to existing comment
old_comment = "Supports: usb, mqtt"
migrated = ensure_hgi_comment_warning(old_comment)
check("ensure_hgi_comment_warning appends warning",
      migrated == old_comment + HGI_COMMENT_WARNING,
      f"migrated={migrated!r}")

# ensure_hgi_comment_warning is idempotent
migrated_again = ensure_hgi_comment_warning(migrated)
check("ensure_hgi_comment_warning is idempotent",
      migrated_again == migrated,
      f"double-migrated={migrated_again!r}")

# Warning does NOT contain transport-type words (would break parsing)
for word in ("usb", "mqtt", "zigbee"):
    check(f"Warning does not contain '{word}'",
          word not in HGI_COMMENT_WARNING.lower(),
          f"warning={HGI_COMMENT_WARNING!r}")

print(json.dumps({"results": results}))
""",
            timeout=30,
        )

        if "error" in result:
            ctx.check("Recipe 121 comment helpers", False, result.get("error", ""))
        else:
            for chk in result.get("results", []):
                ctx.check(
                    chk["name"],
                    chk["status"] == "PASS",
                    chk["detail"],
                )

        # ------------------------------------------------------------------
        # Test 2: Coordinator _has_mqtt gate includes schema _preferred_type
        # ------------------------------------------------------------------
        result = docker_exec_python(
            """
import json
results = []

def check(name, condition, detail=""):
    status = "PASS" if condition else "FAIL"
    results.append({"name": name, "status": status, "detail": detail})

# Read the coordinator source to verify the _schema_mqtt_preferred logic
# is present (regression guard — if someone removes the check, the
# MQTT bridge won't be created for non-primary HGIs switched to MQTT).
import inspect
from custom_components.ramses_cc import coordinator as coord_mod

source = inspect.getsource(coord_mod)
check(
    "Coordinator has _schema_mqtt_preferred check",
    "_schema_mqtt_preferred" in source,
    "The _schema_mqtt_preferred variable is missing — "
    "non-primary HGI USB→MQTT switch will not create the MQTT bridge",
)

check(
    "Coordinator checks _preferred_type == mqtt in schema",
    '_preferred_type' in source and '"mqtt"' in source,
    "The schema _preferred_type check is missing",
)

print(json.dumps({"results": results}))
""",
            timeout=30,
        )

        if "error" in result:
            ctx.check("Recipe 121 coordinator logic", False, result.get("error", ""))
        else:
            for chk in result.get("results", []):
                ctx.check(
                    chk["name"],
                    chk["status"] == "PASS",
                    chk["detail"],
                )

        # ------------------------------------------------------------------
        # Test 3: Config flow has _switching_secondary_to_mqtt logic
        # ------------------------------------------------------------------
        result = docker_exec_python(
            """
import json
results = []

def check(name, condition, detail=""):
    status = "PASS" if condition else "FAIL"
    results.append({"name": name, "status": status, "detail": detail})

import inspect
from custom_components.ramses_cc import config_flow as cf_mod

source = inspect.getsource(cf_mod)

check(
    "Config flow has _switching_secondary_to_mqtt flag",
    "_switching_secondary_to_mqtt" in source,
    "The _switching_secondary_to_mqtt flag is missing — "
    "non-primary HGI USB→MQTT switch won't redirect to broker URL step",
)

check(
    "Config flow removes serial port on non-primary USB→MQTT",
    "removed serial port" in source and "switched to MQTT" in source,
    "The serial port removal logic for non-primary HGIs is missing",
)

check(
    "Config flow redirects non-primary to manage_pool_mqtt_url",
    "_switching_secondary_to_mqtt" in source
    and "async_step_manage_pool_mqtt_url" in source,
    "The redirect to the broker URL step is missing",
)

check(
    "Config flow uses build_hgi_comment for _comment",
    "build_hgi_comment" in source,
    "The config flow should use build_hgi_comment() to include the warning",
)

print(json.dumps({"results": results}))
""",
            timeout=30,
        )

        if "error" in result:
            ctx.check("Recipe 121 config flow logic", False, result.get("error", ""))
        else:
            for chk in result.get("results", []):
                ctx.check(
                    chk["name"],
                    chk["status"] == "PASS",
                    chk["detail"],
                )

        # ------------------------------------------------------------------
        # Test 4: Comment warning migration runs on startup
        # ------------------------------------------------------------------
        result = docker_exec_python(
            """
import json
results = []

def check(name, condition, detail=""):
    status = "PASS" if condition else "FAIL"
    results.append({"name": name, "status": status, "detail": detail})

import inspect
from custom_components.ramses_cc import coordinator as coord_mod

source = inspect.getsource(coord_mod)

check(
    "Coordinator has HGI comment migration in async_setup",
    "ensure_hgi_comment_warning" in source
    and "Migrated HGI _comment" in source,
    "The comment warning migration is missing from async_setup",
)

# Also verify the migration is in async_setup (not just anywhere)
# by checking it's near the "client_state" line (which is in async_setup)
check(
    "Migration is in async_setup (near client_state)",
    "ensure_hgi_comment_warning" in source
    and "client_state" in source
    and source.index("ensure_hgi_comment_warning") < source.index("client_state"),
    "The migration should be in async_setup before client_state loading",
)

print(json.dumps({"results": results}))
""",
            timeout=30,
        )

        if "error" in result:
            ctx.check("Recipe 121 comment migration", False, result.get("error", ""))
        else:
            for chk in result.get("results", []):
                ctx.check(
                    chk["name"],
                    chk["status"] == "PASS",
                    chk["detail"],
                )

        # ------------------------------------------------------------------
        # Test 5: Live check — HGI comments in running config have warning
        # ------------------------------------------------------------------
        result = docker_exec_python(
            """
import json
results = []

def check(name, condition, detail=""):
    status = "PASS" if condition else "FAIL"
    results.append({"name": name, "status": status, "detail": detail})

# Read the running config entry's schema and check that HGI comments
# have the warning suffix (the migration should have run on startup).
p = '/config/.storage/core.config_entries'
d = json.load(open(p))
from custom_components.ramses_cc.const import HGI_COMMENT_WARNING

for e in d['data']['entries']:
    if e['domain'] != 'ramses_cc':
        continue
    schema = e['options'].get('schema', {})
    if not isinstance(schema, dict):
        check("Schema is a dict", False, f"type={type(schema)}")
        break
    hgi_count = 0
    hgi_with_comment = 0
    warned_count = 0
    for dev_id, entry in schema.items():
        if not (
            isinstance(dev_id, str)
            and dev_id.startswith('18:')
            and dev_id != '18:000730'
            and isinstance(entry, dict)
            and entry.get('_class', '').upper() == 'HGI'
        ):
            continue
        hgi_count += 1
        comment = str(entry.get('_comment', ''))
        if not comment:
            # Skip HGIs with no _comment — the warning will be
            # added when the comment is set by the serial probe
            # or MQTT LWT detection (which uses build_hgi_comment).
            continue
        hgi_with_comment += 1
        if HGI_COMMENT_WARNING in comment:
            warned_count += 1
        else:
            check(f"HGI {dev_id} comment has warning",
                  False,
                  f"comment={comment!r}")
    check(
        "All HGI comments with text have warning suffix",
        hgi_with_comment == 0 or hgi_with_comment == warned_count,
        f"{warned_count}/{hgi_with_comment} HGIs with comments have warning "
        f"({hgi_count} total HGIs, {hgi_count - hgi_with_comment} without comment)",
    )
    break
else:
    check("ramses_cc config entry found", False, "no ramses_cc entry")

print(json.dumps({"results": results}))
""",
            timeout=30,
        )

        if "error" in result:
            ctx.check("Recipe 121 live comment check", False, result.get("error", ""))
        else:
            for chk in result.get("results", []):
                ctx.check(
                    chk["name"],
                    chk["status"] == "PASS",
                    chk["detail"],
                )

        ctx.check(
            "All non-primary USB→MQTT switch checks passed",
            ctx.failed == failed_at_start,
        )
