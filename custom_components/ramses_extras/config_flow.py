import logging
from homeassistant import config_entries
from homeassistant.helpers import selector
import voluptuous as vol

from .const import DOMAIN, AVAILABLE_FEATURES
from . import const

_LOGGER = logging.getLogger(__name__)

@config_entries.HANDLERS.register(DOMAIN)
class RamsesExtrasConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Ramses Extras."""
    VERSION = 1
#    MINOR_VERSION = 1

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
            vol.Required(const.CONF_NAME, default="Ramses Extras"): str,
        })
        return self.async_show_form(
            step_id="user",
            data_schema=schema,
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
                title=user_input.get(const.CONF_NAME, "Ramses Extras"),
                data={
                    const.CONF_NAME: user_input.get(const.CONF_NAME, "Ramses Extras"),
                    const.CONF_ENABLED_FEATURES: enabled_features
                }
            )

        # Build options for multi-select (simple labels with descriptions for dropdown)
        feature_options = []
        for feature_key, feature_config in AVAILABLE_FEATURES.items():
            feature_name = feature_config.get("name", feature_key)
            description = feature_config.get("description", "")
            
            # Create readable label with name and description
            if description:
                # Truncate long descriptions for dropdown readability
                short_desc = description[:60] + "..." if len(description) > 60 else description
                label = f"{feature_name} - {short_desc}"
            else:
                label = feature_name
                
            feature_options.append(selector.SelectOptionDict(
                value=feature_key,
                label=label
            ))

        # Build detailed summary for description area with entity information
        feature_summaries = []
        for feature_key, feature_config in AVAILABLE_FEATURES.items():
            name = feature_config.get("name", feature_key)
            category = feature_config.get("category", "")
            description = feature_config.get("description", "")
            
            # Build detailed information including entities
            detail_parts = [f"**{name}** ({category})"]
            if description:
                detail_parts.append(description)
            
            # Add supported device types right after description
            supported_devices = feature_config.get("supported_device_types", [])
            if supported_devices:
                detail_parts.append(f"Device Types: {', '.join(supported_devices)}")
            
            # Add entity requirements (no Required/Optional sections)
            required_sensors = feature_config.get("required_entities", {}).get("sensors", [])
            required_switches = feature_config.get("required_entities", {}).get("switches", [])
            required_booleans = feature_config.get("required_entities", {}).get("booleans", [])
            optional_sensors = feature_config.get("optional_entities", {}).get("sensors", [])
            optional_switches = feature_config.get("optional_entities", {}).get("switches", [])
            
            if required_sensors or required_switches or required_booleans:
                if required_sensors:
                    detail_parts.append(f"• Sensors: {', '.join(required_sensors)}")
                if required_switches:
                    detail_parts.append(f"• Switches: {', '.join(required_switches)}")
                if required_booleans:
                    detail_parts.append(f"• Booleans: {', '.join(required_booleans)}")
                    
            # Add optional entities with parentheses
            if optional_sensors or optional_switches:
                if optional_sensors:
                    detail_parts.append(f"• Optional Sensors: {', '.join(optional_sensors)}")
                if optional_switches:
                    detail_parts.append(f"• Optional Switches: {', '.join(optional_switches)}")
            
            feature_summaries.append("• " + "\n  ".join(detail_parts))

        features_info = "\n\n".join(feature_summaries)

        schema = vol.Schema({
            vol.Optional("name", default="Ramses Extras"): str,
            vol.Optional("features", default=[]): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=feature_options,
                    multiple=True,
                )
            ),
        })

        return self.async_show_form(
            step_id="features",
            data_schema=schema,
            description_placeholders={"info": features_info}
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

        # Build options for multi-select (simple labels with descriptions for dropdown)
        feature_options = []
        for feature_key, feature_config in AVAILABLE_FEATURES.items():
            feature_name = feature_config.get("name", feature_key)
            description = feature_config.get("description", "")
            
            # Create readable label with name and description
            if description:
                # Truncate long descriptions for dropdown readability
                short_desc = description[:60] + "..." if len(description) > 60 else description
                label = f"{feature_name} - {short_desc}"
            else:
                label = feature_name
                
            feature_options.append(selector.SelectOptionDict(
                value=feature_key,
                label=label
            ))

        # Build detailed summary for description area with entity information
        feature_summaries = []
        for feature_key, feature_config in AVAILABLE_FEATURES.items():
            name = feature_config.get("name", feature_key)
            category = feature_config.get("category", "")
            description = feature_config.get("description", "")
            
            # Build detailed information including entities
            detail_parts = [f"**{name}** ({category})"]
            if description:
                detail_parts.append(description)
            
            # Add supported device types right after description
            supported_devices = feature_config.get("supported_device_types", [])
            if supported_devices:
                detail_parts.append(f"Device Types: {', '.join(supported_devices)}")
            
            # Add entity requirements (no Required/Optional sections)
            required_sensors = feature_config.get("required_entities", {}).get("sensors", [])
            required_switches = feature_config.get("required_entities", {}).get("switches", [])
            required_booleans = feature_config.get("required_entities", {}).get("booleans", [])
            optional_sensors = feature_config.get("optional_entities", {}).get("sensors", [])
            optional_switches = feature_config.get("optional_entities", {}).get("switches", [])
            
            if required_sensors or required_switches or required_booleans:
                if required_sensors:
                    detail_parts.append(f"• Sensors: {', '.join(required_sensors)}")
                if required_switches:
                    detail_parts.append(f"• Switches: {', '.join(required_switches)}")
                if required_booleans:
                    detail_parts.append(f"• Booleans: {', '.join(required_booleans)}")
                    
            # Add optional entities with parentheses
            if optional_sensors or optional_switches:
                if optional_sensors:
                    detail_parts.append(f"• Optional Sensors: {', '.join(optional_sensors)}")
                if optional_switches:
                    detail_parts.append(f"• Optional Switches: {', '.join(optional_switches)}")
            
            feature_summaries.append("• " + "\n  ".join(detail_parts))

        features_info = "\n\n".join(feature_summaries)

        # Build the info text (no warnings on initial display)
        info_text = "Configure which Ramses Extras features are enabled."
        info_text += "\n📖 For detailed documentation, visit: https://github.com/YOUR_USERNAME/ramses_extras/wiki"
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
                # User confirmed, proceed with the changes
                return await self._save_config(self._pending_data)
            else:
                # User cancelled, go back to features step
                return await self.async_step_features()

        # Build confirmation message with details about what will be removed
        current_features = self._config_entry.data.get("enabled_features", {})
        selected_features = self._pending_data.get("features", [])

        # Convert selected features to enabled features dict
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

                # Add specific warnings based on feature type
                required_sensors = feature_config.get("required_entities", {}).get("sensors", [])
                required_switches = feature_config.get("required_entities", {}).get("switches", [])

                if required_sensors:
                    detail_parts.append(f"  - {len(required_sensors)} sensor entities\n")
                if required_switches:
                    detail_parts.append(f"  - {len(required_switches)} switch entities\n")

                # Add dashboard card warnings
                if "card" in feature_key:
                    detail_parts.append("  - Dashboard card")

                # Add automation warnings
                if "automation" in feature_key:
                    detail_parts.append("  - Related automations")

                removal_details.append(" ".join(detail_parts))

        confirmation_text = "The following features will be disabled:\n\n"
        confirmation_text += "\n".join(removal_details)
        confirmation_text += "\n\nThis action cannot be undone. Are you sure you want to proceed?"

        schema = vol.Schema({
            vol.Required("confirm", default=False): bool,
        })

        _LOGGER.info("Confirmation text: %s", confirmation_text)
        return self.async_show_form(
            step_id="confirm",
            data_schema=schema,
            description_placeholders={
                "info": confirmation_text
            }
        )

    async def _save_config(self, user_input):
        """Save the configuration and reload the integration."""
        # Convert selected features to enabled features dict
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

        # Reload the integration to apply changes
        await self.hass.config_entries.async_reload(self._config_entry.entry_id)

        return self.async_create_entry(title="", data={})