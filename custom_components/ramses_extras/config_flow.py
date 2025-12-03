import logging
import shutil
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

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
from .framework.helpers.config.feature_config_flow import FeatureConfigFlowBase
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
        self, user_input: dict[str, list[str]] | None = None
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
    """Handle options flow for Ramses Extras with menu-based navigation."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize options flow."""
        self._config_entry = config_entry
        self._pending_data: dict[str, list[str]] | None = None
        self._entity_manager: EntityManager | None = (
            None  # Will be initialized when needed
        )
        self._feature_changes_detected = False
        self._entities_to_remove: list[str] = []
        self._entities_to_create: list[str] = []

    async def async_step_init(
        self, user_input: dict[str, list[str]] | None = None
    ) -> config_entries.FlowResult:
        """Handle options initialization with dynamic feature loading menu."""
        _LOGGER.info("🏠 Initializing Ramses Extras options menu")

        # Generate menu options dynamically from AVAILABLE_FEATURES
        menu_options = ["features_management"]  # Always include features management

        # Add features that have menu_visible=True
        for feature_key, feature_config in AVAILABLE_FEATURES.items():
            if feature_config.get("menu_visible", False):
                menu_options.append(feature_key)
                _LOGGER.info(f"📋 Added menu option for feature: {feature_key}")

        menu_options.append("general_settings")  # Always include general settings

        _LOGGER.info(f"🎯 Final menu options: {menu_options}")
        return self.async_show_menu(
            step_id="init",
            menu_options=menu_options,
        )

    async def async_step_features_management(
        self, user_input: dict[str, list[str]] | None = None
    ) -> config_entries.FlowResult:
        """Handle features management - enable/disable features (ramses_cc pattern)."""
        if user_input is not None:
            # Get current features and determine feature changes
            current_features = self._config_entry.data.get("enabled_features", {})
            selected_features = user_input.get("features", [])

            # Convert selected features to enabled features dict
            enabled_features = {}
            for feature_key in AVAILABLE_FEATURES.keys():
                # Default feature is always enabled, regardless of user selection
                if feature_key == "default":
                    enabled_features[feature_key] = True
                else:
                    enabled_features[feature_key] = feature_key in selected_features

            # Check for any feature changes using EntityManager
            feature_changes = []
            for feature_key, feature_config in AVAILABLE_FEATURES.items():
                currently_enabled = current_features.get(feature_key, False)
                will_be_enabled = enabled_features[feature_key]

                if currently_enabled != will_be_enabled:
                    change_type = "enabling" if will_be_enabled else "disabling"
                    feature_changes.append((feature_key, change_type))

            # If there are any feature changes, build entity catalog
            #  and show confirmation
            if feature_changes:
                # Initialize EntityManager once and build catalog with target features
                self._entity_manager = EntityManager(self.hass)

                # Check for existing device selections in feature configurations
                # and create entities only for selected devices, not all compatible ones
                feature_configs = self._config_entry.options.get("features", {})
                _LOGGER.info(f"Existing feature configs: {feature_configs}")

                # For each feature being enabled, check if it has device selections
                for feature_key, will_be_enabled in enabled_features.items():
                    if will_be_enabled and feature_key != "default":
                        # Check if this feature has existing device selections
                        existing_feature_config = feature_configs.get(feature_key, {})
                        selected_devices = existing_feature_config.get(
                            "selected_devices", []
                        )

                        if selected_devices:
                            _LOGGER.info(
                                f"Feature {feature_key} has existing selections: "
                                f"{selected_devices}"
                            )
                            # Store the selected devices for this feature to use
                            #  during entity creation
                            # This will be used by the EntityManager to only
                            #  create entities for
                            # selected devices
                            if not hasattr(
                                self._entity_manager, "_feature_device_selections"
                            ):
                                self._entity_manager._feature_device_selections = {}

                            self._entity_manager._feature_device_selections[
                                feature_key
                            ] = selected_devices
                        else:
                            _LOGGER.info(
                                f"Feature {feature_key} has no existing selections - "
                                f"will use all compatible devices"
                            )

                await self._entity_manager.build_entity_catalog(
                    AVAILABLE_FEATURES, current_features, enabled_features
                )

                # Store entity changes for confirmation
                self._entities_to_remove = self._entity_manager.get_entities_to_remove()
                self._entities_to_create = self._entity_manager.get_entities_to_create()
                self._feature_changes_detected = True
                self._pending_data = user_input

                _LOGGER.info(
                    f"EntityManager created for feature changes: {feature_changes}"
                )

                # Show confirmation with entity changes
                return await self.async_step_confirm()

            # No feature changes detected, save config
            return await self._save_config(user_input)

        # Get current enabled features for default values
        current_features = self._config_entry.data.get("enabled_features", {})

        # Ensure all features are present in the config (for backward compatibility)
        if len(current_features) != len(AVAILABLE_FEATURES):
            _LOGGER.warning("backward compatible code used")
            # Initialize missing features with their default values
            for feature_key, feature_config in AVAILABLE_FEATURES.items():
                if feature_key not in current_features:
                    # Default feature is always enabled
                    if feature_key == "default":
                        current_features[feature_key] = True
                    else:
                        current_features[feature_key] = feature_config.get(
                            "default_enabled", False
                        )

            # Update the config entry with the complete feature set
            new_data = self._config_entry.data.copy()
            new_data["enabled_features"] = current_features
            self.hass.config_entries.async_update_entry(
                self._config_entry, data=new_data
            )

        # Get current selected features for the selector default
        # Exclude "default" feature since it's not user-configurable in the selector
        current_selected = [
            k for k, v in current_features.items() if v and k != "default"
        ]

        # Build options for multi-select (ramses_cc pattern)
        feature_options = []
        for feature_key, feature_config in AVAILABLE_FEATURES.items():
            # Skip default feature from user configuration (it's always enabled)
            if feature_key == "default":
                continue

            feature_name = str(feature_config.get("name", feature_key))
            description = str(feature_config.get("description", ""))
            if description:
                short_desc = (
                    description[:60] + "..." if len(description) > 60 else description
                )
                label = f"{feature_name} - {short_desc}"
            else:
                label = feature_name

            feature_options.append(
                selector.SelectOptionDict(value=feature_key, label=label)
            )

        # Build clean info text
        info_text = (
            "**Features Management**\n\n"
            "Enable or disable Ramses Extras features:\n\n"
            f"📖 Documentation: {GITHUB_WIKI_URL}\n\n"
            "Select the features you want to enable:"
        )

        schema_dict = {
            vol.Optional("features", default=current_selected): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=feature_options,
                    multiple=True,
                    mode=selector.SelectSelectorMode.LIST,
                )
            ),
        }

        schema = vol.Schema(schema_dict)

        return self.async_show_form(
            step_id="features_management",
            data_schema=schema,
            description_placeholders={"info": info_text},
            last_step=True,  # This is the final step for this menu option
        )

    async def async_step_humidity_control(
        self, user_input: dict[str, list[str]] | None = None
    ) -> config_entries.FlowResult:
        """Handle Humidity Control configuration with device selection."""
        feature_key = "humidity_control"

        if feature_key not in AVAILABLE_FEATURES:
            return self.async_abort(reason="invalid_feature")

        feature_config = AVAILABLE_FEATURES[feature_key]

        # Check if feature is enabled
        current_features = self._config_entry.data.get("enabled_features", {})
        if not current_features.get(feature_key, False):
            info_text = (
                "**Humidity Control is not enabled**\n\n"
                "Please enable Humidity Control in Features Management first."
            )
            return self.async_show_form(
                step_id="humidity_control",
                data_schema=vol.Schema({}),
                description_placeholders={"info": info_text},
                last_step=True,
            )

        # Handle device selection directly in this step
        return await self._handle_device_selection_for_feature(
            feature_key, feature_config, user_input
        )

    async def async_step_hvac_fan_card(
        self, user_input: dict[str, list[str]] | None = None
    ) -> config_entries.FlowResult:
        """Handle HVAC Fan Card configuration - card settings (ramses_cc pattern)."""
        feature_key = "hvac_fan_card"

        if feature_key not in AVAILABLE_FEATURES:
            return self.async_abort(reason="invalid_feature")

        feature_config = AVAILABLE_FEATURES[feature_key]

        # Check if feature is enabled
        current_features = self._config_entry.data.get("enabled_features", {})
        if not current_features.get(feature_key, False):
            info_text = (
                "**HVAC Fan Card is not enabled**\n\n"
                "Please enable the HVAC Fan Card feature in Features Management first."
            )
            return self.async_show_form(
                step_id="hvac_fan_card",
                data_schema=vol.Schema({}),
                description_placeholders={"info": info_text},
                last_step=True,
            )

        # HVAC Fan Card doesn't require device selection - it's card-only
        info_text = (
            f"**{feature_config.get('name', 'HVAC Fan Card')} Configuration**\n\n"
            f"{
                feature_config.get(
                    'description', 'Card-only feature - no extra config needed.'
                )
            }\n\n"
            f"✅ **Status:** Ready\n\n"
            f"This is a card-only feature. Entities are created automatically "
            f"for all compatible devices."
        )

        schema = vol.Schema({})

        return self.async_show_form(
            step_id="hvac_fan_card",
            data_schema=schema,
            description_placeholders={"info": info_text},
            last_step=True,
        )

    async def async_step_hello_world_card(
        self, user_input: dict[str, list[str]] | None = None
    ) -> config_entries.FlowResult:
        """Handle Hello World Card configuration with optional device selection."""
        feature_key = "hello_world_card"

        _LOGGER.info("🚀 Hello World Card config flow started")

        if feature_key not in AVAILABLE_FEATURES:
            _LOGGER.error("❌ Hello World Card feature not found in AVAILABLE_FEATURES")
            return self.async_abort(reason="invalid_feature")

        feature_config = AVAILABLE_FEATURES[feature_key]
        _LOGGER.info(f"📋 Hello World Card feature config: {feature_config}")

        # Check if feature is enabled
        current_features = self._config_entry.data.get("enabled_features", {})
        _LOGGER.info(f"🔍 Current features: {current_features}")
        if not current_features.get(feature_key, False):
            _LOGGER.warning("⚠️ Hello World Card feature is not enabled")
            info_text = (
                "**Hello World Card is not enabled**\n\n"
                "Please enable Hello World Card in Features Management first."
            )
            return self.async_show_form(
                step_id="hello_world_card",
                data_schema=vol.Schema({}),
                description_placeholders={"info": info_text},
                last_step=True,
            )

        _LOGGER.info(
            "✅ Hello World Card feature is enabled, proceeding with device selection"
        )
        # Handle optional device selection directly in this step
        return await self._handle_device_selection_for_feature(
            feature_key, feature_config, user_input, optional=True
        )

    async def async_step_general_settings(
        self, user_input: dict[str, list[str]] | None = None
    ) -> config_entries.FlowResult:
        """Handle general integration settings (ramses_cc pattern)."""
        # General settings - for now, just return info about integration
        info_text = (
            "**General Integration Settings**\n\n"
            "General Ramses Extras integration settings:\n\n"
            "✅ **Integration Status:** Active\n"
            f"✅ **Available Features:** {len(AVAILABLE_FEATURES) - 1} "
            f"optional features\n"
            "✅ **Card Registration:** Automatic\n"
            "✅ **Entity Management:** Lazy creation enabled\n\n"
            "Visit the GitHub wiki for detailed documentation:\n"
            f"📖 {GITHUB_WIKI_URL}"
        )

        schema = vol.Schema({})

        return self.async_show_form(
            step_id="general_settings",
            data_schema=schema,
            description_placeholders={"info": info_text},
            last_step=True,
        )

    async def _handle_device_selection_for_feature(
        self,
        feature_key: str,
        feature_config: dict[str, Any],
        user_input: dict[str, Any] | None = None,
        optional: bool = False,
    ) -> config_entries.FlowResult:
        """Handle device selection directly in a single step for a feature.

        Args:
            feature_key: Feature identifier
            feature_config: Feature configuration
            user_input: User input from device selection
            optional: Whether device selection is optional

        Returns:
            Flow result with device selection form or confirmation
        """
        try:
            # Get current device selection
            current_selection = []
            if "features" in self._config_entry.options:
                feature_options = self._config_entry.options.get("features", {})
                if feature_key in feature_options:
                    current_selection = feature_options[feature_key].get(
                        "selected_devices", []
                    )

            # Handle user input - direct save
            if user_input is not None:
                selected_devices = user_input.get("selected_devices", [])

                # Apply entity changes based on device selection
                await self._apply_device_selection_entity_changes(
                    feature_key, current_selection, selected_devices
                )

                # Store the feature configuration in options
                new_options = self._config_entry.options.copy()
                if "features" not in new_options:
                    new_options["features"] = {}
                new_options["features"][feature_key] = {
                    "selected_devices": selected_devices,
                    "feature_id": feature_key,
                }

                self.hass.config_entries.async_update_entry(
                    self._config_entry, options=new_options
                )

                _LOGGER.info(
                    f"💾 Stored feature config for {feature_key}: selected devices = "
                    f"{selected_devices}"
                )

                # Return to main menu
                return await self.async_step_init()

            # Discover devices for selection
            from .framework.helpers.device_selection import (
                create_device_selection_manager,
            )

            _LOGGER.info(f"🔍 Starting device discovery for feature: {feature_key}")
            device_selection_manager = await create_device_selection_manager(
                self.hass, feature_key
            )

            # Determine device types based on feature
            if feature_key == "humidity_control":
                # For humidity control, we only want FAN devices
                device_types = ["HvacVentilator"]
                discovered_devices = (
                    await device_selection_manager.discover_compatible_devices(
                        device_types
                    )
                )

                # Filter to only FAN devices for humidity control
                fan_devices = []
                for device in discovered_devices:
                    # Check if this is a FAN device (not just any HvacVentilator)
                    if self._is_fan_device(device):
                        fan_devices.append(device)

                discovered_devices = fan_devices
            else:
                # For other features like hello_world_card, show all device types
                # Get supported device types from feature configuration
                supported_device_types = feature_config.get(
                    "supported_device_types", []
                )

                # Special handling for hello_world_card - show ALL ramses_cc devices
                if feature_key == "hello_world_card":
                    _LOGGER.info(
                        "🌍 Hello World Card - using wildcard device discovery for ALL "
                        "ramses_cc devices"
                    )
                    # Use the new wildcard method to get ALL ramses_cc devices
                    discovered_devices = (
                        await device_selection_manager.discover_all_ramses_cc_devices()
                    )
                    _LOGGER.info(
                        f"🌍 Found {len(discovered_devices)} ramses_cc devices for "
                        f"hello_world_card"
                    )
                else:
                    # For other features, use the filtered device discovery
                    if not supported_device_types:
                        # Default to common device types if not specified
                        supported_device_types = [
                            "HvacVentilator",
                            "HvacCarbonDioxideSensor",
                            "HvacTemperatureSensor",
                            "HvacHumiditySensor",
                            "HvacController",
                            "Climate",
                            "Fan",
                            "Sensor",
                            "Switch",
                            "Number",
                            "BinarySensor",
                        ]

                    _LOGGER.info(
                        f"🔍 Discovering devices for {feature_key} with types: "
                        f"{supported_device_types}"
                    )
                    discovered_devices = (
                        await device_selection_manager.discover_compatible_devices(
                            supported_device_types
                        )
                    )
                    _LOGGER.info(
                        f"🔍 Found {len(discovered_devices)} devices for {feature_key}"
                    )

            if not discovered_devices:
                # No devices found - show error message
                # Determine which device types to show in the error message
                error_device_types = (
                    device_types
                    if feature_key == "humidity_control"
                    else supported_device_types
                )
                info_text = (
                    f"**No Compatible Devices Found**\n\n"
                    f"No devices of types {', '.join(error_device_types)} were found.\n"
                    f"This feature requires compatible devices to function.\n\n"
                    f"Make sure your Ramses system has the required devices configured."
                )
                _LOGGER.warning(
                    f"No compatible devices found for {feature_key}: "
                    f"{error_device_types}"
                )
                return self.async_show_form(
                    step_id=feature_key,
                    data_schema=vol.Schema({}),
                    description_placeholders={"info": info_text},
                    last_step=True,
                )

            # Build device selection options
            device_options = []
            for device in discovered_devices:
                # Format device label with proper naming
                device_name = device.get("name", device["device_id"])
                device_type = device.get("device_type", "Unknown")

                # For wildcard discovery, devices might have better names from broker
                # Use device name if meaningful, otherwise use device_id
                if device_name == device["device_id"] or not device_name:
                    # Device name is just the ID, try to make it more readable
                    if device_type == "HvacVentilator":
                        device_label = f"FAN {device['device_id']}"
                    elif device_type == "HvacCarbonDioxideSensor":
                        device_label = f"CO2 {device['device_id']}"
                    elif device_type == "HvacTemperatureSensor":
                        device_label = f"TEMP {device['device_id']}"
                    elif device_type == "HvacHumiditySensor":
                        device_label = f"HUM {device['device_id']}"
                    else:
                        device_label = f"{device_type} {device['device_id']}"
                else:
                    # Device has a proper name, use it
                    device_label = (
                        f"{device_name} ({device['device_id']}) - {device_type}"
                    )

                device_options.append(
                    selector.SelectOptionDict(
                        value=device["device_id"],
                        label=device_label,
                    )
                )

            # Build info text with device list
            feature_name = feature_config.get("name", feature_key)
            info_text = (
                f"**{feature_name} Device Selection**\n\n"
                f"Select devices to enable {feature_name} entities:\n\n"
            )

            for device in discovered_devices:
                # Use the same naming logic as device labels for consistency
                device_name = device.get("name", device["device_id"])
                device_type = device.get("device_type", "Unknown")

                if device_name == device["device_id"] or not device_name:
                    # Device name is just the ID, use type prefix
                    if device_type == "HvacVentilator":
                        display_name = f"FAN {device['device_id']}"
                    elif device_type == "HvacCarbonDioxideSensor":
                        display_name = f"CO2 {device['device_id']}"
                    elif device_type == "HvacTemperatureSensor":
                        display_name = f"TEMP {device['device_id']}"
                    elif device_type == "HvacHumiditySensor":
                        display_name = f"HUM {device['device_id']}"
                    else:
                        display_name = f"{device_type} {device['device_id']}"
                else:
                    display_name = device_name

                device_info = f"• {display_name} ({device_type})"
                if device.get("zone"):
                    device_info += f" (Zone: {device['zone']})"
                info_text += f"{device_info}\n"

            if optional:
                info_text += (
                    "\n\n**Note:** Device selection is optional for this feature. "
                    "You can proceed without selecting devices."
                )
            else:
                info_text += (
                    "\n\n**Note:** Entities will be created only for selected devices."
                )

            # Build schema
            schema_dict = {
                vol.Optional(
                    "selected_devices", default=current_selection
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=device_options,
                        multiple=True,
                        mode=selector.SelectSelectorMode.LIST,
                    )
                ),
            }

            schema = vol.Schema(schema_dict)

            return self.async_show_form(
                step_id=feature_key,
                data_schema=schema,
                description_placeholders={"info": info_text},
                last_step=True,  # Direct save, no confirmation step
            )

        except Exception as e:
            _LOGGER.error(
                f"❌ Failed to handle device selection for {feature_key}: {e}"
            )
            return self.async_abort(reason="feature_config_failed")

    async def _apply_device_selection_entity_changes(
        self,
        feature_key: str,
        old_devices: list[str],
        new_devices: list[str],
    ) -> None:
        """Apply entity changes based on device selection changes for a feature.

        Args:
            feature_key: The feature whose device selection changed
            old_devices: Previously selected device IDs
            new_devices: Newly selected device IDs
        """
        try:
            _LOGGER.info(
                f"Applying device selection changes for {feature_key}: "
                f"{old_devices} -> {new_devices}"
            )

            # Calculate device changes
            old_device_set = set(old_devices)
            new_device_set = set(new_devices)
            devices_to_add = new_device_set - old_device_set
            devices_to_remove = old_device_set - new_device_set

            if not devices_to_add and not devices_to_remove:
                _LOGGER.debug(f"No device changes for {feature_key}")
                return

            # Get feature configuration
            feature_config = AVAILABLE_FEATURES.get(feature_key, {})
            if not feature_config:
                _LOGGER.error(f"Feature config not found for {feature_key}")
                return

            # Get required entities for this feature
            required_entities = await self._get_required_entities_for_feature(
                feature_key
            )

            # Calculate entity changes
            entities_to_create = []
            entities_to_remove = []

            # Entities to create for newly selected devices
            for device_id in devices_to_add:
                for entity_type, entity_names in required_entities.items():
                    for entity_name in entity_names:
                        entity_id = (
                            f"{entity_type}.{entity_name}_{device_id.replace(':', '_')}"
                        )
                        entities_to_create.append(entity_id)

            # Entities to remove for deselected devices
            for device_id in devices_to_remove:
                for entity_type, entity_names in required_entities.items():
                    for entity_name in entity_names:
                        entity_id = (
                            f"{entity_type}.{entity_name}_{device_id.replace(':', '_')}"
                        )
                        entities_to_remove.append(entity_id)

            _LOGGER.info(
                f"Entity changes for {feature_key}: "
                f"create {len(entities_to_create)}, remove {len(entities_to_remove)}"
            )

            # Apply entity changes
            if entities_to_remove:
                await self._remove_entities_for_device_selection(entities_to_remove)

            if entities_to_create:
                # For creation, we trigger integration reload to create entities
                # This is the same approach used in the main config flow
                _LOGGER.info("Triggering integration reload to create new entities")
                await self.hass.config_entries.async_reload(self._config_entry.entry_id)

        except Exception as e:
            _LOGGER.error(
                f"Failed to apply device selection entity changes for {feature_key}: "
                f"{e}"
            )

    async def _get_required_entities_for_feature(
        self, feature_key: str
    ) -> dict[str, list[str]]:
        """Get required entities for a feature.

        Args:
            feature_key: Feature identifier

        Returns:
            Dictionary mapping entity_type to list of entity names
        """
        try:
            # Import the feature's const module
            import importlib

            feature_module_path = (
                f"custom_components.ramses_extras.features.{feature_key}.const"
            )
            feature_module = importlib.import_module(feature_module_path)

            # Get the FEATURE_CONST for this feature
            const_key = f"{feature_key.upper()}_CONST"
            if hasattr(feature_module, const_key):
                const_data = getattr(feature_module, const_key, {})
                return cast(
                    dict[str, list[str]], const_data.get("required_entities", {})
                )

            return {}
        except Exception as e:
            _LOGGER.debug(f"Could not get required entities for {feature_key}: {e}")
            return {}

    async def _remove_entities_for_device_selection(
        self, entity_ids: list[str]
    ) -> None:
        """Remove entities for device selection changes.

        Args:
            entity_ids: List of entity IDs to remove
        """
        try:
            from homeassistant.helpers import entity_registry

            entity_registry_instance = entity_registry.async_get(self.hass)

            removed_count = 0
            for entity_id in entity_ids:
                try:
                    entity_registry_instance.async_remove(entity_id)
                    removed_count += 1
                    _LOGGER.debug(f"Removed entity: {entity_id}")
                except Exception as e:
                    _LOGGER.warning(f"Could not remove entity {entity_id}: {e}")

            _LOGGER.info(
                f"Removed {removed_count} entities for device selection change"
            )

        except Exception as e:
            _LOGGER.error(f"Failed to remove entities for device selection: {e}")

    # Legacy method kept for backward compatibility - redirects to new menu
    async def async_step_features(
        self, user_input: dict[str, list[str]] | None = None
    ) -> config_entries.FlowResult:
        """Legacy method - redirects to new menu-based features management."""
        # Redirect to new menu-based approach
        return await self.async_step_init()

    async def async_step_confirm(
        self, user_input: dict[str, bool] | None = None
    ) -> config_entries.FlowResult:
        """Handle confirmation step for feature changes using EntityManager."""
        if user_input is not None:
            if user_input.get("confirm", False):
                return await self._save_config(
                    self._pending_data if self._pending_data else {}
                )
            return await self.async_step_features()

        # Use EntityManager to build clean confirmation message
        if self._entity_manager is None:
            # Fallback to old behavior if EntityManager not initialized
            return await self.async_step_features()

        # Get entity changes from EntityManager
        entities_to_remove = self._entities_to_remove
        entities_to_create = self._entities_to_create

        # Get feature summary
        entity_summary = self._entity_manager.get_entity_summary()

        # Build clean confirmation text
        confirmation_parts = []

        # Entities to be removed
        if entities_to_remove:
            confirmation_parts.append(
                f"**Entities to be removed ({len(entities_to_remove)}):**\n"
                f"• {', '.join(entities_to_remove[:5])}"
                f"{'...' if len(entities_to_remove) > 5 else ''}"
            )

        # Entities to be created
        if entities_to_create:
            confirmation_parts.append(
                f"**Entities to be created ({len(entities_to_create)}):**\n"
                f"• {', '.join(entities_to_create[:5])}"
                f"{'...' if len(entities_to_create) > 5 else ''}"
            )

        # Entity summary
        summary_parts = [
            f"Total possible entities: {entity_summary['total_entities']}",
            f"Existing and enabled: {entity_summary['existing_enabled']}",
            f"Existing but will be removed: {entity_summary['existing_disabled']}",
            f"Will be created: {entity_summary['non_existing_enabled']}",
        ]
        confirmation_parts.append(
            "**Entity Summary:**\n• " + "\n• ".join(summary_parts)
        )

        if not confirmation_parts:
            confirmation_parts.append("No entity changes detected.")

        confirmation_text = "\n\n".join(confirmation_parts)

        # Add general warnings for card changes
        if any("card" in entity for entity in entities_to_remove + entities_to_create):
            confirmation_text += "\n\n**Important for card changes:**"
            confirmation_text += "\n• After saving, restart Home Assistant"
            confirmation_text += "\n• Clear browser cache to see changes"

        confirmation_text += (
            "\n\nThis action cannot be undone. Are you sure you want to proceed?"
        )

        schema = vol.Schema(
            {
                vol.Required("confirm", default=False): bool,
                vol.Optional("cancel", default=False): bool,
            }
        )

        return self.async_show_form(
            step_id="confirm",
            data_schema=schema,
            description_placeholders={"info": confirmation_text},
        )

    async def _save_config(
        self, user_input: dict[str, list[str]]
    ) -> config_entries.FlowResult:
        """Save the configuration and apply entity changes using EntityManager."""
        enabled_features = {}
        selected_features = user_input.get("features", [])

        for feature_key in AVAILABLE_FEATURES.keys():
            # Default feature is always enabled, regardless of user selection
            if feature_key == "default":
                enabled_features[feature_key] = True
            else:
                enabled_features[feature_key] = feature_key in selected_features

        _LOGGER.info(
            f"Config flow - Current features: "
            f"{self._config_entry.data.get('enabled_features', {})}"
        )
        _LOGGER.info(f"Config flow - New features: {enabled_features}")

        # Apply entity changes using EntityManager if available
        if self._entity_manager and self._feature_changes_detected:
            try:
                _LOGGER.info(
                    f"Applying entity changes using EntityManager: "
                    f"remove={len(self._entities_to_remove)}, "
                    f"create={len(self._entities_to_create)}"
                )
                await self._entity_manager.apply_entity_changes()
            except Exception as e:
                _LOGGER.warning(
                    f"EntityManager changes failed, continuing with config update: {e}"
                )
        else:
            # No EntityManager available, should not happen in normal flow
            _LOGGER.warning("EntityManager not available, skipping entity changes")

        # Update the config entry data
        new_data = self._config_entry.data.copy()
        new_data["enabled_features"] = enabled_features

        self.hass.config_entries.async_update_entry(self._config_entry, data=new_data)

        # Install/remove cards based on new feature settings
        await _manage_cards_config_flow(self.hass, enabled_features)

        # Reload the integration to apply entity changes
        # This triggers platform setup which creates/removes entities
        _LOGGER.info("Config flow - Reloading integration to apply entity changes")
        await self.hass.config_entries.async_reload(self._config_entry.entry_id)

        return self.async_create_entry(title="", data={})

    def _is_fan_device(self, device: dict[str, Any]) -> bool:
        """Check if a device is a FAN device (not just any HVAC device).

        Args:
            device: Device information dictionary with device_id, device_type, etc.

        Returns:
            True if the device is a FAN device, False otherwise
        """
        # For device info dictionaries, check if it's a FAN device
        # The device_type should be "HvacVentilator" for FAN devices
        device_type = device.get("device_type", "")

        # Device is considered a FAN device if it's an HvacVentilator type
        # This is the primary indicator for FAN devices in the device selection
        # framework
        return cast(str, device_type) == "HvacVentilator"
