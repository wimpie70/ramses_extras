import json
import logging
import shutil
from pathlib import Path
from typing import TYPE_CHECKING, Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers import selector

from .const import (
    AVAILABLE_FEATURES,
    CARD_FOLDER,
    CONF_ENABLED_FEATURES,
    CONF_NAME,
    DOMAIN,
    GITHUB_WIKI_URL,
    INTEGRATION_DIR,
)
from .framework.helpers.config_flow import ConfigFlowHelper
from .framework.helpers.device.filter import DeviceFilter
from .framework.helpers.entity.manager import EntityManager
from .framework.helpers.platform import (
    calculate_required_entities,
    get_enabled_features,
)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)


def _get_feature_details_from_module(feature_key: str) -> dict[str, Any]:
    """Get feature details from AVAILABLE_FEATURES.

    Args:
        feature_key: Feature identifier

    Returns:
        Dictionary with feature details or empty dict if not found
    """
    feature_config = AVAILABLE_FEATURES.get(feature_key, {})
    if not feature_config:
        return {}

    # Extract supported device types from feature configuration
    supported_device_types = feature_config.get("supported_device_types", [])
    if not supported_device_types:
        # Default to HvacVentilator for most features
        supported_device_types = ["HvacVentilator"]

    # For now, return minimal details since entity loading is handled elsewhere
    return {
        "supported_device_types": supported_device_types,
        "required_entities": {},  # Will be populated by entity manager
    }


async def _manage_cards_config_flow(
    hass: "HomeAssistant", enabled_features: dict[str, bool]
) -> None:
    """Install or remove custom cards based on enabled features (for config flow)."""
    # Use the new /local/ramses_extras path structure instead of www/community
    www_local_path = Path(hass.config.path("local")) / "ramses_extras"

    # Handle all card features dynamically
    for feature_key, feature_config in AVAILABLE_FEATURES.items():
        # Skip default feature from card management (it's not a card feature)
        if feature_key == "default":
            continue

        # Get card info from the registry
        from .extras_registry import extras_registry

        card_info = extras_registry.get_card_config(feature_key) or {}

        # Use the location from the card_info or feature key
        card_source_path = (
            INTEGRATION_DIR / CARD_FOLDER / card_info.get("location", feature_key)
        )
        card_dest_path = www_local_path / "features" / feature_key

        if enabled_features.get(feature_key, False):
            if card_source_path.exists():
                # For automatic registration, we don't need to copy files anymore
                # The card is registered as a static resource in async_setup_entry
                _LOGGER.info(f"Card {feature_key} is automatically registered")
            else:
                _LOGGER.warning(
                    f"Cannot register {feature_key}: {card_source_path} not found"
                )
        else:
            # Remove card from community folder if it exists
            await _remove_card_config_flow(hass, card_dest_path)


async def _install_card_config_flow(
    hass: "HomeAssistant", source_path: Path, dest_path: Path
) -> None:
    """Install a custom card by copying files (for config flow)."""
    try:
        if source_path.exists():
            # Create destination directory if it doesn't exist
            dest_path.mkdir(parents=True, exist_ok=True)

            # Copy all files from source to destination using executor
            await hass.async_add_executor_job(
                _copy_card_files_config_flow, source_path, dest_path
            )

            _LOGGER.info(f"Successfully installed card to {dest_path}")
        else:
            _LOGGER.warning(f"Card source path does not exist: {source_path}")
    except Exception as e:
        _LOGGER.error(f"Failed to install card: {e}")


def _copy_card_files_config_flow(source_path: Path, dest_path: Path) -> None:
    """Copy card files from source to destination (runs in executor)."""
    for file_path in source_path.rglob("*"):
        if file_path.is_file():
            relative_path = file_path.relative_to(source_path)
            dest_file_path = dest_path / relative_path

            # Create subdirectories if needed
            dest_file_path.parent.mkdir(parents=True, exist_ok=True)

            # Copy file
            shutil.copy2(file_path, dest_file_path)


async def _remove_card_config_flow(hass: "HomeAssistant", card_path: Path) -> None:
    """Remove a custom card (for config flow)."""
    try:
        if card_path.exists():
            await hass.async_add_executor_job(shutil.rmtree, card_path)
            _LOGGER.info(f"Successfully removed card from {card_path}")
        else:
            _LOGGER.debug(f"Card path does not exist, nothing to remove: {card_path}")
    except Exception as e:
        _LOGGER.error(f"Failed to remove card: {e}")


@config_entries.HANDLERS.register(DOMAIN)
class RamsesExtrasConfigFlow(config_entries.ConfigFlow):
    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Handle the initial step."""
        # Check if we already have an entry for this domain
        existing_entries = self.hass.config_entries.async_entries(DOMAIN)
        if existing_entries:
            return self.async_abort(reason="single_instance_allowed")

        # No user input needed for single-instance integration
        # Just create the config entry directly
        enabled_features = {}
        for feature_key in AVAILABLE_FEATURES.keys():
            # Default feature is always enabled, others start disabled
            if feature_key == "default":
                enabled_features[feature_key] = True
            else:
                enabled_features[feature_key] = (
                    False  # Start with all optional features disabled
                )

        return self.async_create_entry(
            title="Ramses Extras",
            data={
                CONF_NAME: "Ramses Extras",
                CONF_ENABLED_FEATURES: enabled_features,
            },
        )

    @classmethod
    def async_get_options_flow(
        cls, config_entry: ConfigEntry
    ) -> "RamsesExtrasOptionsFlowHandler":
        """Return options flow handler for existing config entries."""
        return RamsesExtrasOptionsFlowHandler(config_entry)


class RamsesExtrasOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options flow for Ramses Extras."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize options flow."""
        self._config_entry = config_entry
        self._pending_data: dict[str, Any] | None = None
        self._entity_manager: EntityManager | None = (
            None  # Will be initialized when needed
        )
        self._config_flow_helper: ConfigFlowHelper | None = None
        self._feature_changes_detected = False
        self._entities_to_remove: list[str] = []
        self._entities_to_create: list[str] = []
        self._selected_feature: str | None = None
        self._all_devices: list[Any] | None = None
        self._features_for_device_config: list[str] | None = None

    async def async_step_init(
        self, user_input: dict[str, list[str]] | None = None
    ) -> config_entries.FlowResult:
        """Handle options initialization - redirect to main menu."""
        return await self.async_step_main_menu()

    async def async_step_main_menu(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Handle the main configuration menu with ramses_cc style
        link/button navigation."""
        # DEBUG: Log all available features
        _LOGGER.info(
            f"DEBUG: All available features: {list(AVAILABLE_FEATURES.keys())}"
        )

        # Build main menu options with ramses_cc style (links/buttons, not dropdowns)
        # Menu options must be a list of step IDs; labels are provided via translations
        menu_options: list[str] = []

        # Add static menu options; step IDs must match async_step_* method names
        static_menu_items = {
            "features": "Enable/Disable Features",
            "configure_devices": "Configure Devices for Features",
            "view_configuration": "View Current Configuration",
            "advanced_settings": "Advanced Settings",
        }

        for static_item, static_label in static_menu_items.items():
            menu_options.append(static_item)
            _LOGGER.info(
                f"DEBUG: Added static menu item: {static_item} -> {static_label}"
            )

        # Add dynamic feature options for features with config flows
        # Only list features that are actually enabled in the config entry
        dynamic_features_found = []
        current_features = self._config_entry.data.get("enabled_features", {})
        for feature_id, feature_config in AVAILABLE_FEATURES.items():
            # Don't Skip default feature from menu (we may have settings for it)
            # if feature_id == "default":
            #     _LOGGER.info("DEBUG: Skipping default feature from menu")
            #     continue

            # Only add features that have device configuration (has_device_config: True)
            if feature_config.get("has_device_config", False):
                # Skip features that are not enabled
                if not current_features.get(feature_id):
                    _LOGGER.info(
                        "DEBUG: Feature %s is not enabled, skipping", feature_id
                    )
                    continue

                # Use feature-specific step IDs that map to
                # async_step_feature_* handlers
                step_id = f"feature_{feature_id}"
                menu_options.append(step_id)
                dynamic_features_found.append(feature_id)
                _LOGGER.info(
                    f"DEBUG: Added dynamic menu item: {step_id} -> "
                    f"{feature_config.get('name', feature_id)}"
                )
            else:
                _LOGGER.info(
                    f"DEBUG: Feature {feature_id} does not have "
                    f"has_device_config=True, skipping"
                )

        # DEBUG: Log final menu options
        _LOGGER.info(f"DEBUG: Final menu items: {menu_options}")
        _LOGGER.info(f"DEBUG: Dynamic features found: {dynamic_features_found}")

        # Get current configuration summary
        enabled_count = sum(
            1
            for enabled in current_features.values()
            if enabled and not isinstance(enabled, str)
        )

        info_text = "🎛️ **Ramses Extras Configuration**\n\n"

        info_text += f"Currently have {enabled_count} features enabled.\n"
        info_text += "Choose what you want to configure:\n\n"

        # Add feature-centric details using per-feature translations when available
        feature_lines: list[str] = []
        for feature_id in dynamic_features_found:
            feature_title = await self._get_feature_title_from_translations(feature_id)
            feature_lines.append(f"- Feature: {feature_title}")

        if feature_lines:
            info_text += "\nAvailable feature configurations:\n" + "\n".join(
                feature_lines
            )

        # DEBUG: Log translation availability
        _LOGGER.info(f"DEBUG: Current language: {self.hass.config.language}")
        _LOGGER.info(f"DEBUG: Translation domain: {DOMAIN}")

        # DEBUG: Check if translation files are available
        try:
            from homeassistant.helpers.translation import async_get_translations

            translations = await async_get_translations(
                self.hass,
                self.hass.config.language,
                "options",
                integrations=[DOMAIN],
            )
            _LOGGER.info(f"DEBUG: Available translations: {translations}")
        except Exception as e:
            _LOGGER.error(f"DEBUG: Error checking translations: {e}")

        # DEBUG: Check if feature translations exist in options category
        try:
            feature_translations = await async_get_translations(
                self.hass,
                self.hass.config.language,
                "options",
                integrations=[DOMAIN],
            )
            _LOGGER.info(f"DEBUG: Feature item translation: {feature_translations}")
        except Exception as e:
            _LOGGER.error(f"DEBUG: Error checking feature_item translation: {e}")

        # DEBUG: Check if translations are loaded at all
        try:
            # Try to get the integration translations directly
            integration_translations = self.hass.data.get("translations", {}).get(
                DOMAIN, {}
            )
            _LOGGER.info(
                f"DEBUG: Integration translations loaded: "
                f"{bool(integration_translations)}"
            )
            if integration_translations:
                _LOGGER.info(
                    f"DEBUG: Integration translations content: "
                    f"{integration_translations}"
                )
        except Exception as e:
            _LOGGER.error(f"DEBUG: Error checking integration translations: {e}")

        # DEBUG: Check translation file paths (run blocking I/O in executor)
        try:
            import os

            translations_dir = os.path.join(os.path.dirname(__file__), "translations")
            _LOGGER.info(f"DEBUG: Translations directory: {translations_dir}")

            def _path_info(path: str) -> tuple[bool, list[str]]:
                exists = os.path.exists(path)
                files: list[str] = []
                if exists:
                    files = os.listdir(path)
                return exists, files

            exists, files = await self.hass.async_add_executor_job(
                _path_info, translations_dir
            )
            _LOGGER.info(f"DEBUG: Translations directory exists: {exists}")
            if exists:
                _LOGGER.info(f"DEBUG: Files in translations directory: {files}")
        except Exception as e:
            _LOGGER.error(f"DEBUG: Error checking translation files: {e}")

        return self.async_show_menu(
            step_id="main_menu",
            menu_options=menu_options,
            description_placeholders={"info": info_text},
        )

    async def async_step_features(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Handle enable/disable features step."""
        # Get current enabled features
        current_features = self._config_entry.data.get("enabled_features", {})
        enabled_features = {k: v for k, v in current_features.items() if k != "default"}

        # Get config flow helper
        helper = self._get_config_flow_helper()

        if user_input is not None:
            # User submitted feature selection - stage changes for confirmation
            selected_features = user_input.get("features", [])

            # Build new enabled_features mapping including default
            staged_enabled_features: dict[str, bool] = {"default": True}
            for feature_id in AVAILABLE_FEATURES.keys():
                if feature_id == "default":
                    continue  # Skip default feature in selector
                staged_enabled_features[feature_id] = feature_id in selected_features

            # Store staged changes in pending data for confirm step
            if self._pending_data is None:
                self._pending_data = {}

            self._pending_data["enabled_features_old"] = current_features
            self._pending_data["enabled_features_new"] = staged_enabled_features
            self._feature_changes_detected = staged_enabled_features != current_features

            return await self.async_step_confirm()

        # Build feature selection schema
        schema = helper.get_feature_selection_schema(enabled_features)

        # Build info text
        info_text = helper.build_feature_info_text()

        return self.async_show_form(
            step_id="features",
            data_schema=schema,
            description_placeholders={"info": info_text},
        )

    async def async_step_configure_devices(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Handle configure devices step."""
        return await self.async_step_main_menu()

    async def async_step_view_configuration(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Handle view configuration step."""
        # Get current configuration summary
        current_features = self._config_entry.data.get("enabled_features", {})
        enabled_count = sum(
            1
            for enabled in current_features.values()
            if enabled and not isinstance(enabled, str)
        )

        info_text = "📋 **Current Configuration**\n\n"
        info_text += f"Enabled features: {enabled_count}\n\n"

        # List enabled features
        for feature_id, enabled in current_features.items():
            if enabled and not isinstance(enabled, str):
                feature_name = AVAILABLE_FEATURES.get(feature_id, {}).get(
                    "name", feature_id
                )
                info_text += f"- {feature_name} ({feature_id})\n"

        return self.async_show_form(
            step_id="view_configuration",
            description_placeholders={"info": info_text},
            data_schema=vol.Schema({}),
        )

    async def async_step_advanced_settings(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Handle advanced settings step."""
        if user_input is not None:
            # Handle advanced settings form submission
            pass

        # Show advanced settings form
        data_schema = vol.Schema(
            {
                vol.Optional("debug_mode", default=False): selector.BooleanSelector(),
                vol.Optional("log_level", default="info"): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            selector.SelectOptionDict(value="debug", label="Debug"),
                            selector.SelectOptionDict(value="info", label="Info"),
                            selector.SelectOptionDict(value="warning", label="Warning"),
                            selector.SelectOptionDict(value="error", label="Error"),
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
            }
        )

        return self.async_show_form(
            step_id="advanced_settings",
            data_schema=data_schema,
            description_placeholders={"info": "Configure advanced settings"},
        )

    async def async_step_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Confirmation step after feature or device configuration.

        This step summarizes pending changes and applies them once confirmed,
        before returning to the main menu.
        """
        helper = self._get_config_flow_helper()

        current_features = self._config_entry.data.get("enabled_features", {})
        pending = self._pending_data or {}

        staged_enabled_features = pending.get("enabled_features_new", current_features)

        if user_input is not None:
            # Apply staged feature changes, if any
            if staged_enabled_features != current_features:
                new_data = dict(self._config_entry.data)
                new_data["enabled_features"] = staged_enabled_features
                self.hass.config_entries.async_update_entry(
                    self._config_entry,
                    data=new_data,
                )

                # Update cards based on new feature set
                await _manage_cards_config_flow(self.hass, staged_enabled_features)

            # Reset pending state and return to main menu
            self._pending_data = None
            self._feature_changes_detected = False

            return await self.async_step_main_menu()

        # Build summary of feature changes
        feature_change_lines: list[str] = []
        if staged_enabled_features != current_features:
            for feature_id, old_value in current_features.items():
                new_value = bool(staged_enabled_features.get(feature_id, False))
                if bool(old_value) != new_value:
                    feature_name = AVAILABLE_FEATURES.get(feature_id, {}).get(
                        "name", feature_id
                    )
                    state = "ENABLED" if new_value else "DISABLED"
                    feature_change_lines.append(
                        f"- {feature_name} ({feature_id}): {state}"
                    )

        # Add high-level feature/device summary from helper
        feature_device_summary = helper.get_feature_device_summary()

        info_text = "✅ **Confirm configuration changes**\n\n"
        if feature_change_lines:
            info_text += "Feature changes:\n" + "\n".join(feature_change_lines) + "\n\n"

        info_text += feature_device_summary

        return self.async_show_form(
            step_id="confirm",
            data_schema=vol.Schema({}),
            description_placeholders={"info": info_text},
        )

    # Add missing methods for backward compatibility
    async def async_step_feature_config(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Handle feature configuration step."""
        if not hasattr(self, "_selected_feature") or not self._selected_feature:
            return await self.async_step_main_menu()

        feature_id = self._selected_feature
        feature_config = AVAILABLE_FEATURES.get(feature_id, {})

        # Get devices for this feature
        devices = self._get_all_devices()
        filtered_devices = (
            self._get_config_flow_helper().get_devices_for_feature_selection(
                feature_config, devices
            )
        )

        # Get current enabled devices for this feature
        current_enabled = (
            self._get_config_flow_helper().get_enabled_devices_for_feature(feature_id)
        )

        if user_input is not None:
            # User submitted device selection for this feature - stage it and confirm
            selected_device_ids = user_input.get("enabled_devices", [])
            self._store_feature_device_config(feature_id, selected_device_ids)

            if self._pending_data is None:
                self._pending_data = {}

            feature_devices: dict[str, Any] = self._pending_data.get(
                "feature_devices", {}
            )
            feature_devices[feature_id] = selected_device_ids
            self._pending_data["feature_devices"] = feature_devices

            return await self.async_step_confirm()

        # Build device options
        device_options = [
            selector.SelectOptionDict(
                value=device_id, label=self._get_device_label(device)
            )
            for device in filtered_devices
            if (device_id := self._extract_device_id(device))
        ]

        # Create schema for device selection, using LIST mode for checkboxes
        schema = vol.Schema(
            {
                vol.Required(
                    "enabled_devices", default=current_enabled
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=device_options,
                        multiple=True,
                        mode=selector.SelectSelectorMode.LIST,
                    )
                ),
            }
        )

        feature_name = feature_config.get("name", feature_id)
        info_text = f"🎛️ **{feature_name} Configuration**\n\n"
        info_text += f"Select devices to enable {feature_name} for:\n"

        return self.async_show_form(
            step_id="feature_config",
            data_schema=schema,
            description_placeholders={"info": info_text},
        )

    async def async_step_device_selection(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Handle device selection step."""
        if not hasattr(self, "_selected_feature") or not self._selected_feature:
            # Fallback to main menu if no feature is selected
            return await self.async_step_main_menu()

        feature_id = self._selected_feature
        feature_config = AVAILABLE_FEATURES.get(feature_id, {})

        # Get devices for this feature
        devices = self._get_all_devices()
        filtered_devices = (
            self._get_config_flow_helper().get_devices_for_feature_selection(
                feature_config, devices
            )
        )

        # Get current enabled devices for this feature
        current_enabled = (
            self._get_config_flow_helper().get_enabled_devices_for_feature(feature_id)
        )

        # Build device options
        device_options = [
            selector.SelectOptionDict(
                value=device_id, label=self._get_device_label(device)
            )
            for device in filtered_devices
            if (device_id := self._extract_device_id(device))
        ]

        # Create schema for device selection
        schema = vol.Schema(
            {
                vol.Required(
                    "enabled_devices", default=current_enabled
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=device_options,
                        multiple=True,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
            }
        )

        feature_name = feature_config.get("name", feature_id)
        info_text = f"🎛️ **{feature_name} Device Selection**\n\n"
        info_text += f"Select devices to enable {feature_name} for:\n"

        return self.async_show_form(
            step_id="device_selection",
            data_schema=schema,
            description_placeholders={"info": info_text},
        )

    def _store_feature_device_config(
        self, feature_id: str, device_ids: list[str]
    ) -> None:
        """Store feature/device configuration."""
        helper = self._get_config_flow_helper()
        helper.set_enabled_devices_for_feature(feature_id, device_ids)

    def _get_all_devices(self) -> list[Any]:
        """Get all available devices."""
        if hasattr(self.hass, "data") and "ramses_extras" in self.hass.data:
            devices = self.hass.data["ramses_extras"].get("devices", [])
            return devices if isinstance(devices, list) else []
        return []

    def _extract_device_id(self, device: Any) -> str | None:
        """Extract device ID from device object."""
        if isinstance(device, str):
            return device

        if hasattr(device, "id"):
            return str(device.id)
        if hasattr(device, "device_id"):
            return str(device.device_id)
        if hasattr(device, "_id"):
            return str(device._id)
        if hasattr(device, "name"):
            return str(device.name)

        return None

    def _get_device_label(self, device: Any) -> str:
        """Get display label for a device."""
        if isinstance(device, str):
            base_label = device
        elif hasattr(device, "name"):
            base_label = str(device.name)
        elif hasattr(device, "device_id"):
            base_label = str(device.device_id)
        elif hasattr(device, "id"):
            base_label = str(device.id)
        else:
            base_label = "Unknown Device"

        # Try to enrich the label with device slugs when available so users
        # can see both the ID and the logical slug (e.g. FAN).
        try:
            slugs = DeviceFilter._get_device_slugs(device)
            if slugs:
                # Remove duplicates and avoid repeating the base label as slug
                unique_slugs = sorted({str(slug) for slug in slugs if str(slug)})
                slugs_label = ", ".join(unique_slugs)
                if slugs_label and slugs_label != base_label:
                    return f"{base_label} [{slugs_label}]"
        except Exception:  # pragma: no cover - defensive, should not happen
            pass

        return base_label

    def _get_config_flow_helper(self) -> ConfigFlowHelper:
        """Get or create config flow helper."""
        if self._config_flow_helper is None:
            self._config_flow_helper = ConfigFlowHelper(self.hass, self._config_entry)
        return self._config_flow_helper

    async def _get_feature_title_from_translations(self, feature_id: str) -> str:
        """Get feature title from feature-specific translations if available.

        Falls back to the feature name from AVAILABLE_FEATURES when no
        feature-specific translation file is present.
        """
        feature_config = AVAILABLE_FEATURES.get(feature_id, {})
        default_title = str(feature_config.get("name", feature_id))

        language = getattr(self.hass.config, "language", "en") or "en"

        base_path = Path(__file__).parent / "features" / feature_id / "translations"
        translations_path = base_path / f"{language}.json"
        if not translations_path.exists():
            translations_path = base_path / "en.json"
            if not translations_path.exists():
                return default_title

        def _load_title(path: Path, fallback: str) -> str:
            try:
                with path.open(encoding="utf-8") as file:
                    data: dict[str, Any] = json.load(file)
                title = (
                    data.get("config", {})
                    .get("step", {})
                    .get(f"feature_{feature_id}", {})
                    .get("title", fallback)
                )
                return str(title) if title else fallback
            except Exception:
                return fallback

        result: str = await self.hass.async_add_executor_job(
            _load_title, translations_path, default_title
        )
        return result

    # Add handler for dynamic feature menu items
    async def async_step_feature_default(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Handle default configuration via feature-specific helper.

        This method stays as the Home Assistant entrypoint but delegates the
        actual form building to the feature's own config_flow helper so that
        the default feature can serve as an example for other features.
        """
        from .features.default import config_flow as default_config_flow

        return await default_config_flow.async_step_default_config(self, user_input)

    async def async_step_feature_humidity_control(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Handle humidity control feature configuration."""
        self._selected_feature = "humidity_control"
        return await self.async_step_feature_config(user_input)

    async def async_step_feature_hvac_fan_card(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Handle HVAC fan card feature configuration.

        The HVAC fan card does not require per-device configuration. This
        step therefore only shows an informational message and no form
        fields, so the user can see that the card is enabled without
        having to select devices.
        """
        feature_id = "hvac_fan_card"
        feature_config = AVAILABLE_FEATURES.get(feature_id, {})
        feature_name = feature_config.get("name", feature_id)

        info_text = "🎴 **" + str(feature_name) + "**\n\n"
        info_text += (
            "This feature only installs and registers the HVAC fan card. "
            "No additional configuration is required."
        )

        # Reuse the generic feature_config step translations by using the
        # existing step_id but with an empty schema.
        return self.async_show_form(
            step_id="feature_config",
            data_schema=vol.Schema({}),
            description_placeholders={"info": info_text},
        )

    async def async_step_feature_hello_world_card(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Handle hello world card feature configuration."""
        self._selected_feature = "hello_world_card"
        return await self.async_step_feature_config(user_input)
