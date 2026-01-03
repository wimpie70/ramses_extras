"""Integration to provide additional entities and automations for Ramses RF/Hive
systems."""

from __future__ import annotations

import asyncio
import importlib
import logging
import shutil
from pathlib import Path
from typing import Any, cast

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED, Platform
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.typing import ConfigType
from homeassistant.loader import async_get_integration

from .const import (
    AVAILABLE_FEATURES,
    CARD_FOLDER,
    DOMAIN,
    EVENT_DEVICES_UPDATED,
    PLATFORM_REGISTRY,
    register_feature_platform,
)

# Import CardRegistry for simplified card registration
from .framework.helpers.card_registry import CardRegistry
from .framework.helpers.paths import DEPLOYMENT_PATHS, PathConstants

# Since this integration can only be set up from config entries,
# use the config_entry_only_config_schema to avoid the warning
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

_LOGGER = logging.getLogger(__name__)

INTEGRATION_DIR = Path(__file__).parent
_setup_in_progress = False


async def _async_get_integration_version(hass: HomeAssistant) -> str:
    data = hass.data.setdefault(DOMAIN, {})
    cached_version = data.get("_integration_version")
    if isinstance(cached_version, str) and cached_version:
        return cached_version

    try:
        integration = await async_get_integration(hass, DOMAIN)
        version = integration.manifest.get("version")
        if isinstance(version, str) and version:
            data["_integration_version"] = version
            return version
    except Exception:
        pass

    data["_integration_version"] = "0.0.0"
    return "0.0.0"


async def _discover_card_features() -> list[dict[str, Any]]:
    """Discover all features that contain card assets."""
    features_dir = INTEGRATION_DIR / "features"
    card_features = []

    if not features_dir.exists():
        return []

    def _do_discovery() -> None:
        for feature_path in features_dir.iterdir():
            if not feature_path.is_dir():
                continue

            www_dir = feature_path / "www" / feature_path.name
            if not www_dir.exists():
                continue

            # Find .js files that are likely cards or editors
            js_files = list(www_dir.glob("*.js"))
            if not js_files:
                continue

            card_features.append(
                {
                    "feature_name": feature_path.name,
                    "source_dir": www_dir,
                    "js_files": [f.name for f in js_files],
                }
            )

    await asyncio.to_thread(_do_discovery)
    return card_features


async def _cleanup_old_card_deployments(
    hass: HomeAssistant,
    current_version: str,
    card_features: list[dict[str, Any]],
) -> None:
    root_dir = Path(hass.config.config_dir) / "www" / "ramses_extras"
    if not root_dir.exists():
        return

    current_dirname = f"v{current_version}"

    legacy_helpers = root_dir / "helpers"
    legacy_features = root_dir / "features"

    def _do_cleanup() -> None:
        legacy_helpers.mkdir(parents=True, exist_ok=True)
        legacy_features.mkdir(parents=True, exist_ok=True)

        # Stable shim redirects to current version
        stable_shim_content = (
            f'import "/local/ramses_extras/v{current_version}/helpers/main.js";\n'
        )

        # Tombstone template for old versions to catch 404s and show a warning
        tombstone_template = """
/*
 * Ramses Extras - Restart Required
 * This version of the integration has been upgraded.
 * Please restart Home Assistant to use the new version.
 */
(function() {
    const warning = "Ramses Extras: Upgrade detected. " +
                    "A Home Assistant restart is required.";
    console["warn"](
        "%c Ramses Extras %c " + warning,
        "background: #df4b37; color: #fff; padding: 2px 4px; " +
        "border-radius: 3px; font-weight: bold;",
        "color: #df4b37; font-weight: bold;"
    );

    // Define a dummy card to show the warning in the UI
    class RestartRequiredCard extends HTMLElement {
        setConfig(config) { this._config = config; }
        set hass(hass) {
            if (!this.content) {
                this.innerHTML = `
                    <ha-card header="Ramses Extras - Restart Required">
                        <div class="card-content" style="color: #df4b37; ` +
                        `font-weight: bold; padding: 16px;">
                            ${warning}<br><br>
                            Please restart Home Assistant to complete the upgrade.
                        </div>
                    </ha-card>
                `;
                this.content = true;
            }
        }
        getCardSize() { return 2; }
    }

    // Register discovered tags as restart-required cards
    const tags = TAGS_PLACEHOLDER;
    tags.forEach(tag => {
        if (!customElements.get(tag)) {
            customElements.define(tag, RestartRequiredCard);
        }
    });
})();
"""

        legacy_shims: list[Path] = [
            legacy_helpers / "main.js",
        ]

        # Collect tags for the tombstone JS from discovered card files
        discovered_tags = set()
        for feature in card_features:
            for js_file in feature["js_files"]:
                # Only include the main card file as a tag, not the editor
                if js_file.endswith(".js") and not js_file.endswith("-editor.js"):
                    tag = js_file.replace(".js", "")
                    discovered_tags.add(tag)

        # Update tombstone content with dynamic tags
        tags_js = str(list(discovered_tags))
        tombstone_content = tombstone_template.replace("TAGS_PLACEHOLDER", tags_js)

        for feature in card_features:
            feature_name = feature["feature_name"]
            for js_file in feature["js_files"]:
                legacy_shims.append(legacy_features / feature_name / js_file)

        for shim_path in legacy_shims:
            shim_path.parent.mkdir(parents=True, exist_ok=True)
            shim_path.write_text(stable_shim_content)

        for entry in root_dir.iterdir():
            if not entry.is_dir():
                continue
            if not entry.name.startswith("v"):
                continue
            if entry.name == current_dirname:
                continue

            # Instead of deleting immediately, we "poison" old version files
            # with tombstone warnings to help users realize a restart is needed
            # if their browser is still trying to load the old version paths.
            _LOGGER.debug("Poisoning old version deployment: %s", entry.name)
            try:
                for sub_file in entry.rglob("*.js"):
                    sub_file.write_text(tombstone_content)
            except Exception as e:
                _LOGGER.warning("Failed to poison old version %s: %s", entry.name, e)

            # Optional: We could still delete after some time, but for now we just
            # keep them as tombstones.
            # shutil.rmtree(entry, ignore_errors=True)

    await asyncio.to_thread(_do_cleanup)


async def _import_module_in_executor(module_path: str) -> Any:
    """Import module in executor to avoid blocking event loop."""
    import asyncio

    def _do_import() -> Any:
        return importlib.import_module(module_path)

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _do_import)


async def _import_feature_platform_modules(feature_names: list[str]) -> None:
    """Import per-feature platform modules so they can register into
    `PLATFORM_REGISTRY`.

    The feature platform modules register themselves via
    :func:`custom_components.ramses_extras.const.register_feature_platform` at
    import time. The root HA platforms (e.g.
    :mod:`custom_components.ramses_extras.sensor`) depend on these registrations.

    Features are allowed to omit a platform module (e.g. no `number` platform).
    Missing modules are treated as normal and ignored.

    :param feature_names: Feature IDs to import platforms for.
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


async def _handle_startup_event(
    event: Event, hass: HomeAssistant, config: ConfigType
) -> None:
    _LOGGER.info("Starting Ramses Extras from YAML configuration")

    await async_setup_yaml_config(hass, config)


# Component will be loaded when hass starts up.
async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up Ramses Extras integration from YAML configuration."""

    # Use module-level function with explicit parameters to avoid closure issues
    # and thread-safe execution using run_coroutine_threadsafe
    def _startup_callback(event: Event) -> None:
        """Thread-safe callback for startup event."""
        import asyncio

        # Use run_coroutine_threadsafe for thread safety
        asyncio.run_coroutine_threadsafe(
            _handle_startup_event(event, hass, config), hass.loop
        )

    hass.bus.async_listen(EVENT_HOMEASSISTANT_STARTED, _startup_callback)

    return True


async def async_setup_yaml_config(hass: HomeAssistant, config: ConfigType) -> None:
    """Set up Ramses Extras from YAML config if present."""

    yaml_config = config.get(DOMAIN, {})
    if not yaml_config:
        return

    try:
        _LOGGER.info("Setting up Ramses Extras from YAML configuration...")

        # Create a config entry from YAML for the integrations to use
        entry_data = {
            "yaml": True,
            "enabled_features": yaml_config.get("enabled_features", {}),
        }

        # Note: This will trigger the normal setup flow
        hass.async_create_task(
            hass.config_entries.flow.async_init(
                DOMAIN,
                context={"source": "yaml"},
                data=entry_data,
            )
        )

    except Exception:
        _LOGGER.exception("Failed to set up Ramses Extras from YAML")


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up entry for Ramses Extras."""
    _LOGGER.info("Starting Ramses Extras integration setup...")

    # Setup from UI (config entry)
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {}
    hass.data[DOMAIN]["entry_id"] = entry.entry_id
    hass.data[DOMAIN]["config_entry"] = entry  # Store for async_setup_platforms access
    hass.data[DOMAIN]["enabled_features"] = entry.data.get("enabled_features", {})
    hass.data[DOMAIN]["PLATFORM_REGISTRY"] = (
        PLATFORM_REGISTRY  # Make registry available to platforms
    )

    device_refresh_task: asyncio.Task[None] | None = None
    device_refresh_lock: asyncio.Lock = hass.data[DOMAIN].setdefault(
        "_devices_refresh_lock",
        asyncio.Lock(),
    )

    async def _refresh_devices_after_delay() -> None:
        try:
            await asyncio.sleep(5)
            async with device_refresh_lock:
                await _discover_and_store_devices(hass)
            async_dispatcher_send(hass, EVENT_DEVICES_UPDATED)
        except asyncio.CancelledError:
            return

    def _schedule_device_refresh() -> None:
        nonlocal device_refresh_task
        if device_refresh_task is not None and not device_refresh_task.done():
            return
        device_refresh_task = hass.async_create_task(_refresh_devices_after_delay())

    @callback  # type: ignore[untyped-decorator]
    def _cancel_device_refresh_task() -> None:
        nonlocal device_refresh_task
        if device_refresh_task is not None and not device_refresh_task.done():
            device_refresh_task.cancel()

    @callback  # type: ignore[untyped-decorator]
    def _on_entity_registry_updated(
        event: Event[er.EventEntityRegistryUpdatedData],
    ) -> None:
        data = event.data
        if data.get("action") != "create":
            return
        entity_id = data.get("entity_id")
        if not isinstance(entity_id, str):
            return

        entity_reg = er.async_get(hass)
        entry = entity_reg.async_get(entity_id)
        if entry is None or getattr(entry, "platform", None) != "ramses_cc":
            return

        _schedule_device_refresh()

    entry.async_on_unload(_cancel_device_refresh_task)

    entry.async_on_unload(
        hass.bus.async_listen(
            er.EVENT_ENTITY_REGISTRY_UPDATED,
            _on_entity_registry_updated,
        )
    )

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    _LOGGER.debug("Enabled features: %s", entry.data.get("enabled_features", {}))

    async def _load_feature_definitions_and_platforms(
        hass: HomeAssistant, entry: ConfigEntry
    ) -> None:
        """Load feature definitions, platforms, and WebSocket modules.

        This is the single authoritative place for loading:
        - Feature definitions (via load_feature)
        - Platform registrations (via async_forward_entry_setups)
        - WebSocket integration (via async_setup_websocket_integration)
        """
        from .extras_registry import extras_registry

        # Load default feature definitions
        from .features.default.commands import register_default_commands

        register_default_commands()

        # Load enabled feature definitions
        enabled_features_dict = entry.data.get("enabled_features", {})
        enabled_feature_names = [
            name for name, enabled in enabled_features_dict.items() if enabled
        ]

        # Always include default
        if "default" not in enabled_feature_names:
            enabled_feature_names.append("default")

        extras_registry.load_all_features(enabled_feature_names)

        await _import_feature_platform_modules(enabled_feature_names)

        # CRITICAL: Discover devices BEFORE setting up platforms
        await _discover_and_store_devices(hass)

        # Forward the setup to the sensor, switch, etc. platforms
        await hass.config_entries.async_forward_entry_setups(
            entry,
            [Platform.SENSOR, Platform.SWITCH, Platform.BINARY_SENSOR, Platform.NUMBER],
        )

        # Register WebSocket commands for features
        await _setup_websocket_integration(hass)

        # Log loaded definitions for verification
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

    await _load_feature_definitions_and_platforms(hass, entry)

    _LOGGER.debug("WebSocket functionality uses feature-centric architecture")

    # Copy helper files, register/clean Lovelace resources, deploy card assets.
    await _setup_card_files_and_config(hass, entry)

    # Register services before setting up platforms
    await _register_services(hass)

    # Continue with additional platform setup if needed
    await async_setup_platforms(hass)

    # STEP: Post-creation validation with SimpleEntityManager
    await _validate_startup_entities_simple(hass, entry)

    # Explicitly create and start feature instances for
    #  enabled features (including default)
    features = hass.data[DOMAIN].setdefault("features", {})
    feature_ready = hass.data[DOMAIN].setdefault("feature_ready", {})
    hass.data[DOMAIN].setdefault("cards_enabled", False)
    hass.data[DOMAIN]["cards_pending_features"] = set()
    enabled_features = entry.data.get("enabled_features") or entry.options.get(
        "enabled_features"
    )
    if not isinstance(enabled_features, dict):
        enabled_features = {}
    enabled_feature_names = [k for k, v in enabled_features.items() if v is True]
    # Always include default
    if "default" not in enabled_feature_names:
        enabled_feature_names.append("default")
    import importlib

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

    existing_unsub = hass.data[DOMAIN].get("_cards_enabled_unsub")
    if callable(existing_unsub):
        existing_unsub()

    hass.data[DOMAIN]["_cards_enabled_unsub"] = hass.bus.async_listen(
        "ramses_extras_feature_ready", _on_feature_ready
    )

    for feature_name in enabled_feature_names:
        if feature_name in features:
            continue  # Already created
        try:
            feature_module_name = (
                f"custom_components.ramses_extras.features.{feature_name}"
            )
            # Run the blocking import operation in a thread pool
            feature_module = await asyncio.to_thread(
                importlib.import_module, feature_module_name
            )
            # Create feature instance if create function exists
            create_func_name = f"create_{feature_name.replace('-', '_')}_feature"
            if hasattr(feature_module, create_func_name):
                create_feature_func = getattr(feature_module, create_func_name)
                # Handle both sync and async create functions

                if asyncio.iscoroutinefunction(create_feature_func):
                    feature_instance = await create_feature_func(hass, entry)
                else:
                    feature_instance = create_feature_func(hass, entry)

                # Start the automation manager if it exists in the feature instance
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

    return True


async def _register_services(hass: HomeAssistant) -> None:
    """Register custom services."""
    _LOGGER.info("Registering Ramses Extras services")

    from .features.default.services import async_setup_services

    await async_setup_services(hass)


async def _setup_websocket_integration(hass: HomeAssistant) -> None:
    """Set up WebSocket integration for Ramses Extras.

    Args:
        hass: Home Assistant instance
    """
    try:
        from .websocket_integration import async_setup_websocket_integration

        success = await async_setup_websocket_integration(hass)
        if success:
            _LOGGER.info("WebSocket integration setup complete")
        else:
            _LOGGER.warning("WebSocket integration setup failed")

    except Exception as error:
        _LOGGER.error("Error setting up WebSocket integration: %s", error)
        # Don't fail the entire integration if WebSocket setup fails


# Legacy functions removed - CardRegistry handles all card registration
# Legacy function removed - CardRegistry handles all card registration


async def _expose_feature_config_to_frontend(
    hass: HomeAssistant, entry: ConfigEntry
) -> None:
    """Expose feature configuration to frontend JavaScript for card feature toggles."""
    try:
        _LOGGER.info("Exposing feature configuration to frontend...")

        # Get enabled features from the entry
        enabled_features = (
            entry.data.get("enabled_features")
            or entry.options.get("enabled_features")
            or {}
        )

        version = await _async_get_integration_version(hass)

        # Use json.dumps to properly convert Python values to JavaScript
        import json

        js_enabled_features = json.dumps(enabled_features, indent=2)

        # Log feature configuration for debugging
        console_log = (
            f"console.log('Ramses Extras features loaded (v{version}):', "
            "window.ramsesExtras.features);"
        )

        js_content = f"""// Ramses Extras Feature Configuration
// Auto-generated during integration setup
window.ramsesExtras = window.ramsesExtras || {{}};
window.ramsesExtras.version = "{version}";
window.ramsesExtras.features = {js_enabled_features};

// Log feature configuration for debugging
{console_log}
"""

        # Write the JavaScript file to the helpers directory
        destination_helpers_dir = DEPLOYMENT_PATHS.get_destination_helpers_path(
            hass.config.config_dir,
            version,
        )
        feature_config_file = destination_helpers_dir / "ramses-extras-features.js"

        # Write the file
        await asyncio.to_thread(feature_config_file.write_text, js_content)

        _LOGGER.info(
            "Feature configuration exposed to frontend: %s", feature_config_file
        )

    except Exception as e:
        _LOGGER.error("Failed to expose feature configuration to frontend: %s", e)
        import traceback

        _LOGGER.debug("Full traceback: %s", traceback.format_exc())


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    try:
        data = hass.data.setdefault(DOMAIN, {})

        old_enabled_features_raw = data.get("enabled_features")
        new_enabled_features_raw = (
            entry.data.get("enabled_features")
            or entry.options.get("enabled_features")
            or {}
        )

        old_enabled_features = (
            old_enabled_features_raw
            if isinstance(old_enabled_features_raw, dict)
            else {}
        )
        new_enabled_features = (
            new_enabled_features_raw
            if isinstance(new_enabled_features_raw, dict)
            else {}
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

        await _expose_feature_config_to_frontend(hass, entry)

        enabled_features_changed = old_enabled_features != new_enabled_features
        matrix_changed = old_matrix_state != new_matrix_state

        if enabled_features_changed or matrix_changed:
            if data.get("_reload_pending") is True:
                return

            data["_reload_pending"] = True

            async def _do_reload() -> None:
                try:
                    await hass.config_entries.async_reload(entry.entry_id)
                finally:
                    hass.data.get(DOMAIN, {}).pop("_reload_pending", None)

            hass.async_create_task(_do_reload())
    except Exception as e:
        _LOGGER.warning("Failed to update frontend feature configuration: %s", e)


async def _copy_all_card_files(
    hass: HomeAssistant, card_features: list[dict[str, Any]]
) -> None:
    """Copy all card files to Home Assistant's www directory regardless
    of feature status."""
    try:
        _LOGGER.info("Starting unconditional card files copy process...")

        version = await _async_get_integration_version(hass)

        for card_feature in card_features:
            feature_name = card_feature["feature_name"]
            source_dir = card_feature["source_dir"]
            destination_dir = DEPLOYMENT_PATHS.get_destination_features_path(
                hass.config.config_dir,
                feature_name,
                version,
            )

            if source_dir.exists():
                destination_dir.mkdir(parents=True, exist_ok=True)

                await asyncio.to_thread(
                    shutil.copytree,
                    source_dir,
                    destination_dir,
                    dirs_exist_ok=True,
                )
                _LOGGER.info("Card file copied: %s -> %s", source_dir, destination_dir)
            else:
                _LOGGER.warning(f"Card source directory not found: {source_dir}")

        _LOGGER.info("All card files copy process complete")

    except Exception as e:
        _LOGGER.error(f"Failed to copy card files: {e}")
        import traceback

        _LOGGER.debug(f"Full traceback: {traceback.format_exc()}")


# Legacy function removed - now handled by CardRegistry


async def _copy_helper_files(hass: HomeAssistant) -> None:
    """Copy helper files to Home Assistant's www directory for card functionality."""
    try:
        _LOGGER.info("Starting helper files copy process...")

        version = await _async_get_integration_version(hass)

        # Source and destination paths
        source_helpers_dir = INTEGRATION_DIR / "framework" / "www"
        destination_helpers_dir = DEPLOYMENT_PATHS.get_destination_helpers_path(
            hass.config.config_dir,
            version,
        )

        _LOGGER.info(f"Source helpers directory: {source_helpers_dir}")
        _LOGGER.info(f"Destination helpers directory: {destination_helpers_dir}")
        _LOGGER.info(f"Source directory exists: {source_helpers_dir.exists()}")

        if not source_helpers_dir.exists():
            _LOGGER.warning(f"Helper files directory not found: {source_helpers_dir}")
            return

        # Create destination directory if it doesn't exist
        destination_helpers_dir.mkdir(parents=True, exist_ok=True)
        _LOGGER.info(f"Created directory: {destination_helpers_dir}")

        # Copy all helper files
        await asyncio.to_thread(
            shutil.copytree,
            source_helpers_dir,
            destination_helpers_dir,
            dirs_exist_ok=True,
        )
        _LOGGER.info("Helper files copied successfully")

    except Exception as e:
        _LOGGER.error(f"Failed to copy helper files: {e}")
        import traceback

        _LOGGER.debug(f"Full traceback: {traceback.format_exc()}")


# Legacy functions removed - CardRegistry handles all card registration


async def _validate_startup_entities_simple(
    hass: HomeAssistant, entry: ConfigEntry
) -> None:
    """Validate startup entity creation and fix discrepancies using SimpleEntityManager.

    This function runs after all platforms have been set up to ensure that
    the actual entities match the expected configuration. It uses SimpleEntityManager
    to detect and fix any discrepancies.

    Args:
        hass: Home Assistant instance
        entry: Configuration entry
    """
    try:
        from custom_components.ramses_extras.framework.helpers.entity.simple_entity_manager import (  # noqa: E501
            SimpleEntityManager,
        )

        # Create SimpleEntityManager for validation
        entity_manager = SimpleEntityManager(hass)

        # Restore matrix state from config entry if available
        matrix_state = entry.data.get("device_feature_matrix", {})
        if matrix_state:
            entity_manager.restore_device_feature_matrix_state(matrix_state)
            _LOGGER.info(f"Restored matrix state with {len(matrix_state)} devices")

        # Validate entities on startup
        await entity_manager.validate_entities_on_startup()

        _LOGGER.info("SimpleEntityManager startup validation completed")

    except Exception as e:
        _LOGGER.error(f"SimpleEntityManager startup validation failed: {e}")
        # Don't fail startup if validation fails - log error and continue
        import traceback

        _LOGGER.debug(f"Full traceback: {traceback.format_exc()}")


async def _discover_and_store_devices(hass: HomeAssistant) -> None:
    """Discover devices and store them in hass.data for platform access.

    We store full device objects so that config flows can use DeviceFilter
    and other helpers that rely on device attributes such as slugs or types.
    """
    devices = await _discover_ramses_devices(hass)

    # Store devices in a location that platforms can access
    data = hass.data.setdefault(DOMAIN, {})
    data["devices"] = devices
    data["device_discovery_complete"] = True

    device_ids = [getattr(device, "id", str(device)) for device in devices]
    _LOGGER.info(
        "Stored %d devices for platform access: %s",
        len(devices),
        device_ids,
    )


async def async_setup_platforms(hass: HomeAssistant) -> None:
    """Enhanced platform setup with reliable device discovery integration."""
    global _setup_in_progress

    # Prevent multiple simultaneous setup attempts
    if _setup_in_progress:
        _LOGGER.debug("Platform setup already in progress, skipping")
        return

    _setup_in_progress = True

    try:
        _LOGGER.info("Platform setup: integrating with device discovery...")

        # Check if ramses_cc is loaded and working
        ramses_cc_loaded = "ramses_cc" in hass.config.components
        _LOGGER.info(f"Ramses CC loaded: {ramses_cc_loaded}")

        if ramses_cc_loaded:
            _LOGGER.debug("Ramses CC is loaded, verifying device discovery...")

            # Check if device discovery was already completed
            device_data = hass.data.setdefault(DOMAIN, {})
            if "devices" in device_data and "device_discovery_complete" in device_data:
                _LOGGER.debug(
                    "Device discovery already completed, using cached results"
                )
                devices = device_data["devices"]
                device_ids = [getattr(device, "id", str(device)) for device in devices]
                _LOGGER.debug("Using cached device IDs: %s", device_ids)
            else:
                # Re-discover devices and update storage
                devices = await _discover_ramses_devices(hass)
                device_ids = [getattr(device, "id", str(device)) for device in devices]
                device_data["devices"] = devices
                device_data["device_discovery_complete"] = True
                _LOGGER.debug("Fresh discovery device IDs: %s", device_ids)

            if devices:
                _LOGGER.info(
                    "Platform setup: Found %d Ramses devices: %s",
                    len(devices),
                    device_ids,
                )
            else:
                _LOGGER.info("Platform setup: No Ramses devices found via any method")

            return
        _LOGGER.info("Ramses CC not loaded yet, will retry in 60 seconds.")

        # Schedule a retry in 60 seconds - only if ramses_cc not loaded
        if "ramses_cc" not in hass.config.components:

            async def delayed_retry() -> None:
                global _setup_in_progress
                _setup_in_progress = False
                await async_setup_platforms(hass)

            # Use async_call_later
            async_call_later(hass, 60.0, delayed_retry)

    except Exception as e:
        _LOGGER.error(f"Error in platform setup: {e}")
    finally:
        # Reset setup flag
        _setup_in_progress = False


async def _discover_ramses_devices(hass: HomeAssistant) -> list[Any]:
    """Discover Ramses devices from ramses_cc integration with improved reliability.

    This function leverages ramses_cc to discover devices by looking for
    ramses_cc entities in the entity registry with multiple fallback methods.
    """

    # Access the broker from the ramses_cc integration
    ramses_cc_entries = hass.config_entries.async_entries("ramses_cc")
    if not ramses_cc_entries:
        _LOGGER.warning("No ramses_cc entries found")
        return await _discover_devices_from_entity_registry(hass)

    # Use the first ramses_cc entry
    entry = ramses_cc_entries[0]

    try:
        # Method 1: Try to get broker from hass.data (most reliable)
        broker = None
        if "ramses_cc" in hass.data and entry.entry_id in hass.data["ramses_cc"]:
            broker_data = hass.data["ramses_cc"][entry.entry_id]
            # The broker is stored directly, not nested under a "broker" key
            if (
                hasattr(broker_data, "__class__")
                and "Broker" in broker_data.__class__.__name__
            ):
                broker = broker_data
            elif isinstance(broker_data, dict) and "broker" in broker_data:
                broker = broker_data["broker"]
            elif not isinstance(broker_data, dict) and hasattr(broker_data, "broker"):
                broker = broker_data.broker
            else:
                # Direct assignment if broker is stored directly
                broker = broker_data
            _LOGGER.debug(f"Found broker via hass.data method: {broker}")

        # Method 2: If not found, try getting broker from the entry
        if broker is None and hasattr(entry, "broker"):
            broker = entry.broker
            _LOGGER.debug(f"Found broker via entry method: {broker}")

        # Method 3: Try to access through the integration registry
        if broker is None:
            # Look for ramses_cc integration instance in integration registry
            for integration in hass.data.get("integrations", {}).values():
                if hasattr(integration, "broker") and integration.broker:
                    broker = integration.broker
                    _LOGGER.debug(f"Found broker via integration registry: {broker}")
                    break

        # Method 4: Direct import and access (new fallback)
        if broker is None:
            try:
                from ramses_cc.gateway import Gateway

                # Try to find gateway through Home Assistant's component registry
                gateway_entries = [
                    e for e in ramses_cc_entries if hasattr(e, "gateway")
                ]
                if gateway_entries:
                    broker = gateway_entries[0].gateway
                    _LOGGER.debug(f"Found broker via direct gateway access: {broker}")
            except ImportError:
                _LOGGER.debug("ramses_cc module not available for direct access")

        if broker is None:
            _LOGGER.warning("Could not find ramses_cc broker via any method")
            # Fallback: try to find devices from entity registry
            return await _discover_devices_from_entity_registry(hass)

        # Get devices from the broker with robust access
        # The broker stores devices as _devices (list), not devices (dict)
        devices = getattr(broker, "_devices", None)
        if devices is None:
            # Try alternative attribute names
            devices = getattr(broker, "devices", None)

        if not devices:
            _LOGGER.debug("No devices found in broker, using entity registry fallback")
            return await _discover_devices_from_entity_registry(hass)

        # Normalize to a plain list of device objects
        if isinstance(devices, dict):
            devices_list = list(devices.values())
        elif isinstance(devices, (list, set, tuple)):
            devices_list = list(devices)
        else:
            devices_list = [devices]

        # Log summary of discovered devices by ID for debugging
        device_ids = [getattr(device, "id", str(device)) for device in devices_list]
        _LOGGER.info(
            "Found %d devices from broker for config flows: %s",
            len(devices_list),
            device_ids,
        )

        # Return full device objects so downstream code can filter by slugs/types
        return devices_list

    except Exception as e:
        _LOGGER.error(f"Error accessing ramses_cc broker: {e}")
        import traceback

        _LOGGER.debug(f"Full traceback: {traceback.format_exc()}")
        # Fallback to entity registry discovery
        return await _discover_devices_from_entity_registry(hass)


async def _discover_devices_from_entity_registry(hass: HomeAssistant) -> list[str]:
    """Fallback method to discover devices from entity registry with comprehensive
    device support."""
    try:
        from homeassistant.helpers.entity_registry import async_get

        entity_registry = async_get(hass)
        device_ids = []

        # Look for ramses_cc entities across multiple domains
        relevant_domains = [
            "fan",
            "climate",
            "sensor",
            "switch",
            "number",
            "binary_sensor",
        ]

        for entity in entity_registry.entities.values():
            if (
                entity.domain in relevant_domains
                and entity.platform == "ramses_cc"
                and hasattr(entity, "device_id")
            ):
                device_id = entity.device_id
                if device_id and device_id not in device_ids:
                    device_ids.append(device_id)

        _LOGGER.info(
            f"Found {len(device_ids)} devices via entity registry fallback: "
            f"{device_ids}"
        )
        return device_ids

    except Exception as e:
        _LOGGER.error(f"Error discovering devices from entity registry: {e}")
        return []


async def _register_cards(hass: HomeAssistant) -> None:
    """Register all cards using feature-centric CardRegistry.

    This uses the new feature-centric CardRegistry that follows HA standards:
    - Uses standard lovelace_resources storage key
    - Discovers cards from feature const.py files dynamically
    - Maintains feature-centric architecture
    - Simple, reliable implementation
    """
    try:
        _LOGGER.info("Starting feature-centric CardRegistry registration")

        version = await _async_get_integration_version(hass)

        # Create CardRegistry and register bootstrap resource
        registry = CardRegistry(hass)
        await registry.register_bootstrap(version)

        _LOGGER.info("Feature-centric CardRegistry registration complete")

    except Exception as e:
        _LOGGER.error(f"CardRegistry registration failed: {e}")
        # Don't raise - let the integration continue without card registration
        # This ensures that card registration issues don't break the entire startup
        _LOGGER.warning("Continuing integration startup without card registration")


async def _setup_card_files_and_config(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Setup card files and expose feature configuration to frontend.

    This handles the file copying and config exposure that cards need for functionality.
    """
    try:
        _LOGGER.info("Setting up card files and configuration")

        # Discover all features with card assets once
        card_features = await _discover_card_features()

        # Always copy helper files first so the bootstrap module exists.
        await _copy_helper_files(hass)

        # Register bootstrap resource and clean up legacy resources before removing
        # any old deployed files.
        await _register_cards(hass)

        # Keep only the current versioned deployment dir.
        version = await _async_get_integration_version(hass)
        await _cleanup_old_card_deployments(hass, version, card_features)

        # Always copy all card files regardless of feature status
        await _copy_all_card_files(hass, card_features)

        # Expose feature configuration to frontend for card feature toggles
        await _expose_feature_config_to_frontend(hass, entry)

        _LOGGER.info("Card files and configuration setup complete")

    except Exception as e:
        _LOGGER.error(f"Card files and config setup failed: {e}")
        raise


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.info("Unloading Ramses Extras integration...")

    # Forward the unload to our platforms
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
        # Clean up stored data (single-instance integration)
        hass.data.pop(DOMAIN, None)

    return bool(unload_ok)


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Remove a config entry.

    For this single-instance integration, ensure we don't leave orphaned entity
    registry entries behind when the user removes the integration.
    """

    # Remove entities
    entity_registry = er.async_get(hass)
    entity_entries = list(entity_registry.entities.values())
    for entity_entry in entity_entries:
        if entity_entry.platform != DOMAIN:
            continue
        entity_registry.async_remove(entity_entry.entity_id)

    # Remove devices created by ramses_extras (but not ramses_cc devices)
    device_registry = dr.async_get(hass)
    device_entries = list(device_registry.devices.values())
    for device_entry in device_entries:
        # Only remove devices that were created by ramses_extras
        # Check if the device has our integration as a config entry
        if entry.id in device_entry.config_entries:
            device_registry.async_remove_device(device_entry.id)


async def _cleanup_orphaned_devices(
    hass: HomeAssistant,
    entry: ConfigEntry,
    device_registry: Any | None = None,
    entity_registry: Any | None = None,
) -> None:
    """Clean up orphaned devices.

    Simple logic: if a device has no entities, it's orphaned and should be removed.
    """
    from homeassistant.helpers import device_registry as dr
    from homeassistant.helpers import entity_registry as er

    device_registry = cast(Any, device_registry or dr.async_get(hass))
    entity_registry = cast(Any, entity_registry or er.async_get(hass))

    if device_registry is None:
        _LOGGER.warning("Device registry unavailable, skipping cleanup")
        return

    if entity_registry is None:
        _LOGGER.warning("Entity registry unavailable, skipping cleanup")
        return

    # Get all devices that belong to ramses_extras
    ramses_devices = []
    for device_entry in device_registry.devices.values():
        if any(identifier[0] == DOMAIN for identifier in device_entry.identifiers):
            ramses_devices.append(device_entry)

    # Find orphaned devices: devices that have no entities
    orphaned_devices = []
    for device_entry in ramses_devices:
        # Check if this device has any entities
        entities = entity_registry.entities.get(device_entry.id, [])
        if not entities:
            # No entities found - this device is orphaned
            device_id = list(device_entry.identifiers)[0][1]  # Extract device ID
            orphaned_devices.append((device_id, device_entry))
            _LOGGER.info(f"Found orphaned device: {device_id} (no entities)")

    if not orphaned_devices:
        _LOGGER.debug("No orphaned devices found")
        return

    _LOGGER.info(f"Removing {len(orphaned_devices)} orphaned devices")

    # Remove orphaned devices
    for device_id, device_entry in orphaned_devices:
        try:
            if entry.entry_id in device_entry.config_entries:
                device_registry.async_remove_device(device_entry.id)
                _LOGGER.info(f"Removed orphaned device: {device_id}")
            else:
                _LOGGER.debug(
                    f"Device {device_id} not owned by ramses_extras, skipping"
                )
        except Exception as e:
            _LOGGER.warning(f"Failed to remove device {device_id}: {e}")
