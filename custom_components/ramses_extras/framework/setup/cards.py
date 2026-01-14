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


async def discover_card_features() -> list[dict[str, Any]]:
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
    root_dir = Path(hass.config.config_dir) / "www" / "ramses_extras"
    if not root_dir.exists():
        return

    current_dirname = f"v{current_version}"

    legacy_helpers = root_dir / "helpers"
    legacy_features = root_dir / "features"

    def _do_cleanup() -> None:
        legacy_helpers.mkdir(parents=True, exist_ok=True)
        legacy_features.mkdir(parents=True, exist_ok=True)

        stable_shim_content = (
            f'import "/local/ramses_extras/v{current_version}/helpers/'
            'ramses-extras-features.js";\n'
            f'import "/local/ramses_extras/v{current_version}/helpers/main.js";\n'
        )

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

        discovered_tags: set[str] = set()
        for feature in card_features:
            for js_file in feature["js_files"]:
                if js_file.endswith(".js") and not js_file.endswith("-editor.js"):
                    tag = js_file.replace(".js", "")
                    discovered_tags.add(tag)

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

            _LOGGER.debug("Poisoning old version deployment: %s", entry.name)
            try:
                for sub_file in entry.rglob("*.js"):
                    sub_file.write_text(tombstone_content)
            except Exception as e:
                _LOGGER.warning("Failed to poison old version %s: %s", entry.name, e)

    await asyncio.to_thread(_do_cleanup)


async def copy_all_card_files(
    hass: HomeAssistant, card_features: list[dict[str, Any]]
) -> None:
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
    try:
        _LOGGER.info("Starting helper files copy process...")

        version = await async_get_integration_version(hass)

        source_helpers_dir = INTEGRATION_DIR / "framework" / "www"
        destination_helpers_dir = DEPLOYMENT_PATHS.get_destination_helpers_path(
            hass.config.config_dir,
            version,
        )

        _LOGGER.info("Source helpers directory: %s", source_helpers_dir)
        _LOGGER.info("Destination helpers directory: %s", destination_helpers_dir)
        _LOGGER.info("Source directory exists: %s", source_helpers_dir.exists())

        if not source_helpers_dir.exists():
            _LOGGER.warning("Helper files directory not found: %s", source_helpers_dir)
            return

        destination_helpers_dir.mkdir(parents=True, exist_ok=True)
        _LOGGER.info("Created directory: %s", destination_helpers_dir)

        await asyncio.to_thread(
            shutil.copytree,
            source_helpers_dir,
            destination_helpers_dir,
            dirs_exist_ok=True,
        )
        _LOGGER.info("Helper files copied successfully")

    except Exception as e:
        _LOGGER.error("Failed to copy helper files: %s", e)
        import traceback

        _LOGGER.debug("Full traceback: %s", traceback.format_exc())


async def register_cards(hass: HomeAssistant) -> None:
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
