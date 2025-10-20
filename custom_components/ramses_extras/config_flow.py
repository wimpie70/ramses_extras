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

        # If no user input and this is auto-discovery, create entry automatically
        if not user_input and self.init_data is None:
            return self.async_create_entry(
                title="Ramses Extras",
                data={"name": "Ramses Extras"}
            )

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

    async def async_step_init(self, user_input=None):
        """Handle options flow for existing config entries."""
        return await self.async_step_features()

    @classmethod
    def async_get_options_flow(cls, config_entry):
        """Return options flow handler for existing config entries."""
        return RamsesExtrasOptionsFlowHandler(config_entry)


class RamsesExtrasOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options flow for Ramses Extras."""

    def __init__(self, config_entry):
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        """Handle options initialization."""
        return await self.async_step_features()

    async def async_step_features(self, user_input=None):
        """Handle the feature selection step for options."""
        if user_input is not None:
            # Convert selected features to enabled features dict
            enabled_features = {}
            selected_features = user_input.get("features", [])
            
            for feature_key in AVAILABLE_FEATURES.keys():
                enabled_features[feature_key] = feature_key in selected_features

            # Update the config entry data
            new_data = self.config_entry.data.copy()
            new_data["enabled_features"] = enabled_features

            self.hass.config_entries.async_update_entry(
                self.config_entry, data=new_data
            )

            # Reload the integration to apply changes
            await self.hass.config_entries.async_reload(self.config_entry.entry_id)

            return self.async_create_entry(title="", data={})

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
                "info": "Configure which Ramses Extras features are enabled.\n\n📖 For detailed documentation, visit: https://github.com/YOUR_USERNAME/ramses_extras/wiki"
            }
        )

    async def async_setup(self, hass, config):
        """Set up the Ramses Extras integration."""
        # No auto-discovery - integration is manually added by user
        return True