"""Floorplan Helper feature options flow.

One knob lives here: which plan editor owns the map (``editor`` —
``auto`` resolves to whichever installed editor already holds a plan).
Everything spatial or per-device — marker positions, icon/colours/
label/actions, zone membership, captions — belongs to the editor's
plan or the actions card's own YAML, which is the single source of
truth. Stored ``icon_overrides``/``caption_overrides``/
``marker_style_overrides``/``caption_fields`` options still apply as a
fallback for elements without a marker, and are migrated into the
project on the next export.

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
from homeassistant.helpers.selector import (
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .const import OPTION_EDITOR
from .editors import editor_keys
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
    if user_input is not None:
        options = get_floorplan_options(flow._config_entry)
        options[OPTION_EDITOR] = user_input.get(OPTION_EDITOR) or "auto"
        persist_floorplan_options(flow.hass, flow._config_entry, options)
        _LOGGER.info(
            "Floorplan Helper options saved (editor=%s)", options[OPTION_EDITOR]
        )
        return await flow.async_step_main_menu()

    current = get_floorplan_options(flow._config_entry).get(OPTION_EDITOR, "auto")
    info_text = (
        "🗺️ **Floorplan Helper**\n\n"
        "Compiles the editor's plan into a floorplan card "
        "bundle (SVG, CSS, rules YAML). The plan is the "
        "single source of truth — marker icon, colours, label, "
        "actions, zone and caption are edited in the editor "
        "or per device in the actions card's ⚙ panel.\n\n"
        "After adapting the plan, use the actions card's "
        "**Export ⇒** button to copy the generated card YAML, then "
        "create a floorplan card with it on the dashboard page where "
        "the map should appear. Place the actions card itself next "
        "to the editor card on the same view.\n\n"
        "For everything else, see the wiki on GitHub: "
        "https://github.com/wimpie70/ramses_extras/wiki"
    )

    schema = vol.Schema(
        {
            vol.Required(OPTION_EDITOR, default=current): SelectSelector(
                SelectSelectorConfig(
                    options=[
                        {
                            "value": "auto",
                            "label": "Auto — whichever installed editor holds the plan",
                        },
                        {
                            "value": "studio",
                            "label": "Floorplan Studio (card, browser-side projects)",
                        },
                        {
                            "value": "hfs",
                            "label": "ha-floorplan-studio (integration)",
                        },
                    ],
                    mode=SelectSelectorMode.DROPDOWN,
                )
            )
        }
    )

    return flow.async_show_form(
        step_id="feature_config",
        data_schema=schema,
        description_placeholders={"info": info_text},
    )


__all__ = ["async_step_floorplan_helper_config"]
