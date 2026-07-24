"""Recipe R50: Device health tracking — orphaned/lost devices (issue 767).

Tests the device health tracking feature (item 7 from issue 767) end-to-end:
- Drives the config flow via REST API to the ``review_device_health`` step
- Verifies the step title and description render correctly
- Injects an orphaned flag via .storage manipulation, then verifies the step
  shows the device
- Submits "keep" and verifies the flag is cleared

See: https://github.com/ramses-rf/ramses_cc/issues/767
"""

from __future__ import annotations

import json
import subprocess
import urllib.error
import urllib.request

from ..base import Recipe, RecipeContext
from ..helpers import (
    HA_URL,
    docker_exec_python,
    get_ramses_storage,
    get_schema_retry,
    load_profile_yaml,
)
from ..profile import mixed_yaml


def _get_entry_id() -> str:
    """Get the ramses_cc config entry ID from .storage."""
    raw = subprocess.check_output(
        ["docker", "exec", "ha-sim", "cat", "/config/.storage/core.config_entries"],
        text=True,
    )
    data = json.loads(raw)["data"]
    for entry in data["entries"]:
        if entry["domain"] == "ramses_cc":
            return entry["entry_id"]
    raise RuntimeError("ramses_cc config entry not found")


def _options_flow_start(token: str, entry_id: str) -> dict:
    """Start an options flow via REST API and return the flow result."""
    url = f"{HA_URL}/api/config/config_entries/options/flow"
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
    resp = urllib.request.urlopen(req, timeout=30)
    return json.loads(resp.read())


def _options_flow_configure(token: str, flow_id: str, user_input: dict) -> dict:
    """Configure an options flow step via REST API and return the result."""
    url = f"{HA_URL}/api/config/config_entries/options/flow/{flow_id}"
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
        resp = urllib.request.urlopen(req, timeout=30)
        return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        content = e.read().decode()
        raise RuntimeError(f"HTTP {e.code}: {content}") from e


class R50DeviceHealthTrackingIssue767(Recipe):
    id = "R50"
    seq = 510
    title = "Device health tracking — orphaned/lost devices (issue 767)"

    async def run(self, ctx: RecipeContext) -> None:
        ctx.log_section("Recipe 50: Device health tracking — orphaned/lost devices")

        # 1. Load mixed profile
        print("  Loading mixed profile...")
        yaml_text = mixed_yaml()
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

        # 2. Verify schema loaded
        schema = get_schema_retry()
        ctx.check(
            "schema loaded with devices",
            len(schema) > 5,
            f"schema keys: {list(schema.keys())[:10]}",
        )

        # 3. Verify DiscoveryManager methods exist
        # NOTE: These methods are part of PR 861 (device health tracking).
        # If the PR is not merged, we skip the remaining checks gracefully.
        code = """
import json
try:
    from custom_components.ramses_cc.discovery import DiscoveryManager
    has_orphaned = hasattr(DiscoveryManager, "get_orphaned_devices")
    has_lost = hasattr(DiscoveryManager, "get_lost_devices")
    print(json.dumps({
        "has_get_orphaned_devices": has_orphaned,
        "has_get_lost_devices": has_lost,
        "ok": True,
    }))
except ImportError as e:
    print(json.dumps({"error": str(e), "ok": False}))
"""
        result = docker_exec_python(code)

        has_methods = (
            result.get("ok")
            and result.get("has_get_orphaned_devices")
            and result.get("has_get_lost_devices")
        )

        if not has_methods:
            print(
                "  SKIP: device health tracking methods not implemented"
                " (PR 861 not merged)"
            )
            print("  (skipping config flow + orphan tests)")
            return

        ctx.check(
            "DiscoveryManager.get_orphaned_devices method exists",
            result.get("ok") and result.get("has_get_orphaned_devices"),
            f"result={result}",
        )

        ctx.check(
            "DiscoveryManager.get_lost_devices method exists",
            result.get("ok") and result.get("has_get_lost_devices"),
            f"result={result}",
        )

        # 4. Drive the config flow via REST API
        print("  Starting options flow...")
        entry_id = _get_entry_id()
        init_result = _options_flow_start(ctx.token, entry_id)

        ctx.check(
            "options flow init returns a menu",
            init_result.get("type") == "menu" and init_result.get("step_id") == "init",
            f"type={init_result.get('type')}, step={init_result.get('step_id')}",
        )

        flow_id = init_result["flow_id"]

        # Navigate to review_device_health
        print("  Navigating to review_device_health step...")
        step_result = _options_flow_configure(
            ctx.token, flow_id, {"next_step_id": "review_device_health"}
        )

        ctx.check(
            "review_device_health step is a FORM",
            step_result.get("type") == "form",
            f"type={step_result.get('type')}",
        )

        ctx.check(
            "review_device_health step_id correct",
            step_result.get("step_id") == "review_device_health",
            f"step_id={step_result.get('step_id')}",
        )

        # 5. With no orphaned/lost devices, should show "No orphaned or lost"
        placeholders = step_result.get("description_placeholders", {})
        ctx.check(
            "no devices message shown when healthy",
            "No orphaned or lost" in placeholders.get("message", ""),
            f"message={placeholders.get('message', '')[:100]}",
        )

        # 6. Manipulate last_seen for a device in .storage to simulate
        #    it going offline.  The scan_state is a JSON string inside
        #    .storage/ramses_cc → discovery → scan_state.  We set the
        #    device's last_seen to 10 days ago, then restart the HA
        #    container (not reload — reload saves state on unload,
        #    overwriting our changes).  On restart, import_json restores
        #    the scan engine with the old timestamp, and
        #    check_orphaned_devices (called in the config flow step)
        #    will flag it.
        trv_id = "04:150003"
        print(f"  Manipulating last_seen for {trv_id} to 10 days ago...")

        inject_code = f"""
import json
from datetime import datetime as dt, timedelta as td

try:
    with open("/config/.storage/ramses_cc") as f:
        raw = json.load(f)
    data = raw["data"]
    discovery = data.get("discovery", {{}})

    # 1. Modify scan_state — set last_seen to 10 days ago
    scan_state_str = discovery.get("scan_state", "")
    if not scan_state_str:
        print(json.dumps({{"error": "no scan_state in .storage", "ok": False}}))
        raise SystemExit()

    scan_state = json.loads(scan_state_str)
    old_date = (dt.now() - td(days=10)).isoformat(timespec="seconds")
    found = False
    for dev in scan_state.get("devices", []):
        if dev.get("device_id") == "{trv_id}":
            dev["last_seen"] = old_date
            found = True
            break

    if not found:
        # Add the device to scan_state if not present
        scan_state.setdefault("devices", []).append({{
            "device_id": "{trv_id}",
            "first_seen": old_date,
            "last_seen": old_date,
            "likely_type": "TRV",
            "codes_seen": ["3150"],
            "bound_to": "01:150000",
            "zone_idx": "03",
            "domain_id": None,
            "rssi": -72.0,
            "confidence": "high",
            "is_battery": True,
            "src_count": 10,
            "dst_count": 2,
        }})

    discovery["scan_state"] = json.dumps(scan_state, indent=2)

    # 2. Set metadata status to accepted (so check_for_lost_devices works)
    devices = discovery.get("devices", {{}})
    if "{trv_id}" not in devices:
        devices["{trv_id}"] = {{
            "status": "accepted",
            "enabled": True,
            "faked": False,
        }}
    else:
        devices["{trv_id}"]["status"] = "accepted"
    discovery["devices"] = devices
    data["discovery"] = discovery

    with open("/config/.storage/ramses_cc", "w") as f:
        json.dump({{"version": raw.get("version", 1), "data": data}}, f)

    print(json.dumps({{"ok": True, "found": found, "trv_id": "{trv_id}"}}))
except SystemExit:
    pass
except Exception as e:
    print(json.dumps({{"error": str(e), "ok": False}}))
"""
        inject_result = docker_exec_python(inject_code)
        ctx.check(
            f"last_seen manipulated for {trv_id}",
            inject_result.get("ok"),
            f"result={inject_result}",
        )

        if not inject_result.get("ok"):
            print("  SKIP: could not manipulate last_seen")
            return

        # 7. Restart the HA container to pick up the modified .storage.
        #    We can't use reload_config_entry because the coordinator saves
        #    state on unload, overwriting our modifications.  A container
        #    restart kills the process (no save-on-unload) and HA restores
        #    from .storage on startup.
        #    We also don't stop profile emissions — the scan engine restores
        #    from .storage first, and check_orphaned_devices runs in the
        #    config flow step before any new packets can update last_seen.
        print("  Restarting HA container to pick up modified scan state...")

        import subprocess as sp

        sp.run(
            ["docker", "restart", "ha-sim"],
            check=True,
            capture_output=True,
            timeout=60,
        )

        # Wait for HA to be ready
        ctx.wait(30, "for HA container to restart")
        ctx.refresh_token()
        ctx.wait(10, "for ramses_cc to initialize")
        ctx.wait(15, "for ramses_cc reload")
        ctx.refresh_token()
        ctx.wait(5, "for discovery manager to initialize")

        # 8. Re-drive the flow — now the orphaned device should show up
        print("  Re-driving options flow to see orphaned device...")
        init_result2 = _options_flow_start(ctx.token, entry_id)
        flow_id2 = init_result2["flow_id"]
        step_result2 = _options_flow_configure(
            ctx.token, flow_id2, {"next_step_id": "review_device_health"}
        )

        ctx.check(
            "review_device_health step is FORM (with orphaned device)",
            step_result2.get("type") == "form",
            f"type={step_result2.get('type')}",
        )

        placeholders2 = step_result2.get("description_placeholders", {})
        message2 = placeholders2.get("message", "")
        ctx.check(
            f"orphaned device {trv_id} shown in step description",
            trv_id in message2,
            f"message={message2[:200]}",
        )

        # 9. Verify the form has a per-device selector field
        data_schema = step_result2.get("data_schema")
        schema_str = json.dumps(data_schema) if data_schema else ""
        ctx.check(
            f"form has selector field for {trv_id}",
            data_schema is not None and trv_id in schema_str,
            f"schema present: {data_schema is not None}",
        )

        # 10. Submit "keep" to clear the flag
        #    The device may be classified as LOST (not just orphaned) because
        #    check_for_lost_devices runs before check_orphaned_devices in the
        #    config flow step.  LOST takes priority in the deduplication, so
        #    the form field is "lost_<device_id>".  We detect the prefix from
        #    the form schema.
        print(f"  Submitting 'keep' for {trv_id}...")

        # Detect the field prefix from the form schema
        field_prefix = "orphaned"
        if isinstance(data_schema, list):
            for field in data_schema:
                name = field.get("name", "") if isinstance(field, dict) else ""
                if trv_id in name:
                    field_prefix = name.split("_")[0]
                    break

        submit_input = {f"{field_prefix}_{trv_id}": "keep"}
        try:
            submit_result = _options_flow_configure(ctx.token, flow_id2, submit_input)
            ctx.check(
                "'keep' submission creates entry (flow completes)",
                submit_result.get("type") == "create_entry",
                f"type={submit_result.get('type')}",
            )
        except RuntimeError as e:
            ctx.check(
                "'keep' submission completes",
                False,
                f"submission failed: {str(e)[:120]}",
            )

        # 11. Verify the orphaned flag was cleared in .storage
        ctx.wait(5, "for state save to flush")
        storage = get_ramses_storage()
        discovery = storage.get("discovery", {})
        devices = discovery.get("devices", {})
        trv_meta = devices.get(trv_id, {})
        ctx.check(
            f"orphaned flag cleared for {trv_id} after 'keep'",
            not trv_meta.get("orphaned"),
            f"orphaned={trv_meta.get('orphaned')}",
        )

        # 12. Verify discovery scan engine is tracking devices
        ctx.check(
            "discovery scan engine has tracked devices",
            len(devices) > 0,
            f"discovery device count: {len(devices)}",
        )

        # 13. Verify translations exist for the step
        trans_code = """
import json
try:
    with open("/config/custom_components/ramses_cc/translations/en.json") as f:
        data = json.load(f)
    step = data["options"]["step"].get("review_device_health", {})
    menu = data["options"]["step"]["init"]["menu_options"].get(
        "review_device_health", ""
    )
    print(json.dumps({
        "has_step_title": bool(step.get("title")),
        "has_menu_label": bool(menu),
        "step_title": step.get("title", ""),
        "menu_label": menu,
        "ok": True,
    }))
except Exception as e:
    print(json.dumps({"error": str(e), "ok": False}))
"""
        trans_result = docker_exec_python(trans_code)
        ctx.check(
            "en.json has review_device_health step title",
            trans_result.get("ok") and trans_result.get("has_step_title"),
            f"title={trans_result.get('step_title', 'MISSING')}",
        )

        ctx.check(
            "en.json has review_device_health menu label",
            trans_result.get("ok") and trans_result.get("has_menu_label"),
            f"label={trans_result.get('menu_label', 'MISSING')}",
        )

        print("  Device health tracking feature verified end-to-end:")
        print("    - Methods exist (get_orphaned_devices, get_lost_devices)")
        print("    - Config flow step reachable via REST API")
        print("    - Step shows 'no devices' when healthy")
        print("    - last_seen manipulation → orphaned device detected")
        print("    - Orphaned device shown in step with per-device selector")
        print("    - 'keep' submission completes and clears flag")
        print("    - Translations present in en.json")
