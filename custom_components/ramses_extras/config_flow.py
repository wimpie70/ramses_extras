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
        if user_input is not None:
            return self.async_create_entry(title="Ramses Extras", data=user_input)

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
        
    async def async_setup(hass, config):
        hass.async_create_task(
            hass.config_entries.flow.async_init(
                DOMAIN, context={"source": config_entries.SOURCE_DISCOVERY}
            )
        )
        return True