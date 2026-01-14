"""YAML-to-config-flow bridge (secondary method) for Ramses Extras integration.

This module provides optional YAML configuration support by converting YAML
configuration into config flow entries. The integration primarily uses config flow
setup, with YAML serving as a secondary method that creates config flow entries
from YAML data during Home Assistant startup.

Note: This is a secondary setup method. The primary method is config flow setup
via async_setup_entry.

Configuration Priority:
YAML configuration is only used to create the initial config entry. Once the
config entry is modified through the UI (config flow), those settings take
precedence over the original YAML configuration. The system is designed to be
config flow-centric where UI changes become the source of truth.
"""

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
    """Handle Home Assistant startup event for YAML-to-config-flow bridge.

    :param event: Startup event
    :param hass: Home Assistant instance
    :param config: YAML configuration
    """
    _LOGGER.info("Starting Ramses Extras from YAML configuration")

    await async_setup_yaml_config(hass, config)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up optional YAML-to-config-flow bridge (secondary method).

    Registers a startup event listener to create a config flow entry
    from YAML configuration after Home Assistant has fully started.
    This is a secondary setup method - the primary method is config flow.

    :param hass: Home Assistant instance
    :param config: YAML configuration

    :return: True if setup was successful
    """

    def _startup_callback(event: Event) -> None:
        asyncio.run_coroutine_threadsafe(
            _handle_startup_event(event, hass, config),
            hass.loop,
        )

    hass.bus.async_listen(EVENT_HOMEASSISTANT_STARTED, _startup_callback)

    return True


async def async_setup_yaml_config(hass: HomeAssistant, config: ConfigType) -> None:
    """Create config flow entry from YAML configuration.

    Converts YAML configuration data into a config flow entry with
    context indicating YAML source.

    :param hass: Home Assistant instance
    :param config: YAML configuration dictionary
    """
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
