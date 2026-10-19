# Part of the Ramses Extra integration
# See https://github.com/wimpie70/ramses_extras for more information
#
"""WebSocket commands for the Floorplan Helper feature.

- ``get_bundle`` — generate (or regenerate) the ha-floorplan bundle and
  return it; powers a "copy card YAML" action in extras cards.
- ``get_topology`` — return the floorplan model (devices, groups,
  areas, entities) without generating files; used for previews.
- ``list_icons`` — return the shipped icon keys.

:platform: Home Assistant
:feature: Floorplan Helper WebSocket Commands
"""

import logging
from typing import TYPE_CHECKING, Any

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant

from custom_components.ramses_extras.const import DOMAIN

from .const import (
    FLOORPLAN_ICONS,
    FLOORPLAN_STATIC_BASE,
    OPTION_CUSTOM_SVG_PATH,
    OPTION_EDITOR_URL,
    OPTION_PLANNER_URL,
    OPTION_SVG_MODE,
    OPTION_TOOLBAR_ENABLED,
)
from .generator import async_generate_bundle
from .mapping import get_floorplan_options
from .topology import build_floorplan_model

if TYPE_CHECKING:
    from homeassistant.components.websocket_api import ActiveConnection

_LOGGER = logging.getLogger(__name__)


def _config_entry(hass: HomeAssistant) -> Any | None:
    return hass.data.get(DOMAIN, {}).get("config_entry")


@websocket_api.websocket_command(
    {
        vol.Required("type"): "ramses_extras/floorplan_helper/get_bundle",
    }
)
@websocket_api.async_response
async def ws_get_bundle(
    hass: HomeAssistant, connection: ActiveConnection, msg: dict[str, Any]
) -> None:
    """Generate the floorplan bundle and return it."""
    try:
        entry = _config_entry(hass)
        if entry is None:
            connection.send_error(
                msg["id"], "no_config_entry", "No ramses_extras config entry"
            )
            return
        connection.send_result(msg["id"], await async_generate_bundle(hass, entry))
    except Exception as err:
        _LOGGER.error("Failed to generate floorplan bundle: %s", err)
        connection.send_error(
            msg["id"], "bundle_failed", "Failed to generate floorplan bundle"
        )


@websocket_api.websocket_command(
    {
        vol.Required("type"): "ramses_extras/floorplan_helper/get_topology",
    }
)
@websocket_api.async_response
async def ws_get_topology(
    hass: HomeAssistant, connection: ActiveConnection, msg: dict[str, Any]
) -> None:
    """Return the floorplan topology model without writing files."""
    try:
        connection.send_result(msg["id"], await build_floorplan_model(hass))
    except Exception as err:
        _LOGGER.error("Failed to build floorplan topology: %s", err)
        connection.send_error(
            msg["id"], "topology_failed", "Failed to build topology model"
        )


@websocket_api.websocket_command(
    {
        vol.Required("type"): "ramses_extras/floorplan_helper/list_icons",
    }
)
@websocket_api.async_response
async def ws_list_icons(
    hass: HomeAssistant, connection: ActiveConnection, msg: dict[str, Any]
) -> None:
    """Return the shipped icon keys and their URL base."""
    connection.send_result(
        msg["id"],
        {
            "icons": list(FLOORPLAN_ICONS),
            "icon_base_url": f"{FLOORPLAN_STATIC_BASE}/icons",
        },
    )


@websocket_api.websocket_command(
    {
        vol.Required("type"): "ramses_extras/floorplan_helper/get_config",
    }
)
@websocket_api.async_response
async def ws_get_config(
    hass: HomeAssistant, connection: ActiveConnection, msg: dict[str, Any]
) -> None:
    """Return the floorplan options the actions card needs (tool URLs)."""
    entry = _config_entry(hass)
    if entry is None:
        connection.send_error(
            msg["id"], "no_config_entry", "No ramses_extras config entry"
        )
        return
    options = get_floorplan_options(entry)
    connection.send_result(
        msg["id"],
        {
            "svg_mode": options.get(OPTION_SVG_MODE),
            "custom_svg_path": options.get(OPTION_CUSTOM_SVG_PATH),
            "editor_url": options.get(OPTION_EDITOR_URL),
            "planner_url": options.get(OPTION_PLANNER_URL),
            "toolbar_enabled": options.get(OPTION_TOOLBAR_ENABLED),
        },
    )


__all__ = [
    "ws_get_bundle",
    "ws_get_config",
    "ws_get_topology",
    "ws_list_icons",
]
