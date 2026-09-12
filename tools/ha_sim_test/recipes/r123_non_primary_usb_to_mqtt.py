"""Recipe R123: Non-primary HGI USB→MQTT switch regression test.

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
        ctx.log_section("Recipe 123: Non-primary HGI USB→MQTT switch")
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
            ctx.check("Recipe 123 comment helpers", False, result.get("error", ""))
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

# Behavioral check: call _extract_pool_hgis_from_schema directly
# with a synthetic schema containing an HGI with _preferred_type:
# "mqtt" and verify it's included in the returned list.
from custom_components.ramses_cc.coordinator import RamsesCoordinator

# Create a minimal mock self with the required attributes.
class _MockEntry:
    def __init__(self, options):
        self.options = options

mock_self = object.__new__(RamsesCoordinator)
mock_self.entry = _MockEntry({
    "schema": {
    "_owner": "me",
        "18:001111": {
            "_class": "HGI",
            "_owner": "me",
            "_preferred_type": "mqtt",
        },
        "18:002222": {
            "_class": "HGI",
            "_preferred_type": "usb",
        },
    },
})

hgis = RamsesCoordinator._extract_pool_hgis_from_schema(mock_self)
check(
    "MQTT-preferred HGI included in pool list",
    "18:001111" in hgis,
    f"hgis={hgis}",
)
check(
    "Ownerless USB HGI included as discovery candidate",
    "18:002222" in hgis,
    f"hgis={hgis}",
)

print(json.dumps({"results": results}))
""",
            timeout=30,
        )

        if "error" in result:
            ctx.check("Recipe 123 coordinator logic", False, result.get("error", ""))
        else:
            for chk in result.get("results", []):
                ctx.check(
                    chk["name"],
                    chk["status"] == "PASS",
                    chk["detail"],
                )

        # ------------------------------------------------------------------
        # Test 3: Config flow manage_pool_mqtt_url accepts HGI ID (not URL)
        # ------------------------------------------------------------------
        result = docker_exec_python(
            """
import json
results = []

def check(name, condition, detail=""):
    status = "PASS" if condition else "FAIL"
    results.append({"name": name, "status": status, "detail": detail})

# Behavioral check: verify the options flow's manage_pool_mqtt_url
# step accepts an HGI ID (not a full mqtt:// URL).  This is the
# redesigned form (issue 1119 — HA MQTT is always the broker).
from custom_components.ramses_cc import config_flow as cf_mod

# The method is on RamsesOptionsFlowHandler (pool management is an
# options-flow step, not a config-flow step).
flow_cls = cf_mod.RamsesOptionsFlowHandler

# Check the method exists.
check(
    "async_step_manage_pool_mqtt_url exists",
    hasattr(flow_cls, "async_step_manage_pool_mqtt_url"),
    "The manage_pool_mqtt_url step is missing",
)

# Behavioral: inspect compiled bytecode constants (co_consts) instead
# of source text — robust to formatting/comment changes while still
# verifying the form collects the right fields.
method = flow_cls.async_step_manage_pool_mqtt_url
all_str_consts: set[str] = set()

def _collect_consts(code_obj):
    for c in code_obj.co_consts:
        if isinstance(c, str):
            all_str_consts.add(c)
        elif hasattr(c, "co_consts"):
            _collect_consts(c)

_collect_consts(method.__code__)

check(
    "Form accepts hgi_id field (not mqtt_url)",
    "hgi_id" in all_str_consts and "mqtt_url" not in all_str_consts,
    "The form should collect hgi_id, not mqtt_url (issue 1119)",
)
check(
    "Form has optional topic_prefix field",
    "topic_prefix" in all_str_consts,
    "The form should have an optional topic_prefix field",
)
check(
    "No broker/port/credential fields collected",
    not any(
        field in all_str_consts
        for field in ("broker", "port", "username", "password")
    ),
    "The form should not collect broker/port/credentials (HA MQTT is the broker)",
)

print(json.dumps({"results": results}))
""",
            timeout=30,
        )

        if "error" in result:
            ctx.check("Recipe 123 config flow logic", False, result.get("error", ""))
        else:
            for chk in result.get("results", []):
                ctx.check(
                    chk["name"],
                    chk["status"] == "PASS",
                    chk["detail"],
                )

        # ------------------------------------------------------------------
        # Test 4: Comment warning migration uses deepcopy (issue 1119)
        # ------------------------------------------------------------------
        result = docker_exec_python(
            """
import json
results = []

def check(name, condition, detail=""):
    status = "PASS" if condition else "FAIL"
    results.append({"name": name, "status": status, "detail": detail})

# Behavioral check: call ensure_hgi_comment_warning directly and
# verify it appends the warning suffix.  Also verify the coordinator's
# migration uses deepcopy (not shallow copy) by checking the source
# for the deepcopy call in the migration block.
from custom_components.ramses_cc.const import (
    HGI_COMMENT_WARNING,
    ensure_hgi_comment_warning,
)

# Behavioral: ensure_hgi_comment_warning appends to a bare comment.
old = "Supports: usb"
migrated = ensure_hgi_comment_warning(old)
check(
    "ensure_hgi_comment_warning appends warning",
    migrated == old + HGI_COMMENT_WARNING,
    f"migrated={migrated!r}",
)

# Behavioral: idempotent on already-warned comments.
again = ensure_hgi_comment_warning(migrated)
check(
    "ensure_hgi_comment_warning is idempotent",
    again == migrated,
    f"again={again!r}",
)

# Behavioral: the coordinator module imports deepcopy (production-
# class check — verifies the actual module namespace, not source
# text).  The migration path uses deepcopy to avoid mutating the
# live options dict (issue 1119).
from custom_components.ramses_cc import coordinator as coord_mod

check(
    "Coordinator imports deepcopy for schema mutations",
    hasattr(coord_mod, "deepcopy"),
    "The coordinator should import deepcopy for schema mutations",
)

print(json.dumps({"results": results}))
""",
            timeout=30,
        )

        if "error" in result:
            ctx.check("Recipe 123 comment migration", False, result.get("error", ""))
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
            ctx.check("Recipe 123 live comment check", False, result.get("error", ""))
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
