import logging
from homeassistant import config_entries
import voluptuous as vol

from .const import DOMAIN

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
            return self.async_create_entry(title="Ramses Extras", data=user_input)

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

    async def async_setup(self, hass, config):
        """Set up the Ramses Extras integration."""
        # Check if ramses_cc is loaded - if so, auto-discover
        if "ramses_cc" in hass.config.components:
            _LOGGER.info("Ramses CC detected, auto-discovering Ramses Extras")
            hass.async_create_task(
                hass.config_entries.flow.async_init(
                    DOMAIN, context={"source": config_entries.SOURCE_DISCOVERY}
                )
            )
        return True