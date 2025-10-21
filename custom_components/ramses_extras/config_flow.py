import logging
import shutil
from pathlib import Path
from homeassistant import config_entries
from homeassistant.helpers import selector
import voluptuous as vol

from .const import DOMAIN, AVAILABLE_FEATURES, GITHUB_WIKI_URL, INTEGRATION_DIR
from . import const

_LOGGER = logging.getLogger(__name__)


async def _manage_cards_config_flow(hass, enabled_features):
    """Install or remove custom cards based on enabled features (for config flow)."""
    www_community_path = Path(hass.config.path("www", "community"))

    # Handle all card features dynamically
    for feature_key, feature_config in AVAILABLE_FEATURES.items():
        if feature_config.get("category") == "cards":
            card_source_path = INTEGRATION_DIR / feature_config.get("location", "")
            card_dest_path = www_community_path / feature_key

            if enabled_features.get(feature_key, False):
                if card_source_path.exists():
                    # For automatic registration, we don't need to copy files anymore
                    # The card is registered as a static resource in async_setup_entry
                    _LOGGER.info(f"Card {feature_key} is automatically registered")
                else:
                    _LOGGER.warning(f"Cannot register {feature_key}: source file not found at {card_source_path}")
            else:
                # Remove card from community folder if it exists
                await _remove_card_config_flow(hass, card_dest_path)


async def _install_card_config_flow(hass, source_path, dest_path):
    """Install a custom card by copying files (for config flow)."""
    try:
        if source_path.exists():
            # Create destination directory if it doesn't exist
            dest_path.mkdir(parents=True, exist_ok=True)

            # Copy all files from source to destination using executor
            await hass.async_add_executor_job(_copy_card_files_config_flow, source_path, dest_path)

            _LOGGER.info(f"Successfully installed card to {dest_path}")
        else:
            _LOGGER.warning(f"Card source path does not exist: {source_path}")
    except Exception as e:
        _LOGGER.error(f"Failed to install card: {e}")


def _copy_card_files_config_flow(source_path, dest_path):
    """Copy card files from source to destination (runs in executor)."""
    for file_path in source_path.rglob("*"):
        if file_path.is_file():
            relative_path = file_path.relative_to(source_path)
            dest_file_path = dest_path / relative_path

            # Create subdirectories if needed
            dest_file_path.parent.mkdir(parents=True, exist_ok=True)

            # Copy file
            shutil.copy2(file_path, dest_file_path)


async def _remove_card_config_flow(hass, card_path):
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
class RamsesExtrasConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        # Check if we already have an entry for this domain
        existing_entries = self.hass.config_entries.async_entries(DOMAIN)
        if existing_entries:
            return self.async_abort(reason="single_instance_allowed")

        # No user input needed for single-instance integration
        # Just create the config entry directly
        enabled_features = {}
        for feature_key in AVAILABLE_FEATURES.keys():
            enabled_features[feature_key] = False  # Start with all disabled

        return self.async_create_entry(
            title="Ramses Extras",
            data={
                const.CONF_NAME: "Ramses Extras",
                const.CONF_ENABLED_FEATURES: enabled_features
            }
        )

    @classmethod
    def async_get_options_flow(cls, config_entry):
        """Return options flow handler for existing config entries."""
        return RamsesExtrasOptionsFlowHandler(config_entry)


class RamsesExtrasOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options flow for Ramses Extras."""

    def __init__(self, config_entry):
        """Initialize options flow."""
        self._config_entry = config_entry
        self._pending_data = None

    async def async_step_init(self, user_input=None):
        """Handle options initialization - redirect to features step."""
        return await self.async_step_features()

    async def async_step_features(self, user_input=None):
        """Handle the feature selection step for options."""
        if user_input is not None:
            # Check if any currently enabled features would be disabled
            current_features = self._config_entry.data.get("enabled_features", {})
            selected_features = user_input.get("features", [])

            # Convert selected features to enabled features dict
            enabled_features = {}
            for feature_key in AVAILABLE_FEATURES.keys():
                enabled_features[feature_key] = feature_key in selected_features

            # Check for deselected features
            deselected_features = []
            for feature_key, feature_config in AVAILABLE_FEATURES.items():
                currently_enabled = current_features.get(feature_key, False)
                will_be_enabled = enabled_features[feature_key]

                if currently_enabled and not will_be_enabled:
                    deselected_features.append(feature_key)

            if deselected_features:
                # Store the pending data and go to confirmation step
                self._pending_data = user_input
                return await self.async_step_confirm()

            # No features being deselected, proceed directly
            return await self._save_config(user_input)

        # Get current enabled features for default values
        current_features = self._config_entry.data.get("enabled_features", {})

        # Ensure all features are present in the config (for backward compatibility)
        if len(current_features) != len(AVAILABLE_FEATURES):
            # Initialize missing features with their default values
            for feature_key, feature_config in AVAILABLE_FEATURES.items():
                if feature_key not in current_features:
                    current_features[feature_key] = feature_config.get("default_enabled", False)

            # Update the config entry with the complete feature set
            new_data = self._config_entry.data.copy()
            new_data["enabled_features"] = current_features
            self.hass.config_entries.async_update_entry(self._config_entry, data=new_data)

        # Get current selected features for the selector default
        current_selected = [k for k, v in current_features.items() if v]

        # Build options for multi-select
        feature_options = []
        for feature_key, feature_config in AVAILABLE_FEATURES.items():
            feature_name = feature_config.get("name", feature_key)
            description = feature_config.get("description", "")
            if description:
                short_desc = description[:60] + "..." if len(description) > 60 else description
                label = f"{feature_name} - {short_desc}"
            else:
                label = feature_name

            feature_options.append(selector.SelectOptionDict(
                value=feature_key,
                label=label
            ))

        # Build detailed summary for description area
        feature_summaries = []
        for feature_key, feature_config in AVAILABLE_FEATURES.items():
            name = feature_config.get("name", feature_key)
            category = feature_config.get("category", "")
            description = feature_config.get("description", "")

            detail_parts = [f"**{name}** ({category})"]
            if description:
                detail_parts.append(description)

            # Add supported device types
            supported_devices = feature_config.get("supported_device_types", [])
            if supported_devices:
                detail_parts.append(f"Device Types: {', '.join(supported_devices)}")

            # Add entity requirements
            required_sensors = feature_config.get("required_entities", {}).get("sensors", [])
            required_switches = feature_config.get("required_entities", {}).get("switches", [])
            required_booleans = feature_config.get("required_entities", {}).get("booleans", [])

            if required_sensors or required_switches or required_booleans:
                if required_sensors:
                    detail_parts.append(f"• Sensors: {', '.join(required_sensors)}")
                if required_switches:
                    detail_parts.append(f"• Switches: {', '.join(required_switches)}")
                if required_booleans:
                    detail_parts.append(f"• Booleans: {', '.join(required_booleans)}")

            feature_summaries.append("• " + "\n  ".join(detail_parts))

        features_info = "\n\n".join(feature_summaries)

        # Build the info text
        info_text = "Configure which Ramses Extras features are enabled."
        info_text += "\n📖 For detailed documentation, visit: " + GITHUB_WIKI_URL
        info_text += f"\n\n**Available Features:**\n{features_info}"

        schema = vol.Schema({
            vol.Optional("features", default=current_selected): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=feature_options,
                    multiple=True,
                )
            ),
        })

        return self.async_show_form(
            step_id="features",
            data_schema=schema,
            description_placeholders={
                "info": info_text
            }
        )

    async def async_step_confirm(self, user_input=None):
        """Handle confirmation step for feature deselection."""
        if user_input is not None:
            if user_input.get("confirm", False):
                return await self._save_config(self._pending_data)
            else:
                return await self.async_step_features()

        # Build confirmation message
        current_features = self._config_entry.data.get("enabled_features", {})
        selected_features = self._pending_data.get("features", [])

        enabled_features = {}
        for feature_key in AVAILABLE_FEATURES.keys():
            enabled_features[feature_key] = feature_key in selected_features

        # Build details about what will be removed
        removal_details = []
        for feature_key, feature_config in AVAILABLE_FEATURES.items():
            currently_enabled = current_features.get(feature_key, False)
            will_be_enabled = enabled_features[feature_key]

            if currently_enabled and not will_be_enabled:
                feature_name = feature_config.get("name", feature_key)
                detail_parts = [f"  • {feature_name}\n"]

                required_sensors = feature_config.get("required_entities", {}).get("sensors", [])
                required_switches = feature_config.get("required_entities", {}).get("switches", [])

                if required_sensors:
                    detail_parts.append(f"  - {len(required_sensors)} sensor entities\n")
                if required_switches:
                    detail_parts.append(f"  - {len(required_switches)} switch entities\n")

                if "card" in feature_key:
                    detail_parts.append("  - Dashboard card")
                if "automation" in feature_key:
                    detail_parts.append("  - Related automations")

                removal_details.append(" ".join(detail_parts))

        confirmation_text = "The following features will be disabled:\n\n"
        confirmation_text += "\n".join(removal_details)
        confirmation_text += "\n\nThis action cannot be undone. Are you sure you want to proceed?"

        schema = vol.Schema({
            vol.Required("confirm", default=False): bool,
        })

        return self.async_show_form(
            step_id="confirm",
            data_schema=schema,
            description_placeholders={
                "info": confirmation_text
            }
        )

    async def _save_config(self, user_input):
        """Save the configuration and reload the integration."""
        enabled_features = {}
        selected_features = user_input.get("features", [])

        for feature_key in AVAILABLE_FEATURES.keys():
            enabled_features[feature_key] = feature_key in selected_features

        # Update the config entry data
        new_data = self._config_entry.data.copy()
        new_data["enabled_features"] = enabled_features

        self.hass.config_entries.async_update_entry(
            self._config_entry, data=new_data
        )

        # Install/remove cards based on new feature settings
        await _manage_cards_config_flow(self.hass, enabled_features)

        # Reload the integration to apply changes
        await self.hass.config_entries.async_reload(self._config_entry.entry_id)

        return self.async_create_entry(title="", data={})