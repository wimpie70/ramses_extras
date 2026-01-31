"""Card setup and deployment for Ramses Extras Lovelace cards.

This module provides functionality for discovering, copying, registering,
and managing Lovelace custom cards for Ramses Extras features.

Card Management Flow (Called from entry.py):
These functions are called from run_entry_setup_pipeline() and
async_update_listener() in entry.py:

1. setup_card_files_and_config (called in run_entry_setup_pipeline step 2):
   - Orchestrates the complete card setup process
   - Discovers card features from feature directories
   - Copies helper files to versioned deployment directory
   - Registers cards with Home Assistant's Lovelace system
   - Cleans up old card deployments and creates stable shims
   - Copies all card files to versioned deployment directories
   - Exposes feature configuration to frontend

2. expose_feature_config_to_frontend (called in async_update_listener):
   - Updates frontend configuration when config entry changes
   - Creates JavaScript file with feature configuration and debug settings
   - Provides version information to Lovelace cards
   - Ensures frontend stays in sync with backend configuration

Pipeline Context:
In run_entry_setup_pipeline():
- load_feature_definitions_and_platforms (step 1)
- setup_card_files_and_config (step 2)
- register_services (step 3)
- async_setup_platforms (step 4)
- validate_startup_entities_simple (step 5)
- cleanup_orphaned_devices (step 6)
- create_and_start_feature_instances (step 7)

In async_update_listener():
- Called after configuration changes
- Updates frontend configuration to match new settings

Card Deployment Strategy:
1. Version-based deployment: Each integration version gets its own www directory
2. Stable shims: Create redirect files for backward compatibility
3. Helper files: Shared JavaScript utilities copied to helpers directory
4. Feature cards: Individual card files copied to feature-specific paths
5. Configuration exposure: Feature settings exposed via JavaScript

Card Discovery Process:
1. Scan features directory for subdirectories with www folders
2. Look for JavaScript files (.js) in those www directories
3. Create feature information dictionaries with paths and metadata
4. Filter for valid card features only

Key Functions:
- async_get_integration_version: Version management with caching
- discover_card_features: Feature discovery and validation
- cleanup_old_card_deployments: Version cleanup and shims
- copy_all_card_files: Card file deployment
- copy_helper_files: Shared utilities deployment
- register_cards: Home Assistant Lovelace registration
- expose_feature_config_to_frontend: Configuration synchronization
- setup_card_files_and_config: Complete setup orchestration
"""

from __future__ import annotations

import asyncio
import logging
import shutil
from pathlib import Path
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.loader import async_get_integration

from ...const import DOMAIN
from ...feature_utils import get_enabled_features_dict
from ..helpers.card_registry import CardRegistry
from ..helpers.paths import DEPLOYMENT_PATHS

_LOGGER = logging.getLogger(__name__)

INTEGRATION_DIR = Path(__file__).resolve().parents[2]


async def async_get_integration_version(hass: HomeAssistant) -> str:
    """Get the integration version with caching.

    :param hass: Home Assistant instance

    :return: Integration version string (e.g., "0.12.0")
    """
    data = hass.data.setdefault(DOMAIN, {})
    cached_version = data.get("_integration_version")
    if isinstance(cached_version, str) and cached_version and cached_version != "0.0.0":
        return cached_version

    try:
        integration = await async_get_integration(hass, DOMAIN)
        version = integration.manifest.get("version")
        if isinstance(version, str) and version:
            data["_integration_version"] = version
            return version
    except Exception:
        pass

    # Only set to 0.0.0 if we don't have a cached version
    # This prevents version reset during integration reloads
    if not cached_version:
        data["_integration_version"] = "0.0.0"
    return cached_version or "0.0.0"


async def discover_card_features() -> list[dict[str, Any]]:
    """Discover features that have Lovelace cards.

    Scans the features directory for subdirectories containing www folders
    with JavaScript files for Lovelace cards.

    :return: List of dictionaries containing feature information and file paths
    """
    features_dir = INTEGRATION_DIR / "features"
    card_features: list[dict[str, Any]] = []

    if not features_dir.exists():
        return []

    def _do_discovery() -> None:
        for feature_path in features_dir.iterdir():
            if not feature_path.is_dir():
                continue

            www_dir = feature_path / "www" / feature_path.name
            if not www_dir.exists():
                continue

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


async def cleanup_old_card_deployments(
    hass: HomeAssistant,
    current_version: str,
    card_features: list[dict[str, Any]],
) -> None:
    """Clean up old versioned card deployments.

    Removes all old versioned directories (v0.x.x format) since we now use
    a stable deployment path without version directories.

    :param hass: Home Assistant instance
    :param current_version: Current integration version (kept for compatibility)
    :param card_features: List of discovered card features
    """
    root_dir = Path(hass.config.config_dir) / "www" / "ramses_extras"
    if not root_dir.exists():
        return

    def _do_cleanup() -> None:
        # Remove all old versioned directories (v0.x.x format)
        for entry in root_dir.iterdir():
            if not entry.is_dir():
                continue
            if entry.name.startswith("v") and entry.name[1:2].isdigit():
                _LOGGER.info(f"Removing old versioned deployment: {entry.name}")
                shutil.rmtree(entry, ignore_errors=True)

    await asyncio.to_thread(_do_cleanup)


async def copy_all_card_files(
    hass: HomeAssistant, card_features: list[dict[str, Any]]
) -> None:
    """Copy all card files to stable deployment directory.

    Copies JavaScript files for all discovered card features to the
    stable www directory structure.

    :param hass: Home Assistant instance
    :param card_features: List of discovered card features
    """
    try:
        _LOGGER.info("Starting unconditional card files copy process...")

        version = await async_get_integration_version(hass)

        for card_feature in card_features:
            feature_name = card_feature["feature_name"]
            source_dir: Path = card_feature["source_dir"]
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
                _LOGGER.warning("Card source directory not found: %s", source_dir)

        _LOGGER.info("All card files copy process complete")

    except Exception as e:
        _LOGGER.error("Failed to copy card files: %s", e)
        import traceback

        _LOGGER.debug("Full traceback: %s", traceback.format_exc())


async def copy_helper_files(hass: HomeAssistant) -> None:
    """Copy helper files to the stable deployment directory.

    Copies shared helper JavaScript files that are used by all cards
    to the stable helpers directory.

    :param hass: Home Assistant instance
    """
    try:
        _LOGGER.info("Starting helper files copy process...")

        version = await async_get_integration_version(hass)

        source_www_dir = INTEGRATION_DIR / "framework" / "www"
        destination_helpers_dir = DEPLOYMENT_PATHS.get_destination_helpers_path(
            hass.config.config_dir,
            version,
        )

        _LOGGER.info("Source www directory: %s", source_www_dir)
        _LOGGER.info("Destination helpers directory: %s", destination_helpers_dir)
        _LOGGER.info("Source directory exists: %s", source_www_dir.exists())

        if not source_www_dir.exists():
            _LOGGER.warning("Helper files directory not found: %s", source_www_dir)
            return

        destination_helpers_dir.mkdir(parents=True, exist_ok=True)
        _LOGGER.info("Created directory: %s", destination_helpers_dir)

        # Copy all .js files from www root to helpers directory
        for js_file in source_www_dir.glob("*.js"):
            dest_file = destination_helpers_dir / js_file.name
            await asyncio.to_thread(shutil.copy2, js_file, dest_file)
            _LOGGER.debug("Copied %s to %s", js_file.name, dest_file)

        # Copy helpers subdirectory if it exists
        source_helpers_subdir = source_www_dir / "helpers"
        if source_helpers_subdir.exists():
            dest_helpers_subdir = destination_helpers_dir / "helpers"
            await asyncio.to_thread(
                shutil.copytree,
                source_helpers_subdir,
                dest_helpers_subdir,
                dirs_exist_ok=True,
            )
            _LOGGER.debug("Copied helpers subdirectory")

        _LOGGER.info("Helper files copied successfully")

    except Exception as e:
        _LOGGER.error("Failed to copy helper files: %s", e)
        import traceback

        _LOGGER.debug("Full traceback: %s", traceback.format_exc())


async def register_cards(hass: HomeAssistant) -> None:
    """Register cards with Home Assistant's Lovelace system.

    Uses the CardRegistry to register the bootstrap resource that
    enables dynamic card loading.

    :param hass: Home Assistant instance
    """
    try:
        _LOGGER.info("Starting feature-centric CardRegistry registration")

        version = await async_get_integration_version(hass)

        registry = CardRegistry(hass)
        await registry.register_bootstrap(version)

        _LOGGER.info("Feature-centric CardRegistry registration complete")

    except Exception as e:
        _LOGGER.error("CardRegistry registration failed: %s", e)
        _LOGGER.warning("Continuing integration startup without card registration")


async def expose_feature_config_to_frontend(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> None:
    """Expose feature configuration to the frontend.

    Creates a JavaScript file with feature configuration, debug settings,
    and version information that can be accessed by Lovelace cards.

    :param hass: Home Assistant instance
    :param entry: Configuration entry
    """
    try:
        _LOGGER.info("Exposing feature configuration to frontend...")

        enabled_features = get_enabled_features_dict(
            hass,
            entry,
            include_default=False,
            prefer_hass_data=False,
        )

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

        version = await async_get_integration_version(hass)

        import json

        js_enabled_features = json.dumps(enabled_features, indent=2)
        js_debug_mode = json.dumps(debug_mode)
        js_log_level = json.dumps(log_level)
        js_frontend_log_level = json.dumps(frontend_log_level)

        options_payload: dict[str, Any] = {}
        default_poll_ms = entry.options.get("ramses_debugger_default_poll_ms")
        if isinstance(default_poll_ms, int):
            options_payload["ramses_debugger_default_poll_ms"] = int(default_poll_ms)
        js_options = json.dumps(options_payload, indent=2)

        console_log = (
            f"if (window.ramsesExtras.debug === true) "
            f"console.log('Ramses Extras features loaded (v{version}):', "
            "window.ramsesExtras.features);"
        )

        js_content = f"""// Ramses Extras Feature Configuration
// Auto-generated during integration setup
window.ramsesExtras = window.ramsesExtras || {{}};
window.ramsesExtras.version = \"{version}\";
window.ramsesExtras.features = {js_enabled_features};
window.ramsesExtras.debug = {js_debug_mode};
window.ramsesExtras.frontendLogLevel = {js_frontend_log_level};
window.ramsesExtras.logLevel = {js_log_level};
window.ramsesExtras.options = {js_options};

// Log feature configuration for debugging
{console_log}
"""

        destination_helpers_dir = DEPLOYMENT_PATHS.get_destination_helpers_path(
            hass.config.config_dir,
            version,
        )
        feature_config_file = destination_helpers_dir / "ramses-extras-features.js"

        await asyncio.to_thread(feature_config_file.write_text, js_content)

        _LOGGER.info(
            "Feature configuration exposed to frontend: %s", feature_config_file
        )

    except Exception as e:
        _LOGGER.error("Failed to expose feature configuration to frontend: %s", e)
        import traceback

        _LOGGER.debug("Full traceback: %s", traceback.format_exc())


async def setup_card_files_and_config(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Set up all card files and configuration.

    Orchestrates the complete card setup process:
    1. Discover card features
    2. Copy helper files
    3. Register cards
    4. Clean up old deployments
    5. Copy card files
    6. Expose configuration to frontend

    :param hass: Home Assistant instance
    :param entry: Configuration entry

    :raises Exception: If card setup fails
    """
    try:
        _LOGGER.info("Setting up card files and configuration")

        card_features = await discover_card_features()

        await copy_helper_files(hass)

        await register_cards(hass)

        version = await async_get_integration_version(hass)
        await cleanup_old_card_deployments(hass, version, card_features)

        await copy_all_card_files(hass, card_features)

        await expose_feature_config_to_frontend(hass, entry)

        _LOGGER.info("Card files and configuration setup complete")

    except Exception as e:
        _LOGGER.error("Card files and config setup failed: %s", e)
        raise
