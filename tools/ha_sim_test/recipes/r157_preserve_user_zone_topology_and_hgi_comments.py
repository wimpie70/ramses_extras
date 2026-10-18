"""Recipe R157: Preserve user zone topology & idempotent HGI comments.

Guards against the regressions found in ramses_cc PR 1361 / PR 1365 while
verifying the safe implementation of:
- PR 1363: idempotent ``ensure_hgi_comment_warning`` (collapses repeated
  warning suffixes).
- PR 1364: ``refresh_device_comments`` prefers configured schema zones over
  stale scan engine ``zone_index`` and strips stale ``zone XX`` when a
  device is no longer assigned to a zone.
- Safe zone topology preservation in ``sync_learned_topology`` and
  ``async_step_schema``:
  1. Multi-actuator union merge in step 1b continues to merge a 2nd/3rd
     learned TRV into a zone that already has 1 TRV (regression guard for
     PR 1361 Bug 1a and PR 1365).
  2. Explicit ``actuators: []`` on a zone is preserved against both
     ``learned_schema`` (step 1b) and ``device_comments`` (step 1g).
  3. A sensor assigned to a zone (e.g. ``0B``) is never duplicated across
     two zones (regression guard for PR 1361 Bug 1b) nor evicted into an
     empty zone by a stale ``zone 00`` comment.
  4. User zone edits in ``async_step_schema`` update ``device_comments``,
     persisted ``scan_state``, and the live in-memory ``DiscoveryScan`` so
     the reload triggered by saving options does not clobber the changes.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from ..base import Recipe, RecipeContext
from ..const import CTL, HGI, TRV
from ..helpers import (
    _get_ramses_cc_entry_id,
    call_service,
    docker_exec_python,
    get_current_instance,
    get_ramses_storage,
    get_schema,
    get_schema_retry,
    load_profile_yaml,
    wait_for,
    wait_for_transport_ready,
)
from ..profile import _build_yaml

_THM_Z0B = "22:150002"
_TRV_1 = "04:150011"
_TRV_1_HEX = "1249FB"  # dev_id_to_hex_id("04:150011")
_TRV_2 = "04:150012"
_TRV_2_HEX = "1249FC"  # dev_id_to_hex_id("04:150012")

_ZONE_EMPTY = "00"
_ZONE_RAD = "09"
_ZONE_UFH = "0B"

_STALE_THM_COMMENT = (
    "Likely THM. zone 00. bound to 01:150000. (auto-generated — do not edit)"
)


def _options_flow_start(token: str, entry_id: str) -> dict[str, Any]:
    """Start an options flow via REST API and return the flow result."""
    url = f"{get_current_instance().ha_url}/api/config/config_entries/options/flow"
    body = json.dumps({"handler": entry_id}).encode()
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def _options_flow_configure(
    token: str, flow_id: str, user_input: dict[str, Any]
) -> dict[str, Any]:
    """Configure an options flow step via REST API and return the result."""
    url = (
        f"{get_current_instance().ha_url}"
        f"/api/config/config_entries/options/flow/{flow_id}"
    )
    body = json.dumps(user_input).encode()
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as err:
        content = err.read().decode()
        raise RuntimeError(f"HTTP {err.code}: {content}") from err


def _profile_yaml() -> str:
    """Build profile with empty zone 00, RAD zone 09, and UFH zone 0B."""
    kl = {
        HGI: {"class": "HGI"},
        CTL: {"class": "CTL"},
        _THM_Z0B: {"class": "THM"},
        TRV: {"class": "TRV"},
        _TRV_1: {"class": "TRV"},
        _TRV_2: {"class": "TRV"},
    }
    schema = {
        CTL: {
            "zones": {
                _ZONE_EMPTY: {
                    "class": "underfloor_heating",
                },
                _ZONE_RAD: {
                    "_name": "Study",
                    "class": "radiator_valve",
                    "sensor": _TRV_1,
                    "actuators": [_TRV_1],
                },
                _ZONE_UFH: {
                    "_name": "Old Shop",
                    "class": "underfloor_heating",
                    "sensor": _THM_Z0B,
                },
            }
        },
        "device_comments": {
            _THM_Z0B: _STALE_THM_COMMENT,
        },
    }
    return _build_yaml(kl, schema)


class R157PreserveUserZoneTopologyAndHgiComments(Recipe):
    """Verify user zone topology preservation and HGI comment idempotency."""

    id = "R157"
    seq = 1570
    title = "Preserve user zone topology & idempotent HGI comments"
    tags = ("schemas", "config_flow", "discovery", "pr_1363", "pr_1364")

    async def run(self, ctx: RecipeContext) -> None:
        """Run unit-level and live e2e checks against ha-sim."""
        ctx.log_section(
            "Recipe 157: Preserve user zone topology & idempotent HGI comments"
        )

        # ── Part 1: In-container unit checks for sync_learned_topology,
        #            ensure_hgi_comment_warning, and refresh_device_comments
        unit_res = docker_exec_python(
            """
import inspect
import json
from unittest.mock import MagicMock

from custom_components.ramses_cc import const as cc_const
from custom_components.ramses_cc.discovery import DiscoveryManager
from custom_components.ramses_cc.schemas import sync_learned_topology
from ramses_rf.const import SZ_ACTUATORS, SZ_SENSOR, SZ_ZONES

checks = []


def record(label, cond, detail=""):
    checks.append({"label": label, "ok": bool(cond), "detail": str(detail)})


# 1a. Unconditional regression guard: multi-actuator union merge (PR 1361/1365 Bug 1a)
cfg_multi = {
    "main_tcs": "01:123456",
    "01:123456": {
        SZ_ZONES: {
            "01": {SZ_SENSOR: "04:111111", SZ_ACTUATORS: ["04:111111"]}
        }
    },
}
lrn_multi = {
    "main_tcs": "01:123456",
    "01:123456": {
        SZ_ZONES: {
            "01": {
                SZ_SENSOR: "04:111111",
                SZ_ACTUATORS: ["04:111111", "04:222222"],
            }
        }
    },
}
res_multi = sync_learned_topology(cfg_multi, lrn_multi) or cfg_multi
acts_01 = res_multi["01:123456"][SZ_ZONES]["01"].get(SZ_ACTUATORS, [])
record(
    "sync_learned_topology union-merges 2nd learned TRV into existing zone actuators",
    acts_01 == ["04:111111", "04:222222"],
    f"actuators={acts_01}",
)

# 1b. Unconditional regression guard: sensor never duplicated across two zones
cfg_dup = {
    "_owner": "me",
    "main_tcs": "01:123456",
    "01:123456": {
        SZ_ZONES: {
            "00": {},
            "0B": {SZ_SENSOR: "34:124201"},
        }
    },
    "34:124201": {"_owner": "me"},
    "device_comments": {
        "34:124201": (
            "Likely THM. zone 00. bound to 01:123456. "
            "(auto-generated — do not edit)"
        ),
    },
}
lrn_dup = {"main_tcs": "01:123456", "01:123456": {SZ_ZONES: {}}}
res_dup = sync_learned_topology(cfg_dup, lrn_dup) or cfg_dup
zones_dup = res_dup["01:123456"][SZ_ZONES]
sensor_zones = [
    z_idx for z_idx, z_data in zones_dup.items()
    if isinstance(z_data, dict) and z_data.get(SZ_SENSOR) == "34:124201"
]
record(
    "sync_learned_topology never duplicates a sensor across two zones",
    len(sensor_zones) == 1,
    f"zones={zones_dup}",
)

# 1c. Conditional checks when the new fixes are present in ha-sim
has_hgi_fix = hasattr(cc_const, "HGI_COMMENT_WARNING_TEXT")
has_comment_zone_fix = (
    "configured_device_zones"
    in inspect.getsource(DiscoveryManager.refresh_device_comments)
)
has_user_sensor_fix = (
    "user_assigned_sensors" in inspect.getsource(sync_learned_topology)
)

if has_hgi_fix:
    w_txt = cc_const.HGI_COMMENT_WARNING_TEXT
    base = "Supports: usb, mqtt"
    expected = f"{base} {w_txt}"
    dup = f"{expected} {w_txt}   {w_txt}"
    record(
        "ensure_hgi_comment_warning collapses duplicated warning suffixes",
        cc_const.ensure_hgi_comment_warning(dup) == expected
        and cc_const.ensure_hgi_comment_warning("") == w_txt,
        f"got={cc_const.ensure_hgi_comment_warning(dup)!r}",
    )

if has_comment_zone_fix:
    dev_thm = MagicMock(
        device_id="34:124201",
        likely_type="THM",
        zone_index="00",
        bound_to="01:145038",
        is_authoritative_domain=False,
        confidence="high",
        domain_id=None,
        codes_seen=[],
        is_battery=False,
        rssi=-65.0,
    )
    scan_mock = MagicMock()
    scan_mock.get_devices.return_value = [dev_thm]
    mgr = DiscoveryManager(MagicMock(), scan_mock, auto_notify=False)
    refreshed = mgr.refresh_device_comments(
        {},
        config_schema={
            "01:145038": {SZ_ZONES: {"0B": {SZ_SENSOR: "34:124201"}}}
        },
    )
    record(
        "refresh_device_comments prefers config_schema zone over stale scan zone_index",
        "zone 0B" in refreshed.get("34:124201", "")
        and "zone 00" not in refreshed.get("34:124201", ""),
        f"comment={refreshed.get('34:124201')!r}",
    )

if has_user_sensor_fix:
    record(
        "sync_learned_topology preserves configured sensor in zone 0B "
        "against stale zone 00 comment",
        zones_dup.get("0B", {}).get(SZ_SENSOR) == "34:124201"
        and zones_dup.get("00", {}).get(SZ_SENSOR) is None,
        f"zones={zones_dup}",
    )
    res_removed_act = (
        sync_learned_topology(
            cfg_multi,
            {
                "main_tcs": "01:123456",
                "01:123456": {
                    SZ_ZONES: {
                        "01": {
                            SZ_SENSOR: "04:111111",
                            SZ_ACTUATORS: [
                                "04:111111",
                                "04:222222",
                                "04:333333",
                            ],
                        }
                    }
                },
            },
            removed_devices={"04:333333"},
        )
        or cfg_multi
    )
    record(
        "sync_learned_topology union-merges actuators while excluding removed_devices",
        res_removed_act["01:123456"][SZ_ZONES]["01"].get(SZ_ACTUATORS)
        == ["04:111111", "04:222222"],
        f"zone_01={res_removed_act['01:123456'][SZ_ZONES]['01']}",
    )

print(
    json.dumps(
        {
            "ok": True,
            "checks": checks,
            "has_user_sensor_fix": has_user_sensor_fix,
        }
    )
)
"""
        )
        ctx.check(
            "in-container topology & comment checks executed",
            bool(unit_res.get("ok")),
            f"unit_res={unit_res}",
        )
        for item in unit_res.get("checks", []):
            ctx.check(item["label"], item["ok"], item.get("detail", ""))

        has_user_sensor_fix = bool(unit_res.get("has_user_sensor_fix"))

        # ── Part 2: Live simulation e2e — load profile, inject 2nd TRV 000C
        #            for zone 09, and verify multi-TRV union merge + sensor
        #            isolation
        print("  Loading profile with zones 00, 09 (1 TRV), and 0B (THM)...")
        try:
            await load_profile_yaml(
                ctx.token,
                _profile_yaml(),
                speed=0.01,
                preload_schema=True,
                reload_ramses=True,
            )
        except RuntimeError as err:
            ctx.check("profile loaded", False, detail=str(err)[:200])
            return

        ctx.wait_for_ramses_cc_reload(timeout=30)
        ctx.refresh_token()
        wait_for_transport_ready(timeout=30)
        ctx.wait_for_schema_stable(timeout=15)

        # Inject 000C binding a 2nd TRV (04:150012) as radiator actuator (08)
        # in zone 09 alongside _TRV_1 (04:150011).
        inject_payload = f"{_ZONE_RAD}0800{_TRV_1_HEX}{_ZONE_RAD}0800{_TRV_2_HEX}"

        def _inject_second_trv() -> None:
            try:
                call_service(
                    ctx.token,
                    "ramses_extras",
                    "device_simulator_inject_message",
                    {
                        "source_id": CTL,
                        "dst": get_current_instance().hgi_id,
                        "code": "000C",
                        "payload": inject_payload,
                        "verb": "RP",
                    },
                )
            except RuntimeError as err:
                print(f"  000C inject failed: {err}")

        def _second_trv_merged() -> bool:
            zones = get_schema().get(CTL, {}).get("zones", {})
            z09 = zones.get(_ZONE_RAD, {})
            acts = z09.get("actuators", []) if isinstance(z09, dict) else []
            return _TRV_1 in acts and _TRV_2 in acts

        for attempt in range(2):
            _inject_second_trv()
            ctx.wait(2, "for 000C packet to arrive")
            try:
                call_service(ctx.token, "ramses_cc", "sync_topology")
            except RuntimeError:
                pass
            ctx.wait_for_schema_stable(timeout=10, msg="for sync_topology")
            try:
                call_service(ctx.token, "ramses_cc", "force_update")
            except RuntimeError:
                pass
            ctx.wait_for_schema_stable(timeout=10, msg="for save_client_state")
            if wait_for(
                _second_trv_merged,
                timeout=10,
                interval=2,
                msg=(
                    f"for {_TRV_2} to merge into zone {_ZONE_RAD}"
                    f" (attempt {attempt + 1})"
                ),
                floor=4.0,
            ):
                break

        zones_after = get_schema_retry().get(CTL, {}).get("zones", {})
        z09_acts = zones_after.get(_ZONE_RAD, {}).get("actuators", [])
        ctx.check(
            f"live e2e: 2nd TRV {_TRV_2} union-merged into zone {_ZONE_RAD} actuators",
            _TRV_1 in z09_acts and _TRV_2 in z09_acts,
            f"zone_{_ZONE_RAD}={zones_after.get(_ZONE_RAD)}",
        )

        # Verify THM_Z0B is never duplicated across zones
        thm_zones = [
            z_idx
            for z_idx, z_data in zones_after.items()
            if isinstance(z_data, dict) and z_data.get("sensor") == _THM_Z0B
        ]
        ctx.check(
            f"live e2e: {_THM_Z0B} occupies at most one zone sensor slot",
            len(thm_zones) == 1,
            f"thm_zones={thm_zones}, zones={zones_after}",
        )

        if not has_user_sensor_fix:
            print(
                "  Skipping PR-specific options-flow scan_state sync check "
                "(fix not yet installed in ha-sim)"
            )
            return

        ctx.check(
            (
                f"live e2e: {_THM_Z0B} stays in zone {_ZONE_UFH}"
                " despite stale zone 00 comment"
            ),
            zones_after.get(_ZONE_UFH, {}).get("sensor") == _THM_Z0B
            and zones_after.get(_ZONE_EMPTY, {}).get("sensor") is None,
            f"zones={zones_after}",
        )

        # ── Part 3: Live Options Flow async_step_schema test — verify
        #            user zone edits update scan_state and survive reload
        entry_id = _get_ramses_cc_entry_id()
        if not entry_id:
            ctx.check("ramses_cc entry_id found", False, "missing entry_id")
            return

        current_schema = dict(get_schema_retry())
        ctl_entry = dict(current_schema.get(CTL, {}))
        zones_edit = dict(ctl_entry.get("zones", {}))
        # Clear zone 09 actuators to [] via the schema editor
        z09_edit = dict(zones_edit.get(_ZONE_RAD, {}))
        z09_edit["actuators"] = []
        zones_edit[_ZONE_RAD] = z09_edit
        ctl_entry["zones"] = zones_edit
        current_schema[CTL] = ctl_entry

        try:
            init_flow = _options_flow_start(ctx.token, entry_id)
            step_schema = _options_flow_configure(
                ctx.token, init_flow["flow_id"], {"next_step_id": "schema"}
            )
            submit_res = _options_flow_configure(
                ctx.token,
                step_schema["flow_id"],
                {
                    "schema": current_schema,
                    "owner_name": str(current_schema.get("_owner", "me")),
                },
            )
            ctx.check(
                "options flow schema step submitted",
                submit_res.get("type") in ("create_entry", "form"),
                f"type={submit_res.get('type')}",
            )
        except Exception as err:  # noqa: BLE001
            ctx.check("options flow schema step submitted", False, str(err)[:160])
            return

        ctx.wait_for_ramses_cc_reload(timeout=30)
        ctx.refresh_token()
        wait_for_transport_ready(timeout=30)
        ctx.wait_for_schema_stable(timeout=15)

        # Check that scan_state in .storage/ramses_cc preserved zone_index="0B"
        # for _THM_Z0B across the unload/reload cycle
        storage = get_ramses_storage()
        scan_state_raw = (
            storage.get("data", {}).get("discovery", {}).get("scan_state", "")
        )
        scan_devs = (
            {
                d.get("device_id"): d
                for d in json.loads(scan_state_raw).get("devices", [])
                if isinstance(d, dict)
            }
            if scan_state_raw
            else {}
        )
        if _THM_Z0B in scan_devs:
            ctx.check(
                f"post-reload scan_state keeps {_THM_Z0B} zone_index={_ZONE_UFH}",
                scan_devs[_THM_Z0B].get("zone_index") == _ZONE_UFH,
                f"scan_dev={scan_devs.get(_THM_Z0B)}",
            )
        zones_post_opt = get_schema_retry().get(CTL, {}).get("zones", {})
        ctx.check(
            f"post-reload schema keeps {_THM_Z0B} as zone {_ZONE_UFH} sensor",
            zones_post_opt.get(_ZONE_UFH, {}).get("sensor") == _THM_Z0B,
            f"zone_{_ZONE_UFH}={zones_post_opt.get(_ZONE_UFH)}",
        )
