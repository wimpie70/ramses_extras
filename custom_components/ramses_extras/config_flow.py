import logging
from homeassistant import config_entries
from homeassistant.helpers import selector
import voluptuous as vol

from .const import DOMAIN, AVAILABLE_FEATURES

_LOGGER = logging.getLogger(__name__)

@config_entries.HANDLERS.register(DOMAIN)
class RamsesExtrasConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Ramses Extras."""
    VERSION = 0
    MINOR_VERSION = 1

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        # Check if we already have an entry for this domain
        existing_entries = self.hass.config_entries.async_entries(DOMAIN)
        if existing_entries:
            return self.async_abort(reason="single_instance_allowed")

        if user_input is not None:
            # Move to feature selection step
            return await self.async_step_features()

        schema = vol.Schema({
            vol.Required("name", default="Ramses Extras"): str,
        })
        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            description_placeholders={
                "info": "Ramses Extras provides additional functionality on top of Ramses RF."
            }
        )

    async def async_step_features(self, user_input=None):
        """Handle the feature selection step."""
        if user_input is not None:
            # Convert selected features to enabled features dict
            enabled_features = {}
            selected_features = user_input.get("features", [])
            
            for feature_key in AVAILABLE_FEATURES.keys():
                enabled_features[feature_key] = feature_key in selected_features

            return self.async_create_entry(
                title=user_input.get("name", "Ramses Extras"),
                data={
                    "name": user_input.get("name", "Ramses Extras"),
                    "enabled_features": enabled_features
                }
            )

        # Build options for multi-select
        feature_options = []
        for feature_key, feature_config in AVAILABLE_FEATURES.items():
            feature_name = feature_config.get("name", feature_key)
            
            # Create option with name
            option = {
                "value": feature_key,
                "label": feature_name,
            }
            feature_options.append(option)

        schema = vol.Schema({
            "name": vol.Required("name", default="Ramses Extras"),
            "features": selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=feature_options,
                    multiple=True,
                    mode=selector.SelectSelectorMode.LIST,
                ),
            ),
        })

        return self.async_show_form(
            step_id="features",
            data_schema=schema,
            description_placeholders={
                "info": "Select which Ramses Extras features you want to enable.\n\n📖 For detailed documentation, visit: https://github.com/YOUR_USERNAME/ramses_extras/wiki"
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
        # Don't manually set self.config_entry - use the passed config_entry directly
        self._config_entry = config_entry

    async def async_step_init(self, user_input=None):
        """Handle options initialization - redirect to features step."""
        return await self.async_step_features()

    async def async_step_features(self, user_input=None):
        """Handle the feature selection step for options."""
        if user_input is not None:
            # Convert selected features to enabled features dict
            enabled_features = {}
            selected_features = user_input.get("features", [])

            for feature_key in AVAILABLE_FEATURES.keys():
                enabled_features[feature_key] = feature_key in selected_features

            # Check for deselected features and build warnings
            current_features = self._config_entry.data.get("enabled_features", {})
            warnings = []

            for feature_key, feature_config in AVAILABLE_FEATURES.items():
                currently_enabled = current_features.get(feature_key, False)
                will_be_enabled = enabled_features[feature_key]

                if currently_enabled and not will_be_enabled:
                    # Feature is being disabled - add warning
                    feature_name = feature_config.get("name", feature_key)
                    warning_parts = [f"⚠️ **{feature_name}** will be disabled:"]

                    # Add specific warnings based on feature type
                    required_sensors = feature_config.get("required_entities", {}).get("sensors", [])
                    required_switches = feature_config.get("required_entities", {}).get("switches", [])

                    if required_sensors:
                        warning_parts.append(f"   • {len(required_sensors)} sensor entities will be removed")
                    if required_switches:
                        warning_parts.append(f"   • {len(required_switches)} switch entities will be removed")

                    # Add dashboard card warnings
                    if "card" in feature_key:
                        warning_parts.append("   • Dashboard card will be removed")

                    # Add automation warnings
                    if "automation" in feature_key:
                        warning_parts.append("   • Related automations will be disabled")

                    warnings.append("\n".join(warning_parts))

            # Update the config entry data
            new_data = self._config_entry.data.copy()
            new_data["enabled_features"] = enabled_features

            self.hass.config_entries.async_update_entry(
                self._config_entry, data=new_data
            )

            # Reload the integration to apply changes
            await self.hass.config_entries.async_reload(self._config_entry.entry_id)

            # Show warnings if any features were deselected (for debugging)
            if warnings:
                # Log warnings for debugging purposes
                for warning in warnings:
                    _LOGGER.info(f"Feature deselection warning: {warning.replace('⚠️ **', '').replace('**', '')}")

            return self.async_create_entry(title="", data={})

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

            # Create option with name
            option = {
                "value": feature_key,
                "label": feature_name,
            }
            feature_options.append(option)

        # Build the info text (no warnings on initial display)
        info_text = "Configure which Ramses Extras features are enabled."
        info_text += "\n📖 For detailed documentation, visit: https://github.com/YOUR_USERNAME/ramses_extras/wiki"

        schema = vol.Schema({
            vol.Optional("features", default=current_selected): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=feature_options,
                    multiple=True,
                    mode=selector.SelectSelectorMode.LIST,
                ),
            ),
        })

        return self.async_show_form(
            step_id="features",
            data_schema=schema,
            description_placeholders={
                "info": info_text
            }
        )