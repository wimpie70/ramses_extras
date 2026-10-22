"""Floorplan Helper feature options flow.

Only feature-wide knobs live here (exported toolbar, studio URL).
Everything spatial or per-device — drawing SVG paths, marker
positions, icon/colours/label/actions, zone membership, captions —
belongs to the floorplan-studio project or the actions card's own
YAML/editor, which is the single source of truth. Stored
``icon_overrides``/``caption_overrides``/``marker_style_overrides``/
``caption_fields`` options still apply as a fallback for elements
without a marker, and are migrated into the project on the next export.

Follows the feature config flow contract: exposes
``async_step_floorplan_helper_config(flow, user_input)`` which the main
options flow delegates to once ``_selected_feature`` is set.

:platform: Home Assistant
:feature: Floorplan Helper
"""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.helpers import selector

from .const import (
    DEFAULT_EDITOR_URL,
    OPTION_EDITOR_URL,
    OPTION_TOOLBAR_ENABLED,
)
from .mapping import get_floorplan_options, persist_floorplan_options

_LOGGER = logging.getLogger(__name__)


async def async_step_floorplan_helper_config(
    flow: Any, user_input: dict[str, Any] | None = None
) -> Any:
    """Floorplan Helper configuration step.

    :param flow: The main options-flow handler instance
    :param user_input: Submitted form data (or None on first display)
    :return: ConfigFlowResult
    """
    config_entry = flow._config_entry  # noqa: SLF001
    options = get_floorplan_options(config_entry)

    if user_input is not None:
        section = dict(options)
        section[OPTION_TOOLBAR_ENABLED] = bool(user_input.get("toolbar_enabled", True))
        section[OPTION_EDITOR_URL] = (
            user_input.get("editor_url") or DEFAULT_EDITOR_URL
        ).strip()
        persist_floorplan_options(flow.hass, config_entry, section)
        _LOGGER.info("Floorplan Helper options saved")
        return await flow.async_step_main_menu()

    info_text = (
        "🗺️ **Floorplan Helper**\n\n"
        "Compiles the floorplan-studio project into the floorplan card "
        "bundle (merged SVG, CSS, rules YAML). The project is the "
        "single source of truth — marker icon, colours, label, "
        "actions, zone and caption are edited on the marker in "
        "studio or per device in the actions card's ⚙ panel.\n\n"
        "Place a `ramses-floorplan-actions` card next to the studio "
        "card on the same dashboard view — its buttons drive the "
        "workflow (store, seed, export, update cards) and its "
        "`floors:` config names the drawing SVG per floor, so "
        "different maps can live on different views."
    )

    schema = vol.Schema(
        {
            vol.Optional(
                "toolbar_enabled",
                default=options.get(OPTION_TOOLBAR_ENABLED, True),
            ): selector.BooleanSelector(),
            vol.Optional(
                "editor_url",
                default=options.get(OPTION_EDITOR_URL) or DEFAULT_EDITOR_URL,
            ): selector.TextSelector(selector.TextSelectorConfig(multiline=False)),
        }
    )

    return flow.async_show_form(
        step_id="feature_config",
        data_schema=schema,
        description_placeholders={"info": info_text},
    )


__all__ = ["async_step_floorplan_helper_config"]
