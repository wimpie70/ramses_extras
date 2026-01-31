"""Feature setup and management for Ramses Extras integration.

This module provides functionality for loading, setting up, and managing
feature instances including platform imports, WebSocket integration,
and automation lifecycle management.

Feature Setup Flow (Called from entry.py):
These functions are called from run_entry_setup_pipeline() in entry.py:

1. load_feature_definitions_and_platforms (called early in pipeline):
   - Registers default commands from features/default/commands.py
   - Determines enabled features from config entry
   - Imports platform modules (sensor, switch, binary_sensor, number)
     for each enabled feature
   - Discovers Ramses devices and stores them in hass.data
   - Sets up platforms for device integration
   - Initializes WebSocket integration for real-time communication

2. create_and_start_feature_instances (called late in pipeline):
   - Dynamically creates feature instances using feature-specific creation functions
   - Manages automation lifecycle for each feature
   - Handles feature readiness events for card coordination
   - Sets up feature-specific automations and entities
   - Called after platforms, services, and validation are complete

Pipeline Context:
In run_entry_setup_pipeline(), the order is:
- load_feature_definitions_and_platforms (step 1)
- setup_card_files_and_config (step 2)
- register_services (step 3)
- async_setup_platforms (step 4)
- validate_startup_entities_simple (step 5)
- cleanup_orphaned_devices (step 6)
- create_and_start_feature_instances (step 7)

Key Functions:
- import_feature_platform_modules: Dynamic platform module importing
- setup_websocket_integration: Real-time communication setup
- load_feature_definitions_and_platforms: Main feature loading pipeline
- create_and_start_feature_instances: Feature instance management
"""

from __future__ import annotations

import asyncio
import importlib
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import Event, HomeAssistant, callback

from ...const import DOMAIN
from ...feature_utils import get_enabled_feature_names

_LOGGER = logging.getLogger(__name__)


async def import_feature_platform_modules(feature_names: list[str]) -> None:
    """Import platform modules for enabled features.

    Dynamically imports platform modules (sensor, switch, binary_sensor, number)
    for each enabled feature to make them available for Home Assistant.

    :param feature_names: List of feature names to import platforms for
    """
    platform_module_names = {
        Platform.SENSOR: "sensor",
        Platform.SWITCH: "switch",
        Platform.BINARY_SENSOR: "binary_sensor",
        Platform.NUMBER: "number",
    }

    for feature_name in feature_names:
        for platform_name in platform_module_names.values():
            module_path = (
                "custom_components.ramses_extras.features."
                f"{feature_name}.platforms.{platform_name}"
            )

            try:
                await asyncio.to_thread(importlib.import_module, module_path)
            except ModuleNotFoundError as err:
                if err.name in {module_path, module_path.rsplit(".", 1)[0]}:
                    continue
                _LOGGER.warning(
                    "Unexpected import error while loading platform module %s: %s",
                    module_path,
                    err,
                )
            except Exception as err:
                _LOGGER.warning(
                    "Error importing platform module %s: %s",
                    module_path,
                    err,
                )


async def setup_websocket_integration(hass: HomeAssistant) -> None:
    """Set up WebSocket integration for Ramses Extras.

    Initializes WebSocket commands and integration for real-time
    communication with the frontend.

    :param hass: Home Assistant instance
    """
    try:
        from ...websocket_integration import async_setup_websocket_integration

        success = await async_setup_websocket_integration(hass)
        if success:
            _LOGGER.info("WebSocket integration setup complete")
        else:
            _LOGGER.warning("WebSocket integration setup failed")

    except Exception as error:
        _LOGGER.error("Error setting up WebSocket integration: %s", error)


async def load_feature_definitions_and_platforms(
    hass: HomeAssistant,
    entry: ConfigEntry,
    *,
    discover_and_store_devices_fn: Any,
) -> None:
    """Load feature definitions and set up platforms.

    Registers default commands, loads enabled features, imports platform
    modules, discovers devices, sets up platforms, and initializes
    WebSocket integration.

    :param hass: Home Assistant instance
    :param entry: Configuration entry
    :param discover_and_store_devices_fn: Function to discover and store devices
    """
    from ...extras_registry import extras_registry
    from ...features.default.commands import register_default_commands

    register_default_commands()

    enabled_feature_names = get_enabled_feature_names(
        hass,
        entry,
        prefer_hass_data=False,
    )

    await asyncio.to_thread(extras_registry.load_all_features, enabled_feature_names)

    await import_feature_platform_modules(enabled_feature_names)

    await discover_and_store_devices_fn(hass)

    await hass.config_entries.async_forward_entry_setups(
        entry,
        [Platform.SENSOR, Platform.SWITCH, Platform.BINARY_SENSOR, Platform.NUMBER],
    )

    await setup_websocket_integration(hass)

    sensor_count = len(extras_registry.get_all_sensor_configs())
    switch_count = len(extras_registry.get_all_switch_configs())
    number_count = len(extras_registry.get_all_number_configs())
    boolean_count = len(extras_registry.get_all_boolean_configs())
    _LOGGER.info(
        "Entity registry loaded: %d sensor, %d switch, %d number, %d binary sensor",
        sensor_count,
        switch_count,
        number_count,
        boolean_count,
    )


async def create_and_start_feature_instances(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> None:
    """Create and start feature instances for enabled features.

    Dynamically creates feature instances using feature-specific creation
    functions, manages automation lifecycle, and handles feature readiness
    events for card coordination.

    :param hass: Home Assistant instance
    :param entry: Configuration entry
    """
    features = hass.data[DOMAIN].setdefault("features", {})
    feature_ready = hass.data[DOMAIN].setdefault("feature_ready", {})
    hass.data[DOMAIN].setdefault("cards_enabled", False)
    hass.data[DOMAIN]["cards_pending_features"] = set()

    enabled_feature_names = get_enabled_feature_names(
        hass,
        entry,
        prefer_hass_data=False,
    )

    automation_managers_to_start: list[Any] = []
    cards_pending_features: set[str] = set()

    @callback  # type: ignore[untyped-decorator]
    def _on_feature_ready(event: Event[dict[str, Any]]) -> None:
        feature_id = event.data.get("feature_id")
        if not isinstance(feature_id, str):
            return

        pending = hass.data.get(DOMAIN, {}).get("cards_pending_features")
        if not isinstance(pending, set):
            return

        if feature_id not in pending:
            return

        pending.discard(feature_id)

        _LOGGER.debug(
            "Cards latch: received feature_ready for %s, remaining pending=%s",
            feature_id,
            sorted(pending),
        )

        if pending:
            return

        if hass.data[DOMAIN].get("cards_enabled") is True:
            return

        hass.data[DOMAIN]["cards_enabled"] = True
        _LOGGER.debug("Cards latch: cards_enabled=True")
        hass.bus.async_fire("ramses_extras_cards_enabled", {})

    hass.data[DOMAIN]["cards_pending_features"] = cards_pending_features

    # Set up event listener BEFORE creating features to avoid race condition
    # where features fire ready events before listener is attached
    existing_unsub = hass.data[DOMAIN].get("_cards_enabled_unsub")
    if callable(existing_unsub):
        existing_unsub()

    hass.data[DOMAIN]["_cards_enabled_unsub"] = hass.bus.async_listen(
        "ramses_extras_feature_ready", _on_feature_ready
    )

    for feature_name in enabled_feature_names:
        if feature_name in features:
            continue
        try:
            feature_module_name = (
                f"custom_components.ramses_extras.features.{feature_name}"
            )
            feature_module = await asyncio.to_thread(
                importlib.import_module, feature_module_name
            )

            create_func_name = f"create_{feature_name.replace('-', '_')}_feature"
            if hasattr(feature_module, create_func_name):
                create_feature_func = getattr(feature_module, create_func_name)

                if asyncio.iscoroutinefunction(create_feature_func):
                    feature_instance = await create_feature_func(hass, entry)
                else:
                    feature_instance = create_feature_func(hass, entry)

                automation_manager = None
                if isinstance(feature_instance, dict):
                    automation_manager = feature_instance.get("automation")

                if automation_manager:
                    feature_ready.setdefault(feature_name, False)
                    cards_pending_features.add(feature_name)
                    if not automation_manager.is_automation_active():
                        automation_managers_to_start.append(automation_manager)
                else:
                    feature_ready[feature_name] = True
                    hass.bus.async_fire(
                        "ramses_extras_feature_ready", {"feature_id": feature_name}
                    )

                features[feature_name] = feature_instance
                _LOGGER.info("Created feature instance: %s", feature_name)
        except Exception as e:
            _LOGGER.warning(
                "Failed to create feature instance '%s': %s", feature_name, e
            )

    if not cards_pending_features:
        hass.data[DOMAIN]["cards_enabled"] = True
        _LOGGER.debug("Cards latch: cards_enabled=True (no pending automations)")
        hass.bus.async_fire("ramses_extras_cards_enabled", {})

    for automation_manager in automation_managers_to_start:
        hass.async_create_task(automation_manager.start())
