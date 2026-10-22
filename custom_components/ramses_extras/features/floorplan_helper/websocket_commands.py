# Part of the Ramses Extra integration
# See https://github.com/wimpie70/ramses_extras for more information
#
"""WebSocket commands for the Floorplan Helper feature.

- ``get_bundle`` — generate (or regenerate) the ha-floorplan bundle and
  return it; powers a "copy card YAML" action in extras cards.
- ``get_topology`` — return the floorplan model (devices, groups,
  areas, entities) without generating files; used for previews.
- ``get_project`` — return the stored studio project (latest.json) so
  the actions card can push it back into studio's IndexedDB.
- ``list_icons`` — return the shipped icon keys.

:platform: Home Assistant
:feature: Floorplan Helper WebSocket Commands
"""

import json
import logging
from typing import TYPE_CHECKING, Any

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant

from custom_components.ramses_extras.const import DOMAIN

from .bundle import async_generate_bundle
from .const import (
    FLOORPLAN_ICONS,
    FLOORPLAN_STATIC_BASE,
    OPTION_CUSTOM_SVG_PATH,
    OPTION_DEVICE_VIEW_URL,
    OPTION_DEVICE_ZONES,
    OPTION_EDITOR,
    OPTION_SVG_MODE,
    OPTION_TOOLBAR_ENABLED,
)
from .domains import caption_suffix_for, get_domain
from .editors import adapter_for, detect_editors, resolve_editor
from .importer import studio_marker_positions
from .mapping import get_floorplan_options
from .markers import editor_url, marker_meta_for_device
from .rules import caption_pairs_for_device
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
        vol.Optional("editor"): str,
    }
)
@websocket_api.async_response
async def ws_get_config(
    hass: HomeAssistant, connection: ActiveConnection, msg: dict[str, Any]
) -> None:
    """Return the floorplan options the actions card needs (tool URLs).

    ``editor`` — the card's own yaml override — resolves the adapter
    the card is bound to; the reply carries its capabilities so the
    menu can hide rows the editor can't support (no pull/push for
    server-side plans).
    """
    entry = _config_entry(hass)
    if entry is None:
        connection.send_error(
            msg["id"], "no_config_entry", "No ramses_extras config entry"
        )
        return
    options = get_floorplan_options(entry)
    adapter = await resolve_editor(hass, options, msg.get("editor"))
    available = await detect_editors(hass)

    # resolved per-device captions + the entity choices the actions
    # card's caption editor offers — the same precedence the export
    # uses, so the checkboxes show what the card will actually render
    captions: dict[str, list[list[str]]] = {}
    choices: dict[str, list[list[str]]] = {}
    try:
        model = await build_floorplan_model(hass)
        plan = await adapter.async_load(hass)
        meta = studio_marker_positions(plan) if isinstance(plan, dict) else None
        for dev in model.get("devices") or []:
            did = str(dev.get("device_id") or "")
            if not did:
                continue
            domain = get_domain(dev)
            captions[did] = [
                [eid, sfx]
                for eid, sfx in caption_pairs_for_device(
                    dev, options, marker_meta_for_device(dev, meta)
                )
            ]
            choices[did] = [
                [str(e["entity_id"]), caption_suffix_for(str(e["entity_id"]), domain)]
                for e in dev.get("entities") or []
                if e.get("entity_id")
            ]
    except Exception as err:  # pragma: no cover - model needs registries
        _LOGGER.debug("device captions unavailable: %s", err)

    connection.send_result(
        msg["id"],
        {
            "svg_mode": options.get(OPTION_SVG_MODE),
            "custom_svg_path": options.get(OPTION_CUSTOM_SVG_PATH),
            "editor": adapter.key,
            "editor_caps": {
                field: getattr(adapter.capabilities, field)
                for field in (
                    "marker_icons",
                    "marker_colors",
                    "marker_actions",
                    "multi_entity",
                    "stamp_extras",
                    "browser_side",
                    "card_element",
                    "panel_element",
                    "panel_module",
                )
            },
            "editor_url": adapter.capabilities.editor_url or editor_url(options),
            "editor_option": options.get(OPTION_EDITOR),
            "editors_available": available,
            "toolbar_enabled": options.get(OPTION_TOOLBAR_ENABLED),
            "device_zones": options.get(OPTION_DEVICE_ZONES, {}),
            "device_view_url": options.get(OPTION_DEVICE_VIEW_URL, ""),
            "device_captions": captions,
            "caption_choices": choices,
        },
    )


@websocket_api.websocket_command(
    {
        vol.Required("type"): "ramses_extras/floorplan_helper/get_project",
        vol.Optional("editor"): str,
    }
)
@websocket_api.async_response
async def ws_get_project(
    hass: HomeAssistant, connection: ActiveConnection, msg: dict[str, Any]
) -> None:
    """Return the resolved editor's stored plan (canonical JSON)."""
    entry = _config_entry(hass)
    options = get_floorplan_options(entry) if entry is not None else None
    adapter = await resolve_editor(hass, options, msg.get("editor"))
    plan = await adapter.async_load(hass)
    if plan is None:
        connection.send_error(
            msg["id"],
            "no_project",
            f"No stored {adapter.name} plan",
        )
        return
    connection.send_result(
        msg["id"],
        {"project_json": json.dumps(plan), "editor": adapter.key},
    )


__all__ = [
    "ws_get_bundle",
    "ws_get_config",
    "ws_get_project",
    "ws_get_topology",
    "ws_list_icons",
]
