from __future__ import annotations

import asyncio
import logging

from homeassistant.const import EVENT_HOMEASSISTANT_STARTED
from homeassistant.core import Event, HomeAssistant
from homeassistant.helpers.typing import ConfigType

from ...const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def _handle_startup_event(
    event: Event, hass: HomeAssistant, config: ConfigType
) -> None:
    _LOGGER.info("Starting Ramses Extras from YAML configuration")

    await async_setup_yaml_config(hass, config)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    def _startup_callback(event: Event) -> None:
        asyncio.run_coroutine_threadsafe(
            _handle_startup_event(event, hass, config),
            hass.loop,
        )

    hass.bus.async_listen(EVENT_HOMEASSISTANT_STARTED, _startup_callback)

    return True


async def async_setup_yaml_config(hass: HomeAssistant, config: ConfigType) -> None:
    yaml_config = config.get(DOMAIN, {})
    if not yaml_config:
        return

    try:
        _LOGGER.info("Setting up Ramses Extras from YAML configuration...")

        entry_data = {
            "yaml": True,
            "enabled_features": yaml_config.get("enabled_features", {}),
        }

        hass.async_create_task(
            hass.config_entries.flow.async_init(
                DOMAIN,
                context={"source": "yaml"},
                data=entry_data,
            )
        )

    except Exception:
        _LOGGER.exception("Failed to set up Ramses Extras from YAML")
