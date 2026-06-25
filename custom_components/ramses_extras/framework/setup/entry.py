"""Entry point setup and lifecycle management for Ramses Extras integration.

This module provides the main setup functions for the Ramses Extras Home Assistant
integration, including entry setup, configuration management, and cleanup operations.

Key functions:
- async_setup_entry: Main integration setup, calls run_entry_setup_pipeline to setup all
features
- async_unload_entry: Integration cleanup
- async_update_listener: Configuration updates
- initialize_entry_data: Data structure initialization
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from ...const import DOMAIN, PLATFORM_REGISTRY
from ...feature_utils import get_enabled_features_dict
from .cards import expose_feature_config_to_frontend, setup_card_files_and_config
from .devices import (
    async_setup_platforms,
    cleanup_orphaned_devices,
    discover_and_store_devices,
    setup_entity_registry_device_refresh,
)
from .features import (
    create_and_start_feature_instances,
    load_feature_definitions_and_platforms,
)

_LOGGER = logging.getLogger(__name__)


def apply_log_level_from_entry(entry: ConfigEntry) -> None:
    """Apply logging level configuration from config entry.

    :param entry: Configuration entry containing log level settings
    """
    log_level_raw = entry.options.get("log_level")
    if not isinstance(log_level_raw, str):
        return

    log_level = log_level_raw.lower().strip()
    level_map = {
        "debug": logging.DEBUG,
        "info": logging.INFO,
        "warning": logging.WARNING,
        "error": logging.ERROR,
    }

    level = level_map.get(log_level)
    if level is None:
        return

    logging.getLogger("custom_components.ramses_extras").setLevel(level)


def initialize_entry_data(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Initialize hass.data structure for Ramses Extras integration.

    Sets up the data structure in hass.data to store integration state,
    configuration, and enabled features.

    :param hass: Home Assistant instance
    :param entry: Configuration entry for the integration
    """
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {}
    hass.data[DOMAIN]["entry_id"] = entry.entry_id
    hass.data[DOMAIN]["config_entry"] = entry
    hass.data[DOMAIN]["enabled_features"] = get_enabled_features_dict(
        hass,
        entry,
        include_default=False,
        prefer_hass_data=False,
    )
    hass.data[DOMAIN]["PLATFORM_REGISTRY"] = PLATFORM_REGISTRY


async def register_services(hass: HomeAssistant) -> None:
    """Register Ramses Extras services with Home Assistant.

    :param hass: Home Assistant instance
    """
    _LOGGER.info("Registering Ramses Extras services")

    from ...services_integration import async_register_feature_services

    await async_register_feature_services(hass)


async def validate_startup_entities_simple(
    hass: HomeAssistant, entry: ConfigEntry
) -> None:
    """Validate entities on startup using SimpleEntityManager.

    Restores device feature matrix state and validates all entities
    to ensure they are properly configured and available.

    :param hass: Home Assistant instance
    :param entry: Configuration entry containing device feature matrix
    """
    try:
        from ..helpers.entity.simple_entity_manager import SimpleEntityManager

        entity_manager = SimpleEntityManager(hass)

        matrix_state = entry.data.get("device_feature_matrix", {})
        if matrix_state:
            entity_manager.restore_device_feature_matrix_state(matrix_state)
            _LOGGER.info("Restored matrix state with %d devices", len(matrix_state))

        await entity_manager.validate_entities_on_startup()

        _LOGGER.info("SimpleEntityManager startup validation completed")

    except Exception as e:
        _LOGGER.error("SimpleEntityManager startup validation failed: %s", e)
        import traceback

        _LOGGER.debug("Full traceback: %s", traceback.format_exc())


async def run_entry_setup_pipeline(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Run the complete setup pipeline for Ramses Extras integration.

    Executes all setup steps in the correct order:
    1. Load feature definitions and platforms
    2. Setup card files and configuration
    3. Register services
    4. Setup platforms
    5. Validate startup entities
    6. Cleanup orphaned devices
    7. Create and start feature instances
    8. Configure zones from YAML in zone coordinators

    :param hass: Home Assistant instance
    :param entry: Configuration entry for the integration
    """
    await load_feature_definitions_and_platforms(
        hass,
        entry,
        discover_and_store_devices_fn=discover_and_store_devices,
    )

    _LOGGER.debug("WebSocket functionality uses feature-centric architecture")

    # Clear version cache to ensure fresh version lookup for downgrades
    data = hass.data.setdefault(DOMAIN, {})
    data.pop("_integration_version", None)
    _LOGGER.debug("Cleared integration version cache for fresh lookup")

    # Start the shared message stream early so that all features (including
    # the HVAC Fan Card's frontend message broker) receive real-time RAMSES
    # messages.  This must happen before card setup so that the stream is
    # ready when the card requests data.
    from ..helpers.ramses_message_stream import get_ramses_message_stream

    stream = get_ramses_message_stream(hass)
    stream.start()
    _LOGGER.info("Started shared Ramses message stream")

    await setup_card_files_and_config(hass, entry)

    await register_services(hass)

    await async_setup_platforms(hass)

    await validate_startup_entities_simple(hass, entry)

    await cleanup_orphaned_devices(hass, entry)

    await create_and_start_feature_instances(hass, entry)

    # Configure zones from YAML in zone coordinators
    await configure_zones_from_yaml(hass)


async def configure_zones_from_yaml(hass: HomeAssistant) -> None:
    """Configure zones from YAML in zone coordinators.

    Loads zones from the configuration and configures them in the
    appropriate zone coordinators with their valve entity settings.

    :param hass: Home Assistant instance
    """
    from ..helpers.config.model import get_fan_max_open_zones
    from ..helpers.zone_coordinator import get_zone_coordinator
    from ..helpers.zones import get_zone_registry

    _LOGGER.debug("Configuring zones from YAML...")

    zone_registry = get_zone_registry(hass)
    all_zones = zone_registry.list_all_zones()

    _LOGGER.debug("Found %s FANs with zones", len(all_zones))

    # Get zones section for max_open_zones lookup
    from ..helpers.config.migration import get_migrated_feature_section

    config_entry = hass.data.get(DOMAIN, {}).get("config_entry")
    raw_config: dict = {}
    if config_entry:
        if config_entry.data:
            raw_config.update(config_entry.data)
        if config_entry.options:
            raw_config.update(config_entry.options)
    zones_section = get_migrated_feature_section(raw_config, "zones")

    for fan_id, zones in all_zones.items():
        _LOGGER.debug("Processing FAN %s with %s zones", fan_id, len(zones))
        coordinator = get_zone_coordinator(hass, fan_id)

        # Set max_open_zones from config
        max_open_zones = get_fan_max_open_zones(zones_section, fan_id)
        if max_open_zones is not None:
            coordinator.set_max_open_zones(max_open_zones)
            _LOGGER.info("Set max_open_zones=%s for FAN %s", max_open_zones, fan_id)
        for zone in zones:
            zone_id = zone.get("zone_id")
            if not zone_id:
                _LOGGER.warning("Zone missing zone_id for FAN %s", fan_id)
                continue

            zone_type = zone.get("type", "paired_valves")
            inlet_entity = zone.get("inlet_valve_entity")
            outlet_entity = zone.get("outlet_valve_entity")
            min_position = zone.get("min_position", 0)
            max_position = zone.get("max_position", 100)
            actuation_priority = zone.get("actuation_priority", 100)

            _LOGGER.debug(
                "Zone %s:%s - type=%s, inlet=%s, outlet=%s, priority=%s",
                fan_id,
                zone_id,
                zone_type,
                inlet_entity,
                outlet_entity,
                actuation_priority,
            )

            # Only configure controllable zones with valve entities
            if zone_type in ("paired_valves", "custom_valve", "shelly_2pm_gen3"):
                if not inlet_entity or not outlet_entity:
                    _LOGGER.warning(
                        "Zone %s:%s missing valve entities, skipping",
                        fan_id,
                        zone_id,
                    )
                    continue

                coordinator.configure_zone(
                    zone_id=zone_id,
                    zone_type=zone_type,
                    inlet_valve_entity=inlet_entity,
                    outlet_valve_entity=outlet_entity,
                    min_position=min_position,
                    max_position=max_position,
                    is_controllable=True,
                    actuation_priority=actuation_priority,
                )
                _LOGGER.info(
                    "Configured zone %s:%s type=%s inlet=%s outlet=%s priority=%s",
                    fan_id,
                    zone_id,
                    zone_type,
                    inlet_entity,
                    outlet_entity,
                    actuation_priority,
                )

    _LOGGER.info("Configured zones from YAML for %s FANs", len(all_zones))


async def async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle configuration updates for the integration.

    Called when the configuration entry is updated. Manages changes to
    enabled features, device feature matrix, and debug settings.
    Triggers reload when significant changes occur.

    :param hass: Home Assistant instance
    :param entry: Updated configuration entry
    """
    try:
        data = hass.data.setdefault(DOMAIN, {})

        apply_log_level_from_entry(entry)

        old_debug_mode_raw = data.get("debug_mode")
        old_debug_mode = (
            bool(old_debug_mode_raw) if old_debug_mode_raw is not None else None
        )

        old_enabled_features_raw = data.get("enabled_features")
        if isinstance(old_enabled_features_raw, dict):
            old_enabled_features = old_enabled_features_raw
        else:
            old_enabled_features = {}

        new_enabled_features = get_enabled_features_dict(
            hass,
            entry,
            include_default=False,
            prefer_hass_data=False,
        )

        old_matrix_state_raw = data.get("device_feature_matrix")
        new_matrix_state_raw = entry.data.get("device_feature_matrix") or {}

        old_matrix_state = (
            old_matrix_state_raw if isinstance(old_matrix_state_raw, dict) else {}
        )
        new_matrix_state = (
            new_matrix_state_raw if isinstance(new_matrix_state_raw, dict) else {}
        )

        data["enabled_features"] = new_enabled_features
        data["device_feature_matrix"] = new_matrix_state

        await expose_feature_config_to_frontend(hass, entry)

        frontend_log_level_raw = entry.options.get("frontend_log_level")
        if isinstance(frontend_log_level_raw, str) and frontend_log_level_raw:
            frontend_log_level = frontend_log_level_raw
        else:
            frontend_log_level = (
                "debug" if bool(entry.options.get("debug_mode")) else "info"
            )

        debug_mode = frontend_log_level == "debug"

        log_level = entry.options.get("log_level")
        if not isinstance(log_level, str) or not log_level:
            log_level = "info"

        data["debug_mode"] = debug_mode
        data["frontend_log_level"] = frontend_log_level
        data["log_level"] = log_level

        if old_debug_mode is None or old_debug_mode != debug_mode:
            _LOGGER.info("Debug mode changed: %s -> %s", old_debug_mode, debug_mode)

        options_payload: dict[str, Any] = {}
        default_poll_ms = entry.options.get("ramses_debugger_default_poll_ms")
        if isinstance(default_poll_ms, int):
            options_payload["ramses_debugger_default_poll_ms"] = int(default_poll_ms)

        hass.bus.async_fire(
            "ramses_extras_options_updated",
            {
                "enabled_features": new_enabled_features,
                "device_feature_matrix": new_matrix_state,
                "debug_mode": debug_mode,
                "frontend_log_level": frontend_log_level,
                "log_level": log_level,
                "cards_enabled": data.get("cards_enabled") is True,
                "options": options_payload,
            },
        )

        enabled_features_changed = old_enabled_features != new_enabled_features
        matrix_changed = old_matrix_state != new_matrix_state

        if enabled_features_changed or matrix_changed:
            if data.get("_reload_pending") is True:
                return

            data["_reload_pending"] = True

            async def _do_reload() -> None:
                try:
                    entry_id = getattr(entry, "entry_id", None)
                    if not isinstance(entry_id, str) or not entry_id:
                        return

                    if hass.config_entries.async_get_entry(entry_id) is None:
                        return

                    await hass.config_entries.async_reload(entry_id)
                finally:
                    hass.data.get(DOMAIN, {}).pop("_reload_pending", None)

            hass.async_create_task(_do_reload())

    except Exception as e:
        _LOGGER.warning("Failed to update frontend feature configuration: %s", e)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Ramses Extras integration from a config entry.

    This is the main setup function that initializes the entire integration,
    including data structures, platforms, services, and features.

    :param hass: Home Assistant instance
    :param entry: Configuration entry for the integration

    :return: True if setup was successful, False otherwise
    """
    _LOGGER.info("Starting Ramses Extras integration setup...")

    apply_log_level_from_entry(entry)

    initialize_entry_data(hass, entry)

    await setup_entity_registry_device_refresh(
        hass,
        entry,
        discover_and_store_devices_fn=discover_and_store_devices,
    )

    entry.async_on_unload(entry.add_update_listener(async_update_listener))

    _LOGGER.debug("Enabled features: %s", entry.data.get("enabled_features", {}))

    await run_entry_setup_pipeline(hass, entry)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload Ramses Extras integration.

    Cleans up all integration resources including platforms, services,
    automations, and data structures when the integration is unloaded.

    :param hass: Home Assistant instance
    :param entry: Configuration entry to unload

    :return: True if unload was successful, False otherwise
    """
    _LOGGER.info("Unloading Ramses Extras integration...")

    # Stop the shared message stream
    if DOMAIN in hass.data:
        domain_data = hass.data[DOMAIN]
        if isinstance(domain_data, dict):
            stream = domain_data.get("ramses_message_stream")
            if stream is not None and hasattr(stream, "stop"):
                try:
                    stream.stop()
                    _LOGGER.info("Stopped shared Ramses message stream")
                except Exception as e:
                    _LOGGER.warning("Failed to stop message stream: %s", e)

            remote_listener_unsubs = domain_data.get("_fan_remote_listener_unsubs", [])
            if isinstance(remote_listener_unsubs, list):
                for unsub in remote_listener_unsubs:
                    try:
                        if callable(unsub):
                            unsub()
                    except Exception as e:
                        _LOGGER.warning("Failed to remove remote fan listener: %s", e)

            # Stop humidity_control automation if running
            if "humidity_automation" in domain_data:
                try:
                    automation = domain_data["humidity_automation"]
                    if hasattr(automation, "stop"):
                        await automation.stop()
                        _LOGGER.info("Stopped humidity control automation")
                except Exception as e:
                    _LOGGER.warning("Failed to stop automation: %s", e)

    from ...services_integration import async_unload_feature_services

    await async_unload_feature_services(hass)

    unload_ok = await hass.config_entries.async_unload_platforms(
        entry,
        [
            Platform.SENSOR,
            Platform.SWITCH,
            Platform.BINARY_SENSOR,
            Platform.NUMBER,
            Platform.SELECT,
        ],
    )

    if unload_ok:
        hass.data.pop(DOMAIN, None)
        _LOGGER.info("Ramses Extras integration unloaded successfully")

    return bool(unload_ok)


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Remove Ramses Extras integration and clean up all related data.

    Removes all entities, devices, Lovelace resources, www files,
    and automations associated with this integration.

    :param hass: Home Assistant instance
    :param entry: Configuration entry being removed
    """
    import shutil
    from pathlib import Path

    from homeassistant.helpers.storage import Store

    _LOGGER.info("Removing Ramses Extras integration and cleaning up...")

    try:
        from ...features.device_simulator import async_restore_ramses_cc_gateway_topic
    except ImportError:
        async_restore_ramses_cc_gateway_topic = None  # type: ignore[assignment]
    if callable(async_restore_ramses_cc_gateway_topic):
        try:
            await async_restore_ramses_cc_gateway_topic(hass)
        except Exception as err:  # pragma: no cover - defensive
            _LOGGER.warning(
                "Failed to restore simulator gateway topic on removal: %s", err
            )

    # 1. Stop any running automations
    if DOMAIN in hass.data:
        domain_data = hass.data[DOMAIN]
        if isinstance(domain_data, dict):
            # Stop humidity_control automation if running
            if "humidity_automation" in domain_data:
                try:
                    automation = domain_data["humidity_automation"]
                    if hasattr(automation, "stop"):
                        await automation.stop()
                        _LOGGER.info("Stopped humidity control automation")
                except Exception as e:
                    _LOGGER.warning("Failed to stop automation: %s", e)

    # 2. Remove entities
    entity_registry = er.async_get(hass)
    entity_entries = list(entity_registry.entities.values())
    removed_entities = 0
    for entity_entry in entity_entries:
        if entity_entry.platform != DOMAIN:
            continue
        entity_registry.async_remove(entity_entry.entity_id)
        removed_entities += 1
    if removed_entities:
        _LOGGER.info("Removed %d entities", removed_entities)

    # 3. Remove devices
    device_registry = dr.async_get(hass)
    device_entries = list(device_registry.devices.values())
    entry_id = getattr(entry, "entry_id", None)
    if not isinstance(entry_id, str):
        entry_id = getattr(entry, "id", None)
    if not isinstance(entry_id, str):
        entry_id = None

    removed_devices = 0
    for device_entry in device_entries:
        if entry_id and entry_id in device_entry.config_entries:
            device_registry.async_remove_device(device_entry.id)
            removed_devices += 1
    if removed_devices:
        _LOGGER.info("Removed %d devices", removed_devices)

    # 4. Remove Lovelace resources
    try:
        store = Store(hass, 1, "lovelace_resources")
        data = await store.async_load()
        if data and "items" in data:
            original_count = len(data["items"])
            # Remove all ramses_extras resources
            data["items"] = [
                item
                for item in data["items"]
                if not item.get("url", "").startswith("/local/ramses_extras/")
            ]
            removed_resources = original_count - len(data["items"])
            if removed_resources > 0:
                await store.async_save(data)
                _LOGGER.info("Removed %d Lovelace resources", removed_resources)
    except Exception as e:
        _LOGGER.warning("Failed to remove Lovelace resources: %s", e)

    # 5. Remove www files
    try:
        www_path = Path(hass.config.path("www/ramses_extras"))
        if www_path.exists():
            await hass.async_add_executor_job(shutil.rmtree, www_path)
            _LOGGER.info("Removed www/ramses_extras directory")
    except Exception as e:
        _LOGGER.warning("Failed to remove www files: %s", e)

    # 6. Clear hass.data
    hass.data.pop(DOMAIN, None)

    _LOGGER.info("Ramses Extras integration removal complete")
