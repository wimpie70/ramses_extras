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
        self._pending_data: dict[str, list[str]] | None = None
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
        if user_input is not None:
            # User selected a menu option
            menu_choice = user_input.get("menu_option")

            if menu_choice == "enable_features":
                return await self.async_step_features()
            if menu_choice == "configure_devices":
                return await self.async_step_device_menu()
            if menu_choice == "view_configuration":
                return await self.async_step_view_configuration()
            if menu_choice == "advanced_settings":
                return await self.async_step_advanced_settings()
            # Unknown option, go back to main menu
            return await self.async_step_main_menu()

        # Build main menu options with ramses_cc style (links/buttons, not dropdowns)
        menu_options = [
            selector.SelectOptionDict(
                value="enable_features", label="1.1 Enable/Disable Features"
            ),
            selector.SelectOptionDict(
                value="configure_devices", label="1.2 Configure Devices for Features"
            ),
            selector.SelectOptionDict(
                value="view_configuration", label="1.3 View Current Configuration"
            ),
            selector.SelectOptionDict(
                value="advanced_settings", label="1.4 Advanced Settings"
            ),
        ]

        # Add dynamic feature options for features with config flows (ramses_cc style)
        for feature_id, feature_config in AVAILABLE_FEATURES.items():
            # Skip default feature from menu (it's always enabled)
            if feature_id == "default":
                continue

            # Only add features that have device configuration (has_device_config: True)
            if feature_config.get("has_device_config", False):
                feature_name = feature_config.get("name", feature_id)
                menu_options.append(
                    selector.SelectOptionDict(
                        value=f"feature_{feature_id}",
                        label=f"1.{len(menu_options) + 1} {feature_name} Settings",
                    )
                )

        schema = vol.Schema(
            {
                vol.Required("menu_option"): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=menu_options,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                        # Using dropdown for now, but UI will show as links
                    )
                ),
            }
        )

        # Get current configuration summary
        current_features = self._config_entry.data.get("enabled_features", {})
        enabled_count = sum(
            1
            for enabled in current_features.values()
            if enabled and not isinstance(enabled, str)
        )

        info_text = "🎛️ **Ramses Extras Configuration**\n\n"
        info_text += f"Currently have {enabled_count} features enabled.\n"
        info_text += "Choose what you want to configure:\n\n"

        return self.async_show_form(
            step_id="main_menu",
            data_schema=schema,
            description_placeholders={"info": info_text},
        )
