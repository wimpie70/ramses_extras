"""Recipe R166: zone _name mismatch must not corrupt the schema (issue 1435).

Reproduces https://github.com/ramses-rf/ramses_cc/issues/1435:

- The stored schema has zone ``00`` with ``_name: "Woonkamer"``.
- The controller then reports a different name for that zone on the wire
  (0004 broadcast naming it "Thermostat") — e.g. the user renamed the zone
  on the controller, or the schema was authored with a custom name.
- ``check_name_mismatches`` stores metadata under the composite zone id
  ``<ctl>_00`` with the default discovery status NEW.

Pre-fix defects verified end-to-end here:

1. The composite zone id surfaces in the *Review discovered devices*
  options flow as a NEW device (instead of only in the name-mismatch
  section), with default action "Skip for now".
2. Submitting that form with defaults removes the zone from the schema
  and writes an invalid top-level ``<ctl>_00: {_skipped: true}`` key,
  which fails ramses_rf schema validation on the next reload.

Post-fix expectations (all checks in this recipe):

- The review form never lists the composite zone id as a new device
  (genuinely new devices still appear — positive control).
- Submitting the form with defaults leaves the zone and schema intact.
- The config entry still loads after a reload.
"""

from __future__ import annotations

import json
import time
import urllib.request

from ..base import Recipe, RecipeContext
from ..const import CTL, HGI, TRV
from ..helpers import (
    _get_ramses_cc_entry_id,
    call_service,
    get_current_instance,
    get_schema_retry,
    get_token,
    is_ramses_cc_loaded,
    load_profile_yaml,
    wait_for,
    wait_for_transport_ready,
    ws_send,
)
from ..profile import _build_yaml

_ZONE = "00"
_SCHEMA_NAME = "Woonkamer"
_CTRL_NAME = "Thermostat"
_ZONE_CHILD = f"{CTL}_{_ZONE}"
_UNKNOWN_TRV = "04:200002"  # not in schema — triggers real-time checkpoint

# 0004 zone_name broadcast for zone 00, NUL-padded to 20 bytes (see R151).
_PKT_ZONE_NAME = (
    "0000" + _CTRL_NAME.encode("ascii").hex().upper() + "00" * (20 - len(_CTRL_NAME))
)


def _profile_yaml() -> str:
    kl = {
        HGI: {"class": "HGI"},
        CTL: {"class": "CTL"},
        TRV: {"class": "TRV"},
    }
    schema = {
        "_owner": "me",
        "main_tcs": CTL,
        CTL: {
            "_class": "CTL",
            "_owner": "me",
            "zones": {
                _ZONE: {
                    "_name": _SCHEMA_NAME,
                    "class": "radiator_valve",
                    "actuators": [TRV],
                },
            },
        },
        TRV: {"_class": "TRV", "_owner": "me"},
    }
    return _build_yaml(kl, schema)


def _ha_post(token: str, path: str, data: dict, method: str = "POST") -> dict:
    """POST/DELETE to the HA REST API and return the decoded response."""
    ha_url = get_current_instance().ha_url
    req = urllib.request.Request(
        f"{ha_url}{path}",
        data=json.dumps(data).encode() if method == "POST" else None,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    try:
        resp = urllib.request.urlopen(req, timeout=30)
        content = resp.read()
        return json.loads(content) if content else {}
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP {e.code}: {e.read().decode()[:200]}") from e


class R166ZoneNameMismatchSchemaCorruption(Recipe):
    id = "R166"
    seq = 1660
    title = "Zone _name mismatch must not corrupt schema (issue 1435)"
    tags = ("discovery", "schema", "review", "issue-1435")

    def _inject(
        self, ctx: RecipeContext, source_id: str, code: str, payload: str
    ) -> None:
        call_service(
            ctx.token,
            "ramses_extras",
            "device_simulator_inject_message",
            {
                "source_id": source_id,
                "code": code,
                "payload": payload,
                "verb": "I",
            },
        )

    async def run(self, ctx: RecipeContext) -> None:
        ctx.log_section("Recipe 166: zone _name mismatch corruption (issue 1435)")

        # 1. Seed the schema: zone 00 _name "Woonkamer".
        print("  Loading profile (zone 00 _name='Woonkamer')...")
        try:
            await load_profile_yaml(
                ctx.token,
                _profile_yaml(),
                speed=0.01,
                preload_schema=True,
                reload_ramses=True,
            )
        except RuntimeError as e:
            ctx.check("profile loaded", False, detail=str(e)[:200])
            return
        ctx.wait_for_ramses_cc_reload(timeout=30)
        ctx.refresh_token()
        wait_for_transport_ready(timeout=30)
        ctx.wait_for_schema_stable(timeout=15)

        schema = get_schema_retry()
        zone = schema.get(CTL, {}).get("zones", {}).get(_ZONE, {})
        ctx.check(
            "precondition: zone 00 seeded with _name",
            zone.get("_name") == _SCHEMA_NAME,
            f"zone={zone}",
        )

        # Activate the CTL so its packets are accepted by the simulator.
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

        # 2. Controller announces a different zone name on the wire.
        print(f"  Injecting CTL 0004 naming zone {_ZONE} '{_CTRL_NAME}'...")
        self._inject(ctx, CTL, "0004", _PKT_ZONE_NAME)
        ctx.wait(3, "for 0004 to reach ramses_rf")

        # 3. Trigger the real-time discovery checkpoint: a heartbeat from
        #    an unknown device makes the scan engine report a new device,
        #    which runs the debounced checkpoint (~5s) including
        #    check_name_mismatches.
        print(f"  Injecting 1FC9 heartbeat from unknown {_UNKNOWN_TRV}...")
        self._inject(ctx, _UNKNOWN_TRV, "1FC9", "0030C912E294")
        ctx.wait(10, "for real-time discovery checkpoint", floor=8.0)

        # 4. The periodic-save path alone must never corrupt the schema.
        try:
            call_service(ctx.token, "ramses_cc", "sync_topology")
        except RuntimeError as e:
            print(f"  sync_topology failed: {e}")
        ctx.wait_for_schema_stable(timeout=10, msg="for sync_learned_topology")
        try:
            call_service(ctx.token, "ramses_cc", "force_update")
        except RuntimeError:
            pass
        ctx.wait_for_schema_stable(timeout=10, msg="for save")

        schema = get_schema_retry()
        zones = schema.get(CTL, {}).get("zones", {})
        ctx.check(
            "zone survives periodic sync/save (no review interaction)",
            _ZONE in zones,
            f"zones={sorted(zones)}",
        )
        ctx.check(
            "no composite top-level key after periodic save",
            _ZONE_CHILD not in schema,
            f"schema keys with '_'={[k for k in schema if '_' in str(k)]}",
        )

        # 5. Drive the real review_discovered options flow over the HTTP API.
        entry_id = _get_ramses_cc_entry_id()
        if not entry_id:
            ctx.check("ramses_cc config entry found", False, "no entry_id")
            return
        token = ctx.token

        print("  Opening options flow -> review_discovered...")
        try:
            flow = _ha_post(
                token,
                "/api/config/config_entries/options/flow",
                {"handler": entry_id},
            )
        except RuntimeError as e:
            ctx.check("options flow created", False, str(e)[:150])
            return
        flow_id = flow.get("flow_id")
        try:
            step = _ha_post(
                token,
                f"/api/config/config_entries/options/flow/{flow_id}",
                {"next_step_id": "review_discovered"},
            )
        except RuntimeError as e:
            ctx.check("review_discovered step reached", False, str(e)[:150])
            return

        schema_fields = {
            f.get("name"): f for f in step.get("data_schema", []) if f.get("name")
        }
        device_fields = sorted(n for n in schema_fields if n.startswith("device_"))
        print(f"  review form device fields: {device_fields}")

        # Positive control: the genuinely unknown TRV must be listed.
        ctx.check(
            "genuinely new device still listed in review form",
            f"device_{_UNKNOWN_TRV}" in schema_fields,
            f"device fields={device_fields}",
        )
        # The core regression check: the zone child id must NOT be a
        # new-device field (pre-fix it is, with default 'skip').
        ctx.check(
            "composite zone id not listed as new device",
            f"device_{_ZONE_CHILD}" not in schema_fields,
            f"device fields={device_fields}",
        )
        # Instead it must surface in the name-mismatch section.
        ctx.check(
            "zone listed in name-mismatch section",
            f"name_mismatch_{_ZONE_CHILD}" in schema_fields,
            f"fields={sorted(schema_fields)}",
        )

        # 6. Submit the form — the reproduction is a user who keeps their
        #    custom zone _name (skips the name-mismatch action) and clicks
        #    Submit with everything else at its default.  Pre-fix the zone
        #    was listed as a NEW device with default "skip", so even this
        #    minimal interaction deleted the zone and corrupted the schema.
        user_input = {}
        for name, field in schema_fields.items():
            if "default" in field:
                user_input[name] = field["default"]
        user_input.setdefault("owner_name", "me")
        user_input.setdefault("bulk_action", "none")
        # The user wants to keep their custom _name — explicitly skip the
        # name-mismatch action (its form default is "update_name").
        if f"name_mismatch_{_ZONE_CHILD}" in schema_fields:
            user_input[f"name_mismatch_{_ZONE_CHILD}"] = "skip"
        print(f"  Submitting review form with defaults: {sorted(user_input)}")
        try:
            _ha_post(
                token,
                f"/api/config/config_entries/options/flow/{flow_id}",
                user_input,
            )
        except RuntimeError as e:
            print(f"  review submit returned: {str(e)[:120]}")
        ctx.wait_for_schema_stable(timeout=15, msg="for review submit save")

        schema = get_schema_retry()
        zones = schema.get(CTL, {}).get("zones", {})
        ctx.check(
            "zone still in schema after default review submit",
            _ZONE in zones,
            f"zones={sorted(zones)}",
        )
        ctx.check(
            "zone keeps user-authored _name after review submit",
            zones.get(_ZONE, {}).get("_name") == _SCHEMA_NAME,
            f"zone={zones.get(_ZONE)}",
        )
        ctx.check(
            "no invalid composite top-level key after review submit",
            _ZONE_CHILD not in schema,
            f"schema keys with '_'={[k for k in schema if '_' in str(k)]}",
        )

        # 7. Ultimate proof: the entry must still load after a reload —
        #    pre-fix the invalid key fails schema validation (setup_error).
        print("  Reloading ramses_cc config entry...")
        try:
            call_service(
                ctx.token,
                "homeassistant",
                "reload_config_entry",
                {"entry_id": entry_id},
            )
        except RuntimeError as e:
            print(f"  reload call failed: {e}")
        ctx.wait_for_ramses_cc_reload(timeout=30)
        ctx.refresh_token()
        ctx.check(
            "ramses_cc still loads after reload",
            is_ramses_cc_loaded(),
            "config entry not in loaded state",
        )
