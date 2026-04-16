from __future__ import annotations

import asyncio
from copy import deepcopy
from functools import partial
from types import MappingProxyType
from typing import Any

import yaml
from custom_components.ramses_cc.const import CONF_SCHEMA
from homeassistant.core import HomeAssistant

from .const import LOGGER, SIMULATOR_HGI_ID
from .system_config import SystemConfigProfile, apply_timeout_scale

RAMSES_CC_STORAGE_KEY = "ramses_cc"
RAMSES_CC_STORAGE_VERSION = 1
SZ_CLIENT_STATE = "client_state"
SZ_SCHEMA = "schema"
SZ_PACKETS = "packets"


def _ensure_hgi_entry(
    known_list: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    if SIMULATOR_HGI_ID not in known_list:
        known_list = dict(known_list)
        known_list[SIMULATOR_HGI_ID] = {"class": "HGI"}
    return known_list


def parse_profile_yaml(yaml_text: str) -> dict[str, Any]:
    try:
        data = yaml.safe_load(yaml_text)
    except yaml.YAMLError as err:  # pragma: no cover - exercised via tests
        raise ValueError(f"Invalid YAML: {err}") from err
    if not isinstance(data, dict) or not data:
        raise ValueError("Profile YAML must define a mapping of devices")
    return data


def build_profile_from_payload(
    name: str,
    payload: dict[str, Any],
    *,
    description: str | None = None,
) -> SystemConfigProfile:
    device_configs: dict[str, Any]
    known_list = payload.get("_known_list") or payload.get("known_list")
    if known_list is None:
        known_list = payload
    if not isinstance(known_list, dict) or not known_list:
        raise ValueError("Profile YAML must include a 'known_list' mapping")
    device_configs = {"_known_list": _ensure_hgi_entry(dict(known_list))}

    if "_enforce_known_list" in payload:
        device_configs["_enforce_known_list"] = payload["_enforce_known_list"]
    else:
        device_configs["_enforce_known_list"] = {"enabled": True}

    if "_schema" in payload:
        device_configs["_schema"] = payload["_schema"]

    # Copy per-device overrides (keys that look like device IDs)
    for key, value in payload.items():
        if key in {
            "known_list",
            "_known_list",
            "_schema",
            "_enforce_known_list",
            "timeout_scale",
            "description",
        }:
            continue
        if isinstance(key, str) and ":" in key:
            device_configs[key] = value

    timeout_scale = payload.get("timeout_scale", 1.0)
    try:
        timeout_scale = float(timeout_scale)
    except (TypeError, ValueError):
        timeout_scale = 1.0

    profile_description = (
        description or payload.get("description") or "Imported profile"
    )

    return SystemConfigProfile(
        name=name,
        description=profile_description,
        timeout_scale=timeout_scale,
        device_configs=device_configs,
    )


def build_profile_from_yaml(
    name: str,
    yaml_text: str,
    *,
    description: str | None = None,
) -> SystemConfigProfile:
    payload = parse_profile_yaml(yaml_text)
    profile = build_profile_from_payload(name, payload, description=description)
    profile.source_yaml = yaml_text
    return profile


def profile_to_yaml(profile: SystemConfigProfile) -> str:
    """Render a SystemConfigProfile back to a YAML string."""

    if profile.source_yaml:
        return profile.source_yaml

    payload: dict[str, Any] = {}
    known_list = profile.device_configs.get("_known_list")
    if known_list:
        payload["known_list"] = known_list

    enforce = profile.device_configs.get("_enforce_known_list")
    if enforce is not None:
        payload["_enforce_known_list"] = enforce

    schema = profile.device_configs.get("_schema")
    if schema:
        payload["_schema"] = schema

    for key, value in profile.device_configs.items():
        if key.startswith("_"):
            continue
        payload[key] = value

    if profile.description:
        payload["description"] = profile.description

    if profile.timeout_scale not in (None, 1.0):
        payload["timeout_scale"] = profile.timeout_scale

    yaml_text = str(yaml.safe_dump(payload, sort_keys=False))
    profile.source_yaml = yaml_text
    return yaml_text


async def _trigger_ramses_discovery(hass: HomeAssistant) -> None:
    """Poke the ramses_cc coordinator to run device discovery immediately."""

    try:
        ramses_cc_entries = hass.config_entries.async_entries("ramses_cc")
        if not ramses_cc_entries:
            return
        entry_id = ramses_cc_entries[0].entry_id
        coordinator = (hass.data.get("ramses_cc") or {}).get(entry_id)
        if coordinator is None:
            return
        discover = getattr(coordinator, "_async_discovery_task", None)
        if callable(discover):
            LOGGER.debug("Triggering immediate ramses_cc discovery after burst")
            await discover()
    except Exception as err:  # noqa: BLE001
        LOGGER.warning("Could not trigger ramses_cc discovery: %s", err)


async def async_apply_profile(
    hass: HomeAssistant,
    profile_name: str,
    profile: SystemConfigProfile,
    *,
    reload_ramses_cc: bool = True,
    speed: float | None = None,
    auto_start_devices: bool = False,
) -> dict[str, Any]:
    """Apply a profile: stop devices, update known_list, reload, set timeouts."""

    ra = hass.data.setdefault("ramses_extras", {})
    actions: list[str] = []

    engine = ra.get("device_simulator_engine")
    if engine:
        await engine.async_stop_all()
        actions.append("stopped_devices")

    known_list = profile.device_configs.get("_known_list")
    schema = profile.device_configs.get("_schema")
    schema_payload = dict(schema) if isinstance(schema, dict) else None
    if known_list is not None:
        actions.extend(
            await _update_known_list_and_reload(
                hass,
                dict(known_list),
                profile.device_configs.get("_enforce_known_list", False),
                reload_ramses_cc,
                auto_start_on_reload=auto_start_devices,
                schema=schema_payload,
            )
        )

    scale = speed if speed is not None else profile.timeout_scale
    apply_timeout_scale(scale)
    actions.append(f"timeout_scale={scale}")

    LOGGER.info("Loaded simulator profile: %s (actions: %s)", profile_name, actions)
    return {
        "success": True,
        "profile": profile_name,
        "actions": actions,
    }


async def _update_known_list_and_reload(
    hass: HomeAssistant,
    known_list: dict[str, Any],
    enforce_cfg: Any,
    reload_ramses_cc: bool,
    *,
    auto_start_on_reload: bool = True,
    schema: dict[str, Any] | None = None,
) -> list[str]:
    """Persist known_list to ramses_cc options and optionally reload the entry."""

    actions: list[str] = []
    ramses_cc_entries = hass.config_entries.async_entries("ramses_cc")
    if not ramses_cc_entries:
        LOGGER.warning("Profile load: no ramses_cc config entry found")
        return actions

    entry = ramses_cc_entries[0]
    new_options = dict(entry.options)
    new_options["known_list"] = known_list

    enforce = (
        bool(enforce_cfg.get("enabled", False))
        if isinstance(enforce_cfg, dict)
        else bool(enforce_cfg)
    )
    ramses_rf_opts = dict(new_options.get("ramses_rf", {}))
    ramses_rf_opts["enforce_known_list"] = enforce
    new_options["ramses_rf"] = ramses_rf_opts

    if schema is not None:
        new_options[CONF_SCHEMA] = deepcopy(schema)
    else:
        new_options.pop(CONF_SCHEMA, None)

    object.__setattr__(entry, "options", MappingProxyType(new_options))

    try:
        from homeassistant.helpers.storage import Store as HaStore

        ce_store: HaStore = HaStore(hass, 1, "core.config_entries")
        ce_data: dict = await ce_store.async_load() or {}
        for stored_entry in ce_data.get("entries", []):
            if stored_entry.get("entry_id") == entry.entry_id:
                stored_entry["options"] = dict(new_options)
                break
        await ce_store.async_save(ce_data)
        LOGGER.debug("Profile load: persisted ramses_cc options to store")
    except Exception as err:  # noqa: BLE001
        LOGGER.warning("Profile load: could not persist ramses_cc options: %s", err)

    actions.append("updated_known_list")
    LOGGER.info(
        "Profile load: known_list=%s enforce_known_list=%s schema_keys=%s",
        list(known_list.keys()),
        enforce,
        list(schema.keys()) if schema else [],
    )

    profile_devices = {
        dev_id: cfg for dev_id, cfg in known_list.items() if cfg.get("class") != "HGI"
    }

    if reload_ramses_cc:
        hass.async_create_task(
            _reload_ramses_cc(
                hass,
                entry.entry_id,
                True,
                auto_start_on_reload,
                profile_devices,
            )
        )
        actions.append("reloading_ramses_cc")
    else:
        actions.append("skipped_reload")

    return actions


async def _reload_ramses_cc(
    hass: HomeAssistant,
    entry_id: str,
    wipe_schema: bool,
    auto_start_on_reload: bool,
    profile_devices: dict[str, dict],
) -> None:
    """Unload ramses_cc, reload it, and auto-start devices."""

    from homeassistant.helpers import device_registry as dr
    from homeassistant.helpers.storage import Store as HaStore

    await hass.config_entries.async_unload(entry_id)

    if wipe_schema:
        dev_reg = dr.async_get(hass)
        stale = dr.async_entries_for_config_entry(dev_reg, entry_id)
        for dev in stale:
            dev_reg.async_remove_device(dev.id)
        if stale:
            LOGGER.info("Profile load: removed %d stale HA devices", len(stale))

        try:
            ha_store: HaStore = HaStore(
                hass,
                RAMSES_CC_STORAGE_VERSION,
                RAMSES_CC_STORAGE_KEY,
            )
            stored: dict[str, Any] = await ha_store.async_load() or {}
            client_state = stored.get(SZ_CLIENT_STATE, {})
            changed = False
            if SZ_SCHEMA in client_state:
                client_state.pop(SZ_SCHEMA)
                changed = True
            if SZ_PACKETS in client_state:
                client_state.pop(SZ_PACKETS)
                changed = True
            if changed:
                await ha_store.async_save(stored)
                LOGGER.info("Profile load: cleared HA store schema+packets")
        except Exception as err:  # noqa: BLE001
            LOGGER.warning("Profile load: could not clear HA store schema: %s", err)

    await hass.config_entries.async_setup(entry_id)

    if profile_devices:
        ra = hass.data.get("ramses_extras", {})
        engine = ra.get("device_simulator_engine")
        if engine:
            await asyncio.sleep(3)
            from .scenario_engine import ActiveDevice

            for dev_id, dev_cfg in profile_devices.items():
                slug = dev_cfg.get("class", "FAN")
                device = ActiveDevice(
                    device_id=dev_id,
                    slug=slug,
                    variant_id="default",
                    excluded_codes=["1FC9"],
                    suppress_autonomous=False,
                    suppress_responses=False,
                    enabled=True,
                    origin="profile",
                )
                await engine.async_activate_device(
                    device,
                    start_emitter=auto_start_on_reload,
                    emit_startup_burst=False,
                )
                LOGGER.info("Profile load: registered %s (%s)", dev_id, slug)
            await asyncio.sleep(1)
            await _trigger_ramses_discovery(hass)
