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

    :param hass: Home Assistant instance
    :param entry: Configuration entry for the integration
    """
    await load_feature_definitions_and_platforms(
        hass,
        entry,
        discover_and_store_devices_fn=discover_and_store_devices,
    )

    _LOGGER.debug("WebSocket functionality uses feature-centric architecture")

    await setup_card_files_and_config(hass, entry)

    await register_services(hass)

    await async_setup_platforms(hass)

    await validate_startup_entities_simple(hass, entry)

    await cleanup_orphaned_devices(hass, entry)

    await create_and_start_feature_instances(hass, entry)


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

        hass.bus.async_fire(
            "ramses_extras_options_updated",
            {
                "enabled_features": new_enabled_features,
                "device_feature_matrix": new_matrix_state,
                "debug_mode": debug_mode,
                "frontend_log_level": frontend_log_level,
                "log_level": log_level,
                "cards_enabled": data.get("cards_enabled") is True,
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
    and data structures when the integration is unloaded.

    :param hass: Home Assistant instance
    :param entry: Configuration entry to unload

    :return: True if unload was successful, False otherwise
    """
    _LOGGER.info("Unloading Ramses Extras integration...")

    from ...services_integration import async_unload_feature_services

    await async_unload_feature_services(hass)

    unload_ok = await hass.config_entries.async_unload_platforms(
        entry,
        [
            Platform.SENSOR,
            Platform.SWITCH,
            Platform.BINARY_SENSOR,
            Platform.NUMBER,
        ],
    )

    if unload_ok:
        hass.data.pop(DOMAIN, None)

    return bool(unload_ok)


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Remove Ramses Extras integration and clean up all related data.

    Removes all entities and devices associated with this integration
    from the Home Assistant registries.

    :param hass: Home Assistant instance
    :param entry: Configuration entry being removed
    """
    entity_registry = er.async_get(hass)
    entity_entries = list(entity_registry.entities.values())
    for entity_entry in entity_entries:
        if entity_entry.platform != DOMAIN:
            continue
        entity_registry.async_remove(entity_entry.entity_id)

    device_registry = dr.async_get(hass)
    device_entries = list(device_registry.devices.values())
    entry_id = getattr(entry, "entry_id", None)
    if not isinstance(entry_id, str):
        entry_id = getattr(entry, "id", None)
    if not isinstance(entry_id, str):
        entry_id = None

    for device_entry in device_entries:
        if entry_id and entry_id in device_entry.config_entries:
            device_registry.async_remove_device(device_entry.id)
